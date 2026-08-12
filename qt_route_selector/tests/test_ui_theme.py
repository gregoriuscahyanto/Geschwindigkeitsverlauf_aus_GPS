from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui_theme import apply_readable_light_theme  # noqa: E402


class UiThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_light_palette_has_readable_contrast(self) -> None:
        apply_readable_light_theme(self.app)
        palette = self.app.palette()
        window = palette.color(QPalette.ColorRole.Window)
        text = palette.color(QPalette.ColorRole.WindowText)
        base = palette.color(QPalette.ColorRole.Base)

        self.assertGreater(window.lightness(), 200)
        self.assertGreater(base.lightness(), 240)
        self.assertLess(text.lightness(), 80)
        self.assertGreater(window.lightness() - text.lightness(), 120)


if __name__ == "__main__":
    unittest.main()
