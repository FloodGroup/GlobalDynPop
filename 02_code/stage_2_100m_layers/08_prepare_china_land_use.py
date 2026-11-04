# -*- coding: utf-8 -*-
"""Stage 2, step 8 (China, no internet): the Amap AOIs of every Chinese city on its 100 m grid, as the area share
of seven AOI groups in every cell (land-use evidence before the Overture land use, 10_prepare_buildings_open_space.py).

    python 02_code/stage_2_100m_layers/s08_cnpoi.py aois --export <Amap export folder>      (first: the AOI pseudo-parcels)
    python 02_code/stage_2_100m_layers/s13b_landuse_aoi.py [--stems ...] [--overwrite]

Input: 01_inputs/restricted_NOT_PUBLIC/aoi_amap/<stem>.parquet (s08_cnpoi.py aois: the AOIs met by the reverse
geocoding of the own Amap download, as circular pseudo-parcels around the AOI centre covering the core 64 % of the AOI
area; classes C1 residential, C2 work and commerce, C3 education, C4 health care and public services, C5 leisure,
C6 transport; industrial flag). The parcels are painted on a 25 m sub-grid from the largest to the smallest, so that
where parcels overlap the smallest decides (as in gdp/buildings.py), and an industrial C2 parcel is counted as AOI_IND.
-> 01_inputs/basemap/land_use_aoi/<stem>.npz: uint8 arrays AOI_C1 ... AOI_C6, AOI_IND (number of the 16 sub-cells of the
   cell, 0-16) and meta. Aggregated to 100 m cells; the AOIs themselves stay in restricted_NOT_PUBLIC.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as config  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402

OUT = config.BASEMAP / "land_use_aoi"
SUB = 4
GROUPS = ["AOI_C1", "AOI_C2", "AOI_C3", "AOI_C4", "AOI_C5", "AOI_C6", "AOI_IND"]


def aoi_layer(row, f: Path):
    import geopandas as gpd
    import pyproj
    import rasterio.features
    import shapely
    from affine import Affine
    g = grid_of(row)
    a = gpd.read_parquet(f)
    if not len(a):
        return {}, {"aois": 0}
    cls = a["cls"].astype(str).to_numpy()
    ind = a["industrial"].astype(int).to_numpy().astype(bool) if "industrial" in a.columns else np.zeros(len(a), bool)
    grp = np.array(["AOI_IND" if (i and c == "C2") else f"AOI_{c}" for c, i in zip(cls, ind)], dtype=object)
    ok = np.isin(grp, GROUPS)
    geoms = a.geometry.values[ok]
    grp = grp[ok]
    if not len(geoms):
        return {}, {"aois": 0}
    tr = pyproj.Transformer.from_crs(a.crs or 4326, g.crs, always_xy=True)
    geoms = shapely.transform(np.asarray(geoms), lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    geoms = shapely.make_valid(geoms)
    geoms = shapely.intersection(geoms, shapely.box(*g.bounds()))
    keep = ~shapely.is_empty(geoms) & (shapely.area(geoms) > 0)
    geoms, grp = geoms[keep], grp[keep]
    if not len(geoms):
        return {}, {"aois": 0}
    order = np.argsort(-shapely.area(geoms))                  # largest first: the smallest parcel decides
    val = np.array([GROUPS.index(x) + 1 for x in grp], np.uint8)
    transform = Affine(g.cell / SUB, 0, g.x0, 0, -g.cell / SUB, g.y1)
    M = rasterio.features.rasterize(((geoms[i], int(val[i])) for i in order), out_shape=(g.ny * SUB, g.nx * SUB),
                                    transform=transform, fill=0, dtype="uint8")
    M = M.reshape(g.ny, SUB, g.nx, SUB).transpose(0, 2, 1, 3).reshape(g.ny, g.nx, SUB * SUB)
    out, info = {}, {"aois": int(len(geoms)), "groups": {}}
    for k, code in enumerate(GROUPS, start=1):
        cnt = (M == k).sum(axis=2).astype(np.uint8)
        if cnt.any():
            out[code] = cnt
            info["groups"][code] = {"parcels": int((grp == code).sum()),
                                    "km2": round(float(cnt.sum()) / 16 * g.cell ** 2 / 1e6, 3)}
    return out, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    c = load_cities()
    if a.stems:
        c = c[c.stem.isin(a.stems)]
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for row in c.to_dict("records"):
        f = config.AOI_AMAP / f"{row['stem']}.parquet"
        o = OUT / f"{row['stem']}.npz"
        if not f.exists() or (o.exists() and not a.overwrite):
            continue
        t0 = time.time()
        arrs, info = aoi_layer(row, f)
        np.savez_compressed(o, meta=np.array(json.dumps({"source": "Amap AOI pseudo-parcels (s08_cnpoi.py aois)",
                                                         "sub_cells": SUB * SUB, **info})), **arrs)
        n += 1
        print(json.dumps({"stem": row["stem"], "aois": info.get("aois", 0), "s": round(time.time() - t0, 1)}), flush=True)
    print(json.dumps({"cities": n}), flush=True)


if __name__ == "__main__":
    main()
