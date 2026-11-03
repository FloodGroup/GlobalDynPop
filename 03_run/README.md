# Running the model

The run folders follow the same four stages as the [scientific programs](../02_code/README.md).

| Run folder | Executes | Result |
|---|---|---|
| `stage_1_data_inputs/` | Verify original-source file integrity | Raw-source check |
| `stage_2_100m_layers/` | Generate city grids, population/building layers, place counts, floor area and routing graphs from raw city subsets; then save smoothed places and effective kernels | Stage 2 intermediates |
| `stage_3_activity_allocation/` | Destination attractiveness, network assignment and destination population allocation | Stage 3 intermediates and packaged components |
| `stage_4_outputs/` | Hourly population, functional land use, population maps and numerical checks | Stage 4 outputs |

Run all four stages:

```console
python 03_run/run_city_demo.py run
```

Run one stage, for example Stage 3:

```console
python 03_run/run_city_demo.py run --stage 3
```

Check the supplied processed layers and outputs:

```console
python 03_run/run_city_demo.py check
```

On Windows, use `RUN_ALL_STAGES.cmd` for the full example or `01_RUN.cmd`, `02_RUN.cmd`, `03_RUN.cmd` or `04_RUN.cmd` inside the corresponding stage folder. `environment.cmd` contains common environment settings. `runtime/` holds the shared worker launcher, task locks and memory monitoring; these support execution across stages.

`stage_2_100m_layers/02_RUN.cmd` executes Stage 2 programs 01 through 06 in order. Step 04 reads the raw building records, calls `buildings.py` to calculate floor area and writes `buildings/floor_area_by_use/`. Every spatial layer is recomputed; existing files do not cause a step to be skipped. Hourly location shares and calibrated parameters are adopted study products.

`stage_2_100m_layers/rebuild_from_sources.cmd` uses the separate `--global-sources` interface, which requires external global datasets and source access. See the [Stage 2 code guide](../02_code/stage_2_100m_layers/README.md). Each stage writes to its designated intermediate/output location.

Stage 4 also writes the population and time-use figures to `06_docs/figures/`. Set `DYNAMIC_POPULATION_FIGURES` to choose a different figure directory. See the [Stage 4 method](../06_docs/methods/stage_4_outputs.md) for plotting settings and standalone commands.

## Run configuration and numerical checks

`demo_configuration/` stores the three city stems, the file manifest used for input integrity, and the decoded-array fingerprints used for numerical reproduction. The runner reads these files directly. The [example guide](../06_docs/reproduction/city_demo.md) documents city selection and dataset attribution.

## Recorded environment

Requires Python 3.11 or newer. The three-city run was checked on Windows-11-10.0.26200-SP0 with Python 3.12.7. The recorded package versions are numpy 1.26.4, scipy 1.13.1, pyproj 3.7.2, shapely 2.2.0, pandas 2.2.2, matplotlib 3.9.2, numba 0.60.0. These versions describe the recorded full model run; `environment.yml` specifies compatible dependencies without locking every package version. The [automated checks](../.github/workflows/checks.yml) verify the bundled input hashes and decoded output arrays on Ubuntu and Windows with Python 3.11. They do not execute a full model rebuild or test a fresh installation of the complete Conda environment.

## Other city inputs and result comparison



For the bundled three cities, follow the [example guide](../06_docs/reproduction/city_demo.md). For other cities, supply the complete, licensed input tree separately and set DYNAMIC_POPULATION_STAGE2 to its root. The model entry points are 02_calculate_in_transit_population.py (network), 03_calculate_population_components.py (components), 01_generate_hourly_population.py (24-hour grids) and 02_classify_functional_land_use.py (land use). They are in the stage folders under 02_code. Consult each script's --help. Ensure DYNAMIC_POPULATION_ROOT points to the repository root, DYNAMIC_POPULATION_WORK and DYNAMIC_POPULATION_OUTPUTS are writable, and DYNAMIC_POPULATION_NETWORK contains the intended network version. Select the cities to process with explicit stems.

The three-city wrapper checks expected stage outputs and checks the results against stored numerical fingerprints. For other inputs, inspect each output and log: some underlying scripts print per-city errors while exiting zero.

## Raw-input rebuild and validation

`03_run/stage_2_100m_layers/02_RUN.cmd` rebuilds the local example from its raw spatial subsets. `rebuild_from_sources.cmd` selects the separate external global-source interfaces with `--global-sources`; those require source access and permissions. Survey harmonisation and calibration require their own upstream records. A historical release may no longer be downloadable. Record any changed source version and its numerical consequences. Raw observation files are not supplied. Repeating observation-based validation requires the corresponding observation bundle and schema. The three-city numerical checks do not replace observation-based validation.

## Compare results

`python 02_code/stage_4_outputs/05_compare_results.py --net-a REF --net-b RUN --stems CITY` compares network arrays. The same checker supports --a/--b for components and --hourly-a/--hourly-b for hourly grids. It rejects missing inputs, empty comparisons, incompatible arrays, non-finite values and mismatched raster grids. Raster comparisons require rasterio. Numerical tolerance is relative to the largest reference-cell magnitude; inspect absolute differences as well.
