from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from qt_route_selector.synchronized_mat_export import export_matlab_simulation


class SynchronizedMatExportTests(unittest.TestCase):
    def test_all_simulation_inputs_share_time_length(self) -> None:
        # Deliberately use different spatial/time lengths. The exported
        # simulation inputs must all follow the 5-sample time axis.
        result = {
            "distance": {
                "distance_m": np.asarray([0.0, 30.0, 70.0, 100.0]),
                "latitude": np.asarray([48.0, 48.001, 48.002, 48.003]),
                "longitude": np.asarray([9.0, 9.001, 9.002, 9.003]),
                "curve_radius_m": np.asarray([np.inf, 80.0, 35.0, np.inf]),
                "road_limit_kmh": np.asarray([50.0, 50.0, 30.0, 70.0]),
                "surface_limit_kmh": np.asarray([50.0, 50.0, 30.0, 70.0]),
                "curve_limit_kmh": np.asarray([140.0, 55.0, 32.0, 140.0]),
                "base_target_kmh": np.asarray([50.0, 50.0, 30.0, 70.0]),
                "planned_speed_kmh": np.asarray([0.0, 35.0, 28.0, 0.0]),
                "actual_speed_kmh": np.asarray([0.0, 34.0, 27.0, 0.0]),
                "noise_kmh": np.asarray([0.0, 0.2, -0.1, 0.0]),
                "post_curve_boost_kmh": np.asarray([0.0, 1.0, 2.0, 0.0]),
            },
            "time": {
                "time_s": np.asarray([0.0, 2.0, 4.0, 6.0, 8.0]),
                "distance_m": np.asarray([0.0, 18.0, 44.0, 73.0, 100.0]),
                "speed_kmh": np.asarray([0.0, 25.0, 31.0, 27.0, 0.0]),
                "target_kmh": np.asarray([0.0, 30.0, 35.0, 30.0, 0.0]),
                "acceleration_mps2": np.asarray([0.0, 1.2, 0.3, -0.8, -1.5]),
            },
            "events": {},
            "summary": {},
        }
        elevation = np.asarray([400.0, 405.0, 410.0, 408.0])
        power = {
            "grade_spatial": np.asarray([0.0, 0.04, -0.02, 0.0]),
            "total_kw": np.asarray([0.0, 12.0, 18.0, 7.0, -3.0]),
            "acceleration_kw": np.zeros(5),
            "grade_kw": np.zeros(5),
            "rolling_kw": np.zeros(5),
            "air_kw": np.zeros(5),
            "trailer_kw": np.zeros(5),
            "traction_power_kw": np.asarray([0.0, 12.0, 18.0, 7.0, 0.0]),
            "recuperation_power_kw": np.asarray([0.0, 0.0, 0.0, 0.0, 3.0]),
            "cumulative_traction_energy_kwh": np.zeros(5),
            "cumulative_recuperation_energy_kwh": np.zeros(5),
            "cumulative_net_energy_kwh": np.zeros(5),
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = export_matlab_simulation(
                result,
                Path(temporary_directory) / "sync.mat",
                power_data=power,
                elevation_m=elevation,
            )
            loaded = loadmat(path, simplify_cells=True)

        input_names = sorted(name for name in loaded if name.startswith("input_"))
        self.assertTrue(input_names)
        sizes = {np.asarray(loaded[name]).size for name in input_names}
        self.assertEqual(sizes, {5})

        required = {
            "input_time_s",
            "input_distance_m",
            "input_v_kmh",
            "input_curve_radius_m",
            "input_elevation_m",
            "input_grade_pct",
            "input_lat_deg",
            "input_lon_deg",
            "input_v_road_limit_kmh",
            "input_p_total_kw",
            "input_post_curve_boost_kmh",
        }
        self.assertTrue(required.issubset(loaded.keys()), required - loaded.keys())

        sim_input = loaded["sim_input"]
        self.assertIsInstance(sim_input, dict)
        self.assertEqual(
            {np.asarray(value).size for value in sim_input.values()},
            {5},
        )
        np.testing.assert_allclose(np.asarray(sim_input["time_s"]).ravel(), [0, 2, 4, 6, 8])
        np.testing.assert_allclose(np.asarray(sim_input["v_kmh"]).ravel(), [0, 25, 31, 27, 0])
        self.assertEqual(np.asarray(sim_input["curve_radius_m"]).size, 5)
        self.assertEqual(np.asarray(sim_input["post_curve_boost_kmh"]).size, 5)


if __name__ == "__main__":
    unittest.main()
