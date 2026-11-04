"""Stage 2, step 3: Calculate classified building floor area from raw building and land-use records."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import gc
import math
import numpy as np
from stage_2_100m_layers.buildings import city_floor_area

def floor_area(row, ov, open_building_map, height, rules, mixed, strip_cells=None):
    """city_floor_area, in horizontal strips for large grids."""
    ny, nx = int(row["ny"]), int(row["nx"])
    k = 1 if not strip_cells else max(1, math.ceil(ny * nx / strip_cells))
    if k == 1:
        return city_floor_area(row, ov, open_building_map, height, rules, mixed)
    h = math.ceil(ny / k)
    cell = float(row.get("cell", 100.0))
    fa = np.zeros((9, ny, nx), np.float32)
    parts = []
    for i in range(k):
        r0, r1 = i * h, min(ny, (i + 1) * h)
        if r0 >= r1:
            break
        sub = dict(row); sub["y1"] = float(row["y1"]) - r0 * cell; sub["ny"] = r1 - r0
        f, st = city_floor_area(sub, ov, open_building_map, None if height is None else height[r0:r1], rules, mixed)
        fa[:, r0:r1] = f
        parts.append(st)
        del f
        gc.collect()
    nb = sum(st.get("buildings", 0) for st in parts)
    st = {"stem": row["stem"], "strips": len(parts), "buildings": nb}
    for key in ("read", "underground", "obm_buildings", "split_buildings", "footprint_km2", "gross_km2", "seconds"):
        st[key] = sum(p.get(key, 0) or 0 for p in parts)
    for key in ("share_obm", "share_own_class", "share_own_subtype", "share_land_use", "share_default", "share_aoi", "floors_known"):
        st[key] = sum((p.get(key) or 0) * p.get("buildings", 0) for p in parts) / max(nb, 1)
    st["gross_by_class_km2"] = [float(x) for x in fa.reshape(9, -1).sum(1) / 1e6]
    return fa, st


def main(argv=None):
    from stage_2_100m_layers.local_raw_preparation import run_step
    return run_step(3,argv)

if __name__=='__main__':main()
