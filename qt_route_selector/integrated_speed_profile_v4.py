from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from .enhanced_speed_simulation import simulate_speed_profile as _enhanced_simulate
    from .integrated_speed_profile_v3 import IntegratedSpeedProfileWindow as _V3Window
    from .load_collective_curve import cumulative_load_curve
    from .resistance_power import calculate_resistance_power, road_grade
    from .technical_previews import TechnicalPreviewController
except ImportError:
    from enhanced_speed_simulation import simulate_speed_profile as _enhanced_simulate
    from integrated_speed_profile_v3 import IntegratedSpeedProfileWindow as _V3Window
    from load_collective_curve import cumulative_load_curve
    from resistance_power import calculate_resistance_power, road_grade
    from technical_previews import TechnicalPreviewController


_SCENARIO_COLORS: tuple[tuple[int, int, int], ...] = (
    (25, 100, 210),
    (210, 70, 45),
    (45, 145, 80),
    (145, 80, 175),
    (215, 145, 25),
    (35, 150, 165),
    (110, 75, 45),
    (105, 105, 105),
)

_SINGLE_SPEED_LEGEND = (
    ("Straßenlimit", (100, 100, 100)),
    ("Kurvenlimit", (135, 55, 160)),
    ("Soll", (220, 140, 25)),
    ("Simuliert", (25, 100, 210)),
)
_SINGLE_POWER_LEGEND = (
    ("Gesamt", (25, 25, 25)),
    ("Beschleunigung", (35, 125, 90)),
    ("Steigung", (145, 95, 45)),
    ("Roll", (100, 100, 100)),
    ("Luft", (25, 100, 210)),
    ("Anhänger", (135, 55, 160)),
)


class IntegratedSpeedProfileWindow(_V3Window):
    """V4 UI: cumulative duty cycles, snapshots, smoothing and technical previews."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._v4_ready = False
        self._comparison_configs: list[dict[str, Any]] = []
        self._comparison_results: list[dict[str, Any]] = []
        self._comparison_resistance: list[dict[str, Any] | None] = []
        self._comparison_names: list[str] = []
        self._loading_parameters = False
        self._fixed_legends: dict[str, QLabel] = {}
        self.preview_controller: TechnicalPreviewController | None = None
        super().__init__(route_path)

        self._remove_manual_dem_buttons()
        self._install_toolbar_controls()
        self._install_elevation_smoothing_control()
        self._install_comparison_controls()
        self._install_collective_controls()
        self._install_fixed_legends()
        self.preview_controller = TechnicalPreviewController(self)
        self._v4_ready = True
        self._update_fixed_legends()
        self._apply_plot_layout()

    # ------------------------------------------------------------------
    # Small UX helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _legend_html(entries: list[tuple[str, tuple[int, int, int]]]) -> str:
        parts: list[str] = []
        for name, color in entries:
            r, g, b = color
            parts.append(
                f"<span style='color:rgb({r},{g},{b});font-size:15px'>■</span> {name}"
            )
        return "&nbsp;&nbsp;&nbsp;".join(parts)

    def _hide_builtin_legends(self) -> None:
        for plot in (self.speed_plot, self.resistance_plot):
            legend = plot.plotItem.legend
            if legend is not None:
                legend.hide()

    def _install_toolbar_controls(self) -> None:
        toolbar = self.axis_combo.parentWidget()
        layout = toolbar.layout() if toolbar is not None else None
        if not isinstance(layout, QHBoxLayout):
            return

        self.reset_views_button = QPushButton("Ansicht zurücksetzen")
        self.reset_views_button.setToolTip(
            "Zoom und Verschiebung aller Zeit-/Streckenplots und des Lastkollektivs zurücksetzen."
        )
        self.reset_views_button.clicked.connect(self.reset_plot_views)
        layout.insertWidget(max(0, layout.count() - 1), self.reset_views_button)

        self.simulation_busy_label = QLabel("Simulation läuft …")
        self.simulation_busy_label.hide()
        layout.insertWidget(max(0, layout.count() - 1), self.simulation_busy_label)

        self.simulation_busy_bar = QProgressBar()
        self.simulation_busy_bar.setRange(0, 0)
        self.simulation_busy_bar.setMaximumWidth(130)
        self.simulation_busy_bar.setTextVisible(False)
        self.simulation_busy_bar.hide()
        layout.insertWidget(max(0, layout.count() - 1), self.simulation_busy_bar)

    def _set_busy(self, busy: bool, text: str = "Simulation läuft …") -> None:
        if hasattr(self, "simulation_busy_label"):
            self.simulation_busy_label.setText(text)
            self.simulation_busy_label.setVisible(busy)
        if hasattr(self, "simulation_busy_bar"):
            self.simulation_busy_bar.setVisible(busy)
        if busy:
            QApplication.processEvents()

    def reset_plot_views(self) -> None:
        for plot in (
            self.speed_plot,
            self.longitudinal_plot,
            self.elevation_plot,
            self.resistance_plot,
            self.load_collective_plot,
        ):
            plot.enableAutoRange()
        if self._result is not None and not self._comparison_configs:
            self._focus_speed_axis()

    # ------------------------------------------------------------------
    # Automatic DEM only + smoothed visible elevation
    # ------------------------------------------------------------------
    def _remove_manual_dem_buttons(self) -> None:
        for button in self.findChildren(QPushButton):
            if button.text() in {"DEM / GeoTIFF wählen", "DEM entfernen"}:
                button.hide()
                button.setEnabled(False)
                button.deleteLater()
        if self.dem_status_label is not None and self._dem_path is None:
            self.dem_status_label.setText(
                "Höhenmodell wird automatisch aus der Datenverwaltung übernommen."
            )

    def _install_elevation_smoothing_control(self) -> None:
        route_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Route"),
            None,
        )
        layout = route_group.layout() if route_group is not None else None
        if layout is None or not hasattr(layout, "addWidget"):
            return
        self.elevation_smoothing_spin = QDoubleSpinBox()
        self.elevation_smoothing_spin.setRange(0.0, 300.0)
        self.elevation_smoothing_spin.setSingleStep(5.0)
        self.elevation_smoothing_spin.setDecimals(0)
        self.elevation_smoothing_spin.setValue(30.0)
        self.elevation_smoothing_spin.setSuffix(" m")
        self.elevation_smoothing_spin.setKeyboardTracking(False)
        self.elevation_smoothing_spin.setToolTip(
            "Distanzfenster der sichtbaren Höhenkurve; 0 m zeigt die Rohwerte."
        )
        self.elevation_smoothing_spin.valueChanged.connect(
            lambda *_: self._update_plots() if self._result is not None else None
        )
        row = layout.rowCount() if hasattr(layout, "rowCount") else layout.count()
        try:
            layout.addWidget(QLabel("Höhenprofil-Glättung"), row, 0)
            layout.addWidget(self.elevation_smoothing_spin, row, 1, 1, 2)
        except TypeError:
            pass

    @staticmethod
    def _smooth_distance_series(
        distance_m: np.ndarray,
        values: np.ndarray,
        window_m: float,
    ) -> np.ndarray:
        distance = np.asarray(distance_m, dtype=float)
        data = np.asarray(values, dtype=float)
        if distance.shape != data.shape or data.size < 3 or window_m <= 0.0:
            return data.copy()
        finite = np.isfinite(distance) & np.isfinite(data)
        if np.count_nonzero(finite) < 2:
            return data.copy()
        clean = data.copy()
        clean[~finite] = np.interp(distance[~finite], distance[finite], data[finite])
        steps = np.diff(distance)
        steps = steps[steps > 1e-6]
        if steps.size == 0:
            return clean
        half_window = max(1, int(round(window_m / float(np.median(steps)) / 2.0)))
        kernel_size = 2 * half_window + 1
        if kernel_size >= clean.size:
            kernel_size = max(3, clean.size // 2 * 2 - 1)
            half_window = kernel_size // 2
        if kernel_size < 3:
            return clean
        padded = np.pad(clean, (half_window, half_window), mode="edge")
        kernel = np.ones(kernel_size, dtype=float) / float(kernel_size)
        return np.convolve(padded, kernel, mode="valid")

    def _spatial_elevation(self, sample_distance: np.ndarray) -> np.ndarray:
        raw = super()._spatial_elevation(sample_distance)
        window = (
            float(self.elevation_smoothing_spin.value())
            if hasattr(self, "elevation_smoothing_spin")
            else 30.0
        )
        return self._smooth_distance_series(sample_distance, raw, window)

    # ------------------------------------------------------------------
    # Snapshot-based multi-configuration comparison
    # ------------------------------------------------------------------
    def _install_comparison_controls(self) -> None:
        driver_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Fahrer"),
            None,
        )
        parent = driver_group.parentWidget() if driver_group is not None else None
        parent_layout = parent.layout() if parent is not None else None
        if driver_group is None or not isinstance(parent_layout, QVBoxLayout):
            return

        box = QGroupBox("Konfigurationen vergleichen")
        layout = QVBoxLayout(box)
        info = QLabel(
            "Aktuelle Einstellung speichern, Parameter ändern und direkt überlagert vergleichen. "
            "Bei nur einer Konfiguration bleiben alle Detailgrenzen sichtbar."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        name_row = QWidget()
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        self.compare_name_edit = QLineEdit("Vergleich 1")
        save_button = QPushButton("Aktuelle speichern")
        save_button.clicked.connect(self._save_comparison_config)
        name_layout.addWidget(self.compare_name_edit, 1)
        name_layout.addWidget(save_button)
        layout.addWidget(name_row)

        manage_row = QWidget()
        manage_layout = QHBoxLayout(manage_row)
        manage_layout.setContentsMargins(0, 0, 0, 0)
        self.compare_combo = QComboBox()
        load_button = QPushButton("Laden")
        delete_button = QPushButton("Löschen")
        clear_button = QPushButton("Alle löschen")
        load_button.clicked.connect(self._load_selected_comparison)
        delete_button.clicked.connect(self._delete_selected_comparison)
        clear_button.clicked.connect(self._clear_comparisons)
        manage_layout.addWidget(self.compare_combo, 1)
        manage_layout.addWidget(load_button)
        manage_layout.addWidget(delete_button)
        manage_layout.addWidget(clear_button)
        layout.addWidget(manage_row)

        index = parent_layout.indexOf(driver_group)
        parent_layout.insertWidget(max(0, index), box)
        self.comparison_group = box

    def _refresh_compare_combo(self) -> None:
        if not hasattr(self, "compare_combo"):
            return
        self.compare_combo.clear()
        for item in self._comparison_configs:
            self.compare_combo.addItem(str(item["name"]))
        self._update_fixed_legends()

    def _save_comparison_config(self) -> None:
        name = self.compare_name_edit.text().strip()
        if not name:
            name = f"Vergleich {len(self._comparison_configs) + 1}"
        self._comparison_configs.append(
            {"name": name, "parameters": copy.deepcopy(self.parameters())}
        )
        self.compare_name_edit.setText(f"Vergleich {len(self._comparison_configs) + 1}")
        self._refresh_compare_combo()
        self.recalculate()

    def _load_selected_comparison(self) -> None:
        index = self.compare_combo.currentIndex()
        if not (0 <= index < len(self._comparison_configs)):
            return
        self._apply_parameters(dict(self._comparison_configs[index]["parameters"]))

    def _delete_selected_comparison(self) -> None:
        index = self.compare_combo.currentIndex()
        if 0 <= index < len(self._comparison_configs):
            del self._comparison_configs[index]
            self._refresh_compare_combo()
            self.recalculate()

    def _clear_comparisons(self) -> None:
        self._comparison_configs.clear()
        self._refresh_compare_combo()
        self.recalculate()

    def _apply_parameters(self, parameters: dict[str, Any]) -> None:
        self._loading_parameters = True
        blocked: list[tuple[QWidget, bool]] = []
        try:
            profile_name = str(parameters.get("driver_profile", self.profile_combo.currentData()))
            old = self.profile_combo.blockSignals(True)
            blocked.append((self.profile_combo, old))
            profile_index = self.profile_combo.findData(profile_name)
            if profile_index >= 0:
                self.profile_combo.setCurrentIndex(profile_index)
            for key, widget in self._control_widgets.items():
                if key not in parameters:
                    continue
                old = widget.blockSignals(True)
                blocked.append((widget, old))
                value = parameters[key]
                if isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
        finally:
            for widget, old in reversed(blocked):
                widget.blockSignals(old)
            self._loading_parameters = False
        if self.preview_controller is not None:
            self.preview_controller.update()
        self.recalculate()

    def schedule_recalculate(self, *_args: Any) -> None:
        if self.preview_controller is not None:
            self.preview_controller.update()
        if not self._loading_parameters:
            super().schedule_recalculate(*_args)

    # ------------------------------------------------------------------
    # Fixed, non-movable legends
    # ------------------------------------------------------------------
    def _legend_label(self) -> QLabel:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setStyleSheet("QLabel { padding: 1px 3px; }")
        return label

    def _install_fixed_legends(self) -> None:
        stacked = self.speed_plot.parentWidget()
        layout = stacked.layout() if stacked is not None else None
        if not isinstance(layout, QVBoxLayout):
            return
        for key, plot in (
            ("speed", self.speed_plot),
            ("acceleration", self.longitudinal_plot),
            ("elevation", self.elevation_plot),
            ("power", self.resistance_plot),
        ):
            label = self._legend_label()
            layout.insertWidget(max(0, layout.indexOf(plot)), label)
            self._fixed_legends[key] = label

        right_layout = self.right_analysis_panel.layout() if self.right_analysis_panel else None
        if isinstance(right_layout, QVBoxLayout):
            label = self._legend_label()
            right_layout.insertWidget(max(0, right_layout.indexOf(self.load_collective_plot)), label)
            self._fixed_legends["collective"] = label
        self._hide_builtin_legends()

    def _comparison_entries(self) -> list[tuple[str, tuple[int, int, int]]]:
        names = ["Aktuell"] + [str(item["name"]) for item in self._comparison_configs]
        return [
            (name, _SCENARIO_COLORS[index % len(_SCENARIO_COLORS)])
            for index, name in enumerate(names)
        ]

    def _update_fixed_legends(self) -> None:
        if not self._fixed_legends:
            return
        if self._comparison_configs:
            html = self._legend_html(self._comparison_entries())
            for key in ("speed", "acceleration", "power", "collective"):
                if key in self._fixed_legends:
                    self._fixed_legends[key].setText(html)
            if "elevation" in self._fixed_legends:
                self._fixed_legends["elevation"].setText(
                    "Gemeinsames geglättetes Höhenprofil der Route"
                )
        else:
            self._fixed_legends["speed"].setText(
                self._legend_html(list(_SINGLE_SPEED_LEGEND))
            )
            self._fixed_legends["acceleration"].setText("Simulierte Längsbeschleunigung")
            self._fixed_legends["elevation"].setText("Geglättetes Straßenhöhenprofil")
            self._fixed_legends["power"].setText(
                self._legend_html(list(_SINGLE_POWER_LEGEND))
            )
            self._fixed_legends["collective"].setText("Kumulierte Lastdauerlinie")
        self._hide_builtin_legends()

    # ------------------------------------------------------------------
    # Cumulative load-duration curve
    # ------------------------------------------------------------------
    def _install_collective_controls(self) -> None:
        right_layout = self.right_analysis_panel.layout() if self.right_analysis_panel else None
        if not isinstance(right_layout, QVBoxLayout):
            return
        controls = QWidget()
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        self.collective_normalized_check = QCheckBox("normiert")
        self.collective_positive_check = QCheckBox("nur Antrieb")
        self.collective_log_check = QCheckBox("log. Zeitanteil")
        self.collective_log_check.setChecked(False)
        for check in (
            self.collective_normalized_check,
            self.collective_positive_check,
            self.collective_log_check,
        ):
            check.toggled.connect(lambda *_: self._plot_cumulative_collective())
            layout.addWidget(check)
        layout.addStretch(1)
        right_layout.insertWidget(max(0, right_layout.indexOf(self.load_collective_plot)), controls)
        self.collective_controls = controls

    def _plot_cumulative_collective(self) -> None:
        if not hasattr(self, "collective_normalized_check"):
            return
        self.load_collective_plot.clear()
        normalized = self.collective_normalized_check.isChecked()
        positive_only = self.collective_positive_check.isChecked()
        self.load_collective_plot.setTitle("Kumuliertes Lastkollektiv / Lastdauerlinie")
        self.load_collective_plot.setLabel("bottom", "Kumulierter Zeitanteil", units="%")
        self.load_collective_plot.setLabel(
            "left", "Normierte Last" if normalized else "Radleistung", units="" if normalized else "kW"
        )
        self.load_collective_plot.setLogMode(x=self.collective_log_check.isChecked(), y=False)

        datasets = (
            self._comparison_resistance
            if self._comparison_configs and self._comparison_resistance
            else [self._resistance_time_data]
        )
        for index, data in enumerate(datasets):
            if not data:
                continue
            curve = cumulative_load_curve(
                np.asarray(data["time_s"], dtype=float),
                np.asarray(data["total_kw"], dtype=float),
                positive_only=positive_only,
                normalize=normalized,
            )
            x = np.asarray(curve["time_share_pct"], dtype=float)
            y = np.asarray(curve["load"], dtype=float)
            if x.size == 0:
                continue
            color = _SCENARIO_COLORS[index % len(_SCENARIO_COLORS)]
            self.load_collective_plot.plot(x, y, pen=pg.mkPen(color, width=2.2))
        self.load_collective_plot.showGrid(x=True, y=True, alpha=0.25)
        self.load_collective_plot.enableAutoRange()

    # ------------------------------------------------------------------
    # Comparison simulation and plotting
    # ------------------------------------------------------------------
    def _resistance_for_result(
        self,
        result: dict[str, Any],
        parameters: dict[str, Any],
        elevation_distance: np.ndarray,
        elevation_values: np.ndarray,
    ) -> dict[str, Any] | None:
        try:
            spatial_distance = np.asarray(result["distance"]["distance_m"], dtype=float)
            time_data = result["time"]
            time_s = np.asarray(time_data["time_s"], dtype=float)
            time_distance = np.asarray(time_data["distance_m"], dtype=float)
            speed_kmh = np.asarray(time_data["speed_kmh"], dtype=float)
            acceleration = np.asarray(time_data["acceleration_mps2"], dtype=float)
        except (KeyError, TypeError, ValueError):
            return None
        if spatial_distance.size < 2 or time_s.size == 0:
            return None
        elevation = np.interp(spatial_distance, elevation_distance, elevation_values)
        available = np.count_nonzero(np.isfinite(elevation)) >= 2
        grade_spatial = road_grade(
            spatial_distance,
            elevation,
            smoothing_distance_m=float(parameters.get("grade_smoothing_m", 40.0)),
        )
        grade_time = np.interp(time_distance, spatial_distance, grade_spatial)
        data = calculate_resistance_power(
            time_s, speed_kmh, acceleration, grade_time, parameters
        )
        data["distance_m"] = time_distance
        data["spatial_distance_m"] = spatial_distance
        data["grade_spatial"] = grade_spatial
        data["elevation_available"] = available
        return data

    def recalculate(self) -> None:
        if self._route is None:
            return
        current_parameters = copy.deepcopy(self.parameters())
        parameter_sets = [current_parameters] + [
            copy.deepcopy(item["parameters"]) for item in self._comparison_configs
        ]
        names = ["Aktuell"] + [str(item["name"]) for item in self._comparison_configs]
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._set_busy(
                True,
                "Vergleich wird berechnet …" if self._comparison_configs else "Simulation läuft …",
            )
            results: list[dict[str, Any]] = []
            for parameters in parameter_sets:
                results.append(_enhanced_simulate(self._route, parameters))
                QApplication.processEvents()

            self._result = results[0]
            distance = np.asarray(self._result["distance"]["distance_m"], dtype=float)
            elevation = self._spatial_elevation(distance)
            resistance = [
                self._resistance_for_result(result, parameters, distance, elevation)
                for result, parameters in zip(results, parameter_sets)
            ]
            self._comparison_results = results
            self._comparison_resistance = resistance
            self._comparison_names = names
            self._resistance_time_data = resistance[0] if resistance else None
            self._update_plots()
        except Exception as exc:
            self.statusBar().showMessage(f"Simulation fehlgeschlagen: {exc}")
            QMessageBox.critical(self, "Simulation fehlgeschlagen", str(exc))
        finally:
            self._set_busy(False)
            QApplication.restoreOverrideCursor()

    def _update_plots(self) -> None:
        super()._update_plots()
        if not self._v4_ready:
            return
        if self._comparison_configs and self._comparison_results:
            self._plot_comparison()
        self._plot_cumulative_collective()
        self._update_fixed_legends()
        self._apply_plot_layout()
        if not self._comparison_configs:
            self._focus_speed_axis()

    def _plot_comparison(self) -> None:
        for plot in (
            self.speed_plot,
            self.longitudinal_plot,
            self.elevation_plot,
            self.resistance_plot,
        ):
            self._clear_plot(plot)
        self._event_items.clear()

        x_label, x_unit = ("Strecke", "km") if self._axis_mode == "distance" else ("Zeit", "min")
        for index, result in enumerate(self._comparison_results):
            color = _SCENARIO_COLORS[index % len(_SCENARIO_COLORS)]
            distance_data = result["distance"]
            time_data = result["time"]
            spatial_distance = np.asarray(distance_data["distance_m"], dtype=float)
            time_s = np.asarray(time_data["time_s"], dtype=float)
            time_distance = np.asarray(time_data["distance_m"], dtype=float)
            acceleration_time = np.asarray(time_data["acceleration_mps2"], dtype=float)
            resistance = self._comparison_resistance[index] if index < len(self._comparison_resistance) else None

            if self._axis_mode == "distance":
                x = spatial_distance / 1000.0
                speed = np.asarray(distance_data["actual_speed_kmh"], dtype=float)
                unique_distance, unique_indexes = np.unique(time_distance, return_index=True)
                if unique_distance.size >= 2:
                    acceleration = np.interp(
                        spatial_distance, unique_distance, acceleration_time[unique_indexes]
                    )
                    power = (
                        np.interp(
                            spatial_distance,
                            unique_distance,
                            np.asarray(resistance["total_kw"], dtype=float)[unique_indexes],
                        )
                        if resistance
                        else np.zeros_like(spatial_distance)
                    )
                else:
                    acceleration = np.zeros_like(spatial_distance)
                    power = np.zeros_like(spatial_distance)
            else:
                x = time_s / 60.0
                speed = np.asarray(time_data["speed_kmh"], dtype=float)
                acceleration = acceleration_time
                power = np.asarray(resistance["total_kw"], dtype=float) if resistance else np.zeros_like(time_s)

            pen = pg.mkPen(color, width=2.2)
            self.speed_plot.plot(x, speed, pen=pen)
            self.longitudinal_plot.plot(x, acceleration, pen=pen)
            self.resistance_plot.plot(x, power, pen=pen)

        distance = np.asarray(self._result["distance"]["distance_m"], dtype=float)
        elevation = self._spatial_elevation(distance)
        if self._axis_mode == "distance":
            elevation_x = distance / 1000.0
        else:
            current_time = self._result["time"]
            elevation_x = np.asarray(current_time["time_s"], dtype=float) / 60.0
            elevation = np.interp(
                np.asarray(current_time["distance_m"], dtype=float), distance, elevation
            )
        if np.any(np.isfinite(elevation)):
            self.elevation_plot.plot(
                elevation_x, elevation, pen=pg.mkPen((145, 95, 45), width=1.8)
            )

        self.longitudinal_plot.addLine(y=0.0, pen=pg.mkPen((100, 100, 100), width=1))
        self.resistance_plot.addLine(y=0.0, pen=pg.mkPen((100, 100, 100), width=1))
        for plot in (
            self.speed_plot,
            self.longitudinal_plot,
            self.elevation_plot,
            self.resistance_plot,
        ):
            plot.setLabel("bottom", x_label, units=x_unit)
            plot.enableAutoRange()
        self.speed_plot.setTitle("Geschwindigkeit – Konfigurationsvergleich")
        self.longitudinal_plot.setTitle("Längsbeschleunigung – Konfigurationsvergleich")
        self.elevation_plot.setTitle("Geglättetes Höhenprofil")
        self.resistance_plot.setTitle("Fahrwiderstandsleistung – Konfigurationsvergleich")

        self._install_hover_items()
        self._set_hover_index(0)
        self._update_comparison_summary()

    def _update_comparison_summary(self) -> None:
        rows: list[str] = []
        for index, result in enumerate(self._comparison_results):
            summary = result.get("summary", {})
            resistance = self._comparison_resistance[index] if index < len(self._comparison_resistance) else None
            energy = float(resistance["traction_energy_kwh"]) if resistance else 0.0
            rows.append(
                f"<b>{self._comparison_names[index]}</b>: "
                f"{float(summary.get('duration_min', 0.0)):.1f} min · "
                f"Ø {float(summary.get('average_speed_kmh', 0.0)):.1f} km/h · "
                f"Radenergie {energy:.2f} kWh"
            )
        self.summary_label.setText("<br>".join(rows))
        self.power_summary_label.setText(
            "Vergleichsmodus: dynamische Plots und Lastdauerlinie zeigen je Konfiguration genau eine Linie."
        )

    def _apply_plot_layout(self) -> None:
        super()._apply_plot_layout()
        if not self._v4_ready:
            return
        self.load_collective_plot.setMinimumHeight(220)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
