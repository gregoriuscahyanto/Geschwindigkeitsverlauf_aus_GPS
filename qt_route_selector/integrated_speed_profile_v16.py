from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLabel

try:
    from .integrated_speed_profile_v15 import IntegratedSpeedProfileWindow as _V15Window
except ImportError:
    from integrated_speed_profile_v15 import IntegratedSpeedProfileWindow as _V15Window


class IntegratedSpeedProfileWindow(_V15Window):
    """V16: clean info-link wiring and stable simulation-QML backend lifetime."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._stabilize_simulation_qml_lifetime()

    def _install_elevation_smoothing_info_link(self) -> None:
        """Connect the inline help link exactly once without blind disconnect()."""
        label = getattr(self, "_smoothing_title_label", None)
        if not isinstance(label, QLabel):
            return
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(False)
        label.setText(
            "Höhenprofil-Glättung&nbsp;&nbsp;"
            "<a href='info' style='text-decoration:none'>(i)</a>"
        )
        label.setToolTip("Kurze technische Erklärung und Beispielwerte anzeigen")
        if not bool(label.property("parameterHelpConnected")):
            label.linkActivated.connect(
                lambda _link: self._show_parameter_help("elevation_smoothing")
            )
            label.setProperty("parameterHelpConnected", True)

    def _stabilize_simulation_qml_lifetime(self) -> None:
        """Keep the QML context bridge alive through QQuickWidget teardown."""
        bridge = getattr(self, "map_bridge", None)
        widget = getattr(self, "map_widget", None)
        if bridge is None or widget is None:
            return
        if bridge.parent() is None:
            bridge.setParent(widget)
        widget.rootContext().setContextProperty("simulationMapBridge", bridge)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
