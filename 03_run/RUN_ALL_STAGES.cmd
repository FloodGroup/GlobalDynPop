@echo off
call "%~dp0environment.cmd"
cd /d "%DYNAMIC_POPULATION_ROOT%"
"%DYNAMIC_POPULATION_PYTHON%" 03_run\run_city_demo.py run
exit /b %errorlevel%
