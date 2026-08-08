from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QFileSystemWatcher, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

try:
    from .speed_simulation import (
        DRIVER_PROFILES,
        export_simulation,
        load_route_result,
        merged_parameters,
        profile_parameters,
        simulate_speed_profile,
    )
except ImportError:
    from speed_simulation import (
        DRIVER_PROFILES,
        export_simulation,
        load_route_result,
        merged_parameters,
        profile_parameters,
        simulate_speed_profile,
    )


class LiveSpeedProfileWindow(QMainWindow):
    """Live editor and plotter for the simulated driving-speed profile."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Live-Geschwindigkeitsverlauf")
        self.resize(1500, 900)

        self._route_path = Path(route_path or "route_result.json").expanduser().resolve()
        self._route: dict[str, Any] | None = None
        self._result: dict[str, Any] | None = None
        self._control_widgets: dict[str, QWidget] = {}
        self._event_items: list[Any] = []
        self._profile_update_active = False
        self._light_count_initialized = False
        self._last_route_mtime_ns = 0

        self._recalculate_timer = QTimer(self)
        self._recalculate_timer.setSingleShot(True)
        self._recalculate_timer.setInterval(120)
        self._recalculate_timer.timeout.connect(self.recalculate)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_route_file)
        self._poll_timer.start()

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._route_file_changed)

        self._build_ui()
        self._build_menu()
        self._apply_profile("normalo")
        self.reload_route(silent=True)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Datei")
        open_action = QAction("route_result.json öffnen …", self)
        open_action.triggered.connect(self.choose_route_file)
        file_menu.addAction(open_action)
        reload_action = QAction("Route neu laden", self)
        reload_action.triggered.connect(self.reload_route)
        file_menu.addAction(reload_action)
        export_action = QAction("Simulation exportieren …", self)
        export_action.triggered.connect(self.export_result)
        file_menu.addAction(export_action)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        control_scroll = QScrollArea()
        control_scroll.setWidgetResizable(True)
        control_scroll.setMinimumWidth(390)
        control_scroll.setMaximumWidth(520)
        control_root = QWidget()
        control_scroll.setWidget(control_root)
        control_layout = QVBoxLayout(control_root)
        control_layout.setContentsMargins(10, 10, 10, 10)
        control_layout.setSpacing(10)

        route_box = QGroupBox("Route")
        route_layout = QGridLayout(route_box)
        self.route_path_label = QLabel(str(self._route_path))
        self.route_path_label.setWordWrap(True)
        route_layout.addWidget(self.route_path_label, 0, 0, 1, 3)
        choose_button = QPushButton("Datei wählen")
        choose_button.clicked.connect(self.choose_route_file)
        reload_button = QPushButton("Neu laden")
        reload_button.clicked.connect(self.reload_route)
        export_button = QPushButton("CSV + JSON exportieren")
        export_button.clicked.connect(self.export_result)
        route_layout.addWidget(choose_button, 1, 0)
        route_layout.addWidget(reload_button, 1, 1)
        route_layout.addWidget(export_button, 1, 2)
        control_layout.addWidget(route_box)

        profile_box = QGroupBox("Fahrer")
        profile_form = QFormLayout(profile_box)
        self.profile_combo = QComboBox()
        for key, profile in DRIVER_PROFILES.items():
            self.profile_combo.addItem(str(profile["label"]), key)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        profile_form.addRow("Preset", self.profile_combo)
        self.profile_note = QLabel()
        self.profile_note.setWordWrap(True)
        profile_form.addRow("Beschreibung", self.profile_note)
        self._add_double(profile_form, "Temperament", "temperament", 0.4, 1.8, 0.05, 1.0, " ×", 2)
        self._add_double(profile_form, "Reisegeschwindigkeit", "driver_cruise_kmh", 5, 250, 5, 130, " km/h")
        self._add_double(profile_form, "Absolute Obergrenze", "driver_hard_max_kmh", 5, 300, 5, 140, " km/h")
        self._add_double(profile_form, "Geschwindigkeits-Bias", "speed_bias_kmh", -20, 30, 0.5, 0, " km/h")
        self._add_double(profile_form, "Toleranz", "speed_tolerance_kmh", 0, 20, 0.5, 1, " km/h")
        self._add_double(profile_form, "Regler Kp", "Kp", 0.05, 3.0, 0.05, 1.1, decimals=2)
        self._add_double(profile_form, "Max. Beschleunigung", "a_max_mps2", 0.1, 8, 0.1, 2.8, " m/s²")
        self._add_double(profile_form, "Max. Verzögerung", "b_max_mps2", 0.1, 8, 0.1, 3.0, " m/s²")
        self._add_double(profile_form, "Max. Ruck", "j_max_mps3", 0.05, 5, 0.05, 1.2, " m/s³")
        self._add_check(profile_form, "Start bei 0 km/h", "start_stop", True)
        self._add_check(profile_form, "Am Ziel anhalten", "end_stop", True)
        control_layout.addWidget(profile_box)

        tabs = QTabWidget()
        tabs.addTab(self._curve_tab(), "Kurven")
        tabs.addTab(self._traffic_tab(), "Ampeln")
        tabs.addTab(self._overtaking_tab(), "Überholen")
        tabs.addTab(self._noise_tab(), "Rauschen")
        tabs.addTab(self._vehicle_tab(), "Fahrzeug")
        control_layout.addWidget(tabs)
        control_layout.addStretch(1)

        plot_root = QWidget()
        plot_layout = QVBoxLayout(plot_root)
        plot_layout.setContentsMargins(6, 6, 6, 6)
        plot_layout.setSpacing(6)

        self.summary_label = QLabel("Noch keine Route geladen.")
        self.summary_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.summary_label.setMargin(8)
        self.summary_label.setWordWrap(True)
        plot_layout.addWidget(self.summary_label)

        pg.setConfigOptions(antialias=True)
        self.distance_plot = pg.PlotWidget(title="Geschwindigkeit über Strecke")
        self.distance_plot.setLabel("left", "Geschwindigkeit", units="km/h")
        self.distance_plot.setLabel("bottom", "Strecke", units="km")
        self.distance_plot.showGrid(x=True, y=True, alpha=0.25)
        self.distance_plot.addLegend(offset=(10, 10))
        plot_layout.addWidget(self.distance_plot, 3)

        self.time_plot = pg.PlotWidget(title="Geschwindigkeit über Zeit")
        self.time_plot.setLabel("left", "Geschwindigkeit", units="km/h")
        self.time_plot.setLabel("bottom", "Zeit", units="min")
        self.time_plot.showGrid(x=True, y=True, alpha=0.25)
        self.time_plot.addLegend(offset=(10, 10))
        plot_layout.addWidget(self.time_plot, 2)

        self.acceleration_plot = pg.PlotWidget(title="Längsbeschleunigung")
        self.acceleration_plot.setLabel("left", "Beschleunigung", units="m/s²")
        self.acceleration_plot.setLabel("bottom", "Zeit", units="min")
        self.acceleration_plot.showGrid(x=True, y=True, alpha=0.25)
        plot_layout.addWidget(self.acceleration_plot, 1)

        splitter.addWidget(control_scroll)
        splitter.addWidget(plot_root)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.statusBar().showMessage("Warte auf route_result.json …")

    def _curve_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add_check(form, "Kurvenlimit verwenden", "apply_curve_speed", True)
        self._add_double(form, "Max. Querbeschleunigung", "max_lat_accel_mps2", 0.2, 6, 0.05, 2.2, " m/s²")
        self._add_double(form, "Minimaler Radius", "min_curve_radius_m", 2, 100, 1, 8, " m")
        self._add_double(form, "Maximaler Radius", "max_curve_radius_m", 100, 20000, 100, 5000, " m")
        self._add_double(form, "Abtastabstand", "curve_sample_distance_m", 3, 100, 1, 12, " m")
        self._add_double(form, "Glättungsfenster", "curve_smooth_distance_m", 0, 200, 5, 25, " m")
        self._add_double(form, "Plan-Verzögerung", "curve_plan_decel_mps2", 0.2, 6, 0.1, 1.8, " m/s²")
        self._add_check(form, "Straßenbelag berücksichtigen", "use_surface_limit", True)
        return page

    def _traffic_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add_check(form, "Ampelvorgänge verwenden", "use_traffic_lights", True)
        self._add_int(form, "Anzahl Stopps", "traffic_light_count", 0, 100, 1, 0)
        self.detected_lights_label = QLabel("Erkannte Ampeln: –")
        form.addRow("OSM", self.detected_lights_label)
        self._add_double(form, "Rotphase min.", "traffic_light_dwell_min_s", 0, 180, 1, 20, " s")
        self._add_double(form, "Rotphase max.", "traffic_light_dwell_max_s", 0, 300, 1, 60, " s")
        self._add_double(form, "Plan-Verzögerung", "traffic_light_plan_decel_mps2", 0.2, 6, 0.1, 1.8, " m/s²")
        self._add_double(form, "Stopptoleranz", "traffic_light_stop_tolerance_m", 0.5, 10, 0.5, 2, " m")
        return page

    def _overtaking_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add_check(form, "Überholvorgänge verwenden", "use_overtaking", False)
        self._add_int(form, "Anzahl", "overtaking_count", 0, 50, 1, 0)
        self._add_double(form, "Langsames Fahrzeug", "overtaking_slow_speed_kmh", 10, 160, 5, 70, " km/h")
        self._add_double(form, "Intensität / Boost", "overtaking_intensity_kmh", 0, 80, 2, 20, " km/h")
        self._add_double(form, "Folgestrecke", "overtaking_follow_distance_m", 20, 1000, 10, 180, " m")
        self._add_double(form, "Überholstrecke", "overtaking_pass_distance_m", 20, 1000, 10, 100, " m")
        return page

    def _noise_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add_check(form, "Fahrerrauschen", "use_driver_noise", True)
        self._add_double(form, "Standardabweichung", "noise_std_kmh", 0, 20, 0.1, 1.8, " km/h")
        self._add_double(form, "Zeitkonstante", "noise_tau_s", 0.1, 120, 0.5, 3.5, " s")
        self._add_int(form, "Zufalls-Seed", "simulation_seed", 0, 2_000_000_000, 1, 42)
        return page

    def _vehicle_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add_check(form, "Massen-/Anhänger-Modell", "use_trailer_model", False)
        self._add_double(form, "Fahrzeugmasse", "vehicle_mass_kg", 300, 10000, 50, 1800, " kg")
        self._add_double(form, "Anhängermasse", "trailer_mass_kg", 0, 10000, 50, 1200, " kg")
        self._add_double(form, "Rollwiderstand", "rolling_resistance_coeff", 0, 0.1, 0.001, 0.015, decimals=3)
        self._add_double(form, "Max. Antriebskraft", "max_drive_force_n", 500, 50000, 100, 5200, " N")
        self._add_double(form, "Max. Bremskraft", "max_brake_force_n", 500, 100000, 100, 9000, " N")
        note = QLabel(
            "Das aktuelle Routing liefert noch kein Höhenprofil. Das Massenmodell begrenzt "
            "deshalb zunächst Beschleunigung und Bremsung auf ebener Strecke."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _add_double(
        self,
        form: QFormLayout,
        label: str,
        key: str,
        minimum: float,
        maximum: float,
        step: float,
        value: float,
        suffix: str = "",
        decimals: int = 1,
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

    def _add_int(
        self,
        form: QFormLayout,
        label: str,
        key: str,
        minimum: int,
        maximum: int,
        step: int,
        value: int,
    ) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setValue(value)
        widget.setKeyboardTracking(False)
        widget.valueChanged.connect(self.schedule_recalculate)
        self._control_widgets[key] = widget
        form.addRow(label, widget)
        return widget

    def _add_check(self, form: QFormLayout, label: str, key: str, checked: bool) -> QCheckBox:
        widget = QCheckBox()
        widget.setChecked(checked)
        widget.toggled.connect(self.schedule_recalculate)
        self._control_widgets[key] = widget
        form.addRow(label, widget)
        return widget

    def _profile_changed(self) -> None:
        if not self._profile_update_active:
            self._apply_profile(str(self.profile_combo.currentData()))

    def _apply_profile(self, name: str) -> None:
        profile = DRIVER_PROFILES.get(name, DRIVER_PROFILES["normalo"])
        parameters = profile_parameters(name)
        self._profile_update_active = True
        try:
            index = self.profile_combo.findData(name)
            if index >= 0 and self.profile_combo.currentIndex() != index:
                self.profile_combo.setCurrentIndex(index)
            self.profile_note.setText(str(profile["note"]))
            for key, value in parameters.items():
                widget = self._control_widgets.get(key)
                if isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
        finally:
            self._profile_update_active = False
        self.schedule_recalculate()

    def parameters(self) -> dict[str, Any]:
        values: dict[str, Any] = {"driver_profile": str(self.profile_combo.currentData())}
        for key, widget in self._control_widgets.items():
            if isinstance(widget, QDoubleSpinBox):
                values[key] = float(widget.value())
            elif isinstance(widget, QSpinBox):
                values[key] = int(widget.value())
            elif isinstance(widget, QCheckBox):
                values[key] = bool(widget.isChecked())
        return merged_parameters(values)

    def schedule_recalculate(self, *_args: Any) -> None:
        if not self._profile_update_active:
            self._recalculate_timer.start()

    def choose_route_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "route_result.json auswählen",
            str(self._route_path.parent),
            "Route result (route_result.json *.json);;JSON (*.json);;Alle Dateien (*)",
        )
        if selected:
            self.set_route_path(selected)
            self.reload_route()

    def set_route_path(self, path: str | Path) -> None:
        self._route_path = Path(path).expanduser().resolve()
        self.route_path_label.setText(str(self._route_path))
        for watched in self._watcher.files():
            self._watcher.removePath(watched)
        if self._route_path.is_file():
            self._watcher.addPath(str(self._route_path))

    def _route_file_changed(self, _path: str) -> None:
        QTimer.singleShot(150, lambda: self.reload_route(silent=True))

    def _poll_route_file(self) -> None:
        if not self._route_path.is_file():
            return
        try:
            mtime = self._route_path.stat().st_mtime_ns
        except OSError:
            return
        if mtime != self._last_route_mtime_ns:
            self.reload_route(silent=True)

    def reload_route(self, *_args: Any, silent: bool = False) -> None:
        if not self._route_path.is_file():
            if not silent:
                QMessageBox.information(
                    self,
                    "Route fehlt",
                    f"Noch keine Route gefunden:\n{self._route_path}\n\n"
                    "Berechne zuerst eine Route in der Kartenanwendung.",
                )
            self.statusBar().showMessage("Warte auf route_result.json …")
            return
        try:
            route = load_route_result(self._route_path)
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "Route konnte nicht geladen werden", str(exc))
            self.statusBar().showMessage(f"Route konnte nicht geladen werden: {exc}")
            return

        self._route = route
        self._last_route_mtime_ns = self._route_path.stat().st_mtime_ns
        self.set_route_path(self._route_path)
        detected = len(route.get("traffic_signals", []))
        self.detected_lights_label.setText(f"Erkannte Ampeln: {detected}")
        if not self._light_count_initialized:
            light_widget = self._control_widgets.get("traffic_light_count")
            if isinstance(light_widget, QSpinBox):
                light_widget.setValue(detected)
            self._light_count_initialized = True
        self.statusBar().showMessage("Route geladen; Änderungen werden live berechnet.")
        self.recalculate()

    def recalculate(self) -> None:
        if self._route is None:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._result = simulate_speed_profile(self._route, self.parameters())
            self._update_plots()
        except Exception as exc:
            self.statusBar().showMessage(f"Simulation fehlgeschlagen: {exc}")
            QMessageBox.critical(self, "Simulation fehlgeschlagen", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _add_region(self, plot: pg.PlotWidget, start: float, end: float, color: tuple[int, int, int, int]) -> None:
        region = pg.LinearRegionItem(values=(start, end), movable=False, brush=color, pen=None)
        region.setZValue(-20)
        plot.addItem(region)
        self._event_items.append((plot, region))

    def _update_plots(self) -> None:
        if self._result is None:
            return
        self.distance_plot.clear()
        self.time_plot.clear()
        self.acceleration_plot.clear()
        self._event_items.clear()

        distance = self._result["distance"]
        time = self._result["time"]
        events = self._result["events"]
        summary = self._result["summary"]

        x_km = distance["distance_m"] / 1000.0
        self.distance_plot.plot(x_km, distance["road_limit_kmh"], pen=pg.mkPen((90, 90, 90), width=1.3, style=Qt.PenStyle.DashLine), name="Straßenlimit")
        curve = distance["curve_limit_kmh"].copy()
        curve[~(curve < 400.0)] = float("nan")
        self.distance_plot.plot(x_km, curve, pen=pg.mkPen((135, 55, 160), width=1.4, style=Qt.PenStyle.DotLine), name="Kurvenlimit")
        self.distance_plot.plot(x_km, distance["base_target_kmh"], pen=pg.mkPen((220, 140, 25), width=1.2), name="Basis/Soll")
        self.distance_plot.plot(x_km, distance["planned_speed_kmh"], pen=pg.mkPen((30, 140, 85), width=1.8), name="Geplant")
        self.distance_plot.plot(x_km, distance["actual_speed_kmh"], pen=pg.mkPen((25, 100, 210), width=2.5), name="Fahrer simuliert")

        for event in events["traffic_lights"]:
            line = pg.InfiniteLine(float(event["distance_m"]) / 1000.0, angle=90, pen=pg.mkPen((210, 40, 40, 180), width=1.5))
            self.distance_plot.addItem(line)
            self._event_items.append((self.distance_plot, line))
        for event in events["overtaking"]:
            self._add_region(
                self.distance_plot,
                float(event["follow_start_m"]) / 1000.0,
                float(event["pass_end_m"]) / 1000.0,
                (70, 130, 220, 45),
            )

        time_min = time["time_s"] / 60.0
        self.time_plot.plot(time_min, time["target_kmh"], pen=pg.mkPen((220, 140, 25), width=1.3), name="Soll")
        self.time_plot.plot(time_min, time["speed_kmh"], pen=pg.mkPen((25, 100, 210), width=2.5), name="Simuliert")
        for start, end in events["traffic_light_dwell_intervals_s"]:
            self._add_region(self.time_plot, float(start) / 60.0, float(end) / 60.0, (220, 50, 50, 55))

        self.acceleration_plot.plot(time_min, time["acceleration_mps2"], pen=pg.mkPen((35, 125, 90), width=1.8))
        self.acceleration_plot.addLine(y=0.0, pen=pg.mkPen((100, 100, 100), width=1))

        self.distance_plot.enableAutoRange()
        self.time_plot.enableAutoRange()
        self.acceleration_plot.enableAutoRange()

        profile = DRIVER_PROFILES.get(str(self.profile_combo.currentData()), DRIVER_PROFILES["normalo"])
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

    def export_result(self) -> None:
        if self._result is None:
            QMessageBox.information(self, "Keine Simulation", "Zuerst eine Route laden und simulieren.")
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Simulation exportieren",
            str(self._route_path.parent / "speed_profile_result"),
            "Dateipräfix (*.json)",
        )
        if not selected:
            return
        prefix = Path(selected)
        if prefix.suffix.lower() in {".json", ".csv"}:
            prefix = prefix.with_suffix("")
        try:
            json_path, csv_path = export_simulation(self._result, prefix)
        except Exception as exc:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(exc))
            return
        self.statusBar().showMessage(f"Gespeichert: {json_path.name} und {csv_path.name}")


def _default_route_path() -> Path:
    candidates = [
        Path.cwd() / "route_result.json",
        Path(__file__).resolve().parent / "route_result.json",
        Path(__file__).resolve().parent.parent / "route_result.json",
    ]
    return next((path.resolve() for path in candidates if path.is_file()), candidates[0].resolve())


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Live Speed Profile")
    window = LiveSpeedProfileWindow(_default_route_path())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
