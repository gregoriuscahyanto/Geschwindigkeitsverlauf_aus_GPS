from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from qt_route_selector.mat_export import export_matlab_simulation


class MatlabExportTests(unittest.TestCase):
    def test_export_contains_radius_elevation_power_and_raw_route(self) -> None:
        distance_m = np.asarray([0.0, 50.0, 100.0])
        result = {
            "parameters": {"driver_profile": "normalo", "vehicle_mass_kg": 1800.0},
            "distance": {
                "distance_m": distance_m,
                "road_limit_kmh": np.asarray([50.0, 50.0, 70.0]),
                "surface_limit_kmh": np.asarray([50.0, 50.0, 70.0]),
                "curve_limit_kmh": np.asarray([120.0, 35.0, 120.0]),
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
                "overtaking": [],
            },
            "summary": {
                "distance_km": 0.1,
                "duration_min": 0.5,
                "average_speed_kmh": 12.0,
            },
        }
        elevation_m = np.asarray([430.0, 435.0, 432.0])
        power_data = {
            "time_s": np.asarray([0.0, 5.0, 10.0]),
            "distance_m": distance_m,
            "spatial_distance_m": distance_m,
            "grade_spatial": np.asarray([0.0, 0.1, -0.06]),
            "grade_fraction": np.asarray([0.0, 0.1, -0.06]),
            "grade_pct": np.asarray([0.0, 10.0, -6.0]),
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
            "segments": [{"from_index": 0, "distance_m": 50.0, "highway": "primary"}],
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
                source_route="route_result.json",
            )
            self.assertEqual(output.suffix, ".mat")
            self.assertTrue(output.is_file())

            loaded = loadmat(output, simplify_cells=True)

        self.assertIn("distance", loaded)
        self.assertIn("time", loaded)
        self.assertIn("power", loaded)
        self.assertIn("distance_table", loaded)
        self.assertIn("time_table", loaded)
        self.assertIn("route_json", loaded)
        self.assertIn("load_collective", loaded)

        distance = loaded["distance"]
        np.testing.assert_allclose(np.asarray(distance["elevation_m"]), elevation_m)
        np.testing.assert_allclose(
            np.asarray(distance["curve_radius_m"]),
            np.asarray([np.inf, 42.0, np.inf]),
        )
        np.testing.assert_allclose(np.asarray(distance["grade_pct"]), [0.0, 10.0, -6.0])

        power = loaded["power"]
        self.assertAlmostEqual(float(power["net_energy_kwh"]), 0.03)
        np.testing.assert_allclose(np.asarray(power["total_kw"]), [0.0, 37.0, -17.0])

        route_roundtrip = json.loads(str(loaded["route_json"]))
        self.assertEqual(route_roundtrip["traffic_signals"][0]["osm_id"], 12345)
        self.assertEqual(route_roundtrip["segments"][0]["highway"], "primary")

        columns = [str(item) for item in np.atleast_1d(loaded["distance_columns"])]
        self.assertIn("curve_radius_m", columns)
        self.assertIn("elevation_m", columns)
        time_columns = [str(item) for item in np.atleast_1d(loaded["time_columns"])]
        self.assertIn("total_kw", time_columns)
        self.assertIn("cumulative_net_energy_kwh", time_columns)


if __name__ == "__main__":
    unittest.main()
