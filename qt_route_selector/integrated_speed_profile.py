from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, QSettings, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
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
    from .speed_limit_policy import (
        POLICY_GERMANY_POINTS,
        POLICY_LABELS,
        POLICY_OBEY,
        install_integrated_speed_profile_policy,
        normalize_policy,
    )
    from .structure_elevation import correct_structure_elevation
except ImportError:
    from _internal.simulation_layers import integrated_speed_profile as _base_layer
    from _internal.simulation_layers.integrated_speed_profile import _osm_only_event_positions
    from _internal.simulation_layers.integrated_speed_profile_v16 import (
        IntegratedSpeedProfileWindow as _CurrentWindow,
    )
    from runtime_paths import exports_dir
    from speed_limit_policy import (
        POLICY_GERMANY_POINTS,
        POLICY_LABELS,
        POLICY_OBEY,
        install_integrated_speed_profile_policy,
        normalize_policy,
    )
    from structure_elevation import correct_structure_elevation

# The implementation layers live below _internal, while QML resources remain
# next to the public application modules.
_base_layer.APP_DIR = Path(__file__).resolve().parent
install_integrated_speed_profile_policy()


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
        # super().__init__ may already build plots and therefore call the
        # overridden _spatial_elevation/_update_plots methods. Initialize state first.
        self._structure_elevation_cache_key: tuple | None = None
        self._structure_elevation_cache_values: np.ndarray | None = None
        self._structure_elevation_stats: dict[str, int] = {}
        self.speed_limit_policy_combo: QComboBox | None = None
        self.max_speeding_points_spin: QSpinBox | None = None
        self.speed_limit_policy_note: QLabel | None = None
        super().__init__(route_path)
        self._mat_export_thread: QThread | None = None
        self._mat_export_worker: _MatExportWorker | None = None
        self._mat_export_button: QPushButton | None = None
        self._install_speed_limit_policy_controls()
        self._merge_summary_cards()
        self._configure_mat_export_ui()

    def _install_speed_limit_policy_controls(self) -> None:
        """Add an independent legal-speed strategy below the driver preset."""

        driver_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Fahrer"),
            None,
        )
        form = driver_group.layout() if driver_group is not None else None
        if not isinstance(form, QFormLayout):
            return

        combo = QComboBox(driver_group)
        for key, label in POLICY_LABELS.items():
            combo.addItem(label, key)
        combo.setToolTip(
            "Legt fest, wie das OSM-Geschwindigkeitslimit die Fahrer-Simulation begrenzt. "
            "Kurven-, Oberflächen- und Fahrzeuggrenzen bleiben unabhängig davon aktiv."
        )

        points = QSpinBox(driver_group)
        points.setRange(0, 2)
        points.setSingleStep(1)
        points.setValue(0)
        points.setSuffix(" Punkt(e)")
        points.setKeyboardTracking(False)
        points.setToolTip(
            "Konservative Deutschland-Pkw-Näherung pro Geschwindigkeitsverstoß: "
            "0 Punkte -> höchstens +20 km/h; 1 Punkt -> höchstens +30 km/h; "
            "2 Punkte -> keine zusätzliche punktbedingte Obergrenze."
        )

        note = QLabel(driver_group)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-size: 11px;")

        form.addRow("Tempolimit-Strategie", combo)
        form.addRow("Max. Punkte", points)
        form.addRow(note)

        self.speed_limit_policy_combo = combo
        self.max_speeding_points_spin = points
        self.speed_limit_policy_note = note
        combo.currentIndexChanged.connect(self._speed_limit_policy_changed)
        points.valueChanged.connect(self.schedule_recalculate)
        self._speed_limit_policy_changed()

    def _speed_limit_policy_changed(self, *_args: Any) -> None:
        combo = self.speed_limit_policy_combo
        points = self.max_speeding_points_spin
        if combo is None or points is None:
            return
        policy = normalize_policy(combo.currentData())
        points.setEnabled(policy == POLICY_GERMANY_POINTS)
        if self.speed_limit_policy_note is not None:
            if policy == POLICY_GERMANY_POINTS:
                self.speed_limit_policy_note.setText(
                    "Deutschland-Pkw, konservativ: Die App kennt inner-/außerorts nicht immer "
                    "sicher und verwendet deshalb die strengere gemeinsame Punktegrenze."
                )
            elif policy == "ignore":
                self.speed_limit_policy_note.setText(
                    "Das OSM-Tempolimit wird ignoriert; Kurvenphysik, Straßenbelag und die "
                    "absolute Fahrer-Obergrenze bleiben wirksam."
                )
            else:
                self.speed_limit_policy_note.setText(
                    "Das OSM-Tempolimit bleibt die normale rechtliche Geschwindigkeitsgrenze."
                )
        self.schedule_recalculate()

    def parameters(self) -> dict[str, Any]:
        values = super().parameters()
        combo = self.speed_limit_policy_combo
        points = self.max_speeding_points_spin
        values["speed_limit_policy"] = normalize_policy(
            combo.currentData() if combo is not None else POLICY_OBEY
        )
        values["max_speeding_points"] = int(points.value()) if points is not None else 0
        return values

    def _spatial_elevation(self, sample_distance: np.ndarray) -> np.ndarray:
        """Use DEM/GPX heights, but not terrain heights inside tunnels/on bridges."""

        elevation = np.asarray(super()._spatial_elevation(sample_distance), dtype=float).reshape(-1)
        distance = np.asarray(sample_distance, dtype=float).reshape(-1)
        if elevation.size != distance.size or elevation.size < 2:
            return elevation
        if np.count_nonzero(np.isfinite(elevation)) < 2:
            return elevation

        settings = QSettings("GPSDrivingSimulation", "QtRouteSelector")
        roads_file = str(settings.value("roads_file", "") or "").strip()
        roads_path = Path(roads_file).expanduser().resolve() if roads_file else None
        if roads_path is None or not roads_path.is_file():
            return elevation

        route_sample_coordinates = getattr(self, "_route_sample_coordinates", None)
        if not callable(route_sample_coordinates):
            return elevation
        coordinates = route_sample_coordinates(distance)
        if coordinates is None:
            return elevation
        latitude, longitude = coordinates
        latitude = np.asarray(latitude, dtype=float).reshape(-1)
        longitude = np.asarray(longitude, dtype=float).reshape(-1)
        if latitude.size != distance.size or longitude.size != distance.size:
            return elevation

        try:
            stat = roads_path.stat()
            cache_key = (
                str(roads_path),
                stat.st_mtime_ns,
                stat.st_size,
                str(getattr(self, "_route_path", "")),
                int(getattr(self, "_last_route_mtime_ns", 0) or 0),
                distance.size,
                round(float(distance[0]), 3),
                round(float(distance[-1]), 3),
            )
        except OSError:
            return elevation

        if (
            self._structure_elevation_cache_key == cache_key
            and self._structure_elevation_cache_values is not None
        ):
            return self._structure_elevation_cache_values.copy()

        try:
            corrected, stats = correct_structure_elevation(
                roads_path,
                distance,
                latitude,
                longitude,
                elevation,
            )
        except Exception:
            return elevation

        self._structure_elevation_cache_key = cache_key
        self._structure_elevation_cache_values = np.asarray(corrected, dtype=float).copy()
        self._structure_elevation_stats = dict(stats)

        corrected_runs = int(stats.get("corrected_runs", 0) or 0)
        if corrected_runs:
            tunnel_points = int(stats.get("tunnel_points", 0) or 0)
            bridge_points = int(stats.get("bridge_points", 0) or 0)
            label = getattr(self, "dem_status_label", None)
            if isinstance(label, QLabel):
                base = label.text().split(" | OSM-Strukturen:", 1)[0]
                label.setText(
                    f"{base} | OSM-Strukturen: {corrected_runs} Abschnitt(e) korrigiert "
                    f"({tunnel_points} Tunnel-, {bridge_points} Brücken-Stützpunkte)."
                )

        return self._structure_elevation_cache_values.copy()

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
