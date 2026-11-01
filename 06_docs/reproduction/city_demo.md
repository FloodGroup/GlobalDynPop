# Three-city example

Helsinki (Finland), Kitakyushu (Japan) and Takasaki-Maebashi (Japan) provide complete examples on the original 100 m model grids, including the surrounding model domain. They were selected from the held-out validation set for good population-distribution agreement and manageable file sizes. They are illustrative successful cases, not a representative estimate of performance across all cities.

| City | Validation case | Nighttime rho | Daytime rho | Day/night-ratio rho | Grade |
|---|---|---:|---:|---:|---|
| Helsinki | FI01 | 0.896 | 0.937 | 0.838 | good |
| Kitakyushu | JP03 holiday | 0.899 | 0.925 | 0.846 | good |
| Kitakyushu | JP03 weekday | 0.906 | 0.962 | 0.765 | good |
| Takasaki-Maebashi | JP03 holiday | 0.958 | 0.941 | 0.750 | good |
| Takasaki-Maebashi | JP03 weekday | 0.959 | 0.964 | 0.824 | good |

Rho denotes Spearman correlation; the ratio column compares day/night population ratios. These are held-out validation cases graded good. The evaluation uses the kilometre grids recorded below, rather than the 100 m output cells. Validation observations are external.

| City and day type | Case identifier | Evaluation grid | Units evaluated (n) | Daytime CPC |
|---|---|---|---:|---:|
| Helsinki, FI01 | `944_FI_Helsinki:FI01` | 1/2 km | 80 | 0.868 |
| Kitakyushu, holiday | `01027_JPN_Kitakyushu:JP03:holiday` | 1km/2 km | 116 | 0.884 |
| Kitakyushu, weekday | `01027_JPN_Kitakyushu:JP03:weekday` | 1km/2 km | 116 | 0.898 |
| Takasaki-Maebashi, holiday | `05685_JPN_Takasaki_Maebashi:JP03:holiday` | 1km/2 km | 71 | 0.896 |
| Takasaki-Maebashi, weekday | `05685_JPN_Takasaki_Maebashi:JP03:weekday` | 1km/2 km | 71 | 0.895 |

All five cases belong to the validation sample. Helsinki's source record has `weekday=True` without a separate day-type label; the Japan records explicitly distinguish weekday and holiday. City stems are listed in [the run configuration](../../03_run/demo_configuration/city_demo_stems.txt).

## Run and numerical checks

Follow the [run guide](../../03_run/README.md) to install the environment and run all four stages or a selected stage. `run_city_demo.py run` verifies the raw subsets, rebuilds the Stage 2 spatial layers, computes Stage 3 allocations, writes Stage 4 outputs and updates the PNG figures. It adopts the supplied time-use shares and allocation settings. Original survey harmonisation and kernel calibration require external source records.

`run_city_demo.py check` checks processed-input file hashes and exact decoded-array fingerprints. Reproduction uses the same intermediate/output directories; running replaces the included results in place. File metadata is excluded from numerical comparisons. Observation-based validation separately requires the external observation records.

The runner reads three files under `03_run/demo_configuration/`: [city stems](../../03_run/demo_configuration/city_demo_stems.txt), [file manifest](../../03_run/demo_configuration/city_demo_files.csv) and [numerical fingerprints](../../03_run/demo_configuration/city_demo_array_checksums.json).

## Data and products

Raw spatial subsets are under `01_inputs/demo/raw/`. Stage 2 stores prepared grids, residents, buildings, places, graphs and adopted settings; Stage 3 stores attractiveness, destination allocations and transit. Final components, 144 single-band hourly rasters and functional land use are under `05_outputs/demo/`. See the [raw-source guide](../../01_inputs/demo/raw/README.md), [intermediate-data dictionary](../../04_intermediate/README.md) and [output dictionary](../../05_outputs/README.md) for file contents and units.

The resident grid covers the urban-centre bounding box plus its margin; its total can differ from the urban-centre population in the city table. The model conserves the full domain population. Component compression permits small encoding differences; hourly float32 rasters use lossless DEFLATE. Each file represents one local hour, with 24 files per city and day type.

Helsinki uses the Finland time-use profile with rest-day timing contrasts borrowed from GBR, ESP and BEL. Both Japanese cities use the Japan profile, including the documented workday school adjustment. See the [time-use guide](../../04_intermediate/demo/stage_2/time_use/time_use.pdf).

## Data sources and attribution


The source-package versions below identify the inputs used to produce these files. The transformations include city-grid reprojection, aggregation, classification, graph construction and population modelling. The source data licences continue to apply; the software licence does not replace them.

| Data | Provider and version | Attribution and terms | In this package |
|---|---|---|---|
| City definitions | European Commission, JRC, GHS-UCDB R2024A | [GHSL terms and required citations](https://human-settlement.emergency.copernicus.eu/GHSLhowToCite.php), CC BY 4.0 | Public; three-city derived layers included in this package |
| Resident population | European Commission, JRC, GHS-POP R2023A, 2025 epoch | [Product and citation](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php), CC BY 4.0 | Public; three-city derived layers included in this package |
| Built volume and non-residential volume | European Commission, JRC, GHS-BUILT-V R2023A, 2025 epoch | [Product and citation](https://human-settlement.emergency.copernicus.eu/ghs_buV2023.php), CC BY 4.0 | Public; three-city derived layers included in this package |
| Building height | European Commission, JRC, GHS-BUILT-H R2023A, 2018 epoch | [Product and citation](https://human-settlement.emergency.copernicus.eu/ghs_buH2023.php), CC BY 4.0 | Public; three-city derived layers included in this package |
| Buildings and routing graphs | Overture Maps Foundation, release 2026-10-21.0; © OpenStreetMap contributors and other listed suppliers | [Overture attribution](https://docs.overturemaps.org/attribution/), [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/); these derived database layers are supplied under ODbL 1.0 | Public; three-city derived layers included in this package |
| Building occupancy/height evidence | Oostwegel, Schorlemmer, Lingner and Evaz Zadeh (2025), OpenBuildingMap, GFZ Data Services | [Dataset DOI](https://doi.org/10.5880/GFZ.LKUT.2025.002), [provider and attribution](https://www.openbuildingmap.org/), ODbL 1.0; combined with Overture and GHSL for floor area | Public; three-city derived layers included in this package |
| Overture POI counts | Overture Maps Foundation, Places release 2026-10-21.0 | [Source-specific attribution and terms](https://docs.overturemaps.org/attribution/), including CDLA Permissive 2.0, Apache 2.0 and CC0; supplied as aggregate class counts | Public; three-city derived layers included in this package |
| OpenStreetMap POI counts | © OpenStreetMap contributors, planet 2026-10-22 | [Copyright and terms](https://www.openstreetmap.org/copyright), ODbL 1.0 | Public; three-city derived layers included in this package |
| Hourly activity shares | Study-produced aggregate FIN/JPN tables | Donor assignments and processing methods are retained in `location_share_sources.csv`; Japan: Statistics Bureau, Survey on Time Use and Leisure Activities 2016; Finland: national baseline with the donor ratios described above. Raw survey records are external. | Public aggregate tables included; raw survey microdata not included |

Population layers are model results derived from these inputs. Cite the GlobalDynPop manuscript together with the relevant source datasets when reusing them. No mobile-network observation records or commercial China POI layers are part of this bundle.


For GHSL, also cite Pesaresi et al. (2024), “Advances on the Global Human Settlement Layer by joint assessment of Earth Observation and population survey data”, International Journal of Digital Earth 17(1), and the product-specific publications linked above.

## Figures

The [population maps](../figures/demo_population_distributions.png) and [time-use weights](../figures/time_use_weights.png) are regenerated by Stage 4. Processing methods and parameter sources are in the [stage guides](../README.md#methods).
