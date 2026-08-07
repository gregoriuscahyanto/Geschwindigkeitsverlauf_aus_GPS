from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from auto_data import (
    DATASETS,
    cached_dataset,
    prepare_dataset,
    prepare_elevation_for_route,
)
from auto_region import (
    dataset_label,
    detect_dataset_for_points,
)
from main import RoutePointModel, RouteSelector, TrafficSignalModel
from offline_map import OfflineMapItem

DATASETS["austria"]["label"] = "Österreich (gesamt)"


class AutomaticRegionWorker(QObject):
    progress = Signal(str, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, points: list[Any], data_root: Path) -> None:
        super().__init__()
        self.points = list(points)
        self.data_root = data_root

    @Slot()
    def run(self) -> None:
        try:
            dataset_key = detect_dataset_for_points(
                self.points,
                self.data_root,
                progress=lambda text, percent: self.progress.emit(text, percent),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(dataset_key)


class AutomaticDataWorker(QObject):
    progress = Signal(str, int)
    finished = Signal("QVariantMap")
    failed = Signal(str)

    def __init__(self, dataset_key: str, data_root: Path) -> None:
        super().__init__()
        self.dataset_key = dataset_key
        self.data_root = data_root

    @Slot()
    def run(self) -> None:
        try:
            result = prepare_dataset(
                self.dataset_key,
                self.data_root,
                progress=lambda text, percent: self.progress.emit(text, percent),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)


class AutomaticElevationWorker(QObject):
    progress = Signal(str, int)
    finished = Signal("QVariantMap")
    failed = Signal(str)

    def __init__(
        self,
        dataset_key: str,
        data_root: Path,
        route_points: list[dict[str, Any]],
    ) -> None:
        super().__init__()
        self.dataset_key = dataset_key
        self.data_root = data_root
        self.route_points = route_points

    @Slot()
    def run(self) -> None:
        try:
            result = prepare_elevation_for_route(
                self.dataset_key,
                self.data_root,
                self.route_points,
                progress=lambda text, percent: self.progress.emit(text, percent),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)


class CompleteApplicationWindow(QMainWindow):
    """One desktop window with automatic routing-region and elevation handling."""

    def __init__(self, *, force_offline: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("GPS-Routenplaner und Geschwindigkeitsverlauf")
        self.resize(1600, 980)
        self.setMinimumSize(1100, 720)

        self._region_thread: QThread | None = None
        self._region_worker: AutomaticRegionWorker | None = None
        self._data_thread: QThread | None = None
        self._data_worker: AutomaticDataWorker | None = None
        self._elevation_thread: QThread | None = None
        self._elevation_worker: AutomaticElevationWorker | None = None
        self._pending_region_points: list[Any] = []
        self._last_region_signature: tuple[tuple[float, float], ...] | None = None
        self._simulation_load_pending = True
        self._simulation_creating = False
        self._coverage_creating = False
        self.speed_profile: Any | None = None
        self.coverage_tab: Any | None = None
        self._pending_dem_file = ""
        self._active_dataset_key = ""
        self.data_root = Path.cwd() / "data"

        qmlRegisterType(OfflineMapItem, "OfflineMap", 1, 0, "OfflineMapItem")

        self.route_point_model = RoutePointModel()
        self.traffic_signal_model = TrafficSignalModel()
        self.route_selector = RouteSelector(
            self.route_point_model,
            self.traffic_signal_model,
        )
        if force_offline:
            self.route_selector.setMapPreference("offline")

        self.qml_engine = QQmlApplicationEngine()
        self.qml_engine.rootContext().setContextProperty("routeSelector", self.route_selector)
        self.qml_engine.rootContext().setContextProperty("routePointModel", self.route_point_model)
        self.qml_engine.rootContext().setContextProperty("trafficSignalModel", self.traffic_signal_model)
        self.qml_engine.load(str(APP_DIR / "main.qml"))
        roots = self.qml_engine.rootObjects()
        if not roots or not isinstance(roots[0], QWindow):
            raise RuntimeError("Die QML-Routenansicht konnte nicht eingebettet werden.")

        self.route_window = roots[0]
        self.route_window.setVisible(False)
        self.route_container = QWidget.createWindowContainer(self.route_window, self)
        self.route_container.setMinimumSize(900, 600)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_route_page(), "1 · Route und Karte")
        self.simulation_placeholder = self._build_simulation_placeholder()
        self.tabs.addTab(self.simulation_placeholder, "2 · Geschwindigkeitsverlauf")
        self.coverage_placeholder = self._build_coverage_placeholder()
        self.tabs.addTab(self.coverage_placeholder, "3 · Datenabdeckung")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        self.route_selector.routeChanged.connect(self._route_changed)
        self.route_selector.selectionChanged.connect(self._selection_changed)
        QTimer.singleShot(0, self._restore_cached_dataset)

    def _build_route_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(6, 6, 6, 6)
        page_layout.setSpacing(6)
        data_group = QGroupBox("Automatische Routing- und Höhendaten")
        group_layout = QVBoxLayout(data_group)
        first_row = QHBoxLayout()
        first_row.addWidget(QLabel("Automatisch erkanntes Gebiet:"))
        self.detected_region_label = QLabel("Noch nicht bestimmt – Start und Ziel anklicken")
        self.detected_region_label.setStyleSheet("font-weight: 600;")
        first_row.addWidget(self.detected_region_label, 1)
        group_layout.addLayout(first_row)
        self.data_status = QLabel(
            "Start und Ziel setzen. Die App erkennt danach selbst das passende Gebiet, aktiviert "
            "vorhandene Routingdaten oder bereitet fehlende Daten automatisch vor."
        )
        self.data_status.setWordWrap(True)
        group_layout.addWidget(self.data_status)
        self.data_progress = QProgressBar()
        self.data_progress.setRange(0, 100)
        self.data_progress.setValue(0)
        group_layout.addWidget(self.data_progress)
        page_layout.addWidget(data_group)
        page_layout.addWidget(self.route_container, 1)
        return page

    def _build_simulation_placeholder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(
            "Der Geschwindigkeitsverlauf wird erst beim Öffnen dieses Tabs initialisiert.\n\n"
            "Dadurch bleiben Programmstart und Routenplanung unabhängig von PyQtGraph, "
            "Rasterio und der zweiten Kartenansicht reaktionsfähig."
        )
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _build_coverage_placeholder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(
            "Die Datenabdeckungskarte wird erst beim Öffnen dieses Tabs geladen.\n\n"
            "Sie zeigt lokal vorhandene .poly-Grenzen, OSM-PBF-Dateien und fertige Routing-GPKGs."
        )
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    @staticmethod
    def _points_signature(points: list[Any]) -> tuple[tuple[float, float], ...]:
        signature: list[tuple[float, float]] = []
        for point in points:
            if isinstance(point, dict):
                latitude = float(point["latitude"])
                longitude = float(point["longitude"])
            else:
                latitude = float(point[0])
                longitude = float(point[1])
            signature.append((round(latitude, 6), round(longitude, 6)))
        return tuple(signature)

    @Slot()
    def _restore_cached_dataset(self) -> None:
        saved = str(self.route_selector.settings.value("active_dataset_key", "") or "")
        if saved in DATASETS:
            result = cached_dataset(saved, self.data_root)
            if result is not None:
                self._activate_prepared_data(result, restored=True)
                self.detected_region_label.setText(
                    f"Zuletzt aktiv: {dataset_label(saved)} – wird nach Start/Ziel automatisch geprüft"
                )
                return
        self.data_status.setText(
            "Start und Ziel anklicken. Danach erkennt die App automatisch das kleinste passende "
            "Routinggebiet und bereitet fehlende Daten selbst vor."
        )
        self.data_progress.setValue(0)

    def _refresh_coverage_if_ready(self) -> None:
        if self.coverage_tab is None:
            return
        try:
            self.coverage_tab.refresh(active_dataset_key=self._active_dataset_key)
        except Exception:
            pass

    def _activate_prepared_data(self, result: dict[str, Any], *, restored: bool = False) -> None:
        dataset_key = str(result.get("dataset", ""))
        roads_file = str(result.get("roads_file", ""))
        dem_file = str(result.get("dem_file", ""))
        if roads_file:
            self.route_selector._set_roads_file(roads_file)
        if dem_file:
            self._pending_dem_file = dem_file
            if self.speed_profile is not None:
                try:
                    self.speed_profile.set_dem_path(dem_file)
                except Exception as exc:
                    self.data_status.setText(
                        f"Routingdaten aktiv; Höhenmodell konnte nicht aktiviert werden: {exc}"
                    )
                    return
        self._active_dataset_key = dataset_key
        if dataset_key:
            self.route_selector.settings.setValue("active_dataset_key", dataset_key)
            if self.route_selector.pointCount >= 2:
                self.detected_region_label.setText(dataset_label(dataset_key))
        self.data_progress.setValue(100)
        self._refresh_coverage_if_ready()
        label = dataset_label(dataset_key)
        if restored and dem_file:
            self.data_status.setText(f"✓ {label}: vorhandenes GPKG und Höhendaten automatisch aktiviert.")
        elif restored:
            self.data_status.setText(
                f"✓ {label}: vorhandenes GPKG automatisch aktiviert. Benötigte Höhenkacheln werden nach der Routenberechnung ergänzt."
            )
        elif dem_file:
            self.data_status.setText(f"Fertig: {label}-GPKG und Höhenmodell sind aktiv.")
        else:
            self.data_status.setText(
                f"Fertig: {label}-GPKG ist aktiv. Höhenkacheln folgen automatisch mit der Route."
            )
        self.route_selector.statusChanged.emit(
            f"{label}: lokaler Routingindex ist aktiv – Route kann berechnet werden."
        )

    @Slot("QVariantMap")
    def _selection_changed(self, data: dict[str, Any]) -> None:
        points = data.get("points", []) if isinstance(data, dict) else []
        if not isinstance(points, list) or len(points) < 2:
            self._pending_region_points = []
            self._last_region_signature = None
            self.detected_region_label.setText("Noch nicht bestimmt – Start und Ziel anklicken")
            return
        signature = self._points_signature(points)
        if signature == self._last_region_signature:
            return
        if self._region_thread is not None or self._data_thread is not None:
            self._pending_region_points = list(points)
            return
        self._last_region_signature = signature
        self._start_region_detection(list(points))

    def _start_region_detection(self, points: list[Any]) -> None:
        if self._region_thread is not None or len(points) < 2:
            return
        self.detected_region_label.setText("wird automatisch ermittelt …")
        self.data_status.setText(
            "Ermittle aus Start/Ziel das passende Routinggebiet. Die kleinen Gebietsgrenzen werden bei Bedarf automatisch geladen und danach lokal gecacht."
        )
        self.data_progress.setValue(0)
        thread = QThread(self)
        worker = AutomaticRegionWorker(points, self.data_root)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._region_progress_changed)
        worker.finished.connect(self._region_detected)
        worker.failed.connect(self._region_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._region_thread_finished)
        self._region_thread = thread
        self._region_worker = worker
        thread.start()

    @Slot(str, int)
    def _region_progress_changed(self, text: str, percent: int) -> None:
        self.data_status.setText(text)
        self.data_progress.setValue(percent)

    @Slot(str)
    def _region_detected(self, dataset_key: str) -> None:
        if dataset_key not in DATASETS:
            self._region_failed(f"Unbekanntes automatisch erkanntes Gebiet: {dataset_key}")
            return
        label = dataset_label(dataset_key)
        self.detected_region_label.setText(label)
        cached = cached_dataset(dataset_key, self.data_root)
        if cached is not None:
            self._activate_prepared_data(cached, restored=True)
            self.data_status.setText(
                f"✓ Automatisch erkannt: {label}. Das vorhandene GPKG wurde aktiviert; kein erneuter OSM-Download erforderlich."
            )
            return
        self.data_status.setText(
            f"Automatisch erkannt: {label}. Lokales GPKG fehlt und wird jetzt aus OSM vorbereitet …"
        )
        self._start_dataset_preparation(
            dataset_key,
            confirm_large=bool(DATASETS[dataset_key].get("large_download")),
        )

    @Slot(str)
    def _region_failed(self, message: str) -> None:
        self._last_region_signature = None
        self.detected_region_label.setText("Gebiet konnte nicht automatisch bestimmt werden")
        self.data_status.setText(f"Gebietserkennung fehlgeschlagen: {message}")
        self.data_progress.setValue(0)

    @Slot()
    def _region_thread_finished(self) -> None:
        self._region_thread = None
        self._region_worker = None
        self._refresh_coverage_if_ready()
        self._maybe_process_pending_region()

    def _maybe_process_pending_region(self) -> None:
        if not self._pending_region_points or self._region_thread is not None or self._data_thread is not None:
            return
        points = self._pending_region_points
        self._pending_region_points = []
        signature = self._points_signature(points)
        if signature == self._last_region_signature:
            return
        self._last_region_signature = signature
        self._start_region_detection(points)

    @Slot(int)
    def _tab_changed(self, index: int) -> None:
        if index == 1:
            if self.speed_profile is None and not self._simulation_creating:
                QTimer.singleShot(60, self._ensure_simulation_created)
                return
            if self.speed_profile is not None and self._simulation_load_pending:
                QTimer.singleShot(60, self._load_pending_simulation)
            return
        if index == 2:
            if self.coverage_tab is None and not self._coverage_creating:
                QTimer.singleShot(40, self._ensure_coverage_created)
            else:
                self._refresh_coverage_if_ready()

    @Slot()
    def _ensure_simulation_created(self) -> None:
        if self.speed_profile is not None or self._simulation_creating:
            return
        if self.tabs.currentIndex() != 1:
            return
        self._simulation_creating = True
        try:
            from integrated_speed_profile_v3 import IntegratedSpeedProfileWindow
            simulation = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
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

    @Slot()
    def _ensure_coverage_created(self) -> None:
        if self.coverage_tab is not None or self._coverage_creating:
            return
        if self.tabs.currentIndex() != 2:
            return
        self._coverage_creating = True
        try:
            from coverage_tab import CoverageTab
            coverage = CoverageTab(
                self.data_root,
                active_dataset_key=self._active_dataset_key,
                parent=self,
            )
            self.coverage_tab = coverage
            self.tabs.blockSignals(True)
            try:
                self.tabs.removeTab(2)
                self.tabs.insertTab(2, coverage, "3 · Datenabdeckung")
                self.tabs.setCurrentIndex(2)
            finally:
                self.tabs.blockSignals(False)
        except Exception as exc:
            QMessageBox.critical(self, "Datenabdeckung konnte nicht initialisiert werden", str(exc))
            self.tabs.setCurrentIndex(0)
        finally:
            self._coverage_creating = False

    @Slot()
    def _load_pending_simulation(self) -> None:
        if not self._simulation_load_pending or self.speed_profile is None:
            return
        self._simulation_load_pending = False
        self.speed_profile.statusBar().showMessage("Route und Simulation werden geladen …")
        self.speed_profile.reload_route(silent=True)

    def _start_dataset_preparation(self, dataset_key: str, *, confirm_large: bool) -> None:
        if self._data_thread is not None or dataset_key not in DATASETS:
            return
        cached = cached_dataset(dataset_key, self.data_root)
        if cached is not None:
            self._activate_prepared_data(cached, restored=True)
            return
        if confirm_large:
            answer = QMessageBox.question(
                self,
                "Großer grenzüberschreitender Datensatz",
                "Start und Ziel liegen nicht gemeinsam in einem kleineren unterstützten Regionalextrakt. Für eine durchgehende Route benötigt die App deshalb den gemeinsamen DACH-Datensatz (Deutschland, Österreich, Schweiz). Dieser Download ist mehrere GB groß, wird aber nur einmal benötigt und danach lokal als GPKG wiederverwendet.\n\nDACH jetzt automatisch herunterladen und vorbereiten?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.data_status.setText(
                    "Grenzroute erkannt, aber DACH wurde nicht vorbereitet. Die beiden Punkte bleiben erhalten; setze einen Punkt neu, um die Automatik erneut zu starten."
                )
                self.data_progress.setValue(0)
                return
        self.data_progress.setValue(0)
        self.data_status.setText(
            f"{dataset_label(dataset_key)}: OSM wird bei Bedarf geladen und automatisch in GPKG umgewandelt …"
        )
        thread = QThread(self)
        worker = AutomaticDataWorker(dataset_key, self.data_root)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._data_progress_changed)
        worker.finished.connect(self._data_preparation_finished)
        worker.failed.connect(self._data_preparation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._data_thread_finished)
        self._data_thread = thread
        self._data_worker = worker
        thread.start()

    @Slot(str, int)
    def _data_progress_changed(self, text: str, percent: int) -> None:
        self.data_status.setText(text)
        self.data_progress.setValue(percent)

    @Slot("QVariantMap")
    def _data_preparation_finished(self, result: dict[str, Any]) -> None:
        self._activate_prepared_data(result)

    @Slot(str)
    def _data_preparation_failed(self, message: str) -> None:
        self.data_status.setText(f"Automatische Datenvorbereitung fehlgeschlagen: {message}")
        self.data_progress.setValue(0)
        self._refresh_coverage_if_ready()
        QMessageBox.critical(self, "Automatische Datenvorbereitung fehlgeschlagen", message)

    @Slot()
    def _data_thread_finished(self) -> None:
        self._data_thread = None
        self._data_worker = None
        self._refresh_coverage_if_ready()
        self._maybe_process_pending_region()

    def _start_route_elevation(self, points: list[dict[str, Any]]) -> None:
        dataset_key = self._active_dataset_key
        if not dataset_key or self._elevation_thread is not None or len(points) < 2:
            return
        if dataset_key == "austria" and self._pending_dem_file:
            return
        thread = QThread(self)
        worker = AutomaticElevationWorker(dataset_key, self.data_root, list(points))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._elevation_progress_changed)
        worker.finished.connect(self._elevation_finished)
        worker.failed.connect(self._elevation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._elevation_thread_finished)
        self._elevation_thread = thread
        self._elevation_worker = worker
        self.data_status.setText("Höhendaten für die berechnete Route werden automatisch vorbereitet …")
        self.data_progress.setValue(0)
        thread.start()

    @Slot(str, int)
    def _elevation_progress_changed(self, text: str, percent: int) -> None:
        self.data_status.setText(text)
        self.data_progress.setValue(percent)

    @Slot("QVariantMap")
    def _elevation_finished(self, result: dict[str, Any]) -> None:
        dem_file = str(result.get("dem_file", ""))
        tile_count = int(result.get("tile_count", 0) or 0)
        provider = str(result.get("provider", ""))
        if dem_file:
            self._pending_dem_file = dem_file
            if self.speed_profile is not None:
                try:
                    self.speed_profile.set_dem_path(dem_file)
                except Exception as exc:
                    self.data_status.setText(f"Höhendaten geladen, aber Aktivierung fehlgeschlagen: {exc}")
                    return
        self.data_progress.setValue(100)
        if provider == "austria_dgm10":
            self.data_status.setText("Österreichisches 10-m-Höhenmodell ist für die Route aktiv.")
        else:
            self.data_status.setText(
                f"Höhendaten bereit: {tile_count} Copernicus-GLO-30-Kachel(n) automatisch geladen/gecacht."
            )

    @Slot(str)
    def _elevation_failed(self, message: str) -> None:
        self.data_status.setText(
            f"Route ist berechnet; Höhendaten konnten nicht automatisch geladen werden: {message}"
        )

    @Slot()
    def _elevation_thread_finished(self) -> None:
        self._elevation_thread = None
        self._elevation_worker = None

    def _route_changed(self, points: list[dict[str, Any]]) -> None:
        if len(points) <= 1:
            return
        self._simulation_load_pending = True
        self._start_route_elevation(points)
        if self.tabs.currentIndex() == 1 and self.speed_profile is not None:
            QTimer.singleShot(80, self._load_pending_simulation)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GPS Route and Live Speed Profile")
    app.setOrganizationName("GPSDrivingSimulation")
    window = CompleteApplicationWindow()
    window.show()
    app._main_window = window
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
