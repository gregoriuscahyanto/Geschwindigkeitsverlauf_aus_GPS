[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Requirements = Join-Path $RepoRoot "requirements.txt"
$Wheelhouse = Join-Path $RepoRoot "wheelhouse"

if (-not (Test-Path $Requirements)) {
    throw "requirements.txt wurde nicht gefunden: $Requirements"
}

if ($env:OS -ne "Windows_NT") {
    throw "Das Offline-Wheelhouse muss auf Windows erstellt werden, damit Windows-x64-Wheels heruntergeladen werden."
}

$BuilderPython = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $BuilderPython = (& py -3.11 -c "import sys; print(sys.executable)") | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { $BuilderPython = $null }
}
if (-not $BuilderPython -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $BuilderPython = (& python -c "import sys; print(sys.executable)") | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { $BuilderPython = $null }
}
if (-not $BuilderPython) {
    throw "Python 3.11 wurde nicht gefunden."
}
$BuilderPython = $BuilderPython.Trim()

& $BuilderPython -c "import struct,sys; assert sys.platform.startswith('win'); assert sys.version_info[:2] == (3,11), sys.version; assert struct.calcsize('P') * 8 == 64, '32-bit Python'; print('Builder:', sys.version.split()[0], 'Windows x64', sys.executable)"
if ($LASTEXITCODE -ne 0) {
    throw "Für das Offline-Paket wird Python 3.11 64 Bit unter Windows benötigt."
}

& $BuilderPython -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    & $BuilderPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "pip konnte auf dem Vorbereitungsrechner nicht bereitgestellt werden."
    }
}

if (Test-Path $Wheelhouse) {
    Write-Host "Entferne vorhandenes wheelhouse, damit keine veralteten Pakete übrig bleiben ..."
    Remove-Item -Recurse -Force $Wheelhouse
}
New-Item -ItemType Directory -Force -Path $Wheelhouse | Out-Null

Write-Host "Lade alle Python-Abhängigkeiten einschließlich Unterabhängigkeiten als Wheels ..."
& $BuilderPython -m pip download --only-binary=:all: --dest $Wheelhouse -r $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Das Offline-Wheelhouse konnte nicht vollständig erzeugt werden. Mindestens eine Abhängigkeit ist für Python 3.11/Windows x64 nicht als Wheel verfügbar oder der Paketindex ist nicht erreichbar."
}

$Wheels = @(Get-ChildItem -Path $Wheelhouse -Filter "*.whl" -File | Sort-Object Name)
if ($Wheels.Count -eq 0) {
    throw "Es wurden keine Wheel-Dateien erzeugt."
}

$RequirementsHash = (Get-FileHash -Algorithm SHA256 $Requirements).Hash
$Manifest = @(
    "GPS-Routenplaner Offline-Wheelhouse",
    "Erzeugt: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')",
    "Ziel: Windows x64 / Python 3.11",
    "requirements.txt SHA256: $RequirementsHash",
    "Anzahl Wheels: $($Wheels.Count)",
    "",
    "Enthaltene Dateien:"
) + @($Wheels | ForEach-Object { $_.Name })
$Manifest | Set-Content -Path (Join-Path $Wheelhouse "MANIFEST.txt") -Encoding UTF8

Write-Host ""
Write-Host "Offline-Paket vorbereitet."
Write-Host "Wheelhouse: $Wheelhouse"
Write-Host "Wheels: $($Wheels.Count)"
Write-Host ""
Write-Host "Für den Enterprise-PC den Projektordner inklusive wheelhouse kopieren."
Write-Host "Dort genügt anschließend: .\scripts\setup_windows.ps1"
