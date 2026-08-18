from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QMessageBox

from . import complete_app as _complete_app
from . import complete_app_base as _complete_app_base
from . import coverage_tab as _coverage_tab
from .elevation_persistence import resolve_elevation_source, save_route_elevation_source
from .qtlocation_cache import prepared_qml_directory
from .runtime_paths import data_dir, route_result_path


# QtLocation's default OSM cache is a machine-wide GenericCacheLocation. Multiple
# QtLocation instances (or other Qt map applications) may therefore manage the
# same tile files. Give each map in this application its own app-owned cache and
# load a generated QML copy with the official osm.mapping.cache.directory
# parameter injected. The repository QML itself remains unchanged.
_SOURCE_DIR = Path(__file__).resolve().parent
_complete_app_base.APP_DIR = prepared_qml_directory(
    _SOURCE_DIR / "main.qml",
    "route-map",
)
_coverage_tab.APP_DIR = prepared_qml_directory(
    _SOURCE_DIR / "coverage_map.qml",
    "coverage-map",
)
# complete_app_base contains a historical top-level import for CoverageTab.
# Reuse the already configured package module instead of loading a second copy.
sys.modules.setdefault("coverage_tab", _coverage_tab)


def _install_persistent_simulation_window() -> type:
    """Install the route-bound persistence, elevation restore and current sidebar UI.

    The import is deliberately lazy so the large simulation UI is still loaded
    only when tab 2 is opened.
    """

    from . import integrated_speed_profile as public_module
    from .simulation_settings import PersistentSimulationSettingsMixin
    from .simulation_ui_layout import SimulationUiLayoutMixin
    from .speed_axis_autoscale import SpeedAxisAutoscaleMixin

    base_window = public_module.IntegratedSpeedProfileWindow
    if bool(getattr(base_window, "_route_app_extensions_installed", False)):
        return base_window

    class RouteElevationRestoreMixin:
        """Re-apply the DEM stored with whichever route JSON is currently opened."""

        def reload_route(self, *_args: Any, silent: bool = False) -> None:
            super().reload_route(*_args, silent=silent)
            route_path = Path(getattr(self, "_route_path", route_result_path())).expanduser().resolve()
            source = resolve_elevation_source(route_path, data_dir())
            if source is None:
                return
            current = getattr(self, "_dem_path", None)
            try:
                if current is not None and Path(current).expanduser().resolve() == source:
                    return
            except Exception:
                pass
            setter = getattr(self, "set_dem_path", None)
            if callable(setter):
                setter(str(source))

    if issubclass(base_window, PersistentSimulationSettingsMixin):

        class PersistentIntegratedSpeedProfileWindow(
            SpeedAxisAutoscaleMixin,
            SimulationUiLayoutMixin,
            RouteElevationRestoreMixin,
            base_window,
        ):
            """Current simulation UI with route-bound project state and compact cards."""

    else:

        class PersistentIntegratedSpeedProfileWindow(
            SpeedAxisAutoscaleMixin,
            SimulationUiLayoutMixin,
            PersistentSimulationSettingsMixin,
            RouteElevationRestoreMixin,
            base_window,
        ):
            """Current simulation UI with route-bound project state and compact cards."""

    PersistentIntegratedSpeedProfileWindow.__name__ = "IntegratedSpeedProfileWindow"
    PersistentIntegratedSpeedProfileWindow.__qualname__ = "IntegratedSpeedProfileWindow"
    PersistentIntegratedSpeedProfileWindow._route_app_extensions_installed = True
    public_module.IntegratedSpeedProfileWindow = PersistentIntegratedSpeedProfileWindow
    return PersistentIntegratedSpeedProfileWindow


class CompleteApplicationWindow(_complete_app.CompleteApplicationWindow):
    """Normal complete app with persistent route-bound simulation settings and DEM data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._restore_elevation_for_current_route()

    def _current_route_project(self) -> Path:
        selected = str(getattr(self.route_selector, "_route_result_file", "") or "").strip()
        if selected:
            return Path(selected).expanduser().resolve()
        return Path(route_result_path()).expanduser().resolve()

    def _restore_elevation_for_current_route(self) -> None:
        route_path = self._current_route_project()
        dataset_key = str(
            self.route_selector.settings.value("active_dataset_key", "") or ""
        ).strip()
        source = resolve_elevation_source(
            route_path,
            self.data_root,
            dataset_key=dataset_key,
        )
        if source is None:
            return
        self._pending_dem_file = str(source)
        if self.speed_profile is not None:
            setter = getattr(self.speed_profile, "set_dem_path", None)
            if callable(setter):
                setter(str(source))

    def _ensure_simulation_created(self) -> None:
        """Create tab 2 from the final patched class, never from a legacy top-level shim."""
        if self.speed_profile is not None or self._simulation_creating:
            return
        if self.tabs.currentIndex() != 1:
            return

        self._restore_elevation_for_current_route()
        simulation_type = _install_persistent_simulation_window()
        self._simulation_creating = True
        try:
            # complete_app_base historically imports ``integrated_speed_profile_v3``
            # as a top-level compatibility module. That can create a second,
            # unpatched module instance and bypass the mixins installed above.
            # Instantiate the returned final class directly so autoscaling,
            # settings persistence, DEM restore and the current sidebar layout
            # are guaranteed to be active in the visible simulation tab.
            simulation = simulation_type(Path.cwd() / "route_result.json")
            simulation.setWindowFlags(Qt.WindowType.Widget)
            if self._pending_dem_file:
                simulation.set_dem_path(self._pending_dem_file)
            self.speed_profile = simulation
            self.tabs.blockSignals(True)
            try:
                self.tabs.removeTab(1)
                self.tabs.insertTab(1, simulation, "2 · Geschwindigkeitsverlauf")
                self.tabs.setCurrentIndex(1)
            finally:
                self.tabs.blockSignals(False)
        except Exception as exc:
            QMessageBox.critical(self, "Simulation konnte nicht initialisiert werden", str(exc))
            self.tabs.setCurrentIndex(0)
            return
        finally:
            self._simulation_creating = False

        if self._simulation_load_pending:
            QTimer.singleShot(80, self._load_pending_simulation)

    def _elevation_finished(self, result: dict[str, Any]) -> None:
        super()._elevation_finished(result)
        dem_file = str(result.get("dem_file", "") or "").strip()
        if not dem_file:
            return
        try:
            save_route_elevation_source(
                self._current_route_project(),
                self.data_root,
                dem_file,
                provider=str(result.get("provider", "") or ""),
                tile_count=int(result.get("tile_count", 0) or 0),
            )
        except Exception as exc:
            # Elevation is already active in the current session. A persistence
            # failure should not discard it; surface the problem as a status note.
            self.data_status.setText(
                f"Höhendaten sind aktiv, konnten aber nicht in der Routendatei vermerkt werden: {exc}"
            )


# complete_app.main resolves CompleteApplicationWindow from its module globals at
# runtime. Replace that one reference so all of its existing startup/data logic
# remains unchanged while the simulation tab gets the persistent subclass above.
_complete_app.CompleteApplicationWindow = CompleteApplicationWindow


def main() -> int:
    return _complete_app.main()


__all__ = ["CompleteApplicationWindow", "main", "_install_persistent_simulation_window"]
