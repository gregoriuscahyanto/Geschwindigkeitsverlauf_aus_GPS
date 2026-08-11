from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from qt_route_selector.mat_export import export_matlab_simulation


class MatlabExportTests(unittest.TestCase):
    def test_export_contains_only_individual_double_arrays(self) -> None:
        distance_m = np.asarray([0.0, 50.0, 100.0])
        result = {
            "parameters": {"vehicle_mass_kg": 1800.0, "trailer_enabled": False},
            "distance": {
                "distance_m": distance_m,
                "road_limit_kmh": np.asarray([50.0, 50.0, 70.0]),
                "surface_limit_kmh": np.asarray([50.0, 50.0, 70.0]),
                "curve_limit_kmh": np.asarray([np.inf, 35.0, np.inf]),
                "base_target_kmh": np.asarray([50.0, 35.0, 70.0]),
                "planned_speed_kmh": np.asarray([0.0, 35.0, 0.0]),
                "actual_speed_kmh": np.asarray([0.0, 33.0, 0.0]),
                "noise_kmh": np.asarray([0.0, 0.2, 0.0]),
                "curve_radius_m": np.asarray([np.inf, 42.0, np.inf]),
                "latitude": np.asarray([48.70, 48.7005, 48.7010]),
                "longitude": np.asarray([9.30, 9.3005, 9.3010]),
            },
            "time": {
                "time_s": np.asarray([0.0, 5.0, 10.0]),
                "distance_m": distance_m,
                "speed_kmh": np.asarray([0.0, 33.0, 0.0]),
                "target_kmh": np.asarray([0.0, 35.0, 0.0]),
                "acceleration_mps2": np.asarray([0.0, 1.1, -1.2]),
            },
            "events": {
                "traffic_lights": [{"distance_m": 100.0, "dwell_s": 20.0}],
                "traffic_light_dwell_intervals_s": [[10.0, 30.0]],
            },
            "summary": {
                "distance_km": 0.1,
                "duration_min": 0.5,
                "average_speed_kmh": 12.0,
            },
        }
        elevation_m = np.asarray([430.0, 435.0, 432.0])
        power_data = {
            "grade_spatial": np.asarray([0.0, 0.1, -0.06]),
            "acceleration_kw": np.asarray([0.0, 18.0, -12.0]),
            "grade_kw": np.asarray([0.0, 16.0, -5.0]),
            "rolling_kw": np.asarray([0.0, 2.0, 0.0]),
            "air_kw": np.asarray([0.0, 1.0, 0.0]),
            "trailer_kw": np.zeros(3),
            "total_kw": np.asarray([0.0, 37.0, -17.0]),
            "traction_power_kw": np.asarray([0.0, 37.0, 0.0]),
            "recuperation_power_kw": np.asarray([0.0, 0.0, 17.0]),
            "traction_energy_kwh": 0.04,
            "recuperation_energy_kwh": 0.01,
            "net_energy_kwh": 0.03,
            "cumulative_traction_energy_kwh": np.asarray([0.0, 0.025, 0.04]),
            "cumulative_recuperation_energy_kwh": np.asarray([0.0, 0.0, 0.01]),
            "cumulative_net_energy_kwh": np.asarray([0.0, 0.025, 0.03]),
            "trailer_enabled": False,
        }
        route = {
            "coordinates": [
                {"latitude": 48.70, "longitude": 9.30, "elevation_m": 430.0},
                {"latitude": 48.7005, "longitude": 9.3005, "elevation_m": 435.0},
                {"latitude": 48.7010, "longitude": 9.3010, "elevation_m": 432.0},
            ],
            "traffic_signals": [{"distance_from_start_m": 100.0, "osm_id": 12345}],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = export_matlab_simulation(
                result,
                Path(temporary_directory) / "complete_export",
                route=route,
                parameters=result["parameters"],
                power_data=power_data,
                elevation_m=elevation_m,
            )
            self.assertEqual(output.suffix, ".mat")
            self.assertTrue(output.is_file())
            loaded = loadmat(output)

        variables = {key: value for key, value in loaded.items() if not key.startswith("__")}
        self.assertTrue(variables)
        for name, value in variables.items():
            self.assertIsInstance(value, np.ndarray, name)
            self.assertEqual(value.dtype, np.dtype(np.float64), name)

        required = {
            "time_s",
            "distance_m",
            "v_kmh",
            "v_target_kmh",
            "a_mps2",
            "elevation_m",
            "curve_radius_m",
            "grade_pct",
            "v_road_limit_kmh",
            "v_curve_limit_kmh",
            "p_total_kw",
            "p_acceleration_kw",
            "p_grade_kw",
            "p_rolling_kw",
            "p_air_kw",
            "p_trailer_kw",
            "p_traction_kw",
            "p_recuperation_kw",
            "e_traction_kwh",
            "e_recuperation_kwh",
            "e_net_kwh",
            "route_distance_m",
            "route_elevation_m",
            "route_curve_radius_m",
            "traffic_light_distance_m",
            "traffic_light_dwell_s",
            "traffic_light_start_s",
            "traffic_light_end_s",
            "param_vehicle_mass_kg",
            "summary_average_speed_kmh",
        }
        self.assertTrue(required.issubset(variables.keys()), required - variables.keys())

        np.testing.assert_allclose(variables["time_s"].ravel(), [0.0, 5.0, 10.0])
        np.testing.assert_allclose(variables["v_kmh"].ravel(), [0.0, 33.0, 0.0])
        np.testing.assert_allclose(variables["elevation_m"].ravel(), elevation_m)
        np.testing.assert_allclose(
            variables["curve_radius_m"].ravel(), [np.inf, 42.0, np.inf]
        )
        np.testing.assert_allclose(variables["grade_pct"].ravel(), [0.0, 10.0, -6.0])
        np.testing.assert_allclose(variables["p_total_kw"].ravel(), [0.0, 37.0, -17.0])
        self.assertAlmostEqual(float(variables["e_net_kwh"].ravel()[0]), 0.03)
        self.assertAlmostEqual(float(variables["param_vehicle_mass_kg"].ravel()[0]), 1800.0)
        self.assertEqual(float(variables["param_trailer_enabled"].ravel()[0]), 0.0)
        self.assertAlmostEqual(float(variables["route_extra_traffic_signals_1_osm_id"].ravel()[0]), 12345.0)


if __name__ == "__main__":
    unittest.main()
