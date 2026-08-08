from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from qt_route_selector.integrated_speed_profile_v9 import IntegratedSpeedProfileWindow
from qt_route_selector.main import RoutePointModel, RouteSelector, TrafficSignalModel


class V9UiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        route_path = Path(self.temp_dir.name) / "missing-route.json"
        self.window = IntegratedSpeedProfileWindow(route_path)
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def test_zero_lines_are_compatible_and_all_y_axes_can_be_visible(self) -> None:
        self.window._add_zero_line("acceleration")
        self.window._add_zero_line("power")
        self.window._set_combined_axis_visibility(
            {"speed", "acceleration", "elevation", "power"}
        )
        self.assertTrue(self.window._combined_axes["speed"].isVisible())
        self.assertTrue(self.window._combined_axes["acceleration"].isVisible())
        self.assertTrue(self.window._combined_axes["elevation"].isVisible())
        self.assertTrue(self.window._combined_axes["power"].isVisible())

    def test_parameter_sidebar_has_room_and_toolbar_uses_one_style(self) -> None:
        pane = self.window._parameter_pane
        self.assertIsNotNone(pane)
        self.assertGreaterEqual(pane.minimumWidth(), 450)
        self.assertGreaterEqual(pane.maximumWidth(), 520)

        toolbar = self.window.axis_combo.parentWidget()
        self.assertIsNotNone(toolbar)
        self.assertIn("border-radius: 7px", toolbar.styleSheet())
        self.assertEqual(self.window.sidebar_toggle_button.styleSheet(), "")
        self.assertEqual(self.window.signals_button.styleSheet(), "")


class RouteMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_metadata_contains_creation_time_and_route_endpoints(self) -> None:
        selector = RouteSelector(RoutePointModel(), TrafficSignalModel())
        selector.points = [(48.0, 9.0), (48.5, 10.0), (49.0, 11.0)]
        metadata = selector._file_metadata_payload()

        self.assertIn("created_at", metadata)
        self.assertIn("created_date", metadata)
        self.assertIn("created_time", metadata)
        self.assertEqual(metadata["start_gps"], {"latitude": 48.0, "longitude": 9.0})
        self.assertEqual(metadata["end_gps"], {"latitude": 49.0, "longitude": 11.0})
        self.assertEqual(metadata["waypoint_count"], 1)


if __name__ == "__main__":
    unittest.main()
