from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Property, QPointF, QRectF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtQuick import QQuickPaintedItem


EARTH_RADIUS_M = 6_378_137.0
TILE_SIZE = 256.0
MAX_MERCATOR_LATITUDE = 85.05112878


ROAD_STYLES: dict[str, tuple[str, float]] = {
    "motorway": ("#d88b52", 4.8),
    "motorway_link": ("#e1a16e", 3.6),
    "trunk": ("#d9a45d", 4.4),
    "trunk_link": ("#e2b57b", 3.4),
    "primary": ("#d8b66b", 4.0),
    "primary_link": ("#e3c68e", 3.2),
    "secondary": ("#c5b98c", 3.4),
    "secondary_link": ("#d2c9a8", 2.8),
    "tertiary": ("#b8b4a1", 3.0),
    "tertiary_link": ("#c9c6b7", 2.5),
    "residential": ("#c5c8ca", 2.1),
    "living_street": ("#c9ccce", 2.0),
    "unclassified": ("#bfc3c5", 2.1),
    "service": ("#d1d3d4", 1.6),
    "track": ("#c7b99d", 1.2),
}


def _clamp_latitude(latitude: float) -> float:
    return max(-MAX_MERCATOR_LATITUDE, min(MAX_MERCATOR_LATITUDE, latitude))


def geo_to_world(latitude: float, longitude: float, zoom: float) -> QPointF:
    latitude = _clamp_latitude(latitude)
    world_size = TILE_SIZE * (2.0**zoom)
    x = (longitude + 180.0) / 360.0 * world_size
    latitude_radians = math.radians(latitude)
    mercator = math.asinh(math.tan(latitude_radians))
    y = (1.0 - mercator / math.pi) / 2.0 * world_size
    return QPointF(x, y)


def world_to_geo(x: float, y: float, zoom: float) -> tuple[float, float]:
    world_size = TILE_SIZE * (2.0**zoom)
    longitude = x / world_size * 360.0 - 180.0
    mercator = math.pi * (1.0 - 2.0 * y / world_size)
    latitude = math.degrees(math.atan(math.sinh(mercator)))
    return _clamp_latitude(latitude), longitude


def _nice_scale_length(value_m: float) -> float:
    if value_m <= 0.0:
        return 1.0
    exponent = 10.0 ** math.floor(math.log10(value_m))
    normalized = value_m / exponent
    if normalized >= 5.0:
        factor = 5.0
    elif normalized >= 2.0:
        factor = 2.0
    else:
        factor = 1.0
    return factor * exponent


class OfflineMapItem(QQuickPaintedItem):
    """Simple native vector map for local OSM-derived road geometries.

    The item performs Web-Mercator projection, pan/zoom interaction and
    coordinate selection itself. It never requests network resources.
    """

    coordinateClicked = Signal(float, float)
    viewportChanged = Signal("QVariantMap")
    centerChanged = Signal()
    zoomLevelChanged = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setAntialiasing(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)

        self._center_latitude = 48.743
        self._center_longitude = 9.320
        self._zoom_level = 12.0

        self._roads: list[dict[str, Any]] = []
        self._route: list[tuple[float, float]] = []
        self._signals: list[tuple[float, float, float]] = []
        self._start: tuple[float, float] | None = None
        self._target: tuple[float, float] | None = None
        self._selection_bbox: dict[str, float] | None = None

        self._pressed = False
        self._press_position = QPointF()
        self._last_position = QPointF()
        self._drag_distance = 0.0

    @Property(float, notify=centerChanged)
    def centerLatitude(self) -> float:
        return self._center_latitude

    @centerLatitude.setter
    def centerLatitude(self, value: float) -> None:
        value = _clamp_latitude(float(value))
        if not math.isclose(value, self._center_latitude):
            self._center_latitude = value
            self.centerChanged.emit()
            self.update()
            self._emit_viewport()

    @Property(float, notify=centerChanged)
    def centerLongitude(self) -> float:
        return self._center_longitude

    @centerLongitude.setter
    def centerLongitude(self, value: float) -> None:
        value = float(value)
        if not math.isclose(value, self._center_longitude):
            self._center_longitude = value
            self.centerChanged.emit()
            self.update()
            self._emit_viewport()

    @Property(float, notify=zoomLevelChanged)
    def zoomLevel(self) -> float:
        return self._zoom_level

    @zoomLevel.setter
    def zoomLevel(self, value: float) -> None:
        value = max(3.0, min(20.0, float(value)))
        if not math.isclose(value, self._zoom_level):
            self._zoom_level = value
            self.zoomLevelChanged.emit()
            self.update()
            self._emit_viewport()

    def _center_world(self) -> QPointF:
        return geo_to_world(
            self._center_latitude,
            self._center_longitude,
            self._zoom_level,
        )

    def _geo_to_screen(self, latitude: float, longitude: float) -> QPointF:
        world = geo_to_world(latitude, longitude, self._zoom_level)
        center = self._center_world()
        return QPointF(
            world.x() - center.x() + self.width() / 2.0,
            world.y() - center.y() + self.height() / 2.0,
        )

    def _screen_to_geo(self, x: float, y: float) -> tuple[float, float]:
        center = self._center_world()
        world_x = center.x() + x - self.width() / 2.0
        world_y = center.y() + y - self.height() / 2.0
        return world_to_geo(world_x, world_y, self._zoom_level)

    @Slot(result="QVariantMap")
    def visibleBounds(self) -> dict[str, float]:
        north, west = self._screen_to_geo(0.0, 0.0)
        south, east = self._screen_to_geo(self.width(), self.height())
        return {
            "west": min(west, east),
            "south": min(south, north),
            "east": max(west, east),
            "north": max(south, north),
        }

    @Slot("QVariantList")
    def setRoads(self, features: list[dict[str, Any]]) -> None:
        roads: list[dict[str, Any]] = []
        for feature in features or []:
            raw_coordinates = feature.get("coordinates", [])
            coordinates: list[tuple[float, float]] = []
            for index in range(0, len(raw_coordinates) - 1, 2):
                coordinates.append(
                    (
                        float(raw_coordinates[index]),
                        float(raw_coordinates[index + 1]),
                    )
                )
            if len(coordinates) >= 2:
                roads.append(
                    {
                        "highway": str(feature.get("highway", "")),
                        "rank": int(feature.get("rank", 0)),
                        "coordinates": coordinates,
                    }
                )
        self._roads = sorted(roads, key=lambda item: item["rank"])
        self.update()

    @Slot("QVariantList")
    def setRoute(self, points: list[dict[str, Any]]) -> None:
        self._route = [
            (float(point["latitude"]), float(point["longitude"]))
            for point in points or []
            if "latitude" in point and "longitude" in point
        ]
        self.update()

    @Slot("QVariantList")
    def setSignals(self, points: list[dict[str, Any]]) -> None:
        self._signals = [
            (
                float(point["latitude"]),
                float(point["longitude"]),
                float(point.get("distance_from_start_m", 0.0)),
            )
            for point in points or []
            if "latitude" in point and "longitude" in point
        ]
        self.update()

    @Slot("QVariantMap")
    def setSelection(self, payload: dict[str, Any]) -> None:
        points = payload.get("points", []) if payload else []
        self._start = (
            (float(points[0][0]), float(points[0][1]))
            if len(points) >= 1
            else None
        )
        self._target = (
            (float(points[1][0]), float(points[1][1]))
            if len(points) >= 2
            else None
        )
        bbox = payload.get("bbox") if payload else None
        self._selection_bbox = dict(bbox) if bbox else None
        self.update()

    @Slot()
    def clearRoads(self) -> None:
        self._roads = []
        self.update()

    @Slot("QVariantMap", int)
    def fitBounds(self, bbox: dict[str, float], padding: int = 50) -> None:
        if not bbox or self.width() <= 1.0 or self.height() <= 1.0:
            return
        west = float(bbox["west"])
        east = float(bbox["east"])
        south = float(bbox["south"])
        north = float(bbox["north"])
        top_left = geo_to_world(north, west, 0.0)
        bottom_right = geo_to_world(south, east, 0.0)
        normalized_width = max(1e-12, abs(bottom_right.x() - top_left.x()))
        normalized_height = max(1e-12, abs(bottom_right.y() - top_left.y()))
        usable_width = max(1.0, self.width() - 2.0 * padding)
        usable_height = max(1.0, self.height() - 2.0 * padding)
        zoom_x = math.log2(usable_width / normalized_width / TILE_SIZE)
        zoom_y = math.log2(usable_height / normalized_height / TILE_SIZE)
        zoom = max(3.0, min(20.0, min(zoom_x, zoom_y)))
        self._center_latitude = (north + south) / 2.0
        self._center_longitude = (west + east) / 2.0
        self._zoom_level = zoom
        self.centerChanged.emit()
        self.zoomLevelChanged.emit()
        self.update()
        self._emit_viewport()

    @Slot()
    def fitRoute(self) -> None:
        if len(self._route) < 2:
            return
        latitudes = [point[0] for point in self._route]
        longitudes = [point[1] for point in self._route]
        self.fitBounds(
            {
                "west": min(longitudes),
                "south": min(latitudes),
                "east": max(longitudes),
                "north": max(latitudes),
            },
            70,
        )

    def _emit_viewport(self) -> None:
        if self.width() > 1.0 and self.height() > 1.0:
            self.viewportChanged.emit(self.visibleBounds())

    def _pan_pixels(self, dx: float, dy: float) -> None:
        center = self._center_world()
        latitude, longitude = world_to_geo(
            center.x() - dx,
            center.y() - dy,
            self._zoom_level,
        )
        self._center_latitude = latitude
        self._center_longitude = longitude
        self.centerChanged.emit()
        self.update()

    def _zoom_at(self, factor: float, position: QPointF) -> None:
        old_zoom = self._zoom_level
        new_zoom = max(3.0, min(20.0, old_zoom + math.log2(factor)))
        if math.isclose(old_zoom, new_zoom):
            return

        anchor_latitude, anchor_longitude = self._screen_to_geo(
            position.x(),
            position.y(),
        )
        anchor_world = geo_to_world(anchor_latitude, anchor_longitude, new_zoom)
        center_world = QPointF(
            anchor_world.x() - position.x() + self.width() / 2.0,
            anchor_world.y() - position.y() + self.height() / 2.0,
        )
        latitude, longitude = world_to_geo(
            center_world.x(),
            center_world.y(),
            new_zoom,
        )
        self._zoom_level = new_zoom
        self._center_latitude = latitude
        self._center_longitude = longitude
        self.centerChanged.emit()
        self.zoomLevelChanged.emit()
        self.update()
        self._emit_viewport()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._press_position = event.position()
            self._last_position = event.position()
            self._drag_distance = 0.0
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._pressed:
            event.ignore()
            return
        position = event.position()
        delta = position - self._last_position
        self._drag_distance += math.hypot(delta.x(), delta.y())
        self._pan_pixels(delta.x(), delta.y())
        self._last_position = position
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._pressed:
            event.ignore()
            return
        self._pressed = False
        if self._drag_distance < 6.0:
            latitude, longitude = self._screen_to_geo(
                event.position().x(),
                event.position().y(),
            )
            self.coordinateClicked.emit(latitude, longitude)
        else:
            self._emit_viewport()
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        if not math.isclose(steps, 0.0):
            self._zoom_at(2.0 ** (steps / 2.0), event.position())
        event.accept()

    def geometryChange(self, new_geometry: QRectF, old_geometry: QRectF) -> None:
        super().geometryChange(new_geometry, old_geometry)
        self.update()
        self._emit_viewport()

    def _road_pen(self, highway: str) -> QPen:
        color, base_width = ROAD_STYLES.get(highway, ("#c9ccce", 1.4))
        zoom_factor = max(0.55, min(2.0, 2.0 ** ((self._zoom_level - 13.0) / 4.0)))
        pen = QPen(QColor(color), base_width * zoom_factor)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _draw_polyline(
        self,
        painter: QPainter,
        coordinates: list[tuple[float, float]],
        pen: QPen,
    ) -> None:
        points = QPolygonF(
            [self._geo_to_screen(latitude, longitude) for latitude, longitude in coordinates]
        )
        if len(points) >= 2:
            painter.setPen(pen)
            painter.drawPolyline(points)

    def _draw_marker(
        self,
        painter: QPainter,
        coordinate: tuple[float, float],
        fill: QColor,
        radius: float,
    ) -> None:
        point = self._geo_to_screen(*coordinate)
        painter.setPen(QPen(QColor("white"), 2.5))
        painter.setBrush(fill)
        painter.drawEllipse(point, radius, radius)

    def _draw_selection_bbox(self, painter: QPainter) -> None:
        if not self._selection_bbox:
            return
        bbox = self._selection_bbox
        polygon = QPolygonF(
            [
                self._geo_to_screen(float(bbox["north"]), float(bbox["west"])),
                self._geo_to_screen(float(bbox["north"]), float(bbox["east"])),
                self._geo_to_screen(float(bbox["south"]), float(bbox["east"])),
                self._geo_to_screen(float(bbox["south"]), float(bbox["west"])),
            ]
        )
        painter.setPen(QPen(QColor("#4267d5"), 1.5))
        painter.setBrush(QColor(66, 103, 213, 28))
        painter.drawPolygon(polygon)

    def _draw_scale(self, painter: QPainter) -> None:
        meters_per_pixel = (
            math.cos(math.radians(self._center_latitude))
            * 2.0
            * math.pi
            * EARTH_RADIUS_M
            / (TILE_SIZE * 2.0**self._zoom_level)
        )
        target_meters = meters_per_pixel * 120.0
        scale_meters = _nice_scale_length(target_meters)
        scale_pixels = scale_meters / max(meters_per_pixel, 1e-9)
        x = 18.0
        y = self.height() - 24.0
        painter.setPen(QPen(QColor("#303438"), 2.0))
        painter.drawLine(QPointF(x, y), QPointF(x + scale_pixels, y))
        painter.drawLine(QPointF(x, y - 5.0), QPointF(x, y + 5.0))
        painter.drawLine(
            QPointF(x + scale_pixels, y - 5.0),
            QPointF(x + scale_pixels, y + 5.0),
        )
        label = (
            f"{scale_meters / 1000.0:g} km"
            if scale_meters >= 1000.0
            else f"{scale_meters:g} m"
        )
        painter.setPen(QColor("#303438"))
        painter.drawText(QPointF(x, y - 8.0), label)

    def paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.boundingRect(), QColor("#edf0ea"))

        for road in self._roads:
            self._draw_polyline(
                painter,
                road["coordinates"],
                self._road_pen(road["highway"]),
            )

        self._draw_selection_bbox(painter)

        if len(self._route) >= 2:
            route_pen = QPen(QColor("#1769d2"), 6.0)
            route_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            route_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self._draw_polyline(painter, self._route, route_pen)

        for latitude, longitude, _distance in self._signals:
            self._draw_marker(
                painter,
                (latitude, longitude),
                QColor("#e02b2b"),
                4.5,
            )

        if self._start:
            self._draw_marker(painter, self._start, QColor("#18883a"), 9.0)
        if self._target:
            self._draw_marker(painter, self._target, QColor("#c62828"), 9.0)

        self._draw_scale(painter)

        painter.setFont(QFont("Sans Serif", 8))
        painter.setPen(QColor("#596067"))
        painter.drawText(
            QRectF(8.0, self.height() - 22.0, self.width() - 16.0, 18.0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "© OpenStreetMap contributors · lokale Vektordaten",
        )

        if not self._roads:
            painter.setFont(QFont("Sans Serif", 13))
            painter.setPen(QColor("#596067"))
            painter.drawText(
                self.boundingRect().adjusted(30.0, 30.0, -30.0, -30.0),
                Qt.AlignmentFlag.AlignCenter,
                "Straßendatei wählen und den Kartenausschnitt laden",
            )
