# Run Stage 4: Outputs

Run from the repository root in the environment defined by [environment.yml](../../environment.yml).

Required inputs: Stage 3 population-component GeoTIFFs and the Stage 2 hourly location shares. Functional land use also requires the Stage 2 spatial layers.

```console
python 03_run/run_city_demo.py run --stage 4
```

On Windows, use [04_RUN.cmd](../../03_run/stage_4_outputs/04_RUN.cmd). The runner executes the stage's numbered programs in order. Required earlier-stage products must already exist.

Default output directories: `05_outputs/demo/` and `06_docs/figures/`.

## Redraw figures

```console
python 02_code/stage_4_outputs/06_visualize_hourly_population.py
python 02_code/stage_4_outputs/07_visualize_time_use.py
```

Both programs accept `--out`. For population maps, `--stems` selects one to three cities and `--hourly` and `--stage2` select alternate input directories. The stage runner uses `DYNAMIC_POPULATION_FIGURES` for both figure outputs.

## Check results

```console
python 03_run/run_city_demo.py check
```
