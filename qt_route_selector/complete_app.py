from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

try:
    from .complete_app_base import *  # noqa: F401,F403
    from .complete_app_base import CompleteApplicationWindow as _BaseWindow
except ImportError:
    from complete_app_base import *  # type: ignore  # noqa: F401,F403
    from complete_app_base import CompleteApplicationWindow as _BaseWindow


class CompleteApplicationWindow(_BaseWindow):
    """Complete app with a compact automatic-first routing workflow."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stabilize_qml_backend_lifetimes()
        self.setMinimumSize(920, 640)
        if hasattr(self, "route_container"):
            self.route_container.setMinimumSize(640, 420)
        self._hide_manual_road_data_button()

    def _stabilize_qml_backend_lifetimes(self) -> None:
        """Keep context objects alive until the QQmlApplicationEngine is torn down.

        Without QObject ownership, Python attribute destruction during application
        shutdown can release a context object before QML has finished evaluating
        its final bindings. On Windows this showed up as repeated
        ``Cannot read property ... of null`` messages from main.qml.
        """
        engine = getattr(self, "qml_engine", None)
        if engine is None:
            return
        for obj in (
            getattr(self, "route_selector", None),
            getattr(self, "route_point_model", None),
            getattr(self, "traffic_signal_model", None),
        ):
            if isinstance(obj, QObject) and obj.parent() is None:
                obj.setParent(engine)

    def _build_route_page(self) -> QWidget:
        """One compact status card; region and data selection are automatic."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(6, 6, 6, 6)
        page_layout.setSpacing(6)

        data_group = QGroupBox("Daten für diese Route")
        data_group.setStyleSheet(
            "QGroupBox { font-weight:600; border:1px solid palette(midlight); "
            "border-radius:8px; margin-top:8px; padding-top:8px; }"
        )
        group_layout = QVBoxLayout(data_group)
        group_layout.setContentsMargins(12, 12, 12, 9)
        group_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        region_caption = QLabel("Gebiet:")
        region_caption.setStyleSheet("font-weight:600;")
        header.addWidget(region_caption)
        self.detected_region_label = QLabel("Noch nicht bestimmt – Start und Ziel anklicken")
        self.detected_region_label.setStyleSheet("font-weight:600;")
        self.detected_region_label.setWordWrap(True)
        header.addWidget(self.detected_region_label, 1)
        group_layout.addLayout(header)

        self.data_status = QLabel(
            "Start und Ziel setzen. Die App erkennt das passende Gebiet automatisch und verwendet "
            "vorhandene Routing- und Höhendaten oder bereitet fehlende Daten selbst vor."
        )
        self.data_status.setWordWrap(True)
        self.data_status.setStyleSheet("color:palette(mid);")
        group_layout.addWidget(self.data_status)

        self.data_progress = QProgressBar()
        self.data_progress.setRange(0, 100)
        self.data_progress.setValue(0)
        self.data_progress.setTextVisible(False)
        self.data_progress.setMaximumHeight(10)
        group_layout.addWidget(self.data_progress)

        self.route_data_group = data_group
        page_layout.addWidget(data_group)
        page_layout.addWidget(self.route_container, 1)
        return page

    def _hide_manual_road_data_button(self) -> None:
        """Remove the old manual road-file action from the normal user workflow."""
        route_window = getattr(self, "route_window", None)
        if route_window is None:
            return
        for item in route_window.findChildren(QObject):
            try:
                text = item.property("text")
            except Exception:
                continue
            if str(text or "").strip() == "Straßendaten wählen":
                item.setProperty("visible", False)
                item.setProperty("enabled", False)
                self.manual_road_data_button_hidden = True

    @staticmethod
    def _loading_placeholder(title: str, detail: str) -> tuple[QWidget, QLabel, QProgressBar]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(f"{title}\n\n{detail}")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setMaximumWidth(420)
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addWidget(progress, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return page, label, progress

    def _build_simulation_placeholder(self) -> QWidget:
        page, label, progress = self._loading_placeholder(
            "Geschwindigkeitsverlauf wird erst bei Bedarf geladen.",
            "Beim Öffnen werden Simulation, technische Vorschauen und Kartenansicht initialisiert.",
        )
        self.simulation_loading_label = label
        self.simulation_loading_bar = progress
        return page

    def _build_coverage_placeholder(self) -> QWidget:
        page, label, progress = self._loading_placeholder(
            "Datenabdeckung wird erst bei Bedarf geladen.",
            "Beim Öffnen wird die lokale Kartenabdeckung aus POLY, PBF und GPKG aufgebaut.",
        )
        self.coverage_loading_label = label
        self.coverage_loading_bar = progress
        return page

    def _ensure_simulation_created(self) -> None:
        if hasattr(self, "simulation_loading_label"):
            self.simulation_loading_label.setText(
                "Geschwindigkeitsverlauf wird geladen …\n\nPlots, Vergleichswerkzeuge und Karte werden initialisiert."
            )
        QApplication.processEvents()
        super()._ensure_simulation_created()

    def _ensure_coverage_created(self) -> None:
        if hasattr(self, "coverage_loading_label"):
            self.coverage_loading_label.setText(
                "Datenabdeckung wird geladen …\n\nLokale Gebietsgrenzen und Dateistatus werden aufbereitet."
            )
        QApplication.processEvents()
        super()._ensure_coverage_created()


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
