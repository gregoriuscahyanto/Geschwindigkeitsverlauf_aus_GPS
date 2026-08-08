from __future__ import annotations

import unittest

import numpy as np

from qt_route_selector.resistance_power import (
    calculate_resistance_power,
    load_collective,
    road_grade,
)


class ResistancePowerTests(unittest.TestCase):
    def test_flat_constant_speed_has_roll_and_air_power(self) -> None:
        time = np.arange(0.0, 11.0, 1.0)
        speed = np.full_like(time, 72.0)
        acceleration = np.zeros_like(time)
        grade = np.zeros_like(time)
        result = calculate_resistance_power(
            time,
            speed,
            acceleration,
            grade,
            {
                "vehicle_mass_kg": 1800.0,
                "rolling_resistance_coeff": 0.015,
                "air_drag_coefficient": 0.29,
                "frontal_area_m2": 2.3,
                "air_density_kg_m3": 1.225,
                "use_trailer_model": False,
            },
        )
        self.assertTrue(np.allclose(result["acceleration_kw"], 0.0))
        self.assertTrue(np.allclose(result["grade_kw"], 0.0))
        self.assertTrue(np.all(np.asarray(result["rolling_kw"]) > 0.0))
        self.assertTrue(np.all(np.asarray(result["air_kw"]) > 0.0))
        expected = (
            np.asarray(result["acceleration_kw"])
            + np.asarray(result["grade_kw"])
            + np.asarray(result["rolling_kw"])
            + np.asarray(result["air_kw"])
            + np.asarray(result["trailer_kw"])
        )
        np.testing.assert_allclose(result["total_kw"], expected)
        self.assertGreater(float(result["traction_energy_kwh"]), 0.0)
        self.assertAlmostEqual(float(result["recuperation_energy_kwh"]), 0.0, places=9)
        self.assertAlmostEqual(
            float(result["net_energy_kwh"]),
            float(result["traction_energy_kwh"]),
            places=9,
        )

    def test_uphill_grade_creates_positive_climbing_power(self) -> None:
        distance = np.arange(0.0, 101.0, 5.0)
        elevation = distance * 0.10
        grade = road_grade(distance, elevation, smoothing_distance_m=0.0)
        self.assertAlmostEqual(float(np.median(grade[2:-2])), 0.10, places=2)

        time = np.linspace(0.0, 10.0, len(distance))
        result = calculate_resistance_power(
            time,
            np.full(len(distance), 36.0),
            np.zeros(len(distance)),
            grade,
            {"vehicle_mass_kg": 1500.0},
        )
        self.assertGreater(float(np.median(result["grade_kw"])), 10.0)

    def test_trailer_component_contains_extra_longitudinal_load(self) -> None:
        time = np.arange(0.0, 6.0, 1.0)
        speed = np.full_like(time, 54.0)
        acceleration = np.full_like(time, 0.5)
        grade = np.full_like(time, 0.05)
        result = calculate_resistance_power(
            time,
            speed,
            acceleration,
            grade,
            {
                "vehicle_mass_kg": 1800.0,
                "use_trailer_model": True,
                "trailer_mass_kg": 1200.0,
                "trailer_rolling_resistance_coeff": 0.015,
                "trailer_drag_area_m2": 1.0,
            },
        )
        self.assertTrue(result["trailer_enabled"])
        self.assertTrue(np.all(np.asarray(result["trailer_kw"]) > 0.0))

    def test_deceleration_can_produce_negative_total_power_and_recuperation(self) -> None:
        time = np.arange(0.0, 5.0, 1.0)
        result = calculate_resistance_power(
            time,
            np.full_like(time, 72.0),
            np.full_like(time, -2.0),
            np.zeros_like(time),
            {"vehicle_mass_kg": 1800.0},
        )
        self.assertLess(float(np.min(result["total_kw"])), 0.0)
        self.assertGreater(float(result["recuperation_energy_kwh"]), 0.0)
        self.assertAlmostEqual(
            float(result["braking_energy_kwh"]),
            float(result["recuperation_energy_kwh"]),
            places=9,
        )
        self.assertAlmostEqual(
            float(result["net_energy_kwh"]),
            float(result["traction_energy_kwh"]) - float(result["recuperation_energy_kwh"]),
            places=9,
        )

    def test_cumulative_energy_ends_at_scalar_energy_balance(self) -> None:
        time = np.arange(0.0, 9.0, 1.0)
        speed = np.full_like(time, 54.0)
        acceleration = np.asarray([0.0, 1.2, 1.0, 0.2, -0.5, -1.5, -1.0, 0.3, 0.0])
        result = calculate_resistance_power(
            time,
            speed,
            acceleration,
            np.zeros_like(time),
            {"vehicle_mass_kg": 1800.0},
        )
        drive_curve = np.asarray(result["cumulative_traction_energy_kwh"])
        recup_curve = np.asarray(result["cumulative_recuperation_energy_kwh"])
        net_curve = np.asarray(result["cumulative_net_energy_kwh"])
        self.assertEqual(len(drive_curve), len(time))
        self.assertTrue(np.all(np.diff(drive_curve) >= -1e-12))
        self.assertTrue(np.all(np.diff(recup_curve) >= -1e-12))
        self.assertAlmostEqual(float(drive_curve[-1]), float(result["traction_energy_kwh"]), places=9)
        self.assertAlmostEqual(float(recup_curve[-1]), float(result["recuperation_energy_kwh"]), places=9)
        self.assertAlmostEqual(float(net_curve[-1]), float(result["net_energy_kwh"]), places=9)

    def test_load_collective_is_time_weighted_and_sums_to_100_percent(self) -> None:
        time = np.asarray([0.0, 1.0, 2.0, 4.0, 7.0])
        power = np.asarray([0.0, 10.0, 10.0, 30.0, 30.0])
        result = load_collective(time, power, bin_count=6)
        shares = np.asarray(result["time_share_pct"])
        self.assertGreater(shares.size, 0)
        self.assertAlmostEqual(float(np.sum(shares)), 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
