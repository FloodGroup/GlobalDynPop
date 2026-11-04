# Stage 4: Outputs

## Processing sequence and hourly calculation

Stage 3 writes the component GeoTIFFs before Stage 4 runs. Stage 4 reads those files and the Stage 2 shares. For local hour `h` and day type `tau`:

```text
P(x,h,tau) = s_C1(h,tau) N(x)
           + sum_{c in C2,C3,C4,C5,C7} s_c(h,tau) D_c(x,tau)
           + s_C6(h,tau) T(x,tau)
```

The seven shares sum to one. Each component has the domain population total, so the hourly mixture conserves that total apart from raster encoding and floating-point effects. Components use bounded-error compression; hourly float32 files use lossless DEFLATE without additional decimal rounding. A file named `hour_03` contains 03:00-04:00 local time in its single band. Three cities, two day types and 24 hours produce 144 hourly files.

| Program | Action and dependencies |
|---|---|
| [02_generate_hourly_population.py](../../02_code/stage_4_outputs/02_generate_hourly_population.py) | `render` reads component bands and combines them with `time_use.daytype_shares`; `write_index` records the hourly files. |
| [03_classify_functional_land_use.py](../../02_code/stage_4_outputs/03_classify_functional_land_use.py) | `load_inputs` reads Stage 2 layers; `layers` applies the functional classification; `write` saves the 7-class raster and 34-band attributes. |
| [01_verify_inputs.py](../../02_code/stage_4_outputs/01_verify_inputs.py) | Inspect prepared input availability and structure; an auxiliary check. |
| [04_verify_outputs.py](../../02_code/stage_4_outputs/04_verify_outputs.py) | Inspect numerical output structure, values and totals; an auxiliary check. |
| [05_compare_results.py](../../02_code/stage_4_outputs/05_compare_results.py) | Compare network arrays, population components or hourly rasters from two supplied result directories. |
| [06_visualize_hourly_population.py](../../02_code/stage_4_outputs/06_visualize_hourly_population.py) | Plot nighttime population and signed hourly/day-type contrasts using shared colour scales. |
| [07_visualize_time_use.py](../../02_code/stage_4_outputs/07_visualize_time_use.py) | Read FIN/JPN hourly shares through the model reader; draw workday/rest-day stacked profiles. |

The [demo runner](../../03_run/run_city_demo.py) runs program 01 before computation, programs 02–03 for hourly and land-use outputs, numerical checks and program 04 for output integrity, then programs 06–07 for figures. It reads the same run's Stage 1 grids, Stage 2 layers and Stage 3 components. Program 05 is an optional comparison tool and program 08 draws independent global maps. Runner figures are written to the run directory; direct plotting commands default to `06_docs/figures/`.

## Time-use figure

The four panels show Finland and Japan for workdays and rest days. Stacked colours show the seven location shares, which sum to one at each hour. Steps represent hourly values without temporal interpolation. The figure reads the same normalised CSV data as the model; it does not estimate new weights. The two Japanese cities share a national profile, so their curves are shown once. PNG files are saved with source hashes and normalisation checks.

## Saved products

Numerical products are under `05_outputs/demo/`; documentation figures are under `06_docs/figures/`.

| Product | Files |
|---|---|
| Components N, D_c, T | `population_components/<city>.tif` and `.json` |
| Hourly population P | `hourly_population/<city>/<daytype>/<city>_<daytype>_hour_<HH>.tif`, one band per file; 24 files per day type |
| Functional land use | `functional_land_use/<city>/`: 7-class raster and 34-band attributes |
| Population maps | `06_docs/figures/`: PNG comparison at three selected hours |

[02_generate_hourly_population.py](../../02_code/stage_4_outputs/02_generate_hourly_population.py) reads the components and Stage 2 hourly location shares, then combines them into population per local hour. [03_classify_functional_land_use.py](../../02_code/stage_4_outputs/03_classify_functional_land_use.py) derives functional land use from Stage 2 floor area, building volume, transport and water coverage. Functional land use is an additional exposure-analysis output, not an input to the population gravity model.

[01_verify_inputs.py](../../02_code/stage_4_outputs/01_verify_inputs.py), [04_verify_outputs.py](../../02_code/stage_4_outputs/04_verify_outputs.py) and [05_compare_results.py](../../02_code/stage_4_outputs/05_compare_results.py) provide integrity and comparison tools. The example checks every hourly raster against the mixture derived from the same run's components, and validates population conservation and grid consistency. This is numerical reproduction; observation-based validation requires the external observations.

## Functional land use

Functional land use uses seven classes: 1 residential; 2 commercial and industrial; 3 education; 4 leisure, culture and sport; 5 other built-up land (including major roads and railways); 6 permanent water; 7 open land. GBA capacity and volume, multi-source permanent water and land-use evidence supply the classification inputs. The final seven-class output is distinct from the seven activity-location classes C1-C7.


Functional land-use thresholds are study-defined: built floor area 500 m2 or built volume 1,500 m3; corridor floor area below 1,000 m2; road/rail length at least 100 m; water coverage at least 50%. The exact rules and band descriptions are in [03_classify_functional_land_use.py](../../02_code/stage_4_outputs/03_classify_functional_land_use.py), and the parameter values are listed below.

The model rerun checks numerical reproduction. External observations are required for observation-based validation.

## Implementation modules

[population_fields.py](../../02_code/stage_4_outputs/population_fields.py) reads or computes population fields for selected hours and supports result evaluation. The output programs call Stage 2's grid/share readers and Stage 3's model and routing functions where required. Runtime scheduling is provided by `03_run/`.

## Population maps

[06_visualize_hourly_population.py](../../02_code/stage_4_outputs/06_visualize_hourly_population.py) reads the final single-band GeoTIFFs at 03:00, 08:00 and 13:00 on workdays and at 03:00 and 13:00 on rest days. Each hour denotes the following local one-hour interval. The 11 × 7.6-inch figure has one row per city and five columns:

1. Workday population at 03:00 (nighttime reference).
2. Workday 08:00 minus workday 03:00.
3. Workday 13:00 minus workday 03:00.
4. Rest-day 13:00 minus rest-day 03:00.
5. Workday 13:00 minus rest-day 13:00.

Differences are computed by subtracting the original rasters after conversion to float64, with matching grid dimensions, projection and affine transform required. Values remain people per 100 m cell, not percentages. Positive values are orange and negative values blue. All difference maps share a symmetric logarithmic scale from −100 to +100, with a linear interval from −2 to +2 (base 10, linear-scale parameter 1). Values outside the limits use endpoint colours and colour-bar extensions indicate this saturation. Zero differences are transparent; no nonzero differences are excluded by a display threshold. This scale makes both small and large changes visible without altering the raster values.

Nighttime reference maps use a separate logarithmic scale from 3 to 200 people per cell, shared across cities. Values below 3 are transparent and those above 200 use the upper endpoint colour. Water coverage of at least 50% is drawn as a pale background. The full model domains are retained at native grid spacing, without spatial smoothing or spatial aggregation. Rest days are typical day-type profiles, not specific public holidays.

Stage 4 regenerates the figure from its newly calculated hourly outputs in the run directory. When the plotting program is called directly with its default output directory, the PNG is written to `06_docs/figures/demo_population_distributions.png` at 360 dpi and a PDF to `05_outputs/figure_exports/`. English labels use DejaVu Sans, with a 24-point title and 12.5-point subtitle consistent with the global maps. The hourly-share figure retains its 11 × 6.6-inch canvas and typography. Source hashes, subtraction definitions, scale settings and numerical contrast summaries are recorded in `04_intermediate/figure_data/population_visualization_metadata.json`.

Figure execution commands and output-directory options are in the [Stage 4 run instructions](../../02_code/stage_4_outputs/README.md#redraw-figures).

## Parameter values and sources

The following classification thresholds are study-defined settings.

### Functional land-use thresholds

Implementation: [03_classify_functional_land_use.py](../../02_code/stage_4_outputs/03_classify_functional_land_use.py). Keys below identify individual settings.

| Setting | Value | Unit | Source or basis |
|---|---:|---|---|
| `land_use.BUILT_FLOOR_M2` | 500.0 | m2 | Study-defined |
| `land_use.BUILT_VOLUME_M3` | 1500.0 | m3 | Study-defined |
| `land_use.CORRIDOR_FLOOR_M2` | 1000.0 | m2 | Study-defined |
| `land_use.CORRIDOR_LEN_M` | 100.0 | m | Study-defined |
| `land_use.WATER_SHARE` | 0.5 | fraction | Study-defined |

[Return to project README](../../README.md)
