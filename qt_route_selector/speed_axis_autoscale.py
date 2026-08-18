from __future__ import annotations

from typing import Any, Mapping

import numpy as np


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
    speeds are sufficient to make every physically relevant peak visible.
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

    if not maxima:
        return float(minimum_kmh)

    maximum = max(0.0, max(maxima))
    # Keep enough visual headroom for thin peaks and pyqtgraph's axis labels.
    margin = max(10.0, maximum * 0.08)
    return max(float(minimum_kmh), maximum + margin)


class SpeedAxisAutoscaleMixin:
    """Make plot reset/recalculation include the actual unrestricted speed."""

    def _focus_speed_axis(self) -> None:
        result = getattr(self, "_result", None)
        speed_plot = getattr(self, "speed_plot", None)
        if result is None or speed_plot is None:
            return

        y_max = speed_axis_upper_bound(result)
        speed_plot.enableAutoRange(axis="y", enable=False)
        speed_plot.setYRange(0.0, y_max, padding=0.02)


__all__ = ["SpeedAxisAutoscaleMixin", "speed_axis_upper_bound"]
