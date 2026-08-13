from __future__ import annotations

from PySide6.QtCore import QObject

from .complete_app import CompleteApplicationWindow, main


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


# complete_app historically hid both the manual road-data chooser and the local
# route-calculation button when GPX import was introduced. The Windows launcher
# uses ``python -m qt_route_selector``; override only that obsolete UI policy so
# users can choose either workflow: calculate from clicked points or import GPX.
CompleteApplicationWindow._hide_manual_road_data_button = _hide_only_manual_road_data_button


if __name__ == "__main__":
    raise SystemExit(main())
