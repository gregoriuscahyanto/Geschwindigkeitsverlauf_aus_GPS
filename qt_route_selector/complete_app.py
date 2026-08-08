from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

try:
    from .complete_app_base import *  # noqa: F401,F403
    from .complete_app_base import CompleteApplicationWindow as _BaseWindow
except ImportError:
    from complete_app_base import *  # type: ignore  # noqa: F401,F403
    from complete_app_base import CompleteApplicationWindow as _BaseWindow


class CompleteApplicationWindow(_BaseWindow):
    """Complete app with visible feedback while heavy lazy tabs are initialized."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setMinimumSize(920, 640)
        if hasattr(self, "route_container"):
            self.route_container.setMinimumSize(640, 420)

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
            "Beim Öffnen werden Simulation, technische Mini-Plots und Kartenansicht initialisiert.",
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
