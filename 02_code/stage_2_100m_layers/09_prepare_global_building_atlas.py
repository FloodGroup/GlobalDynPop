# -*- coding: utf-8 -*-
"""Stage 2, step 9 (local raw subsets or provider sources): buildings of every city from GlobalBuildingAtlas LoD1
(Zhu, X. X. et al. 2025, Earth Syst. Sci. Data 17, 6647-6668, doi:10.5194/essd-17-6647-2025; dataset
doi:10.14459/2025mp1782307; CC BY-NC 4.0, polygons from OpenStreetMap and Microsoft under ODbL), read from its Parquet
conversion on Source Cooperative (s3://us-west-2.opendata.source.coop/tge-labs/globalbuildingatlas-lod1/: 922 tiles of
5 x 5 degrees, one row per building with its polygon in WGS 84, its height in metres (-999 = no estimate) and its
bounding box; the row groups are spatially sorted, so a city reads only the row groups that intersect its domain).

    python 02_code/stage_2_100m_layers/09_prepare_global_building_atlas.py --local-raw --verify-reference --output-dir 04_intermediate/demo/reproduction/gba_from_raw
    python 02_code/stage_2_100m_layers/09_prepare_global_building_atlas.py [--stems ...] [--threads 6]
    python 02_code/stage_2_100m_layers/09_prepare_global_building_atlas.py --index        (build an index for remote provider reconstruction)

-> 01_inputs/buildings/gba/<stem>.npz, per 100 m cell of the city grid (float32):
   foot_m2      footprint area of all buildings (polygon area, local scale of the WGS 84 degrees)
   foot_noh_m2  footprint area of the buildings without a height estimate
   vol_h_m3     footprint area x height, buildings with a height estimate
   floor_h_m2   footprint area x storeys, storeys = max(1, round(height / 3 m)), buildings with a height estimate
   n            number of buildings (centroid in the cell)
   (10_prepare_buildings_open_space.py imputes the volume and floor area of the buildings without a height)
Footprints larger than 15 % of a cell that cross cell borders are split over the cells their bounding box covers, in
proportion to the overlap; all other buildings go to the cell of their centroid.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
if os.environ.get("GDP_CA_BUNDLE"):
    os.environ.setdefault("AWS_CA_BUNDLE", os.environ["GDP_CA_BUNDLE"])
import stage_1_data_inputs.configuration as config  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402

OUT = config.GBA
INDEX = config.SOURCE_INDEX / "gba_lod1_rowgroups.parquet"
PREFIX = "us-west-2.opendata.source.coop/tge-labs/globalbuildingatlas-lod1/"
STOREY_M = 3.0
M_PER_DEG = 111_320.0
MARGIN = 0.002            # degrees around the domain


def s3fs():
    """Anonymous S3 access (us-west-2); behind an HTTP proxy (HTTPS_PROXY) its CA bundle in AWS_CA_BUNDLE."""
    import pyarrow.fs as pafs
    from urllib.parse import urlparse
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        os.environ.pop(k, None)
    kw = dict(anonymous=True, region="us-west-2", connect_timeout=30, request_timeout=300)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        u = urlparse(proxy)
        kw["proxy_options"] = {"scheme": u.scheme or "http", "host": u.hostname, "port": u.port}
    return pafs.S3FileSystem(**kw)


def index(threads: int = 8):
    import pandas as pd
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq
    s3 = s3fs()
    files = sorted(i.path for i in s3.get_file_info(pafs.FileSelector(PREFIX)) if i.path.endswith(".parquet"))

    def one(path):
        for k in range(6):
            try:
                md = pq.ParquetFile(path, filesystem=s3).metadata
                break
            except Exception:  # noqa: BLE001
                if k == 5:
                    raise
                time.sleep(5 * (k + 1))
        names = [md.schema.column(i).path for i in range(md.num_columns)]
        ix = {n: names.index(n) for n in ("bbox.xmin", "bbox.xmax", "bbox.ymin", "bbox.ymax")}
        gi = names.index("geometry")
        rows = []
        for k in range(md.num_row_groups):
            rg = md.row_group(k)
            st = {n: rg.column(i).statistics for n, i in ix.items()}
            rows.append((path.rsplit("/", 1)[1], k, st["bbox.xmin"].min, st["bbox.xmax"].max, st["bbox.ymin"].min,
                         st["bbox.ymax"].max, rg.num_rows, rg.total_byte_size, rg.column(gi).total_compressed_size))
        return rows

    recs = []
    with ThreadPoolExecutor(threads) as ex:
        for r in ex.map(one, files):
            recs.extend(r)
    df = pd.DataFrame(recs, columns=["file", "rg", "xmin", "xmax", "ymin", "ymax", "rows", "bytes", "geom_bytes"])

    INDEX.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INDEX, index=False)
    print(len(files), "files", len(df), "row groups", int(df.rows.sum()), "buildings")


def split_add(acc, ny, nx, r0, r1, c0, c1, fx0, fx1, fy0, fy1, w):
    """Add weights w of rectangles (cell-unit coordinates fx (columns) and fy (rows, from the top)) to the grids in
    acc (dict name -> flat array), in proportion to the overlap with every cell. Loop over the (few) large ones."""
    for i in range(len(w)):
        cs = np.arange(max(c0[i], 0), min(c1[i], nx - 1) + 1)
        rs = np.arange(max(r0[i], 0), min(r1[i], ny - 1) + 1)
        if not len(cs) or not len(rs):
            continue
        ox = np.clip(np.minimum(fx1[i], cs + 1) - np.maximum(fx0[i], cs), 0, None)
        oy = np.clip(np.minimum(fy1[i], rs + 1) - np.maximum(fy0[i], rs), 0, None)
        frac = np.outer(oy, ox)
        tot = frac.sum()
        if tot <= 0:
            continue
        frac = frac / tot
        idx = (rs[:, None] * nx + cs[None, :]).ravel()
        f = frac.ravel()
        for k, v in w[i].items():
            np.add.at(acc[k], idx, f * v)


def bounded_map(ex, fn, items, window):
    """ex.map with at most `window` tasks submitted ahead of the one being consumed (bounded memory)."""
    from collections import deque
    it = iter(items)
    q = deque()
    for x in it:
        q.append(ex.submit(fn, x))
        if len(q) >= window:
            break
    while q:
        fut = q.popleft()
        for x in it:
            q.append(ex.submit(fn, x))
            break
        yield fut.result()


def city(row, s3, ix, threads=6, log=print, source_prefix=PREFIX):
    import pyarrow.parquet as pq
    import shapely
    from pyproj import Transformer
    g = grid_of(row)
    ny, nx = int(row["ny"]), int(row["nx"])
    lo0, la0, lo1, la1 = g.lonlat_bounds(0.0)
    m = (ix.xmax >= lo0 - MARGIN) & (ix.xmin <= lo1 + MARGIN) & (ix.ymax >= la0 - MARGIN) & (ix.ymin <= la1 + MARGIN)
    sel = ix[m]
    tr = Transformer.from_crs(4326, g.crs, always_xy=True)
    acc = {k: np.zeros(ny * nx, np.float64) for k in ("foot", "foot_h", "vol_h", "floor_h", "foot_noh", "n")}
    local = threading.local()                       # one ParquetFile per thread and file (readers are not shared)
    stats = {"rows_read": 0, "buildings": 0, "with_height": 0, "split": 0, "bytes": int(sel.bytes.sum())}

    def read(task):
        f, rgs = task
        files = getattr(local, "files", None)
        if files is None:
            files = local.files = {}
        for k in range(6):
            try:
                pf = files.get(f)
                if pf is None:
                    pf = files[f] = pq.ParquetFile(source_prefix + f, filesystem=s3, pre_buffer=True)   # coalesced reads
                return pf.read_row_groups(rgs, columns=["height", "bbox", "geometry"])
            except Exception:  # noqa: BLE001
                files.pop(f, None)
                if k == 5:
                    raise
                time.sleep(5 * (k + 1))

    tasks = []
    for f, s in sel.groupby("file"):
        rgs = sorted(s.rg.tolist())
        for i in range(0, len(rgs), 4):
            tasks.append((f, rgs[i:i + 4]))
    with ThreadPoolExecutor(threads) as ex:
        for tab in bounded_map(ex, read, tasks, 2 * threads):
            stats["rows_read"] += tab.num_rows
            b = tab.column("bbox").combine_chunks()
            xmin = b.field("xmin").to_numpy(); xmax = b.field("xmax").to_numpy()
            ymin = b.field("ymin").to_numpy(); ymax = b.field("ymax").to_numpy()
            keep = (xmax >= lo0) & (xmin <= lo1) & (ymax >= la0) & (ymin <= la1)
            if not keep.any():
                continue
            k_ = np.nonzero(keep)[0]
            geom = shapely.from_wkb(tab.column("geometry").to_numpy(zero_copy_only=False)[k_])
            h = tab.column("height").to_numpy(zero_copy_only=False)[k_].astype(np.float64)
            lat = 0.5 * (ymin[k_] + ymax[k_])
            area = shapely.area(geom) * M_PER_DEG ** 2 * np.cos(np.radians(lat))
            cen = shapely.centroid(geom)
            cx, cy = tr.transform(shapely.get_x(cen), shapely.get_y(cen))
            # projected bounding box (corners) for the split of large footprints
            X0, Y0 = tr.transform(xmin[k_], ymin[k_]); X1, Y1 = tr.transform(xmax[k_], ymax[k_])
            fx0 = (np.minimum(X0, X1) - g.x0) / g.cell; fx1 = (np.maximum(X0, X1) - g.x0) / g.cell
            fy0 = (g.y1 - np.maximum(Y0, Y1)) / g.cell; fy1 = (g.y1 - np.minimum(Y0, Y1)) / g.cell
            ci = np.floor((cx - g.x0) / g.cell).astype(np.int64); ri = np.floor((g.y1 - cy) / g.cell).astype(np.int64)
            inside = (ci >= 0) & (ci < nx) & (ri >= 0) & (ri < ny)
            hasH = h > 0
            stats["buildings"] += int(inside.sum()); stats["with_height"] += int((inside & hasH).sum())
            floors = np.maximum(1.0, np.round(np.where(hasH, h, 0.0) / STOREY_M))
            vals = {"foot": area, "foot_h": np.where(hasH, area, 0.0), "vol_h": np.where(hasH, area * h, 0.0),
                    "floor_h": np.where(hasH, area * floors, 0.0), "foot_noh": np.where(hasH, 0.0, area),
                    "n": np.ones_like(area)}
            big = (np.floor(fx1) > np.floor(fx0)) | (np.floor(fy1) > np.floor(fy0))
            big &= area > 0.15 * g.cell ** 2                # split only footprints large enough to matter
            small = inside & ~big
            idx = ri[small] * nx + ci[small]
            for kk, v in vals.items():
                acc[kk] += np.bincount(idx, weights=v[small], minlength=ny * nx)
            bb = np.nonzero(big & (fx1 >= 0) & (fx0 < nx) & (fy1 >= 0) & (fy0 < ny))[0]
            if len(bb):
                stats["split"] += int(len(bb))
                w = [{kk: float(v[i]) for kk, v in vals.items() if kk != "n"} for i in bb]
                split_add(acc, ny, nx, np.floor(fy0[bb]).astype(int), np.floor(fy1[bb]).astype(int),
                          np.floor(fx0[bb]).astype(int), np.floor(fx1[bb]).astype(int), fx0[bb], fx1[bb], fy0[bb], fy1[bb], w)
                inb = (ci[bb] >= 0) & (ci[bb] < nx) & (ri[bb] >= 0) & (ri[bb] < ny)
                acc["n"] += np.bincount(ri[bb][inb] * nx + ci[bb][inb], minlength=ny * nx)
    # stored: totals and the part with a height estimate, so that the volume and floor area of the buildings without
    # one can be imputed later (GHS-BUILT-H of the cell on the computer of the model); city means for the log only
    H_city = float(acc["vol_h"].sum() / acc["foot_h"].sum()) if acc["foot_h"].sum() > 0 else float("nan")
    F_city = float(acc["floor_h"].sum() / acc["foot_h"].sum()) if acc["foot_h"].sum() > 0 else float("nan")
    out = {"foot_m2": acc["foot"], "foot_noh_m2": acc["foot_noh"], "vol_h_m3": acc["vol_h"], "floor_h_m2": acc["floor_h"],
           "n": acc["n"]}
    out = {k: v.reshape(ny, nx).astype(np.float32) for k, v in out.items()}
    stats.update(H_city=round(H_city, 2), storeys_city=round(F_city, 2), foot_km2=round(float(acc["foot"].sum()) / 1e6, 3),
                 share_foot_with_h=round(float(acc["foot_h"].sum() / max(acc["foot"].sum(), 1e-9)), 4))
    return out, stats


def run(stems=None, shard=None, threads=6):
    import pandas as pd
    ix = pd.read_parquet(INDEX)
    c = load_cities()
    if stems:
        c = c[c.stem.isin(stems)]
    c = c.assign(cells=c.nx * c.ny).sort_values("cells", ascending=False)
    if shard:
        k, n = map(int, shard.split("/"))
        c = c.iloc[k::n]
    OUT.mkdir(parents=True, exist_ok=True)
    s3 = s3fs()
    logf = OUT / f"_log_{(shard or '0/1').replace('/', 'of')}.jsonl"
    for row in c.to_dict("records"):
        f = OUT / f"{row['stem']}.npz"
        if f.exists():
            continue
        t0 = time.time()
        for k in range(4):
            try:
                out, st = city(row, s3, ix, threads=threads)
                break
            except Exception as e:  # noqa: BLE001
                if k == 3:
                    print(json.dumps({"stem": row["stem"], "error": repr(e)}), flush=True)
                    out = None
                time.sleep(30 * (k + 1))
        if out is None:
            continue
        np.savez_compressed(f.with_suffix(".tmp.npz"), **out)
        f.with_suffix(".tmp.npz").replace(f)
        st.update(stem=row["stem"], seconds=round(time.time() - t0, 1), npz_mb=round(f.stat().st_size / 1e6, 2))
        with open(logf, "a") as fh:
            fh.write(json.dumps(st) + "\n")
        print(json.dumps(st), flush=True)



def run_local(stems=None, output_dir=None, threads=4, verify_reference=False):
    """Rebuild GBA aggregates offline from complete city building records."""
    import pandas as pd
    import pyarrow.parquet as pq
    destination = Path(output_dir) if output_dir else OUT
    reference = config.ROOT / "04_intermediate/demo/stage_2/buildings/gba"
    if verify_reference and destination.resolve() == reference.resolve():
        raise ValueError("Choose a separate output directory when comparing with bundled references")
    cities = load_cities()
    if stems:
        missing = set(stems) - set(cities.stem)
        if missing:
            raise ValueError(f"Unknown city stems: {sorted(missing)}")
        cities = cities[cities.stem.isin(stems)]
    destination.mkdir(parents=True, exist_ok=True)
    report = []
    for row in cities.to_dict("records"):
        raw = config.RAW_INPUTS / row["stem"] / "buildings" / "globalbuildingatlas_buildings.parquet"
        metadata = pq.read_metadata(raw)
        lo0, la0, lo1, la1 = grid_of(row).lonlat_bounds(0.0)
        ix = pd.DataFrame([dict(file=raw.as_posix(), rg=i, xmin=lo0, ymin=la0, xmax=lo1, ymax=la1,
                               bytes=metadata.row_group(i).total_byte_size) for i in range(metadata.num_row_groups)])
        arrays, stats = city(row, None, ix, threads=threads, source_prefix="")
        np.savez_compressed(destination / (row["stem"] + ".npz"), **arrays)
        record = dict(stem=row["stem"], raw_records=metadata.num_rows, statistics=stats)
        if verify_reference:
            with np.load(reference / (row["stem"] + ".npz")) as ref:
                checks = {}
                for name, value in arrays.items():
                    if value.shape != ref[name].shape or not np.isfinite(value).all():
                        raise AssertionError(f"Invalid {row['stem']} / {name}")
                    checks[name] = dict(max_abs_difference=float(np.max(np.abs(value.astype(float)-ref[name].astype(float)))),
                                        exact=bool(np.array_equal(value, ref[name])))
                record["reference_comparison"] = checks
        report.append(record)
        print(json.dumps(record), flush=True)
    (destination / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if verify_reference and any(not c["exact"] for r in report for c in r["reference_comparison"].values()):
        raise AssertionError("Local raw reconstruction differs from reference; see verification.json")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--shard")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--local-raw", action="store_true", help="Read bundled city Parquet files without network access")
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--verify-reference", action="store_true")
    a = ap.parse_args()
    stems = list(a.stems or [])
    if a.stems_file:
        stems += [l.strip() for l in open(a.stems_file, encoding="utf-8") if l.strip()]
    if a.local_raw:
        if a.index or a.shard:
            ap.error("--local-raw cannot be combined with --index or --shard")
        run_local(stems or None, a.output_dir, a.threads, a.verify_reference)
    else:
        if a.output_dir or a.verify_reference:
            ap.error("--output-dir and --verify-reference require --local-raw")
        index() if a.index else run(stems or None, a.shard, a.threads)
