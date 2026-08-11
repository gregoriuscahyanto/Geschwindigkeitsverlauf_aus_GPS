from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path
from typing import Callable

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
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
    from .matlab_native_export import convert_to_native_matlab_tables
    from .runtime_paths import exports_dir
except ImportError:
    from _internal.simulation_layers import integrated_speed_profile as _base_layer
    from _internal.simulation_layers.integrated_speed_profile import _osm_only_event_positions
    from _internal.simulation_layers.integrated_speed_profile_v16 import (
        IntegratedSpeedProfileWindow as _CurrentWindow,
    )
    from matlab_native_export import convert_to_native_matlab_tables
    from runtime_paths import exports_dir

# The implementation layers live below _internal, while QML resources remain
# next to the public application modules.
_base_layer.APP_DIR = Path(__file__).resolve().parent


class _MatExportWorker(QObject):
    """Run the potentially slow MATLAB export without blocking the Qt GUI."""

    succeeded = Signal(str)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, job: Callable[[], Path]) -> None:
        super().__init__()
        self._job = job

    @Slot()
    def run(self) -> None:
        try:
            path = self._job()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(str(path))
        finally:
            self.completed.emit()


class IntegratedSpeedProfileWindow(_CurrentWindow):
    """Public simulation window with the compact current application shell."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._mat_export_thread: QThread | None = None
        self._mat_export_worker: _MatExportWorker | None = None
        self._mat_export_button: QPushButton | None = None
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
        """Make the normal export action explicitly describe the native MAT output."""
        for button in self.findChildren(QPushButton):
            if "exportieren" in button.text().lower():
                button.setText("MAT exportieren")
                button.setToolTip(
                    "Eine MATLAB-.mat erzeugen, die ausschließlich native table/timetable-"
                    "Variablen enthält – inklusive Route, Kurvenradius, Höhenprofil, Leistung und Energie."
                )
                self._mat_export_button = button

    @staticmethod
    def _mat_exporter():
        """Load the SciPy-based staging writer only when the user exports."""
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
        """Start an asynchronous MAT export containing only MATLAB tables/timetables."""
        if self._mat_export_thread is not None and self._mat_export_thread.isRunning():
            self.statusBar().showMessage("MATLAB-Export läuft bereits …")
            return

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

        path = Path(selected).expanduser().resolve()
        if path.suffix.lower() != ".mat":
            path = path.with_suffix(".mat")

        try:
            export_matlab_simulation = self._mat_exporter()

            # Snapshot everything the background worker needs. The worker must
            # not read QWidget state or mutable simulation state from its thread.
            result_snapshot = copy.deepcopy(self._result)
            route_snapshot = copy.deepcopy(self._route or {})
            parameters_snapshot = copy.deepcopy(self.parameters())
            power_snapshot = copy.deepcopy(getattr(self, "_resistance_time_data", None))
            comparison_snapshot = {
                "names": copy.deepcopy(getattr(self, "_comparison_names", [])),
                "configs": copy.deepcopy(getattr(self, "_comparison_configs", [])),
                "results": copy.deepcopy(getattr(self, "_comparison_results", [])),
                "resistance": copy.deepcopy(getattr(self, "_comparison_resistance", [])),
            }
            source_route = str(self._route_path or "")
            source_dem = str(getattr(self, "_dem_path", "") or "")

            spatial_distance = np.asarray(
                result_snapshot.get("distance", {}).get("distance_m", []),
                dtype=float,
            )
            elevation_snapshot = np.asarray(
                self._spatial_elevation(spatial_distance), dtype=float
            ).copy()
        except Exception as exc:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(exc))
            return

        def job() -> Path:
            # SciPy writes a temporary staging MAT only. MATLAB then constructs
            # the native table/timetable objects. Raw matrices/structs are not
            # copied into the final file and the staging directory is removed.
            with tempfile.TemporaryDirectory(prefix="gps-routenplaner-mat-") as temporary:
                raw_path = Path(temporary) / "raw_export.mat"
                export_matlab_simulation(
                    result_snapshot,
                    raw_path,
                    route=route_snapshot,
                    parameters=parameters_snapshot,
                    power_data=power_snapshot,
                    elevation_m=elevation_snapshot,
                    source_route=source_route,
                    source_dem=source_dem,
                    comparison=comparison_snapshot,
                )
                return convert_to_native_matlab_tables(raw_path, path)

        thread = QThread(self)
        worker = _MatExportWorker(job)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_mat_export_succeeded)
        worker.failed.connect(self._on_mat_export_failed)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._on_mat_export_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._mat_export_thread = thread
        self._mat_export_worker = worker
        if self._mat_export_button is not None:
            self._mat_export_button.setEnabled(False)
            self._mat_export_button.setText("MAT-Export läuft …")
        self.statusBar().showMessage(
            "MATLAB-Export läuft im Hintergrund … Die Anwendung bleibt bedienbar."
        )
        thread.start()

    @Slot(str)
    def _on_mat_export_succeeded(self, mat_path: str) -> None:
        self.statusBar().showMessage(f"MATLAB-Export gespeichert: {mat_path}", 10000)
        QMessageBox.information(
            self,
            "MATLAB-Export fertig",
            f"Gespeichert:\n{mat_path}\n\n"
            "Die finale Datei enthält ausschließlich table/timetable-Variablen, u. a. "
            "distanceTable, driveTimetable, powerTimetable, loadCollectiveTable, "
            "parametersTable und summaryTable."
        )

    @Slot(str)
    def _on_mat_export_failed(self, message: str) -> None:
        self.statusBar().showMessage("MATLAB-Export fehlgeschlagen", 10000)
        QMessageBox.critical(self, "Export fehlgeschlagen", message)

    @Slot()
    def _on_mat_export_thread_finished(self) -> None:
        if self._mat_export_button is not None:
            self._mat_export_button.setEnabled(True)
            self._mat_export_button.setText("MAT exportieren")
        self._mat_export_worker = None
        self._mat_export_thread = None


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
