from __future__ import annotations

import unittest

from qt_route_selector.parameter_help import PARAMETER_HELP, SPECIAL_HELP


EXPECTED_SIMULATION_PARAMETERS = {
    "temperament",
    "driver_cruise_kmh",
    "driver_hard_max_kmh",
    "speed_bias_kmh",
    "speed_tolerance_kmh",
    "Kp",
    "a_max_mps2",
    "b_max_mps2",
    "j_max_mps3",
    "start_stop",
    "end_stop",
    "use_post_curve_overshoot",
    "post_curve_overshoot_kmh",
    "post_curve_overshoot_probability_pct",
    "post_curve_overshoot_distance_m",
    "apply_curve_speed",
    "max_lat_accel_mps2",
    "min_curve_radius_m",
    "max_curve_radius_m",
    "curve_sample_distance_m",
    "curve_smooth_distance_m",
    "curve_plan_decel_mps2",
    "use_surface_limit",
    "use_traffic_lights",
    "traffic_light_count",
    "traffic_light_dwell_min_s",
    "traffic_light_dwell_max_s",
    "traffic_light_plan_decel_mps2",
    "traffic_light_stop_tolerance_m",
    "use_overtaking",
    "overtaking_count",
    "overtaking_slow_speed_kmh",
    "overtaking_intensity_kmh",
    "overtaking_follow_distance_m",
    "overtaking_pass_distance_m",
    "use_driver_noise",
    "noise_std_kmh",
    "noise_tau_s",
    "simulation_seed",
    "use_trailer_model",
    "vehicle_mass_kg",
    "trailer_mass_kg",
    "rolling_resistance_coeff",
    "max_drive_force_n",
    "max_brake_force_n",
    "air_drag_coefficient",
    "frontal_area_m2",
    "air_density_kg_m3",
    "trailer_rolling_resistance_coeff",
    "trailer_drag_area_m2",
    "grade_smoothing_m",
}


class ParameterHelpTests(unittest.TestCase):
    def test_every_simulation_parameter_has_curated_help(self) -> None:
        self.assertEqual(EXPECTED_SIMULATION_PARAMETERS - set(PARAMETER_HELP), set())

    def test_help_entries_have_description_effect_and_examples(self) -> None:
        for key, entry in PARAMETER_HELP.items():
            self.assertEqual(len(entry), 3, key)
            for text in entry:
                self.assertGreater(len(text.strip()), 10, key)

    def test_special_visible_parameters_are_documented(self) -> None:
        self.assertIn("driver_profile", SPECIAL_HELP)
        self.assertIn("elevation_smoothing", SPECIAL_HELP)


if __name__ == "__main__":
    unittest.main()
