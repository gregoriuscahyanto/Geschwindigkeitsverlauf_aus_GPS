from __future__ import annotations

import copy
import sys
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
    from .runtime_paths import exports_dir
except ImportError:
    from _internal.simulation_layers import integrated_speed_profile as _base_layer
    from _internal.simulation_layers.integrated_speed_profile import _osm_only_event_positions
    from _internal.simulation_layers.integrated_speed_profile_v16 import (
        IntegratedSpeedProfileWindow as _CurrentWindow,
    )
    from runtime_paths import exports_dir

# The implementation layers live below _internal, while QML resources remain
# next to the public application modules.
_base_layer.APP_DIR = Path(__file__).resolve().parent


class _MatExportWorker(QObject):
    """Run MAT serialization without blocking the Qt GUI."""

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
        """Describe the direct Python MAT export in the normal export action."""
        for button in self.findChildren(QPushButton):
            if "exportieren" in button.text().lower():
                button.setText("MAT exportieren")
                button.setToolTip(
                    "MATLAB-.mat mit synchronisierten Simulationseingängen erzeugen. "
                    "Alle input_*-Signale und alle Felder in sim_input besitzen exakt "
                    "dieselbe N×1-Länge wie time_s."
                )
                self._mat_export_button = button

    @staticmethod
    def _mat_exporter():
        """Load SciPy only when the user actually exports."""
        try:
            from .synchronized_mat_export import export_matlab_simulation
        except ImportError as package_error:
            try:
                from synchronized_mat_export import export_matlab_simulation
            except ImportError:
                raise RuntimeError(
                    "Für den MAT-Export fehlt SciPy in der aktuellen .venv.\n\n"
                    "Bitte im Projektordner einmal ausführen:\n"
                    ".\\scripts\\setup_windows.ps1\n\n"
                    "Danach die Anwendung neu starten."
                ) from package_error
        return export_matlab_simulation

    def export_result(self) -> None:
        """Start an asynchronous MAT export containing individual double arrays."""
        if self._mat_export_thread is not None and self._mat_export_thread.isRunning():
            self.statusBar().showMessage("MAT-Export läuft bereits …")
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
            "Vollständige Simulation als MAT-Datei exportieren",
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

            # Snapshot everything before entering the worker thread. The worker
            # does not access QWidget state or mutable simulation state.
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
            return export_matlab_simulation(
                result_snapshot,
                path,
                route=route_snapshot,
                parameters=parameters_snapshot,
                power_data=power_snapshot,
                elevation_m=elevation_snapshot,
                comparison=comparison_snapshot,
            )

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
            "MAT-Export läuft im Hintergrund … Die Anwendung bleibt bedienbar."
        )
        thread.start()

    @Slot(str)
    def _on_mat_export_succeeded(self, mat_path: str) -> None:
        self.statusBar().showMessage(f"MAT-Export gespeichert: {mat_path}", 10000)
        QMessageBox.information(
            self,
            "MAT-Export fertig",
            f"Gespeichert:\n{mat_path}\n\n"
            "Für die Folgesimulation verwende sim_input oder die input_*-Variablen. "
            "Alle diese Signale sind N×1 und besitzen exakt dieselbe Länge wie input_time_s, "
            "z. B. input_v_kmh, input_curve_radius_m, input_elevation_m und input_p_total_kw."
        )

    @Slot(str)
    def _on_mat_export_failed(self, message: str) -> None:
        self.statusBar().showMessage("MAT-Export fehlgeschlagen", 10000)
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
