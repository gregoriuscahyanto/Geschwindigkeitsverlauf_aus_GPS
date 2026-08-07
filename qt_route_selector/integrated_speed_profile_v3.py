from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QSplitter,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from .enhanced_speed_simulation import simulate_speed_profile as _enhanced_simulate
    from .integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow
    from .resistance_power import (
        calculate_resistance_power,
        load_collective,
        road_grade,
    )
except ImportError:
    from enhanced_speed_simulation import simulate_speed_profile as _enhanced_simulate
    from integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow
    from resistance_power import calculate_resistance_power, load_collective, road_grade


class IntegratedSpeedProfileWindow(_BaseWindow):
    """Focused simulation UI with driver dynamics and longitudinal power demand."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._v3_layout_ready = False
        self._resistance_time_data: dict[str, object] | None = None
        self.plot_map_splitter: QSplitter | None = None
        self.right_analysis_panel: QWidget | None = None

        actual_route_path = Path(route_path or "route_result.json").expanduser().resolve()
        deferred_route_path = actual_route_path.with_name(
            f".__startup_deferred_{actual_route_path.name}"
        )

        # Keep startup light: the base constructor receives a guaranteed missing
        # path so no route parsing/simulation blocks the main window before paint.
        super().__init__(deferred_route_path)

        self._route_path = actual_route_path
        if hasattr(self, "route_path_label"):
            self.route_path_label.setText(str(actual_route_path))
        self._install_post_curve_controls()
        self._install_resistance_controls()
        self._install_power_visuals()
        self._connect_hover_events()
        self.statusBar().showMessage(
            "Bereit – Route wird beim Öffnen des Simulation-Tabs oder nach einer neuen Berechnung geladen."
        )

        self._v3_layout_ready = True
        self._apply_plot_layout()
        QTimer.singleShot(0, self._apply_plot_layout)

    def _install_post_curve_controls(self) -> None:
        driver_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Fahrer"),
            None,
        )
        if driver_group is None or not isinstance(driver_group.layout(), QFormLayout):
            return
        form = driver_group.layout()

        enabled = QCheckBox()
        enabled.setChecked(True)
        enabled.setToolTip(
            "Nach einer tatsächlich geschwindigkeitsbegrenzenden Kurve kurz etwas über die "
            "Reisegeschwindigkeit beschleunigen und anschließend wieder einregeln."
        )
        enabled.toggled.connect(self.schedule_recalculate)
        self._control_widgets["use_post_curve_overshoot"] = enabled
        form.addRow("Nach Kurve überschwingen", enabled)

        amount = QDoubleSpinBox()
        amount.setRange(0.0, 10.0)
        amount.setSingleStep(0.5)
        amount.setDecimals(1)
        amount.setValue(3.0)
        amount.setSuffix(" km/h")
        amount.setKeyboardTracking(False)
        amount.setToolTip(
            "Zusätzliche gewünschte Geschwindigkeit nach der Kurve. 3 km/h bedeutet bei "
            "30 km/h Reisegeschwindigkeit einen kurzen Zielwert um 33 km/h."
        )
        amount.valueChanged.connect(self.schedule_recalculate)
        self._control_widgets["post_curve_overshoot_kmh"] = amount
        form.addRow("Überschwingung", amount)

        probability = QDoubleSpinBox()
        probability.setRange(0.0, 100.0)
        probability.setSingleStep(5.0)
        probability.setDecimals(0)
        probability.setValue(60.0)
        probability.setSuffix(" %")
        probability.setKeyboardTracking(False)
        probability.setToolTip(
            "Anteil geeigneter Kurvenausgänge, an denen dieses Fahrerverhalten auftritt. "
            "Der Zufallsablauf bleibt über den Simulations-Seed reproduzierbar."
        )
        probability.valueChanged.connect(self.schedule_recalculate)
        self._control_widgets["post_curve_overshoot_probability_pct"] = probability
        form.addRow("Wahrscheinlichkeit", probability)

        decay = QDoubleSpinBox()
        decay.setRange(20.0, 300.0)
        decay.setSingleStep(10.0)
        decay.setDecimals(0)
        decay.setValue(90.0)
        decay.setSuffix(" m")
        decay.setKeyboardTracking(False)
        decay.setToolTip(
            "Strecke, über die der zusätzliche Geschwindigkeitswunsch wieder auf die normale "
            "Reisegeschwindigkeit abklingt."
        )
        decay.valueChanged.connect(self.schedule_recalculate)
        self._control_widgets["post_curve_overshoot_distance_m"] = decay
        form.addRow("Abklingstrecke", decay)

    def _add_resistance_double(
        self,
        form: QFormLayout,
        label: str,
        key: str,
        minimum: float,
        maximum: float,
        step: float,
        value: float,
        suffix: str = "",
        decimals: int = 3,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(decimals)
        widget.setValue(value)
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        widget.valueChanged.connect(self.schedule_recalculate)
        self._control_widgets[key] = widget
        form.addRow(label, widget)
        return widget

    def _install_resistance_controls(self) -> None:
        mass_widget = self._control_widgets.get("vehicle_mass_kg")
        if mass_widget is None or mass_widget.parentWidget() is None:
            return
        page = mass_widget.parentWidget()
        form = page.layout()
        if not isinstance(form, QFormLayout):
            return

        for label in page.findChildren(QLabel):
            if "liefert noch kein Höhenprofil" in label.text():
                label.setText(
                    "Für die Fahrwiderstandsleistung wird das aktive DEM-Höhenprofil verwendet. "
                    "Ohne Höhenwerte wird der Steigungsanteil mit 0 angesetzt."
                )

        heading = QLabel("<b>Fahrwiderstand / Radleistung</b>")
        heading.setTextFormat(Qt.TextFormat.RichText)
        form.addRow(heading)
        self._add_resistance_double(
            form,
            "Luftwiderstandsbeiwert cW",
            "air_drag_coefficient",
            0.05,
            1.50,
            0.01,
            0.29,
            decimals=2,
        )
        self._add_resistance_double(
            form,
            "Stirnfläche A",
            "frontal_area_m2",
            0.5,
            12.0,
            0.1,
            2.3,
            " m²",
            2,
        )
        self._add_resistance_double(
            form,
            "Luftdichte",
            "air_density_kg_m3",
            0.8,
            1.5,
            0.005,
            1.225,
            " kg/m³",
            3,
        )
        self._add_resistance_double(
            form,
            "Anhänger Rollwiderstand",
            "trailer_rolling_resistance_coeff",
            0.0,
            0.10,
            0.001,
            0.015,
            decimals=3,
        )
        self._add_resistance_double(
            form,
            "Anhänger cW·A",
            "trailer_drag_area_m2",
            0.0,
            8.0,
            0.1,
            1.0,
            " m²",
            2,
        )
        self._add_resistance_double(
            form,
            "Steigungs-Glättung",
            "grade_smoothing_m",
            0.0,
            250.0,
            5.0,
            40.0,
            " m",
            0,
        )
        note = QLabel(
            "Die Leistung ist am Rad bilanziert: positiv = Antriebsbedarf, negativ = Brems-/Schubbetrieb. "
            "Der Anhängeranteil enthält seine zusätzliche Trägheits-, Steigungs-, Roll- und Luftlast."
        )
        note.setWordWrap(True)
        form.addRow(note)

    def _install_power_visuals(self) -> None:
        if hasattr(self, "resistance_plot"):
            return

        self.resistance_plot = self._new_plot(
            "Fahrwiderstandsleistung", "Radleistung", "kW"
        )
        self.resistance_plot.addLegend(offset=(10, 10))
        self.resistance_plot.setXLink(self.speed_plot)

        stacked_widget = self.speed_plot.parentWidget()
        stacked_layout = stacked_widget.layout() if stacked_widget is not None else None
        if isinstance(stacked_layout, QVBoxLayout):
            stacked_layout.addWidget(self.resistance_plot, 2)

        plot_splitter = self.map_widget.parentWidget()
        if not isinstance(plot_splitter, QSplitter):
            raise RuntimeError("Karten-/Plot-Splitter für Leistungsanalyse nicht gefunden.")
        self.plot_map_splitter = plot_splitter

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        replaced = plot_splitter.replaceWidget(1, right_panel)
        if replaced is not None and replaced is not self.map_widget:
            raise RuntimeError("Unerwartetes Widget beim Aufbau der Leistungsanalyse.")
        self.map_widget.setParent(right_panel)
        right_layout.addWidget(self.map_widget, 3)

        self.power_summary_label = QLabel(
            "Lastkollektiv wird nach der ersten Simulation berechnet."
        )
        self.power_summary_label.setWordWrap(True)
        self.power_summary_label.setStyleSheet(
            "QLabel { padding: 5px 7px; border: 1px solid palette(mid); "
            "border-radius: 3px; background: palette(base); }"
        )
        right_layout.addWidget(self.power_summary_label)

        self.load_collective_plot = pg.PlotWidget(
            title="Lastkollektiv – Zeitanteil je Radleistungsbereich"
        )
        self.load_collective_plot.setLabel("left", "Zeitanteil", units="%")
        self.load_collective_plot.setLabel("bottom", "Radleistung", units="kW")
        self.load_collective_plot.showGrid(x=True, y=True, alpha=0.25)
        right_layout.addWidget(self.load_collective_plot, 2)
        self.right_analysis_panel = right_panel

    def recalculate(self) -> None:
        if self._route is None:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._result = _enhanced_simulate(self._route, self.parameters())
            self._update_plots()
        except Exception as exc:
            self.statusBar().showMessage(f"Simulation fehlgeschlagen: {exc}")
            QMessageBox.critical(self, "Simulation fehlgeschlagen", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _calculate_resistance_data(self) -> dict[str, object] | None:
        if self._result is None:
            return None
        distance_data = self._result.get("distance", {})
        time_data = self._result.get("time", {})
        try:
            spatial_distance = np.asarray(distance_data["distance_m"], dtype=float)
            time_s = np.asarray(time_data["time_s"], dtype=float)
            time_distance = np.asarray(time_data["distance_m"], dtype=float)
            speed_kmh = np.asarray(time_data["speed_kmh"], dtype=float)
            acceleration = np.asarray(time_data["acceleration_mps2"], dtype=float)
        except (KeyError, TypeError, ValueError):
            return None
        if spatial_distance.size < 2 or time_s.size == 0:
            return None

        elevation_spatial = self._spatial_elevation(spatial_distance)
        elevation_available = np.count_nonzero(np.isfinite(elevation_spatial)) >= 2
        grade_spatial = road_grade(
            spatial_distance,
            elevation_spatial,
            smoothing_distance_m=float(self.parameters().get("grade_smoothing_m", 40.0)),
        )
        grade_time = np.interp(time_distance, spatial_distance, grade_spatial)
        data = calculate_resistance_power(
            time_s,
            speed_kmh,
            acceleration,
            grade_time,
            self.parameters(),
        )
        data["distance_m"] = time_distance
        data["spatial_distance_m"] = spatial_distance
        data["grade_spatial"] = grade_spatial
        data["elevation_available"] = elevation_available
        return data

    def _update_plots(self) -> None:
        if hasattr(self, "resistance_plot"):
            self._clear_plot(self.resistance_plot)
        if hasattr(self, "load_collective_plot"):
            self.load_collective_plot.clear()
        self._resistance_time_data = self._calculate_resistance_data()

        super()._update_plots()
        if self._v3_layout_ready:
            self._plot_resistance_data()
            self._apply_plot_layout()
            self._focus_speed_axis()

    def _plot_resistance_data(self) -> None:
        data = self._resistance_time_data
        if data is None or self._result is None or not hasattr(self, "resistance_plot"):
            return

        time_s = np.asarray(data["time_s"], dtype=float)
        time_distance = np.asarray(data["distance_m"], dtype=float)
        component_keys = (
            ("total_kw", "Gesamt", (25, 25, 25), 2.4),
            ("acceleration_kw", "Beschleunigung", (35, 125, 90), 1.3),
            ("grade_kw", "Steigung", (145, 95, 45), 1.3),
            ("rolling_kw", "Roll", (100, 100, 100), 1.1),
            ("air_kw", "Luft", (25, 100, 210), 1.3),
            ("trailer_kw", "Anhänger", (135, 55, 160), 1.3),
        )

        if self._axis_mode == "distance":
            spatial_distance = np.asarray(
                self._result["distance"]["distance_m"], dtype=float
            )
            x = spatial_distance / 1000.0
            unique_distance, unique_indexes = np.unique(
                time_distance, return_index=True
            )
            series: dict[str, np.ndarray] = {}
            for key, _name, _color, _width in component_keys:
                values = np.asarray(data[key], dtype=float)
                if unique_distance.size >= 2:
                    series[key] = np.interp(
                        spatial_distance,
                        unique_distance,
                        values[unique_indexes],
                    )
                else:
                    series[key] = np.zeros_like(spatial_distance)
            x_label, x_unit = "Strecke", "km"
        else:
            x = time_s / 60.0
            series = {
                key: np.asarray(data[key], dtype=float)
                for key, _name, _color, _width in component_keys
            }
            x_label, x_unit = "Zeit", "min"

        for key, name, color, width in component_keys:
            if key == "trailer_kw" and not bool(data.get("trailer_enabled", False)):
                continue
            self.resistance_plot.plot(
                x,
                series[key],
                pen=pg.mkPen(color, width=width),
                name=name,
            )
        self.resistance_plot.addLine(
            y=0.0, pen=pg.mkPen((110, 110, 110), width=1)
        )
        self.resistance_plot.setLabel("bottom", x_label, units=x_unit)
        if bool(data.get("elevation_available", False)):
            self.resistance_plot.setTitle("Fahrwiderstandsleistung am Rad")
        else:
            self.resistance_plot.setTitle(
                "Fahrwiderstandsleistung am Rad – Steigungsanteil ohne DEM = 0"
            )
        self.resistance_plot.enableAutoRange()

        collective = load_collective(
            time_s,
            np.asarray(data["total_kw"], dtype=float),
            bin_count=14,
        )
        centers = np.asarray(collective["centers_kw"], dtype=float)
        widths = np.asarray(collective["widths_kw"], dtype=float)
        shares = np.asarray(collective["time_share_pct"], dtype=float)
        if centers.size:
            bars = pg.BarGraphItem(
                x=centers,
                height=shares,
                width=widths * 0.86,
                brush=pg.mkBrush(70, 120, 180, 175),
                pen=pg.mkPen(55, 85, 120, 210),
            )
            self.load_collective_plot.addItem(bars)
            self.load_collective_plot.addLine(
                x=0.0, pen=pg.mkPen((100, 100, 100), width=1)
            )
            self.load_collective_plot.setYRange(
                0.0, max(5.0, float(np.max(shares)) * 1.15), padding=0.02
            )
        self.load_collective_plot.setLabel("left", "Zeitanteil", units="%")
        self.load_collective_plot.setLabel("bottom", "Radleistung", units="kW")

        self.power_summary_label.setText(
            f"Antriebsenergie am Rad: <b>{float(data['traction_energy_kwh']):.2f} kWh</b> &nbsp; | &nbsp; "
            f"Brems-/Schubenergie: <b>{float(data['braking_energy_kwh']):.2f} kWh</b><br>"
            f"P95 positiv: <b>{float(data['p95_positive_kw']):.1f} kW</b> &nbsp; | &nbsp; "
            f"Maximum: <b>{float(data['maximum_kw']):.1f} kW</b> &nbsp; | &nbsp; "
            f"Minimum: <b>{float(data['minimum_kw']):.1f} kW</b>"
        )

    def _connect_hover_events(self) -> None:
        self._hover_proxies.clear()
        plots = [self.speed_plot, self.longitudinal_plot, self.elevation_plot]
        if hasattr(self, "resistance_plot"):
            plots.append(self.resistance_plot)
        for plot in plots:
            proxy = pg.SignalProxy(
                plot.scene().sigMouseMoved,
                rateLimit=60,
                slot=partial(self._plot_hover_moved, plot),
            )
            self._hover_proxies.append(proxy)

    def _install_hover_items(self) -> None:
        cursor_pen = pg.mkPen((35, 35, 35, 190), width=1.2)
        self._hover_cursors = []
        plots = [self.speed_plot, self.longitudinal_plot, self.elevation_plot]
        if hasattr(self, "resistance_plot"):
            plots.append(self.resistance_plot)
        for plot in plots:
            cursor = pg.InfiniteLine(angle=90, movable=False, pen=cursor_pen)
            plot.addItem(cursor, ignoreBounds=True)
            self._hover_cursors.append(cursor)

    def _set_hover_index(self, index: int) -> None:
        super()._set_hover_index(index)
        data = self._resistance_time_data
        if data is None or self._result is None:
            return
        total = np.asarray(data["total_kw"], dtype=float)
        grade_pct = np.asarray(data["grade_pct"], dtype=float)
        if total.size == 0:
            return
        clipped = int(np.clip(index, 0, total.size - 1))
        self.hover_label.setText(
            self.hover_label.text()
            + f"<br>Radleistung: <b>{total[clipped]:.1f} kW</b> &nbsp; | &nbsp; "
            f"Steigung: <b>{grade_pct[clipped]:.1f} %</b>"
        )

    def _focus_speed_axis(self) -> None:
        if self._result is None or not hasattr(self, "speed_plot"):
            return
        road_limit = np.asarray(
            self._result.get("distance", {}).get("road_limit_kmh", []),
            dtype=float,
        )
        finite = road_limit[np.isfinite(road_limit)]
        if finite.size == 0:
            return

        # Ignore mathematical curve-limit spikes for visual scaling.
        y_max = max(40.0, float(np.max(finite)) + 25.0)
        self.speed_plot.enableAutoRange(axis="y", enable=False)
        self.speed_plot.setYRange(0.0, y_max, padding=0.02)

    def set_dem_path(self, path: str | Path | None) -> None:
        """Activate a DEM programmatically, e.g. after an automatic download."""
        if path is None or not str(path).strip():
            self.clear_dem_file()
            return
        dem_path = Path(path).expanduser().resolve()
        if not dem_path.exists():
            raise FileNotFoundError(f"Höhenmodell nicht gefunden: {dem_path}")
        self._dem_path = dem_path
        self._invalidate_dem_cache()
        if self.dem_status_label is not None:
            self.dem_status_label.setText(f"DEM automatisch aktiviert: {dem_path}")
        if self._result is not None:
            self._update_plots()
        self.statusBar().showMessage(f"Höhenmodell aktiviert: {dem_path.name}")

    def _apply_plot_layout(self) -> None:
        required = (
            "speed_plot",
            "longitudinal_plot",
            "elevation_plot",
            "map_widget",
        )
        if not all(hasattr(self, name) for name in required):
            return

        plots: list[tuple[pg.PlotWidget, int]] = [
            (self.speed_plot, 160),
            (self.longitudinal_plot, 125),
            (self.elevation_plot, 125),
        ]
        if hasattr(self, "resistance_plot"):
            plots.append((self.resistance_plot, 155))

        for plot, minimum_height in plots:
            plot.setMinimumHeight(minimum_height)
            plot.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            plot.setStyleSheet(
                "QGraphicsView { border: 1px solid palette(mid); border-radius: 2px; }"
            )
            try:
                plot.plotItem.layout.setContentsMargins(5, 5, 5, 8)
            except AttributeError:
                pass

        upper_plots = [self.speed_plot, self.longitudinal_plot]
        if hasattr(self, "resistance_plot"):
            upper_plots.append(self.elevation_plot)
        for plot in upper_plots:
            bottom_axis = plot.getAxis("bottom")
            bottom_axis.setStyle(showValues=False, tickLength=0)
            bottom_axis.setLabel("")

        bottom_plot = (
            self.resistance_plot if hasattr(self, "resistance_plot") else self.elevation_plot
        )
        bottom_plot.getAxis("bottom").setStyle(showValues=True, tickLength=-5)

        stacked_widget = self.speed_plot.parentWidget()
        if stacked_widget is not None:
            stacked_widget.setMinimumWidth(650)
            stacked_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            layout = stacked_widget.layout()
            if isinstance(layout, QVBoxLayout):
                layout.setContentsMargins(4, 4, 4, 6)
                layout.setSpacing(9)

        plot_splitter = self.plot_map_splitter
        if plot_splitter is None:
            candidate = self.map_widget.parentWidget()
            plot_splitter = candidate if isinstance(candidate, QSplitter) else None
        if isinstance(plot_splitter, QSplitter):
            plot_splitter.setOrientation(Qt.Orientation.Horizontal)
            plot_splitter.setHandleWidth(9)
            plot_splitter.setChildrenCollapsible(False)
            plot_splitter.setStretchFactor(0, 5)
            plot_splitter.setStretchFactor(1, 3)

            available_width = plot_splitter.width()
            if available_width > 0:
                left_width = max(680, available_width * 5 // 8)
                right_width = max(440, available_width - left_width)
                plot_splitter.setSizes([left_width, right_width])
            else:
                plot_splitter.setSizes([850, 520])

        if self.right_analysis_panel is not None:
            self.right_analysis_panel.setMinimumWidth(420)
            self.right_analysis_panel.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
        self.map_widget.setMinimumWidth(420)
        self.map_widget.setMinimumHeight(320)
        self.map_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        if hasattr(self, "load_collective_plot"):
            self.load_collective_plot.setMinimumHeight(190)
            self.load_collective_plot.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
