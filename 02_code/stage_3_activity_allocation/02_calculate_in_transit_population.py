"""Stage 3, step 2: people in transit on the road and rail network (component C6).

    python 02_code/stage_3_activity_allocation/02_calculate_in_transit_population.py [--params 04_intermediate/demo/stage_2/allocation_parameters/population_allocation_parameters.json] [--stems ...] [--stems-file f]
                                           [--order small|large|file] [--overwrite]
    python 03_run/runtime/run_parallel.py --workers 12 --name network -- 02_code/stage_3_activity_allocation/02_calculate_in_transit_population.py   (several processes)

For every city: the road and rail network of the domain (routing graph from the Overture segments and
stations, stored by 05_prepare_transport_graphs.py), the trips
between zones of the city's gravity
model (workday and rest day, kernels and time-use of the country) are assigned to the fastest
routes (stage_3_activity_allocation/network.py), and the person-time is placed on the 100 m cells.
-> 04_intermediate/demo/stage_3/in_transit_population/<stem>.npz  T_workday, T_restday (float32, people if everyone were travelling;
   sums to the domain population), street (m of street per cell), stats (JSON string)
03_calculate_population_components.py uses these layers for C6 when they exist.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration
import stage_3_activity_allocation.network as network  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402
from stage_3_activity_allocation.gravity import kernel_values  # noqa: E402
from stage_3_activity_allocation.model import Params, attractor, iso3_of, load_layers  # noqa: E402
from stage_2_100m_layers.time_use import daytype_shares  # noqa: E402

OUT = configuration.NETWORK
GRAPHS = configuration.ROAD_GRAPHS          # road and rail network of every city (input; 05_prepare_transport_graphs.py)
CLASSES = ("C2", "C3", "C4", "C5", "C7")
PARAMS_FILE = ""          # name of the parameter file (recorded in the stats)
SHARE_COL = {"C2": 1, "C3": 2, "C4": 3, "C5": 4, "C7": 6}






def kernels_used(params, iso):
    """Kernels of the trip matrices (recorded with the layer; 03_calculate_population_components.py checks them)."""
    out = {}
    for dt in ("workday", "restday"):
        p = params.for_country(iso).for_daytype(dt)
        out[dt] = {c: [p.k(c), float(p.d0[c]), float(p.beta.get(c, 1.0))] for c in CLASSES}
    return out


def attractors_used(params, iso):
    """Destination specifications of the trip matrices (recorded with the layer; 03_calculate_population_components.py checks them)."""
    out = {}
    for dt in ("workday", "restday"):
        p = params.for_country(iso).for_daytype(dt)
        out[dt] = {c: (p.attractor[c] if isinstance(p.attractor[c], str) else json.dumps(p.attractor[c], sort_keys=True)) for c in CLASSES}
    return out


def trip_matrices(stem, row, params, grid, N, V, P, kz):
    iso = iso3_of(stem)
    out = {}
    for dt in ("workday", "restday"):
        p = params.for_country(iso).for_daytype(dt)
        sh, _ = daytype_shares(iso, dt)
        w = np.array([sh[:, SHARE_COL[c]].sum() for c in CLASSES])
        w = w / w.sum()
        A_list, kernels = [], []
        for c in CLASSES:
            acls = p.c7_like if c == "C7" else c
            A_list.append(attractor(p.attractor[c], acls, V, P))
            d0, beta, kind = float(p.d0[c]), float(p.beta.get(c, 1.0)), p.k(c)
            radius = min(p.radius_factor * d0, p.max_radius_m) if kind == "pow" else p.radius_factor * d0
            kernels.append((lambda D, d0=d0, kind=kind, beta=beta: kernel_values(D, d0, kind, beta), radius))
        out[dt] = network.zone_od(N, A_list, w, kernels, grid, kz) + (w,)
    return out


def road_graph(stem):
    """Load the routing graph prepared in Stage 2."""
    t0=time.time()
    path=GRAPHS/f'{stem}.npz'
    if not path.is_file():
        raise FileNotFoundError(f'Missing Stage 2 graph: {path}; run 05_prepare_transport_graphs.py first')
    return network.load_graph(path),0.0,time.time()-t0


def run_city(stem, row, params, log=print):
    t0 = time.time()
    g = grid_of(row)
    N, V, P = load_layers(stem)
    kz = network.zone_size(g)
    G, t_fetch, t_build = road_graph(stem)
    od = trip_matrices(stem, row, params, g, N, V, P, kz)
    Nz, cx, cy = od["workday"][0], od["workday"][1], od["workday"][2]
    Ts = [od["workday"][3], od["restday"][3]]
    arrs, zone_local, stats, _ = network.assign(G, g, Nz, cx, cy, Ts, kz, log=log)
    res = {}
    for name, a in zip(("T_workday", "T_restday"), arrs):
        s = a.sum()
        res[name] = (a * (N.sum() / s) if s > 0 else a).astype(np.float32)
    stats.update(stem=stem, zone_cells=kz, fetch_s=round(t_fetch, 1), build_s=round(t_build, 1), total_s=round(time.time() - t0, 1),
                 major_segments=G["n_major_segments"], stations=int(len(G["stations"])),
                 weights_workday=[round(float(x), 4) for x in od["workday"][4]],
                 weights_restday=[round(float(x), 4) for x in od["restday"][4]],
                 street_km=round(float(G["street"].sum() / 1000), 1),
                 kernels=kernels_used(params, iso3_of(stem)), attractors=attractors_used(params, iso3_of(stem)),
                 params_file=PARAMS_FILE)
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f".{stem}.npz"
    np.savez_compressed(tmp, T_workday=res["T_workday"], T_restday=res["T_restday"], street=G["street"].astype(np.float32),
                        stats=json.dumps(stats))
    tmp.replace(OUT / f"{stem}.npz")
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=str(configuration.MODEL_PARAMS))
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--order", choices=["small", "large", "file"], default="small")
    ap.add_argument("--out", help="folder of the layers (default 04_intermediate/demo/stage_3/in_transit_population; another one for a reproduction check)")
    ap.add_argument("--graphs", help="folder of the road and rail networks (default: configuration.ROAD_GRAPHS)")
    a = ap.parse_args(argv)
    global OUT, GRAPHS
    if a.out:
        OUT = Path(a.out)
    if a.graphs:
        GRAPHS = Path(a.graphs)
    from stage_3_activity_allocation.model import params_from
    global PARAMS_FILE
    PARAMS_FILE = Path(a.params).name
    spec = json.loads(Path(a.params).read_text())
    params = params_from(spec)
    c = load_cities()
    if a.stems:
        c = c[c.stem.isin(a.stems)]
    if a.stems_file:
        keep = [s.strip() for s in Path(a.stems_file).read_text().split() if s.strip()]
        c = c[c.stem.isin(keep)]
    c = c.assign(cells=c.nx * c.ny)
    if a.order != "file":
        c = c.sort_values("cells", ascending=(a.order == "small"))

    import memory_guard as memory_guard
    import work_queue as work_queue
    OUT.mkdir(parents=True, exist_ok=True)
    for r in c.to_dict("records"):
        stem = r["stem"]
        f = OUT / f"{stem}.npz"
        if f.exists() and (not a.overwrite or work_queue.written_in_this_run(f)):
            continue
        memory_guard.wait(log=lambda m: print(json.dumps({"stem": stem, "memory": m}), flush=True))   # only with DYNAMIC_POPULATION_MEMWAIT_GB
        lock = work_queue.claim(OUT, stem)          # several processes can share the cities (run_parallel.py)
        if lock is None:
            continue
        try:
            st = run_city(stem, r, params, log=lambda m: print(m, flush=True))
            print(json.dumps({k: st[k] for k in ("stem", "zones", "nodes", "pieces", "stations_used", "network_share", "rail_share",
                                                 "unreached_trip_share", "fetch_s", "build_s", "total_s")}), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"stem": stem, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}), flush=True)
        finally:
            work_queue.release(lock)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
