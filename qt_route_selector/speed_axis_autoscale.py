from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
from PySide6.QtCore import QTimer


_SPEED_AXIS_SERIES: tuple[tuple[str, str], ...] = (
    ("time", "speed_kmh"),
    ("time", "target_kmh"),
    ("distance", "actual_speed_kmh"),
    ("distance", "planned_speed_kmh"),
    ("distance", "road_limit_kmh"),
    ("distance", "surface_limit_kmh"),
)


def speed_axis_upper_bound(
    result: Mapping[str, Any] | None,
    *,
    minimum_kmh: float = 40.0,
) -> float:
    """Return a readable y-axis ceiling that never clips relevant speed signals.

    Curve-limit values are intentionally excluded. On almost straight road
    sections they may be mathematically very large (or infinite) and would make
    the actually driven speed unreadably small. The simulated/target/planned
    speeds plus the summary maximum are sufficient to keep every physically
    relevant peak visible.
    """

    if not result:
        return float(minimum_kmh)

    maxima: list[float] = []
    for section_name, key in _SPEED_AXIS_SERIES:
        section = result.get(section_name, {})
        if not isinstance(section, Mapping):
            continue
        try:
            values = np.asarray(section.get(key, []), dtype=float).reshape(-1)
        except (TypeError, ValueError):
            continue
        finite = values[np.isfinite(values)]
        if finite.size:
            maxima.append(float(np.max(finite)))

    # The header shown to the user already reports this value. Include it as an
    # independent safety source so the plot can never display e.g. "Maximum:
    # 133.6 km/h" while keeping its visible y-axis around 55 km/h.
    summary = result.get("summary", {})
    if isinstance(summary, Mapping):
        try:
            summary_max = float(summary.get("maximum_speed_kmh", float("nan")))
        except (TypeError, ValueError):
            summary_max = float("nan")
        if math.isfinite(summary_max):
            maxima.append(summary_max)

    if not maxima:
        return float(minimum_kmh)

    maximum = max(0.0, max(maxima))
    margin = max(10.0, maximum * 0.08)
    # A rounded upper bound makes the reset view easier to read. 133.6 km/h,
    # for example, becomes a 150 km/h view rather than an awkward 144.3 km/h.
    rounded = math.ceil((maximum + margin) / 10.0) * 10.0
    return max(float(minimum_kmh), rounded)


class SpeedAxisAutoscaleMixin:
    """Keep the visible speed axis large enough for unrestricted simulation peaks."""

    def _apply_speed_axis_range(self) -> None:
        result = getattr(self, "_result", None)
        speed_plot = getattr(self, "speed_plot", None)
        if result is None or speed_plot is None:
            return

        y_max = speed_axis_upper_bound(result)

        # Apply the range through both PlotWidget and its final ViewBox. Some of
        # the historical UI layers toggle AutoRange while rebuilding plots. The
        # explicit ViewBox call makes this the final y-range of the visible axis.
        try:
            speed_plot.enableAutoRange(axis="y", enable=False)
        except Exception:
            pass
        try:
            speed_plot.setYRange(0.0, y_max, padding=0.02)
        except Exception:
            pass
        try:
            plot_item = speed_plot.getPlotItem()
            view_box = plot_item.getViewBox()
            view_box.enableAutoRange(axis="y", enable=False)
            view_box.setYRange(0.0, y_max, padding=0.02)
        except Exception:
            pass

    def _focus_speed_axis(self) -> None:
        self._apply_speed_axis_range()

    def reset_plot_views(self) -> None:
        """Reset all plots, then enforce the speed range after every legacy reset."""
        super().reset_plot_views()
        self._apply_speed_axis_range()
        # Several older plot layers finish layout/AutoRange work asynchronously.
        # Re-apply once the current and next event-loop turns have completed so
        # they cannot silently restore the old road-limit-based ~55 km/h range.
        QTimer.singleShot(0, self._apply_speed_axis_range)
        QTimer.singleShot(50, self._apply_speed_axis_range)

    def _update_plots(self) -> None:
        """Ensure recalculation and signal changes use the same complete speed view."""
        super()._update_plots()
        self._apply_speed_axis_range()
        QTimer.singleShot(0, self._apply_speed_axis_range)


__all__ = ["SpeedAxisAutoscaleMixin", "speed_axis_upper_bound"]
