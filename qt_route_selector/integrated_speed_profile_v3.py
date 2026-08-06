from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSplitter, QSizePolicy, QVBoxLayout

try:
    from .integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow
except ImportError:
    from integrated_speed_profile_v2 import IntegratedSpeedProfileWindow as _BaseWindow


class IntegratedSpeedProfileWindow(_BaseWindow):
    """UI refinement with clearer spacing between the synchronized plots."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._apply_plot_spacing()
        QTimer.singleShot(0, self._apply_plot_spacing)

    def _update_plots(self) -> None:
        super()._update_plots()
        self._apply_plot_spacing()

    def _apply_plot_spacing(self) -> None:
        plots = (
            (self.speed_plot, 185),
            (self.longitudinal_plot, 145),
            (self.elevation_plot, 145),
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

        # The three plots share one x-axis. Show labels only on the bottom plot
        # so the panels have more breathing room while remaining aligned.
        for plot in (self.speed_plot, self.longitudinal_plot):
            bottom_axis = plot.getAxis("bottom")
            bottom_axis.setStyle(showValues=False, tickLength=0)
            bottom_axis.setLabel("")

        elevation_axis = self.elevation_plot.getAxis("bottom")
        elevation_axis.setStyle(showValues=True, tickLength=-5)

        stacked_widget = self.speed_plot.parentWidget()
        if stacked_widget is not None:
            layout = stacked_widget.layout()
            if isinstance(layout, QVBoxLayout):
                layout.setContentsMargins(4, 4, 4, 6)
                layout.setSpacing(12)

        plot_splitter = self.map_widget.parentWidget()
        if isinstance(plot_splitter, QSplitter):
            plot_splitter.setHandleWidth(9)
            plot_splitter.setChildrenCollapsible(False)
            plot_splitter.setStretchFactor(0, 5)
            plot_splitter.setStretchFactor(1, 3)
            if plot_splitter.height() > 0:
                plot_splitter.setSizes([max(520, plot_splitter.height() * 5 // 8), 320])

        self.map_widget.setMinimumHeight(285)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
