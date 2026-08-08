from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox

from qt_route_selector.integrated_speed_profile_v13 import IntegratedSpeedProfileWindow
from qt_route_selector.technical_previews_v2 import FriendlyTechnicalPreviews


class ParameterFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_changes_are_visible_and_inactive_controls_are_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = IntegratedSpeedProfileWindow(Path(directory) / "missing-route.json")
            self.app.processEvents()

            self.assertIsInstance(window.preview_controller, FriendlyTechnicalPreviews)
            self.assertIn("Preset unverändert", window.parameter_change_label.text())
            self.assertFalse(window.parameter_reset_button.isVisible())

            cruise = window._control_widgets["driver_cruise_kmh"]
            self.assertIsInstance(cruise, QDoubleSpinBox)
            cruise.setValue(cruise.value() + 5.0)
            self.app.processEvents()

            self.assertIn("Änderung", window.parameter_change_label.text())
            self.assertIn("driver_cruise_kmh", window._changed_keys())
            self.assertIn("Änderung ansehen", window.preview_controller.buttons["Fahrer"].text())
            self.assertTrue(window.preview_controller.plots["Fahrer"].isHidden())

            window.preview_controller.buttons["Fahrer"].setChecked(True)
            self.app.processEvents()
            self.assertFalse(window.preview_controller.plots["Fahrer"].isHidden())

            noise_toggle = window._control_widgets["use_driver_noise"]
            self.assertIsInstance(noise_toggle, QCheckBox)
            noise_toggle.setChecked(False)
            self.app.processEvents()
            self.assertFalse(window._control_widgets["noise_std_kmh"].isEnabled())
            self.assertFalse(window._control_widgets["noise_tau_s"].isEnabled())

            window._reset_to_active_preset()
            self.app.processEvents()
            self.assertEqual(window._changed_keys(), set())
            self.assertIn("Preset unverändert", window.parameter_change_label.text())
            window.close()


if __name__ == "__main__":
    unittest.main()
