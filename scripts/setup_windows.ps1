[CmdletBinding()]
param(
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
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

# PySide6 contains deeply nested Qt/QML files. On managed Windows machines the
# system-wide LongPathsEnabled policy is often disabled and cannot be changed by
# the user. In that case use a deliberately short per-user venv and TEMP path so
# installation works without registry changes or administrator rights.
$UseShortWindowsPaths = $false
if ($env:OS -eq "Windows_NT") {
    $LongPathsEnabled = 0
    try {
        $LongPathsEnabled = [int](Get-ItemPropertyValue `
            -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
            -Name "LongPathsEnabled" `
            -ErrorAction Stop)
    } catch {
        $LongPathsEnabled = 0
    }
    $UseShortWindowsPaths = ($LongPathsEnabled -ne 1)
}

if ($UseShortWindowsPaths) {
    $ShortBase = if ($env:LOCALAPPDATA) {
        Join-Path $env:LOCALAPPDATA "GPSRP"
    } else {
        Join-Path $HOME "GPSRP"
    }
    $VenvRoot = Join-Path $ShortBase "venv"
    $ShortTemp = Join-Path $ShortBase "tmp"
    $ShortPipCache = Join-Path $ShortBase "pip-cache"
    New-Item -ItemType Directory -Force -Path $ShortBase | Out-Null
    New-Item -ItemType Directory -Force -Path $ShortTemp | Out-Null
    New-Item -ItemType Directory -Force -Path $ShortPipCache | Out-Null
    $env:TEMP = $ShortTemp
    $env:TMP = $ShortTemp
    $env:PIP_CACHE_DIR = $ShortPipCache
    Write-Host "Windows Long Path Support ist nicht aktiviert."
    Write-Host "Verwende deshalb kurze Benutzerpfade (keine Adminrechte erforderlich)."
    Write-Host "Python-Umgebung: $VenvRoot"
} else {
    $VenvRoot = Join-Path $RepoRoot ".venv"
}

$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

if (-not (Test-Path $PythonExe)) {
    Write-Host "Erstelle Python-3.11-Umgebung: $VenvRoot"
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

# Reject a stale/pre-existing venv with the wrong ABI before pip sees the
# cp311/win_amd64 wheelhouse and reports a misleading 'versions: none'.
$PythonRuntime = (& $PythonExe -c "import struct,sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{struct.calcsize(chr(80))*8}')") | Select-Object -First 1
if ($LASTEXITCODE -ne 0 -or -not $PythonRuntime) {
    throw "Die Python-Version der virtuellen Umgebung konnte nicht geprüft werden: $PythonExe"
}
$PythonRuntime = $PythonRuntime.Trim()
if ($PythonRuntime -ne "3.11|64") {
    throw "Die vorhandene virtuelle Umgebung verwendet $PythonRuntime statt Python 3.11 64 Bit. Bitte den Ordner '$VenvRoot' löschen und setup_windows.cmd erneut starten."
}
Write-Host "Python geprüft: 3.11 64 Bit."

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

    $ManifestPath = Join-Path $Wheelhouse "MANIFEST.txt"
    if (-not (Test-Path $ManifestPath)) {
        throw "Das lokale wheelhouse besitzt keine MANIFEST.txt und kann deshalb nicht sicher geprüft werden. Auf einem Internet-PC build_offline_dependencies.cmd neu ausführen und den kompletten wheelhouse-Ordner erneut kopieren."
    }

    $ManifestText = Get-Content -Raw -Path $ManifestPath
    $CurrentRequirementsHash = (Get-FileHash -Algorithm SHA256 $Requirements).Hash.ToUpperInvariant()
    $HashMatch = [regex]::Match(
        $ManifestText,
        '(?im)^requirements\.txt SHA256:\s*([0-9a-f]{64})\s*$'
    )
    if (-not $HashMatch.Success) {
        throw "Die MANIFEST.txt im wheelhouse enthält keinen gültigen requirements.txt-Hash. Das wheelhouse bitte auf einem Internet-PC neu erzeugen."
    }

    $WheelhouseRequirementsHash = $HashMatch.Groups[1].Value.ToUpperInvariant()
    if ($WheelhouseRequirementsHash -ne $CurrentRequirementsHash) {
        throw "Das wheelhouse ist veraltet und passt nicht zur aktuellen requirements.txt. Auf einem Internet-PC build_offline_dependencies.cmd neu ausführen und den kompletten wheelhouse-Ordner erneut kopieren."
    }

    $CountMatch = [regex]::Match($ManifestText, '(?im)^Anzahl Wheels:\s*(\d+)\s*$')
    if ($CountMatch.Success) {
        $ExpectedWheelCount = [int]$CountMatch.Groups[1].Value
        if ($ExpectedWheelCount -ne $OfflineWheels.Count) {
            throw "Das wheelhouse ist unvollständig: MANIFEST.txt erwartet $ExpectedWheelCount Wheels, gefunden wurden $($OfflineWheels.Count). Den kompletten wheelhouse-Ordner erneut kopieren."
        }
    }

    $ManifestWheelNames = @(
        Get-Content -Path $ManifestPath |
            Where-Object { $_ -match '\.whl\s*$' } |
            ForEach-Object { $_.Trim() }
    )
    $MissingWheelNames = @(
        $ManifestWheelNames |
            Where-Object { -not (Test-Path (Join-Path $Wheelhouse $_)) }
    )
    if ($MissingWheelNames.Count -gt 0) {
        $Preview = ($MissingWheelNames | Select-Object -First 5) -join ', '
        throw "Das wheelhouse ist unvollständig. Fehlende Wheel-Datei(en): $Preview. Den kompletten wheelhouse-Ordner erneut kopieren."
    }

    Write-Host "Wheelhouse passt zur aktuellen requirements.txt."
    Write-Host "Installiere Abhängigkeiten ausschließlich lokal; PyPI wird nicht verwendet ..."
    & $PythonExe -m pip install --no-cache-dir --no-index --find-links $Wheelhouse -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Die Offline-Installation ist fehlgeschlagen. Falls Windows einen Pfadlängenfehler meldet, setup_windows.cmd aus dem aktuellen Repository verwenden. Andernfalls das wheelhouse auf dem Internet-PC neu erzeugen."
    }
    $InstallMode = "offline aus $Wheelhouse"
} else {
    Write-Host "Kein lokales wheelhouse gefunden. Installiere Abhängigkeiten über den konfigurierten Python-Paketindex ..."
    & $PythonExe -m pip install --no-cache-dir --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip konnte nicht aktualisiert werden." }
    & $PythonExe -m pip install --no-cache-dir -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Die Python-Abhängigkeiten konnten nicht installiert werden. Wenn PyPI im Unternehmensnetz gesperrt ist, auf einem Internet-PC zuerst build_offline_dependencies.cmd ausführen und den erzeugten wheelhouse-Ordner mitkopieren."
    }
    $InstallMode = "online über den konfigurierten Paketindex"
}

# Fail early if a core runtime dependency is missing. This gives a clearer
# setup error than discovering it later when the simulation tab is opened.
& $PythonExe -c "import PySide6, pyqtgraph, numpy, scipy, pandas, geopandas, rasterio; print('Python-Umgebung OK')"
if ($LASTEXITCODE -ne 0) { throw "Die Python-Umgebung ist unvollständig." }

Write-Host ""
Write-Host "Einrichtung fertig."
Write-Host "Abhängigkeiten: $InstallMode"
Write-Host "Python-Interpreter: $PythonExe"
Write-Host "Runtime-Daten: $RuntimeRoot"
Write-Host "Start: .\start_windows.cmd"

if ($Run) {
    Push-Location $RepoRoot
    try {
        & $PythonExe -m qt_route_selector
    } finally {
        Pop-Location
    }
}
