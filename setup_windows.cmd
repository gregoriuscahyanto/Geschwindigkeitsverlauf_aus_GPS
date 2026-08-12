@echo off
setlocal

set "SCRIPT=%~dp0scripts\setup_windows.ps1"
if not exist "%SCRIPT%" (
    echo setup_windows.ps1 wurde nicht gefunden: %SCRIPT%
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
