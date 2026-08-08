from __future__ import annotations

import sys
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from .integrated_speed_profile_v8 import IntegratedSpeedProfileWindow as _V8Window
except ImportError:
    from integrated_speed_profile_v8 import IntegratedSpeedProfileWindow as _V8Window


class IntegratedSpeedProfileWindow(_V8Window):
    """V9: robust multi-axis plot plus consistent, unclipped controls."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._fit_parameter_sidebar()
        self._style_analysis_toolbar()
        self._refresh_combined_axes()

    # ------------------------------------------------------------------
    # Parameter sidebar: use the complete available width instead of keeping
    # the old content size calculated before the flattened settings existed.
    # ------------------------------------------------------------------
    def _fit_parameter_sidebar(self) -> None:
        outer = self.centralWidget()
        pane = self._parameter_pane
        if not isinstance(outer, QSplitter) or pane is None:
            return

        pane.setMinimumWidth(450)
        pane.setMaximumWidth(570)
        pane.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        desired = min(520, max(470, int(self.width() * 0.29)))
        outer.setSizes([desired, max(900, self.width() - desired)])

        scroll = pane if isinstance(pane, QScrollArea) else None
        if scroll is None:
            candidates = pane.findChildren(QScrollArea)
            scroll = candidates[0] if candidates else None
        if scroll is None:
            return

        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = scroll.widget()
        if content is None:
            return
        content.setMinimumWidth(0)
        content.setMaximumWidth(16_777_215)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        for form in content.findChildren(QFormLayout):
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        for grid in content.findChildren(QGridLayout):
            if grid.columnCount() >= 2:
                grid.setColumnStretch(grid.columnCount() - 1, 1)

        for widget in content.findChildren((QComboBox, QAbstractSpinBox, QLineEdit)):
            widget.setMinimumWidth(0)
            widget.setMaximumWidth(16_777_215)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, widget.sizePolicy().verticalPolicy())

        # Technical preview plots must shrink/grow with the sidebar instead of
        # preserving an old fixed width and being visually cut at the right edge.
        for plot in content.findChildren(pg.PlotWidget):
            plot.setMinimumWidth(0)
            plot.setMaximumWidth(16_777_215)
            plot.setSizePolicy(QSizePolicy.Policy.Expanding, plot.sizePolicy().verticalPolicy())

        content.updateGeometry()
        scroll.updateGeometry()

    # ------------------------------------------------------------------
    # One visual language for every control in the analysis toolbar.
    # ------------------------------------------------------------------
    def _style_analysis_toolbar(self) -> None:
        toolbar = self.axis_combo.parentWidget()
        if toolbar is None:
            return
        toolbar.setStyleSheet(
            "QComboBox, QPushButton, QToolButton {"
            "  min-height: 26px; padding: 3px 9px;"
            "  border: 1px solid palette(mid); border-radius: 7px;"
            "  background: palette(base); color: palette(text);"
            "}"
            "QComboBox:hover, QPushButton:hover, QToolButton:hover {"
            "  border-color: palette(highlight); background: palette(alternate-base);"
            "}"
            "QComboBox:focus, QPushButton:focus, QToolButton:focus {"
            "  border-color: palette(highlight);"
            "}"
            "QToolButton:checked {"
            "  border-color: palette(highlight); background: palette(base); font-weight: 600;"
            "}"
            "QComboBox::drop-down { border: 0px; width: 20px; }"
        )
        if hasattr(self, "sidebar_toggle_button"):
            self.sidebar_toggle_button.setAutoRaise(False)
            self.sidebar_toggle_button.setText("☰  Parameter")
        if hasattr(self, "signals_button"):
            self.signals_button.setAutoRaise(False)
        if hasattr(self, "reset_views_button") and isinstance(self.reset_views_button, QPushButton):
            self.reset_views_button.setFlat(False)

    # ------------------------------------------------------------------
    # pyqtgraph compatibility. InfiniteLine does not accept y= in the version
    # used on the Windows machine; pos + horizontal angle works across versions.
    # ------------------------------------------------------------------
    def _add_zero_line(self, group: str) -> None:
        view = self._combined_views.get(group)
        if view is None:
            return
        line = pg.InfiniteLine(
            pos=0.0,
            angle=0,
            movable=False,
            pen=pg.mkPen((130, 130, 130, 130), width=1),
        )
        view.addItem(line, ignoreBounds=True)
        self._combined_aux_items.append((line, group))

    def _set_combined_axis_visibility(self, groups: set[str]) -> None:
        # Explicitly update every axis after a signal/metric change. This is
        # important when a previous redraw aborted: no stale axis visibility is
        # allowed to survive into the next successful render.
        widths = {
            "speed": 64,
            "acceleration": 72,
            "elevation": 66,
            "power": 70,
        }
        for group, axis in self._combined_axes.items():
            visible = group in groups
            axis.setVisible(visible)
            if visible:
                axis.setWidth(widths.get(group, 66))
                label, unit, color = self._axis_definition(group)
                axis.setLabel(label, units=unit)
                try:
                    axis.setPen(pg.mkPen(color))
                    axis.setTextPen(pg.mkPen(color))
                    axis.setStyle(showValues=True)
                except (AttributeError, TypeError):
                    pass
        self._sync_combined_views()

    @staticmethod
    def _axis_definition(group: str) -> tuple[str, str, tuple[int, int, int]]:
        definitions = {
            "speed": ("Geschwindigkeit", "km/h", (205, 205, 205)),
            "acceleration": ("Beschleunigung", "m/s²", (60, 190, 140)),
            "elevation": ("Höhe", "m", (220, 150, 70)),
            "power": ("Radleistung", "kW", (95, 160, 245)),
        }
        return definitions.get(group, (group, "", (205, 205, 205)))

    def _refresh_combined_axes(self) -> None:
        if not hasattr(self, "signal_actions"):
            return
        if self._comparison_configs and self._comparison_results:
            metric = str(self.comparison_metric_combo.currentData())
            group = "power" if metric == "power" else "acceleration" if metric == "acceleration" else "speed"
            self._set_combined_axis_visibility({group})
            return
        groups: set[str] = set()
        for key, action in self.signal_actions.items():
            if not action.isChecked():
                continue
            definition = self._signal_definition(key)
            if definition is not None:
                groups.add(definition[1])
        self._set_combined_axis_visibility(groups)

    @staticmethod
    def _signal_definition(key: str):
        # Keep this small mirror local to V9 to avoid importing private globals
        # from V8 through two different package import paths.
        groups = {
            "simulated": "speed",
            "road_limit": "speed",
            "curve_limit": "speed",
            "target": "speed",
            "acceleration": "acceleration",
            "elevation": "elevation",
            "power_total": "power",
            "power_acceleration": "power",
            "power_grade": "power",
            "power_rolling": "power",
            "power_air": "power",
            "power_trailer": "power",
        }
        group = groups.get(key)
        return (key, group) if group is not None else None

    def _update_combined_plot(self) -> None:
        super()._update_combined_plot()
        # The parent now finishes without the InfiniteLine exception. Reassert
        # axis visibility to make recovery from the old failed state immediate.
        if hasattr(self, "combined_plot"):
            self._refresh_combined_axes()

    def _set_parameter_pane_visible(self, visible: bool) -> None:
        pane = self._parameter_pane
        if pane is None:
            return
        pane.setVisible(bool(visible))
        if hasattr(self, "sidebar_toggle_button"):
            self.sidebar_toggle_button.setText("☰  Parameter")
            self.sidebar_toggle_button.setToolTip(
                "Parameter ausblenden" if visible else "Parameter einblenden"
            )
        outer = self.centralWidget()
        if isinstance(outer, QSplitter):
            if visible:
                desired = min(520, max(470, int(self.width() * 0.29)))
                outer.setSizes([desired, max(900, self.width() - desired)])
            else:
                outer.setSizes([0, max(1000, self.width())])

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self._parameter_pane is not None and self._parameter_pane.isVisible():
            outer = self.centralWidget()
            if isinstance(outer, QSplitter):
                sizes = outer.sizes()
                if sizes and sizes[0] < 450:
                    desired = min(520, max(470, int(self.width() * 0.29)))
                    outer.setSizes([desired, max(900, sum(sizes) - desired)])


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1720, 980)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
