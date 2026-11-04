# Running the three-city example

The four stages rebuild the example from local raw spatial inputs. Run from the repository root:

```console
conda env create -f environment.yml
conda activate dynamic-population
python 03_run/run_city_demo.py run
python 03_run/run_city_demo.py check
```

`run` executes all four stages, including transport-graph construction and road/rail population assignment. Every run recalculates the selected stages. `check` verifies results already generated in that run directory; it does not substitute bundled components or create missing results.

## Stage execution

The following commands execute the same calculations as a continuous run. Use the same `--out` directory for every command:

```console
python 03_run/run_city_demo.py run --stage 1
python 03_run/run_city_demo.py run --stage 2
python 03_run/run_city_demo.py run --stage 3
python 03_run/run_city_demo.py run --stage 4
python 03_run/run_city_demo.py check
```

| Stage | Execution order | Prerequisites |
|---|---|---|
| 1 | Verify raw subsets, then create city grid definitions | Bundled original spatial subsets |
| 2 | Programs 01–11: settlement, POIs, classified buildings, graph, water, recreation, land use, optional China AOIs, GBA, capacity/open-space fusion, model-layer export | Successful Stage 1 in the same run directory |
| 3 | 01 destination attractiveness → 02 road/rail transit assignment → 03 destination populations and components | Successful Stage 2 in the same run directory |
| 4 | 01 input checks → 02 hourly grids → 03 functional land use → numerical/output checks → 06–07 population and time-use figures | Successful Stages 2 and 3 in the same run directory |

Stage 2 program 08 applies only to Chinese cities with authorised AOI inputs; it is inapplicable to the three supplied Finnish and Japanese examples. Hourly shares, calibrated allocation settings, indoor shares and outdoor-microenvironment weights are adopted non-spatial model inputs. Survey harmonisation and calibration from individual records are outside this spatial reproduction workflow.

A missing prerequisite or calculation failure stops execution with a nonzero exit code. Rerunning an earlier stage invalidates completion of subsequent stages; run them again to propagate the new inputs. Existing outputs are overwritten by the calculations, not treated as completed work.

## Outputs and independent runs

The default run directory is `04_intermediate/demo/reproduction/`:

```text
stage_1/local_grids/       Regenerated city grid table
stage_2/                  Reconstructed spatial layers and adopted parameters
stage_3/                  Attractiveness, destination populations and newly assigned transit
outputs/population_components/
outputs/hourly_population/
outputs/functional_land_use/
figures/                  PNG figures from this run
figure_data/              Figure metadata
figure_exports/           PDF exports
verification.json         Stage completion and numerical checks
```

Use `--out PATH` for a separate run and `--stems CITY_ID ...` for selected example cities. Windows stage launchers forward these options. The runner sets all stage paths consistently; standalone numbered programs use the paths in `configuration.py` and accept the documented environment overrides.

## Source reconstruction and reference comparison

`python 03_run/run_raw_reconstruction.py --out PATH` invokes the same Stage 1 and Stage 2 implementation. It also writes `spatial_reference_comparison.json`, comparing rebuilt arrays with the bundled reference layers. `--compare-only` compares an existing reconstruction, and `--require-exact` exits unsuccessfully if a reference array differs. References are comparison targets, never substitutes for computed spatial layers or population components.

Program 05 in Stage 4 compares separate computed output trees, including each individual hourly raster. For two independent runs `run_a` and `run_b`:

```console
python 02_code/stage_4_outputs/05_compare_results.py --a run_a/outputs/population_components --b run_b/outputs/population_components --net-a run_a/stage_3/in_transit_population --net-b run_b/stage_3/in_transit_population --hourly-a run_a/outputs/hourly_population --hourly-b run_b/outputs/hourly_population --stems 00572_FIN_Helsinki 01027_JPN_Kitakyushu 05685_JPN_Takasaki_Maebashi --tol 0
```

This requires exact equality of decoded values; a positive `--tol` allows a relative tolerance. Program 08 redraws the independent global indoor-share, income and climate maps from archived figure data; it is not part of the three-city population calculation.

## Numerical checks

Checks include raw-file hashes, required arrays, finite/non-negative values, grid dimensions, indoor/outdoor fractions, normalised hourly shares, conservation of each destination/transit/component population, and all 144 hourly rasters for the three cities. Hourly values must agree with the mixture calculated from the same run's components within 0.005 people per cell, allowing for raster compression. Land-use rasters must use the same grid and valid classes. Numerical consistency does not replace validation against external observations.
