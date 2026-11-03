@echo off
call "%~dp0..\environment.cmd"
cd /d "%DYNAMIC_POPULATION_ROOT%"
"%DYNAMIC_POPULATION_PYTHON%" 02_code\stage_1_data_inputs\01_prepare_raw_sources.py %*
exit /b %errorlevel%
