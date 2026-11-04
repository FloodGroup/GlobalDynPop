# Data sources and licences (GlobalDynPop-100m)

The model reads the data sets below. The worked example (`01_inputs/`, `04_intermediate/`, `05_outputs/`) contains
original spatial source subsets, public parameter-source materials and derived 100-m layers for three cities (Helsinki, Kitakyushu and Takasaki-Maebashi); the
original global files must be downloaded from their providers to prepare other cities. Please acknowledge the
original data sets when you use the example or the outputs of the model.

| Data set | Provider | Version or period | Used for | Licence or terms |
|---|---|---|---|---|
| GHS Urban Centre Database (GHS-UCDB) | European Commission, Joint Research Centre | R2024A, 2025 attributes | urban centres, city grids | CC BY 4.0 |
| GHS-POP | European Commission, JRC | R2023A, 2025 epoch | residents (nighttime field) | CC BY 4.0 |
| GHS-BUILT-V, GHS-BUILT-H | European Commission, JRC | R2023A (2025 volume, 2018 height) | built volume, non-residential share, height fallback | CC BY 4.0 |
| GlobalBuildingAtlas (Zhu et al. 2025, Earth Syst. Sci. Data 17, 6647â€“6668) | Technical University of Munich | LoD1, 2025 | building footprints and heights â†’ floor area | **CC BY-NC 4.0** (non-commercial) |
| Overture Maps: buildings, places, transportation, base (land use, water) | Overture Maps Foundation | release 2026-10-21.0 | building use, POIs, road and rail network, land use, open space | ODbL 1.0 (buildings, transportation, base), CDLA-Permissive 2.0 (places) |
| OpenBuildingMap | GFZ Data Services | 2025 | building occupancy and storeys | see provider terms (ODbL-derived) |
| OpenStreetMap | OpenStreetMap contributors | planet 2026-10-22 | POIs where Overture is sparse, water polygons | ODbL 1.0 |
| ESA WorldCover | European Space Agency | 2021 (v200) | permanent water, land cover | CC BY 4.0 |
| JRC Global Surface Water | European Commission, JRC | 1984â€“2021 | permanent water | free use with attribution |
| HAPEM-MS3 activity data | U.S. Environmental Protection Agency | | shares of outdoor micro-environments | public domain (U.S. Government work) |
| National time-use surveys and travel diaries | national statistical agencies and transport authorities | survey-specific years | hourly location shares (aggregates only) | provider terms; microdata not redistributed |
| Global time-use compilation (average days by country) | compiled by the authors from published tables | | hourly location shares of countries without day-type data | aggregates available on request |
| Census and mobility-based commuting data | national agencies and data providers | source-specific | calibration of distance-decay kernels | provider terms; not redistributed |
| Natural Earth | Natural Earth | 1:50m land | base map | public domain |

## Restricted data (not in this repository)

- China: a commercial national POI data set (work destinations) and Amap web services (POIs and areas of interest,
  building use and land use). Authorised AOI inputs can be prepared with Stage 2 program 10; the restricted input data are not included. Without them, Chinese cities fall back to the Overture and OpenStreetMap layers.
- The mobile-network, smartphone and signalling observations used for validation (licensed by their providers).

## Licence of the example layers and outputs

The code is released under the licence in `LICENSE`. The data of the worked example (`01_inputs/`,
`04_intermediate/`, `05_outputs/`) are layers derived from third-party data sets and keep their terms:

- **GlobalBuildingAtlas** (Zhu, X. X. et al. GlobalBuildingAtlas: an open global and complete dataset of building
  polygons, heights and LoD1 3D models. *Earth Syst. Sci. Data* 17, 6647â€“6668 (2025);
  https://doi.org/10.14459/2025mp1782307) is licensed under **CC BY-NC 4.0**. The original GBA subsets (`01_inputs/demo/raw/<city>/buildings/globalbuildingatlas_buildings.parquet`), the GBA grid aggregates (`04_intermediate/demo/stage_2/buildings/gba`), and the floor-area and building layers of
  the example (`04_intermediate/demo/stage_2/buildings/gba_cells`, `04_intermediate/demo/stage_2/buildings/floor_area_by_use`) and every product derived from
  them (`05_outputs/demo/population_components`, `05_outputs/demo/hourly_population`, `05_outputs/demo/functional_land_use`) are therefore provided for
  **non-commercial use only**, with attribution to GlobalBuildingAtlas and to this work
  (https://creativecommons.org/licenses/by-nc/4.0/).
- Layers derived from **Overture Maps** and **OpenStreetMap** (buildings, land use, water, transportation, places)
  are subject to the Open Database License 1.0 (ODbL) or, for Overture places, the CDLA-Permissive 2.0, as stated by
  their providers.
- Layers derived from **GHSL** (European Commission, Joint Research Centre) and **ESA WorldCover** are licensed under
  CC BY 4.0; the **JRC Global Surface Water** data set is free to use with attribution.

Public time-use tables retain their provider terms: Japan Statistics Bureau published tables (source attribution; PDL/CC BY-compatible terms), Eurostat statistical tables (reuse with acknowledgement), World Bank WDI observations (provider attribution), and the EPA HAPEM-MS3 report. The EXPOLIS CSV is a labelled transcription of published numerical results, not participant records. Survey microdata and restricted calibration observations are not redistributed.

Please cite the original data sets (see `06_docs/methods/data_sources.md`) together with this work.
