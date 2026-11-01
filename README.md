# GlobalDynPop-100m

Hourly urban population modelling with a production-constrained gravity model.

GlobalDynPop-100m models hourly population distributions at 100 m resolution for typical workdays and rest days. Its global application covers 1,904 urban centres across 152 countries, defined by the Global Human Settlement Layer Urban Centre Database (GHS-UCDB R2024A) with at least 300,000 residents in 2025. Spatial inputs describe residents, buildings, activity destinations and transport networks. Time-use surveys and travel diaries provide the hourly location shares; commuting observations inform the distance-decay settings.

A production-constrained gravity model redistributes residents to activity destinations according to building floor area, point-of-interest density and activity-specific distance-decay kernels. Trips are assigned to the fastest road and rail routes to estimate the spatial distribution of people in transit. Resident, destination and in-transit population components are then combined using hourly activity-location shares. Each city is modelled on a local equal-area grid covering its urban-centre bounding box plus a 10 km margin on every side.

The data package covers all 1,904 cities. **Helsinki, Kitakyushu and Takasaki-Maebashi** are the three worked examples used to demonstrate the processing workflow and its intermediate and final products.

## Study area and data coverage

Figure 1 shows the global distribution of the study cities, coloured by the source used to derive their hourly location shares: travel diaries, national time-use surveys, national average-day profiles with borrowed regional day-type contrasts, and regional average-day profiles. The accompanying charts show how these sources are distributed across regions, which cities use national or global distance-decay kernels, and the distribution of urban-centre population sizes.

![Figure 1. Global study cities, time-use source groups, kernel groups and population sizes](06_docs/figures/study_area.png)

**Figure 1. Global city coverage and input data.** Panel a shows study cities, coloured by the source of hourly location shares and sized by resident population in 2025; b summarises time-use source coverage by region; c shows the city counts assigned to national or global kernel groups; d shows the population-size distribution.

## Principal data sources

The research draws on global settlement and population databases, building data and points of interest (POIs), land-use data, transport networks, time-use surveys, travel diaries and commuting statistics. The main sources are summarised below.

| Data source | Provider | Version or reference period | Data content | In this package |
|---|---|---|---|---|
| GHSL Urban Centre Database (GHS-UCDB) | European Commission, Joint Research Centre | R2024A; 2025 city attributes | Urban-centre boundaries, city identifiers, resident populations and urban-centre areas. | Public source; three-city subsets included under `01_inputs/demo/` |
| [GHSL population (GHS-POP)](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php) | European Commission, Joint Research Centre | R2023A, 2025 epoch | Gridded resident population counts. | Public source; three-city subsets included under `01_inputs/demo/` |
| [GHSL built volume (GHS-BUILT-V)](https://human-settlement.emergency.copernicus.eu/ghs_buV2023.php) | European Commission, Joint Research Centre | R2023A, 2025 epoch | Gridded total and non-residential building volumes. | Public source; three-city subsets included under `01_inputs/demo/` |
| [GHSL building height (GHS-BUILT-H)](https://human-settlement.emergency.copernicus.eu/ghs_buH2023.php) | European Commission, Joint Research Centre | R2023A, 2018 epoch | Gridded mean building-height estimates, expressed in metres. | Public source; three-city subsets included under `01_inputs/demo/` |
| Overture Maps Buildings | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Building footprint polygons, building-use attributes, and available building heights in metres and floor counts. | Public source; three-city subsets included under `01_inputs/demo/` |
| [OpenBuildingMap](https://doi.org/10.5880/GFZ.LKUT.2025.002) | OpenBuildingMap; GFZ Data Services | 2025 dataset | Building occupancy classifications, height values in metres, and exact or ranged storey counts encoded in the building taxonomy. | Public source; three-city subsets included under `01_inputs/demo/` |
| Overture Maps POIs (Places) | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | POI locations, business and activity categories, and available operating-status attributes. | Public source; three-city subsets included under `01_inputs/demo/` |
| OpenStreetMap | OpenStreetMap contributors | Planet snapshot 2026-10-22 | Mapped points of interest and associated activity tags. | Public source; three-city subsets included under `01_inputs/demo/` |
| Overture Maps Transportation and Infrastructure | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Road and rail segments, stations and other transport-infrastructure features. | Public source; three-city subsets included under `01_inputs/demo/` |
| Overture Maps Land Use | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Land-use polygon geometries with class and subtype attributes describing mapped land functions. | Public source; three-city subsets included under `01_inputs/demo/` |
| Overture Maps Water | Overture Maps Foundation and contributing providers | Release 2026-10-21.0 | Water-body polygon geometries and associated attributes. | Public source; three-city subsets included under `01_inputs/demo/` |
| China POI dataset (CN_POI) | Commercial dataset using the Amap classification system | 2025 and 2026 editions | POI names, activity categories and coordinates for Chinese cities. | Not included (commercial / restricted) |
| Amap Web Services | Amap | 2026 collection | POI records and AOI information. | Not included (commercial / restricted) |
| National time-use surveys | National statistical agencies | Survey-specific years | Activity episodes, location records, survey weights, and published hourly or daily activity tables. | Not included as raw records; adopted aggregates / parameters only where supplied |
| National Household Travel Survey (USA), EOD (Mexico), and São Paulo Origin-Destination Survey (Brazil) | FHWA; INEGI; São Paulo Metro | 2017 | Household travel diaries, trip times, purposes and associated survey information. | Not included as raw records; adopted aggregates / parameters only where supplied |
| V11 time-use parameter dataset | Earlier global population-modelling research | V11 | Country-level average-day activity-location profiles. | Not included as raw records; adopted aggregates / parameters only where supplied |
| Census and mobility-based commuting datasets | National census agencies and mobility-data providers | Source-specific years | Commuting flows and travel-distance information. | Not included as raw records; adopted aggregates / parameters only where supplied |

Building-height information comes from Overture building attributes, OpenBuildingMap height/storey codes and the GHSL building-height raster. Land-use polygons are a separate source from building footprints and POIs.

The source products have different reference years. Dataset versions and provider terms are documented in the [data attribution information](06_docs/reproduction/city_demo.md#data-sources-and-attribution); source-specific processing and parameter evidence are described in the [methods](06_docs/README.md#methods).

## Processing workflow

Figure 2 shows the four-stage calculation. Source data are converted to 100 m layers, then used to estimate destination attractiveness, gravity-based destination allocation and network transit. Hourly location shares combine the resulting components into population grids.

![Figure 2. Four-stage workflow from source data to hourly population grids](06_docs/figures/workflow.png)

**Figure 2. Model calculations and data flow.** Arrows connect raw inputs, prepared layers, activity-allocation components and outputs. Time-use shares feed both transit calculation and the final hourly mixture. Components and hourly grids preserve the city-domain population total.

The paths below describe the three-city execution example.

| Stage | Purpose | Products | Method | Code |
|---|---|---|---|---|
| 1. Data inputs | Select source data for the city domains, preserve source attributes and native raster pixels, and verify the supplied subsets. | Original-source subsets and provenance manifests in `01_inputs/demo/raw/`; verification status. | [Method](06_docs/methods/stage_1_data_inputs.md) | [Code](02_code/stage_1_data_inputs/) |
| 2. 100 m layers | Build local grids; prepare residents, building floor area, POIs and road/rail graphs. Read the adopted hourly shares and distance-decay settings. | `04_intermediate/demo/stage_2/`: spatial layers, graphs, shares and effective kernels. | [Method](06_docs/methods/stage_2_100m_layers.md) | [Code](02_code/stage_2_100m_layers/) |
| 3. Allocation of daily activities | Calculate destination attractiveness, allocate residents with the production-constrained gravity model, and assign trip person-time to the network. | `04_intermediate/demo/stage_3/`: attractiveness, destination population and in-transit population. The component writer also packages these as GeoTIFFs. | [Method](06_docs/methods/stage_3_activity_allocation.md) | [Code](02_code/stage_3_activity_allocation/) |
| 4. Outputs | Combine the population components using hourly location shares; derive functional land use; check and plot the results. | `05_outputs/demo/`: components, 144 single-band hourly population files and functional land use. Figures are in `06_docs/figures/`. | [Method](06_docs/methods/stage_4_outputs.md) | [Code](02_code/stage_4_outputs/) |

Routing zones start at 2 km and expand for large domains. Survey harmonisation and kernel calibration are upstream operations; this example reads their supplied products. The 100 m output grid does not imply that routing or validation is performed at 100 m.

## Run the three-city example

```console
conda env create -f environment.yml
conda activate dynamic-population
python 03_run/run_city_demo.py check
python 03_run/run_city_demo.py run
```

`check` verifies the supplied processed inputs and decoded output arrays. `run` verifies the raw sources, rebuilds the spatial layers, computes the model and updates the figures. It replaces the bundled products in place and compares the numerical results with the stored fingerprints. Use `run --stage 1`, `2`, `3` or `4` to run a single stage with its prerequisites already present. Observation-based validation requires external records and is separate from numerical reproduction.

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

Zhi-Yong Long, Rui-Yi Yang and Huan-Feng Duan, State Key Laboratory of Climate Resilience for Coastal Cities (SKL-CRCC), The Hong Kong Polytechnic University. *Human mobility reshapes global urban flood risk patterns*.

When reusing the data, also cite the relevant original datasets listed under [Data sources and attribution](06_docs/reproduction/city_demo.md#data-sources-and-attribution).

## Licence and data terms

Software in this repository is released under the [GNU General Public License v2.0](LICENSE) (GPL-2.0), matching FloodGroup/LISFLOOD-SWMM-Coupling. Source datasets retain their own terms. See the [source attribution table](06_docs/reproduction/city_demo.md#data-sources-and-attribution) before redistributing data or derived database layers.
