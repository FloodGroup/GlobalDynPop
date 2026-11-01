"""Stage 2, step 5: raw road, rail and station features to routing graphs.

The local workflow also rasterises water polygons to coverage percentages.
Outputs road_and_rail_graphs/ and water_coverage_percent/. Network population
assignment follows in Stage 3. Use --global-sources for the external source-index
graph interface; that interface requires source access and prepares graphs only."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration
import stage_3_activity_allocation.network as network  # noqa: E402
from stage_2_100m_layers.building_sources import overture_reader as O  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402

INDEX = configuration.SOURCE_INDEX / f"overture_rowgroup_index_{O.OVERTURE_RELEASE}.parquet"


def global_main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--order", choices=["small", "large"], default="small")
    ap.add_argument("--out", default=str(configuration.ROAD_GRAPHS))
    ap.add_argument("--max-cells", type=int, default=None, help="only cities with at most this many grid cells")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = load_cities()
    if a.stems:
        c = c[c.stem.isin(a.stems)]
    if a.stems_file:
        keep = [s.strip() for s in Path(a.stems_file).read_text().split() if s.strip()]
        c = c[c.stem.isin(keep)]
    c = c.assign(cells=c.nx * c.ny).sort_values("cells", ascending=(a.order == "small"))
    if a.max_cells:
        c = c[c.cells <= a.max_cells]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from stage_2_100m_layers.building_sources.transportation import fetch
    reader = O.Reader(INDEX, threads=8)
    for r in c.to_dict("records"):
        stem = r["stem"]
        f = out / f"{stem}.npz"
        lock = out / f".{stem}.lock"
        if f.exists():
            continue
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            continue
        try:
            import memory_guard as memory_guard
            memory_guard.wait(log=lambda m: print(json.dumps({"stem": stem, "memory": m}), flush=True))   # only with DYNAMIC_POPULATION_MEMWAIT_GB
            t0 = time.time()
            g = grid_of(r)
            seg, sta = fetch(reader, g)
            t_fetch = time.time() - t0
            if seg is None or seg.num_rows == 0:
                raise RuntimeError("no Overture segments")
            G = network.build_from_table(seg, sta, g)
            n_seg = int(seg.num_rows)
            del seg, sta
            t_build = time.time() - t0 - t_fetch
            meta = {"stem": stem, "overture_release": O.OVERTURE_RELEASE, "segments_road_rail": n_seg,
                    "grid": {"nx": int(g.nx), "ny": int(g.ny), "cell": float(g.cell), "x0": float(g.x0), "y1": float(g.y1),
                             "crs": str(g.crs)}}
            network.save_graph(f, G, meta)
            print(json.dumps({"stem": stem, "nodes": int(G["n_nodes"]), "pieces": int(len(G["p_u"])), "samples": int(len(G["s_cell"])),
                              "stations": int(len(G["stations"])), "fetch_s": round(t_fetch, 1), "build_s": round(t_build, 1),
                              "mb": round(f.stat().st_size / 1e6, 2)}), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"stem": stem, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}), flush=True)
        finally:
            lock.unlink(missing_ok=True)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--global-sources" in arguments:
        arguments.remove("--global-sources")
        return global_main(arguments)
    from stage_2_100m_layers.local_raw_preparation import run_step
    return run_step(5, arguments)


if __name__ == "__main__":
    main()
