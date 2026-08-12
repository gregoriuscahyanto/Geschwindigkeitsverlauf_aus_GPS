from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_readable_light_theme(app: QApplication) -> None:
    """Use a stable light palette independent of the Windows enterprise theme.

    Some managed Windows installations force a dark/high-contrast application
    palette. Parts of the existing Qt/QML UI use palette-based and custom
    styling together, which can otherwise result in dark text on dark surfaces.
    A fixed Fusion/light palette keeps the technical UI reproducibly readable.
    """

    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.Text, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.Button, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(180, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, QColor(0, 102, 204))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(110, 110, 110))

    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(125, 125, 125),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(125, 125, 125),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(125, 125, 125),
    )

    app.setPalette(palette)
