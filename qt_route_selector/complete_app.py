from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from integrated_speed_profile_v3 import IntegratedSpeedProfileWindow  # noqa: E402
from main import RoutePointModel, RouteSelector, TrafficSignalModel  # noqa: E402
from offline_map import OfflineMapItem  # noqa: E402


class CompleteApplicationWindow(QMainWindow):
    """One desktop window containing routing and live simulation as two tabs."""

    def __init__(self, *, force_offline: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("GPS-Routenplaner und Geschwindigkeitsverlauf")
        self.resize(1600, 980)
        self.setMinimumSize(1100, 720)

        qmlRegisterType(OfflineMapItem, "OfflineMap", 1, 0, "OfflineMapItem")

        self.route_point_model = RoutePointModel()
        self.traffic_signal_model = TrafficSignalModel()
        self.route_selector = RouteSelector(
            self.route_point_model,
            self.traffic_signal_model,
        )
        if force_offline:
            self.route_selector.setMapPreference("offline")

        self.qml_engine = QQmlApplicationEngine()
        self.qml_engine.rootContext().setContextProperty(
            "routeSelector", self.route_selector
        )
        self.qml_engine.rootContext().setContextProperty(
            "routePointModel", self.route_point_model
        )
        self.qml_engine.rootContext().setContextProperty(
            "trafficSignalModel", self.traffic_signal_model
        )
        self.qml_engine.load(str(APP_DIR / "main.qml"))
        roots = self.qml_engine.rootObjects()
        if not roots or not isinstance(roots[0], QWindow):
            raise RuntimeError("Die QML-Routenansicht konnte nicht eingebettet werden.")

        self.route_window = roots[0]
        self.route_window.setVisible(False)
        self.route_container = QWidget.createWindowContainer(self.route_window, self)
        self.route_container.setMinimumSize(900, 600)

        self.speed_profile = IntegratedSpeedProfileWindow(
            Path.cwd() / "route_result.json"
        )
        self.speed_profile.setWindowFlags(Qt.WindowType.Widget)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.route_container, "1 · Route und Karte")
        self.tabs.addTab(self.speed_profile, "2 · Geschwindigkeitsverlauf")
        self.setCentralWidget(self.tabs)

        self.route_selector.routeChanged.connect(self._route_changed)

    def _route_changed(self, points: list[dict[str, Any]]) -> None:
        if len(points) <= 1:
            return
        QTimer.singleShot(
            180,
            lambda: self.speed_profile.reload_route(silent=True),
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GPS Route and Live Speed Profile")
    app.setOrganizationName("GPSDrivingSimulation")
    window = CompleteApplicationWindow()
    window.show()
    app._main_window = window  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
