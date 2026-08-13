from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qt_route_selector.simulation_settings import (
    SIMULATION_SETTINGS_KEY,
    SIMULATION_SETTINGS_SCHEMA_VERSION,
    load_settings_from_route,
    save_settings_to_route,
)


class SimulationSettingsTests(unittest.TestCase):
    def test_route_and_multiple_drivers_roundtrip_in_one_json(self) -> None:
        payload = {
            "schema_version": SIMULATION_SETTINGS_SCHEMA_VERSION,
            "active_driver": {
                "name": "Normalo",
                "profile": "normalo",
                "parameters": {
                    "driver_profile": "normalo",
                    "speed_limit_policy": "germany_points",
                    "max_speeding_points": 1,
                    "driver_hard_max_kmh": 155.0,
                    "start_stop": True,
                },
            },
            "drivers": [
                {
                    "name": "Schneller Fahrer",
                    "parameters": {"driver_hard_max_kmh": 180.0},
                },
                {
                    "name": "Eco",
                    "parameters": {"driver_hard_max_kmh": 120.0},
                },
            ],
            "elevation_smoothing_m": 35.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "route_result_20260813_135742.json"
            path.write_text(
                json.dumps(
                    {
                        "metadata": {"created_at": "2026-08-13T13:57:42+02:00"},
                        "coordinates": [
                            {"latitude": 48.0, "longitude": 9.0},
                            {"latitude": 48.1, "longitude": 9.1},
                        ],
                        "segments": [],
                    }
                ),
                encoding="utf-8",
            )
            saved = save_settings_to_route(path, payload)
            loaded = load_settings_from_route(saved)
            document = json.loads(saved.read_text(encoding="utf-8"))

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["active_driver"]["parameters"]["max_speeding_points"], 1)
        self.assertEqual(len(loaded["drivers"]), 2)
        self.assertEqual(loaded["drivers"][0]["name"], "Schneller Fahrer")
        self.assertIn(SIMULATION_SETTINGS_KEY, document)
        self.assertEqual(len(document["coordinates"]), 2)

    def test_old_route_without_driver_settings_is_still_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old_route.json"
            path.write_text('{"coordinates": [], "segments": []}', encoding="utf-8")
            self.assertIsNone(load_settings_from_route(path))

    def test_invalid_embedded_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.json"
            path.write_text(
                json.dumps(
                    {
                        "coordinates": [],
                        SIMULATION_SETTINGS_KEY: {
                            "schema_version": 999,
                            "active_driver": {"parameters": {}},
                            "drivers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Version"):
                load_settings_from_route(path)


if __name__ == "__main__":
    unittest.main()
