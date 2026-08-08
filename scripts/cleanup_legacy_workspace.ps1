[CmdletBinding(SupportsShouldProcess=$true)]
param()

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

if (-not $WhatIfPreference) {
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $RuntimeState | Out-Null
}

function Move-ToBackup([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    $Name = Split-Path -Leaf $Path
    $Destination = Join-Path $BackupRoot $Name
    if ($PSCmdlet.ShouldProcess($Path, "nach $Destination verschieben")) {
        if (-not (Test-Path $BackupRoot)) {
            New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
        }
        Move-Item -Path $Path -Destination $Destination
    }
}

# Preserve already downloaded OSM/DEM data by moving the complete legacy data
# directory into the per-user runtime location when that location is empty.
$LegacyData = Join-Path $RepoRoot "data"
if (Test-Path $LegacyData) {
    if (-not (Test-Path $RuntimeData)) {
        if ($PSCmdlet.ShouldProcess($LegacyData, "nach $RuntimeData verschieben")) {
            New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
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
            New-Item -ItemType Directory -Force -Path $RuntimeState | Out-Null
            Move-Item -Path $Source -Destination $Destination
        }
    } else {
        Move-ToBackup $Source
    }
}

# Retired prototype directories are archived instead of deleted. The local
# .venv is intentionally NOT touched: it is the standard VS Code environment.
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

Write-Host ""
Write-Host "Workspace-Bereinigung abgeschlossen."
Write-Host "Runtime-Daten: $RuntimeRoot"
Write-Host "Lokale Python-Umgebung: $(Join-Path $RepoRoot '.venv') (bleibt erhalten)"
if (Test-Path $BackupRoot) {
    Write-Host "Legacy-Backup: $BackupRoot"
}
