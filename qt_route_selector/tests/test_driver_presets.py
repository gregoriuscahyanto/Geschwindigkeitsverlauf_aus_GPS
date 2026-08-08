from __future__ import annotations

import unittest

from qt_route_selector import speed_simulation
from qt_route_selector.driver_presets import (
    COMPLETE_DRIVER_PROFILES,
    POST_CURVE_DEFAULTS,
    install_complete_driver_profiles,
)


class DriverPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_complete_driver_profiles(speed_simulation)

    def test_all_presets_define_core_driver_behavior(self) -> None:
        required = {
            "temperament",
            "driver_cruise_kmh",
            "driver_hard_max_kmh",
            "speed_bias_kmh",
            "speed_tolerance_kmh",
            "Kp",
            "a_max_mps2",
            "b_max_mps2",
            "j_max_mps3",
            "max_lat_accel_mps2",
            "curve_plan_decel_mps2",
            "traffic_light_plan_decel_mps2",
            "traffic_light_stop_tolerance_m",
            "use_driver_noise",
            "noise_std_kmh",
            "noise_tau_s",
            "use_post_curve_overshoot",
            "post_curve_overshoot_kmh",
            "post_curve_overshoot_probability_pct",
            "post_curve_overshoot_distance_m",
            "use_overtaking",
            "overtaking_count",
            "use_trailer_model",
        }
        self.assertEqual(set(COMPLETE_DRIVER_PROFILES), set(speed_simulation.DRIVER_PROFILES))
        for name, profile in speed_simulation.DRIVER_PROFILES.items():
            self.assertTrue(required.issubset(profile), name)
            self.assertGreaterEqual(profile["driver_hard_max_kmh"], profile["driver_cruise_kmh"])

    def test_profiles_have_expected_behavior_order(self) -> None:
        normal = speed_simulation.profile_parameters("normalo")
        racer = speed_simulation.profile_parameters("rennfahrer")
        retiree = speed_simulation.profile_parameters("rentner")
        trailer = speed_simulation.profile_parameters("rentner_anhaenger")

        self.assertGreater(racer["driver_cruise_kmh"], normal["driver_cruise_kmh"])
        self.assertGreater(normal["driver_cruise_kmh"], retiree["driver_cruise_kmh"])
        self.assertGreater(racer["a_max_mps2"], normal["a_max_mps2"])
        self.assertGreater(normal["a_max_mps2"], retiree["a_max_mps2"])
        self.assertGreater(racer["max_lat_accel_mps2"], retiree["max_lat_accel_mps2"])
        self.assertFalse(retiree["use_driver_noise"])
        self.assertAlmostEqual(retiree["j_max_mps3"], 0.55)
        self.assertAlmostEqual(retiree["post_curve_overshoot_kmh"], 1.0)
        self.assertAlmostEqual(retiree["post_curve_overshoot_probability_pct"], 20.0)
        self.assertFalse(trailer["use_post_curve_overshoot"])
        self.assertTrue(trailer["use_trailer_model"])

    def test_post_curve_defaults_are_part_of_profile_parameters(self) -> None:
        values = speed_simulation.profile_parameters("normalo")
        for key, default in POST_CURVE_DEFAULTS.items():
            self.assertIn(key, values)
            self.assertEqual(values[key], speed_simulation.DRIVER_PROFILES["normalo"][key])
            self.assertEqual(default, COMPLETE_DRIVER_PROFILES["normalo"][key])

    def test_unknown_profile_still_falls_back_to_normalo(self) -> None:
        values = speed_simulation.profile_parameters("does-not-exist")
        self.assertEqual(values["driver_profile"], "normalo")
        self.assertEqual(values["driver_cruise_kmh"], 130.0)


if __name__ == "__main__":
    unittest.main()
