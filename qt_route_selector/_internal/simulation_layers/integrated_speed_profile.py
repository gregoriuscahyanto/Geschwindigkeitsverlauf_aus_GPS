from __future__ import annotations

import math
import sys
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Property, QUrl, Signal, Qt
from PySide6.QtPositioning import QGeoCoordinate
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from . import speed_simulation as _simulation
    from .live_speed_profile import LiveSpeedProfileWindow
except ImportError:
    import speed_simulation as _simulation
    from live_speed_profile import LiveSpeedProfileWindow


APP_DIR = Path(__file__).resolve().parent


def _osm_only_event_positions(
    route: _simulation.PreparedRoute,
    requested: int,
    detected: np.ndarray,
    rng: np.random.Generator,
    *,
    minimum_spacing_m: float = 0.0,
) -> np.ndarray:
    """Return only real OSM traffic signals and never synthesize stops."""

    del route, rng, minimum_spacing_m
    valid = np.asarray(detected, dtype=float)
    valid = np.unique(valid[np.isfinite(valid)])
    requested = min(max(0, int(requested)), len(valid))
    if requested == 0:
        return np.empty(0, dtype=float)
    if requested == len(valid):
        return valid

    groups = np.array_split(np.arange(len(valid), dtype=int), requested)
    indexes = np.asarray([group[len(group) // 2] for group in groups], dtype=int)
    return valid[indexes]


# Enforce the OSM-only traffic-light rule in the existing simulation model.
_simulation._choose_event_positions = _osm_only_event_positions


class SimulationMapBridge(QObject):
    routePathChanged = Signal()
    trafficLightsChanged = Signal()
    currentPositionChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._route_path: list[QGeoCoordinate] = []
        self._traffic_lights: list[QGeoCoordinate] = []
        self._current_latitude = 0.0
        self._current_longitude = 0.0
        self._position_valid = False

    @Property("QVariantList", notify=routePathChanged)
    def routePath(self) -> list[QGeoCoordinate]:
        return self._route_path

    @Property("QVariantList", notify=trafficLightsChanged)
    def trafficLights(self) -> list[QGeoCoordinate]:
        return self._traffic_lights

    @Property(float, notify=currentPositionChanged)
    def currentLatitude(self) -> float:
        return self._current_latitude

    @Property(float, notify=currentPositionChanged)
    def currentLongitude(self) -> float:
        return self._current_longitude

    @Property(bool, notify=currentPositionChanged)
    def positionValid(self) -> bool:
        return self._position_valid

    def set_route(
        self,
        latitude: np.ndarray,
        longitude: np.ndarray,
        light_latitude: np.ndarray,
        light_longitude: np.ndarray,
    ) -> None:
        self._route_path = [
            QGeoCoordinate(float(lat), float(lon))
            for lat, lon in zip(latitude, longitude)
            if math.isfinite(float(lat)) and math.isfinite(float(lon))
        ]
        self._traffic_lights = [
            QGeoCoordinate(float(lat), float(lon))
            for lat, lon in zip(light_latitude, light_longitude)
            if math.isfinite(float(lat)) and math.isfinite(float(lon))
        ]
        self.routePathChanged.emit()
        self.trafficLightsChanged.emit()

    def set_current_position(self, latitude: float, longitude: float) -> None:
        self._current_latitude = float(latitude)
        self._current_longitude = float(longitude)
        self._position_valid = math.isfinite(latitude) and math.isfinite(longitude)
        self.currentPositionChanged.emit()


class IntegratedSpeedProfileWindow(LiveSpeedProfileWindow):
    """Live editor with aligned plots and a synchronized geographic map."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._route_token: tuple[str, int] | None = None
        self._integrated_ready = False
        self._axis_mode = "time"
        self._hover_proxies: list[pg.SignalProxy] = []
        super().__init__(route_path)
        self.setWindowTitle("Geschwindigkeitsverlauf")
        self._flatten_setting_tabs()
        self._rebuild_plot_area()
        self._integrated_ready = True
        self._connect_hover_events()
        if self._result is not None:
            self._update_plots()

    def _flatten_setting_tabs(self) -> None:
        settings_tabs = next(
            (tab for tab in self.findChildren(QTabWidget) if tab.count() == 5),
            None,
        )
        if settings_tabs is None:
            return
        parent = settings_tabs.parentWidget()
        layout = parent.layout() if parent is not None else None
        if layout is None:
            return

        insert_at = layout.indexOf(settings_tabs)
        groups: list[QGroupBox] = []
        while settings_tabs.count():
            title = settings_tabs.tabText(0)
            page = settings_tabs.widget(0)
            settings_tabs.removeTab(0)
            group = QGroupBox(title)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(8, 8, 8, 8)
            page.setParent(group)
            group_layout.addWidget(page)
            groups.append(group)

        layout.removeWidget(settings_tabs)
        settings_tabs.deleteLater()
        for offset, group in enumerate(groups):
            layout.insertWidget(insert_at + offset, group)

    def _new_plot(self, title: str, y_label: str, y_unit: str) -> pg.PlotWidget:
        plot = pg.PlotWidget(title=title)
        plot.setLabel("left", y_label, units=y_unit)
        plot.showGrid(x=True, y=True, alpha=0.25)
        return plot

    def _rebuild_plot_area(self) -> None:
        splitter = self.centralWidget()
        if not isinstance(splitter, QSplitter):
            raise RuntimeError("Unerwarteter Aufbau des Simulationsfensters.")
        plot_root = splitter.widget(1)
        plot_layout = plot_root.layout()
        if plot_layout is None:
            raise RuntimeError("Plot-Layout wurde nicht gefunden.")

        for old_plot in (self.distance_plot, self.time_plot, self.acceleration_plot):
            plot_layout.removeWidget(old_plot)
            old_plot.setParent(None)
            old_plot.deleteLater()

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.addWidget(QLabel("X-Achse:"))
        self.axis_combo = QComboBox()
        self.axis_combo.addItem("Zeit", "time")
        self.axis_combo.addItem("Strecke", "distance")
        self.axis_combo.currentIndexChanged.connect(self._axis_changed)
        toolbar_layout.addWidget(self.axis_combo)
        toolbar_layout.addStretch(1)
        plot_layout.addWidget(toolbar)

        self.hover_label = QLabel(
            "Über einen der drei Plots fahren: Cursor und Kartenposition werden synchron angezeigt."
        )
        self.hover_label.setWordWrap(True)
        self.hover_label.setStyleSheet(
            "QLabel { padding: 6px 8px; border: 1px solid palette(mid); "
            "border-radius: 4px; background: palette(base); }"
        )
        plot_layout.addWidget(self.hover_label)

        self.speed_plot = self._new_plot("Geschwindigkeit", "Geschwindigkeit", "km/h")
        self.speed_plot.addLegend(offset=(10, 10))
        self.longitudinal_plot = self._new_plot(
            "Längsbeschleunigung", "Beschleunigung", "m/s²"
        )
        self.elevation_plot = self._new_plot("Höhenprofil", "Höhe", "m")
        self.longitudinal_plot.setXLink(self.speed_plot)
        self.elevation_plot.setXLink(self.speed_plot)

        stacked_plots = QWidget()
        stacked_layout = QVBoxLayout(stacked_plots)
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setSpacing(3)
        stacked_layout.addWidget(self.speed_plot, 3)
        stacked_layout.addWidget(self.longitudinal_plot, 2)
        stacked_layout.addWidget(self.elevation_plot, 2)

        self.map_bridge = SimulationMapBridge()
        self.map_widget = QQuickWidget()
        self.map_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.map_widget.rootContext().setContextProperty(
            "simulationMapBridge", self.map_bridge
        )
        self.map_widget.setSource(QUrl.fromLocalFile(str(APP_DIR / "simulation_map.qml")))
        self.map_widget.setMinimumHeight(260)

        plot_splitter = QSplitter(Qt.Orientation.Vertical)
        plot_splitter.setChildrenCollapsible(False)
        plot_splitter.addWidget(stacked_plots)
        plot_splitter.addWidget(self.map_widget)
        plot_splitter.setStretchFactor(0, 3)
        plot_splitter.setStretchFactor(1, 2)
        plot_layout.addWidget(plot_splitter, 1)

    def _connect_hover_events(self) -> None:
        self._hover_proxies.clear()
        for plot in (self.speed_plot, self.longitudinal_plot, self.elevation_plot):
            proxy = pg.SignalProxy(
                plot.scene().sigMouseMoved,
                rateLimit=60,
                slot=partial(self._plot_hover_moved, plot),
            )
            self._hover_proxies.append(proxy)

    def _axis_changed(self) -> None:
        self._axis_mode = str(self.axis_combo.currentData())
        if self._result is not None:
            self._update_plots()

    def reload_route(self, *_args: Any, silent: bool = False) -> None:
        super().reload_route(*_args, silent=silent)
        if self._route is None:
            return

        detected_positions: set[float] = set()
        for item in self._route.get("traffic_signals", []):
            try:
                value = float(item.get("distance_from_start_m", math.nan))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                detected_positions.add(round(value, 3))
        detected = len(detected_positions)
        light_widget = self._control_widgets.get("traffic_light_count")
        if isinstance(light_widget, QSpinBox):
            token = (str(self._route_path), self._last_route_mtime_ns)
            light_widget.blockSignals(True)
            try:
                light_widget.setRange(0, detected)
                light_widget.setSuffix(f" / {detected} OSM")
                if token != self._route_token:
                    light_widget.setValue(detected)
                else:
                    light_widget.setValue(min(light_widget.value(), detected))
                light_widget.setEnabled(detected > 0)
            finally:
                light_widget.blockSignals(False)
            self._route_token = token

        self.detected_lights_label.setText(
            f"OSM-Ampeln auf der Route: {detected}; maximal {detected} Stopps"
        )
        if self._integrated_ready:
            self.recalculate()

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6_371_008.8
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = p2 - p1
        dl = math.radians(lon2 - lon1)
        value = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
        value = min(1.0, max(0.0, value))
        return radius * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))

    def _spatial_elevation(self, sample_distance: np.ndarray) -> np.ndarray:
        if self._route is None:
            return np.full_like(sample_distance, np.nan, dtype=float)
        coordinates = self._route.get("coordinates", [])
        if len(coordinates) < 2:
            return np.full_like(sample_distance, np.nan, dtype=float)

        latitude = np.asarray([float(point["latitude"]) for point in coordinates], dtype=float)
        longitude = np.asarray([float(point["longitude"]) for point in coordinates], dtype=float)
        elevation = np.full(len(coordinates), np.nan, dtype=float)
        for index, point in enumerate(coordinates):
            for key in ("elevation_m", "elevation", "ele"):
                if key in point and point[key] is not None:
                    try:
                        elevation[index] = float(point[key])
                    except (TypeError, ValueError):
                        pass
                    break

        finite = np.isfinite(elevation)
        if np.count_nonzero(finite) < 2:
            return np.full_like(sample_distance, np.nan, dtype=float)

        segment_lookup: dict[int, float] = {}
        for segment in self._route.get("segments", []):
            try:
                segment_lookup[int(segment.get("from_index", -1))] = float(
                    segment.get("distance_m", 0.0)
                )
            except (TypeError, ValueError):
                continue
        raw_distance = np.zeros(len(coordinates), dtype=float)
        for index in range(len(coordinates) - 1):
            step = segment_lookup.get(index, 0.0)
            if not math.isfinite(step) or step <= 0.0:
                step = self._haversine_m(
                    latitude[index], longitude[index], latitude[index + 1], longitude[index + 1]
                )
            raw_distance[index + 1] = raw_distance[index] + max(step, 0.1)

        elevation = np.interp(raw_distance, raw_distance[finite], elevation[finite])
        return np.interp(sample_distance, raw_distance, elevation)

    @staticmethod
    def _unique_distance_values(
        distance_m: np.ndarray, values: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        unique_distance, first_indexes = np.unique(distance_m, return_index=True)
        return unique_distance, values[first_indexes]

    def _clear_plot(self, plot: pg.PlotWidget) -> None:
        plot.clear()
        legend = plot.plotItem.legend
        if legend is not None:
            legend.clear()

    def _update_plots(self) -> None:
        if not self._integrated_ready:
            super()._update_plots()
            return
        if self._result is None:
            return

        for plot in (self.speed_plot, self.longitudinal_plot, self.elevation_plot):
            self._clear_plot(plot)
        self._event_items.clear()

        distance_data = self._result["distance"]
        time_data = self._result["time"]
        spatial_distance = np.asarray(distance_data["distance_m"], dtype=float)
        time_s = np.asarray(time_data["time_s"], dtype=float)
        time_distance = np.asarray(time_data["distance_m"], dtype=float)
        elevation_spatial = self._spatial_elevation(spatial_distance)

        if self._axis_mode == "distance":
            x = spatial_distance / 1000.0
            x_label, x_unit = "Strecke", "km"
            actual = np.asarray(distance_data["actual_speed_kmh"], dtype=float)
            target = np.asarray(distance_data["planned_speed_kmh"], dtype=float)
            road_limit = np.asarray(distance_data["road_limit_kmh"], dtype=float)
            curve_limit = np.asarray(distance_data["curve_limit_kmh"], dtype=float)
            unique_distance, acceleration = self._unique_distance_values(
                time_distance,
                np.asarray(time_data["acceleration_mps2"], dtype=float),
            )
            acceleration_y = np.interp(spatial_distance, unique_distance, acceleration)
            elevation_y = elevation_spatial
        else:
            x = time_s / 60.0
            x_label, x_unit = "Zeit", "min"
            actual = np.asarray(time_data["speed_kmh"], dtype=float)
            target = np.asarray(time_data["target_kmh"], dtype=float)
            road_limit = np.interp(
                time_distance,
                spatial_distance,
                np.asarray(distance_data["road_limit_kmh"], dtype=float),
            )
            curve_limit = np.interp(
                time_distance,
                spatial_distance,
                np.asarray(distance_data["curve_limit_kmh"], dtype=float),
            )
            acceleration_y = np.asarray(time_data["acceleration_mps2"], dtype=float)
            elevation_y = np.interp(time_distance, spatial_distance, elevation_spatial)

        curve_plot = curve_limit.copy()
        curve_plot[~np.isfinite(curve_plot) | (curve_plot > 400.0)] = np.nan
        self.speed_plot.plot(
            x,
            road_limit,
            pen=pg.mkPen((100, 100, 100), width=1.2, style=Qt.PenStyle.DashLine),
            name="Straßenlimit",
        )
        self.speed_plot.plot(
            x,
            curve_plot,
            pen=pg.mkPen((135, 55, 160), width=1.2, style=Qt.PenStyle.DotLine),
            name="Kurvenlimit",
        )
        self.speed_plot.plot(
            x, target, pen=pg.mkPen((220, 140, 25), width=1.5), name="Soll"
        )
        self.speed_plot.plot(
            x, actual, pen=pg.mkPen((25, 100, 210), width=2.4), name="Simuliert"
        )
        self.longitudinal_plot.plot(
            x, acceleration_y, pen=pg.mkPen((35, 125, 90), width=1.8)
        )
        self.longitudinal_plot.addLine(
            y=0.0, pen=pg.mkPen((100, 100, 100), width=1)
        )

        if np.any(np.isfinite(elevation_y)):
            self.elevation_plot.setTitle("Höhenprofil")
            self.elevation_plot.plot(
                x, elevation_y, pen=pg.mkPen((145, 95, 45), width=1.8)
            )
        else:
            self.elevation_plot.setTitle(
                "Höhenprofil – keine Höhenwerte in route_result.json"
            )

        for plot in (self.speed_plot, self.longitudinal_plot, self.elevation_plot):
            plot.setLabel("bottom", x_label, units=x_unit)
            plot.enableAutoRange()

        latitude = np.asarray(distance_data["latitude"], dtype=float)
        longitude = np.asarray(distance_data["longitude"], dtype=float)
        light_distances = np.asarray(
            [float(event["distance_m"]) for event in self._result["events"]["traffic_lights"]],
            dtype=float,
        )
        light_latitude = (
            np.interp(light_distances, spatial_distance, latitude)
            if light_distances.size
            else np.empty(0)
        )
        light_longitude = (
            np.interp(light_distances, spatial_distance, longitude)
            if light_distances.size
            else np.empty(0)
        )
        self.map_bridge.set_route(
            latitude, longitude, light_latitude, light_longitude
        )

        self._install_hover_items()
        self._set_hover_index(0)

        summary = self._result["summary"]
        profile = _simulation.DRIVER_PROFILES.get(
            str(self.profile_combo.currentData()), _simulation.DRIVER_PROFILES["normalo"]
        )
        self.summary_label.setText(
            f"<b>{profile['label']}</b> – {profile['note']} &nbsp; | &nbsp; "
            f"Strecke: <b>{summary['distance_km']:.2f} km</b> &nbsp; | &nbsp; "
            f"Fahrtdauer: <b>{summary['duration_min']:.1f} min</b> &nbsp; | &nbsp; "
            f"Ø: <b>{summary['average_speed_kmh']:.1f} km/h</b> &nbsp; | &nbsp; "
            f"Maximum: <b>{summary['maximum_speed_kmh']:.1f} km/h</b> &nbsp; | &nbsp; "
            f"Ampelstopps: <b>{summary['traffic_light_stops']}</b> &nbsp; | &nbsp; "
            f"Überholvorgänge: <b>{summary['overtaking_events']}</b>"
        )
        self.statusBar().showMessage("Live-Simulation aktualisiert.")

    def _install_hover_items(self) -> None:
        cursor_pen = pg.mkPen((35, 35, 35, 190), width=1.2)
        self._hover_cursors = []
        for plot in (self.speed_plot, self.longitudinal_plot, self.elevation_plot):
            cursor = pg.InfiniteLine(angle=90, movable=False, pen=cursor_pen)
            plot.addItem(cursor, ignoreBounds=True)
            self._hover_cursors.append(cursor)

    def _plot_hover_moved(self, plot: pg.PlotWidget, event: Any) -> None:
        if self._result is None or not hasattr(self, "_hover_cursors"):
            return
        position = event[0] if isinstance(event, (tuple, list)) else event
        if position is None or not plot.sceneBoundingRect().contains(position):
            return
        point = plot.plotItem.vb.mapSceneToView(position)
        time_s = np.asarray(self._result["time"]["time_s"], dtype=float)
        if time_s.size == 0:
            return

        if self._axis_mode == "distance":
            route_distance = np.asarray(self._result["time"]["distance_m"], dtype=float)
            target = float(point.x()) * 1000.0
            index = int(np.argmin(np.abs(route_distance - target)))
        else:
            target = float(point.x()) * 60.0
            index = int(np.argmin(np.abs(time_s - target)))
        self._set_hover_index(index)

    def _set_hover_index(self, index: int) -> None:
        if self._result is None:
            return
        time_data = self._result["time"]
        time_s = np.asarray(time_data["time_s"], dtype=float)
        if time_s.size == 0:
            return
        index = int(np.clip(index, 0, len(time_s) - 1))

        distance_m = float(np.asarray(time_data["distance_m"], dtype=float)[index])
        speed_kmh = float(np.asarray(time_data["speed_kmh"], dtype=float)[index])
        target_kmh = float(np.asarray(time_data["target_kmh"], dtype=float)[index])
        acceleration = float(np.asarray(time_data["acceleration_mps2"], dtype=float)[index])
        current_time_s = float(time_s[index])

        distance_data = self._result["distance"]
        spatial_distance = np.asarray(distance_data["distance_m"], dtype=float)
        latitude = float(
            np.interp(
                distance_m,
                spatial_distance,
                np.asarray(distance_data["latitude"], dtype=float),
            )
        )
        longitude = float(
            np.interp(
                distance_m,
                spatial_distance,
                np.asarray(distance_data["longitude"], dtype=float),
            )
        )
        elevation = float(
            np.interp(distance_m, spatial_distance, self._spatial_elevation(spatial_distance))
        )

        cursor_position = (
            distance_m / 1000.0 if self._axis_mode == "distance" else current_time_s / 60.0
        )
        for cursor in self._hover_cursors:
            cursor.setPos(cursor_position)
        self.map_bridge.set_current_position(latitude, longitude)

        elevation_text = f"{elevation:.1f} m" if math.isfinite(elevation) else "keine Daten"
        self.hover_label.setText(
            f"Zeit: <b>{current_time_s:.1f} s</b> &nbsp; | &nbsp; "
            f"Strecke: <b>{distance_m / 1000.0:.3f} km</b> &nbsp; | &nbsp; "
            f"v: <b>{speed_kmh:.1f} km/h</b> &nbsp; | &nbsp; "
            f"Soll: <b>{target_kmh:.1f} km/h</b> &nbsp; | &nbsp; "
            f"a: <b>{acceleration:.2f} m/s²</b> &nbsp; | &nbsp; "
            f"Höhe: <b>{elevation_text}</b><br>"
            f"GPS: <b>{latitude:.6f}, {longitude:.6f}</b>"
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
