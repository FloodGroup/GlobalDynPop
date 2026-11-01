# -*- coding: utf-8 -*-
"""Run one step with several processes at once; the processes share the cities through lock files.

    python 03_run/runtime/run_parallel.py [--workers 12] [--large 3] --name network [--then=<arguments>]
                                           -- 02_code/stage_3_activity_allocation/02_calculate_in_transit_population.py [arguments of the step]

The step (05_prepare_transport_graphs.py, 02_calculate_in_transit_population.py, 03_calculate_population_components.py or 01_generate_hourly_population.py) is started --workers times with the same
arguments; --large of the processes take the cities from the largest down (--order large), the others from the
smallest up, so that few large cities run at the same time. The processes run at below-normal priority (the
computer stays usable) and each writes 04_intermediate/logs/<name>/worker_<k>.log; every minute the number of
finished cities is printed. Before the start, lock files left by an interrupted run are removed (do not run the
same step twice at the same time). --then runs the step once more with these arguments when all processes have
finished (e.g. --then=--index-only for the index of the hourly maps). Defaults: DYNAMIC_POPULATION_WORKERS, DYNAMIC_POPULATION_LARGE_WORKERS
(environment, 03_run/environment.cmd); before each city a process waits until DYNAMIC_POPULATION_MEMWAIT_GB of memory are free.
Before the steps network, components and hourly, the outputs that exist already are checked and damaged files
(after a crash of the computer) are set aside, so that they are recomputed (04_verify_outputs.py). Every process uses
one thread for numerical libraries (OMP_NUM_THREADS etc. = 1, unless set), and while the free memory of the computer
is below DYNAMIC_POPULATION_MIN_FREE_GB (default: 15 % of the memory, at least 4 GB) no process starts a new city (the cities that
are running go on); the progress line shows the free memory.
Exit code 1 when a process failed or a city reported an error (listed in errors.txt of the log folder).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "02_code"))
import stage_1_data_inputs.configuration as configuration
import work_queue as work_queue  # noqa: E402

OUTPUTS = {  # step -> (folder of the outputs, pattern of one finished city)
    "05_prepare_transport_graphs.py": (lambda a: Path(a.get("--out") or configuration.ROAD_GRAPHS), "*.npz"),
    "02_calculate_in_transit_population.py": (lambda a: Path(a.get("--out") or configuration.NETWORK), "*.npz"),
    "03_calculate_population_components.py": (lambda a: Path(a.get("--out") or configuration.COMPONENTS), "*.tif"),
    "01_generate_hourly_population.py": (lambda a: Path(a.get("--out") or configuration.HOURLY), "*/rest_day/*_rest_day_hour_23.tif"),
    "02_classify_functional_land_use.py": (lambda a: Path(a.get("--out") or configuration.OUTPUTS / "functional_land_use"), "*/*_functional_land_use_attributes.tif"),
}


CHECK = {"02_calculate_in_transit_population.py": "network", "03_calculate_population_components.py": "components", "01_generate_hourly_population.py": "hourly"}


def free_gb():
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:  # noqa: BLE001
        return None


def min_free_gb() -> float:
    v = os.environ.get("DYNAMIC_POPULATION_MIN_FREE_GB")
    if v:
        return float(v)
    try:
        import psutil
        return max(4.0, 0.15 * psutil.virtual_memory().total / 1e9)
    except Exception:  # noqa: BLE001
        return 4.0


def opts(args):
    d = {}
    for i, x in enumerate(args):
        if x.startswith("--"):
            d[x] = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else ""
    return d


def count(folder: Path, pattern: str) -> int:
    return sum(1 for p in folder.glob(pattern) if not p.name.startswith(".") and ".tmp." not in p.name)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        raise SystemExit("usage: run_parallel.py [options] -- <script> [arguments]")
    cut = argv.index("--")
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=int(os.environ.get("DYNAMIC_POPULATION_WORKERS") or 4))
    ap.add_argument("--large", type=int, default=int(os.environ.get("DYNAMIC_POPULATION_LARGE_WORKERS") or 2))
    ap.add_argument("--name", required=True)
    ap.add_argument("--then", default="", help="arguments of one more run of the step after all processes")
    ap.add_argument("--stagger-s", type=float, default=3.0)
    a = ap.parse_args(argv[:cut])
    script, sargs = argv[cut + 1], argv[cut + 2:]
    base = Path(script).name
    workers = max(1, a.workers)
    large = min(max(0, a.large), workers - 1) if workers > 1 else 0
    logdir = configuration.LOGS / a.name
    logdir.mkdir(parents=True, exist_ok=True)
    for f in logdir.glob("worker_*.log"):                          # the logs of the previous run are kept as .prev
        f.replace(f.with_suffix(".prev"))
    outdir, pattern = (OUTPUTS[base][0](opts(sargs)), OUTPUTS[base][1]) if base in OUTPUTS else (None, None)
    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=True)
        n = work_queue.clear(outdir)
        if n:
            print(f"removed {n} lock files of an interrupted run", flush=True)
    total = len(open(configuration.CITY_TABLE, encoding="utf-8").read().splitlines()) - 1
    flags = 0x00004000 if os.name == "nt" else 0                 # BELOW_NORMAL_PRIORITY_CLASS
    pre = None if os.name == "nt" else (lambda: os.nice(5))
    env = dict(os.environ, PYTHONUTF8="1", DYNAMIC_POPULATION_RUN_START=str(time.time()))
    env.setdefault("DYNAMIC_POPULATION_MEMWAIT_GB", "2")
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        env.setdefault(v, "1")                                    # many processes: one thread each
    pause = logdir / "PAUSE_low_memory"
    if pause.exists():
        pause.unlink()
    env["DYNAMIC_POPULATION_PAUSE_FILE"] = str(pause)
    min_free = min_free_gb()
    if base in CHECK and "--out" not in sargs:                    # damaged outputs of an earlier run are recomputed
        print(time.strftime("%H:%M:%S"), f"{a.name}: checking the outputs that exist already", flush=True)
        subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / "02_code" / "stage_4_outputs" / "04_verify_outputs.py"), "--step", CHECK[base],
                        "--jobs", str(min(workers, 8)), "--move-damaged"], cwd=configuration.ROOT, env=env, creationflags=flags)
    has_order = "--order" not in sargs and base in OUTPUTS
    procs = []
    t0 = time.time()
    print(time.strftime("%H:%M:%S"), f"{a.name}: {workers} processes ({large} from the largest city) of {base}", flush=True)
    for k in range(workers):
        cmd = [sys.executable, script, *sargs]
        if has_order:
            cmd += ["--order", "large" if k < large else "small"]
        fh = open(logdir / f"worker_{k:02d}.log", "w", encoding="utf-8")
        fh.write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(cmd[1:])}\n"); fh.flush()
        p = subprocess.Popen(cmd, cwd=configuration.ROOT, env=dict(env, DYNAMIC_POPULATION_WORKER=f"{k:02d}"), stdout=fh, stderr=subprocess.STDOUT,
                             creationflags=flags, preexec_fn=pre)
        procs.append((p, fh))
        time.sleep(a.stagger_s)
    last = -1
    while any(p.poll() is None for p, _ in procs):
        time.sleep(5)
        free = free_gb()
        if free is not None:                       # no new city while the free memory is low
            if free < min_free and not pause.exists():
                pause.write_text(f"free memory {free:.1f} GB < {min_free:.1f} GB", encoding="utf-8")
                print(time.strftime("%H:%M:%S"), f"{a.name}: free memory {free:.1f} GB - no new city until "
                      f"{min_free + 2:.1f} GB are free", flush=True)
            elif free >= min_free + 2 and pause.exists():
                pause.unlink()
                print(time.strftime("%H:%M:%S"), f"{a.name}: free memory {free:.1f} GB - going on", flush=True)
        if time.time() - last >= 60:
            last = time.time()
            running = sum(p.poll() is None for p, _ in procs)
            done = count(outdir, pattern) if outdir is not None else 0
            mem = f", free memory {free:.1f} GB" if free is not None else ""
            print(time.strftime("%H:%M:%S"), f"{a.name}: {done}/{total} cities done, {running} processes running, "
                  f"{(time.time() - t0) / 60:.0f} min{mem}", flush=True)
    if pause.exists():
        pause.unlink()
    for _, fh in procs:
        fh.close()
    rcs = [p.returncode for p, _ in procs]
    errors = []
    for f in sorted(logdir.glob("worker_*.log")):
        for line in open(f, encoding="utf-8", errors="replace"):
            if line.startswith("{") and '"error"' in line:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("error"):
                    errors.append({"worker": f.stem, "stem": d.get("stem"), "error": str(d["error"])[:300]})
    errors = list({e["stem"]: e for e in errors}.values())        # one entry per city
    if a.then:
        cmd = [sys.executable, script, *sargs, *shlex.split(a.then)]
        with open(logdir / "then.log", "w", encoding="utf-8") as fh:
            rcs.append(subprocess.run(cmd, cwd=configuration.ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT).returncode)
    done = count(outdir, pattern) if outdir is not None else 0
    with open(logdir / "errors.txt", "w", encoding="utf-8") as fh:
        for e in errors:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    summary = {"step": a.name, "script": base, "workers": workers, "minutes": round((time.time() - t0) / 60, 1),
               "cities_done": done, "cities_total": total, "errors": len(errors), "exit_codes": rcs}
    (logdir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(time.strftime("%H:%M:%S"), json.dumps(summary), flush=True)
    for e in errors[:20]:
        print("  error:", e["stem"], e["error"][:160], flush=True)
    return 1 if any(rcs) or errors else 0


if __name__ == "__main__":
    sys.exit(main())
