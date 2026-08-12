from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from qt_route_selector.mat_export import export_matlab_simulation


class MatlabExportTests(unittest.TestCase):
    def test_export_contains_compact_doubles_and_axis_grouped_struct(self) -> None:
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
                "post_curve_boost_kmh": np.asarray([0.0, 2.0, 0.0]),
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
                "post_curve_overshoot": [
                    {
                        "curve_exit_m": 50.0,
                        "peak_boost_kmh": 2.0,
                        "rise_distance_m": 25.0,
                        "decay_distance_m": 90.0,
                    },
                    {
                        "curve_exit_m": 80.0,
                        "peak_boost_kmh": 1.5,
                        "rise_distance_m": 20.0,
                        "decay_distance_m": 75.0,
                    },
                ],
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
            "braking_energy_kwh": 0.012,
            "p95_positive_kw": 35.0,
            "maximum_kw": 37.0,
            "minimum_kw": -17.0,
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
            "segments": [
                {"from_index": 0, "to_index": 1, "distance_m": 50.0, "highway": "primary"},
                {"from_index": 1, "to_index": 2, "distance_m": 50.0, "highway": "primary"},
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
            simplified = loadmat(output, simplify_cells=True)

        variables = {key: value for key, value in loaded.items() if not key.startswith("__")}
        self.assertTrue(variables)
        self.assertIn("sim", variables)

        # Every flat top-level signal remains a MATLAB double. Only sim is a struct.
        for name, value in variables.items():
            if name == "sim":
                continue
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
            "route_post_curve_boost_kmh",
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
            "e_braking_kwh",
            "p_p95_positive_kw",
            "p_max_kw",
            "p_min_kw",
            "route_distance_m",
            "route_elevation_m",
            "route_curve_radius_m",
            "traffic_light_distance_m",
            "traffic_light_dwell_s",
            "traffic_light_start_s",
            "traffic_light_end_s",
            "post_curve_curve_exit_m",
            "post_curve_peak_boost_kmh",
            "post_curve_rise_distance_m",
            "post_curve_decay_distance_m",
            "segment_from_index",
            "segment_to_index",
            "segment_distance_m",
            "osm_signal_distance_from_start_m",
            "osm_signal_osm_id",
            "param_vehicle_mass_kg",
            "summary_average_speed_kmh",
        }
        self.assertTrue(required.issubset(variables.keys()), required - variables.keys())

        # Compactness is part of the contract: records are columns, not thousands of scalars.
        self.assertLess(len(variables), 121)
        self.assertFalse(any(name.startswith("route_extra_") for name in variables))
        self.assertFalse(any("post_curve_overshoot_1_" in name for name in variables))

        # Time-axis signals share exactly one length.
        time_axis_names = {
            "time_s", "distance_m", "v_kmh", "v_target_kmh", "a_mps2",
            "elevation_m", "curve_radius_m", "grade_pct", "p_total_kw",
            "p_acceleration_kw", "p_grade_kw", "p_rolling_kw", "p_air_kw",
            "p_trailer_kw", "p_traction_kw", "p_recuperation_kw",
            "e_traction_cum_kwh", "e_recuperation_cum_kwh", "e_net_cum_kwh",
        }
        self.assertEqual({variables[name].size for name in time_axis_names}, {3})

        # Route-axis signals share the independent spatial route length.
        route_axis_names = {
            "route_distance_m", "route_lat_deg", "route_lon_deg",
            "route_elevation_m", "route_curve_radius_m", "route_grade_pct",
            "route_v_road_limit_kmh", "route_v_curve_limit_kmh",
            "route_post_curve_boost_kmh",
        }
        self.assertEqual({variables[name].size for name in route_axis_names}, {3})

        np.testing.assert_allclose(variables["time_s"].ravel(), [0.0, 5.0, 10.0])
        np.testing.assert_allclose(variables["v_kmh"].ravel(), [0.0, 33.0, 0.0])
        np.testing.assert_allclose(variables["elevation_m"].ravel(), elevation_m)
        np.testing.assert_allclose(
            variables["curve_radius_m"].ravel(), [np.inf, 42.0, np.inf]
        )
        np.testing.assert_allclose(variables["grade_pct"].ravel(), [0.0, 10.0, -6.0])
        np.testing.assert_allclose(variables["p_total_kw"].ravel(), [0.0, 37.0, -17.0])
        np.testing.assert_allclose(variables["post_curve_curve_exit_m"].ravel(), [50.0, 80.0])
        np.testing.assert_allclose(variables["segment_distance_m"].ravel(), [50.0, 50.0])
        self.assertAlmostEqual(float(variables["e_net_kwh"].ravel()[0]), 0.03)
        self.assertAlmostEqual(float(variables["param_vehicle_mass_kg"].ravel()[0]), 1800.0)
        self.assertEqual(float(variables["param_trailer_enabled"].ravel()[0]), 0.0)
        self.assertAlmostEqual(float(variables["osm_signal_osm_id"].ravel()[0]), 12345.0)

        # The struct makes the natural reference axes explicit without MATLAB itself.
        sim = simplified["sim"]
        self.assertIsInstance(sim, dict)
        self.assertIn("time", sim)
        self.assertIn("route", sim)
        self.assertIn("geometry", sim)
        self.assertIn("events", sim)
        self.assertIn("load", sim)
        self.assertIn("segments", sim)
        self.assertIn("parameters", sim)
        self.assertIn("summary", sim)

        np.testing.assert_allclose(np.asarray(sim["time"]["time_s"]).ravel(), [0.0, 5.0, 10.0])
        np.testing.assert_allclose(np.asarray(sim["time"]["v_kmh"]).ravel(), [0.0, 33.0, 0.0])
        np.testing.assert_allclose(np.asarray(sim["route"]["elevation_m"]).ravel(), elevation_m)
        np.testing.assert_allclose(
            np.asarray(sim["route"]["curve_radius_m"]).ravel(), [np.inf, 42.0, np.inf]
        )
        np.testing.assert_allclose(
            np.asarray(sim["events"]["post_curve"]["curve_exit_m"]).ravel(), [50.0, 80.0]
        )
        np.testing.assert_allclose(
            np.asarray(sim["segments"]["distance_m"]).ravel(), [50.0, 50.0]
        )
        self.assertAlmostEqual(float(sim["parameters"]["vehicle_mass_kg"]), 1800.0)
        self.assertAlmostEqual(float(sim["summary"]["average_speed_kmh"]), 12.0)


if __name__ == "__main__":
    unittest.main()
