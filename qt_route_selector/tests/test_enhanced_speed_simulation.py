from __future__ import annotations

import unittest

import numpy as np

from qt_route_selector.enhanced_speed_simulation import simulate_speed_profile
from qt_route_selector.speed_simulation import profile_parameters


def corner_route() -> dict:
    coordinates = []
    # Long eastbound approach.
    for index in range(31):
        coordinates.append(
            {"latitude": 48.0, "longitude": 9.0 + index * 0.0001}
        )
    # 90-degree bend followed by a long northbound exit.
    for index in range(1, 41):
        coordinates.append(
            {"latitude": 48.0 + index * 0.0001, "longitude": 9.003}
        )

    segments = []
    for index in range(len(coordinates) - 1):
        segments.append(
            {
                "from_index": index,
                "to_index": index + 1,
                "distance_m": 11.1,
                "maxspeed_kmh": 50.0,
                "surface": "asphalt",
                "highway": "primary",
            }
        )
    return {"coordinates": coordinates, "segments": segments, "traffic_signals": []}


class EnhancedSpeedSimulationTests(unittest.TestCase):
    def test_post_curve_overshoot_can_exceed_cruise_then_decay(self) -> None:
        parameters = profile_parameters("normalo")
        parameters.update(
            {
                "driver_cruise_kmh": 30.0,
                "driver_hard_max_kmh": 60.0,
                "speed_tolerance_kmh": 5.0,
                "use_driver_noise": False,
                "traffic_light_count": 0,
                "use_post_curve_overshoot": True,
                "post_curve_overshoot_kmh": 3.0,
                "post_curve_overshoot_probability_pct": 100.0,
                "post_curve_overshoot_distance_m": 100.0,
                "simulation_seed": 11,
            }
        )
        result = simulate_speed_profile(corner_route(), parameters)

        events = result["events"]["post_curve_overshoot"]
        self.assertGreaterEqual(len(events), 1)

        distance = np.asarray(result["distance"]["distance_m"], dtype=float)
        planned = np.asarray(result["distance"]["planned_speed_kmh"], dtype=float)
        exit_m = float(events[0]["curve_exit_m"])
        after = (distance >= exit_m + 15.0) & (distance <= exit_m + 160.0)
        self.assertTrue(np.any(after))
        self.assertGreater(float(np.max(planned[after])), 30.5)

        far_after = distance >= exit_m + 250.0
        if np.any(far_after):
            self.assertLessEqual(float(np.median(planned[far_after])), 30.5)

    def test_post_curve_overshoot_can_be_disabled(self) -> None:
        parameters = profile_parameters("normalo")
        parameters.update(
            {
                "driver_cruise_kmh": 30.0,
                "driver_hard_max_kmh": 60.0,
                "use_driver_noise": False,
                "traffic_light_count": 0,
                "use_post_curve_overshoot": False,
            }
        )
        result = simulate_speed_profile(corner_route(), parameters)
        self.assertEqual(result["events"]["post_curve_overshoot"], [])
        np.testing.assert_allclose(
            result["distance"]["post_curve_boost_kmh"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
