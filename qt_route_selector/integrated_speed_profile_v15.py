from __future__ import annotations

from html import escape
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from .integrated_speed_profile_v14 import IntegratedSpeedProfileWindow as _V14Window
except ImportError:
    from integrated_speed_profile_v14 import IntegratedSpeedProfileWindow as _V14Window


class IntegratedSpeedProfileWindow(_V14Window):
    """V15: lightweight, non-modal parameter help popovers anchored to each (i)."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._parameter_help_popup: QFrame | None = None
        self._parameter_help_key: str | None = None
        super().__init__(route_path)

    def _close_parameter_help_popup(self) -> None:
        popup = self._parameter_help_popup
        if popup is not None:
            self._parameter_help_popup = None
            self._parameter_help_key = None
            popup.close()

    def _show_parameter_help(self, key: str) -> None:
        # Clicking the same info icon again acts as a natural toggle.
        if (
            self._parameter_help_popup is not None
            and self._parameter_help_popup.isVisible()
            and self._parameter_help_key == key
        ):
            self._close_parameter_help_popup()
            return

        self._close_parameter_help_popup()

        description, influence, examples = self._help_entry(key)
        current, allowed = self._current_and_range(key)
        title = self._parameter_title(key)

        sender = self.sender()
        anchor = sender if isinstance(sender, QWidget) else self

        popup = QFrame(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        popup.setObjectName("parameterHelpPopover")
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        popup.setStyleSheet(
            "QFrame#parameterHelpPopover {"
            " background: palette(base);"
            " border: 1px solid palette(mid);"
            " border-radius: 10px;"
            "}"
            "QTextBrowser {"
            " border: 0;"
            " background: transparent;"
            " padding: 0;"
            "}"
        )

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(0)

        browser = QTextBrowser(popup)
        browser.setOpenExternalLinks(False)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        browser.setHtml(
            "<div style='line-height:1.28'>"
            f"<div style='font-size:12pt;font-weight:700;margin-bottom:8px'>{escape(title)}</div>"
            "<div style='font-weight:600;margin-top:4px'>Was ist das?</div>"
            f"<div>{escape(description)}</div>"
            "<div style='font-weight:600;margin-top:9px'>Einfluss</div>"
            f"<div>{escape(influence)}</div>"
            "<div style='font-weight:600;margin-top:9px'>Beispielwerte</div>"
            f"<div>{escape(examples)}</div>"
            "<div style='font-weight:600;margin-top:10px'>Aktuell</div>"
            f"<div>{escape(current)}</div>"
            f"<div style='color:gray;margin-top:2px'>{escape(allowed)}</div>"
            "</div>"
        )
        layout.addWidget(browser)

        anchor_right = anchor.mapToGlobal(QPoint(anchor.width(), 0))
        anchor_left = anchor.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(anchor_right) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else self.geometry()

        # Popovers float above the responsive layout. Their width adapts to the
        # available screen rather than changing the sidebar geometry.
        width = max(280, min(420, int(available.width() * 0.30)))
        popup.setFixedWidth(width)
        browser.document().setTextWidth(max(220, width - 32))
        document_height = int(browser.document().size().height())
        browser.setFixedHeight(
            max(150, min(document_height + 12, int(available.height() * 0.62)))
        )
        popup.adjustSize()

        margin = 8
        x = anchor_right.x() + margin
        if x + popup.width() > available.right() - margin:
            x = anchor_left.x() - popup.width() - margin
        x = max(available.left() + margin, min(x, available.right() - popup.width() - margin))

        y = anchor_left.y() - 4
        if y + popup.height() > available.bottom() - margin:
            y = available.bottom() - popup.height() - margin
        y = max(available.top() + margin, y)

        popup.move(x, y)
        self._parameter_help_popup = popup
        self._parameter_help_key = key

        def clear_reference(*_args) -> None:
            if self._parameter_help_popup is popup:
                self._parameter_help_popup = None
                self._parameter_help_key = None

        popup.destroyed.connect(clear_reference)
        popup.show()
        popup.raise_()
        popup.setFocus(Qt.FocusReason.PopupFocusReason)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
