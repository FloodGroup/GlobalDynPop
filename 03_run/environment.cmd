@echo off
rem Settings used by all steps. DYNAMIC_POPULATION_ROOT is this package (the folder above 03_run\).
set DYNAMIC_POPULATION_ROOT=%~dp0..
set PYTHONUTF8=1
rem Python of the environment of the package (environment.yml); change it if python is not on the PATH
if "%DYNAMIC_POPULATION_PYTHON%"=="" set DYNAMIC_POPULATION_PYTHON=python
rem Processes that share the cities of steps 2 to 4 (at below-normal priority; about half the logical processors),
rem of which DYNAMIC_POPULATION_LARGE_WORKERS start from the largest city; DYNAMIC_POPULATION_JOBS: validation programs run at the same time;
rem DYNAMIC_POPULATION_MEMWAIT_GB: a process starts a new city only when this much memory is free.
if "%DYNAMIC_POPULATION_WORKERS%"=="" set DYNAMIC_POPULATION_WORKERS=8
if "%DYNAMIC_POPULATION_LARGE_WORKERS%"=="" set DYNAMIC_POPULATION_LARGE_WORKERS=2
if "%DYNAMIC_POPULATION_JOBS%"=="" set DYNAMIC_POPULATION_JOBS=4
if "%DYNAMIC_POPULATION_MEMWAIT_GB%"=="" set DYNAMIC_POPULATION_MEMWAIT_GB=3
rem DYNAMIC_POPULATION_MIN_FREE_GB: while less memory than this is free, no process starts a new city (default 15 % of the memory)
rem   set DYNAMIC_POPULATION_MIN_FREE_GB=10
rem Optional: folders elsewhere (default: the folders of this package)
rem   set DYNAMIC_POPULATION_RESTRICTED=PATH_TO_AUTHORISED_OBSERVATIONS         restricted mobile-network data (set DYNAMIC_POPULATION_RESTRICTED to your authorised folder)
rem   set DYNAMIC_POPULATION_INPUTS_RESTRICTED=PATH_TO_AUTHORISED_INPUTS   raw China POI data and Amap exports (04_intermediate\demo\stage_2\restricted_NOT_PUBLIC)

rem   set DYNAMIC_POPULATION_STAGE1=PATH_TO_GRID_STAGE   city grid definitions (local_grids/city_grid_definitions.csv)
