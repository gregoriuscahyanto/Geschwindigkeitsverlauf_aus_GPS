from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from .integrated_speed_profile_v6 import IntegratedSpeedProfileWindow as _V6Window
except ImportError:
    from integrated_speed_profile_v6 import IntegratedSpeedProfileWindow as _V6Window


class IntegratedSpeedProfileWindow(_V6Window):
    """V7: roomier, user-resizable analysis layout for laptop displays."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self.plot_stack_splitter: QSplitter | None = None
        self.right_vertical_splitter: QSplitter | None = None
        self._parameter_pane: QWidget | None = None
        super().__init__(route_path)

        self._tune_outer_splitter()
        self._install_parameter_toggle()
        self._install_resizable_plot_stack()
        self._install_resizable_right_analysis()
        self._compact_header_area()
        self._apply_roomy_sizes()

    def _tune_outer_splitter(self) -> None:
        outer = self.centralWidget()
        if not isinstance(outer, QSplitter) or outer.count() < 2:
            return
        outer.setHandleWidth(9)
        outer.setChildrenCollapsible(False)
        outer.setStretchFactor(0, 0)
        outer.setStretchFactor(1, 1)
        self._parameter_pane = outer.widget(0)
        self._parameter_pane.setMinimumWidth(330)
        self._parameter_pane.setMaximumWidth(420)
        width = max(1200, self.width())
        outer.setSizes([370, max(830, width - 370)])

        plot_root = outer.widget(1)
        plot_layout = plot_root.layout()
        if isinstance(plot_layout, QVBoxLayout):
            plot_layout.setContentsMargins(10, 8, 10, 10)
            plot_layout.setSpacing(9)

    def _install_parameter_toggle(self) -> None:
        toolbar = self.axis_combo.parentWidget()
        layout = toolbar.layout() if toolbar is not None else None
        if not isinstance(layout, QHBoxLayout):
            return
        button = QPushButton("Parameter ausblenden")
        button.setToolTip(
            "Blendet die Parameterleiste aus, damit die Analyseplots die volle Fensterbreite nutzen."
        )
        button.clicked.connect(self._toggle_parameter_pane)
        insert_at = max(0, layout.count() - 1)
        layout.insertWidget(insert_at, button)
        self.toggle_parameters_button = button

    def _toggle_parameter_pane(self) -> None:
        pane = self._parameter_pane
        if pane is None:
            return
        visible = pane.isVisible()
        pane.setVisible(not visible)
        self.toggle_parameters_button.setText(
            "Parameter anzeigen" if visible else "Parameter ausblenden"
        )
        outer = self.centralWidget()
        if isinstance(outer, QSplitter) and not visible:
            outer.setSizes([370, max(830, self.width() - 370)])

    @staticmethod
    def _plot_panel(legend: QLabel | None, plot: QWidget) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        if legend is not None:
            legend.setWordWrap(False)
            legend.setMaximumHeight(24)
            legend.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(legend)
        layout.addWidget(plot, 1)
        return panel

    def _install_resizable_plot_stack(self) -> None:
        original_parent = self.speed_plot.parentWidget()
        layout = original_parent.layout() if original_parent is not None else None
        if not isinstance(layout, QVBoxLayout):
            return

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        items = (
            ("speed", self.speed_plot, 150),
            ("acceleration", self.longitudinal_plot, 125),
            ("elevation", self.elevation_plot, 125),
            ("power", self.resistance_plot, 145),
        )
        for key, plot, minimum in items:
            legend = self._fixed_legends.get(key)
            if legend is not None:
                layout.removeWidget(legend)
            layout.removeWidget(plot)
            panel = self._plot_panel(legend, plot)
            panel.setMinimumHeight(minimum)
            splitter.addWidget(panel)

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not splitter:
                widget.setParent(None)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter, 1)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        splitter.setStretchFactor(3, 3)
        splitter.setSizes([210, 165, 165, 210])
        self.plot_stack_splitter = splitter

    def _install_resizable_right_analysis(self) -> None:
        panel = self.right_analysis_panel
        layout = panel.layout() if panel is not None else None
        if panel is None or not isinstance(layout, QVBoxLayout):
            return

        collective_legend = self._fixed_legends.get("collective")
        movable = [self.map_widget, self.power_summary_label]
        if hasattr(self, "collective_controls"):
            movable.append(self.collective_controls)
        if collective_legend is not None:
            movable.append(collective_legend)
        movable.append(self.load_collective_plot)
        for widget in movable:
            layout.removeWidget(widget)

        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(7)
        self.map_widget.setMinimumHeight(250)
        top_layout.addWidget(self.map_widget, 1)
        self.power_summary_label.setMaximumHeight(92)
        self.power_summary_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.power_summary_label.setStyleSheet(
            "QLabel { padding: 5px 7px; border: 1px solid palette(mid); "
            "border-radius: 3px; background: palette(base); font-size: 11px; }"
        )
        top_layout.addWidget(self.power_summary_label)

        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(5)
        if hasattr(self, "collective_controls"):
            bottom_layout.addWidget(self.collective_controls)
        if collective_legend is not None:
            collective_legend.setWordWrap(False)
            collective_legend.setMaximumHeight(36)
            bottom_layout.addWidget(collective_legend)
        self.load_collective_plot.setMinimumHeight(190)
        bottom_layout.addWidget(self.load_collective_plot, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(9)
        splitter.addWidget(top_panel)
        splitter.addWidget(bottom_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([410, 290])

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not splitter:
                widget.setParent(None)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(splitter, 1)
        self.right_vertical_splitter = splitter

    def _compact_header_area(self) -> None:
        self.summary_label.setMaximumHeight(54)
        self.summary_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.hover_label.setMaximumHeight(68)
        self.hover_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        if hasattr(self, "simulation_busy_bar") and isinstance(
            self.simulation_busy_bar, QProgressBar
        ):
            self.simulation_busy_bar.setMaximumHeight(16)

    def _apply_roomy_sizes(self) -> None:
        # Re-apply after inherited plot updates because older versions still set
        # larger fixed minimum heights intended for the pre-splitter layout.
        for plot in (
            self.speed_plot,
            self.longitudinal_plot,
            self.elevation_plot,
            self.resistance_plot,
        ):
            plot.setMinimumHeight(105)
        self.map_widget.setMinimumHeight(240)
        self.load_collective_plot.setMinimumHeight(180)
        if self.plot_stack_splitter is not None:
            self.plot_stack_splitter.setSizes([210, 160, 160, 205])
        if self.right_vertical_splitter is not None:
            self.right_vertical_splitter.setSizes([420, 285])

    def _apply_plot_layout(self) -> None:
        super()._apply_plot_layout()
        # During inherited construction the new splitters do not exist yet.
        # Once V7 has installed them, keep their roomier constraints on every
        # recalculation / axis change.
        if self.plot_stack_splitter is not None or self.right_vertical_splitter is not None:
            self._apply_roomy_sizes()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self.width() >= 1500 and self._parameter_pane is not None and self._parameter_pane.isVisible():
            outer = self.centralWidget()
            if isinstance(outer, QSplitter):
                sizes = outer.sizes()
                if sizes and sizes[0] > 420:
                    outer.setSizes([390, max(900, sum(sizes) - 390)])


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1720, 980)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
