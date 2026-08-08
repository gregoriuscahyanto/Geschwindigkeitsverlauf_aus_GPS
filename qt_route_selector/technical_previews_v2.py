from __future__ import annotations

import math
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


GROUP_KEYS: dict[str, set[str]] = {
    "Fahrer": {
        "temperament",
        "driver_cruise_kmh",
        "driver_hard_max_kmh",
        "speed_bias_kmh",
        "speed_tolerance_kmh",
        "Kp",
        "a_max_mps2",
        "b_max_mps2",
        "j_max_mps3",
        "use_post_curve_overshoot",
        "post_curve_overshoot_kmh",
        "post_curve_overshoot_probability_pct",
        "post_curve_overshoot_distance_m",
    },
    "Kurven": {
        "apply_curve_speed",
        "max_lat_accel_mps2",
        "min_curve_radius_m",
        "max_curve_radius_m",
        "curve_sample_distance_m",
        "curve_smooth_distance_m",
        "curve_plan_decel_mps2",
    },
    "Ampeln": {
        "use_traffic_lights",
        "traffic_light_dwell_min_s",
        "traffic_light_dwell_max_s",
        "traffic_light_plan_decel_mps2",
        "traffic_light_stop_tolerance_m",
    },
    "Überholen": {
        "use_overtaking",
        "overtaking_count",
        "overtaking_slow_speed_kmh",
        "overtaking_intensity_kmh",
        "overtaking_follow_distance_m",
        "overtaking_pass_distance_m",
    },
    "Rauschen": {
        "use_driver_noise",
        "noise_std_kmh",
        "noise_tau_s",
    },
    "Fahrzeug": {
        "vehicle_mass_kg",
        "rolling_resistance_coeff",
        "air_drag_coefficient",
        "frontal_area_m2",
        "air_density_kg_m3",
        "use_trailer_model",
        "trailer_mass_kg",
        "trailer_rolling_resistance_coeff",
        "trailer_drag_area_m2",
    },
}


class FriendlyTechnicalPreviews:
    """Turn the legacy always-visible mini plots into contextual live comparisons."""

    def __init__(self, window: Any, legacy_controller: Any) -> None:
        self.window = window
        self.plots: dict[str, pg.PlotWidget] = dict(getattr(legacy_controller, "plots", {}))
        self.baseline: dict[str, Any] = {}
        self.changed_keys: set[str] = set()
        self.buttons: dict[str, QToolButton] = {}
        self._install_disclosures()
        self.update()

    def set_baseline(self, values: dict[str, Any]) -> None:
        self.baseline = dict(values)
        self.update()

    def set_changed_keys(self, keys: set[str]) -> None:
        self.changed_keys = set(keys)
        self._refresh_buttons()

    def _install_disclosures(self) -> None:
        for group, plot in self.plots.items():
            plot.setFixedHeight(112)
            plot.setMaximumHeight(112)
            plot.hide()
            parent = plot.parentWidget()
            layout = parent.layout() if parent is not None else None
            if layout is None:
                continue

            button = QToolButton(parent)
            button.setCheckable(True)
            button.setChecked(False)
            button.setArrowType(Qt.ArrowType.RightArrow)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setText("Auswirkung anzeigen")
            button.setToolTip(
                "Zeigt eine kleine technische Vorschau. Gestrichelt = Preset, "
                "durchgezogen = aktuelle Einstellung."
            )
            button.toggled.connect(
                lambda checked, current_plot=plot, current_button=button: self._toggle_plot(
                    current_plot, current_button, checked
                )
            )

            if isinstance(layout, QFormLayout):
                row, _role = layout.getWidgetPosition(plot)
                layout.removeWidget(plot)
                wrapper = QWidget(parent)
                wrapper_layout = QVBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 2, 0, 2)
                wrapper_layout.setSpacing(4)
                wrapper_layout.addWidget(button)
                wrapper_layout.addWidget(plot)
                layout.insertRow(max(0, row), wrapper)
            elif isinstance(layout, QVBoxLayout):
                index = layout.indexOf(plot)
                layout.removeWidget(plot)
                wrapper = QWidget(parent)
                wrapper_layout = QVBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 2, 0, 2)
                wrapper_layout.setSpacing(4)
                wrapper_layout.addWidget(button)
                wrapper_layout.addWidget(plot)
                layout.insertWidget(max(0, index), wrapper)
            else:
                continue
            self.buttons[group] = button
        self._refresh_buttons()

    @staticmethod
    def _toggle_plot(plot: pg.PlotWidget, button: QToolButton, checked: bool) -> None:
        plot.setVisible(bool(checked))
        button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def _refresh_buttons(self) -> None:
        for group, button in self.buttons.items():
            changed = bool(GROUP_KEYS.get(group, set()) & self.changed_keys)
            button.setText("Änderung ansehen" if changed else "Auswirkung anzeigen")
            button.setStyleSheet(
                "QToolButton { text-align:left; padding:5px 7px; border-radius:7px; "
                + (
                    "border:1px solid palette(highlight); background:palette(alternate-base); "
                    "font-weight:600;"
                    if changed
                    else "border:1px solid palette(midlight); background:palette(base);"
                )
                + " } QToolButton:hover { border-color:palette(highlight); }"
            )
            button.setToolTip(
                ("In dieser Gruppe wurden Werte gegenüber dem Preset geändert. " if changed else "")
                + "Gestrichelt = Preset, durchgezogen = aktuell."
            )

    def _current(self, key: str, default: float) -> float:
        widget = self.window._control_widgets.get(key)
        if hasattr(widget, "value"):
            return float(widget.value())
        return float(default)

    def _baseline(self, key: str, default: float) -> float:
        try:
            return float(self.baseline.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _checked(self, key: str, default: bool = False, *, baseline: bool = False) -> bool:
        if baseline:
            return bool(self.baseline.get(key, default))
        widget = self.window._control_widgets.get(key)
        return bool(widget.isChecked()) if isinstance(widget, QCheckBox) else bool(default)

    @staticmethod
    def _pens() -> tuple[Any, Any]:
        preset = pg.mkPen((145, 145, 145), width=1.3, style=Qt.PenStyle.DashLine)
        current = pg.mkPen((45, 145, 255), width=2.2)
        return preset, current

    def _driver_curve(self, baseline: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cruise = self._baseline("driver_cruise_kmh", 50.0) if baseline else self._current("driver_cruise_kmh", 50.0)
        a_max = max(0.1, self._baseline("a_max_mps2", 2.8) if baseline else self._current("a_max_mps2", 2.8))
        kp = max(0.05, self._baseline("Kp", 1.1) if baseline else self._current("Kp", 1.1))
        t = np.linspace(0.0, 8.0, 121)
        exponential = cruise * (1.0 - np.exp(-kp * t / 2.2))
        response = np.minimum(exponential, a_max * 3.6 * t)
        return t, np.full_like(t, cruise), response

    def _traffic_curve(self, baseline: bool) -> tuple[np.ndarray, np.ndarray]:
        cruise = self._baseline("driver_cruise_kmh", 50.0) if baseline else self._current("driver_cruise_kmh", 50.0)
        a_max = max(0.1, self._baseline("a_max_mps2", 2.8) if baseline else self._current("a_max_mps2", 2.8))
        decel = max(0.2, self._baseline("traffic_light_plan_decel_mps2", 1.8) if baseline else self._current("traffic_light_plan_decel_mps2", 1.8))
        dwell_min = self._baseline("traffic_light_dwell_min_s", 20.0) if baseline else self._current("traffic_light_dwell_min_s", 20.0)
        dwell_max = self._baseline("traffic_light_dwell_max_s", 60.0) if baseline else self._current("traffic_light_dwell_max_s", 60.0)
        dwell = 0.5 * (dwell_min + dwell_max)
        v0 = min(max(20.0, cruise), 80.0)
        brake_time = v0 / 3.6 / decel
        accel_time = v0 / 3.6 / a_max
        total_time = brake_time + dwell + accel_time + 4.0
        t = np.linspace(0.0, total_time, 180)
        speed = np.zeros_like(t)
        braking = t <= brake_time
        speed[braking] = np.maximum(0.0, v0 * (1.0 - t[braking] / max(brake_time, 1e-6)))
        start_accel = brake_time + dwell
        accelerating = t >= start_accel
        speed[accelerating] = np.minimum(v0, (t[accelerating] - start_accel) * a_max * 3.6)
        return t, speed

    def _overtake_curve(self, baseline: bool) -> tuple[np.ndarray, np.ndarray]:
        get = self._baseline if baseline else self._current
        follow = max(20.0, get("overtaking_follow_distance_m", 180.0))
        passing = max(20.0, get("overtaking_pass_distance_m", 100.0))
        slow = get("overtaking_slow_speed_kmh", 70.0)
        boost = get("overtaking_intensity_kmh", 20.0)
        x = np.linspace(0.0, follow + passing, 180)
        phase = x / max(follow + passing, 1e-6)
        bump = np.sin(np.pi * np.clip(phase, 0.0, 1.0)) ** 2
        return x, slow + boost * bump

    def _noise_curve(self, baseline: bool) -> tuple[np.ndarray, np.ndarray]:
        get = self._baseline if baseline else self._current
        std = max(0.0, get("noise_std_kmh", 1.8))
        tau = max(0.1, get("noise_tau_s", 3.5))
        t = np.linspace(0.0, 20.0, 180)
        dt = float(t[1] - t[0])
        alpha = math.exp(-dt / tau)
        rng = np.random.default_rng(12345)
        noise = np.zeros_like(t)
        for index in range(1, len(t)):
            noise[index] = alpha * noise[index - 1] + math.sqrt(max(0.0, 1.0 - alpha * alpha)) * std * rng.normal()
        return t, noise

    def _vehicle_curve(self, baseline: bool) -> tuple[np.ndarray, np.ndarray]:
        get = self._baseline if baseline else self._current
        v_kmh = np.linspace(0.0, 160.0, 161)
        v = v_kmh / 3.6
        mass = max(1.0, get("vehicle_mass_kg", 1800.0))
        crr = max(0.0, get("rolling_resistance_coeff", 0.015))
        cd = max(0.0, get("air_drag_coefficient", 0.29))
        area = max(0.0, get("frontal_area_m2", 2.3))
        rho = max(0.0, get("air_density_kg_m3", 1.225))
        total = mass * 9.80665 * crr * v / 1000.0 + 0.5 * rho * cd * area * v**3 / 1000.0
        if self._checked("use_trailer_model", False, baseline=baseline):
            trailer_mass = max(0.0, get("trailer_mass_kg", 0.0))
            trailer_crr = max(0.0, get("trailer_rolling_resistance_coeff", crr))
            trailer_cda = max(0.0, get("trailer_drag_area_m2", 1.0))
            total += trailer_mass * 9.80665 * trailer_crr * v / 1000.0
            total += 0.5 * rho * trailer_cda * v**3 / 1000.0
        return v_kmh, total

    def update(self) -> None:
        if not self.plots:
            return
        preset_pen, current_pen = self._pens()

        plot = self.plots.get("Fahrer")
        if plot is not None:
            plot.clear()
            bt, btarget, bresponse = self._driver_curve(True)
            ct, ctarget, cresponse = self._driver_curve(False)
            plot.plot(bt, bresponse, pen=preset_pen)
            plot.plot(ct, cresponse, pen=current_pen)
            plot.plot(ct, ctarget, pen=pg.mkPen((110, 110, 110), width=1, style=Qt.PenStyle.DotLine))
            plot.setTitle("Fahrerreaktion: Preset ↔ aktuell")

        plot = self.plots.get("Kurven")
        if plot is not None:
            plot.clear()
            radius = np.geomspace(5.0, 1000.0, 120)
            b_lat = max(0.2, self._baseline("max_lat_accel_mps2", 2.2))
            c_lat = max(0.2, self._current("max_lat_accel_mps2", 2.2))
            plot.setLogMode(x=True, y=False)
            plot.plot(radius, np.sqrt(b_lat * radius) * 3.6, pen=preset_pen)
            plot.plot(radius, np.sqrt(c_lat * radius) * 3.6, pen=current_pen)
            plot.setTitle("Kurvengeschwindigkeit: Preset ↔ aktuell")

        plot = self.plots.get("Ampeln")
        if plot is not None:
            plot.clear()
            bx, by = self._traffic_curve(True)
            cx, cy = self._traffic_curve(False)
            plot.plot(bx, by, pen=preset_pen)
            plot.plot(cx, cy, pen=current_pen)
            plot.setTitle("Ampelreaktion: Preset ↔ aktuell")

        plot = self.plots.get("Überholen")
        if plot is not None:
            plot.clear()
            bx, by = self._overtake_curve(True)
            cx, cy = self._overtake_curve(False)
            plot.plot(bx, by, pen=preset_pen)
            plot.plot(cx, cy, pen=current_pen)
            plot.setTitle("Überholen: Preset ↔ aktuell")

        plot = self.plots.get("Rauschen")
        if plot is not None:
            plot.clear()
            bx, by = self._noise_curve(True)
            cx, cy = self._noise_curve(False)
            plot.plot(bx, by, pen=preset_pen)
            plot.plot(cx, cy, pen=current_pen)
            plot.addLine(y=0.0, pen=pg.mkPen((120, 120, 120), width=1))
            plot.setTitle("Fahrerrauschen: Preset ↔ aktuell")

        plot = self.plots.get("Fahrzeug")
        if plot is not None:
            plot.clear()
            bx, by = self._vehicle_curve(True)
            cx, cy = self._vehicle_curve(False)
            plot.plot(bx, by, pen=preset_pen)
            plot.plot(cx, cy, pen=current_pen)
            plot.setTitle("Fahrwiderstand: Preset ↔ aktuell")

        self._refresh_buttons()
