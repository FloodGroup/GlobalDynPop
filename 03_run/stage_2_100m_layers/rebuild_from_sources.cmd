@echo off
rem Stage 2 source rebuild (requires external source access and study inputs):
rem city table, GHSL layers, Overture places, floor area, road networks, water. OpenStreetMap / China POI rebuild scripts are not in this slim package.
rem The delivered inputs were made with Overture Maps release 2026-10-21.0, which Overture keeps for about 60 days;
rem with a later release the inputs (and the results) differ slightly.
call "%~dp0..\environment.cmd"
cd /d "%DYNAMIC_POPULATION_ROOT%"
"%DYNAMIC_POPULATION_PYTHON%" 02_code\stage_2_100m_layers\01_create_city_grids.py --global-sources --pop-min 300000 --buffer-km 10 || exit /b 1
"%DYNAMIC_POPULATION_PYTHON%" 02_code\stage_2_100m_layers\02_prepare_settlement_layers.py --global-sources --products pop vol vol_nres height || exit /b 1
"%DYNAMIC_POPULATION_PYTHON%" 02_code\stage_2_100m_layers\03_prepare_destination_counts.py --global-sources || exit /b 1
"%DYNAMIC_POPULATION_PYTHON%" 02_code\stage_2_100m_layers\04_prepare_building_floor_area.py --global-sources --order small || exit /b 1
"%DYNAMIC_POPULATION_PYTHON%" 02_code\stage_2_100m_layers\05_prepare_transport_graphs.py --global-sources --order small || exit /b 1
rem Water coverage percentages: prepare under 04_intermediate/demo/stage_2/water_coverage_percent separately if needed for land use.
