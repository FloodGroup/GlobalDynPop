"""Stage 4, step 2: land use and functional zones of every city on the 100 m grid of the model, for exposure and risk analyses.

    python 02_code/stage_4_outputs/02_classify_functional_land_use.py [--stems ...] [--stems-file f] [--out 05_outputs/land_use] [--overwrite]
                                           [--order small|large|list] [--index-only]
    python 03_run/runtime/run_parallel.py --workers 4 --name land_use --then=--index-only -- 02_code/stage_4_outputs/02_classify_functional_land_use.py

Made from the inputs of the model only (no download): the floor area of the buildings by use
(04_intermediate/demo/stage_2/buildings/floor_area_by_use, Overture Maps and OpenBuildingMap buildings classified as in the model), the GHSL built
volume and its non-residential part (04_intermediate/demo/stage_2/buildings/total_building_volume*), the road and rail network of the routing
graph (04_intermediate/demo/stage_2/road_and_rail_graphs, Overture Maps transportation) and the water share of every cell
(04_intermediate/demo/stage_2/water_coverage_percent, Overture Maps base/water). Every cell gets the floor area of nine uses, the length of the
roads and rail lines by class, its water share and its rail stations (detail file), and one class (class file):

  class  name                              rule (first rule that applies)
   12    water                             water share >= 0.5 and floor area < 1,000 m2
   10    major road                        major roads >= 100 m (motorway to unclassified), floor area < 1,000 m2, rail shorter
   11    railway                           rail lines >= 100 m, floor area < 1,000 m2
   1-9   built-up: the use with the largest floor area, if the floor area is >= 500 m2 or the GHSL built volume
         >= 1,500 m3 (cells with GHSL volume but no mapped building: residential or 9 by the GHSL non-residential share)
           1 residential, 2 commercial and offices, 3 industrial, 4 education, 5 health care and public services,
           6 leisure, culture and sport, 7 transport facilities (stations, depots, airports), 8 other buildings,
           9 non-residential, use unknown
   13    open land                         all other cells (vegetation, farmland, bare land, unmapped)

The floor area of buildings without use evidence is split into a residential and a non-residential part with the GHSL
non-residential share of the built volume of the cell, as in the model (stage_3_activity_allocation.model.nonres_unknown); the industrial floor
area is the part of the commercial and industrial class in factories and warehouses. Road classes come from the
effective speeds of the routing graph (stage_3_activity_allocation.network.ROAD_KMH); local streets are the street length of the cell minus its
major roads. Cities without a water layer get a water share of 0 (column water_layer of the index).

-> <out>/<stem>/<stem>_functional_land_use.tif         class of every cell (uint8 with colour table; 0 = no data)
   <out>/<stem>/<stem>_functional_land_use_attributes.tif  16 bands (float32; band descriptions): floor area by use (m2, bands 1-9),
                                             road length by class (m, 10-12), local streets (m, 13), rail lines (m, 14),
                                             water (per cent of the cell, 15), rail stations (number, 16); LERC-ZSTD
                                             compressed, every value within 0.1 of the exact one
   <out>/functional_land_use_index.csv                 one row per city: area of every class (km2), floor area by use (km2),
                                             road and rail length (km), files
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402

OUT = configuration.OUTPUTS / "functional_land_use"
CLASSES = {1: "residential", 2: "commercial and offices", 3: "industrial", 4: "education",
           5: "health care and public services", 6: "leisure, culture and sport", 7: "transport facilities",
           8: "other buildings", 9: "non-residential, use unknown", 10: "major road", 11: "railway", 12: "water",
           13: "open land"}
COLOURS = {0: (255, 255, 255, 0), 1: (232, 193, 112, 255), 2: (214, 96, 77, 255), 3: (153, 112, 171, 255),
           4: (70, 130, 180, 255), 5: (102, 189, 186, 255), 6: (120, 180, 90, 255), 7: (110, 110, 110, 255),
           8: (196, 160, 130, 255), 9: (190, 150, 150, 255), 10: (40, 40, 40, 255), 11: (130, 60, 60, 255),
           12: (150, 190, 230, 255), 13: (238, 238, 226, 255)}
BANDS = ["floor_residential_m2", "floor_commercial_offices_m2", "floor_industrial_m2", "floor_education_m2",
         "floor_health_public_m2", "floor_leisure_m2", "floor_transport_m2", "floor_other_m2",
         "floor_nonres_unknown_m2", "road_motorway_trunk_m", "road_primary_secondary_m", "road_tertiary_unclassified_m",
         "street_local_m", "rail_m", "water_pct", "rail_stations"]
# road classes from the effective speeds of the routing graph (km/h, stage_3_activity_allocation/network.py ROAD_KMH)
ROAD_GROUP = {45.0: 0, 35.0: 0, 28.0: 1, 24.0: 1, 20.0: 2, 18.0: 2}
BUILT_FLOOR_M2 = 500.0          # a cell is built-up from this floor area ...
BUILT_VOLUME_M3 = 1500.0        # ... or this GHSL built volume
CORRIDOR_FLOOR_M2 = 1000.0      # water, road and rail cells have less floor area than this
CORRIDOR_LEN_M = 100.0          # road or rail length that makes a road or railway cell
WATER_SHARE = 0.5


def load_inputs(stem: str, g):
    """Floor area by use (9, ny, nx), GHSL volume and non-residential volume, routing graph, water share."""
    fa_f = configuration.FLOOR_AREA / f"{stem}.npz"
    if fa_f.exists():
        with np.load(fa_f) as z:
            fa = z["fa"].astype(np.float64)
    else:
        fa = np.zeros((9, g.ny, g.nx))
    vt = np.load(configuration.ghsl_file("vol", stem)).astype(np.float64) if configuration.ghsl_file("vol", stem).exists() else np.zeros(g.shape)
    vn = (np.load(configuration.ghsl_file("vol_nres", stem)).astype(np.float64) if configuration.ghsl_file("vol_nres", stem).exists()
          else np.zeros(g.shape))
    graph = None
    rf = configuration.ROAD_GRAPHS / f"{stem}.npz"
    if rf.exists():
        with np.load(rf, allow_pickle=False) as z:
            graph = {k: z[k] for k in ("p_len", "p_time", "p_rail", "s_n", "s_cell", "street", "stations")}
    wf = configuration.WATER_COVERAGE_PERCENT / f"{stem}.npz"
    water, has_water = np.zeros(g.shape), False
    if wf.exists():
        with np.load(wf) as z:
            water, has_water = z["water"].astype(np.float64) / 100.0, True
    return fa, vt, vn, graph, water, has_water


def layers(stem: str, g):
    """The 16 detail bands (16, ny, nx) and the class of every cell (ny, nx)."""
    fa, vt, vn, graph, water, has_water = load_inputs(stem, g)
    ny, nx = g.shape
    r_nres = np.where(vt > 0, np.clip(vn / np.where(vt > 0, vt, 1.0), 0.0, 1.0), 0.0)
    unk = fa[7]
    D = np.zeros((len(BANDS), ny, nx))
    D[0] = fa[0] + unk * (1.0 - r_nres)            # residential (+ residential part of the unknown use)
    D[1] = np.maximum(fa[1] - fa[8], 0.0)          # commercial and offices: C2 without the industrial part
    D[2] = fa[8]                                   # industrial
    D[3:8] = fa[2:7]                               # education, health and public, leisure, transport, other
    D[8] = unk * r_nres                            # non-residential part of the unknown use
    if graph is not None and len(graph["p_len"]):
        n = graph["s_n"].astype(np.int64)
        piece = np.repeat(np.arange(len(n)), n)
        cell = graph["s_cell"].astype(np.int64)
        step = np.where(n > 0, graph["p_len"] / np.maximum(n, 1), 0.0)[piece]
        speed = np.round(graph["p_len"] / np.maximum(graph["p_time"], 1e-12) / 1000.0, 1)
        rail = graph["p_rail"].astype(bool)
        grp = np.array([3 if rl else ROAD_GROUP.get(float(s), 2) for s, rl in zip(speed, rail)])[piece]
        ok = (cell >= 0) & (cell < ny * nx)
        for j, band in ((0, 9), (1, 10), (2, 11), (3, 13)):
            m = ok & (grp == j)
            D[band] = np.bincount(cell[m], weights=step[m], minlength=ny * nx).reshape(ny, nx)
        D[12] = np.maximum(graph["street"] - D[9] - D[10] - D[11], 0.0)
        st = graph["stations"]
        if len(st):
            r, c = g.index(st[:, 0], st[:, 1])
            k = r >= 0
            np.add.at(D[15], (r[k], c[k]), 1.0)
    D[14] = water * 100.0                          # per cent of the cell
    floor = D[0:9].sum(0)
    road = D[9:12].sum(0)
    cls = np.full((ny, nx), 13, np.uint8)
    built = (floor >= BUILT_FLOOR_M2) | (vt >= BUILT_VOLUME_M3)
    use = np.argmax(D[0:9], axis=0).astype(np.uint8) + 1
    ghsl_only = built & (floor <= 0)
    use = np.where(ghsl_only, np.where(r_nres >= 0.5, 9, 1), use).astype(np.uint8)
    cls[built] = use[built]
    low = floor < CORRIDOR_FLOOR_M2
    cls[low & (road >= CORRIDOR_LEN_M) & (road >= D[13])] = 10
    cls[low & (D[13] >= CORRIDOR_LEN_M) & (D[13] > road)] = 11
    cls[low & (water >= WATER_SHARE)] = 12
    return D.astype(np.float32), cls, has_water


def write(stem: str, g, D, cls, has_water, out: Path):
    import rasterio
    od = out / stem
    od.mkdir(parents=True, exist_ok=True)
    base = dict(driver="GTiff", height=g.ny, width=g.nx, crs=g.crs.to_wkt(), transform=g.transform(), tiled=True,
                blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
    f1, f2 = od / f"{stem}_functional_land_use.tif", od / f"{stem}_functional_land_use_attributes.tif"
    t1, t2 = f1.with_suffix(".tmp.tif"), f2.with_suffix(".tmp.tif")
    with rasterio.open(t1, "w", **base, count=1, dtype="uint8", nodata=0, compress="DEFLATE", zlevel=6) as dst:
        dst.write(cls, 1)
        dst.write_colormap(1, COLOURS)
        dst.set_band_description(1, "land_use_class")
        dst.update_tags(classes=json.dumps(CLASSES), units="class code", source="02_code/stage_4_outputs/02_classify_functional_land_use.py",
                        water_layer=str(has_water).lower())
    try:                                     # LERC: every value within 0.1 of the exact one (m2, m, per cent, stations)
        dst = rasterio.open(t2, "w", **base, count=len(BANDS), dtype="float32", nodata=None, compress="LERC_ZSTD",
                            max_z_error=0.1)
    except Exception:                        # a GDAL without LERC: lossless DEFLATE
        dst = rasterio.open(t2, "w", **base, count=len(BANDS), dtype="float32", nodata=None, compress="DEFLATE", predictor=3,
                            zlevel=6)
    with dst:
        dst.write(D)
        for i, b in enumerate(BANDS, 1):
            dst.set_band_description(i, b)
        dst.update_tags(bands=json.dumps(BANDS), source="02_code/stage_4_outputs/02_classify_functional_land_use.py", water_layer=str(has_water).lower(),
                        units="floor area m2 per cell, length m per cell, water per cent of the cell, stations per cell",
                        precision="LERC_ZSTD, every value within 0.1 of the exact value (rail_stations: round to integers)")
    t1.replace(f1); t2.replace(f2)
    return f1, f2


def index_row(stem: str, c, out: Path):
    import rasterio
    f1, f2 = out / stem / f"{stem}_functional_land_use.tif", out / stem / f"{stem}_functional_land_use_attributes.tif"
    if not (f1.exists() and f2.exists()):
        return None
    with rasterio.open(f1) as s:
        cls = s.read(1)
        wl = s.tags().get("water_layer", "")
    with rasterio.open(f2) as s:
        sums = [float(s.read(i).sum(dtype=np.float64)) for i in range(1, s.count + 1)]
    cell_km2 = 0.01
    rec = {"stem": stem, "name": c.loc[stem, "name"], "iso3": c.loc[stem, "iso3"], "nx": int(c.loc[stem, "nx"]),
           "ny": int(c.loc[stem, "ny"])}
    cnt = np.bincount(cls.ravel(), minlength=14)
    for k, name in CLASSES.items():
        rec[f"area_km2_{k:02d}_{name.split(',')[0].replace(' ', '_')}"] = round(float(cnt[k]) * cell_km2, 2)
    for i, b in enumerate(BANDS[:9]):
        rec[b[:-3] + "_km2"] = round(sums[i] / 1e6, 3)                 # floor_..._m2 -> floor_..._km2
    for i, b in enumerate(BANDS[9:14], 9):
        rec[b[:-2] + "_km"] = round(sums[i] / 1e3, 1)                  # ..._m -> ..._km
    rec["water_km2"] = round(sums[14] / 100.0 * cell_km2, 2)
    rec["rail_stations"] = int(round(sums[15]))
    rec["water_layer"] = wl
    rec["file_classes"] = f"functional_land_use/{stem}/{f1.name}"
    rec["file_detail"] = f"functional_land_use/{stem}/{f2.name}"
    return rec


def write_index(out: Path, c):
    import pandas as pd
    rows = [r for r in (index_row(p.name, c, out) for p in sorted(out.iterdir()) if p.is_dir() and p.name in c.index)
            if r is not None]
    if rows:
        pd.DataFrame(rows).sort_values("stem").to_csv(out / "functional_land_use_index.csv", index=False, encoding="utf-8-sig")
    print(json.dumps({"index": "functional_land_use_index.csv", "cities": len(rows)}), flush=True)


def main(argv=None):
    import work_queue as work_queue
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--order", choices=["small", "large", "list"], default="small")
    ap.add_argument("--index-only", action="store_true", help="only write functional_land_use_index.csv from the existing files")
    a = ap.parse_args(argv)
    c = load_cities().set_index("stem")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.index_only:
        write_index(out, c)
        return 0
    stems = list(a.stems or [])
    if a.stems_file:
        stems += [l.strip() for l in open(a.stems_file, encoding="utf-8") if l.strip()]
    if not stems:
        stems = list(c.index)
    if a.order != "list":
        stems = sorted(stems, key=lambda s: int(c.loc[s, "nx"]) * int(c.loc[s, "ny"]), reverse=(a.order == "large"))
    for k, stem in enumerate(stems, 1):
        f1 = out / stem / f"{stem}_functional_land_use.tif"
        if f1.exists() and (out / stem / f"{stem}_functional_land_use_attributes.tif").exists() and (
                not a.overwrite or work_queue.written_in_this_run(f1)):
            continue
        lock = work_queue.claim(out, stem)
        if lock is None:
            continue
        try:
            row = c.loc[stem].to_dict(); row["stem"] = stem
            g = grid_of(row)
            D, cls, has_water = layers(stem, g)
            write(stem, g, D, cls, has_water, out)
            cnt = np.bincount(cls.ravel(), minlength=14)
            print(json.dumps({"k": k, "stem": stem, "built_km2": round(float(cnt[1:10].sum()) * 0.01, 1),
                              "road_km2": round(float(cnt[10]) * 0.01, 1), "water_km2": round(float(cnt[12]) * 0.01, 1),
                              "water_layer": has_water}), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"stem": stem, "error": f"{type(e).__name__}: {e}"}), flush=True)
        finally:
            work_queue.release(lock)
    if not os.environ.get("DYNAMIC_POPULATION_WORKER"):
        write_index(out, c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
