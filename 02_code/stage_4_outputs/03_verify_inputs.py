"""Stage 4, step 3: check the inputs of the model before a run (no internet needed).

    python 02_code/stage_4_outputs/03_verify_inputs.py [--full] [--manifest MANIFEST.json]

For every input folder of 01_inputs the number of files is compared with the city table (one file per city where the
model needs one), and the files of a sample of cities (all files with --full) are compared with the sizes and SHA-256
checksums of the package manifest (MANIFEST.json in the package root). The restricted folders are reported but not
required: the model runs without them; only some validation steps need them.
Exit code 1 when a required input is missing or differs from the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration  # noqa: E402
from stage_2_100m_layers.cities import load_cities  # noqa: E402

# (label, folder, file pattern per city or None, required)
PER_CITY = [
    ("residents, GHS-POP", configuration.GHSL["pop"], "{stem}.npy", True),
    ("built volume, GHS-BUILT-V", configuration.GHSL["vol"], "{stem}.npy", True),
    ("non-residential volume, GHS-BUILT-V NRES", configuration.GHSL["vol_nres"], "{stem}.npy", True),
    ("building height, GHS-BUILT-H", configuration.GHSL["height"], "{stem}.npy", True),
    ("floor area by use", configuration.FLOOR_AREA, "{stem}.npz", True),
    ("Overture places", configuration.POI_OVERTURE, "{stem}.npz", True),
    ("OpenStreetMap POIs", configuration.POI_OSM, "{stem}.npz", False),
    ("road and rail network", configuration.ROAD_GRAPHS, "{stem}.npz", True),
    ("water coverage percent (functional land use)", configuration.WATER_COVERAGE_PERCENT, "{stem}.npz", False),
]
FILES = [
    ("city table", configuration.CITY_TABLE, True),
    ("model parameters", configuration.MODEL_PARAMS, True),
    ("hourly shares, index", configuration.DAYTYPE_DIR / "location_share_sources.csv", True),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="checksums of every input file (slow)")
    ap.add_argument("--manifest", default=str(configuration.ROOT / "MANIFEST.json"))
    a = ap.parse_args(argv)
    stems = list(load_cities().stem)
    bad = 0
    print(f"{len(stems)} cities in {configuration.CITY_TABLE.relative_to(configuration.ROOT)}")
    for label, folder, pat, req in PER_CITY:
        miss = [s for s in stems if not (folder / pat.format(stem=s)).exists()]
        state = "ok" if not miss else ("MISSING" if req else "incomplete (optional)")
        print(f"  {label:42s} {folder.relative_to(configuration.ROOT)}: {len(stems) - len(miss)} of {len(stems)} {state}"
              + (f" (first missing: {miss[0]})" if miss else ""))
        bad += bool(miss and req)
    cn = load_cities()
    chn = list(cn[cn.iso3 == "CHN"].stem)
    have = sum((configuration.POI_CHINA / f"{s}.npz").exists() for s in chn)
    print(f"  {'China POI layers':42s} {configuration.POI_CHINA.relative_to(configuration.ROOT)}: {have} of {len(chn)} Chinese cities")
    for label, f, req in FILES:
        ok = Path(f).exists()
        print(f"  {label:42s} {Path(f).relative_to(configuration.ROOT)}: {'ok' if ok else ('MISSING' if req else 'missing (optional)')}")
        bad += bool(req and not ok)
    for label, folder in (("restricted inputs (local only)", configuration.INPUTS_RESTRICTED),
                          ("restricted observations (local only)", configuration.RESTRICTED)):
        n = sum(1 for _ in folder.rglob("*") if _.is_file()) if folder.exists() else 0
        print(f"  {label:42s} {folder.relative_to(configuration.ROOT) if folder.is_relative_to(configuration.ROOT) else folder}: "
              f"{n} files{'' if n else ' (not present: the steps that need them report it and go on)'}")
    mf = Path(a.manifest)
    if mf.exists():
        man = json.loads(mf.read_text(encoding="utf-8"))
        files = man["files"]
        sample = set(stems[:: max(1, len(stems) // 25)])
        todo = [(p, m) for p, m in files.items() if p.startswith("04_intermediate/demo/stage_2/")
                and (a.full or any(s in p for s in sample) or "/" not in p[len("04_intermediate/demo/stage_2/"):].strip("/"))]
        diff = 0
        for p, m in todo:
            f = configuration.ROOT / p
            if not f.exists():
                continue
            if f.stat().st_size != m["size"] or ("sha256" in m and sha256(f) != m["sha256"]):
                print("  differs from the manifest:", p); diff += 1
        print(f"  manifest: {len(todo)} files checked, {diff} differ")
        bad += diff
    else:
        print("  no manifest found: sizes and checksums not checked")
    print("inputs complete" if not bad else f"{bad} problem(s) with the inputs")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
