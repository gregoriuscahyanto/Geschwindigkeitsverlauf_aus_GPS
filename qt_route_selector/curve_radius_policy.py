from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np


def curve_radius_with_threshold(route: Any, parameters: Mapping[str, Any]) -> np.ndarray:
    """Calculate curve radii with ``max_curve_radius_m`` as a relevance threshold.

    ``max_curve_radius_m`` means: only bends whose calculated radius is at most
    this value are relevant for the curve-speed model. Larger radii describe
    sufficiently straight road geometry and therefore remain ``inf`` instead of
    being clipped down to the configured threshold.
    """

    distance = np.asarray(route.distance_m, dtype=float)
    radius = np.full(distance.shape, np.inf, dtype=float)
    sample_offset = max(2.0, float(parameters["curve_sample_distance_m"]))
    minimum = max(1.0, float(parameters["min_curve_radius_m"]))
    maximum = max(minimum, float(parameters["max_curve_radius_m"]))

    for index, position in enumerate(distance):
        left = int(np.searchsorted(distance, position - sample_offset, side="left"))
        right = int(np.searchsorted(distance, position + sample_offset, side="right") - 1)
        if left >= index or right <= index or right >= len(distance):
            continue

        ax = float(route.x_m[left] - route.x_m[index])
        ay = float(route.y_m[left] - route.y_m[index])
        bx = float(route.x_m[right] - route.x_m[index])
        by = float(route.y_m[right] - route.y_m[index])
        a = math.hypot(ax, ay)
        b = math.hypot(bx, by)
        c = math.hypot(
            float(route.x_m[right] - route.x_m[left]),
            float(route.y_m[right] - route.y_m[left]),
        )
        twice_area = abs(ax * by - bx * ay)
        if min(a, b, c) < 0.5 or twice_area < 1e-6:
            continue

        value = a * b * c / (2.0 * twice_area)
        if not math.isfinite(value) or value > maximum:
            # Larger radii are intentionally treated as straight/irrelevant.
            continue
        radius[index] = max(value, minimum)

    smooth = max(0.0, float(parameters["curve_smooth_distance_m"]))
    if smooth > 0.0:
        smoothed = np.full(radius.shape, np.inf, dtype=float)
        for index, position in enumerate(distance):
            left = int(np.searchsorted(distance, position - smooth, side="left"))
            right = int(np.searchsorted(distance, position + smooth, side="right"))
            if right > left:
                smoothed[index] = float(np.min(radius[left:right]))
            else:
                smoothed[index] = radius[index]
        radius = smoothed

    return radius


def install_curve_radius_threshold(speed_simulation_module: Any) -> None:
    """Install the corrected radius policy into the shared simulation module."""

    speed_simulation_module._curve_radius = curve_radius_with_threshold


__all__ = ["curve_radius_with_threshold", "install_curve_radius_threshold"]
