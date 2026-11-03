# Stage 2: 100 m layers

## Processing sequence and calculations

The six numbered programs execute in the table order below. Steps 01-05 call `local_raw_preparation.run_step`, which dispatches the corresponding grid, settlement, POI, floor-area or transport calculation. Step 06 derives model-ready place layers and records the effective kernels. The products are consumed by Stage 3; hourly shares also feed Stage 4 directly.

1. **Local grid.** Project the urban-centre polygon to a local Lambert azimuthal equal-area CRS. Expand its bounding box by 10 km on every side and snap the bounds to 100 m cells. Store the projection, dimensions, transform and urban-centre geometry.
2. **Settlement layers.** Resample population and total/non-residential building volumes as extensive counts using source-pixel sub-sampling. Sample height using each raster's own CRS and affine transform. A cropped edge tile must retain its actual transform. Save population in people, volume in cubic metres and height in metres.
3. **Places.** Filter and classify Overture records, then count them in the destination classes on the local grid. Step 06 applies the configured Gaussian smoothing (300 m in the supplied settings). The stored OpenStreetMap counts remain supplementary; automatic selection uses Overture for these cities.
4. **Floor area.** Combine footprint geometry with building-use evidence from Overture, OpenBuildingMap and land-use polygons. Apply the mixed-use rules where needed. Use evidence is prioritised as OpenBuildingMap occupancy, Overture class/subtype, then containing land-use polygons for these cities. Estimate storeys from reported floors, heights and fallback evidence; multiply footprint area by storeys and aggregate to the grid by use. Buildings up to 2,500 square metres are assigned by an internal point; larger footprints are split between cells in proportion to intersection area. OpenBuildingMap supplies both occupancy and height evidence. The stored `fa` array has nine layers: C1-C7, unknown use and industrial floor area; the industrial layer is a subset of C2 and must not be added again to total area.
5. **Transport and water.** Construct a road/rail graph with nodes, edges, travel times and grid sampling positions. Class-specific speeds set edge times. Compute water coverage from source polygons on a finer sampling grid. Stage 3 performs population assignment on this graph.
6. **Model-ready layers.** Export smoothed places and effective distance-decay settings after country/day-type overrides. This records the settings used by the example; it does not rerun commuting-flow calibration.

Storey estimation first uses reported Overture floors. Otherwise it uses available Overture, OpenBuildingMap or GHSL height (accepted height at least 2 m), divided by the assumed 3 m storey height. Remaining cases use OpenBuildingMap exact storeys, class/city medians, a reported storey-range midpoint or one storey. These fallbacks and their thresholds are implementation assumptions, not observed floors for every building; see the linked building code and parameter-source section below.

## Hourly shares and adopted settings

Each time-use matrix has 24 rows (local hours) and seven location columns, C1-C7. Each row is normalised to one when read. These are seven location classes, not seven weekdays. Separate matrices represent workdays and rest days. Helsinki uses FIN; Kitakyushu and Takasaki-Maebashi both use JPN. The [time-use figure](../figures/time_use_weights.png) shows the actual normalised matrices used by the model.

The supplied survey-derived matrices and allocation parameter JSON remain in Stage 2 as adopted research products. Their original diaries and calibration observations are not bundled. The detailed [time-use derivation](../../04_intermediate/time_use.md) describes survey harmonisation, transfer of day-type profiles, and the education and midday adjustments.

## Numbered programs, function calls and products

The default workflow reads original-source city subsets from `01_inputs/demo/raw/` and generates the spatial layers in `04_intermediate/demo/stage_2/`.

| Step | Program | Main function calls | Calculation and product |
|---|---|---|---|
| 01 | [01_create_city_grids.py](../../02_code/stage_2_100m_layers/01_create_city_grids.py) | `run_step(1)` → `city_table` → `source_preparation.city_record` | Urban-centre boundaries to local equal-area 100 m grids: `local_grids/` |
| 02 | [02_prepare_settlement_layers.py](../../02_code/stage_2_100m_layers/02_prepare_settlement_layers.py) | `run_step(2)` → `prepare_settlement` → `grid.resample_counts` or height sampling | Native GHSL raster crops to resident population, total/non-residential building volume and height |
| 03 | [03_prepare_destination_counts.py](../../02_code/stage_2_100m_layers/03_prepare_destination_counts.py) | `run_step(3)` → `places.city_places` → `places.classify` | Classify and count raw Overture places: `point_of_interest_counts/overture/` |
| 04 | [04_prepare_building_floor_area.py](../../02_code/stage_2_100m_layers/04_prepare_building_floor_area.py) | `run_step(4)` → `floor_area` → `buildings.city_floor_area` | Match Overture footprints with OpenBuildingMap occupancy/height and land-use evidence; estimate storeys and floor area: `buildings/floor_area_by_use/` |
| 05 | [05_prepare_transport_graphs.py](../../02_code/stage_2_100m_layers/05_prepare_transport_graphs.py) | `run_step(5)` → `transportation.fetch` → `network.build_from_table`; `water_coverage` | Raw road/rail/station features to routing graphs; water polygons to cell coverage: `road_and_rail_graphs/`, `water_coverage_percent/` |
| 06 | [06_save_model_layers.py](../../02_code/stage_2_100m_layers/06_save_model_layers.py) | `model_layer_exports.save_model_layers` → `model.poi_layer` and Gaussian smoothing | Smooth the generated place counts and record effective kernel settings: `smoothed_places/`, `distance_decay_kernels/` |

[04_prepare_building_floor_area.py](../../02_code/stage_2_100m_layers/04_prepare_building_floor_area.py) is the executable entry point. It reads the raw source files and calls `floor_area`, which uses `buildings.city_floor_area` for the calculations. [buildings.py](../../02_code/stage_2_100m_layers/buildings.py) provides the building-use, storey and floor-area algorithms. Floor area is footprint area multiplied by estimated storeys, aggregated to 100 m cells by use class.

The Stage 2 launcher runs steps 01 through 06 in order and requires each expected output to be newly written. The local-source preparation functions are in [local_raw_preparation.py](../../02_code/stage_2_100m_layers/local_raw_preparation.py). `preparation_metadata/` records source paths and processing statistics. Processing stops on a missing source or a calculation error.

Hourly location shares and calibrated allocation parameters are adopted study products. The example reads these products without repeating survey harmonisation or calibration. The [time-use guide](../../04_intermediate/time_use.md) documents the derivation of the 24-by-7 location-share matrices and the Finland and Japan profiles. The supplied OpenStreetMap place counts are supplementary processed data; the three cities have sufficient Overture coverage for the model's automatic source selection to use Overture alone.

The routing graph contains topology, travel times and sampling locations. Population assignment to the graph occurs in Stage 3. Routing zones start at 2 km and can expand for large domains. Raster conversion uses the GeoTIFF's own bounds, CRS and transform, including clipped edge tiles.

## Source preparation and model processing

Stage 2 reads the local source subsets produced or verified in [Stage 1](stage_1_data_inputs.md). It constructs the 100 m grid, resamples settlement data, interprets building evidence, classifies POIs and builds routing graphs. It does not download global tiles or query remote Parquet sources. The [Stage 1 method](stage_1_data_inputs.md#processing-sequence-and-implementation) describes extraction from external sources.

## Implementation modules

| Module | Called by | Function |
|---|---|---|
| [local_raw_preparation.py](../../02_code/stage_2_100m_layers/local_raw_preparation.py) | Stage 2 steps 01-05, default local-source mode | Read raw city subsets and prepare spatial layers |
| [cities.py](../../02_code/stage_2_100m_layers/cities.py) | Stage 2 preparation; Stage 3 allocation; Stage 4 outputs | Read city definitions and provide each city's grid |
| [grid.py](../../02_code/stage_2_100m_layers/grid.py) | [cities.py](../../02_code/stage_2_100m_layers/cities.py) and Stage 2 raster preparation | Grid geometry, projections and resampling |
| [places.py](../../02_code/stage_2_100m_layers/places.py) | Stage 2 step 03 | Classify and aggregate local Overture POI records |
| [buildings.py](../../02_code/stage_2_100m_layers/buildings.py), `building_sources/` | Stage 2 steps 04-05 | Interpret local building/transport records and calculate floor area by use |
| [time_use.py](../../02_code/stage_2_100m_layers/time_use.py) | Stage 3 step 02; Stage 4 step 01 and population-field reading | Read the Stage 2 hourly location shares |
| [model_layer_exports.py](../../02_code/stage_2_100m_layers/model_layer_exports.py) | Stage 2 step 06 | Save smoothed-place layers and effective kernel settings |

Routing-graph preparation calls graph-building functions in Stage 3's `network.py`. Model-layer export calls parameter and source-selection functions in Stage 3's `model.py`.

## Building and transport source readers

| Source module | Role in the default local workflow |
|---|---|
| [overture_reader.py](../../02_code/stage_2_100m_layers/building_sources/overture_reader.py) | Select model-required fields and filter local source features; `LocalOverture` supplies the city files. |
| [open_building_map_reader.py](../../02_code/stage_2_100m_layers/building_sources/open_building_map_reader.py) | Interpret occupancy and height records from the local city subset. |
| [open_building_map.py](../../02_code/stage_2_100m_layers/building_sources/open_building_map.py) | Interpret occupancy and height/storey codes used in floor-area estimation. |
| [transportation.py](../../02_code/stage_2_100m_layers/building_sources/transportation.py) | Extract transport segments and station evidence for graph construction. |
| [classification_rules.json](../../02_code/stage_2_100m_layers/building_sources/rules/classification_rules.json), [mixed_use.json](../../02_code/stage_2_100m_layers/building_sources/rules/mixed_use.json) | Building-use mappings and mixed-use shares. |

Graph preparation calls [network.py](../../02_code/stage_3_activity_allocation/network.py); model-layer export calls [model.py](../../02_code/stage_3_activity_allocation/model.py). These shared calls do not run population assignment during Stage 2.

[Section 13 of the time-use guide](../../04_intermediate/time_use.md#13-time-use-profiles-and-corrections) illustrates representative national profiles and the education and midday adjustments.

## Parameter values and sources

The [Stage 3 parameter tables](stage_3_activity_allocation.md#parameter-values-and-sources) list the adopted place-smoothing, attractiveness and kernel settings, together with the road/rail speeds used in graph preparation. Grid and building-preparation settings are listed below.

| Setting | Value | Source or basis |
|---|---|---|
| Model cell width | 100 m | Study-defined output resolution. |
| Domain margin | 10 km on each side | Study-defined model extent. |
| Height-to-storey conversion | 3 m/storey | Literature-supported study assumption; [Li et al. (2024), GLAMOUR](https://doi.org/10.1038/s41597-024-03446-2) use the same 3.0 m/storey relation for Chinese building reference heights. |
| Minimum accepted building height | 2 m | Study-defined input-screening threshold. |
| Minimum sample for class-specific median storeys | 30 buildings | Study-defined fallback rule. |
| Footprint area above which cell intersections are used | 2,500 m2 | Study-defined spatial-aggregation threshold. |

Li, R., Sun, T., Ghaffarian, S., Tsamados, M. and Ni, G. (2024). GLAMOUR: GLobAl building MOrphology dataset for URban hydroclimate modelling. *Scientific Data*, 11, 618. [doi:10.1038/s41597-024-03446-2](https://doi.org/10.1038/s41597-024-03446-2). The paper converts floor counts to heights for its Baidu reference buildings in China. Here the same relation is inverted to estimate storeys from heights. Applying a uniform storey height globally is a study assumption.

Time-use processing settings and their evidence are documented in [Section 11 of the time-use guide](../../04_intermediate/time_use.md#11-numerical-settings-and-their-provenance).

[Return to project README](../../README.md)
