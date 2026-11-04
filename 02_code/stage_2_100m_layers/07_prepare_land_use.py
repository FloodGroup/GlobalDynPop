# -*- coding: utf-8 -*-
"""Stage 2, step 7 (local raw subsets or provider sources): land-use polygons of Overture Maps on the 100 m grid of
every city, as the area share of 15 land-use groups in every cell.

    python 02_code/stage_2_100m_layers/07_prepare_land_use.py [--stems ...] [--stems-file f] [--shard k/n] [--out 01_inputs/basemap/land_use]
                                                   [--no-cache]

Overture Maps release 2026-10-21.0, theme base, type land_use (OpenStreetMap landuse, leisure, amenity and other
polygons, ODbL), and the parking lots of type infrastructure (subtype transit, class parking / parking_space). Every
polygon is assigned to a group by its subtype and class (GROUP_OF below); the polygons are
painted on a 25 m sub-grid in the order of PRIORITY, so that a more specific polygon (a school, a park, a square)
replaces a more general one beneath it (a residential area), and every 100 m cell gets the share of its 16 sub-cells
in each group.

-> 01_inputs/basemap/land_use/<stem>.npz: one uint8 array per group present (number of the 16 sub-cells of the cell,
   0-16; share = value / 16) and meta (JSON: release, features and area by group, sub-grid)
Used by the land-use layer (03_classify_functional_land_use.py), the use of buildings without use evidence (10_prepare_buildings_open_space.py) and the
outdoor pool of the destinations (gdp.model.attractor_layer).
The row groups read are kept in 04_intermediate/cache/overture_base/ (neighbouring cities share many of them; the
folder can be deleted afterwards).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as config  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402
from stage_2_100m_layers.overture_base import Reader, LocalReader  # noqa: E402

if os.environ.get("GDP_CA_BUNDLE"):
    os.environ.setdefault("AWS_CA_BUNDLE", os.environ["GDP_CA_BUNDLE"])
OUT = config.BASEMAP / "land_use"
SUB = 4

# groups, painted from the first (lowest priority) to the last
PRIORITY = ["AGR", "NAT", "GRS", "DEV", "RES", "COM", "IND", "PUB", "CEM", "TRN", "CON", "MED", "EDU", "PRK", "REC",
            "PARK", "PED"]
NAMES = {"AGR": "agriculture and horticulture", "NAT": "protected and natural areas", "GRS": "managed grass",
         "DEV": "developed, other or unspecified", "RES": "residential", "COM": "commercial and retail",
         "IND": "industrial, works, extraction, landfill", "PUB": "institutional, religious, military",
         "CEM": "cemeteries", "TRN": "transport land (railway, traffic islands)", "CON": "construction and brownfield",
         "MED": "hospitals and clinics", "EDU": "schools, universities, kindergartens", "REC": "sports and recreation "
         "(pitches, playgrounds, stadiums, golf, camping, zoos and theme parks)", "PARK": "parks and gardens",
         "PED": "pedestrian areas and squares", "PRK": "parking lots (Overture infrastructure, transit/parking)"}


def group_of(st, cl):
    st = st or ""
    cl = cl or ""
    if st in ("agriculture", "aquaculture"):
        return "AGR"
    if st == "horticulture":
        return "PARK" if cl in ("garden", "allotments", "flowerbed") else "AGR"
    if st == "residential":
        return "RES"
    if st == "developed":
        return {"commercial": "COM", "retail": "COM", "industrial": "IND", "works": "IND", "institutional": "PUB",
                "brownfield": "CON"}.get(cl, "DEV")
    if st in ("resource_extraction", "landfill"):
        return "IND"
    if st in ("religious", "military"):
        return "PUB"
    if st == "cemetery":
        return "CEM"
    if st == "education":
        return "EDU"
    if st == "medical":
        return "MED"
    if st == "transportation":
        return "TRN"
    if st == "construction":
        return "CON"
    if st in ("recreation", "golf", "campground", "winter_sports", "entertainment"):
        return "REC"
    if st == "park":
        return "PARK"
    if st == "pedestrian":
        return "PED"
    if st == "managed":
        return "GRS"
    if st == "protected":
        return "NAT"
    return None


def land_use_layer(reader, row, infra=None):
    import pyproj
    import rasterio.features
    import shapely
    from affine import Affine
    g = grid_of(row)
    out, info = {}, {"features": 0, "groups": {}}
    wkb, grp = [], []
    tab, nrg = reader.read_bbox(*g.lonlat_bounds(0.0), cols=("geometry", "subtype", "class", "bbox"))
    if tab is not None and tab.num_rows:
        gg = [group_of(a, b) for a, b in zip(tab.column("subtype").to_pylist(), tab.column("class").to_pylist())]
        for w, x in zip(tab.column("geometry").to_pylist(), gg):
            if x is not None:
                wkb.append(w); grp.append(x)
    if infra is not None:
        ti, _ = infra.read_bbox(*g.lonlat_bounds(0.0), cols=("geometry", "subtype", "class", "bbox"))
        if ti is not None and ti.num_rows:
            for w, a, b in zip(ti.column("geometry").to_pylist(), ti.column("subtype").to_pylist(), ti.column("class").to_pylist()):
                if a == "transit" and b in ("parking", "parking_space"):
                    wkb.append(w); grp.append("PRK")
    if not wkb:
        return out, info
    geoms = shapely.from_wkb(np.array(wkb, dtype=object))
    grp = np.array(grp, dtype=object)
    poly = np.isin(shapely.get_type_id(geoms), (3, 6))            # Polygon, MultiPolygon
    geoms, grp = geoms[poly], grp[poly]
    tr = pyproj.Transformer.from_crs(4326, g.crs, always_xy=True)
    geoms = shapely.transform(geoms, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    geoms = shapely.make_valid(geoms)
    box = shapely.box(*g.bounds())
    geoms = shapely.intersection(geoms, box)
    ok = ~shapely.is_empty(geoms) & (shapely.area(geoms) > 0)
    geoms, grp = geoms[ok], grp[ok]
    if not len(geoms):
        return out, info
    rank = np.array([PRIORITY.index(x) + 1 for x in grp], np.uint8)
    area = shapely.area(geoms)
    order = np.lexsort((-area, rank))                  # by priority, larger polygons first within a group
    transform = Affine(g.cell / SUB, 0, g.x0, 0, -g.cell / SUB, g.y1)
    M = rasterio.features.rasterize(((geoms[i], int(rank[i])) for i in order), out_shape=(g.ny * SUB, g.nx * SUB),
                                    transform=transform, fill=0, dtype="uint8")
    M = M.reshape(g.ny, SUB, g.nx, SUB).transpose(0, 2, 1, 3).reshape(g.ny, g.nx, SUB * SUB)
    for k, code in enumerate(PRIORITY, start=1):
        cnt = (M == k).sum(axis=2).astype(np.uint8)
        if cnt.any():
            out[code] = cnt
            info["groups"][code] = {"features": int((grp == code).sum()), "km2": round(float(cnt.sum()) / 16 * g.cell ** 2 / 1e6, 3)}
    info["features"] = int(len(geoms))
    return out, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--shard")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--no-cache", action="store_true", help="do not keep the row groups read on disk")
    ap.add_argument("--local-raw", action="store_true", help="Use bundled raw subsets without network access")
    a = ap.parse_args(argv)
    c = load_cities()
    stems = list(a.stems or [])
    if a.stems_file:
        stems += [l.strip() for l in open(a.stems_file, encoding="utf-8") if l.strip()]
    if stems:
        c = c[c.stem.isin(stems)]
    if a.shard:
        k, n = map(int, a.shard.split("/"))
        c = c.iloc[k::n]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = None if a.no_cache else config.CACHE / "overture_base"
    reader = None if a.local_raw else Reader("base", "land_use", cache=None if cache is None else cache / "land_use")
    infra = None if a.local_raw else Reader("base", "infrastructure", cache=None if cache is None else cache / "infrastructure")
    for row in c.sort_values("pop2025", ascending=False).to_dict("records"):
        f = out / f"{row['stem']}.npz"
        if f.exists() and not a.overwrite:
            continue
        t0 = time.time()
        for k in range(4):
            try:
                arrs, info = land_use_layer(LocalReader(row["stem"], "land_use") if a.local_raw else reader, row,
                                           LocalReader(row["stem"], "infrastructure") if a.local_raw else infra)
                break
            except Exception as e:  # noqa: BLE001
                if a.local_raw:
                    raise
                if k == 3:
                    print(json.dumps({"stem": row["stem"], "error": repr(e)}), flush=True)
                    arrs = None
                time.sleep(10 * (k + 1))
        if arrs is None:
            continue
        meta = {"release": config.OVERTURE_RELEASE, "sub_cells": SUB * SUB, "group_names": NAMES,
                "features": info["features"], "stats": info["groups"]}
        tmp = f.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, meta=np.array(json.dumps(meta)), **arrs)
        tmp.replace(f)
        print(json.dumps({"stem": row["stem"], "features": info["features"], "groups": len(arrs),
                          "s": round(time.time() - t0, 1)}), flush=True)


if __name__ == "__main__":
    main()
