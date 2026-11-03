# Run Stage 1: Data inputs

Run commands from the repository root in the environment defined by [environment.yml](../../environment.yml).

## Verify supplied or newly extracted subsets

```console
python 03_run/run_city_demo.py run --stage 1
```

The supplied three-city example requires no source download. On Windows, use [01_RUN.cmd](../../03_run/stage_1_data_inputs/01_RUN.cmd). For a different raw-data directory, set `DYNAMIC_POPULATION_RAW_INPUTS` before running verification and Stage 2.

## Extract city subsets

Provide the original GHS-UCDB file, matching Overture and OpenBuildingMap row-group indexes, and a directory for native GHSL tiles. The index schema is documented in the [source-index method](../../06_docs/methods/stage_1_data_inputs.md#source-index-structure).

```console
python 02_code/stage_1_data_inputs/01_prepare_raw_sources.py --urban-centres /data/GHS_UCDB_GLOBE_R2024A.gpkg --city-ids 572 1027 5685 --overture-index /data/overture_rowgroup_index_2026-10-21.0.parquet --places-index /data/places_rowgroup_index_2026-10-21.0.parquet --building-index /data/obm_rowgroup_index.parquet --raster-cache /data/ghsl_tiles --output 01_inputs/extracted/raw
```

Replace `/data/` paths with the locations of your source files. The city IDs select Helsinki, Kitakyushu and Takasaki-Maebashi. On Windows, [prepare_sources.cmd](../../03_run/stage_1_data_inputs/prepare_sources.cmd) accepts the same arguments.

Use `--build-missing-indexes` to create absent indexes from the public source metadata. Use `--offline` with cached GHSL tiles and local Parquet paths in the indexes to extract without network access. The output directory must be inside the repository root; an occupied directory requires `--overwrite`. To process the extracted data, set `DYNAMIC_POPULATION_RAW_INPUTS` to the output directory, then run verification and Stage 2.

```console
python 02_code/stage_1_data_inputs/01_prepare_raw_sources.py --help
```
