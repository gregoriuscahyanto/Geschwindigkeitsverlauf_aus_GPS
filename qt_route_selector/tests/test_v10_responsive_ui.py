from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFormLayout, QSplitter

from qt_route_selector.integrated_speed_profile_v10 import IntegratedSpeedProfileWindow


class ResponsiveSimulationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        route_path = Path(self.temp_dir.name) / "missing-route.json"
        self.window = IntegratedSpeedProfileWindow(route_path)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def test_simple_mode_starts_with_three_clear_signals(self) -> None:
        active = {
            key for key, action in self.window.signal_actions.items() if action.isChecked()
        }
        self.assertEqual(active, {"simulated", "road_limit", "elevation"})

    def test_parameter_pane_has_no_fixed_width_and_forms_wrap(self) -> None:
        pane = self.window._parameter_pane
        self.assertIsNotNone(pane)
        self.assertEqual(pane.minimumWidth(), 0)
        self.assertGreater(pane.maximumWidth(), 1_000_000)

        forms = self.window.parameter_scroll_area.widget().findChildren(QFormLayout)
        self.assertTrue(forms)
        self.assertTrue(
            all(
                form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapLongRows
                for form in forms
            )
        )

    def test_map_moves_below_plot_on_narrow_windows(self) -> None:
        splitter = self.window.plot_map_splitter
        self.assertIsInstance(splitter, QSplitter)

        self.window.resize(1760, 900)
        self.app.processEvents()
        self.window._apply_responsive_layout(force=True)
        self.assertEqual(self.window._responsive_band, "wide")
        self.assertEqual(splitter.orientation(), Qt.Orientation.Horizontal)

        self.window.resize(1180, 800)
        self.app.processEvents()
        self.window._apply_responsive_layout(force=True)
        self.assertEqual(self.window._responsive_band, "compact")
        self.assertEqual(splitter.orientation(), Qt.Orientation.Vertical)

    def test_sidebar_toggle_still_works_in_responsive_mode(self) -> None:
        self.window.sidebar_toggle_button.setChecked(False)
        self.app.processEvents()
        self.window._apply_responsive_layout(force=True)
        self.assertTrue(self.window._parameter_pane.isHidden())

        self.window.sidebar_toggle_button.setChecked(True)
        self.app.processEvents()
        self.window._apply_responsive_layout(force=True)
        self.assertFalse(self.window._parameter_pane.isHidden())


if __name__ == "__main__":
    unittest.main()
