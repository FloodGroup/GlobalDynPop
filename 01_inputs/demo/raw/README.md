# Original-source city subsets

These source subsets cover the model domains of Helsinki, Kitakyushu and Takasaki-Maebashi. They precede model classification and grid conversion, and preserve the original source attributes, coordinates or pixel values.

| Subdirectory of each city | Files | Data role |
|---|---|---|
| `buildings/` | `overture_buildings.parquet`, `open_building_map_buildings.parquet` | Buildings |
| `places/` | `overture_points_of_interest.parquet` | Places |
| `urban_centres/` | `urban_centre_boundary.gpkg` | Urban centres |
| `population/` | `ghsl_resident_population_2025_*.tif`, `ghsl_total_building_volume_2025_*.tif`, `ghsl_non_residential_building_volume_2025_*.tif`, `ghsl_building_height_2018_*.tif` | Population and built-environment support |
| `road_and_rail/` | `overture_transport_segments.parquet` | Road and rail |
| `supporting_land_features/` | `overture_infrastructure_features.parquet`, `overture_land_use_polygons.parquet`, `overture_water_polygons.parquet` | Building/transport support and the functional land-use extension |

Transport records retain all source subtypes; model preprocessing selects road/rail features. Infrastructure records retain the full selected source features before station/category filtering.

Vector subsets select complete source features whose original bounding boxes overlap the model-domain bounding box. Geometries are not cut at the boundary. The 12 GHSL rasters are native-grid integer-window crops: CRS, grid alignment and pixel values match the source tiles. The corresponding prepared population arrays are separately resampled onto the local model grids.

The 36 data files are listed in the source manifests. [Stage 1 preparation](../../../02_code/stage_1_data_inputs/README.md#extract-city-subsets) generates city subsets from external sources; the default example verifies the supplied files. Per-file `.source.json` records identify source Parquet row groups or raster windows. Manifests and metadata retain the provider's source-layer names and URLs, even where the local filename is more descriptive.

## Coverage limits

Stage 2 programs 01 through 05 read these local subsets to generate city grids, population/building layers, Overture place counts, classified floor area, routing graphs and water coverage. The OpenBuildingMap records supply building occupancy and height/storey codes when matched to Overture footprints. Step 06 saves smoothed places and effective kernels.

The original OpenStreetMap POI planet extract and survey microdata are not included. Supplementary processed OpenStreetMap counts, hourly activity shares and calibrated parameters remain under `../../../04_intermediate/demo/stage_2/`. The three example cities use Overture places under the automatic coverage rule, so their spatial rebuild does not require the OpenStreetMap planet extract. Survey harmonisation, recalibration and observation validation require their external records.

## Attribution

GHSL: European Commission, Joint Research Centre, CC BY 4.0; [terms and citation requirements](https://human-settlement.emergency.copernicus.eu/GHSLhowToCite.php).

Overture Maps Foundation, release 2026-10-21.0; © OpenStreetMap contributors and the source providers identified in the original records. Buildings, transportation, infrastructure and land use retain ODbL 1.0 terms. Places retain their source-specific terms. See [Overture attribution](https://docs.overturemaps.org/attribution/) and [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

OpenBuildingMap: Oostwegel, Schorlemmer, Lingner and Evaz Zadeh (2025), GFZ Data Services, [doi:10.5880/GFZ.LKUT.2025.002](https://doi.org/10.5880/GFZ.LKUT.2025.002), ODbL 1.0; distribution mirror at Source Cooperative. See the [provider](https://www.openbuildingmap.org/).

The extraction changes the spatial extent and file container, while preserving original records or pixel values. Source-specific notices remain applicable. Further product citations are in the [three-city guide](../../../06_docs/reproduction/city_demo.md).
