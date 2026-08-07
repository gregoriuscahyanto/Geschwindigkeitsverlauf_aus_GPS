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

from auto_data import (  # noqa: E402
    DATASETS,
    cached_dataset,
    points_within_dataset,
    prepare_dataset,
    prepare_elevation_for_route,
)
from main import RoutePointModel, RouteSelector, TrafficSignalModel  # noqa: E402
from offline_map import OfflineMapItem  # noqa: E402


DATASET_ORDER = (
    "austria",
    "baden_wuerttemberg",
    "bayern",
    "hessen",
    "switzerland",
    "dach",
)


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
    """One desktop window containing routing and lazily created simulation."""

    def __init__(self, *, force_offline: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("GPS-Routenplaner und Geschwindigkeitsverlauf")
        self.resize(1600, 980)
        self.setMinimumSize(1100, 720)

        self._data_thread: QThread | None = None
        self._data_worker: AutomaticDataWorker | None = None
        self._elevation_thread: QThread | None = None
        self._elevation_worker: AutomaticElevationWorker | None = None
        self._simulation_load_pending = True
        self._simulation_creating = False
        self._border_prompt_active = False
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
        self.route_selector.selectionChanged.connect(self._selection_changed)

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
        for key in DATASET_ORDER:
            dataset = DATASETS[key]
            self.dataset_combo.addItem(str(dataset["label"]), key)
        self.dataset_combo.setToolTip(
            "Regionale OSM-Daten werden lokal gespeichert. Bei einer grenzüberschreitenden "
            "Route wird auf den gemeinsamen DACH-Extrakt umgestellt. Höhenkacheln werden "
            "für die konkrete Route automatisch geladen und gecacht."
        )
        self.dataset_combo.currentIndexChanged.connect(self._dataset_combo_changed)
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

    @Slot(int)
    def _dataset_combo_changed(self, _index: int) -> None:
        dataset_key = str(self.dataset_combo.currentData())
        if not dataset_key:
            return
        cached = cached_dataset(dataset_key, self.data_root)
        if cached is not None:
            self._activate_prepared_data(cached, restored=True)
        elif dataset_key == "dach":
            self.data_status.setText(
                "DACH deckt Deutschland, Österreich und die Schweiz grenzüberschreitend ab. "
                "Der Geofabrik-Extrakt ist groß und wird erst nach Bestätigung geladen."
            )
            self.data_progress.setValue(0)
        else:
            self.data_status.setText(
                f"{DATASETS[dataset_key]['label']} ist noch nicht lokal vorbereitet. "
                "Der Button lädt nur fehlende Dateien; Höhendaten kommen automatisch entlang der Route."
            )
            self.data_progress.setValue(0)

    @Slot()
    def _restore_cached_dataset(self) -> None:
        saved = str(
            self.route_selector.settings.value("active_dataset_key", "") or ""
        )
        preferred = saved if saved in DATASETS else str(self.dataset_combo.currentData())
        keys = [preferred] + [key for key in DATASET_ORDER if key != preferred]
        for dataset_key in keys:
            result = cached_dataset(dataset_key, self.data_root)
            if result is None:
                continue
            index = self.dataset_combo.findData(dataset_key)
            self.dataset_combo.blockSignals(True)
            try:
                if index >= 0:
                    self.dataset_combo.setCurrentIndex(index)
            finally:
                self.dataset_combo.blockSignals(False)
            self._activate_prepared_data(result, restored=True)
            return

        self.data_status.setText(
            "Noch kein lokaler Routingdatensatz erkannt. Gebiet wählen und einmalig vorbereiten; "
            "danach werden OSM und Höhenkacheln aus dem Cache wiederverwendet."
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
        if dataset_key:
            self.route_selector.settings.setValue("active_dataset_key", dataset_key)
        self.data_progress.setValue(100)
        label = str(DATASETS.get(dataset_key, {}).get("label", dataset_key))
        if restored and dem_file:
            self.data_status.setText(
                f"✓ {label}: vorhandene OSM-, Routing- und Höhendaten automatisch aktiviert."
            )
        elif restored:
            self.data_status.setText(
                f"✓ {label}: lokaler Routingindex automatisch aktiviert. "
                "Benötigte Höhenkacheln werden nach der Routenberechnung automatisch ergänzt."
            )
        elif dem_file and self.speed_profile is None:
            self.data_status.setText(
                f"Fertig: {label}-Routing und Höhenmodell sind lokal bereit."
            )
        elif dem_file:
            self.data_status.setText(
                f"Fertig: {label}-Routing und Höhenmodell sind aktiv."
            )
        else:
            self.data_status.setText(
                f"Fertig: {label}-Routing ist aktiv. Höhenkacheln folgen automatisch mit der Route."
            )

        self.route_selector.statusChanged.emit(
            "Lokale Straßendaten sind aktiv – Start und Ziel auswählen."
        )

    @Slot("QVariantMap")
    def _selection_changed(self, data: dict[str, Any]) -> None:
        if self._border_prompt_active or self._data_thread is not None:
            return
        dataset_key = self._active_dataset_key
        if not dataset_key or dataset_key == "dach":
            return
        points = data.get("points", []) if isinstance(data, dict) else []
        if not isinstance(points, list) or len(points) < 2:
            return

        inside = points_within_dataset(dataset_key, self.data_root, points)
        if inside is not False:
            return

        dach_index = self.dataset_combo.findData("dach")
        if dach_index >= 0:
            self.dataset_combo.blockSignals(True)
            try:
                self.dataset_combo.setCurrentIndex(dach_index)
            finally:
                self.dataset_combo.blockSignals(False)

        cached = cached_dataset("dach", self.data_root)
        if cached is not None:
            self._activate_prepared_data(cached, restored=True)
            self.data_status.setText(
                "Grenzübertritt erkannt: vorhandener DACH-Routingindex wurde automatisch aktiviert."
            )
            return

        self._border_prompt_active = True
        try:
            answer = QMessageBox.question(
                self,
                "Route verlässt das gewählte Gebiet",
                "Mindestens ein ausgewählter Punkt liegt außerhalb des aktiven regionalen "
                "Geofabrik-Extrakts. Für eine durchgehende Route über Gebiets- oder Landesgrenzen "
                "kann die App den gemeinsamen DACH-Datensatz (Deutschland, Österreich, Schweiz) "
                "automatisch herunterladen und lokal indexieren. Der OSM-PBF ist etwa 5,8 GB groß.\n\n"
                "DACH jetzt automatisch vorbereiten?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        finally:
            self._border_prompt_active = False

        if answer == QMessageBox.StandardButton.Yes:
            self._start_dataset_preparation("dach", confirm_large=False)
        else:
            self.data_status.setText(
                "Grenzübertritt erkannt. Mit dem regionalen Extrakt kann die Route außerhalb des "
                "Gebiets unvollständig sein; für Grenzfahrten DACH vorbereiten."
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
        dataset_key = str(self.dataset_combo.currentData())
        self._start_dataset_preparation(dataset_key, confirm_large=True)

    def _start_dataset_preparation(
        self,
        dataset_key: str,
        *,
        confirm_large: bool,
    ) -> None:
        if self._data_thread is not None or dataset_key not in DATASETS:
            return

        if confirm_large and bool(DATASETS[dataset_key].get("large_download")):
            answer = QMessageBox.question(
                self,
                "Großer grenzüberschreitender Datensatz",
                "Der Geofabrik-DACH-Extrakt umfasst Deutschland, Österreich und die Schweiz und "
                "ist aktuell etwa 5,8 GB groß. Er ist nur nötig, wenn eine Route Gebiets- oder "
                "Landesgrenzen überschreiten soll.\n\nDatensatz jetzt automatisch herunterladen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        cached = cached_dataset(dataset_key, self.data_root)
        if cached is not None:
            self._activate_prepared_data(cached, restored=True)
            return

        self.prepare_data_button.setEnabled(False)
        self.dataset_combo.setEnabled(False)
        self.data_progress.setValue(0)
        self.data_status.setText("Prüfe lokale Dateien und lade nur fehlende Routingdaten …")

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
    app._main_window = window  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
