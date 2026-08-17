from __future__ import annotations

from pathlib import Path
import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QGroupBox, QTextBrowser, QWidget

from qt_route_selector.app_entry import _install_persistent_simulation_window


IntegratedSpeedProfileWindow = _install_persistent_simulation_window()


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

    @staticmethod
    def _ancestor_group(widget: QWidget) -> QGroupBox | None:
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QGroupBox):
                return parent
            parent = parent.parentWidget()
        return None

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

    def test_overshoot_controls_live_in_curves_and_seed_is_not_shown_in_noise(self) -> None:
        window = self.make_window()
        try:
            for key in (
                "use_post_curve_overshoot",
                "post_curve_overshoot_kmh",
                "post_curve_overshoot_probability_pct",
                "post_curve_overshoot_distance_m",
            ):
                group = self._ancestor_group(window._control_widgets[key])
                self.assertIsNotNone(group, key)
                self.assertEqual(group.title(), "Kurven", key)

            seed = window._control_widgets["simulation_seed"]
            self.assertTrue(seed.isHidden())
            form, row = window._form_containing(window, seed)
            self.assertIsNone(form)
            self.assertEqual(row, -1)
        finally:
            window.close()
            self.app.processEvents()

    def test_boolean_controls_have_visible_state_text_and_larger_click_target(self) -> None:
        window = self.make_window()
        try:
            checkbox = window._control_widgets["apply_curve_speed"]
            self.assertIsInstance(checkbox, QCheckBox)
            self.assertGreaterEqual(checkbox.minimumWidth(), 72)
            self.assertEqual(checkbox.text(), "Ein" if checkbox.isChecked() else "Aus")

            checkbox.setChecked(False)
            self.app.processEvents()
            self.assertEqual(checkbox.text(), "Aus")
            checkbox.setChecked(True)
            self.app.processEvents()
            self.assertEqual(checkbox.text(), "Ein")
        finally:
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
