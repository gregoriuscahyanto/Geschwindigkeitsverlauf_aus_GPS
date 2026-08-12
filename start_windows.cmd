@echo off
setlocal

set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto run

if defined LOCALAPPDATA (
    set "PY=%LOCALAPPDATA%\GPSRP\venv\Scripts\python.exe"
)
if exist "%PY%" goto run

echo Keine eingerichtete Python-Umgebung gefunden.
echo Bitte zuerst setup_windows.cmd ausfuehren.
exit /b 1

:run
pushd "%~dp0"
"%PY%" -m qt_route_selector
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
