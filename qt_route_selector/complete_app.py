from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

try:
    from .complete_app_base import *  # noqa: F401,F403
    from .complete_app_base import CompleteApplicationWindow as _BaseWindow
    from .runtime_paths import data_dir, prepare_runtime_directories, route_result_path, state_dir
except ImportError:
    from complete_app_base import *  # type: ignore  # noqa: F401,F403
    from complete_app_base import CompleteApplicationWindow as _BaseWindow
    from runtime_paths import data_dir, prepare_runtime_directories, route_result_path, state_dir


class CompleteApplicationWindow(_BaseWindow):
    """Complete app with a compact automatic-first routing workflow."""

    def __init__(self, *args, **kwargs) -> None:
        runtime_data = data_dir()
        super().__init__(*args, **kwargs)
        # The legacy base class historically used ``Path.cwd() / 'data'``.
        # Override it before its zero-delay restore callback runs so all OSM,
        # DEM and routing-cache data live in the per-user application folder.
        self.data_root = runtime_data
        self._stabilize_qml_backend_lifetimes()
        self.setMinimumSize(920, 640)
        if hasattr(self, "route_container"):
            self.route_container.setMinimumSize(640, 420)
        self._hide_manual_road_data_button()

    def _stabilize_qml_backend_lifetimes(self) -> None:
        """Keep context objects alive until the QQmlApplicationEngine is torn down."""
        engine = getattr(self, "qml_engine", None)
        if engine is None:
            return
        for obj in (
            getattr(self, "route_selector", None),
            getattr(self, "route_point_model", None),
            getattr(self, "traffic_signal_model", None),
        ):
            if isinstance(obj, QObject) and obj.parent() is None:
                obj.setParent(engine)

    def _build_route_page(self) -> QWidget:
        """One compact status card; region and data selection are automatic."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(6, 6, 6, 6)
        page_layout.setSpacing(6)

        data_group = QGroupBox("Daten für diese Route")
        data_group.setStyleSheet(
            "QGroupBox { font-weight:600; border:1px solid palette(midlight); "
            "border-radius:8px; margin-top:8px; padding-top:8px; }"
        )
        group_layout = QVBoxLayout(data_group)
        group_layout.setContentsMargins(12, 12, 12, 9)
        group_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        region_caption = QLabel("Gebiet:")
        region_caption.setStyleSheet("font-weight:600;")
        header.addWidget(region_caption)
        self.detected_region_label = QLabel("Noch nicht bestimmt – Start und Ziel anklicken")
        self.detected_region_label.setStyleSheet("font-weight:600;")
        self.detected_region_label.setWordWrap(True)
        header.addWidget(self.detected_region_label, 1)
        group_layout.addLayout(header)

        self.data_status = QLabel(
            "Start und Ziel setzen. Die App erkennt das passende Gebiet automatisch und verwendet "
            "vorhandene Routing- und Höhendaten oder bereitet fehlende Daten selbst vor."
        )
        self.data_status.setWordWrap(True)
        self.data_status.setStyleSheet("color:palette(mid);")
        group_layout.addWidget(self.data_status)

        self.data_progress = QProgressBar()
        self.data_progress.setRange(0, 100)
        self.data_progress.setValue(0)
        self.data_progress.setTextVisible(False)
        self.data_progress.setMaximumHeight(10)
        group_layout.addWidget(self.data_progress)

        self.route_data_group = data_group
        page_layout.addWidget(data_group)
        page_layout.addWidget(self.route_container, 1)
        return page

    def _hide_manual_road_data_button(self) -> None:
        """Remove the old manual road-file action from the normal user workflow."""
        route_window = getattr(self, "route_window", None)
        if route_window is None:
            return
        for item in route_window.findChildren(QObject):
            try:
                text = item.property("text")
            except Exception:
                continue
            if str(text or "").strip() == "Straßendaten wählen":
                item.setProperty("visible", False)
                item.setProperty("enabled", False)
                self.manual_road_data_button_hidden = True

    @staticmethod
    def _loading_placeholder(title: str, detail: str) -> tuple[QWidget, QLabel, QProgressBar]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(f"{title}\n\n{detail}")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setMaximumWidth(420)
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addWidget(progress, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return page, label, progress

    def _build_simulation_placeholder(self) -> QWidget:
        page, label, progress = self._loading_placeholder(
            "Geschwindigkeitsverlauf wird erst bei Bedarf geladen.",
            "Beim Öffnen werden Simulation, technische Vorschauen und Kartenansicht initialisiert.",
        )
        self.simulation_loading_label = label
        self.simulation_loading_bar = progress
        return page

    def _build_coverage_placeholder(self) -> QWidget:
        page, label, progress = self._loading_placeholder(
            "Datenabdeckung wird erst bei Bedarf geladen.",
            "Beim Öffnen wird die lokale Kartenabdeckung aus POLY, PBF und GPKG aufgebaut.",
        )
        self.coverage_loading_label = label
        self.coverage_loading_bar = progress
        return page

    def _ensure_simulation_created(self) -> None:
        """Create the current public simulation UI using the runtime state file."""
        if self.speed_profile is not None or self._simulation_creating:
            return
        if self.tabs.currentIndex() != 1:
            return
        if hasattr(self, "simulation_loading_label"):
            self.simulation_loading_label.setText(
                "Geschwindigkeitsverlauf wird geladen …\n\nPlots, Vergleichswerkzeuge und Karte werden initialisiert."
            )
        QApplication.processEvents()

        self._simulation_creating = True
        try:
            try:
                from .integrated_speed_profile import IntegratedSpeedProfileWindow
            except ImportError:
                from integrated_speed_profile import IntegratedSpeedProfileWindow

            simulation = IntegratedSpeedProfileWindow(route_result_path())
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

    def _ensure_coverage_created(self) -> None:
        if hasattr(self, "coverage_loading_label"):
            self.coverage_loading_label.setText(
                "Datenabdeckung wird geladen …\n\nLokale Gebietsgrenzen und Dateistatus werden aufbereitet."
            )
        QApplication.processEvents()
        super()._ensure_coverage_created()


def main() -> int:
    paths = prepare_runtime_directories()
    # RouteSelector still writes its transient route JSONs relative to the
    # process working directory. Run the application from its dedicated state
    # directory so those files never pollute the source checkout.
    os.chdir(paths["state"])

    app = QApplication(sys.argv)
    app.setApplicationName("GPS-Routenplaner")
    app.setApplicationDisplayName("GPS-Routenplaner und Geschwindigkeitsverlauf")
    app.setOrganizationName("GPSDrivingSimulation")
    window = CompleteApplicationWindow()
    window.show()
    app._main_window = window  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
