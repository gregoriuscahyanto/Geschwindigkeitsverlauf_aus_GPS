from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

try:
    from .integrated_speed_profile_v4 import (
        IntegratedSpeedProfileWindow as _V4Window,
        _SCENARIO_COLORS,
    )
    from .load_collective_curve import cumulative_load_curve
except ImportError:
    from integrated_speed_profile_v4 import (
        IntegratedSpeedProfileWindow as _V4Window,
        _SCENARIO_COLORS,
    )
    from load_collective_curve import cumulative_load_curve


class IntegratedSpeedProfileWindow(_V4Window):
    """V5: signed load-duration collective with both peaks anchored at x=0."""

    @staticmethod
    def _display_x_for_log(x: np.ndarray, logarithmic: bool) -> np.ndarray:
        values = np.asarray(x, dtype=float).copy()
        if not logarithmic or values.size == 0:
            return values
        # A logarithmic axis cannot represent x=0 mathematically. Keep the data
        # model anchored at 0 %, but render that first point at a tiny positive
        # location so the peak remains visible at the extreme left edge.
        positive = values[values > 0.0]
        epsilon = max(1e-6, float(np.min(positive)) * 0.1) if positive.size else 1e-6
        values[values <= 0.0] = epsilon
        return values

    def _plot_cumulative_collective(self) -> None:
        if not hasattr(self, "collective_normalized_check"):
            return

        self.load_collective_plot.clear()
        normalized = self.collective_normalized_check.isChecked()
        positive_only = self.collective_positive_check.isChecked()
        logarithmic = self.collective_log_check.isChecked()

        self.load_collective_plot.setTitle(
            "Kumuliertes Lastkollektiv – Peaks bei 0 % Zeitanteil"
        )
        self.load_collective_plot.setLabel(
            "bottom", "Kumulierter Zeitanteil", units="%"
        )
        self.load_collective_plot.setLabel(
            "left",
            "Normierte Last" if normalized else "Radleistung",
            units="" if normalized else "kW",
        )
        self.load_collective_plot.setLogMode(x=logarithmic, y=False)

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
            color = _SCENARIO_COLORS[index % len(_SCENARIO_COLORS)]
            pen = pg.mkPen(color, width=2.2)

            positive_x = np.asarray(
                curve["positive_time_share_pct"], dtype=float
            )
            positive_y = np.asarray(curve["positive_load"], dtype=float)
            if positive_x.size:
                self.load_collective_plot.plot(
                    self._display_x_for_log(positive_x, logarithmic),
                    positive_y,
                    pen=pen,
                )

            if not positive_only:
                negative_x = np.asarray(
                    curve["negative_time_share_pct"], dtype=float
                )
                negative_y = np.asarray(curve["negative_load"], dtype=float)
                if negative_x.size:
                    self.load_collective_plot.plot(
                        self._display_x_for_log(negative_x, logarithmic),
                        negative_y,
                        pen=pen,
                    )

        self.load_collective_plot.addLine(
            y=0.0,
            pen=pg.mkPen((110, 110, 110), width=1),
        )
        self.load_collective_plot.showGrid(x=True, y=True, alpha=0.25)
        self.load_collective_plot.enableAutoRange()

        if "collective" in self._fixed_legends:
            if self._comparison_configs:
                self._fixed_legends["collective"].setText(
                    self._legend_html(self._comparison_entries())
                    + "<br>Positiv: vom größten Wert Richtung 0 · "
                    "Negativ: vom kleinsten Wert Richtung 0"
                )
            else:
                self._fixed_legends["collective"].setText(
                    "Kumulierte Lastdauerlinie: positiver und negativer Peak jeweils bei 0 %"
                )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
