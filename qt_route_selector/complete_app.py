from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from .complete_app_base import *  # noqa: F401,F403
    from .complete_app_base import (
        DATASETS,
        CompleteApplicationWindow as _BaseWindow,
        cached_dataset,
    )
    from .gpx_import import build_route_from_gpx, parse_gpx_track
    from .runtime_paths import data_dir, prepare_runtime_directories, route_result_path, state_dir
    from .ui_theme import apply_readable_light_theme
except ImportError:
    from complete_app_base import *  # type: ignore  # noqa: F401,F403
    from complete_app_base import DATASETS, CompleteApplicationWindow as _BaseWindow, cached_dataset
    from gpx_import import build_route_from_gpx, parse_gpx_track
    from runtime_paths import data_dir, prepare_runtime_directories, route_result_path, state_dir
    from ui_theme import apply_readable_light_theme


class GpxImportWorker(QObject):
    """Match one external GPX track to the automatically selected local OSM dataset."""

    progress = Signal(str, int)
    finished = Signal("QVariantMap")
    failed = Signal(str)

    def __init__(self, roads_path: str, gpx_path: str) -> None:
        super().__init__()
        self.roads_path = roads_path
        self.gpx_path = gpx_path

    @Slot()
    def run(self) -> None:
        try:
            result = build_route_from_gpx(
                self.roads_path,
                self.gpx_path,
                progress=lambda text, percent: self.progress.emit(text, percent),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)


class CompleteApplicationWindow(_BaseWindow):
    """Complete app with a compact automatic-first routing workflow."""

    def __init__(self, *args, **kwargs) -> None:
        runtime_data = data_dir()
        self._gpx_thread: QThread | None = None
        self._gpx_worker: GpxImportWorker | None = None
        self._gpx_route_has_elevation = False
        self._pending_gpx_path = ""
        self._pending_gpx_coordinates: list[dict[str, float]] = []
        self._setting_gpx_endpoints = False
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
        self._update_gpx_import_button()

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
        self.detected_region_label = QLabel("Noch nicht bestimmt – GPX importieren oder Punkte anklicken")
        self.detected_region_label.setStyleSheet("font-weight:600;")
        self.detected_region_label.setWordWrap(True)
        header.addWidget(self.detected_region_label, 1)
        group_layout.addLayout(header)

        self.data_status = QLabel(
            "GraphHopper-GPX kann direkt importiert werden. Die App liest Start/Ziel und Track, "
            "erkennt daraus automatisch das Gebiet und aktiviert die passenden lokalen OSM-Daten. "
            "Alternativ können Start/Ziel weiterhin auf der Karte gesetzt werden."
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

        self.gpx_import_button = QPushButton("GraphHopper-GPX importieren")
        self.gpx_import_button.setToolTip(
            "Die GPX kann direkt ohne vorherige Punktauswahl importiert werden. Das Gebiet wird "
            "aus dem Track erkannt; anschließend wird die GPX-Geometrie unverändert mit dem "
            "passenden lokalen OSM-GPKG für Tempolimits, Straßentypen und Ampeln abgeglichen."
        )
        self.gpx_import_button.clicked.connect(self._choose_gpx_route)
        group_layout.addWidget(self.gpx_import_button)

        self.route_selector.pointCountChanged.connect(self._update_gpx_import_button)
        self.route_selector.roadsFileChanged.connect(self._update_gpx_import_button)
        self.route_selector.busyChanged.connect(self._update_gpx_import_button)

        self.route_data_group = data_group
        page_layout.addWidget(data_group)
        page_layout.addWidget(self.route_container, 1)
        return page

    def _hide_manual_road_data_button(self) -> None:
        """Hide legacy/manual actions superseded by the automatic GPX workflow."""
        route_window = getattr(self, "route_window", None)
        if route_window is None:
            return
        hidden_texts = {"Straßendaten wählen", "Route berechnen"}
        for item in route_window.findChildren(QObject):
            try:
                text = str(item.property("text") or "").strip()
            except Exception:
                continue
            if text in hidden_texts:
                item.setProperty("visible", False)
                item.setProperty("enabled", False)
                if text == "Straßendaten wählen":
                    self.manual_road_data_button_hidden = True
                elif text == "Route berechnen":
                    self.local_route_button_hidden = True

    @Slot()
    def _update_gpx_import_button(self) -> None:
        button = getattr(self, "gpx_import_button", None)
        selector = getattr(self, "route_selector", None)
        if button is None or selector is None:
            return
        ready = (
            self._gpx_thread is None
            and getattr(self, "_region_thread", None) is None
            and getattr(self, "_data_thread", None) is None
            and not bool(selector.busy)
        )
        button.setEnabled(ready)

    def _set_selection_from_gpx(self, coordinates: list[dict[str, float]]) -> None:
        """Show GPX start/target markers without triggering a second region detection."""
        if len(coordinates) < 2:
            return
        first = coordinates[0]
        last = coordinates[-1]
        points = [
            (float(first["latitude"]), float(first["longitude"])),
            (float(last["latitude"]), float(last["longitude"])),
        ]
        selector = self.route_selector
        self._setting_gpx_endpoints = True
        try:
            selector.points = points
            selector.current_bbox = selector.bbox_for_points(points)
            selector._clear_route_display()
            selector._update_point_models()
        finally:
            self._setting_gpx_endpoints = False

    def _selection_changed(self, data: dict[str, Any]) -> None:
        if self._setting_gpx_endpoints:
            return
        super()._selection_changed(data)

    @Slot()
    def _choose_gpx_route(self) -> None:
        if (
            self._gpx_thread is not None
            or self._region_thread is not None
            or self._data_thread is not None
        ):
            return

        selected, _ = QFileDialog.getOpenFileName(
            self,
            "GraphHopper-GPX als Route importieren",
            str(Path.home()),
            "GPX-Dateien (*.gpx);;Alle Dateien (*)",
        )
        if not selected:
            return

        try:
            parsed = parse_gpx_track(selected)
            coordinates = list(parsed.get("coordinates", []))
        except Exception as exc:
            QMessageBox.critical(self, "GPX-Import fehlgeschlagen", str(exc))
            return
        if len(coordinates) < 2:
            QMessageBox.critical(
                self,
                "GPX-Import fehlgeschlagen",
                "Die GPX enthält weniger als zwei gültige Trackpunkte.",
            )
            return

        self._pending_gpx_path = str(Path(selected).resolve())
        self._pending_gpx_coordinates = coordinates
        self._set_selection_from_gpx(coordinates)
        self.data_progress.setRange(0, 100)
        self.data_progress.setValue(0)
        self.detected_region_label.setText("wird aus der GPX ermittelt …")
        self.data_status.setText(
            f"GPX gelesen: {len(coordinates)} Trackpunkte. "
            "Ermittle daraus automatisch das passende lokale OSM-Gebiet …"
        )
        self._update_gpx_import_button()
        self._start_region_detection(coordinates)

    def _maybe_start_pending_gpx_import(self) -> None:
        if not self._pending_gpx_path or self._gpx_thread is not None:
            return
        roads_file = str(self.route_selector.roadsFile or "").strip()
        if not roads_file or not Path(roads_file).is_file():
            return

        gpx_path = self._pending_gpx_path
        self._pending_gpx_path = ""
        self._pending_gpx_coordinates = []
        self.data_progress.setRange(0, 100)
        self.data_progress.setValue(0)
        self.data_status.setText(
            "Passendes Gebiet ist aktiv. GraphHopper-GPX wird jetzt mit den lokalen "
            "OSM-Straßen abgeglichen …"
        )
        thread = QThread(self)
        worker = GpxImportWorker(roads_file, gpx_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._gpx_progress_changed)
        worker.finished.connect(self._gpx_import_finished)
        worker.failed.connect(self._gpx_import_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._gpx_thread_finished)
        self._gpx_thread = thread
        self._gpx_worker = worker
        self._update_gpx_import_button()
        thread.start()

    @Slot(str, int)
    def _gpx_progress_changed(self, text: str, percent: int) -> None:
        self.data_status.setText(text)
        self.data_progress.setValue(percent)

    @Slot("QVariantMap")
    def _gpx_import_finished(self, result: dict[str, Any]) -> None:
        coordinates = result.get("coordinates", []) if isinstance(result, dict) else []
        elevation_count = sum(
            1
            for point in coordinates
            if isinstance(point, dict) and point.get("elevation_m") is not None
        )
        self._gpx_route_has_elevation = elevation_count >= 2
        try:
            # Reuse the normal route-result writer, map updates and simulation
            # signals. Only the route geometry source is different.
            self.route_selector._route_finished(result)
        finally:
            self._gpx_route_has_elevation = False

        summary = result.get("summary", {}) if isinstance(result, dict) else {}
        distance_km = float(summary.get("distance_km", 0.0) or 0.0)
        matched = int(summary.get("gpx_matched_segments", 0) or 0)
        unmatched = int(summary.get("gpx_unmatched_segments", 0) or 0)
        if elevation_count >= 2:
            self.data_status.setText(
                f"✓ GraphHopper-GPX importiert: {distance_km:.2f} km. "
                f"OSM-Zuordnung {matched}/{matched + unmatched} Segmente; "
                f"{elevation_count} GPX-Höhenpunkte werden direkt verwendet."
            )
            self.data_progress.setValue(100)
        self.route_selector.statusChanged.emit(
            f"GraphHopper-GPX importiert: {distance_km:.2f} km; "
            f"{matched}/{matched + unmatched} Segmente mit lokalen OSM-Daten verknüpft."
        )

    @Slot(str)
    def _gpx_import_failed(self, message: str) -> None:
        self.data_progress.setRange(0, 100)
        self.data_progress.setValue(0)
        self.data_status.setText(f"GPX-Import fehlgeschlagen: {message}")
        QMessageBox.critical(self, "GPX-Import fehlgeschlagen", message)

    @Slot()
    def _gpx_thread_finished(self) -> None:
        self._gpx_thread = None
        self._gpx_worker = None
        self._update_gpx_import_button()

    def _route_changed(self, points: list[dict[str, Any]]) -> None:
        # GraphHopper exports elevation per track point. If it is present, the
        # simulation can use it directly and no Copernicus/DEM download is
        # necessary merely to obtain an elevation profile.
        if self._gpx_route_has_elevation and len(points) > 1:
            self._simulation_load_pending = True
            if self.tabs.currentIndex() == 1 and self.speed_profile is not None:
                QTimer.singleShot(80, self._load_pending_simulation)
            return
        super()._route_changed(points)

    def _clear_stale_automatic_routing_data(self) -> None:
        """Prevent a previously active regional GPKG from routing a new region."""
        selector = self.route_selector
        old_pbf = bool(selector.isPbfSource)
        selector._roads_file = ""
        selector.settings.remove("roads_file")
        selector.roadsFileChanged.emit()
        if old_pbf != bool(selector.isPbfSource):
            selector.pbfSourceChanged.emit()
        selector.automaticOfflineReloadChanged.emit()
        selector.mapRoadsChanged.emit([])
        selector.mapSummaryChanged.emit({})

        self._active_dataset_key = ""
        self._pending_dem_file = ""
        selector.settings.remove("active_dataset_key")
        selector.selectionChanged.emit(selector._selection_payload())
        self._refresh_coverage_if_ready()

    def _activate_prepared_data(self, result: dict[str, Any], *, restored: bool = False) -> None:
        super()._activate_prepared_data(result, restored=restored)
        if self._pending_gpx_path:
            QTimer.singleShot(0, self._maybe_start_pending_gpx_import)

    def _region_detected(self, dataset_key: str) -> None:
        """Switch datasets safely instead of retaining an unrelated old GPKG."""
        if dataset_key in DATASETS:
            cached = cached_dataset(dataset_key, self.data_root)
            if cached is None and self._active_dataset_key != dataset_key:
                self._clear_stale_automatic_routing_data()
        super()._region_detected(dataset_key)

    def _region_failed(self, message: str) -> None:
        self._pending_gpx_path = ""
        self._pending_gpx_coordinates = []
        super()._region_failed(message)
        self._update_gpx_import_button()

    def _start_dataset_preparation(self, dataset_key: str, *, confirm_large: bool) -> None:
        """Use a country-specific confirmation instead of calling every fallback DACH."""
        if not confirm_large:
            super()._start_dataset_preparation(dataset_key, confirm_large=False)
            return

        cached = cached_dataset(dataset_key, self.data_root)
        if cached is not None:
            self._activate_prepared_data(cached, restored=True)
            return

        if dataset_key == "dach":
            title = "Großer grenzüberschreitender Datensatz"
            question = (
                "Die GPX bzw. gewählten Punkte liegen in mehr als einem DACH-Land. Für eine "
                "durchgehende Auswertung benötigt die App deshalb den gemeinsamen DACH-Datensatz "
                "(Deutschland, Österreich, Schweiz). Dieser Download ist mehrere GB groß, wird "
                "aber nur einmal benötigt und danach lokal als GPKG wiederverwendet.\n\n"
                "DACH jetzt automatisch herunterladen und vorbereiten?"
            )
            declined = (
                "Grenzroute erkannt, aber DACH wurde nicht vorbereitet."
            )
        elif dataset_key == "germany":
            title = "Großer Deutschland-Datensatz"
            question = (
                "Die GPX bzw. gewählten Punkte liegen innerhalb Deutschlands, aber nicht gemeinsam "
                "in einem kleineren Regionalextrakt. Deshalb wird Deutschland (gesamt) benötigt. "
                "Dieser Download ist mehrere GB groß, wird aber nur einmal benötigt und danach "
                "lokal als GPKG wiederverwendet.\n\n"
                "Deutschland jetzt automatisch herunterladen und vorbereiten?"
            )
            declined = "Deutschland wurde erkannt, aber der große Datensatz wurde nicht vorbereitet."
        else:
            title = "Großer Routingdatensatz"
            question = (
                f"{dataset_label(dataset_key)} benötigt einen großen OSM-Datensatz. "
                "Jetzt automatisch herunterladen und vorbereiten?"
            )
            declined = f"{dataset_label(dataset_key)} wurde nicht vorbereitet."

        answer = QMessageBox.question(
            self,
            title,
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._pending_gpx_path = ""
            self._pending_gpx_coordinates = []
            self.data_status.setText(declined)
            self.data_progress.setValue(0)
            self._update_gpx_import_button()
            return

        super()._start_dataset_preparation(dataset_key, confirm_large=False)

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

    # Keep Qt Quick Controls and QWidget styling consistent even when a managed
    # Windows installation forces a dark/high-contrast system application theme.
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")
    app = QApplication(sys.argv)
    apply_readable_light_theme(app)
    app.setApplicationName("GPS-Routenplaner")
    app.setApplicationDisplayName("GPS-Routenplaner und Geschwindigkeitsverlauf")
    app.setOrganizationName("GPSDrivingSimulation")
    window = CompleteApplicationWindow()
    window.show()
    app._main_window = window  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
