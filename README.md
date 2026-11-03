# GlobalDynPop-100m

Hourly urban population modelling with a production-constrained gravity model.

GlobalDynPop-100m models hourly population distributions at 100 m resolution for typical workdays and rest days. Its global application covers 1,904 urban centres across 152 countries, defined by the Global Human Settlement Layer Urban Centre Database (GHS-UCDB R2024A) with at least 300,000 residents in 2025. Spatial inputs describe residents, buildings, activity destinations and transport networks. Time-use surveys and travel diaries provide the hourly location shares; commuting observations inform the distance-decay settings.

A production-constrained gravity model redistributes residents to activity destinations according to building floor area, point-of-interest density and activity-specific distance-decay kernels. Trips are assigned to the fastest road and rail routes to estimate the spatial distribution of people in transit. Resident, destination and in-transit population components are then combined using hourly activity-location shares. Each city is modelled on a local equal-area grid covering its urban-centre bounding box plus a 10 km margin on every side.

This repository provides the processing workflow, input subsets, intermediate layers and outputs for three worked examples: Helsinki, Kitakyushu and Takasaki-Maebashi.

## Study area and data coverage

Figure 1 shows the global distribution of the study cities, coloured by the source used to derive their hourly location shares: travel diaries, national time-use surveys, national average-day profiles with borrowed regional day-type contrasts, and regional average-day profiles. The accompanying charts show how these sources are distributed across regions, which cities use national or global distance-decay kernels, and the distribution of urban-centre population sizes.

![Figure 1. Global study cities, time-use source groups, kernel groups and population sizes](06_docs/figures/study_area.png)

**Figure 1. Global city coverage and input data.** Panel a shows study cities, coloured by the source of hourly location shares and sized by resident population in 2025; b summarises time-use source coverage by region; c shows the city counts assigned to national or global kernel groups; d shows the population-size distribution.

## Principal data sources

The research draws on global settlement and population databases, building data and points of interest (POIs), land-use data, transport networks, time-use surveys, travel diaries and commuting statistics. The main sources are summarised below.

| Data source | Provider | Version or reference period | Data content |
|---|---|---|---|
| GHSL Urban Centre Database (GHS-UCDB) | European Commission, Joint Research Centre | R2024A; 2025 city attributes | Urban-centre boundaries, city identifiers, resident populations and urban-centre areas. |
| [GHSL population (GHS-POP)](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php) | European Commission, Joint Research Centre | R2023A, 2025 epoch | Gridded resident population counts. |
| [GHSL built volume (GHS-BUILT-V)](https://human-settlement.emergency.copernicus.eu/ghs_buV2023.php) | European Commission, Joint Research Centre | R2023A, 2025 epoch | Gridded total and non-residential building volumes. |
| [GHSL building height (GHS-BUILT-H)](https://human-settlement.emergency.copernicus.eu/ghs_buH2023.php) | European Commission, Joint Research Centre | R2023A, 2018 epoch | Gridded mean building-height estimates, expressed in metres. |
| Overture Maps Buildings | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Building footprint polygons, building-use attributes, and available building heights in metres and floor counts. |
| [OpenBuildingMap](https://doi.org/10.5880/GFZ.LKUT.2025.002) | OpenBuildingMap; GFZ Data Services | 2025 dataset | Building occupancy classifications, height values in metres, and exact or ranged storey counts encoded in the building taxonomy. |
| Overture Maps POIs (Places) | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | POI locations, business and activity categories, and available operating-status attributes. |
| OpenStreetMap | OpenStreetMap contributors | Planet snapshot 2026-10-22 | Mapped points of interest and associated activity tags. |
| Overture Maps Transportation and Infrastructure | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Road and rail segments, stations and other transport-infrastructure features. |
| Overture Maps Land Use | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Land-use polygon geometries with class and subtype attributes describing mapped land functions. |
| Overture Maps Water | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Water-body polygon geometries and associated attributes. |
| China POI dataset (CN_POI) | Commercial dataset using the Amap classification system | 2025 and 2026 editions | POI names, activity categories and coordinates for Chinese cities. |
| Amap Web Services | Amap | 2026 collection | POI records and AOI information. |
| National time-use surveys | National statistical agencies | Survey-specific years | Activity episodes, location records, survey weights, and published hourly or daily activity tables. |
| National Household Travel Survey (USA), EOD (Mexico), and São Paulo Origin-Destination Survey (Brazil) | FHWA; INEGI; São Paulo Metro | 2017 | Household travel diaries, trip times, purposes and associated survey information. |
| Census and mobility-based commuting datasets | National census agencies and mobility-data providers | Source-specific years | Commuting flows and travel-distance information. |

Hourly location shares are derived from survey and diary records and inherited national average-day tables. The [time-use guide](04_intermediate/demo/stage_2/time_use/time_use.pdf) describes their construction and the supplied Finland and Japan profiles.

Building-height information comes from Overture building attributes, OpenBuildingMap height/storey codes and the GHSL building-height raster. Land-use polygons are a separate source from building footprints and POIs.

The source products have different reference years. Dataset versions and provider terms are documented in the [data attribution information](06_docs/reproduction/city_demo.md#data-sources-and-attribution); source-specific processing and parameter evidence are described in the [methods](06_docs/README.md#methods).

## Processing workflow

Figure 2 shows the four-stage calculation. Source data are converted to 100 m layers, then used to estimate destination attractiveness, gravity-based destination allocation and network transit. Hourly location shares combine the resulting components into population grids.

![Figure 2. Four-stage workflow from source data to hourly population grids](06_docs/figures/workflow.png)

**Figure 2. Model calculations and data flow.** Arrows connect raw inputs, prepared layers, activity-allocation components and outputs. Time-use shares feed both transit calculation and the final hourly mixture. Components and hourly grids preserve the city-domain population total.

| Stage | Purpose | Products | Method | Code |
|---|---|---|---|---|
| 1. Data inputs | Select urban centres and extract source data for their model domains, preserving source attributes, geometries and native raster pixels. Record provenance and verify file integrity. | City source subsets and provenance manifests. | [Method](06_docs/methods/stage_1_data_inputs.md) | [Code](02_code/stage_1_data_inputs/) |
| 2. 100 m layers | Construct local grids; derive resident population, building floor area and POI layers; build road/rail graphs; assemble hourly location shares and distance-decay settings. | Spatial model layers, routing graphs, hourly location shares and effective kernels. | [Method](06_docs/methods/stage_2_100m_layers.md) | [Code](02_code/stage_2_100m_layers/) |
| 3. Allocation of daily activities | Calculate destination attractiveness, distribute residents with the production-constrained gravity model, and assign trip person-time to the transport network. | Destination attractiveness, destination and in-transit population components by activity and day type, and packaged component GeoTIFFs. | [Method](06_docs/methods/stage_3_activity_allocation.md) | [Code](02_code/stage_3_activity_allocation/) |
| 4. Outputs | Combine population components using hourly location shares; derive functional land use; check and visualise the results. | Hourly population GeoTIFFs (24 single-band files per city and day type), functional land-use layers, figures and numerical checks. | [Method](06_docs/methods/stage_4_outputs.md) | [Code](02_code/stage_4_outputs/) |

Routing zones start at 2 km and expand for large domains. Survey harmonisation and parameter calibration precede population allocation. The 100 m output grid does not imply that routing or validation is performed at 100 m.

## Run the three-city example

```console
conda env create -f environment.yml
conda activate dynamic-population
python 03_run/run_city_demo.py check
python 03_run/run_city_demo.py run
```

`check` verifies the supplied processed inputs and decoded output arrays. `run` verifies the supplied raw sources in Stage 1, rebuilds the spatial layers in Stage 2, computes the model and updates the figures. The `run` command replaces the bundled products in place and compares the numerical results with the stored fingerprints. Source extraction is available separately through the [Stage 1 preparation program](02_code/stage_1_data_inputs/README.md#extract-city-subsets). Use `run --stage 1`, `2`, `3` or `4` to run a single stage with its prerequisites already present. Observation-based validation requires external records and is separate from numerical reproduction.

The [three-city guide](06_docs/reproduction/city_demo.md) records city selection, validation evidence and data attribution. The [run guide](03_run/README.md) covers launchers, path settings and the recorded test environment.

## Hourly activity patterns

Figure 3 shows the hourly location shares used for Finland and Japan. Home accounts for most of the population in the early morning, while work, education and other activities gain share during the day. The displayed profiles have higher daytime home shares on rest days than on workdays.

![Figure 3. Finland and Japan hourly location shares for workdays and rest days](06_docs/figures/time_use_weights.png)

**Figure 3. Temporal weights applied to the population components.** Columns distinguish workdays and rest days; rows distinguish Finland and Japan. The seven coloured shares represent home, work and commerce, education, services, leisure, transit and other locations, and sum to one at every hour. Helsinki uses the Finland profile; both Japanese cities use the Japan profile. The [time-use guide](04_intermediate/demo/stage_2/time_use/time_use.pdf) documents the survey mapping, donor transfer and corrections used to construct these profiles.

## Example population distributions

Figure 4 compares the three cities at 03:00-04:00, 08:00-09:00 and 13:00-14:00. The early-morning maps are dominated by the resident component. Morning and midday maps give greater weight to activity destinations and transit. Workday and rest-day columns show the effect of their respective hourly shares and activity allocations.

![Figure 4. Modelled population in the three cities at three local-hour intervals](06_docs/figures/demo_population_distributions.png)

**Figure 4. Selected-hour population outputs.** Rows show Helsinki, Kitakyushu and Takasaki-Maebashi. The first three columns show workdays and the last three show rest days; all hours are local time. Colours indicate people per 100 m cell. Each city uses one continuous logarithmic scale across its six maps. Colour limits differ between cities; use the corresponding colour-bar values for comparisons. Cells with fewer than three people are hidden and water is shown in pale blue-grey. The displayed extent includes each city's model margin; the complete output contains 24 hourly files per day type.

## Repository layout

```text
01_inputs/demo/raw/       Original-source spatial subsets for the three cities
02_code/stage_*/          Numbered programs and calculation modules by stage
03_run/                  Three-city runner, stage launchers and execution support
04_intermediate/demo/    Stage 2 layers/settings and Stage 3 allocation arrays
05_outputs/demo/         Population components, hourly grids and functional land use
06_docs/methods/         Processing methods and code links for each stage
06_docs/figures/         Workflow, population maps and time-use plots
06_docs/reproduction/    Three-city example and source attribution
```

The [intermediate-data dictionary](04_intermediate/README.md) and [output dictionary](05_outputs/README.md) describe file contents and units. [Raw data coverage](01_inputs/demo/raw/README.md) identifies the supplied sources. Other cities require compatible external inputs; see [run guide](03_run/README.md#other-city-inputs-and-result-comparison).

## Assumptions and parameter sources

The model conserves population within each city domain, including its surrounding margin. It cannot independently estimate net evacuation or migration across that boundary. Routing uses fixed class-specific speeds and a fixed spatial transit pattern within each day type. Outdoor leisure locations enter through mapped places, but the model does not separate indoor and outdoor populations. The [Stage 3 method](06_docs/methods/stage_3_activity_allocation.md) describes routing assumptions and implementation behaviour.

Parameter values and their evidence are documented in the [Stage 2](06_docs/methods/stage_2_100m_layers.md#parameter-values-and-sources), [Stage 3](06_docs/methods/stage_3_activity_allocation.md#parameter-values-and-sources) and [Stage 4](06_docs/methods/stage_4_outputs.md#parameter-values-and-sources) methods.

## Citation

Long, Z.-Y., Yang, R.-Y. & Duan, H.-F. Human mobility reshapes global urban flood risk patterns. Unpublished manuscript.

When reusing the data, also cite the relevant original datasets listed under [Data sources and attribution](06_docs/reproduction/city_demo.md#data-sources-and-attribution).

## Licence and data terms

GlobalDynPop-100m software is licensed under the [GNU General Public License v2.0](LICENSE) (GPL-2.0). Source datasets and derived database layers retain their applicable data licences and attribution requirements, documented under [Data sources and attribution](06_docs/reproduction/city_demo.md#data-sources-and-attribution).
