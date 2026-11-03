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
| [01_generate_hourly_population.py](../../02_code/stage_4_outputs/01_generate_hourly_population.py) | `render` reads component bands and combines them with `time_use.daytype_shares`; `write_index` records the hourly files. |
| [02_classify_functional_land_use.py](../../02_code/stage_4_outputs/02_classify_functional_land_use.py) | `load_inputs` reads Stage 2 layers; `layers` applies the functional classification; `write` saves the 13-class raster and 16-band attributes. |
| [03_verify_inputs.py](../../02_code/stage_4_outputs/03_verify_inputs.py) | Inspect prepared input availability and structure; an auxiliary check. |
| [04_verify_outputs.py](../../02_code/stage_4_outputs/04_verify_outputs.py) | Inspect numerical output structure, values and totals; an auxiliary check. |
| [05_compare_results.py](../../02_code/stage_4_outputs/05_compare_results.py) | Compare network arrays, population components or hourly rasters from two supplied result directories. |
| [06_visualize_hourly_population.py](../../02_code/stage_4_outputs/06_visualize_hourly_population.py) | Plot selected single-band hourly rasters using the existing city-specific continuous colour scales. |
| [07_visualize_time_use.py](../../02_code/stage_4_outputs/07_visualize_time_use.py) | Read FIN/JPN hourly shares through the model reader; draw workday/rest-day stacked profiles. |

The [demo runner](../../03_run/run_city_demo.py) runs output programs 01, 02, 06 and 07, then verifies stored numerical fingerprints. Programs 03-05 are optional inspection tools, not extra model stages. Figures default to `06_docs/figures/`; changing the figure output directory does not change the numerical rasters.

## Time-use figure

The four panels show Finland and Japan for workdays and rest days. Stacked colours show the seven location shares, which sum to one at each hour. Steps represent hourly values without temporal interpolation. The figure reads the same normalised CSV data as the model; it does not estimate new weights. The two Japanese cities share a national profile, so their curves are shown once. PNG files are saved with source hashes and normalisation checks.

## Saved products

Numerical products are under `05_outputs/demo/`; documentation figures are under `06_docs/figures/`.

| Product | Files |
|---|---|
| Components N, D_c, T | `population_components/<city>.tif` and `.json` |
| Hourly population P | `hourly_population/<city>/<daytype>/<city>_<daytype>_hour_<HH>.tif`, one band per file; 24 files per day type |
| Functional land use | `functional_land_use/<city>/`: 13-class raster and 16-band attributes |
| Population maps | `06_docs/figures/`: PNG comparison at three selected hours |

[01_generate_hourly_population.py](../../02_code/stage_4_outputs/01_generate_hourly_population.py) reads the components and Stage 2 hourly location shares, then combines them into population per local hour. [02_classify_functional_land_use.py](../../02_code/stage_4_outputs/02_classify_functional_land_use.py) derives functional land use from Stage 2 floor area, building volume, transport and water coverage. Functional land use is an additional exposure-analysis output, not an input to the population gravity model.

[03_verify_inputs.py](../../02_code/stage_4_outputs/03_verify_inputs.py), [04_verify_outputs.py](../../02_code/stage_4_outputs/04_verify_outputs.py) and [05_compare_results.py](../../02_code/stage_4_outputs/05_compare_results.py) provide integrity and comparison tools. The example checks decoded numerical arrays against stored fingerprints. This is numerical reproduction; observation-based validation requires the external observations.

## Functional land use

Functional land-use thresholds are study-defined: built floor area 500 m2 or built volume 1,500 m3; corridor floor area below 1,000 m2; road/rail length at least 100 m; water coverage at least 50%. The exact rules and band descriptions are in [02_classify_functional_land_use.py](../../02_code/stage_4_outputs/02_classify_functional_land_use.py), and the parameter values are listed below.

The model rerun checks numerical reproduction. External observations are required for observation-based validation.

## Implementation modules

[population_fields.py](../../02_code/stage_4_outputs/population_fields.py) reads or computes population fields for selected hours and supports result evaluation. The output programs call Stage 2's grid/share readers and Stage 3's model and routing functions where required. Runtime scheduling is provided by `03_run/`.

## Population maps

[06_visualize_hourly_population.py](../../02_code/stage_4_outputs/06_visualize_hourly_population.py) reads the final single-band GeoTIFFs at 03:00-04:00, 08:00-09:00 and 13:00-14:00 local time. It produces one PNG with A3 landscape proportions: cities in rows, with three workday maps and three rest-day maps per city. Each city has a separate continuous logarithmic colour scale. The lower limit is 3 people per cell. The upper limit is the 99.5th percentile of cells with at least 3 people, pooled across that city's six displayed maps and rounded up to the next 10 people. The palette progresses through pale lavender and purple, with red and orange concentrated at the high end. Values above the upper limit use the upper colour, indicated by the colour-bar extension. The same limits apply to both day types and all three hours within a city. Counts across cities must be read from their respective colour bars. Cells below 3 people are transparent; water coverage of at least 50% is a pale background. Full model domains are shown without additional spatial smoothing.

Stage 4 updates this figure after generating the numerical outputs.

The output is a 360 dpi PNG named `demo_population_distributions.png`. Labels use English and Times New Roman where installed. `population_visualization_metadata.json` records source hashes and the city-specific continuous scale limits.

Figure execution commands and output-directory options are in the [Stage 4 run instructions](../../02_code/stage_4_outputs/README.md#redraw-figures).

## Parameter values and sources

The following classification thresholds are study-defined settings.

### Functional land-use thresholds

Implementation: [02_classify_functional_land_use.py](../../02_code/stage_4_outputs/02_classify_functional_land_use.py). Keys below identify individual settings.

| Setting | Value | Unit | Source or basis |
|---|---:|---|---|
| `land_use.BUILT_FLOOR_M2` | 500.0 | m2 | Study-defined |
| `land_use.BUILT_VOLUME_M3` | 1500.0 | m3 | Study-defined |
| `land_use.CORRIDOR_FLOOR_M2` | 1000.0 | m2 | Study-defined |
| `land_use.CORRIDOR_LEN_M` | 100.0 | m | Study-defined |
| `land_use.WATER_SHARE` | 0.5 | fraction | Study-defined |

[Return to project README](../../README.md)
