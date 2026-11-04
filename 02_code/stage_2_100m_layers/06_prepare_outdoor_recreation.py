# -*- coding: utf-8 -*-
"""Stage 2, step 6 (local raw subsets or provider sources): outdoor recreation land use on the 100 m grid of every city.

    python 02_code/stage_2_100m_layers/06_prepare_outdoor_recreation.py [--stems ...] [--shard k/n] [--out 01_inputs/basemap/outdoor]

Overture Maps release 2026-10-21.0, theme base, type land_use (OpenStreetMap landuse / leisure polygons, ODbL):
parks (park, dog park, village green), all recreation land use (pitches, playgrounds, recreation grounds, sports tracks,
stadiums, ...), pedestrian areas and squares, gardens and allotments, golf courses, zoos, theme and water parks and camp
sites; rasterised at 25 m and averaged to the 100 m grid of the city, as the water layer (make_basemap.py).
-> 01_inputs/basemap/outdoor/<stem>.npz: outdoor (uint8, per cent of the cell), meta (JSON)
Used by the model (gdp.model.attractor_layer: a share outdoor_w of the leisure and other destinations on this land, in
proportion to its area) and by the land-use classes (s10_land_use.py, class 13 parks and recreation grounds).
"""
import argparse, json, os, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as config  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402
from stage_2_100m_layers.overture_base import Reader, LocalReader  # noqa: E402

if os.environ.get("GDP_CA_BUNDLE"):
    os.environ.setdefault("AWS_CA_BUNDLE", os.environ["GDP_CA_BUNDLE"])
OUT = config.BASEMAP / "outdoor"

SUB = 4
ALL_SUBTYPES = {"park", "recreation", "pedestrian"}
PAIRS = {("golf", "golf_course"), ("horticulture", "garden"), ("horticulture", "allotments"), ("entertainment", "zoo"),
         ("entertainment", "theme_park"), ("entertainment", "water_park"), ("campground", "camp_site")}


def outdoor_layer(reader, row):
    import pyproj, rasterio.features, shapely
    from affine import Affine
    g = grid_of(row)
    tab, nrg = reader.read_bbox(*g.lonlat_bounds(0.0), cols=("geometry", "subtype", "class", "bbox"))
    Wm = np.zeros((g.ny * SUB, g.nx * SUB), np.uint8)
    info = {"features": 0, "classes": {}}
    if tab is not None and tab.num_rows:
        st = np.array(tab.column("subtype").to_pylist(), dtype=object)
        cl = np.array(tab.column("class").to_pylist(), dtype=object)
        keep = np.array([(s in ALL_SUBTYPES) or ((s, c) in PAIRS) for s, c in zip(st, cl)], bool)
        if keep.any():
            geoms = shapely.from_wkb(np.array(tab.column("geometry").to_pylist(), dtype=object)[keep])
            tr = pyproj.Transformer.from_crs(4326, g.crs, always_xy=True)
            geoms = shapely.transform(geoms, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
            geoms = shapely.make_valid(geoms)
            box = shapely.box(*g.bounds())
            geoms = [x for x in shapely.intersection(geoms, box) if not x.is_empty and x.area > 0]
            if geoms:
                transform = Affine(g.cell / SUB, 0, g.x0, 0, -g.cell / SUB, g.y1)
                Wm = rasterio.features.rasterize(((x, 1) for x in geoms), out_shape=Wm.shape, transform=transform,
                                                 fill=0, dtype="uint8")
            kk = [f"{s}/{c}" for s, c in zip(st[keep], cl[keep])]
            u, n = np.unique(np.array(kk, dtype=str), return_counts=True)
            info = {"features": int(keep.sum()), "classes": {str(a): int(b) for a, b in zip(u, n)}}
    frac = Wm.reshape(g.ny, SUB, g.nx, SUB).mean((1, 3))
    return np.round(frac * 100).astype(np.uint8), info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT)); ap.add_argument("--stems", nargs="*"); ap.add_argument("--shard", default="0/1")
    ap.add_argument("--local-raw", action="store_true", help="Use bundled raw subsets without network access")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    c = load_cities().set_index("stem")
    stems = a.stems or list(c.index)
    k, n = (int(x) for x in a.shard.split("/"))
    stems = stems[k::n]
    reader = None if a.local_raw else Reader("base", "land_use")
    for stem in stems:
        f = out / f"{stem}.npz"
        if f.exists() and not a.overwrite:
            continue
        t0 = time.time()
        for attempt in range(3):
            try:
                row = c.loc[stem].to_dict(); row["stem"] = stem
                q, info = outdoor_layer(LocalReader(stem, "land_use") if a.local_raw else reader, row)
                break
            except Exception as e:  # noqa: BLE001
                if a.local_raw:
                    raise
                if attempt == 2:
                    print(json.dumps({"stem": stem, "error": repr(e)[:300]}), flush=True); q = None
                time.sleep(5)
        if q is None:
            continue
        meta = {"stem": stem, "source": "Overture Maps 2026-10-21.0, theme base, type land_use (outdoor recreation)",
                "cell_m": 100, "subcells": SUB, **info}
        tmp = f.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, outdoor=q, meta=json.dumps(meta))
        tmp.replace(f)
        print(json.dumps({"stem": stem, "features": info["features"], "share": round(float(q.mean()) / 100, 4),
                          "s": round(time.time() - t0, 1)}), flush=True)


if __name__ == "__main__":
    main()
