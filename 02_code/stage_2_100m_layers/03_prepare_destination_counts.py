"""Stage 2, step 3: raw Overture places to classified counts on city grids.

Reads the supplied city Parquet files by default. Use --global-sources for
the external source-index interface. Outputs point_of_interest_counts/overture/."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration  # noqa: E402
from stage_2_100m_layers.cities import load_cities  # noqa: E402
from stage_2_100m_layers.places import Reader, build_index, city_places  # noqa: E402


def global_main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    a = ap.parse_args(argv)
    c = load_cities()
    stems = list(a.stems or [])
    if a.stems_file:
        stems += [l.strip() for l in open(a.stems_file, encoding="utf-8") if l.strip()]
    if stems:
        c = c[c.stem.isin(stems)]
    out = configuration.POI_OVERTURE; out.mkdir(parents=True, exist_ok=True)
    idx = out / f"places_rowgroup_index_{configuration.OVERTURE_RELEASE}.parquet"
    if not idx.exists():
        t = time.time(); build_index(idx); print(f"index built in {time.time() - t:.0f} s")
    rd = Reader(idx)
    stats_path = out / "_stats.csv"
    stats = pd.read_csv(stats_path).to_dict("records") if stats_path.exists() else []
    done = {s["stem"] for s in stats}
    for row in c.to_dict("records"):
        if row["stem"] in done and (out / f"{row['stem']}.npz").exists():
            continue
        t = time.time()
        arr, st = city_places(rd, row)
        np.savez_compressed(out / f"{row['stem']}.npz", **arr)
        st.update(stem=row["stem"], seconds=round(time.time() - t, 1))
        stats = [s for s in stats if s["stem"] != row["stem"]] + [st]
        pd.DataFrame(stats).to_csv(stats_path, index=False)
        print(json.dumps(st), flush=True)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--global-sources" in arguments:
        arguments.remove("--global-sources")
        return global_main(arguments)
    from stage_2_100m_layers.local_raw_preparation import run_step
    return run_step(3, arguments)


if __name__ == "__main__":
    main()
