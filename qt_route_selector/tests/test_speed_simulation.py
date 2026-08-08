from __future__ import annotations

import unittest

import numpy as np

from qt_route_selector.speed_simulation import (
    prepare_route,
    profile_parameters,
    simulate_speed_profile,
)


def synthetic_route() -> dict:
    coordinates = []
    for index in range(21):
        coordinates.append(
            {"latitude": 48.0, "longitude": 9.0 + index * 0.0001}
        )
    for index in range(1, 21):
        coordinates.append(
            {"latitude": 48.0 + index * 0.0001, "longitude": 9.002}
        )

    segments = []
    for index in range(len(coordinates) - 1):
        segments.append(
            {
                "from_index": index,
                "to_index": index + 1,
                "distance_m": 11.1,
                "maxspeed_kmh": 80.0 if index < 20 else 50.0,
                "surface": "asphalt",
                "highway": "primary",
            }
        )
    return {
        "coordinates": coordinates,
        "segments": segments,
        "traffic_signals": [
            {
                "latitude": 48.0,
                "longitude": 9.001,
                "distance_from_start_m": 111.0,
            }
        ],
    }


class SpeedSimulationTests(unittest.TestCase):
    def test_prepare_route(self) -> None:
        prepared = prepare_route(synthetic_route(), sample_distance_m=5.0)
        self.assertGreater(prepared.total_distance_m, 400.0)
        self.assertEqual(len(prepared.detected_signal_distances_m), 1)
        self.assertEqual(len(prepared.distance_m), len(prepared.maxspeed_kmh))

    def test_profile_parameters(self) -> None:
        rentner = profile_parameters("rentner")
        racer = profile_parameters("rennfahrer")
        self.assertLess(rentner["a_max_mps2"], racer["a_max_mps2"])
        self.assertFalse(rentner["use_driver_noise"])

    def test_curve_and_light_limit_speed(self) -> None:
        parameters = profile_parameters("normalo")
        parameters.update(
            {
                "driver_cruise_kmh": 120.0,
                "driver_hard_max_kmh": 130.0,
                "traffic_light_count": 1,
                "traffic_light_dwell_min_s": 2.0,
                "traffic_light_dwell_max_s": 2.0,
                "simulation_seed": 1,
            }
        )
        result = simulate_speed_profile(synthetic_route(), parameters)
        distance = result["distance"]
        self.assertLess(float(np.nanmin(distance["curve_limit_kmh"])), 80.0)
        stop = result["events"]["traffic_lights"][0]["distance_m"]
        index = int(np.argmin(np.abs(distance["distance_m"] - stop)))
        self.assertAlmostEqual(
            float(distance["planned_speed_kmh"][index]),
            0.0,
            places=5,
        )
        self.assertGreater(result["summary"]["duration_min"], 0.0)

    def test_overtaking_and_noise_are_deterministic(self) -> None:
        parameters = profile_parameters("rennfahrer")
        parameters.update(
            {
                "traffic_light_count": 0,
                "use_overtaking": True,
                "overtaking_count": 1,
                "simulation_seed": 9,
            }
        )
        first = simulate_speed_profile(synthetic_route(), parameters)
        second = simulate_speed_profile(synthetic_route(), parameters)
        np.testing.assert_allclose(
            first["distance"]["planned_speed_kmh"],
            second["distance"]["planned_speed_kmh"],
        )


if __name__ == "__main__":
    unittest.main()
