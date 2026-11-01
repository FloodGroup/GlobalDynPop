# -*- coding: utf-8 -*-
"""Check the finished outputs of a step and set damaged files aside, so that running the step again recomputes them
(after a crash or a power failure of the computer a file can exist with incomplete contents).

    python 02_code/stage_4_outputs/04_verify_outputs.py --step network|components|hourly [--jobs 8] [--move-damaged]

  network     04_intermediate/demo/stage_3/in_transit_population/<city>.npz: every array can be read (the archive checksums are verified)
  components  05_outputs/demo/population_components/<city>.tif and .json: the JSON can be read, every band of the GeoTIFF can be
              read and its sum agrees with the band sums recorded in the JSON
  hourly      05_outputs/demo/hourly_population/<city>/<daytype>/<city>_<daytype>_hour_<HH>.tif:
              one readable band per file, with local-hour metadata and a people_total tag
With --move-damaged a damaged file is renamed to <file>.damaged (nothing is deleted); for the components the JSON
and the GeoTIFF of a city are set aside together. run_parallel.py runs this check before the steps network,
components and hourly. Report: 04_intermediate/logs/check_<step>.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration  # noqa: E402

BANDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")


def network_ok(f: str) -> str:
    try:
        with np.load(f) as z:
            json.loads(str(z["stats"]))
            for k in z.files:
                np.asarray(z[k]).sum() if z[k].dtype.kind in "fiu" else z[k]
        return ""
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:120]}"


def components_ok(f: str) -> str:
    import rasterio
    p = Path(f)
    j = p.with_suffix(".json")
    try:
        meta = json.loads(j.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return f"json: {type(e).__name__}"
    try:
        sums = meta.get("band_sums") or {}
        with rasterio.open(p) as src:
            names = list(src.descriptions)
            for i, b in enumerate(names, 1):
                a = src.read(i)
                s = float(a.sum(dtype=np.float64))
                if not np.isfinite(s):
                    return f"band {b}: not finite"
                ref = sums.get(b)
                if ref is not None and abs(s - ref) > 1e-3 * max(abs(ref), 1.0) + 0.002 * a.size:
                    return f"band {b}: sum {s:.0f} against {ref:.0f}"
        if not all(b in names for b in BANDS):
            return "bands missing"
        return ""
    except Exception as e:  # noqa: BLE001
        return f"tif: {type(e).__name__}: {str(e)[:120]}"


def hourly_ok(f: str) -> str:
    import rasterio
    try:
        with rasterio.open(f) as src:
            if src.count != 1:
                return f"{src.count} bands; expected one"
            tags = src.tags()
            hour = int(tags["hour"])
            if not 0 <= hour <= 23 or src.descriptions != (f"hour_{hour:02d}",):
                return "hour metadata mismatch"
            values = src.read(1)
            if not np.isfinite(values).all() or (values < 0).any():
                return "invalid population values"
            total = float(values.sum(dtype=np.float64))
            reference = float(tags["people_total"])
            if abs(total - reference) > 1e-3 * max(abs(reference), 1.0) + 1.0:
                return f"sum {total:.0f} against {reference:.0f}"
        return ""
    except Exception as error:
        return f"{type(error).__name__}: {str(error)[:120]}"


STEPS = {"network": (lambda: sorted(configuration.NETWORK.glob("*.npz")), network_ok),
         "components": (lambda: sorted(p for p in configuration.COMPONENTS.glob("*.tif") if not p.name.endswith(".tmp.tif")), components_ok),
         "hourly": (lambda: sorted(p for p in configuration.HOURLY.glob("*/*/*.tif") if not p.name.endswith(".tmp.tif")), hourly_ok)}


def set_aside(p: Path):
    for q in ([p, p.with_suffix(".json")] if p.suffix == ".tif" and p.parent == configuration.COMPONENTS else [p]):
        if q.exists():
            k, dst = 0, q.with_name(q.name + ".damaged")
            while dst.exists():
                k += 1
                dst = q.with_name(q.name + f".damaged{k}")
            q.replace(dst)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True, choices=list(STEPS))
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("DYNAMIC_POPULATION_WORKERS") or 4))
    ap.add_argument("--move-damaged", action="store_true")
    a = ap.parse_args(argv)
    files, check = STEPS[a.step]
    fs = [str(p) for p in files()]
    if a.step == "components":                 # a JSON without its GeoTIFF: set aside too
        for j in sorted(configuration.COMPONENTS.glob("*.json")):
            if not j.with_suffix(".tif").exists() and a.move_damaged:
                set_aside(j)
    bad = {}
    if fs:
        with ProcessPoolExecutor(max_workers=max(1, min(a.jobs, len(fs)))) as ex:
            for f, why in zip(fs, ex.map(check, fs, chunksize=8)):
                if why:
                    bad[f] = why
    if a.move_damaged:
        for f in bad:
            set_aside(Path(f))
    rep = {"step": a.step, "files": len(fs), "damaged": len(bad), "set_aside": bool(a.move_damaged),
           "list": {Path(f).name: w for f, w in bad.items()}}
    configuration.LOGS.mkdir(parents=True, exist_ok=True)
    (configuration.LOGS / f"check_{a.step}.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"check {a.step}: {len(fs)} files, {len(bad)} damaged" + (" (set aside, recomputed by the step)" if bad and a.move_damaged else ""),
          flush=True)
    for f, w in list(bad.items())[:20]:
        print("   ", Path(f).name, w, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
