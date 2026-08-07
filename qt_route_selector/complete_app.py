from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Qt Quick / QtLocation can stall on some Windows enterprise GPU drivers or
# remote-desktop setups. Select the software scene-graph backend before any
# PySide6 module is imported. Users can still override it explicitly by setting
# QT_QUICK_BACKEND in their environment before launching the app.
if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from auto_data import AUSTRIA_DEM_DIRECTORY, DATASETS, prepare_dataset  # noqa: E402
from main import RoutePointModel, RouteSelector, TrafficSignalModel  # noqa: E402
from offline_map import OfflineMapItem  # noqa: E402
from routing_cache import default_cache_path  # noqa: E402


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


class CompleteApplicationWindow(QMainWindow):
    """One desktop window containing routing and lazily created simulation."""

    def __init__(self, *, force_offline: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("GPS-Routenplaner und Geschwindigkeitsverlauf")
        self.resize(1600, 980)
        self.setMinimumSize(1100, 720)

        self._data_thread: QThread | None = None
        self._data_worker: AutomaticDataWorker | None = None
        self._simulation_load_pending = True
        self._simulation_creating = False
        self.speed_profile: Any | None = None
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
        self.qml_engine.rootContext().setContextProperty(
            "routeSelector", self.route_selector
        )
        self.qml_engine.rootContext().setContextProperty(
            "routePointModel", self.route_point_model
        )
        self.qml_engine.rootContext().setContextProperty(
            "trafficSignalModel", self.traffic_signal_model
        )
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
        self.tabs.addTab(
            self.simulation_placeholder,
            "2 · Geschwindigkeitsverlauf",
        )
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        self.route_selector.routeChanged.connect(self._route_changed)

        # Restore already downloaded datasets only after the main window has
        # entered the event loop. This performs local filesystem checks only;
        # it never starts a network download during application startup.
        QTimer.singleShot(0, self._restore_cached_dataset)

    def _build_route_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(6, 6, 6, 6)
        page_layout.setSpacing(6)

        data_group = QGroupBox("Lokale OSM- und Höhendaten")
        group_layout = QVBoxLayout(data_group)
        first_row = QHBoxLayout()

        first_row.addWidget(QLabel("Gebiet:"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.addItem("Österreich – A10 / Großglockner", "austria")
        self.dataset_combo.addItem("Alpen – grenzüberschreitendes OSM", "alps")
        self.dataset_combo.setToolTip(
            "Vorhandene lokale Daten werden beim Programmstart automatisch erkannt und aktiviert. "
            "Der Button lädt nur fehlende Dateien bzw. bereitet fehlende Indizes vor."
        )
        first_row.addWidget(self.dataset_combo, 1)

        self.prepare_data_button = QPushButton("OSM + Höhen prüfen / laden")
        self.prepare_data_button.clicked.connect(self._start_data_preparation)
        first_row.addWidget(self.prepare_data_button)
        group_layout.addLayout(first_row)

        second_row = QHBoxLayout()
        self.data_progress = QProgressBar()
        self.data_progress.setRange(0, 100)
        self.data_progress.setValue(0)
        second_row.addWidget(self.data_progress, 1)
        self.data_status = QLabel(
            "Suche beim Start nach bereits vorhandenen lokalen OSM-, Routing- und Höhendaten …"
        )
        self.data_status.setWordWrap(True)
        second_row.addWidget(self.data_status, 2)
        group_layout.addLayout(second_row)

        self.data_path_label = QLabel(f"Lokaler Datenordner: {self.data_root}")
        self.data_path_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        group_layout.addWidget(self.data_path_label)

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

    def _cached_dataset(self, dataset_key: str) -> dict[str, str] | None:
        dataset = DATASETS.get(dataset_key)
        if dataset is None:
            return None

        pbf_path = (self.data_root / "osm" / str(dataset["osm_filename"])).resolve()
        if not pbf_path.is_file() or pbf_path.stat().st_size <= 0:
            return None

        cache_path = Path(default_cache_path(pbf_path)).resolve()
        if not cache_path.is_file() or cache_path.stat().st_size <= 0:
            return None

        dem_directory = self.data_root / "elevation" / AUSTRIA_DEM_DIRECTORY
        dem_path: Path | None = None
        if dem_directory.is_dir():
            for pattern in ("*.tif", "*.tiff"):
                candidate = next(dem_directory.rglob(pattern), None)
                if candidate is not None and candidate.is_file() and candidate.stat().st_size > 0:
                    dem_path = candidate.resolve()
                    break
        if dem_path is None:
            return None

        return {
            "dataset": dataset_key,
            "pbf_file": str(pbf_path),
            "roads_file": str(cache_path),
            "dem_file": str(dem_path),
            "data_root": str(self.data_root.resolve()),
        }

    @Slot()
    def _restore_cached_dataset(self) -> None:
        # Prefer the currently selected preset, then fall back to any other
        # complete local dataset. This is intentionally network-free.
        preferred = str(self.dataset_combo.currentData())
        keys = [preferred] + [key for key in DATASETS if key != preferred]
        for dataset_key in keys:
            result = self._cached_dataset(dataset_key)
            if result is None:
                continue

            index = self.dataset_combo.findData(dataset_key)
            if index >= 0:
                self.dataset_combo.setCurrentIndex(index)
            self._activate_prepared_data(result, restored=True)
            return

        self.data_status.setText(
            "Noch kein vollständiger lokaler Datensatz erkannt. Beim ersten Mal werden nur fehlende "
            "OSM-/Höhendaten geladen; danach werden sie lokal wiederverwendet."
        )
        self.data_progress.setValue(0)

    def _activate_prepared_data(
        self,
        result: dict[str, Any],
        *,
        restored: bool = False,
    ) -> None:
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
        self.data_progress.setValue(100)
        if restored:
            self.data_status.setText(
                "✓ Bereits heruntergeladene OSM-, Routing- und Höhendaten automatisch erkannt und aktiviert. "
                "Kein erneuter Download erforderlich."
            )
        elif dem_file and self.speed_profile is None:
            self.data_status.setText(
                "Fertig: Routingindex und Höhenmodell sind lokal bereit. Das DEM wird beim Öffnen von Tab 2 aktiviert."
            )
        elif dem_file:
            self.data_status.setText(
                "Fertig: lokaler Routingindex und Höhenmodell sind aktiv."
            )
        else:
            self.data_status.setText("Fertig: lokale Routingdaten sind aktiv.")

        self.route_selector.statusChanged.emit(
            "Lokale Straßendaten sind aktiv – Start und Ziel auswählen."
        )

    @Slot(int)
    def _tab_changed(self, index: int) -> None:
        if index != 1:
            return
        if self.speed_profile is None and not self._simulation_creating:
            QTimer.singleShot(60, self._ensure_simulation_created)
            return
        if self.speed_profile is not None and self._simulation_load_pending:
            QTimer.singleShot(60, self._load_pending_simulation)

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
            QMessageBox.critical(
                self,
                "Simulation konnte nicht initialisiert werden",
                str(exc),
            )
            self.tabs.setCurrentIndex(0)
            return
        finally:
            self._simulation_creating = False

        if self._simulation_load_pending:
            QTimer.singleShot(80, self._load_pending_simulation)

    @Slot()
    def _load_pending_simulation(self) -> None:
        if not self._simulation_load_pending or self.speed_profile is None:
            return
        self._simulation_load_pending = False
        self.speed_profile.statusBar().showMessage("Route und Simulation werden geladen …")
        self.speed_profile.reload_route(silent=True)

    @Slot()
    def _start_data_preparation(self) -> None:
        if self._data_thread is not None:
            return
        dataset_key = str(self.dataset_combo.currentData())
        if dataset_key not in DATASETS:
            return

        if dataset_key == "alps":
            answer = QMessageBox.question(
                self,
                "Großer OSM-Datensatz",
                "Der Geofabrik-Alpen-Extrakt ist über 2 GB groß. Für Tauernautobahn und "
                "Großglockner reicht der wesentlich kleinere Österreich-Datensatz.\n\n"
                "Alpen-Datensatz trotzdem herunterladen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        # Fast path: if the selected dataset is already complete locally, just
        # activate it. No worker, checksum request or network connection needed.
        cached = self._cached_dataset(dataset_key)
        if cached is not None:
            self._activate_prepared_data(cached, restored=True)
            return

        self.prepare_data_button.setEnabled(False)
        self.dataset_combo.setEnabled(False)
        self.data_progress.setValue(0)
        self.data_status.setText("Prüfe lokale Dateien und lade nur fehlende Daten …")

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
        self.data_status.setText(f"Fehler: {message}")
        QMessageBox.critical(self, "Automatische Datenvorbereitung fehlgeschlagen", message)

    @Slot()
    def _data_thread_finished(self) -> None:
        self._data_thread = None
        self._data_worker = None
        self.prepare_data_button.setEnabled(True)
        self.dataset_combo.setEnabled(True)

    def _route_changed(self, points: list[dict[str, Any]]) -> None:
        if len(points) <= 1:
            return
        self._simulation_load_pending = True
        if self.tabs.currentIndex() == 1 and self.speed_profile is not None:
            QTimer.singleShot(80, self._load_pending_simulation)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GPS Route and Live Speed Profile")
    app.setOrganizationName("GPSDrivingSimulation")
    window = CompleteApplicationWindow()
    window.show()
    app._main_window = window  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
