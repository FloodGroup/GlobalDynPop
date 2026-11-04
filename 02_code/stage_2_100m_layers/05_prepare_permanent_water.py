# -*- coding: utf-8 -*-
"""Stage 2, step 5 (local raw subsets or provider sources): permanent water and land cover on the 100 m grid of every city.

    python 02_code/stage_2_100m_layers/05_prepare_permanent_water.py [--stems ...] [--shard k/n] [--out 01_inputs/basemap/landcover]

Three sources, sampled on a 20 m subgrid (5 x 5 subcells per 100 m cell) of the city grid:
  ESA WorldCover 2021 v200 (10 m, CC BY 4.0): 11 land-cover classes; class 80 'permanent water bodies' (water
      for more than nine months of the year).
  JRC Global Surface Water v1.4 1984-2021 (30 m), transitions layer: permanent water at the end of the period
      (classes 1 permanent, 2 new permanent, 7 seasonal to permanent), seasonal water (4 seasonal, 5 new seasonal,
      8 permanent to seasonal).
  Overture Maps 2026-10-21.0 base/water (OpenStreetMap water polygons, ODbL): polygons not flagged as
      intermittent; intermittent polygons kept apart.
A subcell is permanent water if at least two of the three sources mark it as such; where WorldCover has no tile
(open sea), if JRC GSW or OpenStreetMap does.

-> <out>/<stem>.npz (all uint8, per cent of the 100 m cell)
     pw    permanent water (consensus rule above)
     lc    6 bands, land cover of the subcells that are not permanent water (WorldCover classes):
           veg (tree 10, shrub 20, grass 30, moss and lichen 100), crop (cropland 40), built (built-up 50),
           bare (bare / sparse vegetation 60, snow and ice 70), wet (herbaceous wetland 90, mangroves 95, and water 80
           not confirmed as permanent by a second source: seasonal water, ponds), nodata (no WorldCover tile)
     src   5 bands, the sources: WorldCover permanent water (80), JRC GSW permanent water, JRC GSW seasonal water,
           OpenStreetMap water polygons not flagged as intermittent, intermittent OpenStreetMap water polygons
     meta  JSON
Used by the model (gdp.model.load_layers: destinations and people travelling are not placed on permanent water) and by
the land-use classes (s10_land_use.py). Behind a proxy: GDP_CA_BUNDLE = CA bundle of the proxy (GDAL and pyarrow).
"""
import argparse, json, math, os, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as config  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402
from stage_2_100m_layers.overture_base import Reader, LocalReader  # noqa: E402

SUB = 5
WC_URL = ("/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
          "ESA_WorldCover_10m_2021_v200_{}_Map.tif")
GSW_URL = ("/vsicurl/https://storage.googleapis.com/global-surface-water/downloads2021/transitions/"
           "transitions_{}v1_4_2021.tif")
ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
           GDAL_HTTP_MULTIRANGE='YES', GDAL_HTTP_MERGE_CONSECUTIVE_RANGES='YES', GDAL_HTTP_MAX_RETRY='6',
           GDAL_HTTP_RETRY_DELAY='3', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', VSI_CACHE='TRUE',
           VSI_CACHE_SIZE='100000000', GDAL_CACHEMAX=256, GDAL_HTTP_TIMEOUT='120')
LC_GROUPS = {"veg": (10, 20, 30, 100), "crop": (40,), "built": (50,), "bare": (60, 70), "wet": (80, 90, 95),
             "nodata": (0,)}
GSW_PERM, GSW_SEAS, GSW_NODATA = (1, 2, 7), (4, 5, 8), 255
if os.environ.get("GDP_CA_BUNDLE"):
    ENV["GDAL_CURL_CA_BUNDLE"] = os.environ["GDP_CA_BUNDLE"]
    os.environ.setdefault("AWS_CA_BUNDLE", os.environ["GDP_CA_BUNDLE"])
OUT = config.BASEMAP / "landcover"


def wc_tiles(lon0, lat0, lon1, lat1):
    for la in range(math.floor(lat0 / 3) * 3, math.floor(lat1 / 3) * 3 + 1, 3):
        for lo in range(math.floor(lon0 / 3) * 3, math.floor(lon1 / 3) * 3 + 1, 3):
            yield f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


def gsw_tiles(lon0, lat0, lon1, lat1):
    for top in range(math.floor(lat0 / 10) * 10 + 10, math.ceil(lat1 / 10) * 10 + 1, 10):
        for left in range(math.floor(lon0 / 10) * 10, math.floor(lon1 / 10) * 10 + 1, 10):
            yield f"{left}E_" if left >= 0 else f"{-left}W_", f"{top}N" if top >= 0 else f"{-top}S"


def warp_tiles(urls, g, fill):
    """Mosaic of the tiles on the 20 m subgrid of the city (nearest neighbour); `fill` where no tile has data."""
    import rasterio
    from affine import Affine
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    out = np.full((g.ny * SUB, g.nx * SUB), fill, np.uint8)
    tr = Affine(g.cell / SUB, 0, g.x0, 0, -g.cell / SUB, g.y1)
    used, missing = [], []
    for url in urls:
        for attempt in range(4):
            try:
                with rasterio.open(url) as src:
                    with WarpedVRT(src, crs=g.crs, transform=tr, width=out.shape[1], height=out.shape[0],
                                   resampling=Resampling.nearest, src_nodata=src.nodata, nodata=fill) as vrt:
                        a = vrt.read(1)
                m = a != fill
                out[m] = a[m]
                used.append(url.rsplit('/', 1)[-1]); break
            except Exception as e:  # noqa: BLE001
                s = str(e)
                if "404" in s or "does not exist" in s or "No such file" in s:
                    missing.append(url.rsplit('/', 1)[-1]); break
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
    return out, used, missing


def osm_water(reader, g):
    import pyproj, rasterio.features, shapely
    from affine import Affine
    tab, _ = reader.read_bbox(*g.lonlat_bounds(0.01), cols=("geometry", "subtype", "class", "is_intermittent", "bbox"))
    shape = (g.ny * SUB, g.nx * SUB)
    W, I = np.zeros(shape, np.uint8), np.zeros(shape, np.uint8)
    info = {"polygons": 0, "intermittent": 0, "subtypes": {}}
    if tab is None or not tab.num_rows:
        return W, I, info
    geoms = shapely.from_wkb(np.array(tab.column("geometry").to_pylist(), dtype=object))
    gt = shapely.get_type_id(geoms)
    poly = (gt == 3) | (gt == 6) | (gt == 7)
    if not poly.any():
        return W, I, info
    inter = np.array([bool(x) for x in tab.column("is_intermittent").to_pylist()])[poly]
    sub = np.array(tab.column("subtype").to_pylist(), dtype=object)[poly]
    geoms = geoms[poly]
    trf = pyproj.Transformer.from_crs(4326, g.crs, always_xy=True)
    geoms = shapely.transform(geoms, lambda xy: np.column_stack(trf.transform(xy[:, 0], xy[:, 1])))
    geoms = shapely.make_valid(geoms)
    box = shapely.box(*g.bounds())
    geoms = shapely.intersection(geoms, box)
    ok = ~shapely.is_empty(geoms) & (shapely.area(geoms) > 0)
    transform = Affine(g.cell / SUB, 0, g.x0, 0, -g.cell / SUB, g.y1)
    for target, sel in ((W, ok & ~inter), (I, ok & inter)):
        if sel.any():
            target[:] = rasterio.features.rasterize(((x, 1) for x in geoms[sel]), out_shape=shape, transform=transform,
                                                    fill=0, dtype="uint8")
    u, n = np.unique(np.array([str(s) for s in sub[ok]], dtype=str), return_counts=True)
    info = {"polygons": int((ok & ~inter).sum()), "intermittent": int((ok & inter).sum()),
            "subtypes": {str(a): int(b) for a, b in zip(u, n)}}
    return W, I, info


def share(mask, g):
    s = mask.reshape(g.ny, SUB, g.nx, SUB).sum((1, 3), dtype=np.uint16)
    return np.round(s * (100.0 / SUB ** 2)).astype(np.uint8)


def city_layers(reader, row, alt=False, raw_folder=None):
    import rasterio
    g = grid_of(row)
    lon0, lat0, lon1, lat1 = g.lonlat_bounds(0.02)
    wc_urls = [WC_URL.format(t) for t in wc_tiles(lon0, lat0, lon1, lat1)]
    gsw_urls = [GSW_URL.format(a + b) for a, b in gsw_tiles(lon0, lat0, lon1, lat1)]
    if raw_folder is not None:
        wc_urls = [str(Path(raw_folder) / u.rsplit("/", 1)[-1]) for u in wc_urls]
        gsw_urls = [str(Path(raw_folder) / ("JRC_" + u.rsplit("/", 1)[-1])) for u in gsw_urls]
        for source in wc_urls + gsw_urls:
            if not Path(source).is_file():
                raise FileNotFoundError(source)
    with rasterio.Env(**ENV):
        wc, wc_used, wc_miss = warp_tiles(wc_urls, g, 0)
        gs, gs_used, gs_miss = warp_tiles(gsw_urls, g,
                                          GSW_NODATA)
    ow, oi, oinfo = osm_water(reader, g)
    wcw, wcn = wc == 80, wc == 0
    gw = np.isin(gs, GSW_PERM)
    votes = wcw.astype(np.uint8) + gw + ow
    pw = (votes >= 2) | (wcn & (gw | (ow > 0)))
    land = ~pw
    out = {"pw": share(pw, g),
           "lc": np.stack([share(land & np.isin(wc, v), g) for v in LC_GROUPS.values()]),
           "src": np.stack([share(wcw, g), share(gw, g), share(np.isin(gs, GSW_SEAS), g), share(ow > 0, g),
                            share(oi > 0, g)])}
    if alt:
        out["alt"] = np.stack([share(wcw | gw | (ow > 0), g),            # union of the three sources
                               share(wcw | gw | (wcn & (ow > 0)), g),    # satellites only (OSM in open sea)
                               share((ow > 0) | (oi > 0), g)])           # all OSM water polygons
    meta = {"stem": row["stem"], "cell_m": 100, "subcells": SUB,
            "sources": {"worldcover": "ESA WorldCover 10 m 2021 v200", "gsw": "JRC Global Surface Water v1.4 (1984-2021), transitions",
                        "osm": "Overture Maps 2026-10-21.0 base/water"},
            "lc_bands": list(LC_GROUPS),
            "src_bands": ["worldcover_permanent_water", "gsw_permanent", "gsw_seasonal", "osm_water_not_intermittent",
                          "osm_water_intermittent"],
            "rule": "permanent water if >= 2 of 3 sources (WorldCover 80, GSW permanent 1/2/7, OSM not intermittent); "
                    "where WorldCover has no tile, GSW or OSM",
            "wc_tiles": wc_used, "wc_missing": wc_miss, "gsw_tiles": gs_used, "gsw_missing": gs_miss, "osm": oinfo}
    return out, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT)); ap.add_argument("--stems", nargs="*"); ap.add_argument("--shard", default="0/1")
    ap.add_argument("--alt", action="store_true")
    ap.add_argument("--max-cells", type=int, default=None, help="skip cities with more grid cells (memory)")
    ap.add_argument("--reverse", action="store_true", help="smallest cities first (list order reversed)")
    ap.add_argument("--local-raw", action="store_true", help="Use bundled raw subsets without network access")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    c = load_cities().set_index("stem")
    stems = a.stems or list(c.index)
    if a.reverse:
        stems = stems[::-1]
    k, n = (int(x) for x in a.shard.split("/"))
    stems = stems[k::n]
    if a.max_cells:
        stems = [s_ for s_ in stems if int(c.loc[s_, "nx"]) * int(c.loc[s_, "ny"]) <= a.max_cells]
    reader = None if a.local_raw else Reader("base", "water")
    for stem in stems:
        f = out / f"{stem}.npz"
        if f.exists() and not a.overwrite:
            continue
        lock = out / f"{stem}.lock"
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        t0 = time.time(); res = None
        for attempt in range(3):
            try:
                row = c.loc[stem].to_dict(); row["stem"] = stem
                res = city_layers(LocalReader(stem, "water") if a.local_raw else reader, row, a.alt,
                                  config.RAW_INPUTS / stem / "land_cover" if a.local_raw else None)
                break
            except Exception as e:  # noqa: BLE001
                if a.local_raw:
                    raise
                if attempt == 2:
                    print(json.dumps({"stem": stem, "error": repr(e)[:400]}), flush=True)
                time.sleep(10)
        if res is None:
            lock.unlink(missing_ok=True)
            continue
        lay, meta = res
        tmp = out / f"{stem}.{os.getpid()}.tmp.npz"
        np.savez_compressed(tmp, meta=json.dumps(meta), **lay)
        tmp.replace(f)
        config.WATER_COVERAGE_PERCENT.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(config.WATER_COVERAGE_PERCENT / f"{stem}.npz", water=lay["pw"])
        lock.unlink(missing_ok=True)
        print(json.dumps({"stem": stem, "pw": round(float(lay["pw"].mean()) / 100, 4),
                          "wc80": round(float(lay["src"][0].mean()) / 100, 4), "gswp": round(float(lay["src"][1].mean()) / 100, 4),
                          "osm": round(float(lay["src"][3].mean()) / 100, 4), "wc_nodata": round(float(lay["lc"][5].mean()) / 100, 4),
                          "s": round(time.time() - t0, 1)}), flush=True)


if __name__ == "__main__":
    main()
