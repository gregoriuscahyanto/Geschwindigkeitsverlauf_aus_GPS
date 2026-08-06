from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import QApplication

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from live_speed_profile import LiveSpeedProfileWindow  # noqa: E402
from main import RoutePointModel, RouteSelector, TrafficSignalModel  # noqa: E402
from offline_map import OfflineMapItem  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GPS Route and Live Speed Profile")
    app.setOrganizationName("GPSDrivingSimulation")

    qmlRegisterType(OfflineMapItem, "OfflineMap", 1, 0, "OfflineMapItem")

    engine = QQmlApplicationEngine()
    route_point_model = RoutePointModel()
    traffic_signal_model = TrafficSignalModel()
    selector = RouteSelector(route_point_model, traffic_signal_model)
    engine.rootContext().setContextProperty("routeSelector", selector)
    engine.rootContext().setContextProperty("routePointModel", route_point_model)
    engine.rootContext().setContextProperty("trafficSignalModel", traffic_signal_model)
    engine.load(str(APP_DIR / "main.qml"))
    if not engine.rootObjects():
        return 1

    simulator = LiveSpeedProfileWindow(Path.cwd() / "route_result.json")
    simulator.show()

    def route_changed(points: list[dict[str, Any]]) -> None:
        if len(points) > 1:
            QTimer.singleShot(180, lambda: simulator.reload_route(silent=True))

    # route_result.json is written before routeChanged is emitted. A short
    # delay avoids racing the file system on slower enterprise laptops.
    selector.routeChanged.connect(route_changed)

    # Keep Python references for the full application lifetime.
    app._qml_engine = engine  # type: ignore[attr-defined]
    app._route_selector = selector  # type: ignore[attr-defined]
    app._speed_simulator = simulator  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
