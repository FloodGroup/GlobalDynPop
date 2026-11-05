# Three-city example

Helsinki (Finland), Kitakyushu (Japan) and Takasaki-Maebashi (Japan) provide complete examples on the original 100 m model grids, including the surrounding model domain. They were selected from the held-out validation set for good population-distribution agreement and manageable file sizes. They are illustrative successful cases, not a representative estimate of performance across all cities.

## Run and numerical checks

Run `python 03_run/run_city_demo.py run` to reconstruct the four-stage chain from raw spatial subsets. Then run `python 03_run/run_city_demo.py check` to verify the generated results. Sequential `run --stage 1`, `2`, `3`, `4` commands perform the same calculations and must use the same `--out` directory. Stage 3 recalculates road/rail transit, and Stage 4 reads that run's components. See the [execution guide](../../03_run/README.md).

Results are written under `04_intermediate/demo/reproduction/`. Missing inputs or failed calculations produce a nonzero exit code. Bundled reference arrays are used only for optional comparisons; differences are reported separately from internal consistency. Survey-derived hourly shares and calibrated parameters remain adopted non-spatial inputs.

## Data and products

Three-city GlobalBuildingAtlas/Overture/OBM/GHSL source subsets are provided under `01_inputs/demo/raw/`. The raw folder also contains native WorldCover and JRC GSW windows, plus public parameter-source tables and reports. `run_raw_reconstruction.py` rebuilds the spatial chain offline and reports its own comparison results. Survey microdata and calibration observations are outside that command’s scope. Stage 1 stores city grid definitions; Stage 2 stores prepared residents, GBA capacity, permanent water, typed open space, places, graphs and adopted settings; Stage 3 stores attractiveness, destination allocations and transit. Final components, 144 single-band hourly rasters and functional land use are under `05_outputs/demo/`. See the [raw-source guide](../../01_inputs/demo/raw/README.md), [intermediate-data dictionary](../../04_intermediate/README.md) and [output dictionary](../../05_outputs/README.md) for file contents and units.

The resident grid covers the urban-centre bounding box plus its margin; its total can differ from the urban-centre population in the city table. The model conserves the full domain population. Component compression permits small encoding differences; hourly float32 rasters use lossless DEFLATE. Each file represents one local hour, with 24 files per city and day type.

Helsinki uses the Finland time-use profile with rest-day timing contrasts borrowed from GBR, ESP and BEL. Both Japanese cities use the Japan profile, including the documented workday school adjustment. See the [time-use guide](../../04_intermediate/time_use/time_use.md).

## Data sources and attribution

GBA-derived inputs and outputs are subject to the non-commercial conditions in [data terms](../methods/data_sources.md#licence-of-the-example-layers-and-outputs). See the [source inventory](../methods/data_sources.md) for GlobalBuildingAtlas, WorldCover, JRC, indoor-time and outdoor-microenvironment sources.



The table below identifies input dataset versions, providers and data terms. The transformations include city-grid reprojection, aggregation, classification, graph construction and population modelling. The source data licences continue to apply; the software licence does not replace them.

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

Population layers are model results derived from these inputs. Cite the study listed in the [Citation section](../../README.md#citation) together with the relevant source datasets when reusing them. No mobile-network observation records or commercial China POI layers are part of this bundle.


For GHSL, also cite Pesaresi et al. (2024), “Advances on the Global Human Settlement Layer by joint assessment of Earth Observation and population survey data”, International Journal of Digital Earth 17(1), and the product-specific publications linked above.

## Figures

The [population maps](../figures/demo_population_distributions.png) and [time-use weights](../figures/time_use_weights.png) are regenerated by Stage 4. Processing methods and parameter sources are in the [stage guides](../README.md#methods).