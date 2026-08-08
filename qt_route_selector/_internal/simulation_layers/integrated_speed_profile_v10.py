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
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
)

try:
    from .integrated_speed_profile_v9 import IntegratedSpeedProfileWindow as _V9Window
except ImportError:
    from integrated_speed_profile_v9 import IntegratedSpeedProfileWindow as _V9Window


_SIMPLE_SIGNALS = {"simulated", "road_limit", "elevation"}
_ADVANCED_PARAMETER_GROUPS = {"Ampeln", "Überholen", "Rauschen"}


class IntegratedSpeedProfileWindow(_V9Window):
    """V10: responsive simulation UI for small laptops through large monitors."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._responsive_ready = False
        self._responsive_band = ""
        super().__init__(route_path)

        self._responsive_resize_timer = QTimer(self)
        self._responsive_resize_timer.setSingleShot(True)
        self._responsive_resize_timer.setInterval(45)
        self._responsive_resize_timer.timeout.connect(self._apply_responsive_layout)

        self._configure_simple_default_signals()
        self._make_parameter_content_responsive()
        self._simplify_parameter_copy()
        self._install_advanced_parameter_disclosure()
        self._style_parameter_cards()
        self._responsive_ready = True
        self._apply_responsive_layout(force=True)

    def _configure_simple_default_signals(self) -> None:
        if not hasattr(self, "signal_actions"):
            return
        for key, action in self.signal_actions.items():
            old = action.blockSignals(True)
            action.setChecked(key in _SIMPLE_SIGNALS)
            action.blockSignals(old)
        self._update_signal_button_text()
        if self._v8_ready:
            self._update_combined_plot()

    def _make_parameter_content_responsive(self) -> None:
        pane = self._parameter_pane
        if pane is None:
            return

        pane.setMinimumWidth(0)
        pane.setMaximumWidth(16_777_215)
        pane.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        scroll = pane if isinstance(pane, QScrollArea) else None
        if scroll is None:
            candidates = pane.findChildren(QScrollArea)
            scroll = candidates[0] if candidates else None
        if scroll is None:
            return

        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.parameter_scroll_area = scroll

        content = scroll.widget()
        if content is None:
            return
        content.setMinimumWidth(0)
        content.setMaximumWidth(16_777_215)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        for form in content.findChildren(QFormLayout):
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(7)

        for widget_type in (QComboBox, QAbstractSpinBox, QLineEdit):
            for widget in content.findChildren(widget_type):
                widget.setMinimumWidth(0)
                widget.setMaximumWidth(16_777_215)
                widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    widget.sizePolicy().verticalPolicy(),
                )

        for label in content.findChildren(QLabel):
            label.setMinimumWidth(0)
            if len(label.text().strip()) > 34:
                label.setWordWrap(True)
                label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        for button_type in (QPushButton, QToolButton):
            for button in content.findChildren(button_type):
                button.setMinimumWidth(0)
                button.setSizePolicy(
                    QSizePolicy.Policy.Preferred,
                    button.sizePolicy().verticalPolicy(),
                )

        for plot in content.findChildren(pg.PlotWidget):
            plot.setMinimumWidth(0)
            plot.setMaximumWidth(16_777_215)
            plot.setSizePolicy(QSizePolicy.Policy.Expanding, plot.sizePolicy().verticalPolicy())

        content.updateGeometry()
        scroll.updateGeometry()

    def _simplify_parameter_copy(self) -> None:
        if hasattr(self, "comparison_group") and self.comparison_group is not None:
            self.comparison_group.setTitle("Vergleich")
            for label in self.comparison_group.findChildren(QLabel):
                text = label.text()
                if text.startswith("Aktuelle Einstellung speichern"):
                    label.setText(
                        "Variante speichern, Parameter ändern und Ergebnisse direkt vergleichen."
                    )
                    label.setWordWrap(True)

        for button in self.findChildren(QPushButton):
            text = button.text().strip()
            if text == "Aktuelle speichern":
                button.setText("Speichern")
                button.setToolTip("Aktuelle Parameter als Vergleichsvariante speichern")
            elif text == "CSV + JSON exportieren":
                button.setText("Exportieren …")
                button.setToolTip("Simulation als CSV und JSON exportieren")

    def _install_advanced_parameter_disclosure(self) -> None:
        groups = {
            group.title(): group
            for group in self.findChildren(QGroupBox)
            if group.title() in _ADVANCED_PARAMETER_GROUPS
        }
        if not groups:
            return

        anchor = next(
            (
                group
                for group in self.findChildren(QGroupBox)
                if group.title() in {"Kurven", "Fahrer", "Vergleich"}
            ),
            None,
        )
        parent = anchor.parentWidget() if anchor is not None else None
        layout = parent.layout() if parent is not None else None
        if not isinstance(layout, QVBoxLayout):
            return

        button = QToolButton()
        button.setText("Weitere Parameter")
        button.setCheckable(True)
        button.setChecked(False)
        button.setArrowType(Qt.ArrowType.RightArrow)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip("Ampeln, Überholen und Fahrerrauschen ein- oder ausblenden")
        button.setStyleSheet(
            "QToolButton {"
            "  text-align: left; padding: 6px 8px; border: 1px solid palette(midlight);"
            "  border-radius: 8px; background: palette(base); font-weight: 600;"
            "}"
            "QToolButton:hover { border-color: palette(highlight); background: palette(alternate-base); }"
        )
        button.toggled.connect(self._set_advanced_parameters_visible)

        first_indexes = [layout.indexOf(group) for group in groups.values() if layout.indexOf(group) >= 0]
        insert_at = min(first_indexes) if first_indexes else layout.count()
        layout.insertWidget(insert_at, button)
        self.advanced_parameters_button = button
        self._advanced_parameter_groups = list(groups.values())
        self._set_advanced_parameters_visible(False)

    def _set_advanced_parameters_visible(self, visible: bool) -> None:
        for group in getattr(self, "_advanced_parameter_groups", []):
            group.setVisible(bool(visible))
        button = getattr(self, "advanced_parameters_button", None)
        if isinstance(button, QToolButton):
            old = button.blockSignals(True)
            button.setChecked(bool(visible))
            button.setArrowType(
                Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
            )
            button.blockSignals(old)
        if hasattr(self, "parameter_scroll_area"):
            self.parameter_scroll_area.widget().updateGeometry()

    def _style_parameter_cards(self) -> None:
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(
                "QGroupBox {"
                "  border: 1px solid palette(midlight); border-radius: 8px;"
                "  margin-top: 11px; padding: 8px; background: palette(base);"
                "}"
                "QGroupBox::title {"
                "  subcontrol-origin: margin; left: 10px; padding: 0 5px;"
                "  font-weight: 600; background: palette(base);"
                "}"
            )

        for label_name in ("summary_label", "energy_header_label", "hover_label"):
            label = getattr(self, label_name, None)
            if isinstance(label, QLabel):
                label.setStyleSheet(
                    "QLabel { padding: 6px 9px; border: 1px solid palette(midlight); "
                    "border-radius: 8px; background: palette(base); }"
                )

    @staticmethod
    def _band_for_width(width: int) -> str:
        if width < 1280:
            return "compact"
        if width < 1680:
            return "medium"
        return "wide"

    @staticmethod
    def _sidebar_ratio(band: str) -> float:
        return {"compact": 0.36, "medium": 0.31, "wide": 0.28}[band]

    @staticmethod
    def _set_ratio(splitter: QSplitter, first_ratio: float) -> None:
        total = (
            max(1, splitter.width())
            if splitter.orientation() == Qt.Orientation.Horizontal
            else max(1, splitter.height())
        )
        first = max(1, int(round(total * first_ratio)))
        splitter.setSizes([first, max(1, total - first)])

    def _active_axis_groups(self) -> set[str]:
        if self._comparison_configs and self._comparison_results:
            metric = str(self.comparison_metric_combo.currentData())
            if metric == "power":
                return {"power"}
            if metric == "acceleration":
                return {"acceleration"}
            return {"speed"}

        groups: set[str] = set()
        for key, action in self.signal_actions.items():
            if not action.isChecked():
                continue
            definition = self._signal_definition(key)
            if definition is not None:
                groups.add(definition[1])
        return groups

    def _apply_responsive_layout(self, force: bool = False) -> None:
        if not self._responsive_ready:
            return
        outer = self.centralWidget()
        pane = self._parameter_pane
        if not isinstance(outer, QSplitter) or pane is None:
            return

        pane.setMinimumWidth(0)
        pane.setMaximumWidth(16_777_215)
        available_width = max(1, outer.width() or self.width())
        band = self._band_for_width(available_width)
        changed_band = band != self._responsive_band
        self._responsive_band = band

        outer.setStretchFactor(0, 3)
        outer.setStretchFactor(1, 7)
        if pane.isVisible():
            ratio = self._sidebar_ratio(band)
            sidebar = max(1, int(round(available_width * ratio)))
            outer.setSizes([sidebar, max(1, available_width - sidebar)])
        else:
            outer.setSizes([0, available_width])

        sizes = outer.sizes()
        analysis_width = sizes[1] if len(sizes) > 1 else available_width
        map_splitter = getattr(self, "plot_map_splitter", None)
        if isinstance(map_splitter, QSplitter):
            stack_right = band == "compact" or analysis_width < 1050
            target_orientation = (
                Qt.Orientation.Vertical if stack_right else Qt.Orientation.Horizontal
            )
            if force or changed_band or map_splitter.orientation() != target_orientation:
                map_splitter.setOrientation(target_orientation)

            if stack_right:
                self.combined_plot.setMinimumHeight(220)
                self.map_widget.setMinimumHeight(150)
                self.load_collective_plot.setMinimumHeight(135)
                self._set_ratio(map_splitter, 0.58)
            else:
                self.combined_plot.setMinimumHeight(360)
                self.map_widget.setMinimumHeight(220)
                self.load_collective_plot.setMinimumHeight(170)
                self._set_ratio(map_splitter, 0.67 if band == "wide" else 0.63)

        right_splitter = getattr(self, "right_vertical_splitter", None)
        if isinstance(right_splitter, QSplitter):
            self._set_ratio(right_splitter, 0.56)

        self._set_combined_axis_visibility(self._active_axis_groups())

    def _set_combined_axis_visibility(self, groups: set[str]) -> None:
        plot = getattr(self, "combined_plot", None)
        plot_width = max(1, plot.width() if plot is not None else self.width())
        active_count = max(1, len(groups))
        fraction = 0.052 if active_count <= 2 else 0.044
        axis_width = max(44, min(70, int(round(plot_width * fraction))))

        for group, axis in self._combined_axes.items():
            visible = group in groups
            axis.setVisible(visible)
            if not visible:
                continue
            axis.setWidth(axis_width)
            label, unit, color = self._axis_definition(group)
            axis.setLabel(label, units=unit)
            try:
                axis.setPen(pg.mkPen(color))
                axis.setTextPen(pg.mkPen(color))
                axis.setStyle(showValues=True)
            except (AttributeError, TypeError):
                pass
        self._sync_combined_views()

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
        if self._responsive_ready:
            self._apply_responsive_layout(force=True)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if hasattr(self, "_responsive_resize_timer"):
            self._responsive_resize_timer.start()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
