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

The supplied example begins after spatial extraction. Its Stage 1 executable verifies the raw files; it does not download or extract the source datasets. The [Stage 1 code guide](../../02_code/stage_1_data_inputs/README.md) lists the executable, shared modules, calling sequence and verification behaviour. The [raw-data dictionary](../../01_inputs/demo/raw/README.md) lists file contents and source coverage.
