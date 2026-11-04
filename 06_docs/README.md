# Documentation

The [main README](../README.md) introduces the study, its data sources and the four-stage workflow.

## Methods

| Guide | Contents |
|---|---|
| [Stage 1: Data inputs](methods/stage_1_data_inputs.md) | Study domains, retained source information, spatial subsetting and provenance. |
| [Stage 2: 100 m layers](methods/stage_2_100m_layers.md) | Grid construction, population, floor area, places, graphs, hourly shares and kernels. |
| [Stage 3: Allocation of daily activities](methods/stage_3_activity_allocation.md) | Attractiveness, gravity allocation, in-transit assignment and component storage. |
| [Stage 4: Outputs](methods/stage_4_outputs.md) | Hourly mixtures, functional land use, numerical checks and figures. |

The method guides follow each processing sequence through its numbered programs and calculation functions. The [code index](../02_code/) opens the implementation directories, whose README files provide commands, prerequisites and runtime options. The [time-use derivation](../04_intermediate/time_use.md) explains the 24-by-7 shares in detail. Model assumptions are described in the stage methods; the [three-city guide](reproduction/city_demo.md) defines the scope of reproduction. Parameter values and sources are included in the corresponding stage methods.

The [indoor-share guide](../04_intermediate/w_indoor.md) documents W_indoor calculation, evidence sources and reference assignment.

## Figures

- [Indoor share](figures/w_indoor_global.png): adopted values for 1,904 cities.
- [Income](figures/gni_global.png): gross national income per capita, Atlas method.
- [Climate](figures/climate_global.png): five main Köppen–Geiger classes.

- [Study area](figures/study_area.png): the 1,904 study cities, time-use sources, kernel groups and population sizes.

- [Workflow](figures/workflow.png): study overview. Routing zones are adaptive; 2 km is their starting size.
- [Population changes](figures/demo_population_distributions.png): nighttime reference maps, changes from night to morning/midday, and midday workday-minus-rest-day differences for the three example cities.
- [Time-use weights](figures/time_use_weights.png): the Finland and Japan workday/rest-day profiles used by the example.

This directory contains PNG images only. Stage 4 regenerates the population and time-use figures. PDF exports of the indoor-share, income and climate maps are stored in `05_outputs/figure_exports/`.

## Reproduction and sources

The [three-city guide](reproduction/city_demo.md) covers running, selection evidence, input coverage and source attribution. The [run guide](../03_run/README.md) covers the tested environment and additional workflows. Runner configuration and numerical checks are stored under `03_run/demo_configuration/`.

## Citation

See the [Citation section](../README.md#citation) in the main README and the [dataset attribution table](reproduction/city_demo.md#data-sources-and-attribution).
