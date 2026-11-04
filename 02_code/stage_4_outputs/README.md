# Stage 4: Outputs

Run Stage 3 successfully in the same output directory before:

```console
python 03_run/run_city_demo.py run --stage 4
```

## Programs

Program 01 checks inputs before computation. Programs 02 and 03 generate hourly population and functional land use. Output checks run before programs 06 and 07 draw the example figures. Program 05 is an optional comparison tool; program 08 redraws independent global context maps.

- [01_verify_inputs.py](01_verify_inputs.py)
- [02_generate_hourly_population.py](02_generate_hourly_population.py)
- [03_classify_functional_land_use.py](03_classify_functional_land_use.py)
- [04_verify_outputs.py](04_verify_outputs.py)
- [05_compare_results.py](05_compare_results.py)
- [06_visualize_hourly_population.py](06_visualize_hourly_population.py)
- [07_visualize_time_use.py](07_visualize_time_use.py)
- [08_visualize_w_indoor.py](08_visualize_w_indoor.py)

Results are written inside `04_intermediate/demo/reproduction/`, or the directory selected with `--out`. Use the same directory for all stages. Missing or failed upstream stages stop execution. See the [run guide](../../03_run/README.md) and [method guide](../../06_docs/methods/stage_4_outputs.md).

## Redraw figures

The stage runner writes population and time-use PNGs to the run's `figures/` directory, PDF exports to `figure_exports/`, and metadata to `figure_data/`. Documentation copies remain in `06_docs/figures/`.

The independent global maps use archived data in `04_intermediate/figure_data/w_indoor/`:

```console
python 02_code/stage_4_outputs/08_visualize_w_indoor.py
```

This optional command requires Cartopy and writes PNGs to `06_docs/figures/` and PDFs to `05_outputs/figure_exports/`.
