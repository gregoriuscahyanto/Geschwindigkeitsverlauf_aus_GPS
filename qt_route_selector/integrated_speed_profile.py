from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QSpinBox, QSplitter

try:
    from . import speed_simulation as _simulation
    from .live_speed_profile import LiveSpeedProfileWindow
except ImportError:
    import speed_simulation as _simulation
    from live_speed_profile import LiveSpeedProfileWindow


def _osm_only_event_positions(
    route: _simulation.PreparedRoute,
    requested: int,
    detected: np.ndarray,
    rng: np.random.Generator,
    *,
    minimum_spacing_m: float = 0.0,
) -> np.ndarray:
    """Return only real OSM signal positions and never synthesize stops.

    ``requested`` is clamped to the number of signals detected on the route.
    When fewer stops than available signals are requested, positions are
    selected evenly along the route and remain deterministic.
    """

    del route, rng, minimum_spacing_m
    valid = np.asarray(detected, dtype=float)
    valid = valid[np.isfinite(valid)]
    valid = np.unique(valid)
    requested = min(max(0, int(requested)), len(valid))
    if requested == 0:
        return np.empty(0, dtype=float)
    if requested == len(valid):
        return valid

    groups = np.array_split(np.arange(len(valid), dtype=int), requested)
    indexes = np.asarray([group[len(group) // 2] for group in groups], dtype=int)
    return valid[indexes]


# ``simulate_speed_profile`` resolves this helper in the module globals at
# runtime. Replacing it here keeps the original research model intact while
# enforcing the application's OSM-only traffic-light rule.
_simulation._choose_event_positions = _osm_only_event_positions


class IntegratedSpeedProfileWindow(LiveSpeedProfileWindow):
    """Live speed-profile editor with GPS view and synchronized hover cursor."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._route_token: tuple[str, int] | None = None
        super().__init__(route_path)
        self.setWindowTitle("Geschwindigkeitsverlauf")
        self._augment_plot_area()
        self._time_hover_proxy = pg.SignalProxy(
            self.time_plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._time_hover_moved,
        )
        if self._result is not None:
            self._update_plots()

    def _augment_plot_area(self) -> None:
        splitter = self.centralWidget()
        if not isinstance(splitter, QSplitter):
            raise RuntimeError("Unerwarteter Aufbau des Simulationsfensters.")
        plot_root = splitter.widget(1)
        plot_layout = plot_root.layout()
        if plot_layout is None:
            raise RuntimeError("Plot-Layout wurde nicht gefunden.")

        plot_layout.removeWidget(self.distance_plot)

        self.hover_label = QLabel(
            "Über das Zeitdiagramm fahren: Zeit, Geschwindigkeit, Strecke und GPS-Position werden synchron angezeigt."
        )
        self.hover_label.setWordWrap(True)
        self.hover_label.setStyleSheet(
            "QLabel { padding: 6px 8px; border: 1px solid palette(mid); "
            "border-radius: 4px; background: palette(base); }"
        )

        self.gps_plot = pg.PlotWidget(title="GPS-Position auf der Route")
        self.gps_plot.setLabel("left", "Breitengrad", units="°")
        self.gps_plot.setLabel("bottom", "Längengrad", units="°")
        self.gps_plot.showGrid(x=True, y=True, alpha=0.20)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setChildrenCollapsible(False)
        top_splitter.addWidget(self.distance_plot)
        top_splitter.addWidget(self.gps_plot)
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 2)

        plot_layout.insertWidget(1, self.hover_label)
        plot_layout.insertWidget(2, top_splitter, 3)

    def reload_route(self, *_args: Any, silent: bool = False) -> None:
        super().reload_route(*_args, silent=silent)
        if self._route is None:
            return

        detected = len(self._route.get("traffic_signals", []))
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
        self.recalculate()

    def _install_hover_items(self) -> None:
        cursor_pen = pg.mkPen((35, 35, 35, 190), width=1.2)
        self._time_cursor = pg.InfiniteLine(angle=90, movable=False, pen=cursor_pen)
        self._acceleration_cursor = pg.InfiniteLine(angle=90, movable=False, pen=cursor_pen)
        self._distance_cursor = pg.InfiniteLine(angle=90, movable=False, pen=cursor_pen)
        self.time_plot.addItem(self._time_cursor, ignoreBounds=True)
        self.acceleration_plot.addItem(self._acceleration_cursor, ignoreBounds=True)
        self.distance_plot.addItem(self._distance_cursor, ignoreBounds=True)

    def _update_plots(self) -> None:
        super()._update_plots()
        if self._result is None or not hasattr(self, "gps_plot"):
            return

        self.gps_plot.clear()
        distance = self._result["distance"]
        latitude = np.asarray(distance["latitude"], dtype=float)
        longitude = np.asarray(distance["longitude"], dtype=float)
        self.gps_plot.plot(
            longitude,
            latitude,
            pen=pg.mkPen((35, 110, 195), width=2.0),
        )

        events = self._result["events"]
        light_distances = np.asarray(
            [float(event["distance_m"]) for event in events["traffic_lights"]],
            dtype=float,
        )
        if light_distances.size:
            route_distance = np.asarray(distance["distance_m"], dtype=float)
            light_lat = np.interp(light_distances, route_distance, latitude)
            light_lon = np.interp(light_distances, route_distance, longitude)
            self.gps_plot.plot(
                light_lon,
                light_lat,
                pen=None,
                symbol="t",
                symbolSize=11,
                symbolBrush=(210, 45, 45),
                symbolPen=(255, 255, 255),
            )

        self._gps_position = pg.ScatterPlotItem(
            size=14,
            brush=pg.mkBrush(255, 145, 20),
            pen=pg.mkPen(255, 255, 255, width=2),
        )
        self.gps_plot.addItem(self._gps_position)
        self._gps_text = pg.TextItem(anchor=(0.0, 1.0), fill=(255, 255, 255, 210))
        self.gps_plot.addItem(self._gps_text)
        self.gps_plot.enableAutoRange()

        self._install_hover_items()
        self._set_hover_index(0)

    def _time_hover_moved(self, event: Any) -> None:
        if self._result is None or not hasattr(self, "_time_cursor"):
            return
        position = event[0] if isinstance(event, (tuple, list)) else event
        if position is None or not self.time_plot.sceneBoundingRect().contains(position):
            return
        point = self.time_plot.plotItem.vb.mapSceneToView(position)
        time_s = np.asarray(self._result["time"]["time_s"], dtype=float)
        if time_s.size == 0:
            return
        target_s = float(point.x()) * 60.0
        index = int(np.searchsorted(time_s, target_s, side="left"))
        if index >= len(time_s):
            index = len(time_s) - 1
        elif index > 0 and abs(time_s[index - 1] - target_s) <= abs(time_s[index] - target_s):
            index -= 1
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
            np.interp(distance_m, spatial_distance, np.asarray(distance_data["latitude"], dtype=float))
        )
        longitude = float(
            np.interp(distance_m, spatial_distance, np.asarray(distance_data["longitude"], dtype=float))
        )

        time_min = current_time_s / 60.0
        self._time_cursor.setPos(time_min)
        self._acceleration_cursor.setPos(time_min)
        self._distance_cursor.setPos(distance_m / 1000.0)
        self._gps_position.setData([longitude], [latitude])
        self._gps_text.setText(
            f"t={current_time_s:.1f} s\nv={speed_kmh:.1f} km/h\n"
            f"{latitude:.6f}, {longitude:.6f}"
        )
        self._gps_text.setPos(longitude, latitude)
        self.hover_label.setText(
            f"Zeit: <b>{current_time_s:.1f} s</b> &nbsp; | &nbsp; "
            f"Strecke: <b>{distance_m / 1000.0:.3f} km</b> &nbsp; | &nbsp; "
            f"Geschwindigkeit: <b>{speed_kmh:.1f} km/h</b> &nbsp; | &nbsp; "
            f"Soll: <b>{target_kmh:.1f} km/h</b> &nbsp; | &nbsp; "
            f"a: <b>{acceleration:.2f} m/s²</b><br>"
            f"GPS: <b>{latitude:.6f}, {longitude:.6f}</b>"
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
