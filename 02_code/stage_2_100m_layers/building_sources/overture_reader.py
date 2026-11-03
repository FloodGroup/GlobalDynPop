"""Read and filter local Overture subsets for Stage 2 classification."""
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

THEMES = {
    "building": ("buildings", "building", ["id", "height", "num_floors", "class", "subtype", "is_underground"], None),
    "land_use": ("base", "land_use", ["id", "class", "subtype"], "polygon"),
    "infrastructure": ("base", "infrastructure", ["id", "class", "subtype"], "polygon"),
    "water": ("base", "water", ["id", "class", "subtype"], "polygon"),
    "segment": ("transportation", "segment", ["id", "class", "subtype", "subclass", "width_rules",
                                               "subclass_rules", "road_flags"], "road"),
}


class Reader:
    def _read(self, path, rgs, cols, bbox, kind):
        w, s, e, n = bbox
        for k in range(5):
            try:
                f = pq.ParquetFile(path, pre_buffer=True)
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
