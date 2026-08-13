from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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


def next_route_result_path(*, when: datetime | None = None) -> Path:
    """Return a new non-overwriting project filename based on local date/time."""

    directory = state_dir()
    stamp = (when or datetime.now().astimezone()).strftime("%Y%m%d_%H%M%S")
    base = directory / f"route_result_{stamp}.json"
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = directory / f"route_result_{stamp}_{counter:02d}.json"
        if not candidate.exists():
            return candidate
        counter += 1


def latest_route_result_path() -> Path:
    """Return the newest timestamped route project, with legacy fallback."""

    directory = state_dir()
    timestamped = [
        path
        for path in directory.glob("route_result_*.json")
        if path.is_file() and path.stat().st_size > 0
    ]
    if timestamped:
        return max(timestamped, key=lambda path: (path.stat().st_mtime_ns, path.name))
    legacy = directory / "route_result.json"
    return legacy


def route_result_path() -> Path:
    """Return the current/latest route project used by the simulation tab."""

    return latest_route_result_path()


def selected_region_path() -> Path:
    return state_dir() / "selected_region.json"


def _loaded_complete_app_classes() -> list[type]:
    classes: list[type] = []
    for module_name in ("qt_route_selector.complete_app", "complete_app", "__main__"):
        module = sys.modules.get(module_name)
        candidate = getattr(module, "CompleteApplicationWindow", None) if module else None
        if isinstance(candidate, type) and candidate not in classes:
            classes.append(candidate)
    return classes


def _loaded_route_selector_classes() -> list[type]:
    classes: list[type] = []
    for module_name in ("qt_route_selector.main", "main", "__main__"):
        module = sys.modules.get(module_name)
        candidate = getattr(module, "RouteSelector", None) if module else None
        if isinstance(candidate, type) and candidate not in classes:
            classes.append(candidate)
    return classes


def _install_timestamped_route_results() -> None:
    """Make step 1 write immutable timestamped route-project JSON files.

    The routing core predates the complete application and historically writes a
    fixed ``route_result.json`` in the current working directory. The complete app
    keeps every generated/imported route instead. This installer is intentionally
    applied only to already-loaded application classes and therefore does not
    change library-only consumers that never call ``prepare_runtime_directories``.
    """

    for selector_class in _loaded_route_selector_classes():
        if bool(getattr(selector_class, "_timestamped_route_results_installed", False)):
            continue

        def route_finished(self: Any, result: dict[str, Any]) -> None:
            output_path = next_route_result_path()
            output = {
                "metadata": self._file_metadata_payload(),
                "selection": self._selection_payload(),
                **result,
            }
            metadata = output.get("metadata")
            if isinstance(metadata, dict):
                metadata["project_file"] = str(output_path)
            temporary = output_path.with_name(output_path.name + ".tmp")
            temporary.write_text(
                json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, output_path)
            self._route_result_file = str(output_path)
            try:
                self.settings.setValue("last_route_result_file", str(output_path))
            except Exception:
                pass

            route_points = result.get("coordinates", [])
            signal_points = result.get("traffic_signals", [])
            self.routeChanged.emit(route_points)
            self.signalsChanged.emit(signal_points)
            self.traffic_signal_model.set_points(signal_points)
            summary = result.get("summary", {})
            self.summaryChanged.emit(summary)
            cache_note = " (Graph-Cache)" if summary.get("graph_cache_hit") else ""
            self.statusChanged.emit(
                f"Route berechnet und als {output_path.name} gespeichert: "
                f"{summary.get('distance_km', 0.0):.2f} km, "
                f"ca. {summary.get('estimated_minutes', 0.0):.1f} min{cache_note}."
            )
            self._set_busy(False)

        selector_class._route_finished = route_finished
        selector_class._timestamped_route_results_installed = True

    # If the speed-profile tab already exists when a new route is generated,
    # point it at the newly written project before its normal reload timer runs.
    for app_class in _loaded_complete_app_classes():
        if bool(getattr(app_class, "_timestamped_route_sync_installed", False)):
            continue
        original_route_changed = getattr(app_class, "_route_changed", None)
        if not callable(original_route_changed):
            continue

        def synced_route_changed(self: Any, points: list[dict[str, Any]], _original=original_route_changed) -> Any:
            project_file = str(getattr(self.route_selector, "_route_result_file", "") or "").strip()
            speed_profile = getattr(self, "speed_profile", None)
            if project_file and speed_profile is not None:
                try:
                    speed_profile.set_route_path(project_file)
                except Exception:
                    pass
            return _original(self, points)

        app_class._route_changed = synced_route_changed
        app_class._timestamped_route_sync_installed = True


def prepare_runtime_directories() -> dict[str, Path]:
    paths = {
        "root": runtime_root(),
        "data": data_dir(),
        "state": state_dir(),
        "exports": exports_dir(),
    }
    _install_timestamped_route_results()
    return paths
