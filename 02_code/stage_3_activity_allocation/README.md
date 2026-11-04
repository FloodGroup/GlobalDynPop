# Stage 3: Allocation of daily activities

Run Stage 2 successfully in the same output directory before:

```console
python 03_run/run_city_demo.py run --stage 3
```

## Programs

Execute 01 → 02 → 03. Program 01 exports attractiveness. Program 02 computes trips and assigns them to the freshly prepared road/rail graph. Program 03 allocates destination populations and combines residents, destinations and the newly calculated transit fields into component files. Programs 02 and 03 evaluate attractiveness with the same model functions and settings used by program 01; they do not depend on the exported attractiveness file as a cache.

- [01_calculate_destination_attractiveness.py](01_calculate_destination_attractiveness.py)
- [02_calculate_in_transit_population.py](02_calculate_in_transit_population.py)
- [03_calculate_population_components.py](03_calculate_population_components.py)

Results are written inside `04_intermediate/demo/reproduction/`, or the directory selected with `--out`. Use the same directory for all stages. Missing or failed upstream stages stop execution. See the [run guide](../../03_run/README.md) and [method guide](../../06_docs/methods/stage_3_activity_allocation.md).
