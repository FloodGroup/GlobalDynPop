"""Step 10: land use and functional zones of every city on the 100 m grid of the model, for exposure and risk analyses.

    python 02_code/scripts/s10_land_use.py [--stems ...] [--stems-file f] [--out 05_outputs/land_use] [--overwrite]
                                           [--order small|large|list] [--index-only]
    python 02_code/scripts/run_parallel.py --workers 4 --name land_use --then=--index-only -- 02_code/scripts/s10_land_use.py

Made from the inputs of the model only (no download): the floor area of the buildings by use (
01_inputs/buildings/floor_area_by_use, GlobalBuildingAtlas floor area with the use of the Overture Maps and OpenBuildingMap
buildings and of the land use, 10_prepare_buildings_open_space.pyb: 01_inputs/buildings/floor_area), the building
volume (GlobalBuildingAtlas, 01_inputs/buildings/gba_cells; GHSL built volume where it has none) and the GHSL
non-residential share (01_inputs/buildings/ghs_built_volume*), the open space of every cell by type
(01_inputs/basemap/open_space), the land-use groups of Overture Maps and, in China, of the Amap AOIs
(01_inputs/basemap/land_use, land_use_aoi), the road and rail network of the routing
graph (01_inputs/road_network, Overture Maps transportation), the permanent water and land cover of every cell
(01_inputs/basemap/landcover, s11_landcover.py: permanent water where at least two of ESA WorldCover 2021, JRC Global
Surface Water 1984-2021 and OpenStreetMap water polygons not flagged as intermittent agree; WorldCover land cover of the
rest) and its outdoor recreation land (01_inputs/basemap/outdoor, Overture Maps land use: parks, playgrounds, sports
grounds, squares, gardens). Every cell gets the floor area of nine uses, the length of the roads and rail lines by
class, its permanent water, its rail stations, its outdoor recreation land and its land cover (detail file), and one
class (class file):

  class  name                          rule (first rule that applies)
    6    permanent water               permanent water share >= 0.5 and floor area < 1,000 m2
    5    other built-up land           major roads or rail lines >= 100 m and floor area < 1,000 m2 (road and rail
                                       corridors), or a built-up cell whose largest use is health care and public
                                       services, transport facilities, other buildings or non-residential of unknown use
  1-4    built-up: the group with the largest floor area, if the floor area is >= 500 m2 or the building volume
         >= 1,500 m3 (GlobalBuildingAtlas floor area and volume, 10_prepare_buildings_open_space.py; cells with a
         volume but no floor area by use: residential or 5 by the non-residential share of the built volume)
           1 residential, 2 commercial and industrial, 3 education, 4 leisure, culture and sport
    7    open land                     all other cells: parks, sports grounds, squares, parking lots, school and
                                       hospital grounds, construction sites, cemeteries, farmland, trees, shrubs and
                                       grassland, wetlands, bare land

The seven classes are the land-use groups of the analyses (residential, commercial and industrial, education, leisure,
other built-up land, and land that is not built up: permanent water, open land). The detail of every cell (floor area
by use, roads, water, building footprint, volume and height, open space by type, land cover) is in the detail file.

The floor area of buildings without use evidence is split into a residential and a non-residential part with the GHSL
non-residential share of the built volume of the cell, as in the model (gdp.model.nonres_unknown); the industrial floor
area is the part of the commercial and industrial class in factories and warehouses. Road classes come from the
effective speeds of the routing graph (gdp.network.ROAD_KMH); local streets are the street length of the cell minus its
major roads. Cities without a land-cover layer fall back on the Overture Maps water layer (01_inputs/basemap/cities) and
put their open land in class 7 (column water_layer of the index: landcover, overture or none).

-> <out>/<stem>/<stem>_land_use.tif         class of every cell (uint8 with colour table; 0 = no data)
   <out>/<stem>/<stem>_land_use_detail.tif  34 bands (float32; band descriptions): floor area by use (m2, bands 1-9),
                                             road length by class (m, 10-12), local streets (m, 13), rail lines (m, 14),
                                             permanent water (per cent of the cell, 15), rail stations (number, 16),
                                             outdoor recreation land (per cent, 17), cropland, trees / shrubs / grass,
                                             wetlands and seasonal water, bare / paved / other (per cent, 18-21);
                                             building footprint (per cent), volume (m3) and mean height (m)
                                             (22-24), open space by type: street surface, parking, squares, parks,
                                             managed grass, sports grounds, campus grounds, construction sites,
                                             cemeteries, other open land (per cent, 25-34);
                                             LERC-ZSTD compressed, every value within 0.1 of the exact one
   <out>/land_use_index.csv                 one row per city: area of every class (km2), floor area by use (km2),
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
import stage_1_data_inputs.configuration as config  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402

OUT = config.OUTPUTS / "functional_land_use"
CLASSES = {1: "residential", 2: "commercial and industrial", 3: "education", 4: "leisure, culture and sport",
           5: "other built-up land", 6: "permanent water", 7: "open land"}
COLOURS = {0: (255, 255, 255, 0), 1: (232, 193, 112, 255), 2: (214, 96, 77, 255), 3: (70, 130, 180, 255),
           4: (120, 180, 90, 255), 5: (160, 160, 160, 255), 6: (150, 190, 230, 255), 7: (226, 222, 205, 255)}
# floor-area bands (D[0:9]) of each built-up class: residential, commercial + industrial, education, leisure, other
GROUP_BANDS = {1: (0,), 2: (1, 2), 3: (3,), 4: (5,), 5: (4, 6, 7, 8)}
BANDS = ["floor_residential_m2", "floor_commercial_offices_m2", "floor_industrial_m2", "floor_education_m2",
         "floor_health_public_m2", "floor_leisure_m2", "floor_transport_m2", "floor_other_m2",
         "floor_nonres_unknown_m2", "road_motorway_trunk_m", "road_primary_secondary_m", "road_tertiary_unclassified_m",
         "street_local_m", "rail_m", "water_pct", "rail_stations", "outdoor_recreation_pct", "cropland_pct",
         "trees_shrubs_grass_pct", "wetland_seasonal_water_pct", "bare_paved_other_pct",
         # GlobalBuildingAtlas buildings and the open space of the cell by type (10_prepare_buildings_open_space.py)
         "building_footprint_pct", "building_volume_m3", "building_height_m", "street_surface_pct", "parking_pct",
         "plaza_pct", "park_pct", "managed_grass_pct", "sports_recreation_pct", "campus_grounds_pct",
         "construction_pct", "cemetery_pct", "other_open_land_pct"]
# road classes from the effective speeds of the routing graph (km/h, gdp/network.py ROAD_KMH)
ROAD_GROUP = {45.0: 0, 35.0: 0, 28.0: 1, 24.0: 1, 20.0: 2, 18.0: 2}
BUILT_FLOOR_M2 = 500.0          # a cell is built-up from this floor area ...
BUILT_VOLUME_M3 = 1500.0        # ... or this GHSL built volume
CORRIDOR_FLOOR_M2 = 1000.0      # water, road and rail cells have less floor area than this
CORRIDOR_LEN_M = 100.0          # road or rail length that makes a road or railway cell
WATER_SHARE = 0.5


def load_inputs(stem: str, g):
    """Floor area by use (9, ny, nx), GHSL volume and non-residential volume, routing graph, water share."""
    fa_f = config.FLOOR_AREA / f"{stem}.npz"
    if fa_f.exists():
        with np.load(fa_f) as z:
            fa = z["fa"].astype(np.float64)
    else:
        fa = np.zeros((9, g.ny, g.nx))
    vt = np.load(config.ghsl_file("vol", stem)).astype(np.float64) if config.ghsl_file("vol", stem).exists() else np.zeros(g.shape)
    vn = (np.load(config.ghsl_file("vol_nres", stem)).astype(np.float64) if config.ghsl_file("vol_nres", stem).exists()
          else np.zeros(g.shape))
    graph = None
    rf = config.ROAD_GRAPHS / f"{stem}.npz"
    if rf.exists():
        with np.load(rf, allow_pickle=False) as z:
            graph = {k: z[k] for k in ("p_len", "p_time", "p_rail", "s_n", "s_cell", "street", "stations")}
    water, has_water, lc = np.zeros(g.shape), "none", None
    lf = config.BASEMAP / "landcover" / f"{stem}.npz"           # permanent water and land cover (s11_landcover.py)
    wf = config.BASEMAP / "cities" / f"{stem}.npz"              # Overture Maps water only (fallback)
    if lf.exists():
        with np.load(lf) as z:
            water, has_water = z["pw"].astype(np.float64) / 100.0, "landcover"
            lc = z["lc"].astype(np.float64) / 100.0             # veg, crop, built, bare, wet, nodata (land part)
    elif wf.exists():
        with np.load(wf) as z:
            water, has_water = z["water"].astype(np.float64) / 100.0, "overture"
    outdoor = np.zeros(g.shape)
    qf = config.BASEMAP / "outdoor" / f"{stem}.npz"
    if qf.exists():
        with np.load(qf) as z:
            outdoor = z["outdoor"].astype(np.float64) / 100.0
    spatial_layers = {}
    gc_ = config.GBA_CELLS / f"{stem}.npz"                    # (10_prepare_buildings_open_space.py)
    if gc_.exists():
        with np.load(gc_) as z:
            spatial_layers.update({k: z[k].astype(np.float64) for k in ("foot_m2", "vol_m3", "h_mean")})
    os_ = config.OPEN_SPACE / f"{stem}.npz"
    if os_.exists():
        with np.load(os_) as z:
            spatial_layers["os"] = {k: z[k].astype(np.float64) for k in z.files if k != "meta"}
    src = {}
    for f in (config.BASEMAP / "land_use" / f"{stem}.npz", config.BASEMAP / "land_use_aoi" / f"{stem}.npz"):
        if f.exists():
            with np.load(f) as z:
                src.update({k: z[k].astype(np.float64) / 16.0 for k in z.files if k != "meta"})
    spatial_layers["src"] = src
    return fa, vt, vn, graph, water, has_water, lc, outdoor, spatial_layers


def layers(stem: str, g):
    """The 16 detail bands (16, ny, nx) and the class of every cell (ny, nx)."""
    fa, vt, vn, graph, water, has_water, lc, outdoor, spatial_layers = load_inputs(stem, g)
    ny, nx = g.shape
    r_nres = np.where(vt > 0, np.clip(vn / np.where(vt > 0, vt, 1.0), 0.0, 1.0), 0.0)
    if "vol_m3" in spatial_layers:          # GHSL non-residential share only where GHSL has a built volume (gdp.model)
        gv = spatial_layers["vol_m3"]
        ok = (vt > 0.25 * gv) & (gv > 0)
        if ok.sum() > 0.5 * max(int((gv > 0).sum()), 1):
            r_city = float(np.clip(vn[ok].sum() / max(vt[ok].sum(), 1e-9), 0.0, 1.0))
        else:
            known = fa[:7].sum()
            r_city = 1.0 - float(fa[0].sum()) / known if known > 0 else 0.3
        r_nres = np.where(ok, r_nres, r_city)
        vt = np.where(gv > 0, gv, vt)                    # built-up rule on the GlobalBuildingAtlas volume
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
    q = outdoor * (1.0 - water)                    # outdoor recreation land on the land part of the cell
    D[16] = q * 100.0
    if lc is not None:
        D[17] = lc[1] * 100.0                      # cropland
        D[18] = lc[0] * 100.0                      # trees, shrubs, grassland, moss
        D[19] = lc[4] * 100.0                      # wetland, mangroves, water not confirmed as permanent
        D[20] = (lc[3] + lc[2] + lc[5]) * 100.0    # bare / sparse, snow / ice, built-up surface, no data
    else:
        D[20] = (1.0 - water) * 100.0
    if "foot_m2" in spatial_layers:
        D[21] = np.clip(spatial_layers["foot_m2"] / g.cell ** 2, 0.0, 1.0) * 100.0
        D[22] = spatial_layers["vol_m3"]
        D[23] = spatial_layers["h_mean"]
    OS = spatial_layers.get("os", {})
    for band, k in ((24, "street"), (25, "parking"), (26, "plaza"), (27, "park"), (28, "grass"), (29, "rec"),
                    (30, "campus"), (31, "cons"), (33, "open")):
        if k in OS:
            D[band] = OS[k] * 100.0
    src = spatial_layers.get("src", {})
    if "CEM" in src:
        D[32] = src["CEM"] * (1.0 - D[21] / 100.0) * 100.0
    floor = D[0:9].sum(0)
    road = D[9:12].sum(0)
    cls = np.full((ny, nx), 7, np.uint8)            # open land
    built = (floor >= BUILT_FLOOR_M2) | (vt >= BUILT_VOLUME_M3)
    G = np.stack([sum(D[b] for b in GROUP_BANDS[k]) for k in (1, 2, 3, 4, 5)])
    use = np.argmax(G, axis=0).astype(np.uint8) + 1
    vol_only = built & (floor <= 0)
    use = np.where(vol_only, np.where(r_nres >= 0.5, 5, 1), use).astype(np.uint8)
    cls[built] = use[built]
    low = floor < CORRIDOR_FLOOR_M2
    cls[low & ((road >= CORRIDOR_LEN_M) | (D[13] >= CORRIDOR_LEN_M))] = 5
    cls[low & (water >= WATER_SHARE)] = 6
    return D.astype(np.float32), cls, has_water, None


def write(stem: str, g, D, cls, has_water, out: Path, S=None):
    import rasterio
    od = out / stem
    od.mkdir(parents=True, exist_ok=True)
    base = dict(driver="GTiff", height=g.ny, width=g.nx, crs=g.crs.to_wkt(), transform=g.transform(), tiled=True,
                blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
    f1, f2 = od / f"{stem}_land_use.tif", od / f"{stem}_land_use_detail.tif"
    t1, t2 = f1.with_suffix(".tmp.tif"), f2.with_suffix(".tmp.tif")
    with rasterio.open(t1, "w", **base, count=1, dtype="uint8", nodata=0, compress="DEFLATE", zlevel=6) as dst:
        dst.write(cls, 1)
        dst.write_colormap(1, COLOURS)
        dst.set_band_description(1, "land_use_class")
        dst.update_tags(classes=json.dumps(CLASSES), units="class code", source="02_code/scripts/s10_land_use.py",
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
        dst.update_tags(bands=json.dumps(BANDS), source="02_code/scripts/s10_land_use.py", water_layer=str(has_water).lower(),
                        units="floor area m2 per cell, length m per cell, volume m3 per cell, height m, permanent water, "
                              "outdoor recreation land, land cover, building footprint and open space per cent of the "
                              "cell, stations per cell",
                        precision="LERC_ZSTD, every value within 0.1 of the exact value (rail_stations: round to integers)")
    t1.replace(f1); t2.replace(f2)
    return f1, f2


def index_row(stem: str, c, out: Path):
    import rasterio
    f1, f2 = out / stem / f"{stem}_land_use.tif", out / stem / f"{stem}_land_use_detail.tif"
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
    cnt = np.bincount(cls.ravel(), minlength=len(CLASSES) + 1)
    for k, name in CLASSES.items():
        rec[f"area_km2_{k:02d}_{name.split(',')[0].replace(' ', '_')}"] = round(float(cnt[k]) * cell_km2, 2)
    for i, b in enumerate(BANDS[:9]):
        rec[b[:-3] + "_km2"] = round(sums[i] / 1e6, 3)                 # floor_..._m2 -> floor_..._km2
    for i, b in enumerate(BANDS[9:14], 9):
        rec[b[:-2] + "_km"] = round(sums[i] / 1e3, 1)                  # ..._m -> ..._km
    rec["water_km2"] = round(sums[14] / 100.0 * cell_km2, 2)
    rec["rail_stations"] = int(round(sums[15]))
    for i, b in enumerate(BANDS[16:21], 16):
        if i < len(sums):
            rec[b[:-4] + "_km2"] = round(sums[i] / 100.0 * cell_km2, 2)        # ..._pct -> ..._km2
    if len(sums) > 21:                                                     # Additional building statistics
        rec["building_footprint_km2"] = round(sums[21] / 100.0 * cell_km2, 2)
        rec["building_volume_km3"] = round(sums[22] / 1e9, 4)
        for i, b in enumerate(BANDS[24:], 24):
            rec[b[:-4] + "_km2"] = round(sums[i] / 100.0 * cell_km2, 2)
    rec["water_layer"] = wl
    rec["file_classes"] = f1.relative_to(out.parent).as_posix()
    rec["file_detail"] = f2.relative_to(out.parent).as_posix()
    return rec


def write_index(out: Path, c):
    import pandas as pd
    rows = [r for r in (index_row(p.name, c, out) for p in sorted(out.iterdir()) if p.is_dir() and p.name in c.index)
            if r is not None]
    if rows:
        pd.DataFrame(rows).sort_values("stem").to_csv(out / "land_use_index.csv", index=False, encoding="utf-8-sig")
    print(json.dumps({"index": "land_use_index.csv", "cities": len(rows)}), flush=True)


def main(argv=None):
    from stage_1_data_inputs import workqueue
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--order", choices=["small", "large", "list"], default="small")
    ap.add_argument("--index-only", action="store_true", help="only write land_use_index.csv from the existing files")
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
        f1 = out / stem / f"{stem}_land_use.tif"
        if f1.exists() and (out / stem / f"{stem}_land_use_detail.tif").exists() and (
                not a.overwrite or workqueue.written_in_this_run(f1)):
            continue
        lock = workqueue.claim(out, stem)
        if lock is None:
            continue
        try:
            row = c.loc[stem].to_dict(); row["stem"] = stem
            g = grid_of(row)
            D, cls, has_water, S = layers(stem, g)
            write(stem, g, D, cls, has_water, out, S)
            cnt = np.bincount(cls.ravel(), minlength=len(CLASSES) + 1)
            print(json.dumps({"k": k, "stem": stem, "km2": {CLASSES[i]: round(float(cnt[i]) * 0.01, 1) for i in CLASSES},
                              "water_layer": has_water}), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"stem": stem, "error": f"{type(e).__name__}: {e}"}), flush=True)
            raise
        finally:
            workqueue.release(lock)
    if not os.environ.get("GDP_WORKER"):
        write_index(out, c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
