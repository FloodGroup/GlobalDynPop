# Stage 1 code: Source verification

The Stage 1 executable checks the supplied raw spatial files before Stage 2 reads them. Source selection and spatial subsetting principles are described in the [Stage 1 method](../../06_docs/methods/stage_1_data_inputs.md).

## Files and responsibilities

| File | Role | Called by |
|---|---|---|
| [01_verify_raw_sources.py](01_verify_raw_sources.py) | Read the three raw manifests, check that every listed file exists, and compare its SHA-256 fingerprint. | The three-city runner or the Stage 1 launcher. |
| [configuration.py](configuration.py) | Define repository paths, environment-variable overrides and shared model settings. It does not prepare data. | Processing modules across Stages 2-4 through imports. |
| [__init__.py](__init__.py) | Add execution-support modules to the import path and provide compatibility for NumPy archives. | Python when the Stage 1 package is imported. |

## Calling sequence

```text
03_run/run_city_demo.py run --stage 1
  -> 02_code/stage_1_data_inputs/01_verify_raw_sources.py
     -> read source_manifest.json
     -> read raster_manifest.json
     -> read open_building_map_manifest.json
     -> check each listed file and its SHA-256 fingerprint
     -> print the verified file count, or stop with an error
```

The verifier uses only the Python standard library. It resolves its paths directly and does not import `configuration.py`. The shared configuration and package initializer support later processing; they are not additional Stage 1 execution steps.

## Inputs and result

The three manifests are read from `01_inputs/demo/raw/` by default. Together they list 36 source data files. Each manifest entry supplies a repository-relative file path and its expected SHA-256 fingerprint.

A successful check prints `{"raw_source_files_verified": 36}`. A missing file or fingerprint mismatch raises `RuntimeError` with the affected path. File size, source attributes and georeferencing are not separately validated by this script. It writes no spatial layers and does not modify the raw data.

`DYNAMIC_POPULATION_ROOT` overrides the repository root. `DYNAMIC_POPULATION_RAW_INPUTS` overrides the manifest directory; data paths recorded inside the manifests are still resolved relative to the repository root.

## Run

From the repository root:

```console
python 03_run/run_city_demo.py run --stage 1
```

To run the verifier directly:

```console
python 02_code/stage_1_data_inputs/01_verify_raw_sources.py
```

The Windows launcher is [03_run/stage_1_data_inputs/01_RUN.cmd](../../03_run/stage_1_data_inputs/01_RUN.cmd). In a full `run`, the runner completes verification before starting Stage 2. Selecting Stage 1 alone stops after verification.
