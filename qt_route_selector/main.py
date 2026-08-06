from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QSettings, QThread, Signal, Slot
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import QApplication, QFileDialog

from local_router import RoutingError, calculate_route
from map_data import load_map_features
from offline_map import OfflineMapItem


class RoutingWorker(QObject):
    finished = Signal("QVariantMap")
    failed = Signal(str)

    def __init__(
        self,
        roads_path: str,
        start: tuple[float, float],
        target: tuple[float, float],
        bbox: dict[str, float],
    ) -> None:
        super().__init__()
        self.roads_path = roads_path
        self.start = start
        self.target = target
        self.bbox = bbox

    @Slot()
    def run(self) -> None:
        try:
            result = calculate_route(
                roads_path=self.roads_path,
                start=self.start,
                target=self.target,
                bbox=self.bbox,
            )
        except RoutingError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unerwarteter Routingfehler: {exc}")
        else:
            self.finished.emit(result)


class MapDataWorker(QObject):
    finished = Signal("QVariantMap")
    failed = Signal(str)

    def __init__(
        self,
        roads_path: str,
        bbox: dict[str, float],
    ) -> None:
        super().__init__()
        self.roads_path = roads_path
        self.bbox = bbox

    @Slot()
    def run(self) -> None:
        try:
            result = load_map_features(
                roads_path=self.roads_path,
                bbox=self.bbox,
            )
        except RoutingError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Kartendaten konnten nicht geladen werden: {exc}")
        else:
            self.finished.emit(result)


class RouteSelector(QObject):
    selectionChanged = Signal("QVariantMap")
    routeChanged = Signal("QVariantList")
    signalsChanged = Signal("QVariantList")
    summaryChanged = Signal("QVariantMap")
    mapRoadsChanged = Signal("QVariantList")
    mapSummaryChanged = Signal("QVariantMap")
    statusChanged = Signal(str)
    roadsFileChanged = Signal()
    busyChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.points: list[tuple[float, float]] = []
        self.current_bbox: dict[str, float] | None = None
        self.settings = QSettings("GPSDrivingSimulation", "QtRouteSelector")
        self._roads_file = str(self.settings.value("roads_file", "") or "")
        self._busy = False
        self._thread: QThread | None = None
        self._worker: QObject | None = None

    @Property(str, notify=roadsFileChanged)
    def roadsFile(self) -> str:
        return self._roads_file

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    def _set_busy(self, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    @staticmethod
    def _air_distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
        lat1, lon1 = map(math.radians, a)
        lat2, lon2 = map(math.radians, b)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        value = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        )
        return 6_371_008.8 * 2.0 * math.atan2(
            math.sqrt(value), math.sqrt(max(0.0, 1.0 - value))
        )

    @classmethod
    def bbox(cls, a: tuple[float, float], b: tuple[float, float]) -> dict[str, float]:
        distance_m = cls._air_distance_m(a, b)
        margin_m = max(5_000.0, distance_m * 0.25)
        mean_latitude = math.radians((a[0] + b[0]) / 2.0)
        lat_margin = margin_m / 111_320.0
        lon_scale = max(111_320.0 * math.cos(mean_latitude), 1.0)
        lon_margin = margin_m / lon_scale
        return {
            "south": min(a[0], b[0]) - lat_margin,
            "north": max(a[0], b[0]) + lat_margin,
            "west": min(a[1], b[1]) - lon_margin,
            "east": max(a[1], b[1]) + lon_margin,
            "air_distance_km": distance_m / 1000.0,
            "margin_km": margin_m / 1000.0,
        }

    def _selection_payload(self) -> dict[str, Any]:
        return {
            "points": [list(point) for point in self.points],
            "bbox": self.current_bbox,
            "roads_file": self._roads_file,
        }

    def _clear_route_display(self) -> None:
        self.routeChanged.emit([])
        self.signalsChanged.emit([])
        self.summaryChanged.emit({})

    def _start_thread(
        self,
        worker: QObject,
        finished_signal: Signal,
        finished_slot: Any,
        failed_signal: Signal,
        failed_slot: Any,
    ) -> None:
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)  # type: ignore[attr-defined]
        finished_signal.connect(finished_slot)
        failed_signal.connect(failed_slot)
        finished_signal.connect(worker.deleteLater)
        failed_signal.connect(worker.deleteLater)
        finished_signal.connect(self._thread.quit)
        failed_signal.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._worker_cleanup)
        self._thread.start()

    @Slot(float, float)
    def selectPoint(self, lat: float, lon: float) -> None:
        if self._busy:
            return
        if len(self.points) >= 2:
            self.points.clear()
            self.current_bbox = None
            self._clear_route_display()

        self.points.append((float(lat), float(lon)))
        if len(self.points) == 2:
            self.current_bbox = self.bbox(*self.points)
            payload = self._selection_payload()
            Path("selected_region.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.statusChanged.emit(
                "Start und Ziel gewählt – Route kann lokal berechnet werden."
            )
        else:
            self.statusChanged.emit("Start gewählt – jetzt den Zielpunkt anklicken.")

        self.selectionChanged.emit(self._selection_payload())

    @Slot()
    def resetSelection(self) -> None:
        if self._busy:
            return
        self.points.clear()
        self.current_bbox = None
        self.selectionChanged.emit(self._selection_payload())
        self._clear_route_display()
        self.statusChanged.emit("Auswahl gelöscht – Startpunkt anklicken.")

    @Slot()
    def chooseRoadData(self) -> None:
        if self._busy:
            return
        initial = str(Path(self._roads_file).parent) if self._roads_file else str(Path.cwd())
        selected, _ = QFileDialog.getOpenFileName(
            None,
            "Lokale Straßendaten auswählen",
            initial,
            "Routingdaten (*.fgb *.gpkg *.geojson *.shp *.osm.pbf *.pbf);;"
            "OSM PBF (*.osm.pbf *.pbf);;Alle Dateien (*)",
        )
        if not selected:
            return
        self._roads_file = str(Path(selected).resolve())
        self.settings.setValue("roads_file", self._roads_file)
        self.roadsFileChanged.emit()
        self.selectionChanged.emit(self._selection_payload())
        if self._roads_file.lower().endswith((".osm.pbf", ".pbf")):
            self.statusChanged.emit(
                "OSM-PBF gewählt – der sichtbare Ausschnitt wird lokal eingelesen."
            )
        else:
            self.statusChanged.emit(f"Straßendatei gewählt: {Path(selected).name}")

    @Slot("QVariantMap")
    def loadRoadMap(self, bbox: dict[str, float]) -> None:
        if self._busy:
            return
        if not self._roads_file:
            self.statusChanged.emit("Bitte zuerst lokale Straßendaten auswählen.")
            return
        if not Path(self._roads_file).is_file():
            self.statusChanged.emit("Die gespeicherte Straßendatei wurde nicht gefunden.")
            return
        required = {"west", "south", "east", "north"}
        if not bbox or not required.issubset(bbox):
            self.statusChanged.emit("Der sichtbare Kartenausschnitt ist ungültig.")
            return

        self._set_busy(True)
        self.statusChanged.emit("Lokale Straßen für den sichtbaren Ausschnitt werden geladen …")
        worker = MapDataWorker(self._roads_file, dict(bbox))
        self._start_thread(
            worker,
            worker.finished,
            self._map_finished,
            worker.failed,
            self._map_failed,
        )

    @Slot()
    def calculateRoute(self) -> None:
        if self._busy:
            return
        if len(self.points) != 2 or self.current_bbox is None:
            self.statusChanged.emit("Bitte zuerst Start und Ziel auf der Karte auswählen.")
            return
        if not self._roads_file:
            self.statusChanged.emit("Bitte zuerst lokale Straßendaten auswählen.")
            return
        if not Path(self._roads_file).is_file():
            self.statusChanged.emit("Die gespeicherte Straßendatei wurde nicht gefunden.")
            return

        self._set_busy(True)
        self._clear_route_display()
        self.statusChanged.emit("Region wird geladen und Routinggraph wird aufgebaut …")
        worker = RoutingWorker(
            self._roads_file,
            self.points[0],
            self.points[1],
            dict(self.current_bbox),
        )
        self._start_thread(
            worker,
            worker.finished,
            self._route_finished,
            worker.failed,
            self._route_failed,
        )

    @Slot("QVariantMap")
    def _map_finished(self, result: dict[str, Any]) -> None:
        features = result.get("features", [])
        summary = result.get("summary", {})
        self.mapRoadsChanged.emit(features)
        self.mapSummaryChanged.emit(summary)
        suffix = " (Anzeige begrenzt)" if summary.get("truncated") else ""
        self.statusChanged.emit(
            f"Offline-Karte geladen: {summary.get('display_lines', 0)} Linien, "
            f"{summary.get('display_vertices', 0)} Punkte{suffix}."
        )
        self._set_busy(False)

    @Slot(str)
    def _map_failed(self, message: str) -> None:
        self.statusChanged.emit(message)
        self._set_busy(False)

    @Slot("QVariantMap")
    def _route_finished(self, result: dict[str, Any]) -> None:
        output = {
            "selection": self._selection_payload(),
            **result,
        }
        Path("route_result.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.routeChanged.emit(result.get("coordinates", []))
        self.signalsChanged.emit(result.get("traffic_signals", []))
        summary = result.get("summary", {})
        self.summaryChanged.emit(summary)
        self.statusChanged.emit(
            f"Route berechnet: {summary.get('distance_km', 0.0):.2f} km, "
            f"ca. {summary.get('estimated_minutes', 0.0):.1f} min."
        )
        self._set_busy(False)

    @Slot(str)
    def _route_failed(self, message: str) -> None:
        self.statusChanged.emit(message)
        self._set_busy(False)

    @Slot()
    def _worker_cleanup(self) -> None:
        self._worker = None
        self._thread = None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GPS Route Selector")
    app.setOrganizationName("GPSDrivingSimulation")

    qmlRegisterType(OfflineMapItem, "OfflineMap", 1, 0, "OfflineMapItem")

    engine = QQmlApplicationEngine()
    selector = RouteSelector()
    engine.rootContext().setContextProperty("routeSelector", selector)
    engine.load(str(Path(__file__).with_name("main.qml")))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
