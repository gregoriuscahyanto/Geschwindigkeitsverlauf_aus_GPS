[CmdletBinding()]
param(
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = if ($env:GPS_ROUTENPLANER_HOME) {
    $env:GPS_ROUTENPLANER_HOME
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "GPS-Routenplaner"
} else {
    Join-Path $HOME "AppData\Local\GPS-Routenplaner"
}
$VenvRoot = Join-Path $RuntimeRoot "venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "state") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "exports") | Out-Null

if (-not (Test-Path $PythonExe)) {
    Write-Host "Erstelle Python-Umgebung außerhalb des Repositories: $VenvRoot"
    & py -3.11 -m venv $VenvRoot
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $RepoRoot "requirements.txt")

Write-Host ""
Write-Host "Installation fertig."
Write-Host "Runtime-Daten: $RuntimeRoot"
Write-Host "Start: & `"$PythonExe`" -m qt_route_selector"

if ($Run) {
    Push-Location $RepoRoot
    try {
        & $PythonExe -m qt_route_selector
    } finally {
        Pop-Location
    }
}
