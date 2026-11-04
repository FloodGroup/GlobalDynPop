# Stage 1: City grids and data inputs

Stage 1 defines the city projection, extent and 100 m grid, then prepares or verifies original-source subsets. Stage 2 converts those sources into quantities on this fixed grid. See the [method guide](../../06_docs/methods/stage_1_data_inputs.md) and [run guide](../../03_run/README.md).

## Define grids from the bundled boundaries

```console
python 02_code/stage_1_data_inputs/00_create_city_grids.py
python 02_code/stage_1_data_inputs/02_verify_raw_sources.py
```

The combined example command is `python 03_run/run_city_demo.py run --stage 1`. It regenerates the city table from local urban-centre boundaries and verifies the raw subsets; it does not require Stage 2 or Stage 3 results. `check --stage 1` verifies raw subsets and the grid table after Stage 1 has completed in the selected run directory.

The grid table is [city_grid_definitions.csv](../../04_intermediate/demo/stage_1/local_grids/city_grid_definitions.csv). Set `DYNAMIC_POPULATION_STAGE1` to change its parent stage directory, or use `--output` to write a table elsewhere. Use `--stems` or `--stems-file` to select local city subsets; use `--raw` or `DYNAMIC_POPULATION_RAW_INPUTS` for a different raw directory.

## Define grids before extracting new cities

```console
python 02_code/stage_1_data_inputs/00_create_city_grids.py --urban-centres /data/GHS_UCDB_GLOBE_R2024A.gpkg --city-ids 572 1027 5685
```

The source extraction entry point also writes the same grid definitions before extracting the selected cities. Its provider files and indexes are described in the [source-index method](../../06_docs/methods/stage_1_data_inputs.md#source-index-structure). Run `01_prepare_raw_sources.py --help` for extraction options. WorldCover and JRC preparation reads the Stage 1 table.

## Programs

- [00_create_city_grids.py](00_create_city_grids.py): define city domains and write the grid table from original or locally bundled boundaries.
- [01_prepare_raw_sources.py](01_prepare_raw_sources.py): define selected city grids and extract GHSL, Overture and OpenBuildingMap subsets.
- [02_verify_raw_sources.py](02_verify_raw_sources.py): check supplied subsets using per-file source records.
- [03_prepare_land_cover_sources.py](03_prepare_land_cover_sources.py): acquire native WorldCover and JRC raster windows for the defined domains.

The [raw-data guide](../../01_inputs/demo/raw/README.md) describes the bundled GlobalBuildingAtlas and other source records. `python 03_run/run_raw_reconstruction.py` rebuilds Stage 1 grids followed by Stage 2 spatial layers in a separate output directory and compares them with the supplied references.
