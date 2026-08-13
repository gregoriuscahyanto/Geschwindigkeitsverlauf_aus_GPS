from __future__ import annotations

import unittest

import numpy as np

from qt_route_selector.speed_limit_policy import (
    POLICY_GERMANY_POINTS,
    POLICY_IGNORE,
    POLICY_OBEY,
    conservative_germany_points,
    germany_max_overspeed_kmh,
    simulate_speed_profile,
)


class SpeedLimitPolicyTests(unittest.TestCase):
    @staticmethod
    def _route() -> dict:
        return {
            "coordinates": [
                {"latitude": 48.0000, "longitude": 9.0000},
                {"latitude": 48.0135, "longitude": 9.0000},
                {"latitude": 48.0270, "longitude": 9.0000},
            ],
            "segments": [
                {
                    "from_index": 0,
                    "to_index": 1,
                    "distance_m": 1500.0,
                    "maxspeed_kmh": 50.0,
                    "surface": "asphalt",
                    "highway": "primary",
                },
                {
                    "from_index": 1,
                    "to_index": 2,
                    "distance_m": 1500.0,
                    "maxspeed_kmh": 50.0,
                    "surface": "asphalt",
                    "highway": "primary",
                },
            ],
            "traffic_signals": [],
        }

    @staticmethod
    def _parameters(policy: str, max_points: int = 0) -> dict:
        return {
            "driver_profile": "rennfahrer",
            "speed_limit_policy": policy,
            "max_speeding_points": max_points,
            "sample_distance_m": 10.0,
            "dt_s": 0.2,
            "driver_cruise_kmh": 180.0,
            "driver_hard_max_kmh": 180.0,
            "speed_bias_kmh": 0.0,
            "speed_tolerance_kmh": 0.0,
            "apply_curve_speed": False,
            "use_surface_limit": False,
            "use_traffic_lights": False,
            "traffic_light_count": 0,
            "use_overtaking": False,
            "use_driver_noise": False,
            "start_stop": False,
            "end_stop": False,
            "a_max_mps2": 4.0,
            "b_max_mps2": 4.0,
            "j_max_mps3": 3.0,
        }

    def test_germany_point_thresholds_are_conservative(self) -> None:
        self.assertEqual(germany_max_overspeed_kmh(0), 20.0)
        self.assertEqual(germany_max_overspeed_kmh(1), 30.0)
        self.assertTrue(np.isinf(germany_max_overspeed_kmh(2)))
        np.testing.assert_allclose(
            conservative_germany_points(np.asarray([0.0, 20.0, 20.1, 30.0, 30.1, 80.0])),
            [0.0, 0.0, 1.0, 1.0, 2.0, 2.0],
        )

    def test_obey_points_and_ignore_change_effective_limit(self) -> None:
        obey = simulate_speed_profile(self._route(), self._parameters(POLICY_OBEY))
        zero = simulate_speed_profile(
            self._route(), self._parameters(POLICY_GERMANY_POINTS, 0)
        )
        one = simulate_speed_profile(
            self._route(), self._parameters(POLICY_GERMANY_POINTS, 1)
        )
        ignore = simulate_speed_profile(self._route(), self._parameters(POLICY_IGNORE))

        for result in (obey, zero, one, ignore):
            np.testing.assert_allclose(result["distance"]["road_limit_kmh"], 50.0)

        np.testing.assert_allclose(obey["distance"]["speed_policy_limit_kmh"], 50.0)
        np.testing.assert_allclose(zero["distance"]["speed_policy_limit_kmh"], 70.0)
        np.testing.assert_allclose(one["distance"]["speed_policy_limit_kmh"], 80.0)
        np.testing.assert_allclose(ignore["distance"]["speed_policy_limit_kmh"], 180.0)

        self.assertLessEqual(float(np.max(obey["time"]["speed_kmh"])), 50.0 + 1e-6)
        self.assertLessEqual(float(np.max(zero["time"]["speed_kmh"])), 70.0 + 1e-6)
        self.assertLessEqual(float(np.max(one["time"]["speed_kmh"])), 80.0 + 1e-6)
        self.assertGreater(float(np.max(ignore["time"]["speed_kmh"])), 80.0)

    def test_new_outputs_share_the_existing_axes(self) -> None:
        result = simulate_speed_profile(
            self._route(), self._parameters(POLICY_GERMANY_POINTS, 1)
        )
        n_distance = len(result["distance"]["distance_m"])
        for name in (
            "road_limit_kmh",
            "speed_policy_limit_kmh",
            "speeding_over_kmh",
            "speeding_points",
            "actual_speed_kmh",
        ):
            self.assertEqual(len(result["distance"][name]), n_distance, name)

        n_time = len(result["time"]["time_s"])
        for name in (
            "distance_m",
            "speed_kmh",
            "road_limit_kmh",
            "speed_policy_limit_kmh",
            "speeding_over_kmh",
            "speeding_points",
        ):
            self.assertEqual(len(result["time"][name]), n_time, name)

        self.assertLessEqual(result["summary"]["max_speeding_points_estimated"], 1.0)


if __name__ == "__main__":
    unittest.main()
