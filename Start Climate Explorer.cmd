@echo off
setlocal
cd /d "%~dp0"
set "CLIMATE_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CLIMATE_PYTHON%" (
  "%CLIMATE_PYTHON%" -B -m anm_climate.explorer_server --open-browser %*
) else (
  python -B -m anm_climate.explorer_server --open-browser %*
)
if errorlevel 1 pause
