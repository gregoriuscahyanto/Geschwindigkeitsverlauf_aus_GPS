from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QMessageBox,
    QSplitter,
    QSizePolicy,
    QVBoxLayout,
)

try:
    from .enhanced_speed_simulation import simulate_speed_profile as _enhanced_simulate
    from .integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow
except ImportError:
    from enhanced_speed_simulation import simulate_speed_profile as _enhanced_simulate
    from integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow


class IntegratedSpeedProfileWindow(_BaseWindow):
    """UI refinement with focused plots and more human driver dynamics.

    Route loading is deliberately deferred during construction. The base live
    editor normally loads and simulates an existing route_result.json from its
    constructor, which can block the GUI before the main application window is
    shown. The complete application triggers reload_route() only when the
    simulation tab is opened or a newly calculated route arrives.
    """

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._v3_layout_ready = False

        actual_route_path = Path(route_path or "route_result.json").expanduser().resolve()
        deferred_route_path = actual_route_path.with_name(
            f".__startup_deferred_{actual_route_path.name}"
        )

        # The base constructor calls reload_route(silent=True). Give it a
        # guaranteed non-existing path so startup never performs route parsing
        # or a full speed simulation synchronously before the window is shown.
        super().__init__(deferred_route_path)

        self._route_path = actual_route_path
        if hasattr(self, "route_path_label"):
            self.route_path_label.setText(str(actual_route_path))
        self._install_post_curve_controls()
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

    def _update_plots(self) -> None:
        super()._update_plots()
        if self._v3_layout_ready:
            self._apply_plot_layout()
            self._focus_speed_axis()

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

        # Deliberately ignore curve_limit_kmh here. A nearly straight section
        # can mathematically yield several hundred km/h as a curvature limit;
        # that value is useful as a constraint but should not determine the
        # visual scale. Keep roughly 25 km/h headroom above the highest OSM
        # street limit on the route instead.
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
        # Also guard delayed/partial construction. This makes the class robust
        # when Qt or a base class requests an update during initialization.
        required = (
            "speed_plot",
            "longitudinal_plot",
            "elevation_plot",
            "map_widget",
        )
        if not all(hasattr(self, name) for name in required):
            return

        plots = (
            (self.speed_plot, 185),
            (self.longitudinal_plot, 155),
            (self.elevation_plot, 155),
        )
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

        # All three charts share the same x-axis. Only the bottom chart needs
        # tick labels, which leaves more vertical space for the curves.
        for plot in (self.speed_plot, self.longitudinal_plot):
            bottom_axis = plot.getAxis("bottom")
            bottom_axis.setStyle(showValues=False, tickLength=0)
            bottom_axis.setLabel("")

        elevation_axis = self.elevation_plot.getAxis("bottom")
        elevation_axis.setStyle(showValues=True, tickLength=-5)

        stacked_widget = self.speed_plot.parentWidget()
        if stacked_widget is not None:
            stacked_widget.setMinimumWidth(620)
            stacked_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            layout = stacked_widget.layout()
            if isinstance(layout, QVBoxLayout):
                layout.setContentsMargins(4, 4, 4, 6)
                layout.setSpacing(12)

        # The base window creates one splitter containing the stacked plots and
        # the geographic map. Switching it to horizontal places the map on the
        # right without rebuilding the synchronized plot and hover logic.
        plot_splitter = self.map_widget.parentWidget()
        if isinstance(plot_splitter, QSplitter):
            plot_splitter.setOrientation(Qt.Orientation.Horizontal)
            plot_splitter.setHandleWidth(9)
            plot_splitter.setChildrenCollapsible(False)
            plot_splitter.setStretchFactor(0, 5)
            plot_splitter.setStretchFactor(1, 3)

            available_width = plot_splitter.width()
            if available_width > 0:
                left_width = max(650, available_width * 5 // 8)
                right_width = max(420, available_width - left_width)
                plot_splitter.setSizes([left_width, right_width])
            else:
                plot_splitter.setSizes([850, 500])

        self.map_widget.setMinimumWidth(420)
        self.map_widget.setMinimumHeight(500)
        self.map_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    # Standalone mode still loads an existing route, but only after the window
    # has entered the event loop and can paint before the calculation starts.
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
