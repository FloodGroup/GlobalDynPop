# Population allocation parameters

`population_allocation_parameters.json` configures the population-allocation model. It determines how attractive destinations are, how the gravity model weights distance, which country/day-type overrides apply, and whether the in-transit component uses road/rail assignment. The file retains the study-wide country settings; only FIN and JPN settings apply to the three bundled cities.

## Activity classes

| Code | Meaning |
|---|---|
| C1 | Residential population, taken from the resident-population grid |
| C2 | Work, commerce and industry |
| C3 | Education |
| C4 | Healthcare and public services |
| C5 | Leisure, culture and sport |
| C6 | People in transit |
| C7 | Other activities |

## Settings in the JSON

| Key | What it controls | Values and units in this configuration |
|---|---|---|
| `attractor.<class>.poi_w` | POI weight in the mixture of normalised floor area and POI density | 0.5: equal weights when both layers are available; fallback rules apply if a layer is absent |
| `poi_sigma_m` | Gaussian smoothing scale for POI counts | 300 m |
| `ind_w` | Relative weight of industrial floor area in C2 attractiveness | 0.3; only used for C2, even though repeated under other classes |
| `unk_w` | Weight of the non-residential portion of unknown-use floor area in C2 | 1.0; only used for C2 |
| `poi_source` | POI source-selection rule | `auto`: Amap where available, otherwise Overture with OSM supplementation where sparse; `auto_noamap` excludes Amap |
| `alpha` | Exponent applied to normalised destination attractiveness | 1.1 for C2; 1.0 for C3, C4, C5 and C7 |
| `kind` | Distance-decay function used by gravity allocation | `pow`: power law with exponential cutoff |
| `d0.<class>` | Exponential cutoff scale, kappa, of the distance kernel | Metres; it is not a hard maximum trip distance |
| `beta.<class>` | Power-law distance-decay exponent | Dimensionless; larger values reduce the weight of distant destinations |
| `country.<ISO3>` | Country-specific overrides of the global settings | Applied first; the full list is retained for other study cities |
| `restday` | Overrides for rest days | Applied after country overrides |
| `transit` | Source of component C6 | `network`: use the assigned road/rail in-transit population layer |
| `shop_w` | China-specific C2 shop/service weight relative to workplaces | 0.15; does not apply to the three bundled cities |

The distance function is `f(d) = (d + 250 m)^(-beta) * exp(-d/kappa)`. The 250 m offset and numerical search-radius limits are implemented in the code; they are not separate fields in this JSON.

## Effective settings for the three cities

| Activity | Helsinki: kappa / beta, workday | Kitakyushu and Takasaki-Maebashi: kappa / beta, workday | Rest-day change |
|---|---|---|---|
| C2 | 100 km / 1.5 | 10 km / 1.0, from the JPN override | beta becomes 2.0; country-specific kappa is retained |
| C3 | 10 km / 2.0 | 10 km / 2.0 | None |
| C4 | 20 km / 1.5 | 20 km / 1.5 | None |
| C5 | 30 km / 2.0 | 30 km / 2.0 | kappa becomes 100 km |
| C7 | 30 km / 2.0 | 30 km / 2.0 | kappa becomes 100 km |

Hourly activity shares are input tables in `../hourly_location_shares/`; resident counts, building layers and POI counts are separate data inputs. Road speeds, routing-zone rules and land-use classification thresholds are defined in their corresponding programs. This JSON therefore does not contain every setting used by the workflow.

## Parameter sources

The [Stage 3 method](../../../../06_docs/methods/stage_3_activity_allocation.md#parameter-values-and-sources) lists each parameter's value and basis. Global and national work kernels, the education kernel and the fitted attractiveness exponents use study calibration observations. Leisure and rest-day settings use Seoul trip observations; C7 adopts the C5 kernel. The C4 kernel, POI/floor-area mixture weights, smoothing scale and industrial weight are study-defined.

Read by `02_calculate_in_transit_population.py` and `03_calculate_population_components.py` in [Stage 3](../../../../02_code/stage_3_activity_allocation/README.md). Land-use thresholds are explained in [Stage 4](../../../../02_code/stage_4_outputs/README.md).
