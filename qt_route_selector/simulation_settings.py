from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

try:
    from .runtime_paths import state_dir
except ImportError:
    from runtime_paths import state_dir


SIMULATION_SETTINGS_SCHEMA_VERSION = 1
SIMULATION_SETTINGS_FILENAME = "simulation_settings.json"


def simulation_settings_path() -> Path:
    return state_dir() / SIMULATION_SETTINGS_FILENAME


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    return str(value)


def save_settings_file(path: str | Path, payload: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(dict(payload)), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_settings_file(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Die Einstellungsdatei enthält kein JSON-Objekt.")
    version = int(data.get("schema_version", 0) or 0)
    if version != SIMULATION_SETTINGS_SCHEMA_VERSION:
        raise ValueError(
            f"Nicht unterstützte Einstellungsdatei-Version {version}; "
            f"erwartet wird {SIMULATION_SETTINGS_SCHEMA_VERSION}."
        )
    parameters = data.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("Die Einstellungsdatei enthält keine gültigen Simulationsparameter.")
    return data


class PersistentSimulationSettingsMixin:
    """Add explicit JSON save/load actions to the speed-profile tab."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._settings_status_label: QLabel | None = None
        self._install_settings_persistence_controls()

    def _install_settings_persistence_controls(self) -> None:
        driver_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Fahrer"),
            None,
        )
        form = driver_group.layout() if driver_group is not None else None
        if not isinstance(form, QFormLayout):
            return

        controls = QWidget(driver_group)
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        save_button = QPushButton("Einstellungen speichern", controls)
        load_button = QPushButton("Einstellungen laden", controls)
        save_button.setToolTip(
            "Speichert die aktuellen Fahrer-, Fahrzeug- und Simulationsparameter dauerhaft als JSON."
        )
        load_button.setToolTip(
            "Lädt die zuletzt gespeicherten Simulationsparameter aus der JSON-Datei."
        )
        save_button.clicked.connect(self.save_simulation_settings)
        load_button.clicked.connect(self.load_simulation_settings)
        layout.addWidget(save_button)
        layout.addWidget(load_button)

        status = QLabel(driver_group)
        status.setWordWrap(True)
        status.setStyleSheet("color: palette(mid); font-size: 11px;")
        path = simulation_settings_path()
        if path.is_file():
            status.setText(f"Gespeicherte Einstellungen vorhanden: {path}")
        else:
            status.setText(f"Speicherort: {path}")

        form.addRow("Konfiguration", controls)
        form.addRow(status)
        self._settings_status_label = status
        self.settings_save_button = save_button
        self.settings_load_button = load_button

    def _settings_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SIMULATION_SETTINGS_SCHEMA_VERSION,
            "parameters": copy.deepcopy(self.parameters()),
        }
        smoothing = getattr(self, "elevation_smoothing_spin", None)
        if smoothing is not None and hasattr(smoothing, "value"):
            payload["elevation_smoothing_m"] = float(smoothing.value())
        axis_mode = str(getattr(self, "_axis_mode", "") or "")
        if axis_mode:
            payload["axis_mode"] = axis_mode
        comparisons = getattr(self, "_comparison_configs", None)
        if isinstance(comparisons, list):
            payload["comparison_configs"] = copy.deepcopy(comparisons)
        return payload

    def save_simulation_settings(self) -> None:
        path = simulation_settings_path()
        try:
            save_settings_file(path, self._settings_payload())
        except Exception as exc:
            QMessageBox.critical(self, "Einstellungen konnten nicht gespeichert werden", str(exc))
            return
        if self._settings_status_label is not None:
            self._settings_status_label.setText(f"✓ Gespeichert: {path}")
        status_bar = getattr(self, "statusBar", None)
        if callable(status_bar):
            status_bar().showMessage(f"Simulationseinstellungen gespeichert: {path}", 8000)

    def _apply_parameters(self, parameters: dict[str, Any]) -> None:
        # The public window adds speed-limit policy controls outside the legacy
        # _control_widgets dictionary. Apply those first so the inherited
        # parameter loader's single recalculation already uses the restored policy.
        combo = getattr(self, "speed_limit_policy_combo", None)
        points = getattr(self, "max_speeding_points_spin", None)
        blocked: list[tuple[Any, bool]] = []
        try:
            if combo is not None and "speed_limit_policy" in parameters:
                old = combo.blockSignals(True)
                blocked.append((combo, old))
                index = combo.findData(str(parameters["speed_limit_policy"]))
                if index >= 0:
                    combo.setCurrentIndex(index)
            if points is not None and "max_speeding_points" in parameters:
                old = points.blockSignals(True)
                blocked.append((points, old))
                points.setValue(int(parameters["max_speeding_points"]))
        finally:
            for widget, old in reversed(blocked):
                widget.blockSignals(old)

        policy_changed = getattr(self, "_speed_limit_policy_changed", None)
        if callable(policy_changed):
            old_loading = bool(getattr(self, "_loading_parameters", False))
            self._loading_parameters = True
            try:
                policy_changed()
            finally:
                self._loading_parameters = old_loading

        super()._apply_parameters(parameters)

    def load_simulation_settings(self) -> None:
        path = simulation_settings_path()
        if not path.is_file():
            QMessageBox.information(
                self,
                "Keine gespeicherten Einstellungen",
                f"Es gibt noch keine Einstellungsdatei unter:\n{path}",
            )
            return
        try:
            payload = load_settings_file(path)
            parameters = dict(payload["parameters"])

            smoothing = getattr(self, "elevation_smoothing_spin", None)
            if smoothing is not None and "elevation_smoothing_m" in payload:
                old = smoothing.blockSignals(True)
                try:
                    smoothing.setValue(float(payload["elevation_smoothing_m"]))
                finally:
                    smoothing.blockSignals(old)

            comparisons = payload.get("comparison_configs")
            if isinstance(comparisons, list):
                self._comparison_configs = copy.deepcopy(comparisons)
                refresh = getattr(self, "_refresh_compare_combo", None)
                if callable(refresh):
                    refresh()

            axis_mode = str(payload.get("axis_mode", "") or "")
            axis_combo = getattr(self, "axis_combo", None)
            if axis_mode and axis_combo is not None and hasattr(axis_combo, "findData"):
                index = axis_combo.findData(axis_mode)
                if index >= 0:
                    old = axis_combo.blockSignals(True)
                    try:
                        axis_combo.setCurrentIndex(index)
                    finally:
                        axis_combo.blockSignals(old)
                    self._axis_mode = axis_mode

            self._apply_parameters(parameters)
        except Exception as exc:
            QMessageBox.critical(self, "Einstellungen konnten nicht geladen werden", str(exc))
            return

        if self._settings_status_label is not None:
            self._settings_status_label.setText(f"✓ Geladen: {path}")
        status_bar = getattr(self, "statusBar", None)
        if callable(status_bar):
            status_bar().showMessage(f"Simulationseinstellungen geladen: {path}", 8000)


__all__ = [
    "PersistentSimulationSettingsMixin",
    "SIMULATION_SETTINGS_FILENAME",
    "SIMULATION_SETTINGS_SCHEMA_VERSION",
    "load_settings_file",
    "save_settings_file",
    "simulation_settings_path",
]
