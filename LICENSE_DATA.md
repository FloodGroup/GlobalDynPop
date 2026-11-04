# Licence of the data in this repository

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
