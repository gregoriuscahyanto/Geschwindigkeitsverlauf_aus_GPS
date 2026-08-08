from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QSizePolicy,
    QToolButton,
    QWidget,
)

try:
    from .integrated_speed_profile_v13 import IntegratedSpeedProfileWindow as _V13Window
    from .parameter_help import PARAMETER_HELP, SPECIAL_HELP
except ImportError:
    from integrated_speed_profile_v13 import IntegratedSpeedProfileWindow as _V13Window
    from parameter_help import PARAMETER_HELP, SPECIAL_HELP


class IntegratedSpeedProfileWindow(_V13Window):
    """V14: contextual (i) help for every user-adjustable simulation parameter."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self.parameter_info_buttons: dict[str, QToolButton] = {}
        super().__init__(route_path)
        self._install_parameter_info_buttons()

    @staticmethod
    def _info_button(parent: QWidget, callback) -> QToolButton:
        button = QToolButton(parent)
        button.setText("i")
        button.setFixedSize(20, 20)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("Kurze technische Erklärung und Beispielwerte anzeigen")
        button.setStyleSheet(
            "QToolButton { border:1px solid palette(mid); border-radius:10px; "
            "padding:0; font-weight:700; background:palette(base); } "
            "QToolButton:hover { border-color:palette(highlight); "
            "background:palette(alternate-base); color:palette(highlight); }"
        )
        button.clicked.connect(callback)
        return button

    def _wrap_form_label(
        self,
        form: QFormLayout,
        row: int,
        label: QLabel,
        key: str,
    ) -> None:
        if key in self.parameter_info_buttons:
            return
        wrapper = QWidget(label.parentWidget())
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info = self._info_button(wrapper, lambda _checked=False, item=key: self._show_parameter_help(item))
        layout.addWidget(label, 1)
        layout.addWidget(info, 0, Qt.AlignmentFlag.AlignVCenter)
        form.removeWidget(label)
        form.setWidget(row, QFormLayout.ItemRole.LabelRole, wrapper)
        self.parameter_info_buttons[key] = info

    def _install_parameter_info_buttons(self) -> None:
        # All simulation controls tracked in _control_widgets.
        for key, widget in self._control_widgets.items():
            label = self._control_labels.get(key)
            if not isinstance(label, QLabel):
                continue
            for form in self.findChildren(QFormLayout):
                field_row, _field_role = form.getWidgetPosition(widget)
                label_row, _label_role = form.getWidgetPosition(label)
                if field_row >= 0 and field_row == label_row:
                    self._wrap_form_label(form, field_row, label, key)
                    break

        # Preset selector is intentionally not part of _control_widgets but is a
        # user-facing parameter choice and therefore also gets an explanation.
        if hasattr(self, "profile_combo"):
            self._wrap_special_field(self.profile_combo, "driver_profile")

        # Visible elevation smoothing is a display/analysis parameter outside the
        # simulation control dictionary.
        if hasattr(self, "elevation_smoothing_spin"):
            self._wrap_special_field(self.elevation_smoothing_spin, "elevation_smoothing")

    def _wrap_special_field(self, widget: QWidget, key: str) -> None:
        if key in self.parameter_info_buttons:
            return
        for form in self.findChildren(QFormLayout):
            row, _role = form.getWidgetPosition(widget)
            if row < 0:
                continue
            label = form.labelForField(widget)
            if isinstance(label, QLabel):
                self._wrap_form_label(form, row, label, key)
                return

    def _help_entry(self, key: str) -> tuple[str, str, str]:
        if key in PARAMETER_HELP:
            return PARAMETER_HELP[key]
        if key in SPECIAL_HELP:
            return SPECIAL_HELP[key]
        widget = self._control_widgets.get(key)
        description = widget.toolTip().strip() if widget is not None and widget.toolTip() else "Technischer Parameter der Fahrsimulation."
        return (
            description,
            "Eine Änderung dieses Werts wird bei der nächsten Live-Berechnung berücksichtigt, sofern die zugehörige Funktion aktiviert ist.",
            "Orientiere dich zunächst am aktiven Preset und ändere den Wert schrittweise.",
        )

    def _parameter_title(self, key: str) -> str:
        if key == "driver_profile":
            return "Preset"
        if key == "elevation_smoothing":
            return "Höhenprofil-Glättung"
        label = self._control_labels.get(key)
        if isinstance(label, QLabel):
            # V13 may append a bullet to changed parameters.
            return label.text().replace("  •", "").strip()
        return key.replace("_", " ")

    def _current_and_range(self, key: str) -> tuple[str, str]:
        if key == "driver_profile" and hasattr(self, "profile_combo"):
            return self.profile_combo.currentText(), "Auswahl eines vollständigen Fahrer-Presets"
        if key == "elevation_smoothing" and hasattr(self, "elevation_smoothing_spin"):
            widget = self.elevation_smoothing_spin
        else:
            widget = self._control_widgets.get(key)

        if isinstance(widget, QCheckBox):
            return ("Ein" if widget.isChecked() else "Aus"), "Schalter: Ein / Aus"
        if isinstance(widget, QDoubleSpinBox):
            current = widget.text()
            return current, f"Zulässig: {widget.minimum():g} bis {widget.maximum():g}{widget.suffix()}"
        if isinstance(widget, QSpinBox):
            current = widget.text()
            return current, f"Zulässig: {widget.minimum()} bis {widget.maximum()}{widget.suffix()}"
        if widget is not None and hasattr(widget, "currentText"):
            return str(widget.currentText()), "Auswahlfeld"
        return "–", "–"

    def _show_parameter_help(self, key: str) -> None:
        description, influence, examples = self._help_entry(key)
        current, allowed = self._current_and_range(key)
        title = self._parameter_title(key)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(f"{title} – Erklärung")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<b>{title}</b><br><br>"
            f"<b>Was ist das?</b><br>{description}<br><br>"
            f"<b>Einfluss</b><br>{influence}<br><br>"
            f"<b>Beispielwerte</b><br>{examples}<br><br>"
            f"<b>Aktuell:</b> {current}<br>"
            f"<span style='color:gray'>{allowed}</span>"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
