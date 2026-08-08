[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [switch]$RemoveVenv
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RepoParent = Split-Path -Parent $RepoRoot
$RuntimeRoot = if ($env:GPS_ROUTENPLANER_HOME) {
    $env:GPS_ROUTENPLANER_HOME
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "GPS-Routenplaner"
} else {
    Join-Path $HOME "AppData\Local\GPS-Routenplaner"
}
$RuntimeData = Join-Path $RuntimeRoot "data"
$RuntimeState = Join-Path $RuntimeRoot "state"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path $RepoParent ("Geschwindigkeitsverlauf_legacy_" + $Stamp)

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $RuntimeState | Out-Null

function Move-ToBackup([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    if (-not (Test-Path $BackupRoot)) {
        New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
    }
    $Name = Split-Path -Leaf $Path
    $Destination = Join-Path $BackupRoot $Name
    if ($PSCmdlet.ShouldProcess($Path, "nach $Destination verschieben")) {
        Move-Item -Path $Path -Destination $Destination
    }
}

# Preserve already downloaded OSM/DEM data by moving the complete legacy data
# directory into the new per-user runtime location when that location is empty.
$LegacyData = Join-Path $RepoRoot "data"
if (Test-Path $LegacyData) {
    if (-not (Test-Path $RuntimeData)) {
        if ($PSCmdlet.ShouldProcess($LegacyData, "nach $RuntimeData verschieben")) {
            Move-Item -Path $LegacyData -Destination $RuntimeData
        }
    } elseif ((Get-ChildItem -Force $RuntimeData -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0) {
        if ($PSCmdlet.ShouldProcess($LegacyData, "in leeres $RuntimeData verschieben")) {
            Remove-Item -Force $RuntimeData
            Move-Item -Path $LegacyData -Destination $RuntimeData
        }
    } else {
        Write-Warning "Runtime-Daten existieren bereits. Das alte data-Verzeichnis wird sicherheitshalber archiviert."
        Move-ToBackup $LegacyData
    }
}

foreach ($Name in @("route_result.json", "selected_region.json")) {
    $Source = Join-Path $RepoRoot $Name
    if (-not (Test-Path $Source)) { continue }
    $Destination = Join-Path $RuntimeState $Name
    if (-not (Test-Path $Destination)) {
        if ($PSCmdlet.ShouldProcess($Source, "nach $Destination verschieben")) {
            Move-Item -Path $Source -Destination $Destination
        }
    } else {
        Move-ToBackup $Source
    }
}

# These directories belong to the retired prototype workflow. They are not
# deleted: existing local content is moved next to the repository as a dated
# backup so nothing valuable is lost.
foreach ($Name in @(
    "augmented",
    "database",
    "databaseSlim",
    "defaults",
    "results",
    "slprj",
    "tracks",
    "versions"
)) {
    Move-ToBackup (Join-Path $RepoRoot $Name)
}

$LegacyVenv = Join-Path $RepoRoot ".venv"
if ($RemoveVenv -and (Test-Path $LegacyVenv)) {
    $ExternalPython = Join-Path $RuntimeRoot "venv\Scripts\python.exe"
    if (-not (Test-Path $ExternalPython)) {
        throw "Externe Python-Umgebung fehlt. Zuerst .\scripts\setup_windows.ps1 ausführen."
    }
    if ($PSCmdlet.ShouldProcess($LegacyVenv, "alte Repo-.venv löschen")) {
        Remove-Item -Recurse -Force $LegacyVenv
    }
} elseif (Test-Path $LegacyVenv) {
    Write-Host "Hinweis: .venv bleibt erhalten. Für einen komplett sauberen Root nach setup_windows.ps1 erneut mit -RemoveVenv ausführen."
}

Write-Host ""
Write-Host "Workspace-Bereinigung abgeschlossen."
Write-Host "Runtime: $RuntimeRoot"
if (Test-Path $BackupRoot) {
    Write-Host "Legacy-Backup: $BackupRoot"
}
