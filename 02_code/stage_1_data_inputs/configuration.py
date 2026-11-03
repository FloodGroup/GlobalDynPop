"""Folders and fixed settings of GlobalDynPop-100m.

The package has one folder per role (README.md in the package root):

  04_intermediate/demo/stage_2/        inputs of the model, prepared from the downloaded sources (running the model needs no download)
  02_code/          model library and named processing programs
  03_run/           Windows command files, one per step
  04_intermediate/  files written while the model runs: network layers, component layers, logs, caches
  05_outputs/       hourly population of every city on a workday and on a weekend day
  06_docs/          documents

Optional validation or restricted observation trees are not shipped. Point DYNAMIC_POPULATION_VALIDATION / DYNAMIC_POPULATION_RESTRICTED
at your own folders when needed. Data that may not be published use names ending in _NOT_PUBLIC.
Every folder can be moved with an environment variable: DYNAMIC_POPULATION_ROOT for the whole package; DYNAMIC_POPULATION_STAGE2, DYNAMIC_POPULATION_WORK,
DYNAMIC_POPULATION_OUTPUTS, DYNAMIC_POPULATION_VALIDATION, DYNAMIC_POPULATION_RESULTS, DYNAMIC_POPULATION_RESTRICTED and DYNAMIC_POPULATION_INPUTS_RESTRICTED for single folders
(03_run/environment.cmd)."""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v) if v else Path(default)


# ------------------------------------------------------------------------------------------------ package
ROOT = _env("DYNAMIC_POPULATION_ROOT", Path(__file__).resolve().parents[2])
CODE = ROOT / "02_code"
RAW_INPUTS = _env("DYNAMIC_POPULATION_RAW_INPUTS", ROOT / "01_inputs" / "demo" / "raw")
INPUTS = _env("DYNAMIC_POPULATION_STAGE2", ROOT / "04_intermediate" / "demo" / "stage_2")
RUN = ROOT / "03_run"
WORK = _env("DYNAMIC_POPULATION_WORK", ROOT / "04_intermediate" / "demo")
OUTPUTS = _env("DYNAMIC_POPULATION_OUTPUTS", ROOT / "05_outputs" / "demo")
DOCS = ROOT / "06_docs"
VALIDATION = _env("DYNAMIC_POPULATION_VALIDATION", ROOT / "validation")  # optional external tree; not shipped

# ------------------------------------------------------------------------------------------------ 01_inputs
CITIES_DIR = INPUTS / "local_grids"                       # city table and GHS Urban Centre Database
CITY_TABLE = CITIES_DIR / "city_grid_definitions.csv"
UCDB = _env("DYNAMIC_POPULATION_UCDB", RAW_INPUTS / "GHS_UCDB_GLOBE_R2024A.gpkg")
UCDB_LAYER = "GHSL_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A"
# GHSL R2023A on the 100 m grid of every city (02_prepare_settlement_layers.py): residents (static population), built volume
# (total and non-residential) and building height
GHSL = {"pop": INPUTS / "resident_population",
        "vol": INPUTS / "buildings" / "total_building_volume",
        "vol_nres": INPUTS / "buildings" / "non_residential_building_volume",
        "height": INPUTS / "buildings" / "building_height"}
FLOOR_AREA = INPUTS / "buildings" / "floor_area_by_use"     # floor area by use (04_prepare_building_floor_area.py)
POI_OVERTURE = INPUTS / "point_of_interest_counts" / "overture"           # Overture Maps places by class (03_prepare_destination_counts.py)
POI_OSM = INPUTS / "point_of_interest_counts" / "openstreetmap"           # OpenStreetMap POIs by class
POI_CHINA = INPUTS / "point_of_interest_counts" / "china"                 # China POI counts and Amap POIs
CNPOI_INFO = POI_CHINA / "coverage"                  # coverage of the China POI data (counts per city)
ROAD_GRAPHS = _env("DYNAMIC_POPULATION_ROAD_GRAPHS", INPUTS / "road_and_rail_graphs")   # road and rail network of every city (05_prepare_transport_graphs.py)
TIMEUSE = INPUTS / "time_use"                        # hourly activity-location shares and their sources
PARAMS = INPUTS / "allocation_parameters"                       # model parameters
WATER_COVERAGE_PERCENT = INPUTS / "water_coverage_percent"  # uint8 water coverage, 0-100 percent, on each city grid
# inputs that may not be published: raw China POI data, Amap exports, time-use package V10
INPUTS_RESTRICTED = _env("DYNAMIC_POPULATION_INPUTS_RESTRICTED", INPUTS / "restricted_NOT_PUBLIC")
CN_POI_RAW = _env("DYNAMIC_POPULATION_CN_POI", INPUTS_RESTRICTED / "CN_POI")
AMAP_EXPORT = _env("DYNAMIC_POPULATION_AMAP_EXPORT", INPUTS_RESTRICTED / "amap_export_model")
CNPOI_COMPACT = INPUTS_RESTRICTED / "cn_poi_compact"   # compact copy of the raw China POIs
AOI_AMAP = INPUTS_RESTRICTED / "aoi_amap"            # Amap areas of interest by city
TIMEUSE_V10 = _env("DYNAMIC_POPULATION_V10", INPUTS_RESTRICTED / "time_use_V10")

# hourly activity-location shares read by the model: hourly_location_shares; DYNAMIC_POPULATION_DAYTYPE selects
# another input folder with the same location-share schema
DAYTYPE_DIR = INPUTS / os.environ.get("DYNAMIC_POPULATION_DAYTYPE", "hourly_location_shares")
# the model parameters (04_intermediate/demo/stage_2/allocation_parameters/population_allocation_parameters.json)
MODEL_PARAMS = _env("DYNAMIC_POPULATION_PARAMS", PARAMS / "population_allocation_parameters.json")

# ------------------------------------------------------------------------------------------------ 04_intermediate
NETWORK = _env("DYNAMIC_POPULATION_NETWORK", WORK / "stage_3" / "in_transit_population")      # people in transit on the network (02_calculate_in_transit_population.py)
COMPONENTS = _env("DYNAMIC_POPULATION_COMPONENTS", OUTPUTS / "population_components")   # component layers of every city (03_calculate_population_components.py)
CACHE = _env("DYNAMIC_POPULATION_CACHE", WORK / "stage_2" / "cache")            # downloaded tiles and other caches (deletable)
LOGS = WORK / "stage_3" / "logs"
OSM_WORK = INPUTS / "openstreetmap_work"                              # POIs read from the OpenStreetMap planet file

# ------------------------------------------------------------------------------------------------ 05_outputs
HOURLY = _env("DYNAMIC_POPULATION_HOURLY", OUTPUTS / "hourly_population")
DAYTYPE_NAMES = {"workday": "workday", "restday": "rest_day"}   # file names of the outputs by model day type

# ------------------------------------------------------------------------------------------------ optional validation (external)
CITY_SPLIT = VALIDATION / "city_split" / "city_split.csv"      # calibration and validation cities
CALIB = VALIDATION / "calibration"                   # parameter choices on the calibration cities
CALIB_OD = _env("DYNAMIC_POPULATION_CALIB_OD", CALIB / "od_kernel_grids")   # commuting-flow kernel grids of all cities (calibration programs)
RESULTS = _env("DYNAMIC_POPULATION_RESULTS", VALIDATION / "results")   # metric tables of the evaluation programs
OBS = VALIDATION / "observations_NOT_PUBLIC" / "processed"     # observations, prepared
OBS_RAW = VALIDATION / "observations_NOT_PUBLIC" / "raw"       # observations as downloaded
# restricted mobile-network data (Zhengzhou and Shenzhen signalling, Shanghai home-work matrix): only metrics are written
RESTRICTED = _env("DYNAMIC_POPULATION_RESTRICTED", VALIDATION / "restricted_NOT_PUBLIC")
CN_SIGNALLING = RESTRICTED / "CN_Zhengzhou_Shenzhen_signalling" / "Fw__7_1_410100,440300"
SH_HOME_WORK = RESTRICTED / "CN_Shanghai_home_work" / "6-310000-home_to_work-202411.csv"

# ------------------------------------------------------------------------------------------------ settings
POP_MIN = 300_000          # urban centres with at least this 2025 population (UN WUP threshold)
BUFFER_M = 10_000          # model domain = bounding box of the urban centre + this margin
CELL = 100.0               # model resolution (m)

GHSL_FTP = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL"
GHSL_PRODUCTS = {
    # key: (folder, product name); 100 m Mollweide (ESRI:54009) tiles of the R2023A release
    "pop": ("GHS_POP_GLOBE_R2023A", "GHS_POP_E2025_GLOBE_R2023A_54009_100"),
    "vol": ("GHS_BUILT_V_GLOBE_R2023A", "GHS_BUILT_V_E2025_GLOBE_R2023A_54009_100"),
    "vol_nres": ("GHS_BUILT_V_GLOBE_R2023A", "GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_54009_100"),
    # average net building height (m), 2018 epoch; sampled (not summed) onto the city grid
    "height": ("GHS_BUILT_H_GLOBE_R2023A", "GHS_BUILT_H_ANBH_E2018_GLOBE_R2023A_54009_100"),
}
SAMPLED_PRODUCTS = {"height"}
MOLLWEIDE = "ESRI:54009"

OVERTURE_RELEASE = "2026-10-21.0"
OVERTURE_BUCKET = "overturemaps-us-west-2/release"


def ghsl_file(product: str, stem: str) -> Path:
    """GHSL layer of a city on its 100 m grid (float32 .npy)."""
    return GHSL[product] / f"{stem}.npy"

STAGE3 = _env("DYNAMIC_POPULATION_STAGE3", WORK / "stage_3")
DESTINATION_POPULATION = STAGE3 / "destination_population"
