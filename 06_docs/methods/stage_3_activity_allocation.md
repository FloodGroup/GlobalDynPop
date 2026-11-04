# Stage 3: Allocation of daily activities

## Processing sequence

The runner reads the completed Stage 2 outputs in the same run directory. The numbered programs first save attractiveness, then compute the in-transit layers, and finally calculate destination populations and package the components. Destination allocation and transit both use Stage 2 settings; the hourly mixture is written in Stage 4.

## Programs and products

This stage reads `04_intermediate/demo/stage_2/` and writes `04_intermediate/demo/stage_3/`.

| Program | Calls | Saved result |
|---|---|---|
| [01_calculate_destination_attractiveness.py](../../02_code/stage_3_activity_allocation/01_calculate_destination_attractiveness.py) | `save_destination_attractiveness` → `model.attractor` | `destination_attractiveness/<city>.npz`: A_c for each class/day type |
| [02_calculate_in_transit_population.py](../../02_code/stage_3_activity_allocation/02_calculate_in_transit_population.py) | `run_city` → `road_graph`, `trip_matrices` → `network.zone_od`, `network.assign` | `in_transit_population/<city>.npz`: T for workdays and rest days |
| [03_calculate_population_components.py](../../02_code/stage_3_activity_allocation/03_calculate_population_components.py) | `model.components_daytypes`, `gravity.allocate` | `destination_population/<city>.npz`: D_c before raster encoding |

Attractiveness includes the configured exponent and is a dimensionless allocation weight. It need not sum to one after exponentiation. The saved destination populations have full computation precision and include any residents retained at home when no destination is reachable. In-transit layers are normalised to the domain population. Before their contribution to components, they are multiplied by the land fraction and renormalised; the resident C1 field remains the supplied GHS-POP field.

The component writer also packages N, D_c and T into the final per-city GeoTIFFs under `05_outputs/demo/population_components/`. The hourly writer in Stage 4 reads those component files. Array keys use activity codes C2, C3, C4, C5 and C7 plus `_workday` or `_restday`.

## Destination attractiveness and outdoor locations

The indoor destination layer mixes normalised floor area and smoothed POI counts with equal weights. Industrial capacity has weight 0.3, and unknown-use capacity contributes its estimated non-residential fraction. POIs use 300 m Gaussian smoothing followed by the configured host mask: a cell must contain at least 500 m2 of floor area, 1,500 m3 of building volume, or an original POI. The adopted parameter file uses `poi_mask="host"` for all classes.

Each destination layer is multiplied by its land fraction before indoor/outdoor mixing. Let I_c and O_c be the normalised indoor and outdoor pools. The pre-exponent destination field is `A0_c = W_indoor I_c + (1-W_indoor) O_c`. Attractiveness is then `(A0_c / sum(A0_c))^alpha_c`, with alpha=1.1 for work and 1 for the other activities. The gravity model acts on this combined field. Consequently W_indoor is not a guarantee that exactly that fraction of the final allocated population is indoors.

The outdoor pool uses the land outside GBA building footprints, divided into walkable streets; parks, managed grass, sports grounds and squares; and other open land. Their near-destination weights are 0.5755/0.1140/0.3105 for work and 0.5688/0.1244/0.3068 for services, leisure and other activities, from the adopted HAPEM-MS3 tables. Each group is weighted by available area and a 300 m Gaussian neighbourhood of indoor destinations. Agricultural and protected natural land are excluded from the residual open-space type. Empty groups redistribute their weights among available groups.

Education uses campus grounds, with the adult three-group rule as a fallback. Leisure and other activities allocate half the outdoor pool to parks, sports grounds and squares throughout the domain. Where typed inputs are absent, the core model uses an untyped outdoor fallback; the bundled demo explicitly requires all layers.

W_indoor is read from the 1,904-city table under Stage 2 `time_use/w_indoor/`. Its underlying sources measure daily indoor time; using this as the weight of away-from-home activity destinations is a model approximation. China uses province-level survey values, countries with adopted sources use their own values, and other countries use income/geographic/evidence-based reference matching. See the [assignment rules](../../04_intermediate/demo/stage_2/time_use/w_indoor/README.md).

Country overrides are applied before day-type overrides. Each activity class inherits unspecified global destination fields, including outdoor-pool rules, while applying its country-specific POI and distance-kernel settings.

## Gravity allocation

For origin cell `i` and destination cell `j`, the production-constrained allocation is:

```text
Z_c(i) = sum_j A_c(j) f_c(d_ij)
D_c(j) = A_c(j) sum_i N(i) f_c(d_ij) / Z_c(i)
```

`N` is resident population, `A_c` is attractiveness and `d_ij` is Euclidean distance. The configured kernel can be exponential or a power law with exponential cutoff, `(d + dmin)^(-beta) exp(-d/k)`. The supplied effective settings are stored under Stage 2 `distance_decay_kernels/`; these are separate from road travel-time costs. Convolutions on the 100 m grid are evaluated with FFTs. Origins with numerically negligible accessibility retain their residents at the origin. The implementation corrects floating-point residuals and includes retained residents in the stored destination component.

Each class component represents the domain's population allocated to that activity, before hourly weighting. Adding all components directly would count the population repeatedly. Stage 4 weights them by the corresponding location shares.

## In-transit allocation

1. Combine 100 m cells into larger square origin-destination zones. The side starts at 20 cells; the code adds five cells while its approximate zone count exceeds 1000. Large cities therefore use coarser zones.
2. Use population-weighted representative locations and activity-specific gravity weights between zones. Euclidean decay and network path time are distinct quantities.
3. Find fastest paths on a combined road/rail graph using fixed class-specific speeds. The baseline treats edges bidirectionally and has no traffic capacity, lane or time-varying congestion model.
4. Accumulate person-time along edges and sample it to 100 m cells. Allocate local access, egress and other local terms by street length. Failed routes use a distance-based local fallback split between endpoint zones.
5. Combine activity components using the day's activity weights and normalise the in-transit layer. The hourly in-transit share changes the amount; the within-day-type spatial pattern is fixed.

Road speeds (km/h): motorway 45, trunk 35, primary 28, secondary 24, tertiary 20, unclassified 18. Rail: standard gauge 45, narrow gauge 30, subway 35, light rail 25, monorail 30, tram 15. Local 12; walking 4.5. Road, rail and local-street speeds are study-defined effective routing speeds. The walking-speed assumption has empirical support as described below.

### Routing behaviour and interpretation

Local person-time can be omitted in zones without streets before the final normalisation. Intrazonal shortcuts can shorten the intended local distance, and shared road/rail connectors can permit transfers away from stations. These behaviours affect the spatial allocation of transit and are not resolved by conserving the final population total. Graph `p_time` values are precomputed, so changing speeds requires rebuilding the graph. The model also has a Gaussian transit fallback when a network is missing; that fallback does not reproduce road/rail assignment. The three-city runner requires the Stage 2 graph and always recalculates transit in program 02 before writing components. It does not use the Gaussian fallback or bundled transit arrays.

Road traffic-count agreement measures spatial association with traffic flows; it does not directly validate the instantaneous number of people present in each 100 m cell.

## Implementation modules

| Module | Function |
|---|---|
| [destination_attractiveness.py](../../02_code/stage_3_activity_allocation/destination_attractiveness.py) | Persist activity/day-type destination attractiveness |
| [gravity.py](../../02_code/stage_3_activity_allocation/gravity.py) | Production-constrained gravity allocation |
| [network.py](../../02_code/stage_3_activity_allocation/network.py) | Routing graph operations and assignment of trip person-time |
| [model.py](../../02_code/stage_3_activity_allocation/model.py) | Population model settings, destination layers, allocation and components |

[model.py](../../02_code/stage_3_activity_allocation/model.py) and the stage programs read Stage 1 grid definitions and Stage 2 source layers and hourly shares. Graph-building functions are also called during Stage 2 transport preparation. Execution locks and memory monitoring are imported from `03_run/`.

## Parameter values and sources

Study-defined denotes a modelling or implementation choice specified for this study. Study-calibrated denotes a value selected using the study observations and calibration procedure. Literature-supported assumptions cite evidence for the numerical value and describe its application. The calibration sources and selection rules are given below.

### Road and rail speeds

Implementation: [network.py](../../02_code/stage_3_activity_allocation/network.py). Keys below identify individual settings.

| Setting | Value | Unit | Source or basis |
|---|---:|---|---|
| `network.ROAD_KMH.motorway` | 45.0 | km/h | Study-defined |
| `network.ROAD_KMH.trunk` | 35.0 | km/h | Study-defined |
| `network.ROAD_KMH.primary` | 28.0 | km/h | Study-defined |
| `network.ROAD_KMH.secondary` | 24.0 | km/h | Study-defined |
| `network.ROAD_KMH.tertiary` | 20.0 | km/h | Study-defined |
| `network.ROAD_KMH.unclassified` | 18.0 | km/h | Study-defined |
| `network.RAIL_KMH.standard_gauge` | 45.0 | km/h | Study-defined |
| `network.RAIL_KMH.narrow_gauge` | 30.0 | km/h | Study-defined |
| `network.RAIL_KMH.subway` | 35.0 | km/h | Study-defined |
| `network.RAIL_KMH.light_rail` | 25.0 | km/h | Study-defined |
| `network.RAIL_KMH.monorail` | 30.0 | km/h | Study-defined |
| `network.RAIL_KMH.tram` | 15.0 | km/h | Study-defined |

### Routing and graph settings

Implementation: [network.py](../../02_code/stage_3_activity_allocation/network.py). Keys below identify individual settings.

| Setting | Value | Unit | Source or basis |
|---|---:|---|---|
| `network.LOCAL_KMH` | 12.0 | km/h | Study-defined |
| `network.WALK_KMH` | 4.5 | km/h | Literature-supported study assumption; [Schimpl et al. (2011)](https://doi.org/10.1371/journal.pone.0023299), median 1.25 m/s = 4.5 km/h |
| `network.DETOUR` | 1.3 | dimensionless | Study-defined |
| `network.BOARD_MIN` | 5.0 | min | Study-defined |
| `network.WALK_TO_STATION_M` | 1200.0 | m | Study-defined |
| `network.SNAP_STATION_M` | 250.0 | m | Study-defined |
| `network.ACCESS_K` | 6 | road-node connections per zone | Study-defined |
| `network.SAMPLE_M` | 25.0 | m | Study-defined |
| `network.MAX_TRIP_H` | 3.0 | h | Study-defined |
| `network.ZONE_MIN_CELLS` | 20 | grid cells per zone side | Study-defined |
| `network.ZONE_MAX` | 1000 | approximate zone count | Study-defined |
| `network.GRAPH_FORMAT` | 1 | format identifier | Implementation-defined archive format |

### Attractiveness settings

Implementation: [population_allocation_parameters.json](../../04_intermediate/demo/stage_2/allocation_parameters/population_allocation_parameters.json). Keys below identify individual settings.

| Setting | Value | Unit | Source or basis |
|---|---:|---|---|
| `model_parameters.attractor.C2.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.attractor.C2.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.attractor.C2.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.attractor.C2.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.attractor.C2.alpha` | 1.1 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |
| `model_parameters.attractor.C3.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.attractor.C3.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.attractor.C3.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.attractor.C3.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.attractor.C3.alpha` | 1.0 | dimensionless | Study-defined |
| `model_parameters.attractor.C4.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.attractor.C4.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.attractor.C4.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.attractor.C4.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.attractor.C4.alpha` | 1.0 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |
| `model_parameters.attractor.C5.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.attractor.C5.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.attractor.C5.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.attractor.C5.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.attractor.C5.alpha` | 1.0 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |
| `model_parameters.attractor.C7.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.attractor.C7.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.attractor.C7.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.attractor.C7.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.attractor.C7.alpha` | 1.0 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |

### Global and rest-day kernels

Implementation: [population_allocation_parameters.json](../../04_intermediate/demo/stage_2/allocation_parameters/population_allocation_parameters.json). Keys below identify individual settings.

| Setting | Value | Unit | Source or basis |
|---|---:|---|---|
| `model_parameters.d0.C2` | 100000.0 | m | Study-calibrated; Seoul work OD, Japan census commuting and Rio de Janeiro OD |
| `model_parameters.d0.C3` | 10000 | m | Study-calibrated; Seoul school-trip OD |
| `model_parameters.d0.C4` | 20000 | m | Study-defined |
| `model_parameters.d0.C5` | 30000 | m | Study-selected; Seoul other-purpose OD by day type |
| `model_parameters.d0.C7` | 30000 | m | Study-defined transfer of the Seoul-derived C5 kernel |
| `model_parameters.beta.C2` | 1.5 | dimensionless | Study-calibrated; Seoul work OD, Japan census commuting and Rio de Janeiro OD |
| `model_parameters.beta.C3` | 2.0 | dimensionless | Study-calibrated; Seoul school-trip OD |
| `model_parameters.beta.C4` | 1.5 | dimensionless | Study-defined |
| `model_parameters.beta.C5` | 2.0 | dimensionless | Study-selected; Seoul other-purpose OD by day type |
| `model_parameters.beta.C7` | 2.0 | dimensionless | Study-defined transfer of the Seoul-derived C5 kernel |
| `model_parameters.restday.d0.C5` | 100000 | m | Observation-informed study setting; Seoul weekend other-purpose trip distances |
| `model_parameters.restday.d0.C7` | 100000 | m | Observation-informed study setting; Seoul weekend other-purpose trip distances |
| `model_parameters.restday.beta.C2` | 2.0 | dimensionless | Study-selected; Seoul Saturday and Sunday work-trip OD |

### Country overrides

Implementation: [population_allocation_parameters.json](../../04_intermediate/demo/stage_2/allocation_parameters/population_allocation_parameters.json). Keys below identify individual settings.

| Setting | Value | Unit | Source or basis |
|---|---:|---|---|
| `model_parameters.country.CHN.d0.C2` | 10000.0 | m | Study-calibrated; 2025 Annual Report on Commuting in Major Chinese Cities; commuting distances; two-fold selection |
| `model_parameters.country.CHN.attractor.C2.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C2.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.country.CHN.attractor.C2.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C2.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C2.shop_w` | 0.15 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C2.alpha` | 1.1 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |
| `model_parameters.country.CHN.attractor.C3.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C3.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.country.CHN.attractor.C3.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C3.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C3.alpha` | 1.0 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C4.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C4.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.country.CHN.attractor.C4.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C4.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C4.alpha` | 1.0 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |
| `model_parameters.country.CHN.attractor.C5.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C5.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.country.CHN.attractor.C5.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C5.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C5.alpha` | 1.0 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |
| `model_parameters.country.CHN.attractor.C7.poi_w` | 0.5 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C7.poi_sigma_m` | 300 | m | Study-defined |
| `model_parameters.country.CHN.attractor.C7.ind_w` | 0.3 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C7.unk_w` | 1.0 | dimensionless | Study-defined |
| `model_parameters.country.CHN.attractor.C7.alpha` | 1.0 | dimensionless | Study-calibrated; joint attractiveness-exponent search on 107 calibration cases |
| `model_parameters.country.CHN.beta.C2` | 1.25 | dimensionless | Study-calibrated; 2025 Annual Report on Commuting in Major Chinese Cities; commuting distances; two-fold selection |
| `model_parameters.country.ESP.d0.C2` | 100000.0 | m | Study-calibrated; Spain INE mobile-phone daytime OD; two-fold selection |
| `model_parameters.country.ESP.beta.C2` | 1.75 | dimensionless | Study-calibrated; Spain INE mobile-phone daytime OD; two-fold selection |
| `model_parameters.country.FRA.d0.C2` | 15000.0 | m | Study-calibrated; France Census 2020 home-to-work OD; two-fold selection |
| `model_parameters.country.FRA.beta.C2` | 0.75 | dimensionless | Study-calibrated; France Census 2020 home-to-work OD; two-fold selection |
| `model_parameters.country.GBR.d0.C2` | 7500.0 | m | Study-calibrated; England and Wales Census 2011, WU03EW OD; two-fold selection |
| `model_parameters.country.GBR.beta.C2` | 0.75 | dimensionless | Study-calibrated; England and Wales Census 2011, WU03EW OD; two-fold selection |
| `model_parameters.country.IND.d0.C2` | 10000.0 | m | Study-calibrated; Census of India 2011, table B-28; urban-worker distance classes; two-fold selection |
| `model_parameters.country.IND.beta.C2` | 0.75 | dimensionless | Study-calibrated; Census of India 2011, table B-28; urban-worker distance classes; two-fold selection |
| `model_parameters.country.ITA.d0.C2` | 10000.0 | m | Study-calibrated; Italy Census 2011 work-commuting matrix; two-fold selection |
| `model_parameters.country.ITA.beta.C2` | 1.0 | dimensionless | Study-calibrated; Italy Census 2011 work-commuting matrix; two-fold selection |
| `model_parameters.country.JPN.d0.C2` | 10000.0 | m | Study-calibrated; Japan Census 2020 work-commuting OD; two-fold selection |
| `model_parameters.country.JPN.beta.C2` | 1.0 | dimensionless | Study-calibrated; Japan Census 2020 work-commuting OD; two-fold selection |
| `model_parameters.country.POL.d0.C2` | 30000.0 | m | Study-calibrated; Poland Census 2021 work-commuting OD; two-fold selection |
| `model_parameters.country.POL.beta.C2` | 1.5 | dimensionless | Study-calibrated; Poland Census 2021 work-commuting OD; two-fold selection |
| `model_parameters.country.USA.d0.C2` | 20000.0 | m | Study-calibrated; US Census LODES 8, 2021 home-to-work OD; two-fold selection |
| `model_parameters.country.USA.beta.C2` | 0.5 | dimensionless | Study-calibrated; US Census LODES 8, 2021 home-to-work OD; two-fold selection |

`GRAPH_FORMAT` is a file-format identifier. `ZONE_MIN_CELLS` is a zone side length measured in grid cells; `ZONE_MAX` is the approximate zone-count limit. `ACCESS_K` is the number of nearby road-node connections. `ind_w` and `unk_w` are used for C2 even where the configuration repeats them under other classes. China-specific settings are retained in the supplied configuration but do not apply to the three example cities. Graph preparation in Stage 2 also uses the network speed and graph settings listed here.

## Calibration data and parameter selection

The numerical kernel values below are estimates from this study. Their source datasets supply commuting flows or travel distances; they do not publish these model coefficients.

| Parameter group | Source observations | Adopted value and selection |
|---|---|---|
| Global work kernel | Seoul capital-area mobile-network OD by purpose; Japan Census 2020 work commuting for seven calibration cities; Rio de Janeiro OD | beta 1.5, kappa 100 km; highest mean interzonal common part of commuters across the three datasets. |
| Education | Seoul school-trip OD | beta 2.0, kappa 10 km; selected from the candidate grid. |
| Leisure and other activities | Seoul other-purpose OD on Wednesday, Saturday and Sunday | C5 beta 2.0, kappa 30 km; selected for agreement across day types. C7 adopts this kernel as a study-defined transfer. |
| Rest-day work | Seoul Saturday and Sunday work-trip OD | beta 2.0; the workday country-specific kappa is retained. |
| Rest-day leisure and other | Seoul weekend other-purpose OD and trip distances | kappa 100 km; an observation-informed choice favouring longer modelled trips while retaining similar OD agreement. |
| China work kernel | 2025 Annual Report on Commuting in Major Chinese Cities: mean distance and share below 5 km, 20 calibration report cities | beta 1.25, kappa 10 km; two-fold selection using distance loss. |
| India work kernel | Census of India 2011 B-28: urban other-worker distance classes, 61 calibration cities | beta 0.75, kappa 10 km; trips up to 30 km, two-fold selection using distance loss. |
| USA work kernel | LODES 8 home-to-work flows, all jobs, 2021; six calibration cities | beta 0.5, kappa 20 km. |
| France work kernel | Census 2020 home-to-work flows; six calibration cities | beta 0.75, kappa 15 km. |
| England and Wales work kernel | Census 2011 WU03EW; ten calibration cities | beta 0.75, kappa 7.5 km; adopted under the GBR code. |
| Spain work kernel | INE mobile-phone daytime OD; seven calibration cities | beta 1.75, kappa 100 km. |
| Italy work kernel | Census 2011 work-commuting matrix; six calibration cities | beta 1.0, kappa 10 km. |
| Japan work kernel | Census 2020 work commuting; seven calibration cities | beta 1.0, kappa 10 km. |
| Poland work kernel | Census 2021 commuting; five calibration cities | beta 1.5, kappa 30 km. |
| Attractiveness exponents | 107 calibration cases grouped into 1 km population lattices, observation zones, Japanese people-flow data, US hourly device data and Taiwan township observations | Joint search over ten candidate pairs selected alpha C2 = 1.1 and alpha C4/C5/C7 = 1.0. Education alpha C3 = 1.0 is fixed. |

National work kernels use two folds formed by alternating calibration cities in population order. A national kernel is adopted when the kernel selected on each fold improves on the global kernel on the other fold; its final coefficients use all calibration cities in that country. China and India apply the same adoption rule to commuting-distance loss.

The attractiveness search maximises the mean calibration objective across the five observation groups. The selected pair scores 0.800551, compared with 0.796702 for both exponents equal to one. The C4 kernel (beta 1.5, kappa 20 km) remains a study-defined service-trip setting.

### Walking-speed reference

Schimpl, M., et al. (2011). Association between Walking Speed and Age in Healthy, Free-Living Individuals Using Mobile Accelerometry—A Cross-Sectional Study. *PLOS ONE*, 6(8), e23299. [doi:10.1371/journal.pone.0023299](https://doi.org/10.1371/journal.pone.0023299).

The open subset of this healthy-adult accelerometry study has a median free-living walking speed of 1.25 m/s, exactly 4.5 km/h. This supports the value used for station access as a modelling assumption. The model applies one walking speed to all cities and population groups.

[Return to project README](../../README.md)
