"""Per-city reads of OpenBuildingMap (OBM) from its GeoParquet mirror on Source Cooperative.

OpenBuildingMap (Oostwegel et al. 2025, GFZ Data Services, doi:10.5880/GFZ.LKUT.2025.002,
ODbL-1.0) is published as 1,270 zoom-6 quadkey tiles (building.<quadkey>.gpkg.bz2).
Source Cooperative (tge-labs/openbuildingmap) mirrors the same tiles as GeoParquet
(building.<quadkey>.parquet, s3://us-west-2.opendata.source.coop, anonymous access) with a
per-feature `bbox` struct and spatially coherent row groups of 16,384 buildings.

As for Overture (overture_reader.py), a row-group index (file, row group, bbox ranges) is
built once from the file footers; a city reads only the intersecting row groups and keeps
the buildings whose bbox intersects the city box. For each building it keeps the OBM id,
occupancy, height code, source, an internal point (point_on_surface, projected to the
city's UTM zone) and the footprint area (only used to rank several OBM buildings that fall
in one Overture footprint).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely

from stage_2_100m_layers.building_sources.overture_reader import s3fs

BASE = "us-west-2.opendata.source.coop/tge-labs/openbuildingmap"
MIRROR = "https://source.coop/tge-labs/openbuildingmap"
COLUMNS = ["id", "occupancy", "height", "source", "geometry", "bbox"]
R_EARTH = 6371008.8


def build_index(out_path, quadkeys=None, threads: int = 16) -> pd.DataFrame:
    import pyarrow.fs as pafs
    s3 = s3fs()
    info = s3.get_file_info(pafs.FileSelector(BASE, recursive=False))
    files = sorted(i.path for i in info if i.type == pafs.FileType.File and i.path.endswith(".parquet"))
    if quadkeys is not None:
        want = {f"building.{q}.parquet" for q in quadkeys}
        files = [f for f in files if f.rsplit("/", 1)[-1] in want]
        missing = want - {f.rsplit("/", 1)[-1] for f in files}
        if missing:
            raise FileNotFoundError(f"OBM mirror lacks {sorted(missing)[:5]} ...")

    def one(path):
        for k in range(5):
            try:
                md = pq.ParquetFile(path, filesystem=s3).metadata
                names = [md.schema.column(i).path for i in range(md.num_columns)]
                ix = {n: names.index(n) for n in ("bbox.xmin", "bbox.xmax", "bbox.ymin", "bbox.ymax")}
                rows = []
                for g in range(md.num_row_groups):
                    rg = md.row_group(g)
                    st = {n: rg.column(i).statistics for n, i in ix.items()}
                    if any(s is None or not s.has_min_max for s in st.values()):
                        rows.append((path, g, -180.0, 180.0, -90.0, 90.0, rg.num_rows))
                    else:
                        rows.append((path, g, st["bbox.xmin"].min, st["bbox.xmax"].max,
                                     st["bbox.ymin"].min, st["bbox.ymax"].max, rg.num_rows))
                return rows
            except Exception:
                if k == 4:
                    raise
                time.sleep(3 * (k + 1))

    recs = []
    with ThreadPoolExecutor(threads) as ex:
        for rows in ex.map(one, files):
            recs.extend(rows)
    df = pd.DataFrame(recs, columns=["path", "rg", "xmin", "xmax", "ymin", "ymax", "rows"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return df


def _spherical_area(g_ll, lat):
    """Footprint area (m2) of lon/lat polygons, local equirectangular approximation."""
    k = (np.pi / 180.0 * R_EARTH) ** 2
    return shapely.area(g_ll) * k * np.cos(np.radians(lat))


class Reader:
    def __init__(self, index_path, threads: int = 8):
        self.index = pd.read_parquet(index_path)
        self.s3 = s3fs()
        self.threads = threads

    def row_groups(self, bbox):
        w, s, e, n = bbox
        d = self.index
        return d[(d.xmin <= e) & (d.xmax >= w) & (d.ymin <= n) & (d.ymax >= s)]

    def _read(self, path, rgs, bbox, to_utm):
        w, s, e, n = bbox
        f = None
        out = []
        for chunk in np.array_split(np.asarray(rgs), max(1, int(np.ceil(len(rgs) / 32)))):
            for k in range(5):
                try:
                    f = f or pq.ParquetFile(path, filesystem=self.s3, pre_buffer=True)
                    t = f.read_row_groups([int(x) for x in chunk], columns=COLUMNS)
                    break
                except Exception:
                    f = None
                    if k == 4:
                        raise
                    time.sleep(3 * (k + 1))
            bb = t.column("bbox")
            m = pc.and_(pc.and_(pc.less_equal(pc.struct_field(bb, "xmin"), e), pc.greater_equal(pc.struct_field(bb, "xmax"), w)),
                        pc.and_(pc.less_equal(pc.struct_field(bb, "ymin"), n), pc.greater_equal(pc.struct_field(bb, "ymax"), s)))
            t = t.filter(m)
            if not t.num_rows:
                continue
            g = shapely.from_wkb(t.column("geometry").to_numpy(zero_copy_only=False))
            bad = ~shapely.is_valid(g) & ~shapely.is_missing(g)
            if bad.any():
                g[bad] = shapely.make_valid(g[bad])
            ok = ~shapely.is_missing(g) & ~shapely.is_empty(g)
            pt = shapely.point_on_surface(g[ok])
            lon, lat = shapely.get_x(pt), shapely.get_y(pt)
            x, y = to_utm.transform(lon, lat)
            sel = np.flatnonzero(ok)
            out.append(pd.DataFrame({
                "obm_id": t.column("id").to_numpy()[sel],
                "occupancy": t.column("occupancy").dictionary_encode().to_pandas().iloc[sel].to_numpy(),
                "height": t.column("height").dictionary_encode().to_pandas().iloc[sel].to_numpy(),
                "source": t.column("source").dictionary_encode().to_pandas().iloc[sel].to_numpy(),
                "x": x, "y": y,
                "area": _spherical_area(g[ok], lat).astype(np.float32),
                "inside_box": (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n),
                "tile": path.rsplit(".", 2)[-2],
            }))
        return out

    def extract_city(self, bbox, epsg: int):
        """-> (DataFrame of OBM buildings whose internal point lies in the city box, info)."""
        from pyproj import Transformer
        t0 = time.time()
        rg = self.row_groups(bbox)
        jobs = [(p, g.rg.to_numpy()) for p, g in rg.groupby("path")]
        parts = []
        if jobs:
            with ThreadPoolExecutor(min(self.threads, len(jobs))) as ex:
                for res in ex.map(lambda j: self._read(j[0], j[1], bbox, Transformer.from_crs(4326, epsg, always_xy=True)), jobs):
                    parts.extend(res)
        cols = ["obm_id", "occupancy", "height", "source", "x", "y", "area", "inside_box", "tile"]
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({c: [] for c in cols})
        n_box = len(df)
        df = df[df.inside_box.astype(bool)].drop(columns="inside_box")
        dup = df.duplicated(["obm_id", "x", "y"])          # a building stored in two tiles
        df = df[~dup].reset_index(drop=True)
        for c in ("occupancy", "height", "source", "tile"):
            df[c] = df[c].astype("category")
        info = dict(mirror=MIRROR, files=sorted({p.rsplit("/", 1)[-1] for p, _ in jobs}),
                    row_groups=int(len(rg)), rows_in_row_groups=int(rg.rows.sum()) if len(rg) else 0,
                    bbox_hits=int(n_box), buildings=int(len(df)), duplicates_dropped=int(dup.sum()),
                    seconds=round(time.time() - t0, 1))
        return df, info
