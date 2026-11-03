# Run Stage 3: Allocation of daily activities

Run from the repository root in the environment defined by [environment.yml](../../environment.yml).

Required inputs: Completed Stage 2 spatial layers, routing graphs, hourly location shares and allocation settings.

```console
python 03_run/run_city_demo.py run --stage 3
```

On Windows, use [03_RUN.cmd](../../03_run/stage_3_activity_allocation/03_RUN.cmd). The runner executes the stage's numbered programs in order. Required earlier-stage products must already exist.

Default output directories: `04_intermediate/demo/stage_3/` and `05_outputs/demo/population_components/`.
