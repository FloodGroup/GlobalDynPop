# Run Stage 2: 100 m layers

Run from the repository root in the environment defined by [environment.yml](../../environment.yml).

Required inputs: Stage 1 raw source subsets and manifests, plus the supplied hourly location shares and allocation settings.

```console
python 03_run/run_city_demo.py run --stage 2
```

On Windows, use [02_RUN.cmd](../../03_run/stage_2_100m_layers/02_RUN.cmd). The runner executes the stage's numbered programs in order. Required earlier-stage products must already exist.

Default output directories: `04_intermediate/demo/stage_2/`.

To inspect an individual program's options, for example:

```console
python 02_code/stage_2_100m_layers/04_prepare_building_floor_area.py --help
```
