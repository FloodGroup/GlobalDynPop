"""Interpret local OpenBuildingMap occupancy and height evidence for floor area."""
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely

MIRROR="https://source.coop/tge-labs/openbuildingmap"
COLUMNS=["id","occupancy","height","source","geometry","bbox"]
R_EARTH=6371008.8

def _spherical_area(g_ll, lat):
    """Footprint area (m2) of lon/lat polygons, local equirectangular approximation."""
    k = (np.pi / 180.0 * R_EARTH) ** 2
    return shapely.area(g_ll) * k * np.cos(np.radians(lat))


class Reader:
    def _read(self, path, rgs, bbox, to_utm):
        w, s, e, n = bbox
        f = None
        out = []
        for chunk in np.array_split(np.asarray(rgs), max(1, int(np.ceil(len(rgs) / 32)))):
            for k in range(5):
                try:
                    f = f or pq.ParquetFile(path, pre_buffer=True)
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
