# Run the model

Run commands from the repository root after installing [environment.yml](../environment.yml).

```console
python 03_run/run_city_demo.py run
```

| Stage | Run instructions |
|---|---|
| 1. Data inputs | [Extract sources or verify supplied files](stage_1_data_inputs/) |
| 2. 100 m layers | [Run Stage 2](stage_2_100m_layers/) |
| 3. Allocation of daily activities | [Run Stage 3](stage_3_activity_allocation/) |
| 4. Outputs | [Run Stage 4](stage_4_outputs/) |

To check the bundled processed inputs and numerical outputs:

```console
python 03_run/run_city_demo.py check
```

The [run guide](../03_run/README.md) documents environment variables and runtime settings.
