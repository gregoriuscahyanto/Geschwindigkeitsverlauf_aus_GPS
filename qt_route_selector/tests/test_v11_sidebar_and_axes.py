from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication, QFormLayout, QGridLayout, QLayout, QToolButton

from qt_route_selector.integrated_speed_profile_v11 import IntegratedSpeedProfileWindow


class V11SidebarAndAxisTests(unittest.TestCase):
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

    def test_sidebar_shrinks_without_hidden_horizontal_overflow(self) -> None:
        scroll = self.window.parameter_scroll_area
        content = scroll.widget()
        self.assertIsNotNone(content)
        self.assertEqual(
            content.layout().sizeConstraint(),
            QLayout.SizeConstraint.SetNoConstraint,
        )
        self.assertEqual(content.minimumWidth(), 0)
        self.assertEqual(scroll.horizontalScrollBarPolicy().name, "ScrollBarAlwaysOff")

        self.window._apply_sidebar_form_mode(430)
        forms = content.findChildren(QFormLayout)
        self.assertTrue(forms)
        self.assertTrue(
            all(
                form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows
                for form in forms
            )
        )

        route_grid = self.window._route_grid
        self.assertIsInstance(route_grid, QGridLayout)
        status_index = route_grid.indexOf(self.window.dem_status_label)
        _row, column, _row_span, column_span = route_grid.getItemPosition(status_index)
        self.assertEqual(column, 0)
        self.assertEqual(column_span, 3)
        self.assertEqual(self.window.route_path_label.text(), "missing-route.json")
        self.assertIn("missing-route.json", self.window.route_path_label.toolTip())

        self.window._apply_sidebar_form_mode(700)
        self.assertTrue(
            all(
                form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapLongRows
                for form in forms
            )
        )

    def test_every_signal_and_visible_axis_has_an_explicit_axis_badge(self) -> None:
        groups = {"speed", "acceleration", "elevation", "power"}
        self.window._set_combined_axis_visibility(groups)

        expected = {
            "speed": "[v]",
            "acceleration": "[a]",
            "elevation": "[h]",
            "power": "[P]",
        }
        for group, badge in expected.items():
            axis = self.window._combined_axes[group]
            self.assertTrue(axis.isVisible())
            self.assertEqual(axis.labelText, badge)

        guide = self.window.axis_guide_label.text()
        for badge in expected.values():
            self.assertIn(badge, guide)

        self.assertTrue(self.window.signal_actions["simulated"].text().startswith("[v]"))
        self.assertTrue(self.window.signal_actions["acceleration"].text().startswith("[a]"))
        self.assertTrue(self.window.signal_actions["elevation"].text().startswith("[h]"))
        self.assertTrue(self.window.signal_actions["power_total"].text().startswith("[P]"))

        self.window._clear_combined_curves()
        self.window._add_combined_curve(
            "test-acceleration",
            "Test",
            "acceleration",
            np.asarray([0.0, 1.0]),
            np.asarray([0.0, 1.0]),
            (40, 180, 125),
            1.7,
        )
        self.window._refresh_combined_legend()
        buttons = self.window.combined_legend_bar.findChildren(QToolButton)
        self.assertTrue(any(button.text().startswith("[a]") for button in buttons))


if __name__ == "__main__":
    unittest.main()
