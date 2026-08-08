from __future__ import annotations

from pathlib import Path
import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QTextBrowser

from qt_route_selector.integrated_speed_profile import IntegratedSpeedProfileWindow


class CurrentSimulationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self) -> IntegratedSpeedProfileWindow:
        window = IntegratedSpeedProfileWindow(Path("__missing_route_for_ui_test__.json"))
        window.resize(1280, 800)
        window.show()
        self.app.processEvents()
        return window

    def test_current_shell_is_compact_and_responsive(self) -> None:
        window = self.make_window()
        try:
            self.assertIs(window.summary_label.parentWidget(), window.overview_card)
            self.assertIs(window.energy_header_label.parentWidget(), window.overview_card)
            self.assertEqual(window.plot_mode_combo.currentData(), "combined")
            active = {key for key, action in window.signal_actions.items() if action.isChecked()}
            self.assertEqual(active, {"simulated", "road_limit", "elevation"})
            self.assertEqual(window._parameter_pane.minimumWidth(), 0)
            self.assertGreater(window._parameter_pane.maximumWidth(), 1_000_000)
            self.assertEqual(set(window._combined_views), {"speed", "acceleration", "elevation", "power"})
        finally:
            window.close()
            self.app.processEvents()

    def test_parameter_help_is_anchored_non_modal_popover(self) -> None:
        window = self.make_window()
        try:
            button = window.parameter_info_buttons["Kp"]
            button.click()
            self.app.processEvents()
            popup = window._parameter_help_popup
            self.assertIsInstance(popup, QFrame)
            self.assertEqual(popup.windowModality(), Qt.WindowModality.NonModal)
            self.assertTrue(bool(popup.windowFlags() & Qt.WindowType.Popup))
            browser = popup.findChild(QTextBrowser)
            self.assertIsNotNone(browser)
            text = browser.toPlainText()
            for expected in ("Was ist das?", "Einfluss", "Beispielwerte", "Aktuell"):
                self.assertIn(expected, text)
        finally:
            window.close()
            self.app.processEvents()

    def test_manual_parameter_change_is_visible_and_resettable(self) -> None:
        window = self.make_window()
        try:
            kp = window._control_widgets["Kp"]
            baseline = float(kp.value())
            kp.setValue(baseline + 0.1)
            self.app.processEvents()
            self.assertIn("Änderung", window.parameter_change_label.text())
            self.assertTrue(window.parameter_reset_button.isVisible())
            window.parameter_reset_button.click()
            self.app.processEvents()
            self.assertAlmostEqual(float(kp.value()), baseline, places=6)
            self.assertIn("Preset unverändert", window.parameter_change_label.text())
        finally:
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
