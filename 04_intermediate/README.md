# Intermediate data

`demo/stage_1/` contains city projection and grid definitions. `demo/stage_2/` contains the processed 100 m model layers and adopted settings. `demo/stage_3/` contains destination attractiveness, destination-population allocations and in-transit population.

The [Stage 1 dictionary](demo/stage_1/README.md), [Stage 2 dictionary](demo/stage_2/README.md) and [Stage 3 dictionary](demo/stage_3/README.md) describe their files and units. Original sources are under `01_inputs/demo/raw/`; final products are under `05_outputs/demo/`.

[Indoor time share (W_indoor): data sources and methods](w_indoor/w_indoor.md) documents W_indoor sources, provincial values, reference assignment and the global indoor-share, income and climate maps.

[Hourly location shares: data sources and methods](time_use/time_use.md) documents survey processing, day-type transfer, corrections, parameter sources and the supplied Finland and Japan profiles.

The `time_use/` and `w_indoor/` subfolders contain the parameter reports; the activity-location heatmap accompanies the time-use report. Other PNG figures are stored in `06_docs/figures/`, with PDF exports in `05_outputs/figure_exports/`.
