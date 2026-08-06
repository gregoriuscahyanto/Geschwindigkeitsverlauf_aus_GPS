from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QSplitter, QSizePolicy, QVBoxLayout

try:
    from .integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow
except ImportError:
    from integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow


class IntegratedSpeedProfileWindow(_BaseWindow):
    """UI refinement with three stacked plots and the map on the right."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._apply_plot_layout()
        QTimer.singleShot(0, self._apply_plot_layout)

    def _update_plots(self) -> None:
        super()._update_plots()
        self._apply_plot_layout()

    def _apply_plot_layout(self) -> None:
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
