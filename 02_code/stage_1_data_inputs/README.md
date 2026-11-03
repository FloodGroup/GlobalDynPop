# Stage 1 code: Source preparation

Stage 1 selects city source records and native raster windows and verifies the resulting files. It preserves source attributes and geometries. Classification, resampling, floor-area calculation and graph construction are performed in Stage 2. The [Stage 1 method](../../06_docs/methods/stage_1_data_inputs.md) defines the extraction domain and provenance rules.

| File | Function |
|---|---|
| [01_prepare_raw_sources.py](01_prepare_raw_sources.py) | Command-line entry point for city-source extraction. |
| [source_preparation.py](source_preparation.py) | Select urban centres by ID, define extraction bounds, preserve whole vector records, crop native raster windows and write provenance manifests. |
| [ghsl_sources.py](ghsl_sources.py) | Locate, download and cache the native GHSL tiles needed for extraction. |
| [02_verify_raw_sources.py](02_verify_raw_sources.py) | Check each manifest-listed source file against its SHA-256 fingerprint. |
| [configuration.py](configuration.py) | Shared paths and model settings used across the four stages. |

## Extract city subsets

Run from the repository root in the full environment:

```console
python 02_code/stage_1_data_inputs/01_prepare_raw_sources.py --urban-centres /data/GHS_UCDB_GLOBE_R2024A.gpkg --city-ids 572 1027 5685 --overture-index /data/overture_rowgroup_index_2026-10-21.0.parquet --places-index /data/places_rowgroup_index_2026-10-21.0.parquet --building-index /data/obm_rowgroup_index.parquet --raster-cache /data/ghsl_tiles --output 01_inputs/extracted/raw
```

The paths in this command identify external source files. The three IDs select Helsinki, Kitakyushu and Takasaki-Maebashi. The urban-centre file must contain the original `GHSL_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A` layer. Selected cities must meet the study threshold of 300,000 residents in 2025.

Each row-group index is a Parquet table with `path`, `rg`, `xmin`, `xmax`, `ymin` and `ymax`; the Overture spatial index also has `layer` values `building`, `segment`, `infrastructure`, `land_use` and `water`. The Places index may use a single `place` layer; the OpenBuildingMap index may use a single `building` layer. Bounds are WGS84 degrees, `rg` is a zero-based Parquet row-group number, and `path` identifies a local source Parquet file or an anonymous public S3 object. Indexes must match the source release. They are source-access metadata. Add `--build-missing-indexes` to generate absent indexes from the public source Parquet footers; this can require many metadata requests. Existing indexes are reused.

Missing GHSL tiles are downloaded to `--raster-cache`. `--offline` requires cached tiles; a fully offline extraction also requires local Parquet paths in every index. The output directory must lie inside the repository root because manifest paths are repository-relative. An occupied output directory requires `--overwrite`. Extraction writes city subdirectories, per-file `.source.json` records and the three source manifests; it does not write Stage 2 model layers.

On Windows, [prepare_sources.cmd](../../03_run/stage_1_data_inputs/prepare_sources.cmd) accepts the same arguments. For a different raw-data directory, set `DYNAMIC_POPULATION_RAW_INPUTS` to that directory before verification and Stage 2 processing.

## Verify supplied or newly extracted subsets

```console
python 03_run/run_city_demo.py run --stage 1
```

The bundled three-city run starts with the existing raw subsets and therefore executes verification only. It reads `source_manifest.json`, `raster_manifest.json` and `open_building_map_manifest.json` under `DYNAMIC_POPULATION_RAW_INPUTS` (default `01_inputs/demo/raw/`); together the supplied manifests list 36 files. Data paths inside them are resolved relative to `DYNAMIC_POPULATION_ROOT`. A missing file or fingerprint mismatch stops execution. A successful check establishes file integrity; source accuracy, completeness and model agreement require separate assessment.
