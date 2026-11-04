"""Check required model inputs offline; --full also opens every city array."""
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
    ("water coverage percent", configuration.WATER_COVERAGE_PERCENT, "{stem}.npz", True),
    ("GBA cell attributes", configuration.GBA_CELLS, "{stem}.npz", True),
    ("permanent water", configuration.BASEMAP / "landcover", "{stem}.npz", True),
    ("typed open space", configuration.OPEN_SPACE, "{stem}.npz", True),
]
FILES = [
    ("city table", configuration.CITY_TABLE, True),
    ("model parameters", configuration.MODEL_PARAMS, True),
    ("indoor shares", configuration.TIMEUSE / "w_indoor" / "w_indoor_cities.csv", True),
    ("hourly shares, index", configuration.DAYTYPE_DIR / "location_share_sources.csv", True),
]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="open every required city array")
    ap.add_argument("--stems", nargs="+")
    a = ap.parse_args(argv)
    stems = list(a.stems or load_cities().stem)
    unknown = set(stems) - set(load_cities().stem)
    if unknown: raise ValueError(f"Unknown cities: {sorted(unknown)}")
    bad = 0
    print(f"{len(stems)} cities in {configuration.CITY_TABLE}")
    for label, folder, pat, req in PER_CITY:
        miss = [s for s in stems if not (folder / pat.format(stem=s)).exists()]
        state = "ok" if not miss else ("MISSING" if req else "incomplete (optional)")
        print(f"  {label:42s} {folder.relative_to(configuration.ROOT) if folder.is_relative_to(configuration.ROOT) else folder}: {len(stems) - len(miss)} of {len(stems)} {state}"
              + (f" (first missing: {miss[0]})" if miss else ""))
        bad += bool(miss and req)
    cn = load_cities()
    chn = list(cn[cn.iso3 == "CHN"].stem)
    have = sum((configuration.POI_CHINA / f"{s}.npz").exists() for s in chn)
    print(f"  {'China POI layers':42s} {configuration.POI_CHINA}: {have} of {len(chn)} Chinese cities")
    for label, f, req in FILES:
        ok = Path(f).exists()
        print(f"  {label:42s} {Path(f)}: {'ok' if ok else ('MISSING' if req else 'missing (optional)')}")
        bad += bool(req and not ok)
    for label, folder in (("restricted inputs (local only)", configuration.INPUTS_RESTRICTED),
                          ("restricted observations (local only)", configuration.RESTRICTED)):
        n = sum(1 for _ in folder.rglob("*") if _.is_file()) if folder.exists() else 0
        print(f"  {label:42s} {folder.relative_to(configuration.ROOT) if folder.is_relative_to(configuration.ROOT) else folder}: "
              f"{n} files{'' if n else ' (not present: the steps that need them report it and go on)'}")
    if a.full:
        import numpy as np
        for _,folder,pattern,required in PER_CITY:
            for stem in stems:
                path=folder/pattern.format(stem=stem)
                if not path.exists():continue
                try:
                    array=np.load(path,allow_pickle=False)
                    if isinstance(array,np.lib.npyio.NpzFile):
                        with array:
                            for key in array.files:array[key]
                    else:array.shape
                except Exception as exc:
                    print("  unreadable input:",path,exc);bad+=1
    print("inputs complete" if not bad else f"{bad} problem(s) with the inputs")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
