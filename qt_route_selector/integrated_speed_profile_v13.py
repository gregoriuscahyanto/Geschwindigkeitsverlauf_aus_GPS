from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from .integrated_speed_profile_v12 import IntegratedSpeedProfileWindow as _V12Window
    from .speed_simulation import profile_parameters
    from .technical_previews_v2 import FriendlyTechnicalPreviews
except ImportError:
    from integrated_speed_profile_v12 import IntegratedSpeedProfileWindow as _V12Window
    from speed_simulation import profile_parameters
    from technical_previews_v2 import FriendlyTechnicalPreviews


_IGNORED_CHANGE_KEYS = {"traffic_light_count"}

_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "apply_curve_speed": (
        "max_lat_accel_mps2",
        "min_curve_radius_m",
        "max_curve_radius_m",
        "curve_sample_distance_m",
        "curve_smooth_distance_m",
        "curve_plan_decel_mps2",
    ),
    "use_traffic_lights": (
        "traffic_light_dwell_min_s",
        "traffic_light_dwell_max_s",
        "traffic_light_plan_decel_mps2",
        "traffic_light_stop_tolerance_m",
    ),
    "use_overtaking": (
        "overtaking_count",
        "overtaking_slow_speed_kmh",
        "overtaking_intensity_kmh",
        "overtaking_follow_distance_m",
        "overtaking_pass_distance_m",
    ),
    "use_driver_noise": (
        "noise_std_kmh",
        "noise_tau_s",
    ),
    "use_post_curve_overshoot": (
        "post_curve_overshoot_kmh",
        "post_curve_overshoot_probability_pct",
        "post_curve_overshoot_distance_m",
    ),
    "use_trailer_model": (
        "trailer_mass_kg",
        "trailer_rolling_resistance_coeff",
        "trailer_drag_area_m2",
        "max_drive_force_n",
        "max_brake_force_n",
    ),
}


class IntegratedSpeedProfileWindow(_V12Window):
    """V13: contextual previews and immediate feedback for effective parameter changes."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._change_tracking_ready = False
        self._common_control_defaults: dict[str, Any] = {}
        self._preset_baseline: dict[str, Any] = {}
        self._control_labels: dict[str, QLabel] = {}
        self._label_original_text: dict[str, str] = {}
        self._label_original_style: dict[str, str] = {}
        self._widget_original_style: dict[str, str] = {}
        self._widget_original_tooltip: dict[str, str] = {}
        self.parameter_change_card: QFrame | None = None
        self.parameter_change_label: QLabel | None = None
        self.parameter_reset_button: QToolButton | None = None
        super().__init__(route_path)

        self._common_control_defaults = self._snapshot_controls()
        self._discover_control_labels()
        self._install_change_card()
        legacy_preview = self.preview_controller
        if legacy_preview is not None:
            self.preview_controller = FriendlyTechnicalPreviews(self, legacy_preview)
        self._change_tracking_ready = True
        self._select_preset_baseline()
        self._refresh_dependency_state()
        self._refresh_parameter_changes()

    # ------------------------------------------------------------------
    # Preset baseline and change detection
    # ------------------------------------------------------------------
    @staticmethod
    def _widget_value(widget: QWidget) -> Any:
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        if isinstance(widget, QSpinBox):
            return int(widget.value())
        if isinstance(widget, QCheckBox):
            return bool(widget.isChecked())
        if isinstance(widget, QComboBox):
            return widget.currentData()
        return None

    def _snapshot_controls(self) -> dict[str, Any]:
        return {
            key: self._widget_value(widget)
            for key, widget in self._control_widgets.items()
            if self._widget_value(widget) is not None
        }

    def _build_preset_baseline(self) -> dict[str, Any]:
        name = str(self.profile_combo.currentData()) if hasattr(self, "profile_combo") else "normalo"
        baseline = dict(self._common_control_defaults)
        for key, value in profile_parameters(name).items():
            if key in self._control_widgets:
                baseline[key] = value
        return baseline

    def _select_preset_baseline(self) -> None:
        self._preset_baseline = self._build_preset_baseline()
        preview = self.preview_controller
        if isinstance(preview, FriendlyTechnicalPreviews):
            preview.set_baseline(self._preset_baseline)

    @staticmethod
    def _different(current: Any, baseline: Any) -> bool:
        if isinstance(current, bool) or isinstance(baseline, bool):
            return bool(current) != bool(baseline)
        if isinstance(current, (float, int)) and isinstance(baseline, (float, int)):
            return not math.isclose(float(current), float(baseline), rel_tol=0.0, abs_tol=1e-9)
        return current != baseline

    def _inactive_dependency_keys(self) -> set[str]:
        inactive: set[str] = set()
        for controller_key, dependent_keys in _DEPENDENCIES.items():
            controller = self._control_widgets.get(controller_key)
            if isinstance(controller, QCheckBox) and not controller.isChecked():
                inactive.update(dependent_keys)
        return inactive

    def _changed_keys(self) -> set[str]:
        inactive = self._inactive_dependency_keys()
        changed: set[str] = set()
        for key, widget in self._control_widgets.items():
            if key in _IGNORED_CHANGE_KEYS or key in inactive or key not in self._preset_baseline:
                continue
            if self._different(self._widget_value(widget), self._preset_baseline[key]):
                changed.add(key)
        return changed

    # ------------------------------------------------------------------
    # Human-readable labels and status card
    # ------------------------------------------------------------------
    def _discover_control_labels(self) -> None:
        for key, widget in self._control_widgets.items():
            self._widget_original_style[key] = widget.styleSheet()
            self._widget_original_tooltip[key] = widget.toolTip()
            for form in self.findChildren(QFormLayout):
                label_widget = form.labelForField(widget)
                if isinstance(label_widget, QLabel):
                    self._control_labels[key] = label_widget
                    self._label_original_text[key] = label_widget.text()
                    self._label_original_style[key] = label_widget.styleSheet()
                    break

    def _install_change_card(self) -> None:
        driver_group = next(
            (group for group in self.findChildren(QWidget) if getattr(group, "title", lambda: "")() == "Fahrer"),
            None,
        )
        parent = driver_group.parentWidget() if driver_group is not None else None
        layout = parent.layout() if parent is not None else None
        if not isinstance(layout, QVBoxLayout):
            return

        card = QFrame(parent)
        card.setFrameShape(QFrame.Shape.NoFrame)
        row = QHBoxLayout(card)
        row.setContentsMargins(9, 7, 9, 7)
        row.setSpacing(8)
        label = QLabel(card)
        label.setWordWrap(True)
        label.setSizePolicy(label.sizePolicy().horizontalPolicy(), label.sizePolicy().verticalPolicy())
        reset = QToolButton(card)
        reset.setText("↺ Preset")
        reset.setToolTip("Alle geänderten Parameter auf das ausgewählte Preset zurücksetzen")
        reset.clicked.connect(self._reset_to_active_preset)
        row.addWidget(label, 1)
        row.addWidget(reset)

        comparison = getattr(self, "comparison_group", None)
        index = layout.indexOf(comparison) if comparison is not None else layout.indexOf(driver_group)
        layout.insertWidget(max(0, index), card)
        self.parameter_change_card = card
        self.parameter_change_label = label
        self.parameter_reset_button = reset

    def _friendly_change_names(self, keys: set[str]) -> list[str]:
        names: list[str] = []
        for key in sorted(keys):
            label = self._label_original_text.get(key, key.replace("_", " "))
            names.append(label.rstrip(" :"))
        return names

    def _refresh_change_card(self, changed: set[str]) -> None:
        if self.parameter_change_card is None or self.parameter_change_label is None:
            return
        profile = self.profile_combo.currentText() if hasattr(self, "profile_combo") else "Preset"
        if not changed:
            self.parameter_change_label.setText(f"✓ <b>{profile}</b> · Preset unverändert")
            self.parameter_change_label.setToolTip("Alle wirksamen Parameter entsprechen dem ausgewählten Preset.")
            self.parameter_change_card.setStyleSheet(
                "QFrame { border:1px solid palette(midlight); border-radius:8px; background:palette(base); }"
            )
            if self.parameter_reset_button is not None:
                self.parameter_reset_button.hide()
            return

        names = self._friendly_change_names(changed)
        count = len(changed)
        self.parameter_change_label.setText(
            f"● <b>{count} Änderung{'en' if count != 1 else ''}</b> gegenüber {profile}"
        )
        self.parameter_change_label.setToolTip("Geändert: " + ", ".join(names))
        self.parameter_change_card.setStyleSheet(
            "QFrame { border:1px solid palette(highlight); border-radius:8px; "
            "background:palette(alternate-base); }"
        )
        if self.parameter_reset_button is not None:
            self.parameter_reset_button.show()

    def _refresh_control_highlights(self, changed: set[str]) -> None:
        inactive = self._inactive_dependency_keys()
        for key, widget in self._control_widgets.items():
            label = self._control_labels.get(key)
            original_label = self._label_original_text.get(key)
            if label is not None and original_label is not None:
                if key in changed:
                    label.setText(original_label + "  •")
                    label.setStyleSheet(
                        self._label_original_style.get(key, "")
                        + " QLabel { color:palette(highlight); font-weight:600; }"
                    )
                    label.setToolTip("Geändert gegenüber dem ausgewählten Preset")
                else:
                    label.setText(original_label)
                    label.setStyleSheet(self._label_original_style.get(key, ""))
                    label.setToolTip("Der Parameter ist momentan ohne Wirkung." if key in inactive else "")

            if key in changed and isinstance(widget, QAbstractSpinBox):
                widget.setStyleSheet(
                    self._widget_original_style.get(key, "")
                    + " QAbstractSpinBox { border:1px solid palette(highlight); "
                    "background:palette(alternate-base); }"
                )
            else:
                widget.setStyleSheet(self._widget_original_style.get(key, ""))

            base_tip = self._widget_original_tooltip.get(key, "")
            if key in inactive:
                extra = "Dieser Wert ist derzeit deaktiviert und beeinflusst die Simulation nicht."
            elif key in changed:
                extra = "Geändert gegenüber dem ausgewählten Preset."
            else:
                extra = ""
            widget.setToolTip("\n\n".join(part for part in (base_tip, extra) if part))

    def _refresh_parameter_changes(self) -> None:
        if not self._change_tracking_ready:
            return
        changed = self._changed_keys()
        self._refresh_change_card(changed)
        self._refresh_control_highlights(changed)
        preview = self.preview_controller
        if isinstance(preview, FriendlyTechnicalPreviews):
            preview.set_changed_keys(changed)
            preview.update()

    # ------------------------------------------------------------------
    # Explicitly show whether a parameter can currently affect the model
    # ------------------------------------------------------------------
    def _refresh_dependency_state(self) -> None:
        for controller_key, dependent_keys in _DEPENDENCIES.items():
            controller = self._control_widgets.get(controller_key)
            if not isinstance(controller, QCheckBox):
                continue
            enabled = controller.isChecked()
            for key in dependent_keys:
                widget = self._control_widgets.get(key)
                if widget is not None:
                    widget.setEnabled(enabled)
                label = self._control_labels.get(key)
                if label is not None:
                    label.setEnabled(enabled)

    def _set_widgets_from_values(self, values: dict[str, Any]) -> None:
        blocked: list[tuple[QWidget, bool]] = []
        try:
            for key, widget in self._control_widgets.items():
                if key not in values:
                    continue
                old = widget.blockSignals(True)
                blocked.append((widget, old))
                value = values[key]
                if isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
        finally:
            for widget, old in reversed(blocked):
                widget.blockSignals(old)

    def _reset_to_active_preset(self) -> None:
        baseline = self._build_preset_baseline()
        self._set_widgets_from_values(baseline)
        self._preset_baseline = baseline
        preview = self.preview_controller
        if isinstance(preview, FriendlyTechnicalPreviews):
            preview.set_baseline(baseline)
        self._refresh_dependency_state()
        self._refresh_parameter_changes()
        super().schedule_recalculate()

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------
    def _apply_profile(self, name: str) -> None:
        super()._apply_profile(name)
        if self._change_tracking_ready:
            self._select_preset_baseline()
            self._refresh_dependency_state()
            self._refresh_parameter_changes()

    def _apply_parameters(self, parameters: dict[str, Any]) -> None:
        super()._apply_parameters(parameters)
        if self._change_tracking_ready:
            self._select_preset_baseline()
            self._refresh_dependency_state()
            self._refresh_parameter_changes()

    def schedule_recalculate(self, *_args: Any) -> None:
        super().schedule_recalculate(*_args)
        if self._change_tracking_ready:
            self._refresh_dependency_state()
            self._refresh_parameter_changes()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
