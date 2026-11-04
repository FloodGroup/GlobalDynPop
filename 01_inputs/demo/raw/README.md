# Original-source city subsets

These source subsets cover the model domains of Helsinki, Kitakyushu and Takasaki-Maebashi. They precede model classification and grid conversion, and preserve the original source attributes, coordinates or pixel values.

| Subdirectory of each city | Files | Data role |
|---|---|---|
| `buildings/` | `overture_buildings.parquet`, `open_building_map_buildings.parquet`, `globalbuildingatlas_buildings.parquet` | Buildings |
| `places/` | `overture_points_of_interest.parquet` | Places |
| `urban_centres/` | `urban_centre_boundary.gpkg` | Urban centres |
| `population/` | `ghsl_resident_population_2025_*.tif`, `ghsl_total_building_volume_2025_*.tif`, `ghsl_non_residential_building_volume_2025_*.tif`, `ghsl_building_height_2018_*.tif` | Population and built-environment support |
| `road_and_rail/` | `overture_transport_segments.parquet` | Road and rail |
| `land_cover/` | ESA WorldCover 2021 v200 (`ESA_WorldCover_*.tif`) and JRC GSW v1.4 transitions (`JRC_transitions_*.tif`) GeoTIFF windows | Native land-cover and water source pixels |
| `time_use/` | Public survey tables, World Bank observations and HAPEM-MS3 report; Finland also has a labelled published-table transcription | Public source evidence for adopted parameters |
| `supporting_land_features/` | `overture_infrastructure_features.parquet`, `overture_land_use_polygons.parquet`, `overture_water_polygons.parquet` | Building/transport support and the functional land-use extension |

Transport records retain all source subtypes; model preprocessing selects road/rail features. Infrastructure records retain the full selected source features before station/category filtering.

Vector subsets select complete source features whose original bounding boxes overlap the model-domain bounding box. Geometries are not cut at the boundary. The 12 GHSL rasters are native-grid integer-window crops: CRS, grid alignment and pixel values match the source tiles. The corresponding prepared population arrays are separately resampled onto the local model grids.

The three-city subsets contain 57 data files. [Stage 1 preparation](../../../02_code/stage_1_data_inputs/README.md#extract-city-subsets) generates city subsets from external sources; the default example verifies the supplied files. Per-file `.source.json` records identify source Parquet row groups or raster windows. Source metadata retain the provider's source-layer names and URLs, even where the local filename is more descriptive.

## GlobalBuildingAtlas building records

Each city's `buildings/globalbuildingatlas_buildings.parquet` contains complete records from the GlobalBuildingAtlas LoD1 Parquet distribution on Source Cooperative. The original `source`, `id`, `height`, `var`, `region`, `bbox` and WKB `geometry` fields are preserved. Geometry coordinates remain WGS84; height is in metres. The provider's missing-height values remain unchanged. No clipping, deduplication, reprojection or height imputation is applied.

The selection retains source records whose bounding boxes overlap the WGS84 bounds of the full model grid, including its 10 km peripheral margin. The GeoParquet metadata retain the provider CRS and geometry definition; the full-tile bounding-box metadata are omitted because these files are city subsets. Per-file `.source.json` records identify the source tiles, row groups, ETags, extraction bounds, row counts and SHA-256. The raw-source verification command reads these per-file records directly.

| City | Building records |
|---|---:|
| 01027_JPN_Kitakyushu | 431,435 |
| 00572_FIN_Helsinki | 274,831 |
| 05685_JPN_Takasaki_Maebashi | 841,012 |

Rebuild the five GBA grid arrays locally, with no downloads:

```console
python 02_code/stage_2_100m_layers/09_prepare_global_building_atlas.py --local-raw --verify-reference --output-dir 04_intermediate/demo/reproduction/gba_from_raw
```

Run from the repository root. This writes to `04_intermediate/demo/reproduction/gba_from_raw/` and checks all cells against `04_intermediate/demo/stage_2/buildings/gba/`. `--output-dir` chooses a different result directory. Building-use fusion and typed open space are subsequent calculations in program 10.

## Coverage limits

Stage 1 defines city grids from the urban-centre boundaries. Stage 2 programs 01 through 04 read the grid definitions and local subsets to generate population/building layers, Overture place counts, classified floor area, routing graphs and water coverage. The OpenBuildingMap records supply building occupancy and height/storey codes when matched to Overture footprints. Step 11 saves smoothed places and effective kernels.

The original OpenStreetMap POI planet extract and survey microdata are not included. Supplementary processed OpenStreetMap counts, hourly activity shares and calibrated parameters remain under `../../../04_intermediate/demo/stage_2/`. The three example cities use Overture places under the automatic coverage rule, so their spatial rebuild does not require the OpenStreetMap planet extract. Survey harmonisation, recalibration and observation validation require their external records.

The original spatial inputs needed by all three city examples are bundled: urban boundaries, GHSL, Overture buildings/places/transport/base features, OpenBuildingMap, GlobalBuildingAtlas, WorldCover and JRC GSW. Overture water polygons provide the OSM-derived water evidence used by the model; a separate OSM planet download is not required for these examples. The OpenBuildingMap subset includes the additional 0.003-degree reading margin of the building matcher.

The six land-cover GeoTIFFs are native integer-window subsets with original CRS, pixel spacing and pixel values. No 20 m or 100 m resampling has been applied to these raw files. Per-file provenance records retain source URLs, windows and source transforms. Stage 2 program 05 performs the resampling and consensus calculation. Programs 05, 06 and 07 accept `--local-raw`.

Run the complete offline spatial reconstruction from the repository root:

```console
python 02_code/stage_1_data_inputs/02_verify_raw_sources.py
python 03_run/run_raw_reconstruction.py
```

Results are written to `04_intermediate/demo/reproduction/from_raw/`, with step logs and a per-array `verification.json`. The command reports exact and differing comparisons separately; successful calculation does not assert equality to archived reference arrays. Add `--require-exact` to return a nonzero exit status if any comparison differs. An empty output directory is required for a new run; `--compare-only` compares an existing run.

The public `time_use/` source files are not a complete archive of survey microdata, cross-country harmonisation inputs or calibration observations. Hourly location shares, W_indoor and fitted kernel settings remain adopted study parameters in this spatial reconstruction. See [input coverage](source_coverage.csv) for the role and availability of each source family.

ESA WorldCover: [2021 v200](https://esa-worldcover.org/en/data-access), CC BY 4.0, © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data 2021 processed by ESA WorldCover consortium. JRC Global Surface Water: [v1.4 transitions, 1984–2021](https://global-surface-water.appspot.com/download), Source: EC JRC/Google; Pekel et al. (2016), doi:10.1038/nature20584. Versions match the model source definitions.

## Attribution

GlobalBuildingAtlas: Zhu, Chen, Zhang, Shi and Wang (2025), [original dataset](https://doi.org/10.14459/2025mp1782307), CC BY-NC 4.0; [Source Cooperative Parquet distribution](https://source.coop/tge-labs/globalbuildingatlas-lod1). Retain the attribution and applicable source-polygon database terms; see [data licence](../../../LICENSE_DATA.md).

GHSL: European Commission, Joint Research Centre, CC BY 4.0; [terms and citation requirements](https://human-settlement.emergency.copernicus.eu/GHSLhowToCite.php).

Overture Maps Foundation, release 2026-10-21.0; © OpenStreetMap contributors and the source providers identified in the original records. Buildings, transportation, infrastructure and land use retain ODbL 1.0 terms. Places retain their source-specific terms. See [Overture attribution](https://docs.overturemaps.org/attribution/) and [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

OpenBuildingMap: Oostwegel, Schorlemmer, Lingner and Evaz Zadeh (2025), GFZ Data Services, [doi:10.5880/GFZ.LKUT.2025.002](https://doi.org/10.5880/GFZ.LKUT.2025.002), ODbL 1.0; distribution mirror at Source Cooperative. See the [provider](https://www.openbuildingmap.org/).

The extraction changes the spatial extent and file container, while preserving original records or pixel values. Source-specific notices remain applicable. Further product citations are in the [three-city guide](../../../06_docs/reproduction/city_demo.md).
