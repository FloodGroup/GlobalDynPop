@echo off
call "%~dp0..\environment.cmd"
"%DYNAMIC_POPULATION_PYTHON%" "%~dp0..\run_city_demo.py" run --stage 1 %*
exit /b %errorlevel%
