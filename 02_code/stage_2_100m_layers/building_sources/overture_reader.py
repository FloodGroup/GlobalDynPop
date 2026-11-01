"""Fast per-city reads of the Overture GeoParquet release through a row-group index.

The Overture files are spatially sorted and every row group carries min/max statistics
of the per-feature `bbox` struct. The index (one row per row group: file, row group,
bbox ranges) is built once from the file footers; a city then reads only the row groups
whose bbox range intersects the city box, and filters the rows with the same predicate as
overture.py (feature bbox intersects the city box). The result is identical to the
DuckDB query in overture.py (local check) and avoids scanning all
footers for every city.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

OVERTURE_RELEASE = "2026-10-21.0"

BUCKET = "overturemaps-us-west-2/release"
THEMES = {
    "building": ("buildings", "building", ["id", "height", "num_floors", "class", "subtype", "is_underground"], None),
    "land_use": ("base", "land_use", ["id", "class", "subtype"], "polygon"),
    "infrastructure": ("base", "infrastructure", ["id", "class", "subtype"], "polygon"),
    "water": ("base", "water", ["id", "class", "subtype"], "polygon"),
    "segment": ("transportation", "segment", ["id", "class", "subtype", "subclass", "width_rules",
                                               "subclass_rules", "road_flags"], "road"),
}


def s3fs():
    import pyarrow.fs as fs
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        os.environ.pop(k, None)
    return fs.S3FileSystem(anonymous=True, region="us-west-2", connect_timeout=30, request_timeout=120)


def _rg_stats(md, names):
    idx = {n: names.index(n) for n in ("bbox.xmin", "bbox.xmax", "bbox.ymin", "bbox.ymax")}
    rows = []
    for k in range(md.num_row_groups):
        rg = md.row_group(k)
        st = {n: rg.column(i).statistics for n, i in idx.items()}
        if any(s is None or not s.has_min_max for s in st.values()):
            rows.append((k, -180.0, 180.0, -90.0, 90.0, rg.num_rows))
            continue
        rows.append((k, st["bbox.xmin"].min, st["bbox.xmax"].max, st["bbox.ymin"].min, st["bbox.ymax"].max, rg.num_rows))
    return rows


def build_index(out_path: Path, release: str = OVERTURE_RELEASE, threads: int = 16) -> pd.DataFrame:
    import pyarrow.fs as pafs
    s3 = s3fs()
    recs = []
    for layer, (theme, typ, _, _) in THEMES.items():
        info = s3.get_file_info(pafs.FileSelector(f"{BUCKET}/{release}/theme={theme}/type={typ}/", recursive=False))
        files = sorted(i.path for i in info if i.type == pafs.FileType.File and i.path.endswith(".parquet"))

        def one(path):
            for k in range(5):
                try:
                    md = pq.ParquetFile(path, filesystem=s3).metadata
                    names = [md.schema.column(i).path for i in range(md.num_columns)]
                    return [(layer, path) + r for r in _rg_stats(md, names)]
                except Exception:
                    if k == 4:
                        raise
                    time.sleep(3 * (k + 1))

        with ThreadPoolExecutor(threads) as ex:
            for rows in ex.map(one, files):
                recs.extend(rows)
    df = pd.DataFrame(recs, columns=["layer", "path", "rg", "xmin", "xmax", "ymin", "ymax", "rows"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return df


class Reader:
    def __init__(self, index_path: Path, threads: int = 8):
        self.index = pd.read_parquet(index_path)
        self.s3 = s3fs()
        self.threads = threads

    def row_groups(self, layer, bbox):
        w, s, e, n = bbox
        d = self.index[self.index.layer == layer]
        m = (d.xmin <= e) & (d.xmax >= w) & (d.ymin <= n) & (d.ymax >= s)
        return d[m]

    def _read(self, path, rgs, cols, bbox, kind):
        w, s, e, n = bbox
        for k in range(5):
            try:
                f = pq.ParquetFile(path, filesystem=self.s3, pre_buffer=True)
                t = f.read_row_groups(list(rgs), columns=cols + ["bbox", "geometry"])
                break
            except Exception:
                if k == 4:
                    raise
                time.sleep(3 * (k + 1))
        bb = t.column("bbox")
        xmin = pc.struct_field(bb, "xmin"); xmax = pc.struct_field(bb, "xmax")
        ymin = pc.struct_field(bb, "ymin"); ymax = pc.struct_field(bb, "ymax")
        m = pc.and_(pc.and_(pc.less_equal(xmin, e), pc.greater_equal(xmax, w)),
                    pc.and_(pc.less_equal(ymin, n), pc.greater_equal(ymax, s)))
        t = t.filter(m)
        if kind == "road":
            t = t.filter(pc.equal(t.column("subtype"), "road"))
        if kind == "polygon" and t.num_rows:
            # WKB geometry type (little or big endian): 3 Polygon, 6 MultiPolygon
            geo = t.column("geometry").to_pylist()
            typ = np.array([int.from_bytes(g[1:5], "little" if g[0] == 1 else "big") % 1000 for g in geo])
            t = t.filter(pa.array(np.isin(typ, (3, 6))))
        return t.drop(["bbox"])

    def extract(self, layer, bbox):
        theme, typ, cols, kind = THEMES[layer]
        rg = self.row_groups(layer, bbox)
        jobs = [(p, g.rg.to_numpy()) for p, g in rg.groupby("path")]
        if not jobs:
            return None
        with ThreadPoolExecutor(min(self.threads, len(jobs))) as ex:
            parts = list(ex.map(lambda j: self._read(j[0], j[1], cols, bbox, kind), jobs))
        parts = [p for p in parts if p.num_rows]
        if not parts:
            return pa.Table.from_batches([], schema=self._read(jobs[0][0], jobs[0][1][:1], cols, bbox, kind).schema)
        return pa.concat_tables(parts, promote_options="permissive")

    def extract_city(self, bbox, out_dir: Path, layers=tuple(THEMES)) -> dict:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        info = {"release": OVERTURE_RELEASE, "bbox_lonlat": [float(v) for v in bbox], "layers": {}, "reader": "rowgroup-index"}
        for layer in layers:
            t0 = time.time()
            tab = self.extract(layer, bbox)
            if tab is None:
                tab = pa.table({c: pa.array([], pa.string()) for c in THEMES[layer][2]} | {"geometry": pa.array([], pa.binary())})
            if layer == "segment":
                for c in ("width_rules", "subclass_rules", "road_flags"):
                    vals = tab.column(c).to_pylist()
                    tab = tab.set_column(tab.schema.get_field_index(c), c,
                                         pa.array([None if v is None else json.dumps(v) for v in vals], pa.string()))
            tmp = out_dir / f".{layer}.parquet.tmp"
            pq.write_table(tab, tmp, compression="zstd")
            os.replace(tmp, out_dir / f"{layer}.parquet")
            info["layers"][layer] = {"features": tab.num_rows, "seconds": round(time.time() - t0, 2),
                                     "row_groups": int(len(self.row_groups(layer, bbox)))}
        return info
