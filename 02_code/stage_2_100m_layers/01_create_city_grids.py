"""Stage 2, step 1: raw urban-centre boundaries to local 100 m city grids.

Reads the supplied city GeoPackages by default. Use --global-sources for the
external global city-database interface. See --help for each mode."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration  # noqa: E402
from stage_2_100m_layers.cities import make_city_table  # noqa: E402


def global_main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pop-min", type=float, default=configuration.POP_MIN)
    ap.add_argument("--buffer-km", type=float, default=configuration.BUFFER_M / 1000)
    ap.add_argument("--v11", default=str(configuration.TIMEUSE / "V11"))
    ap.add_argument("--out", default=str(configuration.CITY_TABLE))
    a = ap.parse_args(argv)
    df = make_city_table(a.pop_min, a.buffer_km * 1000, v11_root=a.v11)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"{len(df)} cities, {df.iso3.nunique()} countries/areas, population {df.pop2025.sum()/1e9:.2f} bn, "
          f"domains {df.domain_km2.sum()/1e6:.2f} M km2, cells {(df.nx*df.ny).sum()/1e9:.3f} bn, largest {df.domain_km2.max():.0f} km2")
    miss = df[df.iso3.isna() | (df.country_zh == "")]
    if len(miss):
        print("no ISO3 or Chinese name:", miss[["stem", "country"]].drop_duplicates("country").to_string())


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--global-sources" in arguments:
        arguments.remove("--global-sources")
        return global_main(arguments)
    from stage_2_100m_layers.local_raw_preparation import run_step
    return run_step(1, arguments)


if __name__ == "__main__":
    main()
