from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    QSettings,
    QThread,
    QTimer,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import QApplication, QFileDialog

from local_router import RoutingError, calculate_route
from map_data import load_map_features
from offline_map import OfflineMapItem
from routing_cache import build_routing_cache, default_cache_path


class RoutePointModel(QAbstractListModel):
    LatitudeRole = Qt.ItemDataRole.UserRole + 1
    LongitudeRole = Qt.ItemDataRole.UserRole + 2
    IndexRole = Qt.ItemDataRole.UserRole + 3
    KindRole = Qt.ItemDataRole.UserRole + 4
    LabelRole = Qt.ItemDataRole.UserRole + 5

    def __init__(self) -> None:
        super().__init__()
        self._points: list[dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._points)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._points):
            return None
        point = self._points[index.row()]
        mapping = {
            self.LatitudeRole: "latitude",
            self.LongitudeRole: "longitude",
            self.IndexRole: "pointIndex",
            self.KindRole: "pointKind",
            self.LabelRole: "pointLabel",
        }
        key = mapping.get(role)
        return point.get(key) if key else None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.LatitudeRole: b"latitude",
            self.LongitudeRole: b"longitude",
            self.IndexRole: b"pointIndex",
            self.KindRole: b"pointKind",
            self.LabelRole: b"pointLabel",
        }

    def set_points(self, points: list[tuple[float, float]]) -> None:
        mapped: list[dict[str, Any]] = []
        last_index = len(points) - 1
        for index, (latitude, longitude) in enumerate(points):
            if index == 0:
                kind, label = "start", "S"
            elif index == last_index:
                kind, label = "target", "Z"
            else:
                kind, label = "waypoint", str(index)
            mapped.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "pointIndex": index,
                    "pointKind": kind,
                    "pointLabel": label,
                }
            )
        self.beginResetModel()
        self._points = mapped
        self.endResetModel()


class TrafficSignalModel(QAbstractListModel):
    LatitudeRole = Qt.ItemDataRole.UserRole + 1
    LongitudeRole = Qt.ItemDataRole.UserRole + 2
    DistanceRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self) -> None:
        super().__init__()
        self._points: list[dict[str, float]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._points)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._points):
            return None
        point = self._points[index.row()]
        if role == self.LatitudeRole:
            return point["latitude"]
        if role == self.LongitudeRole:
            return point["longitude"]
        if role == self.DistanceRole:
            return point["distance_from_start_m"]
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.LatitudeRole: b"latitude",
            self.LongitudeRole: b"longitude",
            self.DistanceRole: b"distanceFromStartM",
        }

    def set_points(self, points: list[dict[str, float]]) -> None:
        self.beginResetModel()
        self._points = list(points)
        self.endResetModel()


class RoutingWorker(QObject):
    finished = Signal("QVariantMap")
    failed = Signal(str)

    def __init__(
        self,
        roads_path: str,
        points: list[tuple[float, float]],
        bbox: dict[str, float],
        routing_profile: str,
    ) -> None:
        super().__init__()
        self.roads_path = roads_path
        self.points = points
        self.bbox = bbox
        self.routing_profile = routing_profile

    @Slot()
    def run(self) -> None:
        try:
            result = calculate_route(
                roads_path=self.roads_path,
                points=self.points,
                bbox=self.bbox,
                routing_profile=self.routing_profile,
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

    def __init__(self, roads_path: str, bbox: dict[str, float], zoom_level: float) -> None:
        super().__init__()
        self.roads_path = roads_path
        self.bbox = bbox
        self.zoom_level = zoom_level

    @Slot()
    def run(self) -> None:
        try:
            result = load_map_features(
                roads_path=self.roads_path,
                bbox=self.bbox,
                zoom_level=self.zoom_level,
            )
        except RoutingError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Kartendaten konnten nicht geladen werden: {exc}")
        else:
            self.finished.emit(result)


class CacheBuildWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, source_path: str) -> None:
        super().__init__()
        self.source_path = source_path

    @Slot()
    def run(self) -> None:
        try:
            output = build_routing_cache(
                self.source_path,
                progress=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(f"PBF-Index konnte nicht erstellt werden: {exc}")
        else:
            self.finished.emit(str(output))


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
    pointCountChanged = Signal()
    mapModeChanged = Signal()
    mapPreferenceChanged = Signal()
    mapModeReasonChanged = Signal()
    routingProfileChanged = Signal()
    automaticOfflineReloadChanged = Signal()
    pbfSourceChanged = Signal()

    def __init__(
        self,
        route_point_model: RoutePointModel,
        traffic_signal_model: TrafficSignalModel,
    ) -> None:
        super().__init__()
        self.points: list[tuple[float, float]] = []
        self.current_bbox: dict[str, float] | None = None
        self.route_point_model = route_point_model
        self.traffic_signal_model = traffic_signal_model
        self.settings = QSettings("GPSDrivingSimulation", "QtRouteSelector")
        self._roads_file = str(self.settings.value("roads_file", "") or "")
        self._busy = False
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._routing_profile = str(
            self.settings.value("routing_profile", "preferred") or "preferred"
        )
        self._map_preference = str(
            self.settings.value("map_preference", "auto") or "auto"
        )
        self._map_mode = "offline" if self._map_preference == "offline" else "online"
        self._map_mode_reason = "Online-OSM wird geprüft …"

        self._network_manager = QNetworkAccessManager(self)
        try:
            self._network_manager.setTransferTimeout(3500)
        except (AttributeError, TypeError):
            pass
        self._probe_reply: QNetworkReply | None = None
        self._probe_timer = QTimer(self)
        self._probe_timer.setInterval(300_000)
        self._probe_timer.timeout.connect(self._probe_online_map)
        self._probe_timer.start()
        QTimer.singleShot(0, self._probe_online_map)

    @Property(str, notify=roadsFileChanged)
    def roadsFile(self) -> str:
        return self._roads_file

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(int, notify=pointCountChanged)
    def pointCount(self) -> int:
        return len(self.points)

    @Property(str, notify=mapModeChanged)
    def mapMode(self) -> str:
        return self._map_mode

    @Property(str, notify=mapPreferenceChanged)
    def mapPreference(self) -> str:
        return self._map_preference

    @Property(str, notify=mapModeReasonChanged)
    def mapModeReason(self) -> str:
        return self._map_mode_reason

    @Property(str, notify=routingProfileChanged)
    def routingProfile(self) -> str:
        return self._routing_profile

    @Property(bool, notify=automaticOfflineReloadChanged)
    def automaticOfflineReload(self) -> bool:
        return bool(self._roads_file) and not self.isPbfSource

    @Property(bool, notify=pbfSourceChanged)
    def isPbfSource(self) -> bool:
        return self._roads_file.lower().endswith((".osm.pbf", ".pbf"))

    def _set_busy(self, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    def _set_map_mode(self, mode: str, reason: str) -> None:
        mode = "online" if mode == "online" else "offline"
        if self._map_mode != mode:
            self._map_mode = mode
            self.mapModeChanged.emit()
        if self._map_mode_reason != reason:
            self._map_mode_reason = reason
            self.mapModeReasonChanged.emit()

    @Slot(str)
    def setMapPreference(self, preference: str) -> None:
        if preference not in {"auto", "online", "offline"}:
            return
        if self._map_preference != preference:
            self._map_preference = preference
            self.settings.setValue("map_preference", preference)
            self.mapPreferenceChanged.emit()
        if preference == "offline":
            self._set_map_mode("offline", "Offline-Modus wurde manuell gewählt.")
        elif preference == "online":
            self._set_map_mode("online", "Online-OSM wurde manuell gewählt.")
        else:
            self._set_map_mode("online", "Online-OSM wird geprüft …")
            self._probe_online_map()

    @Slot(str)
    def reportOnlineMapError(self, message: str) -> None:
        if self._map_preference == "auto":
            detail = message.strip() or "Online-Kartenquelle nicht erreichbar"
            self._set_map_mode("offline", f"{detail}; lokale Karte wird verwendet.")

    @Slot()
    def retryOnlineMap(self) -> None:
        if self._map_preference == "offline":
            return
        self._probe_online_map()

    def _probe_online_map(self) -> None:
        if self._map_preference == "offline" or self._probe_reply is not None:
            return
        request = QNetworkRequest(QUrl("https://tile.openstreetmap.org/0/0/0.png"))
        request.setRawHeader(
            b"User-Agent",
            b"GeschwindigkeitsverlaufAusGPS/0.2 (Qt research application)",
        )
        self._probe_reply = self._network_manager.head(request)
        self._probe_reply.finished.connect(self._online_probe_finished)

    @Slot()
    def _online_probe_finished(self) -> None:
        reply = self._probe_reply
        self._probe_reply = None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        success = (
            reply.error() == QNetworkReply.NetworkError.NoError
            and status is not None
            and 200 <= int(status) < 400
        )
        error_text = reply.errorString()
        reply.deleteLater()
        if self._map_preference == "auto":
            if success:
                self._set_map_mode("online", "Online-OSM verfügbar.")
            else:
                self._set_map_mode(
                    "offline",
                    f"Online-OSM nicht erreichbar ({error_text}); lokale Karte aktiv.",
                )

    @Slot(str)
    def setRoutingProfile(self, profile: str) -> None:
        if profile not in {"preferred", "fastest", "shortest"}:
            return
        if self._routing_profile != profile:
            self._routing_profile = profile
            self.settings.setValue("routing_profile", profile)
            self.routingProfileChanged.emit()
            self._clear_route_display()
            self.statusChanged.emit("Routingprofil geändert – Route neu berechnen.")

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
    def bbox_for_points(cls, points: list[tuple[float, float]]) -> dict[str, float]:
        latitudes = [point[0] for point in points]
        longitudes = [point[1] for point in points]
        air_distance_m = sum(
            cls._air_distance_m(a, b) for a, b in zip(points[:-1], points[1:])
        )
        margin_m = max(5_000.0, air_distance_m * 0.20)
        mean_latitude = math.radians(sum(latitudes) / len(latitudes))
        lat_margin = margin_m / 111_320.0
        lon_scale = max(111_320.0 * math.cos(mean_latitude), 1.0)
        lon_margin = margin_m / lon_scale
        return {
            "south": min(latitudes) - lat_margin,
            "north": max(latitudes) + lat_margin,
            "west": min(longitudes) - lon_margin,
            "east": max(longitudes) + lon_margin,
            "air_distance_km": air_distance_m / 1000.0,
            "margin_km": margin_m / 1000.0,
        }

    def _selection_payload(self) -> dict[str, Any]:
        return {
            "points": [list(point) for point in self.points],
            "bbox": self.current_bbox,
            "roads_file": self._roads_file,
        }

    def _file_metadata_payload(self) -> dict[str, Any]:
        now = datetime.now().astimezone()
        start = self.points[0] if self.points else None
        end = self.points[-1] if len(self.points) >= 2 else None
        return {
            "created_at": now.isoformat(timespec="seconds"),
            "created_date": now.date().isoformat(),
            "created_time": now.strftime("%H:%M:%S"),
            "timezone": now.tzname() or "local",
            "start_gps": (
                {"latitude": float(start[0]), "longitude": float(start[1])}
                if start is not None
                else None
            ),
            "end_gps": (
                {"latitude": float(end[0]), "longitude": float(end[1])}
                if end is not None
                else None
            ),
            "waypoint_count": max(0, len(self.points) - 2),
            "routing_profile": self._routing_profile,
        }

    def _update_point_models(self) -> None:
        self.route_point_model.set_points(self.points)
        self.pointCountChanged.emit()
        self.selectionChanged.emit(self._selection_payload())

    def _clear_route_display(self) -> None:
        self.routeChanged.emit([])
        self.signalsChanged.emit([])
        self.traffic_signal_model.set_points([])
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
        self.points.append((float(lat), float(lon)))
        self._clear_route_display()
        self.current_bbox = self.bbox_for_points(self.points) if len(self.points) >= 2 else None
        if len(self.points) >= 2:
            selection_output = {
                "metadata": self._file_metadata_payload(),
                **self._selection_payload(),
            }
            Path("selected_region.json").write_text(
                json.dumps(selection_output, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            waypoint_count = max(0, len(self.points) - 2)
            self.statusChanged.emit(
                f"{len(self.points)} Punkte gewählt ({waypoint_count} Zwischenziele). "
                "Weitere Punkte sind möglich oder Route berechnen."
            )
        else:
            self.statusChanged.emit("Start gewählt – Ziel oder erstes Zwischenziel anklicken.")
        self._update_point_models()

    @Slot()
    def undoLastPoint(self) -> None:
        if self._busy or not self.points:
            return
        self.points.pop()
        self.current_bbox = self.bbox_for_points(self.points) if len(self.points) >= 2 else None
        self._clear_route_display()
        self._update_point_models()
        self.statusChanged.emit(
            "Letzten Punkt entfernt."
            if self.points
            else "Alle Punkte entfernt – Startpunkt anklicken."
        )

    @Slot()
    def resetSelection(self) -> None:
        if self._busy:
            return
        self.points.clear()
        self.current_bbox = None
        self._clear_route_display()
        self._update_point_models()
        self.statusChanged.emit("Auswahl gelöscht – Startpunkt anklicken.")

    def _set_roads_file(self, selected: str) -> None:
        old_pbf = self.isPbfSource
        self._roads_file = str(Path(selected).resolve())
        self.settings.setValue("roads_file", self._roads_file)
        self.roadsFileChanged.emit()
        if old_pbf != self.isPbfSource:
            self.pbfSourceChanged.emit()
        self.automaticOfflineReloadChanged.emit()
        self.selectionChanged.emit(self._selection_payload())

    @Slot()
    def chooseRoadData(self) -> None:
        if self._busy:
            return
        initial = str(Path(self._roads_file).parent) if self._roads_file else str(Path.cwd())
        selected, _ = QFileDialog.getOpenFileName(
            None,
            "Lokale Straßendaten auswählen",
            initial,
            "Routingdaten (*.gpkg *.fgb *.geojson *.shp *.osm.pbf *.pbf);;"
            "OSM PBF (*.osm.pbf *.pbf);;Alle Dateien (*)",
        )
        if not selected:
            return
        selected_path = Path(selected).resolve()
        if selected_path.name.lower().endswith((".osm.pbf", ".pbf")):
            cached = default_cache_path(selected_path)
            if cached.is_file() and cached.stat().st_mtime_ns >= selected_path.stat().st_mtime_ns:
                self._set_roads_file(str(cached))
                self.statusChanged.emit(f"Vorhandener Schnellindex verwendet: {cached.name}")
                return
        self._set_roads_file(str(selected_path))
        if self.isPbfSource:
            self.statusChanged.emit(
                "PBF gewählt. Online-Karte bleibt schnell; für schnelles Offline-Panning und "
                "Routing bitte einmalig den PBF-Schnellindex erstellen."
            )
        else:
            self.statusChanged.emit(f"Straßendatei gewählt: {selected_path.name}")

    @Slot()
    def buildPbfIndex(self) -> None:
        if self._busy or not self.isPbfSource:
            return
        source = Path(self._roads_file)
        if not source.is_file():
            self.statusChanged.emit("Die PBF-Datei wurde nicht gefunden.")
            return
        self._set_busy(True)
        worker = CacheBuildWorker(str(source))
        worker.progress.connect(self.statusChanged.emit)
        self._start_thread(
            worker,
            worker.finished,
            self._cache_finished,
            worker.failed,
            self._cache_failed,
        )

    @Slot(str)
    def _cache_finished(self, output_path: str) -> None:
        self._set_roads_file(output_path)
        self.statusChanged.emit(f"Schnellindex erstellt und aktiviert: {Path(output_path).name}")
        self._set_busy(False)

    @Slot(str)
    def _cache_failed(self, message: str) -> None:
        self.statusChanged.emit(message)
        self._set_busy(False)

    @Slot("QVariantMap", float)
    def loadRoadMap(self, bbox: dict[str, float], zoom_level: float = 12.0) -> None:
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
        source_note = "PBF-Scan" if self.isPbfSource else "räumlicher Index"
        self.statusChanged.emit(f"Lokale Straßen werden geladen ({source_note}) …")
        worker = MapDataWorker(self._roads_file, dict(bbox), float(zoom_level))
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
        if len(self.points) < 2 or self.current_bbox is None:
            self.statusChanged.emit("Bitte mindestens Start und Ziel auswählen.")
            return
        if not self._roads_file:
            self.statusChanged.emit("Bitte zuerst lokale Straßendaten auswählen.")
            return
        if not Path(self._roads_file).is_file():
            self.statusChanged.emit("Die gespeicherte Straßendatei wurde nicht gefunden.")
            return

        self._set_busy(True)
        self._clear_route_display()
        if self.isPbfSource:
            self.statusChanged.emit(
                "PBF wird sequenziell gelesen. Der erste Lauf kann lange dauern; "
                "ein Schnellindex beschleunigt weitere Berechnungen deutlich …"
            )
        else:
            self.statusChanged.emit("Routinggraph wird aufgebaut bzw. aus dem Cache geladen …")
        worker = RoutingWorker(
            self._roads_file,
            list(self.points),
            dict(self.current_bbox),
            self._routing_profile,
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
        cache_note = " aus Cache" if summary.get("cache_hit") else ""
        self.statusChanged.emit(
            f"Offline-Karte{cache_note}: {summary.get('display_lines', 0)} Linien, "
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
            "metadata": self._file_metadata_payload(),
            "selection": self._selection_payload(),
            **result,
        }
        Path("route_result.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        route_points = result.get("coordinates", [])
        signal_points = result.get("traffic_signals", [])
        self.routeChanged.emit(route_points)
        self.signalsChanged.emit(signal_points)
        self.traffic_signal_model.set_points(signal_points)
        summary = result.get("summary", {})
        self.summaryChanged.emit(summary)
        cache_note = " (Graph-Cache)" if summary.get("graph_cache_hit") else ""
        self.statusChanged.emit(
            f"Route berechnet: {summary.get('distance_km', 0.0):.2f} km, "
            f"ca. {summary.get('estimated_minutes', 0.0):.1f} min{cache_note}."
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
    route_point_model = RoutePointModel()
    traffic_signal_model = TrafficSignalModel()
    selector = RouteSelector(route_point_model, traffic_signal_model)
    engine.rootContext().setContextProperty("routeSelector", selector)
    engine.rootContext().setContextProperty("routePointModel", route_point_model)
    engine.rootContext().setContextProperty("trafficSignalModel", traffic_signal_model)
    engine.load(str(Path(__file__).with_name("main.qml")))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
