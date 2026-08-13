from __future__ import annotations

from PySide6.QtCore import QObject

from .app_entry import CompleteApplicationWindow, main


def _hide_only_manual_road_data_button(self: CompleteApplicationWindow) -> None:
    """Keep automatic dataset selection, but preserve normal local route calculation."""
    route_window = getattr(self, "route_window", None)
    if route_window is None:
        return
    for item in route_window.findChildren(QObject):
        try:
            text = str(item.property("text") or "").strip()
        except Exception:
            continue
        if text != "Straßendaten wählen":
            continue
        item.setProperty("visible", False)
        item.setProperty("enabled", False)
        self.manual_road_data_button_hidden = True


# Keep the automatic dataset selection, but show the normal local route button.
CompleteApplicationWindow._hide_manual_road_data_button = _hide_only_manual_road_data_button


if __name__ == "__main__":
    raise SystemExit(main())
