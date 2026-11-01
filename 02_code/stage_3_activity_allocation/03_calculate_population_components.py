"""Stage 3, step 3: model components of every city (stage_3_activity_allocation/model.py).

    python 02_code/stage_3_activity_allocation/03_calculate_population_components.py [--params 04_intermediate/demo/stage_2/allocation_parameters/population_allocation_parameters.json] [--stems ...] [--stems-file f]
                                      [--order small|large|list] [--out 05_outputs/demo/population_components]
    python 03_run/runtime/run_parallel.py --workers 12 --name components -- 02_code/stage_3_activity_allocation/03_calculate_population_components.py   (several processes)

For every city, one GeoTIFF (float32, people per 100 m cell, the city's local Lambert azimuthal equal-area grid,
LERC-ZSTD) with the people of each activity location if the whole population were there:

    C1  residents at home (GHS-POP 2025)
    C2  at work places (commercial and industrial floor area and POIs)
    C3  at education
    C4  at medical and public services
    C5  at leisure (restaurants, lodging, parks, culture, sport; shops are C2)
    C6  travelling (trips assigned to the road and rail network, 02_calculate_in_transit_population.py)
    C7  at other activities (destinations as C5, shorter trips)

followed by C2_rest, C5_rest, C6_rest and C7_rest, the rest-day allocation of the classes whose kernels or
destinations differ on rest days (C1, C3 and C4 are the same on both day types). Every band sums to the domain
population. The population of hour h of day type tau is the linear combination
P(h, tau) = sum_c s_c(h, tau) component_c(tau) with the hourly activity-location shares of the country
(01_generate_hourly_population.py). A JSON file per city records the parameters, the destination layers, the POI weight and the share
of residents who found no destination; one record per city goes to 04_intermediate/logs/components/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration  # noqa: E402
from stage_2_100m_layers.cities import grid_of, load_cities  # noqa: E402
from stage_3_activity_allocation.model import Params, components_daytypes, load_layers, poi_density, poi_weight  # noqa: E402

BANDS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
PARAMS_FILE = ""
# LERC (limited error raster compression) with a maximum error of 0.001 people per cell: about
# 5 x smaller than lossless DEFLATE; read by GDAL >= 2.4, QGIS and ArcGIS
COMPRESSION = dict(compress="LERC_ZSTD", max_z_error=0.001)


def params_from(spec: dict) -> Params:
    p = Params()
    for k, v in spec.items():
        if k in ("d0", "attractor", "kind", "beta"):
            per_class = isinstance(v, dict) and set(v) <= {"C2", "C3", "C4", "C5", "C7"}
            getattr(p, k).update(v) if per_class else setattr(p, k, {c: v for c in p.d0})
        elif hasattr(p, k):
            setattr(p, k, v)
    return p


def write_components(path: Path, grid, comp: dict, meta: dict, rest: dict | None = None):
    """Bands C1..C7 (workday) and, for the classes whose rest-day allocation differs, C<k>_rest."""
    import rasterio
    names = list(BANDS)
    layers = [comp["N"] if b == "C1" else comp[b] for b in BANDS]
    if rest is not None:
        for b in BANDS[1:]:
            if not np.array_equal(rest[b], comp[b]):
                names.append(f"{b}_rest"); layers.append(rest[b])
    arr = np.stack(layers).astype(np.float32)
    prof = dict(driver="GTiff", height=grid.ny, width=grid.nx, count=len(names), dtype="float32",
                crs=grid.crs.to_wkt(), transform=grid.transform(), tiled=True, blockxsize=256, blockysize=256,
                BIGTIFF="IF_SAFER", nodata=None, **COMPRESSION)
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **prof) as dst:
        dst.write(arr)
        for i, b in enumerate(names, 1):
            dst.set_band_description(i, b)
        dst.update_tags(**{k: (json.dumps(v) if not isinstance(v, str) else v) for k, v in meta.items()})
    tmp.replace(path)


def effective_kernels(params: Params, iso3: str) -> dict:
    """Kernels used for this city: the country overrides applied, then the rest-day overrides."""
    out = {}
    for dt in ("workday", "restday"):
        q = params.for_country(iso3).for_daytype(dt)
        out[dt] = {c: {"kind": q.k(c), "d0_m": float(q.d0[c]), "beta": float(q.beta.get(c, 1.0))} for c in q.d0}
    return out


def network_ready(stem: str, params: Params, iso3: str):
    """With transit 'network': the layer of 02_calculate_in_transit_population.py exists and was made with this city's
    kernels and destination specifications (layers without these records are accepted). Returns (ok, reason)."""
    f = configuration.NETWORK / f"{stem}.npz"
    if not f.exists():
        return False, "no network layer"
    try:
        st = json.loads(str(np.load(f)["stats"]))
    except Exception:  # noqa: BLE001
        return True, ""
    k = st.get("kernels")
    if not k:
        return True, ""
    for dt in ("workday", "restday"):
        q = params.for_country(iso3).for_daytype(dt)
        for c, (kind, d0, beta) in k[dt].items():
            if kind != q.k(c) or abs(d0 - float(q.d0[c])) > 1e-6 or abs(beta - float(q.beta.get(c, 1.0))) > 1e-9:
                return False, f"network layer made with other kernels ({dt} {c}: {kind} {d0} {beta})"
    att = st.get("attractors")
    if att:
        for dt in ("workday", "restday"):
            q = params.for_country(iso3).for_daytype(dt)
            for c, spec in att[dt].items():
                cur = q.attractor[c] if isinstance(q.attractor[c], str) else json.dumps(q.attractor[c], sort_keys=True)
                if spec != cur:
                    return False, f"network layer made with other destinations ({dt} {c})"
    return True, ""


def run_city(row: dict, params: Params, out: Path):
    stem = row["stem"]
    g = grid_of(row)
    layers = load_layers(stem)
    N, V, P = layers
    both = components_daytypes(stem, params, layers=layers)
    comp, rest = both["workday"], both["restday"]
    configuration.DESTINATION_POPULATION.mkdir(parents=True, exist_ok=True)
    destination_file = configuration.DESTINATION_POPULATION / f"{stem}.npz"
    destination_tmp = destination_file.with_suffix(".tmp.npz")
    np.savez_compressed(destination_tmp, **{f"{c}_{dt}": both[dt][c] for dt in ("workday", "restday") for c in ("C2", "C3", "C4", "C5", "C7")})
    destination_tmp.replace(destination_file)
    iso = row.get("iso3") or stem.split("_")[1]
    meta = {"stem": stem, "name": row.get("name"), "iso3": row.get("iso3"), "pop_domain": float(N.sum()),
            "poi_per_1000": poi_density(P), "poi_weight": poi_weight(P), "stay_share": comp["_stay_share"],
            "has_floor_area": "FA_C1" in P, "has_total_volume": "_VT" in P,
            "params": asdict(params.for_country(iso)),          # v2: the parameters of this city (country overrides applied)
            "params_file": PARAMS_FILE,
            "params_effective": effective_kernels(params, iso),
            "band_sums": {b: float((comp["N"] if b == "C1" else comp[b]).sum()) for b in BANDS},
            "crs_proj4": g.crs.to_proj4(), "x0": g.x0, "y1": g.y1, "nx": g.nx, "ny": g.ny, "cell_m": g.cell}
    write_components(out / f"{stem}.tif", g, comp, {"model": "GlobalDynPop_100m components"}, rest=rest)
    meta["stay_share_restday"] = rest["_stay_share"]
    meta["transit"] = {"workday": comp.get("_transit", "gauss"), "restday": rest.get("_transit", "gauss")}   # C6 source (v2: network)
    a = configuration.POI_CHINA / f"{stem}.npz"
    meta["poi_source_amap"] = a.exists()
    (out / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--params", help="JSON file or inline JSON with Params fields")
    ap.add_argument("--order", default="small", choices=["small", "large", "list"])
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--out", default=str(configuration.COMPONENTS))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--reset-locks", action="store_true")
    ap.add_argument("--allow-missing-fa", action="store_true",
                    help="also run cities without 04_intermediate/demo/stage_2/buildings/floor_area_by_use/<stem>.npz (default: skip them)")
    ap.add_argument("--follow", action="store_true",
                    help="keep looping until every listed city is done, picking up cities as s04 writes their floor area")
    ap.add_argument("--max-cells", type=int, default=None, help="skip cities with more grid cells (memory)")
    ap.add_argument("--allow-gauss-transit", action="store_true",
                    help="with transit 'network': also run cities without a network layer (v1 approximation for C6)")
    ap.add_argument("--poll-s", type=int, default=120)
    a = ap.parse_args(argv)
    spec = {}
    if a.params:
        spec = json.loads(Path(a.params).read_text(encoding="utf-8")) if Path(a.params).exists() else json.loads(a.params)
    params = params_from(spec)
    global PARAMS_FILE
    PARAMS_FILE = Path(a.params).name if a.params and Path(a.params).exists() else ("inline" if a.params else "defaults")
    c = load_cities()
    stems = list(a.stems or [])
    if a.stems_file:
        stems += [l.strip() for l in open(a.stems_file, encoding="utf-8") if l.strip()]
    if stems:
        c = c[c.stem.isin(stems)]
        if a.order == "list":
            c = c.set_index("stem").loc[[s for s in dict.fromkeys(stems) if s in set(c.stem)]].reset_index()
    if a.order != "list":
        c = c.assign(_n=c.nx * c.ny).sort_values("_n", ascending=(a.order == "small"))
    k, n = (int(x) for x in a.shard.split("/"))
    c = c.iloc[k::n]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.reset_locks:
        import work_queue as _wq
        _wq.clear(out)
    if a.max_cells:
        c = c[c.nx * c.ny <= a.max_cells]
    logdir = configuration.LOGS / ("components" if out.resolve() == configuration.COMPONENTS.resolve() else f"components_{out.name}")
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"run_{os.environ.get('DYNAMIC_POPULATION_WORKER') or f'{k}of{n}'}.jsonl"     # one record per city
    import memory_guard as memory_guard
    import work_queue as work_queue
    rows = c.to_dict("records")
    done_now = set()          # written by this process (with --overwrite the .tif exists before the run)
    while True:
        waiting = 0
        for row in rows:
            stem = row["stem"]
            tif = out / f"{stem}.tif"
            if stem in done_now or (tif.exists() and (not a.overwrite or work_queue.written_in_this_run(tif))):
                continue
            if not a.allow_missing_fa and not (configuration.FLOOR_AREA / f"{stem}.npz").exists():
                waiting += 1
                continue
            if params.transit == "network" and not a.allow_gauss_transit:
                ok, why = network_ready(stem, params, row.get("iso3") or stem.split("_")[1])
                if not ok:
                    if why.startswith("network layer made"):
                        print(json.dumps({"stem": stem, "skip": why}), flush=True)
                    waiting += 1
                    continue
            memory_guard.wait(log=lambda m: print(json.dumps({"stem": stem, "memory": m}), flush=True))   # only with DYNAMIC_POPULATION_MEMWAIT_GB
            lock = work_queue.claim(out, stem)      # several processes can share the cities (run_parallel.py)
            if lock is None:
                continue
            t0 = time.time()
            try:
                m = run_city(row, params, out)
                rec = {"stem": stem, "pop_domain": m["pop_domain"], "poi_weight": round(m["poi_weight"], 4),
                       "stay_share": round(m["stay_share"], 4), "has_floor_area": m["has_floor_area"], "error": None}
            except Exception as e:  # noqa: BLE001
                rec = {"stem": stem, "error": repr(e), "trace": traceback.format_exc()[-1500:]}
            rec["wall_s"] = round(time.time() - t0, 1)
            work_queue.release(lock)
            done_now.add(stem)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(json.dumps({x: rec.get(x) for x in ("stem", "poi_weight", "stay_share", "wall_s", "error")}), flush=True)
        if not a.follow or waiting == 0:
            break
        print(json.dumps({"waiting_for_inputs": waiting}), flush=True)
        time.sleep(a.poll_s)


if __name__ == "__main__":
    main()
