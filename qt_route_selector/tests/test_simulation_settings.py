from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qt_route_selector.simulation_settings import (
    SIMULATION_SETTINGS_SCHEMA_VERSION,
    load_settings_file,
    save_settings_file,
)


class SimulationSettingsTests(unittest.TestCase):
    def test_settings_roundtrip_preserves_parameters(self) -> None:
        payload = {
            "schema_version": SIMULATION_SETTINGS_SCHEMA_VERSION,
            "parameters": {
                "driver_profile": "normalo",
                "speed_limit_policy": "germany_points",
                "max_speeding_points": 1,
                "driver_hard_max_kmh": 155.0,
                "start_stop": True,
            },
            "elevation_smoothing_m": 35.0,
            "comparison_configs": [
                {
                    "name": "Autobahn",
                    "parameters": {"driver_hard_max_kmh": 180.0},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "simulation_settings.json"
            saved = save_settings_file(path, payload)
            loaded = load_settings_file(saved)

        self.assertEqual(loaded["parameters"], payload["parameters"])
        self.assertEqual(loaded["elevation_smoothing_m"], 35.0)
        self.assertEqual(loaded["comparison_configs"][0]["name"], "Autobahn")

    def test_invalid_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "simulation_settings.json"
            path.write_text(
                '{"schema_version": 999, "parameters": {}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Version"):
                load_settings_file(path)


if __name__ == "__main__":
    unittest.main()
