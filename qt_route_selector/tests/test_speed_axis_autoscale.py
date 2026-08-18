from __future__ import annotations

import unittest

from qt_route_selector.speed_axis_autoscale import (
    SpeedAxisAutoscaleMixin,
    speed_axis_upper_bound,
)


class _FakePlot:
    def __init__(self) -> None:
        self.auto_range_calls: list[tuple[str, bool]] = []
        self.y_range: tuple[float, float, float] | None = None

    def enableAutoRange(self, *, axis: str, enable: bool) -> None:
        self.auto_range_calls.append((axis, enable))

    def setYRange(self, minimum: float, maximum: float, *, padding: float) -> None:
        self.y_range = (float(minimum), float(maximum), float(padding))


class _FakeWindow(SpeedAxisAutoscaleMixin):
    def __init__(self, result: dict) -> None:
        self._result = result
        self.speed_plot = _FakePlot()


class SpeedAxisAutoscaleTests(unittest.TestCase):
    def test_unrestricted_simulated_peak_is_never_clipped_by_low_road_limit(self) -> None:
        result = {
            "time": {
                "speed_kmh": [0.0, 48.0, 133.6, 72.0],
                "target_kmh": [0.0, 55.0, 140.0, 75.0],
            },
            "distance": {
                "road_limit_kmh": [30.0, 30.0, 30.0],
                "surface_limit_kmh": [30.0, 30.0, 30.0],
                "planned_speed_kmh": [45.0, 140.0, 60.0],
                "actual_speed_kmh": [42.0, 133.6, 58.0],
                # Must not control the visual scale on nearly straight sections.
                "curve_limit_kmh": [10000.0, float("inf"), 5000.0],
            },
        }

        upper = speed_axis_upper_bound(result)
        self.assertGreater(upper, 140.0)
        self.assertLess(upper, 200.0)

        window = _FakeWindow(result)
        window._focus_speed_axis()
        self.assertEqual(window.speed_plot.auto_range_calls, [("y", False)])
        self.assertIsNotNone(window.speed_plot.y_range)
        minimum, maximum, padding = window.speed_plot.y_range
        self.assertEqual(minimum, 0.0)
        self.assertGreater(maximum, 140.0)
        self.assertLess(maximum, 200.0)
        self.assertEqual(padding, 0.02)

    def test_normal_road_limit_still_gets_headroom(self) -> None:
        result = {
            "time": {"speed_kmh": [0.0, 100.0]},
            "distance": {"road_limit_kmh": [130.0]},
        }
        self.assertGreater(speed_axis_upper_bound(result), 130.0)

    def test_nonfinite_values_do_not_break_scaling(self) -> None:
        result = {
            "time": {"speed_kmh": [0.0, float("nan"), 80.0]},
            "distance": {"road_limit_kmh": [float("inf")]},
        }
        upper = speed_axis_upper_bound(result)
        self.assertGreater(upper, 80.0)
        self.assertLess(upper, 120.0)


if __name__ == "__main__":
    unittest.main()
