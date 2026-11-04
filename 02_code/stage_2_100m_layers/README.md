# Stage 2: 100 m layers

Stage 2 rebuilds the spatial inputs from the raw city subsets on the grids created by Stage 1. Run Stage 1 first, then:

```console
python 03_run/run_city_demo.py run --stage 2
```

## Programs

Execute in numerical order. The three example cities do not require the China-only program 08.

- [01_prepare_settlement_layers.py](01_prepare_settlement_layers.py)
- [02_prepare_destination_counts.py](02_prepare_destination_counts.py)
- [03_prepare_building_floor_area.py](03_prepare_building_floor_area.py)
- [04_prepare_transport_graphs.py](04_prepare_transport_graphs.py)
- [05_prepare_permanent_water.py](05_prepare_permanent_water.py)
- [06_prepare_outdoor_recreation.py](06_prepare_outdoor_recreation.py)
- [07_prepare_land_use.py](07_prepare_land_use.py)
- [08_prepare_china_land_use.py](08_prepare_china_land_use.py)
- [09_prepare_global_building_atlas.py](09_prepare_global_building_atlas.py)
- [10_prepare_buildings_open_space.py](10_prepare_buildings_open_space.py)
- [11_save_model_layers.py](11_save_model_layers.py)

Results are written inside `04_intermediate/demo/reproduction/`, or the directory selected with `--out`. Use the same directory for all stages. Missing or failed upstream stages stop execution. See the [run guide](../../03_run/README.md) and [method guide](../../06_docs/methods/stage_2_100m_layers.md).

Programs 03 and 10 write different products: classified source capacity in `buildings/floor_area_legacy/`, followed by fused capacity in `buildings/floor_area_by_use/`. Program 11 exports smoothed POIs and effective kernels only after permanent water, GBA and open space are available. Program 05 also writes the final water-coverage layer used by Stage 4.
