from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QApplication

from qt_route_selector.complete_app import CompleteApplicationWindow


class CompleteApplicationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_three_tabs_and_lazy_current_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = Path(tmp) / "runtime"
            with patch.dict(os.environ, {"GPS_ROUTENPLANER_HOME": str(runtime_root)}):
                window = CompleteApplicationWindow(force_offline=True)
                window.resize(1280, 800)
                window.show()
                self.app.processEvents()
                try:
                    self.assertEqual(window.data_root, runtime_root.resolve() / "data")
                    self.assertEqual(window.tabs.count(), 3)
                    self.assertIsNone(window.speed_profile)
                    self.assertIsNone(window.coverage_tab)

                    window.tabs.setCurrentIndex(1)
                    window._ensure_simulation_created()
                    self.app.processEvents()
                    simulation = window.speed_profile
                    self.assertIsNotNone(simulation)
                    self.assertEqual(
                        Path(simulation._route_path),
                        runtime_root.resolve() / "state" / "route_result.json",
                    )
                    self.assertTrue(hasattr(simulation, "overview_card"))
                    self.assertIs(simulation.summary_label.parentWidget(), simulation.overview_card)
                    self.assertIs(simulation.energy_header_label.parentWidget(), simulation.overview_card)
                    self.assertNotEqual(simulation.map_widget.status(), QQuickWidget.Status.Error)
                finally:
                    window.close()
                    self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
