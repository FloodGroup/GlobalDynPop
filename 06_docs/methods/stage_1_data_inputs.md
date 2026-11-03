# Stage 1 method: Data inputs

Stage 1 establishes the source data for each city domain. Spatial subsets retain the information needed to derive resident population, building floor area, POI density and transport networks. Conversion to the common 100 m grid takes place in [Stage 2](stage_2_100m_layers.md).

## Study cities and spatial coverage

The study covers 1,904 urban centres in 152 countries, selected from GHS-UCDB R2024A with at least 300,000 residents in 2025. Each model domain uses the urban-centre bounding box in a local Lambert azimuthal equal-area projection, extended by 10 km on every side. This includes surrounding residents, destinations and transport links in the calculation.

Helsinki, Kitakyushu and Takasaki-Maebashi provide the worked processing examples. Their supplied raw subsets cover these model domains. The [principal data sources](../../README.md#principal-data-sources) describe the datasets used across the study.

## Source information retained

| Source information | Content retained before model processing | Use in Stage 2 |
|---|---|---|
| Urban-centre boundaries | Geometry, city identifiers and source attributes | Define the local grid and city domain. |
| Resident population | Native GHS-POP pixel counts and georeferencing | Resample population onto the model grid while conserving population. |
| Buildings and building height | Overture footprints and use/height/floor attributes; OpenBuildingMap occupancy and height/storey codes; GHSL height and total/non-residential volume rasters | Classify building use and estimate floor area from footprint area and storeys. |
| POIs | Locations, activity categories and source attributes | Classify destinations and calculate POI counts and density. |
| Land use | Polygon geometries with source class and subtype attributes | Supply building-use evidence where building attributes are insufficient. |
| Road, rail and infrastructure | Segment geometries, network attributes and infrastructure features | Construct the transport graph and identify stations. |
| Water | Polygon geometries and source attributes | Calculate water coverage on the local grid. |

Building heights, floor counts and land-use categories remain source observations at this stage. Their interpretation, missing-value rules and aggregation are described in the Stage 2 method.

## Spatial subsetting and provenance

Vector subsets retain complete source features whose bounding boxes overlap the model-domain bounding box. Features are not geometrically cut at its boundary. Their attributes and coordinates are preserved for later classification and projection.

Raster subsets use integer windows on the native source grids. The source coordinate system, pixel alignment and pixel values are preserved; the cropped file records the affine transform of its own window. Resampling to 100 m is a Stage 2 operation.

Source manifests and per-file provenance records identify the source files, selected Parquet row groups or raster windows, and SHA-256 fingerprints. Comparing a supplied file with its recorded fingerprint establishes file integrity. It does not assess source accuracy, spatial completeness or the quality of the resulting population estimates.

## Connection to later stages

Stage 2 reads the raw spatial subsets and derives model layers. It also reads the adopted 24-by-7 hourly location shares and distance-decay settings. These are processed research products: their survey harmonisation and commuting calibration precede the example run. The [time-use guide](../../04_intermediate/demo/stage_2/time_use/time_use.pdf) explains how the shares were constructed.

## Programs and stage boundary

[01_prepare_raw_sources.py](../../02_code/stage_1_data_inputs/01_prepare_raw_sources.py) selects urban-centre records by ID and writes the corresponding city source subsets. It reads Overture and OpenBuildingMap row-group indexes (or builds missing indexes from source metadata when requested), selects intersecting source records, and crops the native GHSL tiles. [02_verify_raw_sources.py](../../02_code/stage_1_data_inputs/02_verify_raw_sources.py) checks the resulting files against their manifests.

The extraction extent uses the same local projection, 10 km margin and 100 m bound alignment as the model grid. Defining these bounds does not resample source data: Stage 2 writes the grid descriptor and converts the source records into model quantities. The common domain calculation is `source_preparation.city_record`, shared by source extraction and Stage 2 grid preparation.

Building footprints, OpenBuildingMap buildings and land-use evidence are selected with an additional 0.003-degree reading margin, matching the floor-area reader. This is a study-defined processing margin, not an additional output-domain extension. Other vector sources use the domain bounds. Selecting a record by its bounding box can retain features that lie outside the exact domain polygon; Stage 2 applies the model grid and source-specific filters.

The bundled three-city run uses the supplied subsets and executes verification only. Repeating extraction requires the source files or access to the recorded release and matching indexes. The [Stage 1 code guide](../../02_code/stage_1_data_inputs/README.md) documents arguments and index schemas. The [raw-data dictionary](../../01_inputs/demo/raw/README.md) lists the delivered files.

| Setting | Value | Basis |
|---|---|---|
| Minimum urban-centre population | 300,000 in 2025 | Study selection threshold. |
| Domain margin | 10 km per side | Study-defined extent, also used in Stage 2. |
| Domain-bound alignment | 100 m | Shared model-grid resolution. |
| Building-source reading margin | 0.003 degrees | Study-defined allowance used by the floor-area reader. |
| Domain boundary densification | 200 points per side | Study-defined numerical approximation for transforming extraction bounds. |

Urban-centre polygon edges are densified to at most 200 m segments before projection, a study-defined numerical setting shared with grid construction.
