[CmdletBinding()]
param(
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvRoot = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
$RuntimeRoot = if ($env:GPS_ROUTENPLANER_HOME) {
    $env:GPS_ROUTENPLANER_HOME
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "GPS-Routenplaner"
} else {
    Join-Path $HOME "AppData\Local\GPS-Routenplaner"
}

# Keep large/generated application data outside the source checkout.
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "state") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "exports") | Out-Null

if (-not (Test-Path $PythonExe)) {
    Write-Host "Erstelle lokale VS-Code-Umgebung: $VenvRoot"
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -m venv $VenvRoot
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $VenvRoot
    } else {
        throw "Python 3.11 wurde nicht gefunden. Bitte Python 3.11 installieren bzw. durch die IT bereitstellen lassen."
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $PythonExe)) {
        throw "Die virtuelle Umgebung konnte nicht erstellt werden."
    }
}

Write-Host "Installiere/aktualisiere Abhängigkeiten ..."
& $PythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip konnte nicht aktualisiert werden." }
& $PythonExe -m pip install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Die Python-Abhängigkeiten konnten nicht installiert werden." }

# Fail early if a core runtime dependency is missing. This gives a clearer
# setup error than discovering it later when the simulation tab is opened.
& $PythonExe -c "import PySide6, pyqtgraph, numpy, pandas, geopandas, rasterio; print('Python-Umgebung OK')"
if ($LASTEXITCODE -ne 0) { throw "Die Python-Umgebung ist unvollständig." }

Write-Host ""
Write-Host "Installation fertig."
Write-Host "VS-Code-Interpreter: $PythonExe"
Write-Host "Runtime-Daten: $RuntimeRoot"
Write-Host "Start nach Aktivierung: python -m qt_route_selector"
Write-Host "Direktstart: & `"$PythonExe`" -m qt_route_selector"

if ($Run) {
    Push-Location $RepoRoot
    try {
        & $PythonExe -m qt_route_selector
    } finally {
        Pop-Location
    }
}
