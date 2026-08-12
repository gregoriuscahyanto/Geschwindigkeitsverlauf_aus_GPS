@echo off
setlocal

set "SCRIPT=%~dp0scripts\build_offline_dependencies.ps1"
if not exist "%SCRIPT%" (
    echo build_offline_dependencies.ps1 wurde nicht gefunden: %SCRIPT%
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
