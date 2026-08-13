from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
)


SIMULATION_SETTINGS_SCHEMA_VERSION = 1
SIMULATION_SETTINGS_KEY = "simulation_setup"


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


def load_route_document(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    document = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Die Routendatei enthält kein JSON-Objekt.")
    return document


def load_settings_from_route(path: str | Path) -> dict[str, Any] | None:
    document = load_route_document(path)
    payload = document.get(SIMULATION_SETTINGS_KEY)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Die Routendatei enthält ungültige Simulationsparameter.")
    version = int(payload.get("schema_version", 0) or 0)
    if version != SIMULATION_SETTINGS_SCHEMA_VERSION:
        raise ValueError(
            f"Nicht unterstützte Simulationskonfiguration Version {version}; "
            f"erwartet wird {SIMULATION_SETTINGS_SCHEMA_VERSION}."
        )
    active = payload.get("active_driver")
    if not isinstance(active, dict) or not isinstance(active.get("parameters"), dict):
        raise ValueError("Die Routendatei enthält keinen gültigen aktiven Fahrer.")
    drivers = payload.get("drivers", [])
    if not isinstance(drivers, list):
        raise ValueError("Die gespeicherte Fahrerliste ist ungültig.")
    return payload


def save_settings_to_route(
    source_path: str | Path,
    payload: Mapping[str, Any],
) -> Path:
    """Embed the complete speed-profile state into the existing route JSON."""

    destination = Path(source_path).expanduser().resolve()
    document = load_route_document(destination)
    embedded = dict(payload)
    embedded["schema_version"] = SIMULATION_SETTINGS_SCHEMA_VERSION
    document[SIMULATION_SETTINGS_KEY] = _json_safe(embedded)

    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
    return destination


class PersistentSimulationSettingsMixin:
    """Store route and all driver configurations in one self-contained JSON."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._embedded_settings_token: tuple[str, int] | None = None
        self._applying_embedded_settings = False
        self._embedded_settings_ready = False
        self._settings_status_label: QLabel | None = None
        super().__init__(*args, **kwargs)
        self._install_settings_persistence_controls()
        # The public simulation subclass installs additional controls (notably
        # speed-limit policy / max points) after this base constructor returns.
        # Defer the first restore until the event loop so every public control
        # exists before the saved parameter set is applied.
        self._embedded_settings_ready = True
        QTimer.singleShot(0, lambda: self._load_embedded_settings_if_present(force=True))

    def _install_settings_persistence_controls(self) -> None:
        driver_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Fahrer"),
            None,
        )
        form = driver_group.layout() if driver_group is not None else None
        if not isinstance(form, QFormLayout):
            return

        save_button = QPushButton("In Routendatei speichern", driver_group)
        save_button.setToolTip(
            "Speichert den aktuellen Fahrer und alle Vergleichsfahrer direkt in dieselbe "
            "route_result_*.json. Beim späteren Öffnen werden sie automatisch geladen."
        )
        save_button.clicked.connect(self.save_simulation_settings)

        status = QLabel(driver_group)
        status.setWordWrap(True)
        status.setStyleSheet("color: palette(mid); font-size: 11px;")
        status.setText(
            "Route und Fahrer gehören zu einer Datei. Gespeicherte Fahrer werden beim Öffnen "
            "der Routendatei automatisch wiederhergestellt."
        )

        form.addRow("Projekt", save_button)
        form.addRow(status)
        self._settings_status_label = status
        self.settings_save_button = save_button

    def _settings_payload(self) -> dict[str, Any]:
        profile_combo = getattr(self, "profile_combo", None)
        profile_key = ""
        profile_label = "Aktueller Fahrer"
        if profile_combo is not None:
            try:
                profile_key = str(profile_combo.currentData() or "")
                profile_label = str(profile_combo.currentText() or profile_label)
            except Exception:
                pass

        payload: dict[str, Any] = {
            "schema_version": SIMULATION_SETTINGS_SCHEMA_VERSION,
            "active_driver": {
                "name": profile_label,
                "profile": profile_key,
                "parameters": copy.deepcopy(self.parameters()),
            },
            # Existing comparison configurations are the user's additional
            # named drivers/scenarios and travel with this exact route.
            "drivers": copy.deepcopy(getattr(self, "_comparison_configs", [])),
        }
        smoothing = getattr(self, "elevation_smoothing_spin", None)
        if smoothing is not None and hasattr(smoothing, "value"):
            payload["elevation_smoothing_m"] = float(smoothing.value())
        axis_mode = str(getattr(self, "_axis_mode", "") or "")
        if axis_mode:
            payload["axis_mode"] = axis_mode
        dem_path = getattr(self, "_dem_path", None)
        if dem_path is not None:
            payload["dem_path"] = str(dem_path)
        return payload

    def save_simulation_settings(self) -> None:
        route_path = Path(getattr(self, "_route_path", "route_result.json")).expanduser().resolve()
        if not route_path.is_file():
            QMessageBox.information(
                self,
                "Keine Routendatei",
                "Zuerst eine Route bzw. GPX in Schritt 1 erzeugen oder eine Routendatei öffnen.",
            )
            return
        try:
            save_settings_to_route(route_path, self._settings_payload())
            mtime = route_path.stat().st_mtime_ns
            self._embedded_settings_token = (str(route_path), mtime)
            self._last_route_mtime_ns = mtime
        except Exception as exc:
            QMessageBox.critical(self, "Projekt konnte nicht gespeichert werden", str(exc))
            return
        if self._settings_status_label is not None:
            drivers = len(getattr(self, "_comparison_configs", []))
            self._settings_status_label.setText(
                f"✓ In {route_path.name} gespeichert: aktueller Fahrer + {drivers} weitere Fahrer."
            )
        self.statusBar().showMessage(f"Route und Fahrer gemeinsam gespeichert: {route_path}", 9000)

    def _apply_parameters(self, parameters: dict[str, Any]) -> None:
        # The public layer adds the speed-limit controls outside the inherited
        # _control_widgets dictionary. Restore them together with every legacy
        # driver/vehicle/simulation control.
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

    def _apply_embedded_payload(self, payload: Mapping[str, Any]) -> None:
        active = payload.get("active_driver", {})
        parameters = dict(active.get("parameters", {})) if isinstance(active, Mapping) else {}

        smoothing = getattr(self, "elevation_smoothing_spin", None)
        if smoothing is not None and "elevation_smoothing_m" in payload:
            old = smoothing.blockSignals(True)
            try:
                smoothing.setValue(float(payload["elevation_smoothing_m"]))
            finally:
                smoothing.blockSignals(old)

        drivers = payload.get("drivers", [])
        if isinstance(drivers, list):
            self._comparison_configs = copy.deepcopy(drivers)
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

        if parameters:
            self._apply_parameters(parameters)

    def _load_embedded_settings_if_present(self, *, force: bool = False) -> None:
        if not self._embedded_settings_ready or self._applying_embedded_settings:
            return
        route_path = Path(getattr(self, "_route_path", "route_result.json")).expanduser().resolve()
        if not route_path.is_file():
            return
        try:
            token = (str(route_path), route_path.stat().st_mtime_ns)
        except OSError:
            return
        if not force and token == self._embedded_settings_token:
            return

        try:
            payload = load_settings_from_route(route_path)
        except Exception as exc:
            if self._settings_status_label is not None:
                self._settings_status_label.setText(f"Eingebettete Fahrer konnten nicht geladen werden: {exc}")
            return

        self._embedded_settings_token = token
        if payload is None:
            if self._settings_status_label is not None:
                self._settings_status_label.setText(
                    "Diese ältere Routendatei enthält noch keine gespeicherten Fahrer."
                )
            return

        self._applying_embedded_settings = True
        try:
            self._apply_embedded_payload(payload)
        finally:
            self._applying_embedded_settings = False
        if self._settings_status_label is not None:
            drivers = len(payload.get("drivers", []))
            self._settings_status_label.setText(
                f"✓ Aus {route_path.name} automatisch geladen: aktueller Fahrer + {drivers} weitere Fahrer."
            )

    def reload_route(self, *_args: Any, silent: bool = False) -> None:
        super().reload_route(*_args, silent=silent)
        if self._embedded_settings_ready:
            self._load_embedded_settings_if_present()


__all__ = [
    "PersistentSimulationSettingsMixin",
    "SIMULATION_SETTINGS_KEY",
    "SIMULATION_SETTINGS_SCHEMA_VERSION",
    "load_route_document",
    "load_settings_from_route",
    "save_settings_to_route",
]
