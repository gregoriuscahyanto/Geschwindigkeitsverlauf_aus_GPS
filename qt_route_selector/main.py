from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


class RouteSelector(QObject):
    selectionChanged = Signal(dict)
    statusChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.points = []

    @staticmethod
    def bbox(a, b):
        distance = math.hypot((a[0]-b[0])*111000, (a[1]-b[1])*70000)
        margin = max(5000, distance * 0.2)
        lat_margin = margin / 111000
        lon_margin = margin / 70000
        return {
            "south": min(a[0], b[0]) - lat_margin,
            "north": max(a[0], b[0]) + lat_margin,
            "west": min(a[1], b[1]) - lon_margin,
            "east": max(a[1], b[1]) + lon_margin,
        }

    @Slot(float, float)
    def selectPoint(self, lat, lon):
        if len(self.points) >= 2:
            self.points.clear()
        self.points.append((lat, lon))
        data = {"points": self.points}
        if len(self.points) == 2:
            data["bbox"] = self.bbox(*self.points)
            Path("selected_region.json").write_text(
                json.dumps(data, indent=2),
                encoding="utf-8",
            )
            self.statusChanged.emit("Region gespeichert")
        else:
            self.statusChanged.emit("Zielpunkt auswählen")
        self.selectionChanged.emit(data)


def main():
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    selector = RouteSelector()
    engine.rootContext().setContextProperty("routeSelector", selector)
    engine.load(Path(__file__).with_name("main.qml"))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
