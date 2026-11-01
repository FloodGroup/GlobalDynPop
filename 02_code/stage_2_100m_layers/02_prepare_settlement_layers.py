"""Stage 2, step 2: native GHSL raster crops to 100 m city layers.

The local workflow regenerates resident population, total and non-residential
building volume (2025), and building height (2018), using each source raster's
CRS and transform. Use --global-sources for the tile-download interface."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_1_data_inputs.configuration as configuration  # noqa: E402
from stage_2_100m_layers.cities import load_cities  # noqa: E402
from stage_2_100m_layers.global_human_settlement_layer import accumulate, sample  # noqa: E402


def global_main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", nargs="+", default=["pop", "vol_nres"])
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--stems-file")
    ap.add_argument("--sub", type=int, default=4)
    a = ap.parse_args(argv)
    c = load_cities()
    stems = list(a.stems or [])
    if a.stems_file:
        stems += [l.strip() for l in open(a.stems_file, encoding="utf-8") if l.strip()]
    if stems:
        c = c[c.stem.isin(stems)]
    for p in a.products:
        if p in configuration.SAMPLED_PRODUCTS:
            sample(p, c, configuration.GHSL[p])
        else:
            accumulate(p, c, configuration.GHSL[p], sub=a.sub)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--global-sources" in arguments:
        arguments.remove("--global-sources")
        return global_main(arguments)
    from stage_2_100m_layers.local_raw_preparation import run_step
    return run_step(2, arguments)


if __name__ == "__main__":
    main()
