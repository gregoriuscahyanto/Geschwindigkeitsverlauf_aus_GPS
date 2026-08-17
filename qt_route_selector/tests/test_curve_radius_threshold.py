from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from qt_route_selector import speed_simulation
from qt_route_selector.curve_radius_policy import curve_radius_with_threshold


def circular_arc(radius_m: float) -> SimpleNamespace:
    distance = np.arange(0.0, 125.0, 5.0, dtype=float)
    theta = distance / float(radius_m)
    x = float(radius_m) * np.sin(theta)
    y = float(radius_m) * (1.0 - np.cos(theta))
    return SimpleNamespace(distance_m=distance, x_m=x, y_m=y)


def parameters(maximum_m: float) -> dict[str, float]:
    return {
        "curve_sample_distance_m": 10.0,
        "min_curve_radius_m": 8.0,
        "max_curve_radius_m": float(maximum_m),
        "curve_smooth_distance_m": 0.0,
    }


class CurveRadiusThresholdTests(unittest.TestCase):
    def test_package_installs_corrected_policy(self) -> None:
        self.assertIs(speed_simulation._curve_radius, curve_radius_with_threshold)

    def test_large_radius_is_not_clipped_down_to_maximum(self) -> None:
        radius = curve_radius_with_threshold(circular_arc(1000.0), parameters(200.0))

        # Old behavior produced many artificial 200 m samples here. The maximum
        # radius is now a relevance threshold, so a 1000 m bend is ignored.
        self.assertFalse(np.any(np.isfinite(radius)))

    def test_real_tight_curve_remains_finite(self) -> None:
        radius = curve_radius_with_threshold(circular_arc(100.0), parameters(200.0))
        finite = radius[np.isfinite(radius)]

        self.assertGreater(finite.size, 0)
        np.testing.assert_allclose(finite, 100.0, rtol=0.02, atol=0.5)

    def test_higher_threshold_keeps_large_radius_without_clipping(self) -> None:
        radius = curve_radius_with_threshold(circular_arc(1000.0), parameters(5000.0))
        finite = radius[np.isfinite(radius)]

        self.assertGreater(finite.size, 0)
        np.testing.assert_allclose(finite, 1000.0, rtol=0.02, atol=2.0)


if __name__ == "__main__":
    unittest.main()
