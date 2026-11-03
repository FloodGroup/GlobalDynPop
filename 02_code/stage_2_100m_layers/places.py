"""Overture places (POIs) -> activity attractors on the city grid.

Overture Maps release 2026-10-21.0, theme `places` (about 70 million points of interest
from Meta, Microsoft, Foursquare and other sources). The GeoParquet files are spatially
sorted and every row group carries min/max statistics of the per-feature bbox, so a city
reads only the row groups that intersect its domain.

Places are kept when operating_status is not 'permanently_closed' / 'temporarily_closed'
and confidence >= MIN_CONFIDENCE, and are assigned to the activity-location classes of the
time-use data by the top level of the Overture taxonomy (and a few basic categories):

  C2 commercial & industrial  services_and_business, shopping, lifestyle_services
  C3 education                education
  C4 medical & public         health_care, community_and_government
  C5 culture, sport, leisure  food_and_drink, arts_and_entertainment, sports_and_recreation,
                              cultural_and_historic, lodging, parks (geographic_entities/park)
  C6 transport                travel_and_transportation

Counts per 100 m cell are written for each class.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

import stage_1_data_inputs.configuration as configuration
from stage_2_100m_layers.cities import grid_of

MIN_CONFIDENCE = 0.5
CLASSES = ["C2", "C3", "C4", "C5", "C6"]
TOP_TO_CLASS = {
    "services_and_business": "C2", "shopping": "C2", "lifestyle_services": "C2",
    "education": "C3",
    "health_care": "C4", "community_and_government": "C4",
    "food_and_drink": "C5", "arts_and_entertainment": "C5", "sports_and_recreation": "C5",
    "cultural_and_historic": "C5", "lodging": "C5",
    "travel_and_transportation": "C6",
}
PARK_BASIC = {"park", "playground", "garden", "nature_reserve", "beach", "plaza"}
CLOSED = {"permanently_closed", "temporarily_closed"}


def s3fs():
    import pyarrow.fs as fs
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        os.environ.pop(k, None)
    return fs.S3FileSystem(anonymous=True, region="us-west-2", connect_timeout=30, request_timeout=180)


def build_index(out_path: Path, release: str = configuration.OVERTURE_RELEASE, threads: int = 8) -> pd.DataFrame:
    import pyarrow.fs as pafs
    s3 = s3fs()
    info = s3.get_file_info(pafs.FileSelector(f"{configuration.OVERTURE_BUCKET}/{release}/theme=places/type=place/", recursive=False))
    files = sorted(i.path for i in info if i.type == pafs.FileType.File and i.path.endswith(".parquet"))

    def one(path):
        md = pq.ParquetFile(path, filesystem=s3).metadata
        names = [md.schema.column(i).path for i in range(md.num_columns)]
        idx = {n: names.index(n) for n in ("bbox.xmin", "bbox.xmax", "bbox.ymin", "bbox.ymax")}
        rows = []
        for k in range(md.num_row_groups):
            rg = md.row_group(k)
            st = {n: rg.column(i).statistics for n, i in idx.items()}
            if any(s is None or not s.has_min_max for s in st.values()):
                rows.append((path, k, -180.0, 180.0, -90.0, 90.0, rg.num_rows))
            else:
                rows.append((path, k, st["bbox.xmin"].min, st["bbox.xmax"].max, st["bbox.ymin"].min, st["bbox.ymax"].max,
                             rg.num_rows))
        return rows

    recs = []
    with ThreadPoolExecutor(threads) as ex:
        for rows in ex.map(one, files):
            recs.extend(rows)
    df = pd.DataFrame(recs, columns=["path", "rg", "xmin", "xmax", "ymin", "ymax", "rows"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return df


class Reader:
    def __init__(self, index_path: Path):
        self.idx = pd.read_parquet(index_path)
        self.s3 = s3fs()

    def read_bbox(self, lon0, lat0, lon1, lat1, threads: int = 8) -> pd.DataFrame:
        ix = self.idx
        sel = ix[(ix.xmax >= lon0) & (ix.xmin <= lon1) & (ix.ymax >= lat0) & (ix.ymin <= lat1)]
        cols = ["bbox", "confidence", "operating_status", "basic_category", "taxonomy"]
        jobs = [(p, g.rg.tolist()) for p, g in sel.groupby("path")]

        def one(job):
            path, rgs = job
            for k in range(5):
                try:
                    f = pq.ParquetFile(path, filesystem=self.s3)
                    t = f.read_row_groups(rgs, columns=cols)
                    break
                except Exception:
                    if k == 4:
                        raise
                    time.sleep(3 * (k + 1))
            x = pc.struct_field(t["bbox"], "xmin"); y = pc.struct_field(t["bbox"], "ymin")
            m = pc.and_(pc.and_(pc.greater_equal(x, lon0), pc.less_equal(x, lon1)),
                        pc.and_(pc.greater_equal(y, lat0), pc.less_equal(y, lat1)))
            t = t.filter(m)
            tax = t["taxonomy"]
            hier = pc.struct_field(tax, "hierarchy")
            df = pd.DataFrame({
                "lon": pc.struct_field(t["bbox"], "xmin").to_numpy(zero_copy_only=False),
                "lat": pc.struct_field(t["bbox"], "ymin").to_numpy(zero_copy_only=False),
                "confidence": t["confidence"].to_numpy(zero_copy_only=False),
                "status": t["operating_status"].to_pandas(),
                "basic": t["basic_category"].to_pandas(),
                "hier": hier.to_pandas(),
            })
            return df

        parts = []
        with ThreadPoolExecutor(threads) as ex:
            for d in ex.map(one, jobs):
                parts.append(d)
        if not parts:
            return pd.DataFrame(columns=["lon", "lat", "confidence", "status", "basic", "hier"])
        d = pd.concat(parts, ignore_index=True)
        d["top"] = d.hier.map(lambda h: h[0] if h is not None and len(h) else None)
        return d.drop(columns="hier")


def classify(d: pd.DataFrame) -> pd.Series:
    cls = d.top.map(TOP_TO_CLASS)
    park = d.basic.isin(PARK_BASIC)
    cls = cls.where(~park, "C5")
    keep = (~d.status.isin(CLOSED)) & (d.confidence.fillna(0) >= MIN_CONFIDENCE)
    return cls.where(keep)


def city_places(reader: Reader, row: dict) -> dict:
    """Counts of places per 100 m cell and class for one city (dict of float32 arrays)."""
    from pyproj import Transformer
    g = grid_of(row)
    lon0, lat0, lon1, lat1 = g.lonlat_bounds(0.01)
    d = reader.read_bbox(lon0, lat0, lon1, lat1)
    d["cls"] = classify(d)
    out = {c: np.zeros(g.shape, np.float32) for c in CLASSES}
    stats = {"read": int(len(d))}
    if len(d):
        x, y = Transformer.from_crs(4326, g.crs, always_xy=True).transform(d.lon.to_numpy(), d.lat.to_numpy())
        r, c = g.index(x, y)
        ok = r >= 0
        for k in CLASSES:
            m = ok & (d.cls.to_numpy() == k)
            if m.any():
                out[k] = np.bincount(r[m] * g.nx + c[m], minlength=g.nx * g.ny).reshape(g.shape).astype(np.float32)
            stats[k] = int(m.sum())
        stats["in_domain"] = int(ok.sum())
        stats["unclassified"] = int((ok & d.cls.isna().to_numpy()).sum())
    return out, stats
