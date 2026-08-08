from __future__ import annotations

import math
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QSpinBox, QVBoxLayout


class TechnicalPreviewController:
    """Small live plots that explain the effect of the main simulation controls."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self.plots: dict[str, pg.PlotWidget] = {}
        self._install()
        self.update()

    def _new_plot(self, title: str, x_label: str, y_label: str) -> pg.PlotWidget:
        plot = pg.PlotWidget(title=title)
        plot.setFixedHeight(125)
        plot.setMaximumHeight(125)
        plot.setMouseEnabled(x=False, y=False)
        plot.setMenuEnabled(False)
        plot.plotItem.hideButtons()
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.setLabel("bottom", x_label)
        plot.setLabel("left", y_label)
        return plot

    def _attach(self, group_title: str, plot: pg.PlotWidget) -> None:
        group = next(
            (item for item in self.window.findChildren(QGroupBox) if item.title() == group_title),
            None,
        )
        if group is None or group.layout() is None:
            return
        layout = group.layout()
        if isinstance(layout, QFormLayout):
            layout.addRow(plot)
        elif isinstance(layout, QVBoxLayout):
            layout.addWidget(plot)

    def _install(self) -> None:
        definitions = {
            "Fahrer": ("Fahrerreaktion auf Sollwert", "Zeit [s]", "v [km/h]"),
            "Kurven": ("Radius → Kurvengeschwindigkeit", "Radius [m]", "v [km/h]"),
            "Ampeln": ("Bremsen – Halt – Anfahren", "Zeit [s]", "v [km/h]"),
            "Überholen": ("Überholmanöver", "Strecke [m]", "v [km/h]"),
            "Rauschen": ("Korrelierte Fahrerabweichung", "Zeit [s]", "Δv [km/h]"),
            "Fahrzeug": ("Fahrwiderstand auf ebener Strecke", "v [km/h]", "P [kW]"),
        }
        for key, (title, x_label, y_label) in definitions.items():
            plot = self._new_plot(title, x_label, y_label)
            self.plots[key] = plot
            self._attach(key, plot)

    def _value(self, key: str, default: float) -> float:
        widget = self.window._control_widgets.get(key)
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        if isinstance(widget, QSpinBox):
            return float(widget.value())
        return float(default)

    def update(self) -> None:
        if not self.plots:
            return
        cruise = self._value("driver_cruise_kmh", 50.0)
        a_max = max(0.1, self._value("a_max_mps2", 2.8))
        kp = max(0.05, self._value("Kp", 1.1))

        plot = self.plots.get("Fahrer")
        if plot is not None:
            plot.clear()
            t = np.linspace(0.0, 8.0, 121)
            exponential = cruise * (1.0 - np.exp(-kp * t / 2.2))
            response = np.minimum(exponential, a_max * 3.6 * t)
            plot.plot(
                t,
                np.full_like(t, cruise),
                pen=pg.mkPen((120, 120, 120), width=1, style=Qt.PenStyle.DashLine),
            )
            plot.plot(t, response, pen=pg.mkPen((25, 100, 210), width=2))

        plot = self.plots.get("Kurven")
        if plot is not None:
            plot.clear()
            radius = np.geomspace(5.0, 1000.0, 120)
            lat_acc = max(0.2, self._value("max_lat_accel_mps2", 2.2))
            speed = np.sqrt(lat_acc * radius) * 3.6
            plot.setLogMode(x=True, y=False)
            plot.plot(radius, speed, pen=pg.mkPen((135, 55, 160), width=2))

        plot = self.plots.get("Ampeln")
        if plot is not None:
            plot.clear()
            v0 = min(max(20.0, cruise), 80.0)
            decel = max(0.2, self._value("traffic_light_plan_decel_mps2", 1.8))
            dwell = 0.5 * (
                self._value("traffic_light_dwell_min_s", 20.0)
                + self._value("traffic_light_dwell_max_s", 60.0)
            )
            brake_time = v0 / 3.6 / decel
            accel_time = v0 / 3.6 / a_max
            total_time = brake_time + dwell + accel_time + 4.0
            t = np.linspace(0.0, total_time, 180)
            speed = np.zeros_like(t)
            braking = t <= brake_time
            speed[braking] = np.maximum(
                0.0, v0 * (1.0 - t[braking] / max(brake_time, 1e-6))
            )
            start_accel = brake_time + dwell
            accelerating = t >= start_accel
            speed[accelerating] = np.minimum(
                v0, (t[accelerating] - start_accel) * a_max * 3.6
            )
            plot.plot(t, speed, pen=pg.mkPen((210, 70, 45), width=2))

        plot = self.plots.get("Überholen")
        if plot is not None:
            plot.clear()
            follow = max(20.0, self._value("overtaking_follow_distance_m", 180.0))
            passing = max(20.0, self._value("overtaking_pass_distance_m", 100.0))
            slow = self._value("overtaking_slow_speed_kmh", 70.0)
            boost = self._value("overtaking_intensity_kmh", 20.0)
            x = np.linspace(0.0, follow + passing, 180)
            phase = x / max(follow + passing, 1e-6)
            bump = np.sin(np.pi * np.clip(phase, 0.0, 1.0)) ** 2
            plot.plot(x, slow + boost * bump, pen=pg.mkPen((215, 145, 25), width=2))

        plot = self.plots.get("Rauschen")
        if plot is not None:
            plot.clear()
            std = max(0.0, self._value("noise_std_kmh", 1.8))
            tau = max(0.1, self._value("noise_tau_s", 3.5))
            t = np.linspace(0.0, 20.0, 180)
            dt = float(t[1] - t[0])
            alpha = math.exp(-dt / tau)
            rng = np.random.default_rng(12345)
            noise = np.zeros_like(t)
            for index in range(1, len(t)):
                noise[index] = (
                    alpha * noise[index - 1]
                    + math.sqrt(max(0.0, 1.0 - alpha * alpha)) * std * rng.normal()
                )
            plot.plot(t, noise, pen=pg.mkPen((45, 145, 80), width=1.8))
            plot.addLine(y=0.0, pen=pg.mkPen((120, 120, 120), width=1))

        plot = self.plots.get("Fahrzeug")
        if plot is not None:
            plot.clear()
            v_kmh = np.linspace(0.0, 160.0, 161)
            v = v_kmh / 3.6
            mass = max(1.0, self._value("vehicle_mass_kg", 1800.0))
            crr = max(0.0, self._value("rolling_resistance_coeff", 0.015))
            cd = max(0.0, self._value("air_drag_coefficient", 0.29))
            area = max(0.0, self._value("frontal_area_m2", 2.3))
            rho = max(0.0, self._value("air_density_kg_m3", 1.225))
            roll = mass * 9.80665 * crr * v / 1000.0
            air = 0.5 * rho * cd * area * v**3 / 1000.0
            total = roll + air
            trailer = self.window._control_widgets.get("use_trailer_model")
            if isinstance(trailer, QCheckBox) and trailer.isChecked():
                trailer_mass = max(0.0, self._value("trailer_mass_kg", 0.0))
                trailer_crr = max(
                    0.0, self._value("trailer_rolling_resistance_coeff", crr)
                )
                trailer_cda = max(0.0, self._value("trailer_drag_area_m2", 1.0))
                total += trailer_mass * 9.80665 * trailer_crr * v / 1000.0
                total += 0.5 * rho * trailer_cda * v**3 / 1000.0
            plot.plot(
                v_kmh,
                air,
                pen=pg.mkPen((100, 100, 100), width=1.2, style=Qt.PenStyle.DashLine),
            )
            plot.plot(v_kmh, total, pen=pg.mkPen((25, 100, 210), width=2.0))
