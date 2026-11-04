"""Overture Maps GeoParquet of the base theme (water, land use): row-group bbox index and bbox reader.

The files of a release are spatially sorted and every row group carries min/max statistics of the per-feature bbox,
so a city reads only the row groups that intersect its domain (same approach as gdp.places and the building reader).
Indexes are kept in 01_inputs/source_index/overture_<theme>_<type>_rowgroups.parquet.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import stage_1_data_inputs.configuration as config


def s3fs():
    import pyarrow.fs as pafs
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        os.environ.pop(k, None)
    kw = dict(anonymous=True, region="us-west-2", connect_timeout=30, request_timeout=180)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:                                   # behind an HTTP proxy (its CA bundle in AWS_CA_BUNDLE)
        from urllib.parse import urlparse
        u = urlparse(proxy)
        kw["proxy_options"] = {"scheme": u.scheme or "http", "host": u.hostname, "port": u.port}
    return pafs.S3FileSystem(**kw)


def prefix(theme: str, typ: str, release: str = config.OVERTURE_RELEASE) -> str:
    return f"{config.OVERTURE_BUCKET}/{release}/theme={theme}/type={typ}/"


def index_file(theme: str, typ: str) -> Path:
    return config.SOURCE_INDEX / f"overture_{theme}_{typ}_rowgroups.parquet"


def build_index(theme: str, typ: str, threads: int = 8) -> pd.DataFrame:
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq
    s3 = s3fs()
    files = sorted(i.path for i in s3.get_file_info(pafs.FileSelector(prefix(theme, typ), recursive=False))
                   if i.path.endswith(".parquet"))

    def one(path):
        for k in range(5):
            try:
                md = pq.ParquetFile(path, filesystem=s3).metadata
                break
            except Exception:  # noqa: BLE001
                if k == 4:
                    raise
                time.sleep(3 * (k + 1))
        names = [md.schema.column(i).path for i in range(md.num_columns)]
        idx = {n: names.index(n) for n in ("bbox.xmin", "bbox.xmax", "bbox.ymin", "bbox.ymax")}
        rows = []
        for k in range(md.num_row_groups):
            rg = md.row_group(k)
            st = {n: rg.column(i).statistics for n, i in idx.items()}
            if any(s is None or not s.has_min_max for s in st.values()):
                rows.append((path, k, -180.0, 180.0, -90.0, 90.0, rg.num_rows))
            else:
                rows.append((path, k, st["bbox.xmin"].min, st["bbox.xmax"].max, st["bbox.ymin"].min,
                             st["bbox.ymax"].max, rg.num_rows))
        return rows

    recs = []
    with ThreadPoolExecutor(threads) as ex:
        for r in ex.map(one, files):
            recs.extend(r)
    df = pd.DataFrame(recs, columns=["path", "rg", "xmin", "xmax", "ymin", "ymax", "rows"])
    f = index_file(theme, typ)
    f.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(f, index=False)
    return df


class Reader:
    """Features of one theme/type whose bbox intersects a lon/lat box (pyarrow table).

    cache: optional folder where every row group read is kept (only the columns asked for, Parquet), so that the
    cities that share a row group download it once (s13_landuse_overture.py; the folder can be deleted afterwards)."""

    def __init__(self, theme: str, typ: str, cache=None):
        f = index_file(theme, typ)
        self.idx = pd.read_parquet(f) if f.exists() else build_index(theme, typ)
        self.s3 = s3fs()
        self.cache = Path(cache) if cache else None
        if self.cache is not None:
            self.cache.mkdir(parents=True, exist_ok=True)

    def _cache_file(self, path: str, rg: int, cols) -> Path:
        import hashlib
        tag = hashlib.md5(",".join(cols).encode()).hexdigest()[:6]
        return self.cache / f"{Path(path).stem}_rg{int(rg)}_{tag}.parquet"

    def _read_rgs(self, path: str, rgs, cols):
        """the row groups rgs of one file (columns cols): from the cache where there, the others from S3"""
        import threading
        import pyarrow.parquet as pq
        parts, todo = [], []
        for rg in rgs:
            f = self._cache_file(path, rg, cols) if self.cache is not None else None
            if f is not None and f.exists():
                try:
                    parts.append(pq.read_table(f))
                    continue
                except Exception:  # noqa: BLE001  (damaged file: read again)
                    try:
                        f.unlink()
                    except OSError:
                        pass
            todo.append(rg)
        pf = None
        for rg in todo:
            for k in range(6):
                try:
                    if pf is None:
                        pf = pq.ParquetFile(path, filesystem=self.s3, pre_buffer=True)
                    t = pf.read_row_groups([rg], columns=list(cols))
                    break
                except Exception:  # noqa: BLE001
                    pf = None
                    if k == 5:
                        raise
                    time.sleep(5 * (k + 1))
            if self.cache is not None:
                f = self._cache_file(path, rg, cols)
                tmp = f.with_name(f"{f.name}.{os.getpid()}_{threading.get_ident()}.tmp")
                try:
                    pq.write_table(t, tmp, compression="zstd")
                    os.replace(tmp, f)
                except OSError:                  # another process wrote (and may be reading) the same row group
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
            parts.append(t)
        return parts

    def read_bbox(self, lon0, lat0, lon1, lat1, cols, threads: int = 6):
        import pyarrow as pa
        ix = self.idx
        sel = ix[(ix.xmax >= lon0) & (ix.xmin <= lon1) & (ix.ymax >= lat0) & (ix.ymin <= lat1)]
        jobs = [(p, g.rg.tolist()) for p, g in sel.groupby("path")]

        def one(job):
            path, rgs = job
            out = []
            for t in self._read_rgs(path, rgs, cols):
                b = t.column("bbox").combine_chunks()
                f = lambda k: b.field(k).to_numpy(zero_copy_only=False)      # noqa: E731
                m = (f("xmax") >= lon0) & (f("xmin") <= lon1) & (f("ymax") >= lat0) & (f("ymin") <= lat1)
                out.append(t.filter(pa.array(m)).replace_schema_metadata(None))
            return out

        with ThreadPoolExecutor(threads) as ex:
            parts = [t for ts in ex.map(one, jobs) for t in ts]
        if not parts:
            return None, len(sel)
        try:
            tab = pa.concat_tables(parts)
        except (pa.ArrowInvalid, pa.ArrowTypeError):
            sch = parts[0].schema
            tab = pa.concat_tables([t.select(sch.names).cast(sch) for t in parts])
        return tab, len(sel)


class LocalReader:
    """Read complete raw Overture records from a city's bundled Parquet subset."""
    def __init__(self, stem, typ):
        names = {"water": "overture_water_polygons.parquet", "land_use": "overture_land_use_polygons.parquet",
                 "infrastructure": "overture_infrastructure_features.parquet"}
        self.path = config.RAW_INPUTS / stem / "supporting_land_features" / names[typ]
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def read_bbox(self, lon0, lat0, lon1, lat1, cols, threads=1):
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pq.read_table(self.path, columns=list(cols))
        b = table["bbox"].combine_chunks()
        f = lambda key: b.field(key).to_numpy(zero_copy_only=False)
        keep = (f("xmax") >= lon0) & (f("xmin") <= lon1) & (f("ymax") >= lat0) & (f("ymin") <= lat1)
        return table.filter(pa.array(keep)), pq.read_metadata(self.path).num_row_groups
