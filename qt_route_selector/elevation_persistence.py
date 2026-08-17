from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


ELEVATION_METADATA_KEY = "elevation"
COPERNICUS_DIRECTORY = "copernicus-glo30"
AUSTRIA_DIRECTORY = "austria-dgm10"


def _usable_dem_path(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() in {".tif", ".tiff"} and path.stat().st_size > 0
    if path.is_dir():
        return any(
            candidate.is_file() and candidate.stat().st_size > 0
            for pattern in ("*.tif", "*.tiff")
            for candidate in path.rglob(pattern)
        )
    return False


def _resolve_stored_path(value: object, *, data_root: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = data_root / candidate
    candidate = candidate.resolve()
    return candidate if _usable_dem_path(candidate) else None


def route_elevation_source(route_path: str | Path, data_root: str | Path) -> Path | None:
    """Return the elevation source embedded in one route project, if still available."""

    project = Path(route_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve()
    if not project.is_file():
        return None
    try:
        document = json.loads(project.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None

    metadata = document.get("metadata")
    elevation = metadata.get(ELEVATION_METADATA_KEY) if isinstance(metadata, Mapping) else None
    if isinstance(elevation, Mapping):
        for key in ("relative_path", "dem_file"):
            resolved = _resolve_stored_path(elevation.get(key), data_root=root)
            if resolved is not None:
                return resolved

    # Routes saved with the route-bound simulation settings may already contain
    # a DEM path even if they predate metadata.elevation.
    setup = document.get("simulation_setup")
    if isinstance(setup, Mapping):
        resolved = _resolve_stored_path(setup.get("dem_path"), data_root=root)
        if resolved is not None:
            return resolved
    return None


def local_elevation_fallback(
    data_root: str | Path,
    *,
    dataset_key: str = "",
) -> Path | None:
    """Find locally copied DEM files for older route JSONs without elevation metadata."""

    root = Path(data_root).expanduser().resolve()
    elevation_root = root / "elevation"
    if not elevation_root.is_dir():
        return None

    # Austria has a dedicated higher-resolution DEM. All other automatic/local
    # datasets use the Copernicus tile directory.
    if str(dataset_key).strip().lower() == "austria":
        austria = elevation_root / AUSTRIA_DIRECTORY
        if _usable_dem_path(austria):
            candidates = sorted(austria.rglob("*.tif")) + sorted(austria.rglob("*.tiff"))
            if candidates:
                return max(candidates, key=lambda path: path.stat().st_size).resolve()

    copernicus = elevation_root / COPERNICUS_DIRECTORY
    if _usable_dem_path(copernicus):
        return copernicus.resolve()

    # Last fallback for installations that only contain the Austria DEM.
    austria = elevation_root / AUSTRIA_DIRECTORY
    if _usable_dem_path(austria):
        candidates = sorted(austria.rglob("*.tif")) + sorted(austria.rglob("*.tiff"))
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_size).resolve()
    return None


def resolve_elevation_source(
    route_path: str | Path,
    data_root: str | Path,
    *,
    dataset_key: str = "",
) -> Path | None:
    """Resolve route-specific elevation first, then support legacy route files."""

    embedded = route_elevation_source(route_path, data_root)
    if embedded is not None:
        return embedded
    return local_elevation_fallback(data_root, dataset_key=dataset_key)


def save_route_elevation_source(
    route_path: str | Path,
    data_root: str | Path,
    dem_file: str | Path,
    *,
    provider: str = "",
    tile_count: int = 0,
) -> Path:
    """Persist the DEM reference into the same timestamped route project JSON."""

    project = Path(route_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve()
    dem = Path(dem_file).expanduser().resolve()
    if not project.is_file():
        raise FileNotFoundError(project)
    if not _usable_dem_path(dem):
        raise FileNotFoundError(f"Höhenmodell nicht gefunden oder leer: {dem}")

    document = json.loads(project.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Die Routendatei enthält kein JSON-Objekt.")
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        document["metadata"] = metadata

    relative_path = ""
    try:
        relative_path = str(dem.relative_to(root))
    except ValueError:
        pass

    metadata[ELEVATION_METADATA_KEY] = {
        "dem_file": str(dem),
        "relative_path": relative_path,
        "provider": str(provider or ""),
        "tile_count": max(0, int(tile_count)),
    }

    temporary = project.with_name(project.name + ".elevation.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, project)
    return project


__all__ = [
    "ELEVATION_METADATA_KEY",
    "local_elevation_fallback",
    "resolve_elevation_source",
    "route_elevation_source",
    "save_route_elevation_source",
]
