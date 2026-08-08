from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from .integrated_speed_profile_v7 import IntegratedSpeedProfileWindow as _V7Window
except ImportError:
    from integrated_speed_profile_v7 import IntegratedSpeedProfileWindow as _V7Window


_SIGNAL_DEFINITIONS: dict[str, tuple[str, str, tuple[int, int, int], bool, Qt.PenStyle, float]] = {
    "simulated": ("Simuliert", "speed", (45, 145, 255), True, Qt.PenStyle.SolidLine, 2.5),
    "road_limit": ("Straßenlimit", "speed", (155, 155, 155), True, Qt.PenStyle.DashLine, 1.3),
    "curve_limit": ("Kurvenlimit", "speed", (190, 80, 220), True, Qt.PenStyle.DotLine, 1.4),
    "target": ("Soll", "speed", (235, 155, 30), False, Qt.PenStyle.SolidLine, 1.5),
    "acceleration": ("Längsbeschleunigung", "acceleration", (40, 180, 125), True, Qt.PenStyle.SolidLine, 1.7),
    "elevation": ("Höhe", "elevation", (215, 145, 65), True, Qt.PenStyle.SolidLine, 1.7),
    "power_total": ("Leistung gesamt", "power", (225, 225, 225), True, Qt.PenStyle.SolidLine, 2.1),
    "power_acceleration": ("P Beschleunigung", "power", (55, 190, 135), False, Qt.PenStyle.SolidLine, 1.2),
    "power_grade": ("P Steigung", "power", (205, 135, 55), False, Qt.PenStyle.SolidLine, 1.2),
    "power_rolling": ("P Roll", "power", (155, 155, 155), False, Qt.PenStyle.SolidLine, 1.1),
    "power_air": ("P Luft", "power", (65, 145, 240), False, Qt.PenStyle.SolidLine, 1.2),
    "power_trailer": ("P Anhänger", "power", (170, 85, 200), False, Qt.PenStyle.SolidLine, 1.2),
}

_SCENARIO_COLORS: tuple[tuple[int, int, int], ...] = (
    (45, 145, 255),
    (235, 90, 60),
    (55, 175, 100),
    (175, 95, 210),
    (230, 155, 35),
    (45, 175, 190),
    (150, 105, 60),
    (175, 175, 175),
)

_GROUP_AXIS = {
    "speed": ("Geschwindigkeit", "km/h", (205, 205, 205)),
    "acceleration": ("Beschleunigung", "m/s²", (60, 190, 140)),
    "elevation": ("Höhe", "m", (220, 150, 70)),
    "power": ("Radleistung", "kW", (95, 160, 245)),
}


class IntegratedSpeedProfileWindow(_V7Window):
    """V8: compact header, modern sidebar and one selectable multi-axis analysis plot."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._v8_ready = False
        self._combined_items: dict[str, tuple[pg.PlotDataItem, str]] = {}
        self._combined_item_style: dict[
            str, tuple[tuple[int, int, int], float, Qt.PenStyle]
        ] = {}
        self._combined_item_labels: dict[str, str] = {}
        self._combined_aux_items: list[tuple[Any, str]] = []
        self._combined_views: dict[str, pg.ViewBox] = {}
        self._combined_axes: dict[str, pg.AxisItem] = {}
        self._focused_combined_key: str | None = None
        self._combined_hover_proxy: pg.SignalProxy | None = None
        self._combined_x_limits: list[float] = []
        super().__init__(route_path)

        self._install_modern_sidebar_toggle()
        self._move_energy_to_header()
        self._install_combined_plot()
        self._install_combined_controls()
        self._simplify_right_analysis()
        self._v8_ready = True
        self._set_plot_mode("combined")
        self._update_energy_summary()
        if self._result is not None:
            self._update_combined_plot()

    # ------------------------------------------------------------------
    # Modern compact shell
    # ------------------------------------------------------------------
    def _install_modern_sidebar_toggle(self) -> None:
        if hasattr(self, "toggle_parameters_button"):
            self.toggle_parameters_button.hide()

        toolbar = self.axis_combo.parentWidget()
        layout = toolbar.layout() if toolbar is not None else None
        if not isinstance(layout, QHBoxLayout):
            return

        button = QToolButton()
        button.setText("☰  Parameter")
        button.setCheckable(True)
        button.setChecked(True)
        button.setAutoRaise(True)
        button.setToolTip("Parameter-Seitenleiste ein- oder ausblenden")
        button.setStyleSheet(
            "QToolButton { padding: 5px 11px; border: 1px solid palette(mid); "
            "border-radius: 11px; background: palette(base); font-weight: 600; } "
            "QToolButton:hover { background: palette(alternate-base); } "
            "QToolButton:checked { border: 1px solid palette(highlight); }"
        )
        button.toggled.connect(self._set_parameter_pane_visible)
        layout.insertWidget(max(0, layout.count() - 1), button)
        self.sidebar_toggle_button = button

    def _set_parameter_pane_visible(self, visible: bool) -> None:
        pane = self._parameter_pane
        if pane is None:
            return
        pane.setVisible(bool(visible))
        self.sidebar_toggle_button.setText(
            "☰  Parameter" if visible else "☰  Parameter öffnen"
        )
        outer = self.centralWidget()
        if isinstance(outer, QSplitter):
            if visible:
                outer.setSizes([370, max(900, self.width() - 370)])
            else:
                outer.setSizes([0, max(1000, self.width())])

    def _move_energy_to_header(self) -> None:
        if not hasattr(self, "power_summary_label"):
            return
        outer = self.centralWidget()
        if not isinstance(outer, QSplitter) or outer.count() < 2:
            return
        plot_root = outer.widget(1)
        plot_layout = plot_root.layout()
        if not isinstance(plot_layout, QVBoxLayout):
            return

        old_parent = self.power_summary_label.parentWidget()
        old_layout = old_parent.layout() if old_parent is not None else None
        if old_layout is not None:
            old_layout.removeWidget(self.power_summary_label)
        self.power_summary_label.setParent(plot_root)
        self.power_summary_label.setWordWrap(True)
        self.power_summary_label.setMaximumHeight(58)
        self.power_summary_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.power_summary_label.setStyleSheet(
            "QLabel { padding: 4px 8px; border: 1px solid palette(mid); "
            "border-radius: 4px; background: palette(base); font-size: 11px; }"
        )
        self.power_summary_label.setToolTip(
            "Energie = Zeitintegral der signierten Radleistung. Rekuperation wird ideal, "
            "unbegrenzt und mit 100 % Wirkungsgrad angenommen."
        )
        summary_index = plot_layout.indexOf(self.summary_label)
        plot_layout.insertWidget(max(0, summary_index + 1), self.power_summary_label)
        self.energy_header_label = self.power_summary_label

    def _update_energy_summary(self) -> None:
        if not hasattr(self, "power_summary_label"):
            return

        if self._comparison_configs and self._comparison_resistance:
            names = self._comparison_names or [
                "Aktuell",
                *[str(item["name"]) for item in self._comparison_configs],
            ]
            parts: list[str] = []
            for index, data in enumerate(self._comparison_resistance):
                drive, recuperation, net = self._energy_values(data)
                name = names[index] if index < len(names) else f"Konfiguration {index + 1}"
                parts.append(
                    f"<b>{name}</b>: Antrieb {drive:.2f} · Reku {recuperation:.2f} · "
                    f"Netto <b>{net:.2f} kWh</b>"
                )
            self.power_summary_label.setText("Energie &nbsp; | &nbsp; " + " &nbsp; | &nbsp; ".join(parts))
            return

        data = self._resistance_time_data
        if not data:
            self.power_summary_label.setText("Energie: –")
            return
        drive, recuperation, net = self._energy_values(data)
        p95 = float(data.get("p95_positive_kw", 0.0) or 0.0)
        pmax = float(data.get("maximum_kw", 0.0) or 0.0)
        pmin = float(data.get("minimum_kw", 0.0) or 0.0)
        self.power_summary_label.setText(
            f"<b>Energie</b>: Antrieb <b>{drive:.2f} kWh</b> &nbsp; | &nbsp; "
            f"Reku <b>{recuperation:.2f} kWh</b> &nbsp; | &nbsp; "
            f"Netto <b>{net:.2f} kWh</b> &nbsp;&nbsp;&nbsp; "
            f"<b>Leistung</b>: P95 {p95:.1f} · Pmax {pmax:.1f} · Pmin {pmin:.1f} kW"
        )

    def _simplify_right_analysis(self) -> None:
        collective_legend = self._fixed_legends.get("collective")
        if collective_legend is not None:
            collective_legend.hide()
        self.load_collective_plot.setTitle("Kumuliertes Lastkollektiv")
        self.load_collective_plot.setToolTip(
            "Positive und negative Last werden getrennt von ihrem jeweiligen Peak bei 0 % "
            "Zeitanteil Richtung 0 kumuliert."
        )

    def _plot_cumulative_collective(self) -> None:
        super()._plot_cumulative_collective()
        if hasattr(self, "load_collective_plot"):
            self.load_collective_plot.setTitle("Kumuliertes Lastkollektiv")
        collective_legend = self._fixed_legends.get("collective") if hasattr(self, "_fixed_legends") else None
        if collective_legend is not None:
            collective_legend.hide()

    # ------------------------------------------------------------------
    # Combined plot shell and multiple y axes
    # ------------------------------------------------------------------
    def _install_combined_plot(self) -> None:
        if self.plot_stack_splitter is None:
            return
        stack_host = self.plot_stack_splitter.parentWidget()
        host_layout = stack_host.layout() if stack_host is not None else None
        if not isinstance(host_layout, QVBoxLayout):
            return

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.combined_legend_bar = QWidget()
        self.combined_legend_layout = QHBoxLayout(self.combined_legend_bar)
        self.combined_legend_layout.setContentsMargins(3, 0, 3, 0)
        self.combined_legend_layout.setSpacing(4)
        layout.addWidget(self.combined_legend_bar)

        plot = pg.PlotWidget(title="Analyse")
        plot.setMinimumHeight(500)
        plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        plot.showGrid(x=True, y=True, alpha=0.23)
        plot.setLabel("bottom", "Zeit", units="min")
        plot.setLabel("left", "Geschwindigkeit", units="km/h")
        layout.addWidget(plot, 1)
        host_layout.addWidget(container, 1)

        self.combined_container = container
        self.combined_plot = plot
        plot_item = plot.plotItem
        main_view = plot_item.vb
        self._combined_views["speed"] = main_view
        self._combined_axes["speed"] = plot_item.getAxis("left")

        # First right axis uses pyqtgraph's built-in right axis.
        plot_item.showAxis("right")
        acceleration_axis = plot_item.getAxis("right")
        acceleration_view = pg.ViewBox()
        plot.scene().addItem(acceleration_view)
        acceleration_axis.linkToView(acceleration_view)
        acceleration_view.setXLink(main_view)
        self._combined_views["acceleration"] = acceleration_view
        self._combined_axes["acceleration"] = acceleration_axis

        # Two additional right axes for height and power.
        for column, group in ((3, "elevation"), (4, "power")):
            axis = pg.AxisItem("right")
            axis.setWidth(58)
            plot_item.layout.addItem(axis, 2, column)
            view = pg.ViewBox()
            plot.scene().addItem(view)
            axis.linkToView(view)
            view.setXLink(main_view)
            self._combined_views[group] = view
            self._combined_axes[group] = axis

        for group, axis in self._combined_axes.items():
            label, unit, color = _GROUP_AXIS[group]
            axis.setLabel(label, units=unit)
            try:
                axis.setPen(pg.mkPen(color))
                axis.setTextPen(pg.mkPen(color))
            except AttributeError:
                pass

        main_view.sigResized.connect(self._sync_combined_views)
        self._sync_combined_views()
        self.combined_cursor = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen((230, 230, 230, 150), width=1.1)
        )
        main_view.addItem(self.combined_cursor, ignoreBounds=True)
        self._combined_hover_proxy = pg.SignalProxy(
            plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._combined_hover_moved,
        )

    def _sync_combined_views(self) -> None:
        if "speed" not in self._combined_views:
            return
        main_view = self._combined_views["speed"]
        rect = main_view.sceneBoundingRect()
        for group, view in self._combined_views.items():
            if group == "speed":
                continue
            view.setGeometry(rect)
            view.linkedViewChanged(main_view, view.XAxis)

    def _install_combined_controls(self) -> None:
        toolbar = self.axis_combo.parentWidget()
        layout = toolbar.layout() if toolbar is not None else None
        if not isinstance(layout, QHBoxLayout):
            return

        axis_index = layout.indexOf(self.axis_combo)
        insert_at = max(0, axis_index + 1)

        self.plot_mode_combo = QComboBox()
        self.plot_mode_combo.addItem("Analyse", "combined")
        self.plot_mode_combo.addItem("4 Plots", "stacked")
        self.plot_mode_combo.setToolTip("Zwischen kombiniertem Analyseplot und vier Einzelplots wechseln")
        self.plot_mode_combo.currentIndexChanged.connect(self._plot_mode_changed)
        layout.insertWidget(insert_at, self.plot_mode_combo)
        insert_at += 1

        self.signal_menu = QMenu(self)
        self.signal_actions: dict[str, QAction] = {}
        for key, (label, _group, _color, default, _style, _width) in _SIGNAL_DEFINITIONS.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(default)
            action.toggled.connect(lambda _checked, signal_key=key: self._signal_visibility_changed(signal_key))
            self.signal_menu.addAction(action)
            self.signal_actions[key] = action

        self.signals_button = QToolButton()
        self.signals_button.setText("Signale")
        self.signals_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.signals_button.setMenu(self.signal_menu)
        self.signals_button.setToolTip("Kurven im kombinierten Analyseplot auswählen")
        self.signals_button.setStyleSheet(
            "QToolButton { padding: 4px 9px; border: 1px solid palette(mid); "
            "border-radius: 9px; background: palette(base); } "
            "QToolButton:hover { background: palette(alternate-base); }"
        )
        layout.insertWidget(insert_at, self.signals_button)
        insert_at += 1

        self.comparison_metric_combo = QComboBox()
        self.comparison_metric_combo.addItem("Geschwindigkeit", "speed")
        self.comparison_metric_combo.addItem("Längsbeschleunigung", "acceleration")
        self.comparison_metric_combo.addItem("Fahrwiderstandsleistung", "power")
        self.comparison_metric_combo.setToolTip(
            "Im Vergleichsmodus wird bewusst nur eine Linie je Konfiguration gezeichnet."
        )
        self.comparison_metric_combo.currentIndexChanged.connect(
            lambda *_: self._update_combined_plot()
        )
        self.comparison_metric_combo.hide()
        layout.insertWidget(insert_at, self.comparison_metric_combo)
        self._update_signal_button_text()

    def _plot_mode_changed(self) -> None:
        self._set_plot_mode(str(self.plot_mode_combo.currentData()))

    def _set_plot_mode(self, mode: str) -> None:
        combined = mode != "stacked"
        if hasattr(self, "combined_container"):
            self.combined_container.setVisible(combined)
        if self.plot_stack_splitter is not None:
            self.plot_stack_splitter.setVisible(not combined)
        if hasattr(self, "signals_button"):
            self.signals_button.setVisible(combined and not bool(self._comparison_configs))
        if hasattr(self, "comparison_metric_combo"):
            self.comparison_metric_combo.setVisible(combined and bool(self._comparison_configs))
        if combined:
            self._update_combined_plot()
        else:
            self._apply_roomy_sizes()

    def _signal_visibility_changed(self, _signal_key: str) -> None:
        self._update_signal_button_text()
        if self._v8_ready and str(self.plot_mode_combo.currentData()) == "combined":
            self._update_combined_plot()

    def _update_signal_button_text(self) -> None:
        if not hasattr(self, "signals_button"):
            return
        count = sum(1 for action in self.signal_actions.values() if action.isChecked())
        self.signals_button.setText(f"Signale  {count} ▾")

    # ------------------------------------------------------------------
    # Combined signal data
    # ------------------------------------------------------------------
    @staticmethod
    def _interp_unique(
        target_x: np.ndarray, source_x: np.ndarray, source_y: np.ndarray
    ) -> np.ndarray:
        x = np.asarray(source_x, dtype=float)
        y = np.asarray(source_y, dtype=float)
        target = np.asarray(target_x, dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        if np.count_nonzero(valid) < 2:
            return np.full_like(target, np.nan, dtype=float)
        unique_x, indexes = np.unique(x[valid], return_index=True)
        unique_y = y[valid][indexes]
        if unique_x.size < 2:
            return np.full_like(target, unique_y[0] if unique_y.size else np.nan, dtype=float)
        return np.interp(target, unique_x, unique_y)

    def _single_signal_data(self) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        if self._result is None:
            return np.empty(0), {}
        distance_data = self._result["distance"]
        time_data = self._result["time"]
        spatial_distance = np.asarray(distance_data["distance_m"], dtype=float)
        time_s = np.asarray(time_data["time_s"], dtype=float)
        time_distance = np.asarray(time_data["distance_m"], dtype=float)
        elevation_spatial = self._spatial_elevation(spatial_distance)

        if self._axis_mode == "distance":
            x = spatial_distance / 1000.0
            actual = np.asarray(distance_data["actual_speed_kmh"], dtype=float)
            target = np.asarray(distance_data["planned_speed_kmh"], dtype=float)
            acceleration = self._interp_unique(
                spatial_distance,
                time_distance,
                np.asarray(time_data["acceleration_mps2"], dtype=float),
            )
            elevation = elevation_spatial
        else:
            x = time_s / 60.0
            actual = np.asarray(time_data["speed_kmh"], dtype=float)
            target = np.asarray(time_data["target_kmh"], dtype=float)
            acceleration = np.asarray(time_data["acceleration_mps2"], dtype=float)
            elevation = np.interp(time_distance, spatial_distance, elevation_spatial)

        road_spatial = np.asarray(distance_data["road_limit_kmh"], dtype=float)
        curve_spatial = np.asarray(distance_data["curve_limit_kmh"], dtype=float)
        if self._axis_mode == "distance":
            road_limit = road_spatial
            curve_limit = curve_spatial.copy()
        else:
            road_limit = np.interp(time_distance, spatial_distance, road_spatial)
            curve_limit = np.interp(time_distance, spatial_distance, curve_spatial)
        curve_limit = np.asarray(curve_limit, dtype=float)
        curve_limit[~np.isfinite(curve_limit) | (curve_limit > 400.0)] = np.nan

        data: dict[str, np.ndarray] = {
            "simulated": actual,
            "road_limit": road_limit,
            "curve_limit": curve_limit,
            "target": target,
            "acceleration": acceleration,
            "elevation": elevation,
        }

        resistance = self._resistance_time_data
        if resistance:
            power_mapping = {
                "power_total": "total_kw",
                "power_acceleration": "acceleration_kw",
                "power_grade": "grade_kw",
                "power_rolling": "rolling_kw",
                "power_air": "air_kw",
                "power_trailer": "trailer_kw",
            }
            resistance_time = np.asarray(resistance.get("time_s", []), dtype=float)
            resistance_distance = np.asarray(resistance.get("distance_m", []), dtype=float)
            for signal_key, resistance_key in power_mapping.items():
                values = np.asarray(resistance.get(resistance_key, []), dtype=float)
                if values.size == 0:
                    continue
                if self._axis_mode == "distance":
                    data[signal_key] = self._interp_unique(
                        spatial_distance, resistance_distance, values
                    )
                elif values.shape == time_s.shape and resistance_time.shape == time_s.shape:
                    data[signal_key] = values
                else:
                    data[signal_key] = self._interp_unique(time_s, resistance_time, values)
        return x, data

    def _comparison_metric_data(
        self,
        result: dict[str, Any],
        resistance: dict[str, Any] | None,
        metric: str,
    ) -> tuple[np.ndarray, np.ndarray, str]:
        distance_data = result["distance"]
        time_data = result["time"]
        spatial_distance = np.asarray(distance_data["distance_m"], dtype=float)
        time_s = np.asarray(time_data["time_s"], dtype=float)
        time_distance = np.asarray(time_data["distance_m"], dtype=float)

        if metric == "acceleration":
            group = "acceleration"
            if self._axis_mode == "distance":
                x = spatial_distance / 1000.0
                y = self._interp_unique(
                    spatial_distance,
                    time_distance,
                    np.asarray(time_data["acceleration_mps2"], dtype=float),
                )
            else:
                x = time_s / 60.0
                y = np.asarray(time_data["acceleration_mps2"], dtype=float)
            return x, y, group

        if metric == "power":
            group = "power"
            if not resistance:
                return np.empty(0), np.empty(0), group
            values = np.asarray(resistance.get("total_kw", []), dtype=float)
            r_time = np.asarray(resistance.get("time_s", []), dtype=float)
            r_distance = np.asarray(resistance.get("distance_m", []), dtype=float)
            if self._axis_mode == "distance":
                x = spatial_distance / 1000.0
                y = self._interp_unique(spatial_distance, r_distance, values)
            else:
                x = time_s / 60.0
                if values.shape == time_s.shape:
                    y = values
                else:
                    y = self._interp_unique(time_s, r_time, values)
            return x, y, group

        group = "speed"
        if self._axis_mode == "distance":
            return (
                spatial_distance / 1000.0,
                np.asarray(distance_data["actual_speed_kmh"], dtype=float),
                group,
            )
        return time_s / 60.0, np.asarray(time_data["speed_kmh"], dtype=float), group

    # ------------------------------------------------------------------
    # Combined plot rendering and line focus
    # ------------------------------------------------------------------
    def _clear_combined_curves(self) -> None:
        for _key, (item, group) in list(self._combined_items.items()):
            view = self._combined_views.get(group)
            if view is not None:
                try:
                    view.removeItem(item)
                except Exception:
                    pass
        for item, group in self._combined_aux_items:
            view = self._combined_views.get(group)
            if view is not None:
                try:
                    view.removeItem(item)
                except Exception:
                    pass
        self._combined_items.clear()
        self._combined_item_style.clear()
        self._combined_item_labels.clear()
        self._combined_aux_items.clear()
        self._combined_x_limits.clear()
        self._focused_combined_key = None

    def _add_combined_curve(
        self,
        key: str,
        label: str,
        group: str,
        x: np.ndarray,
        y: np.ndarray,
        color: tuple[int, int, int],
        width: float,
        style: Qt.PenStyle = Qt.PenStyle.SolidLine,
    ) -> None:
        view = self._combined_views.get(group)
        if view is None:
            return
        x_values = np.asarray(x, dtype=float)
        y_values = np.asarray(y, dtype=float)
        if x_values.shape != y_values.shape or x_values.size == 0:
            return
        valid_x = x_values[np.isfinite(x_values)]
        if valid_x.size:
            self._combined_x_limits.extend([float(np.min(valid_x)), float(np.max(valid_x))])

        item = pg.PlotDataItem(
            x_values,
            y_values,
            pen=pg.mkPen(color, width=width, style=style),
            connect="finite",
        )
        view.addItem(item)
        curve = getattr(item, "curve", None)
        if curve is not None and hasattr(curve, "setClickable"):
            curve.setClickable(True, width=11)
            signal = getattr(curve, "sigClicked", None)
            if signal is not None:
                signal.connect(lambda *_args, curve_key=key: self._focus_combined_line(curve_key))
        else:
            signal = getattr(item, "sigClicked", None)
            if signal is not None:
                signal.connect(lambda *_args, curve_key=key: self._focus_combined_line(curve_key))

        self._combined_items[key] = (item, group)
        self._combined_item_style[key] = (color, width, style)
        self._combined_item_labels[key] = label

    def _focus_combined_line(self, key: str) -> None:
        self._focused_combined_key = None if self._focused_combined_key == key else key
        for item_key, (item, _group) in self._combined_items.items():
            color, width, style = self._combined_item_style[item_key]
            focused = self._focused_combined_key
            if focused is None:
                alpha = 255
                current_width = width
                z = 2
            elif item_key == focused:
                alpha = 255
                current_width = width + 2.2
                z = 20
            else:
                alpha = 45
                current_width = max(0.8, width * 0.8)
                z = 1
            item.setPen(pg.mkPen((*color, alpha), width=current_width, style=style))
            item.setZValue(z)
        self._refresh_combined_legend()

    def _refresh_combined_legend(self) -> None:
        if not hasattr(self, "combined_legend_layout"):
            return
        layout = self.combined_legend_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self._combined_items:
            label = QLabel("Keine Signale ausgewählt")
            label.setStyleSheet("QLabel { color: palette(mid); padding: 2px 4px; }")
            layout.addWidget(label)
            layout.addStretch(1)
            return

        for key in self._combined_items:
            color, _width, _style = self._combined_item_style[key]
            label = self._combined_item_labels[key]
            button = QToolButton()
            button.setText(f"● {label}")
            button.setAutoRaise(True)
            is_focused = key == self._focused_combined_key
            opacity = 255 if self._focused_combined_key in (None, key) else 110
            button.setStyleSheet(
                "QToolButton { border: none; padding: 2px 5px; "
                f"color: rgba({color[0]}, {color[1]}, {color[2]}, {opacity}); "
                + ("font-weight: 700; text-decoration: underline;" if is_focused else "")
                + " } QToolButton:hover { background: palette(alternate-base); border-radius: 7px; }"
            )
            button.setToolTip("Anklicken, um diese Linie hervorzuheben; erneut anklicken zum Lösen")
            button.clicked.connect(lambda _checked=False, curve_key=key: self._focus_combined_line(curve_key))
            layout.addWidget(button)
        layout.addStretch(1)

    def _set_combined_axis_visibility(self, groups: set[str]) -> None:
        for group, axis in self._combined_axes.items():
            axis.setVisible(group in groups)

    def _add_zero_line(self, group: str) -> None:
        view = self._combined_views.get(group)
        if view is None:
            return
        line = pg.InfiniteLine(y=0.0, movable=False, pen=pg.mkPen((130, 130, 130, 130), width=1))
        view.addItem(line, ignoreBounds=True)
        self._combined_aux_items.append((line, group))

    def _finish_combined_ranges(self, groups: set[str], comparison: bool) -> None:
        main_view = self._combined_views.get("speed")
        if main_view is None:
            return
        if self._combined_x_limits:
            x_min = min(self._combined_x_limits)
            x_max = max(self._combined_x_limits)
            if math.isfinite(x_min) and math.isfinite(x_max):
                if math.isclose(x_min, x_max):
                    x_max = x_min + 1.0
                main_view.setXRange(x_min, x_max, padding=0.02)

        for group in groups:
            view = self._combined_views.get(group)
            if view is None:
                continue
            try:
                view.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
            except TypeError:
                view.enableAutoRange(y=True)

        if "speed" in groups and not comparison and self._result is not None:
            road = np.asarray(self._result["distance"].get("road_limit_kmh", []), dtype=float)
            finite = road[np.isfinite(road)]
            if finite.size:
                main_view.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
                main_view.setYRange(0.0, max(40.0, float(np.max(finite)) + 25.0), padding=0.02)
        self._sync_combined_views()

    def _update_combined_plot(self) -> None:
        if not self._v8_ready or not hasattr(self, "combined_plot"):
            return
        self._clear_combined_curves()
        comparison = bool(self._comparison_configs and self._comparison_results)
        if hasattr(self, "signals_button"):
            self.signals_button.setVisible(not comparison)
        if hasattr(self, "comparison_metric_combo"):
            self.comparison_metric_combo.setVisible(comparison)

        groups: set[str] = set()
        if comparison:
            metric = str(self.comparison_metric_combo.currentData())
            names = self._comparison_names or [
                "Aktuell",
                *[str(item["name"]) for item in self._comparison_configs],
            ]
            for index, result in enumerate(self._comparison_results):
                resistance = (
                    self._comparison_resistance[index]
                    if index < len(self._comparison_resistance)
                    else None
                )
                x, y, group = self._comparison_metric_data(result, resistance, metric)
                name = names[index] if index < len(names) else f"Konfiguration {index + 1}"
                color = _SCENARIO_COLORS[index % len(_SCENARIO_COLORS)]
                self._add_combined_curve(
                    f"comparison:{index}", name, group, x, y, color, 2.4
                )
                groups.add(group)
            metric_label = self.comparison_metric_combo.currentText()
            self.combined_plot.setTitle(f"{metric_label} – Konfigurationsvergleich")
        else:
            x, values = self._single_signal_data()
            for key, action in self.signal_actions.items():
                if not action.isChecked() or key not in values:
                    continue
                label, group, color, _default, style, width = _SIGNAL_DEFINITIONS[key]
                self._add_combined_curve(key, label, group, x, values[key], color, width, style)
                groups.add(group)
            self.combined_plot.setTitle("Fahrtanalyse")

        if "acceleration" in groups:
            self._add_zero_line("acceleration")
        if "power" in groups:
            self._add_zero_line("power")

        self.combined_plot.setLabel(
            "bottom",
            "Strecke" if self._axis_mode == "distance" else "Zeit",
            units="km" if self._axis_mode == "distance" else "min",
        )
        self._set_combined_axis_visibility(groups)
        self._finish_combined_ranges(groups, comparison)
        self._refresh_combined_legend()

    def _combined_hover_moved(self, event: Any) -> None:
        if self._result is None or not hasattr(self, "combined_plot"):
            return
        position = event[0] if isinstance(event, (tuple, list)) else event
        if position is None or not self.combined_plot.sceneBoundingRect().contains(position):
            return
        point = self.combined_plot.plotItem.vb.mapSceneToView(position)
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
        super()._set_hover_index(index)
        if self._result is None or not hasattr(self, "combined_cursor"):
            return
        time_data = self._result["time"]
        time_s = np.asarray(time_data["time_s"], dtype=float)
        if time_s.size == 0:
            return
        clipped = int(np.clip(index, 0, len(time_s) - 1))
        if self._axis_mode == "distance":
            position = float(np.asarray(time_data["distance_m"], dtype=float)[clipped]) / 1000.0
        else:
            position = float(time_s[clipped]) / 60.0
        self.combined_cursor.setPos(position)

    # ------------------------------------------------------------------
    # Inherited simulation updates
    # ------------------------------------------------------------------
    def _update_plots(self) -> None:
        super()._update_plots()
        if self._v8_ready:
            self._update_combined_plot()
            self._update_energy_summary()

    def reset_plot_views(self) -> None:
        super().reset_plot_views()
        if hasattr(self, "combined_plot"):
            for view in self._combined_views.values():
                try:
                    view.enableAutoRange()
                except Exception:
                    pass
            self._update_combined_plot()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1720, 980)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
