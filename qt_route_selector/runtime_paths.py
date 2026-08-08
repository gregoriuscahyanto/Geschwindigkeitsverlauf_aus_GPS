from __future__ import annotations

import os
from pathlib import Path

APP_FOLDER = "GPS-Routenplaner"
ENV_RUNTIME_HOME = "GPS_ROUTENPLANER_HOME"


def runtime_root(*, create: bool = True) -> Path:
    """Return the per-user application data directory.

    The location can be overridden with ``GPS_ROUTENPLANER_HOME``. On Windows
    the default is ``%LOCALAPPDATA%\\GPS-Routenplaner``; on other platforms the
    XDG data directory (or ``~/.local/share``) is used.
    """
    override = os.environ.get(ENV_RUNTIME_HOME, "").strip()
    if override:
        root = Path(override).expanduser()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", "").strip()
        root = (Path(base) if base else Path.home() / "AppData" / "Local") / APP_FOLDER
    else:
        base = os.environ.get("XDG_DATA_HOME", "").strip()
        root = (Path(base).expanduser() if base else Path.home() / ".local" / "share") / "gps-routenplaner"

    root = root.resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def data_dir(*, create: bool = True) -> Path:
    path = runtime_root(create=create) / "data"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir(*, create: bool = True) -> Path:
    path = runtime_root(create=create) / "state"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir(*, create: bool = True) -> Path:
    path = runtime_root(create=create) / "exports"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def route_result_path() -> Path:
    return state_dir() / "route_result.json"


def selected_region_path() -> Path:
    return state_dir() / "selected_region.json"


def prepare_runtime_directories() -> dict[str, Path]:
    return {
        "root": runtime_root(),
        "data": data_dir(),
        "state": state_dir(),
        "exports": exports_dir(),
    }
