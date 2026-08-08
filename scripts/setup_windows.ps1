[CmdletBinding()]
param(
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvRoot = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
$Requirements = Join-Path $RepoRoot "requirements.txt"
$Wheelhouse = Join-Path $RepoRoot "wheelhouse"
$RuntimeRoot = if ($env:GPS_ROUTENPLANER_HOME) {
    $env:GPS_ROUTENPLANER_HOME
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "GPS-Routenplaner"
} else {
    Join-Path $HOME "AppData\Local\GPS-Routenplaner"
}

if (-not (Test-Path $Requirements)) {
    throw "requirements.txt wurde nicht gefunden: $Requirements"
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

# A normal Python venv already contains pip. If a restricted Python build did
# not create it, try the standard-library bootstrap without contacting PyPI.
& $PythonExe -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip fehlt in der virtuellen Umgebung; versuche lokalen ensurepip-Bootstrap ..."
    & $PythonExe -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "pip konnte in der virtuellen Umgebung nicht bereitgestellt werden. Die verwendete Python-Installation muss venv/ensurepip unterstützen."
    }
}

$OfflineWheels = @()
if (Test-Path $Wheelhouse) {
    $OfflineWheels = @(Get-ChildItem -Path $Wheelhouse -Filter "*.whl" -File -ErrorAction SilentlyContinue)
}

if ($OfflineWheels.Count -gt 0) {
    Write-Host "Offline-Wheelhouse erkannt ($($OfflineWheels.Count) Pakete)."
    Write-Host "Installiere Abhängigkeiten ausschließlich lokal; PyPI wird nicht verwendet ..."
    & $PythonExe -m pip install --no-index --find-links $Wheelhouse -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Die Offline-Installation ist fehlgeschlagen. Das wheelhouse ist vermutlich unvollständig oder passt nicht zu Python 3.11/Windows x64. Auf einem Internet-PC .\scripts\build_offline_dependencies.ps1 neu ausführen."
    }
    $InstallMode = "offline aus $Wheelhouse"
} else {
    Write-Host "Kein lokales wheelhouse gefunden. Installiere Abhängigkeiten über den konfigurierten Python-Paketindex ..."
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip konnte nicht aktualisiert werden." }
    & $PythonExe -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Die Python-Abhängigkeiten konnten nicht installiert werden. Wenn PyPI im Unternehmensnetz gesperrt ist, auf einem Internet-PC zuerst .\scripts\build_offline_dependencies.ps1 ausführen und den erzeugten wheelhouse-Ordner mitkopieren."
    }
    $InstallMode = "online über den konfigurierten Paketindex"
}

# Fail early if a core runtime dependency is missing. This gives a clearer
# setup error than discovering it later when the simulation tab is opened.
& $PythonExe -c "import PySide6, pyqtgraph, numpy, pandas, geopandas, rasterio; print('Python-Umgebung OK')"
if ($LASTEXITCODE -ne 0) { throw "Die Python-Umgebung ist unvollständig." }

Write-Host ""
Write-Host "Einrichtung fertig."
Write-Host "Abhängigkeiten: $InstallMode"
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
