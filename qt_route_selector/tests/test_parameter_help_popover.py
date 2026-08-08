from __future__ import annotations

from pathlib import Path
import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QTextBrowser

from qt_route_selector.integrated_speed_profile_v16 import IntegratedSpeedProfileWindow


class ParameterHelpPopoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_info_button_opens_anchored_non_modal_popover(self) -> None:
        window = IntegratedSpeedProfileWindow(Path("__missing_route_for_help_test__.json"))
        window.resize(1200, 800)
        window.show()
        self.app.processEvents()
        try:
            button = window.parameter_info_buttons.get("Kp")
            self.assertIsNotNone(button)

            button.click()
            self.app.processEvents()

            popup = window._parameter_help_popup
            self.assertIsInstance(popup, QFrame)
            self.assertTrue(popup.isVisible())
            self.assertEqual(window._parameter_help_key, "Kp")
            self.assertEqual(popup.windowModality(), Qt.WindowModality.NonModal)
            self.assertTrue(bool(popup.windowFlags() & Qt.WindowType.Popup))

            browser = popup.findChild(QTextBrowser)
            self.assertIsNotNone(browser)
            text = browser.toPlainText()
            for expected in ("Was ist das?", "Einfluss", "Beispielwerte", "Aktuell"):
                self.assertIn(expected, text)

            # V16 keeps the QML bridge alive until the map widget itself is torn down.
            self.assertIs(window.map_bridge.parent(), window.map_widget)

            # A second click on the same (i) toggles the lightweight help off.
            button.click()
            self.app.processEvents()
            self.assertIsNone(window._parameter_help_popup)
        finally:
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
