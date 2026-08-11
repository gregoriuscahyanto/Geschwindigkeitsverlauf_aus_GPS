from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

try:
    from ._internal.simulation_layers import integrated_speed_profile as _base_layer
    from ._internal.simulation_layers.integrated_speed_profile import _osm_only_event_positions
    from ._internal.simulation_layers.integrated_speed_profile_v16 import (
        IntegratedSpeedProfileWindow as _CurrentWindow,
    )
    from .matlab_table_loader import write_matlab_table_loader
    from .runtime_paths import exports_dir
except ImportError:
    from _internal.simulation_layers import integrated_speed_profile as _base_layer
    from _internal.simulation_layers.integrated_speed_profile import _osm_only_event_positions
    from _internal.simulation_layers.integrated_speed_profile_v16 import (
        IntegratedSpeedProfileWindow as _CurrentWindow,
    )
    from matlab_table_loader import write_matlab_table_loader
    from runtime_paths import exports_dir

# The implementation layers live below _internal, while QML resources remain
# next to the public application modules.
_base_layer.APP_DIR = Path(__file__).resolve().parent


class IntegratedSpeedProfileWindow(_CurrentWindow):
    """Public simulation window with the compact current application shell."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._merge_summary_cards()
        self._configure_mat_export_ui()

    def _merge_summary_cards(self) -> None:
        """Show route statistics and energy in one responsive summary card."""
        outer = self.centralWidget()
        if not isinstance(outer, QSplitter) or outer.count() < 2:
            return
        plot_root = outer.widget(1)
        layout = plot_root.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        summary = getattr(self, "summary_label", None)
        energy = getattr(self, "energy_header_label", None)
        if not isinstance(summary, QLabel) or not isinstance(energy, QLabel):
            return
        if getattr(self, "overview_card", None) is not None:
            return

        positions = [index for index in (layout.indexOf(summary), layout.indexOf(energy)) if index >= 0]
        insert_at = min(positions) if positions else 0
        layout.removeWidget(summary)
        layout.removeWidget(energy)

        card = QFrame(plot_root)
        card.setObjectName("overviewCard")
        card.setStyleSheet(
            "QFrame#overviewCard { background:palette(base); border:1px solid palette(midlight); "
            "border-radius:10px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 9, 14, 9)
        card_layout.setSpacing(5)

        for label in (summary, energy):
            label.setParent(card)
            label.setStyleSheet("QLabel { border:0; background:transparent; padding:0; }")
            label.setWordWrap(True)
            card_layout.addWidget(label)

        layout.insertWidget(insert_at, card)
        self.overview_card = card

    def _configure_mat_export_ui(self) -> None:
        """Make the normal export action explicitly describe the MAT output."""
        for button in self.findChildren(QPushButton):
            if "exportieren" in button.text().lower():
                button.setText("MAT exportieren")
                button.setToolTip(
                    "Vollständigen Simulationsdatensatz als MATLAB-.mat exportieren, "
                    "inklusive Route, Kurvenradius, Höhenprofil, Leistung und Energie. "
                    "Zusätzlich wird ein MATLAB-Loader für table/timetable erzeugt."
                )

    @staticmethod
    def _mat_exporter():
        """Load the MAT writer only when the user actually exports.

        This keeps the simulation usable in an existing venv that has not yet
        been refreshed with the new SciPy dependency.
        """
        try:
            from .mat_export import export_matlab_simulation
        except ImportError as package_error:
            try:
                from mat_export import export_matlab_simulation
            except ImportError:
                raise RuntimeError(
                    "Für den MATLAB-Export fehlt SciPy in der aktuellen .venv.\n\n"
                    "Bitte im Projektordner einmal ausführen:\n"
                    ".\\scripts\\setup_windows.ps1\n\n"
                    "Danach die Anwendung neu starten."
                ) from package_error
        return export_matlab_simulation

    def export_result(self) -> None:
        """Export the complete current simulation plus a MATLAB table loader."""
        if self._result is None:
            QMessageBox.information(
                self,
                "Keine Simulation",
                "Zuerst eine Route laden und simulieren.",
            )
            return

        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Vollständige Simulation als MATLAB-Datei exportieren",
            str(exports_dir() / "speed_profile_result.mat"),
            "MATLAB-Datei (*.mat)",
        )
        if not selected:
            return

        path = Path(selected)
        if path.suffix.lower() != ".mat":
            path = path.with_suffix(".mat")

        try:
            export_matlab_simulation = self._mat_exporter()
            spatial_distance = np.asarray(
                self._result.get("distance", {}).get("distance_m", []),
                dtype=float,
            )
            elevation = self._spatial_elevation(spatial_distance)
            comparison = {
                "names": getattr(self, "_comparison_names", []),
                "configs": getattr(self, "_comparison_configs", []),
                "results": getattr(self, "_comparison_results", []),
                "resistance": getattr(self, "_comparison_resistance", []),
            }
            mat_path = export_matlab_simulation(
                self._result,
                path,
                route=self._route or {},
                parameters=self.parameters(),
                power_data=getattr(self, "_resistance_time_data", None),
                elevation_m=elevation,
                source_route=self._route_path,
                source_dem=getattr(self, "_dem_path", None),
                comparison=comparison,
            )
            loader_path = write_matlab_table_loader(mat_path)
        except Exception as exc:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(exc))
            return

        self.statusBar().showMessage(
            f"MATLAB-Export gespeichert: {mat_path.name}; Loader: {loader_path.name}"
        )
        QMessageBox.information(
            self,
            "MATLAB-Export fertig",
            f"Gespeichert:\n{mat_path}\n\n"
            f"MATLAB-Loader:\n{loader_path}\n\n"
            f"In MATLAB einfach '{loader_path.stem}' ausführen. Danach stehen "
            "distanceTable, driveTimetable, powerTimetable und trafficLightTable bereit.",
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


__all__ = ["IntegratedSpeedProfileWindow", "_osm_only_event_positions", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
