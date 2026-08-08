from __future__ import annotations

import sys
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
)

try:
    from .integrated_speed_profile_v10 import IntegratedSpeedProfileWindow as _V10Window
except ImportError:
    from integrated_speed_profile_v10 import IntegratedSpeedProfileWindow as _V10Window


_AXIS_BADGES = {
    "speed": "v",
    "acceleration": "a",
    "elevation": "h",
    "power": "P",
}
_AXIS_ORDER = ("speed", "acceleration", "elevation", "power")


class IntegratedSpeedProfileWindow(_V10Window):
    """V11: unclipped responsive parameters and explicit signal-to-axis mapping."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._v11_ready = False
        self.axis_guide_label: QLabel | None = None
        self._route_card_compact: bool | None = None
        super().__init__(route_path)

        self._fix_sidebar_minimum_size_constraint()
        self._configure_route_card()
        self._install_axis_guide()
        self._label_signal_actions_with_axes()
        self._v11_ready = True
        self._apply_responsive_layout(force=True)
        self._refresh_combined_legend()
        self._refresh_axis_guide()

    def _refresh_scroll_area(self) -> None:
        super()._refresh_scroll_area()
        self._fix_sidebar_minimum_size_constraint()

    def _fix_sidebar_minimum_size_constraint(self) -> None:
        scroll = getattr(self, "parameter_scroll_area", None)
        if not isinstance(scroll, QScrollArea):
            pane = getattr(self, "_parameter_pane", None)
            if isinstance(pane, QScrollArea):
                scroll = pane
            elif pane is not None:
                candidates = pane.findChildren(QScrollArea)
                scroll = candidates[0] if candidates else None
        if not isinstance(scroll, QScrollArea):
            return

        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content = scroll.widget()
        if content is None:
            return

        self.parameter_scroll_area = scroll
        content.setMinimumSize(0, 0)
        content.setMaximumWidth(16_777_215)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root_layout = content.layout()
        if root_layout is not None:
            root_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        for group in content.findChildren(QGroupBox):
            group.setMinimumWidth(0)
            group.setMaximumWidth(16_777_215)
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            page_layout = group.layout()
            if page_layout is not None:
                page_layout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
            for child in group.findChildren(QLabel):
                child.setMinimumWidth(0)
                if child.wordWrap():
                    child.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        content.updateGeometry()
        scroll.updateGeometry()

    def _configure_route_card(self) -> None:
        route_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Route"),
            None,
        )
        layout = route_group.layout() if route_group is not None else None
        if route_group is None or not isinstance(layout, QGridLayout):
            return

        self._route_group = route_group
        self._route_grid = layout
        self._route_buttons = [
            button
            for button in route_group.findChildren(QPushButton)
            if button.isEnabled()
            and button.text().strip() in {"Datei wählen", "Neu laden", "Exportieren …", "CSV + JSON exportieren"}
        ]
        self._dem_title_label = next(
            (label for label in route_group.findChildren(QLabel) if label.text().strip() == "Höhenmodell"),
            None,
        )
        self._smoothing_title_label = next(
            (
                label
                for label in route_group.findChildren(QLabel)
                if label.text().strip() == "Höhenprofil-Glättung"
            ),
            None,
        )

        self.route_path_label.setWordWrap(False)
        self.route_path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._update_route_path_display()
        if self.dem_status_label is not None:
            self.dem_status_label.setWordWrap(True)
            self.dem_status_label.setMinimumWidth(0)
            self.dem_status_label.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

    def _update_route_path_display(self) -> None:
        if not hasattr(self, "route_path_label"):
            return
        path = Path(self._route_path)
        self.route_path_label.setText(path.name or str(path))
        self.route_path_label.setToolTip(str(path))

    def _reflow_route_card(self, compact: bool) -> None:
        layout = getattr(self, "_route_grid", None)
        if not isinstance(layout, QGridLayout) or self._route_card_compact == compact:
            return
        self._route_card_compact = compact

        route_label = getattr(self, "route_path_label", None)
        dem_title = getattr(self, "_dem_title_label", None)
        dem_status = getattr(self, "dem_status_label", None)
        smoothing_title = getattr(self, "_smoothing_title_label", None)
        smoothing_spin = getattr(self, "elevation_smoothing_spin", None)
        movable = [route_label, dem_title, dem_status, smoothing_title, smoothing_spin]
        movable.extend(getattr(self, "_route_buttons", []))
        for widget in movable:
            if widget is not None:
                layout.removeWidget(widget)

        if route_label is not None:
            layout.addWidget(route_label, 0, 0, 1, 3)
        buttons = getattr(self, "_route_buttons", [])
        for column, button in enumerate(buttons[:3]):
            layout.addWidget(button, 1, column)

        if compact:
            if dem_title is not None:
                layout.addWidget(dem_title, 2, 0, 1, 3)
            if dem_status is not None:
                layout.addWidget(dem_status, 3, 0, 1, 3)
            if smoothing_title is not None:
                layout.addWidget(smoothing_title, 4, 0, 1, 3)
            if smoothing_spin is not None:
                layout.addWidget(smoothing_spin, 5, 0, 1, 3)
        else:
            if dem_title is not None:
                layout.addWidget(dem_title, 2, 0)
            if dem_status is not None:
                layout.addWidget(dem_status, 2, 1, 1, 2)
            if smoothing_title is not None:
                layout.addWidget(smoothing_title, 3, 0)
            if smoothing_spin is not None:
                layout.addWidget(smoothing_spin, 3, 1, 1, 2)

        layout.invalidate()
        if getattr(self, "_route_group", None) is not None:
            self._route_group.updateGeometry()

    def _apply_sidebar_form_mode(self, viewport_width: int | None = None) -> None:
        scroll = getattr(self, "parameter_scroll_area", None)
        if not isinstance(scroll, QScrollArea) or scroll.widget() is None:
            return
        width = int(viewport_width if viewport_width is not None else scroll.viewport().width())
        compact = width < 490
        policy = (
            QFormLayout.RowWrapPolicy.WrapAllRows
            if compact
            else QFormLayout.RowWrapPolicy.WrapLongRows
        )
        content = scroll.widget()
        for form in content.findChildren(QFormLayout):
            form.setRowWrapPolicy(policy)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(7)
        self._reflow_route_card(compact)

    def _install_axis_guide(self) -> None:
        container = getattr(self, "combined_container", None)
        layout = container.layout() if container is not None else None
        if layout is None:
            return
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setStyleSheet(
            "QLabel { padding: 3px 5px; color: palette(mid); background: transparent; }"
        )
        label.setToolTip(
            "Die Kennbuchstaben stehen auch vor jedem Signal. So ist sofort sichtbar, "
            "welche Y-Achse zu welcher Linie gehört."
        )
        layout.insertWidget(0, label)
        self.axis_guide_label = label

    def _label_signal_actions_with_axes(self) -> None:
        for key, action in getattr(self, "signal_actions", {}).items():
            definition = self._signal_definition(key)
            if definition is None:
                continue
            group = definition[1]
            badge = _AXIS_BADGES.get(group, "?")
            text = action.text()
            if not text.startswith("["):
                action.setText(f"[{badge}]  {text}")

    def _visible_axis_groups(self) -> set[str]:
        return {
            group
            for group, axis in getattr(self, "_combined_axes", {}).items()
            if axis.isVisible()
        }

    def _focused_axis_group(self) -> str | None:
        key = getattr(self, "_focused_combined_key", None)
        item = getattr(self, "_combined_items", {}).get(key) if key is not None else None
        return item[1] if item is not None else None

    def _refresh_axis_guide(self, groups: set[str] | None = None) -> None:
        label = self.axis_guide_label
        if label is None:
            return
        active = groups if groups is not None else self._visible_axis_groups()
        focused_group = self._focused_axis_group()
        parts: list[str] = []
        for group in _AXIS_ORDER:
            if group not in active:
                continue
            name, unit, color = self._axis_definition(group)
            badge = _AXIS_BADGES[group]
            if focused_group is not None and group != focused_group:
                rgb = (145, 145, 145)
                weight = "normal"
            else:
                rgb = color
                weight = "700" if group == focused_group else "600"
            parts.append(
                f"<span style='color:rgb({rgb[0]},{rgb[1]},{rgb[2]});font-weight:{weight}'>"
                f"[{badge}] {name} [{unit}]</span>"
            )
        label.setText("<b>Y-Achsen:</b>&nbsp;&nbsp;" + "&nbsp;&nbsp;&nbsp;".join(parts))
        label.setVisible(bool(parts))

    def _style_axes_for_focus(self, groups: set[str] | None = None) -> None:
        active = groups if groups is not None else self._visible_axis_groups()
        focused_group = self._focused_axis_group()
        for group, axis in getattr(self, "_combined_axes", {}).items():
            if group not in active:
                continue
            _name, unit, color = self._axis_definition(group)
            badge = _AXIS_BADGES[group]
            axis.setLabel(f"[{badge}]", units=unit)
            if focused_group is None or focused_group == group:
                pen = pg.mkPen(color, width=2.0 if focused_group == group else 1.2)
                text_pen = pg.mkPen(color)
            else:
                pen = pg.mkPen((*color, 70), width=1.0)
                text_pen = pg.mkPen((*color, 95))
            try:
                axis.setPen(pen)
                axis.setTextPen(text_pen)
                axis.setStyle(showValues=True)
            except (AttributeError, TypeError):
                pass
        self._refresh_axis_guide(active)

    def _set_combined_axis_visibility(self, groups: set[str]) -> None:
        super()._set_combined_axis_visibility(groups)
        if self._v11_ready:
            self._style_axes_for_focus(groups)

    def _refresh_combined_legend(self) -> None:
        super()._refresh_combined_legend()
        if not self._v11_ready or not hasattr(self, "combined_legend_bar"):
            return
        buttons = self.combined_legend_bar.findChildren(QToolButton)
        for (key, (_item, group)), button in zip(self._combined_items.items(), buttons):
            badge = _AXIS_BADGES.get(group, "?")
            text = button.text()
            if not text.startswith("["):
                button.setText(f"[{badge}]  {text}")
            name, unit, _color = self._axis_definition(group)
            button.setToolTip(
                f"Y-Achse [{badge}] {name} [{unit}]. Anklicken, um die Linie und ihre Achse hervorzuheben."
            )
        self._refresh_axis_guide()

    def _focus_combined_line(self, key: str) -> None:
        super()._focus_combined_line(key)
        if self._v11_ready:
            self._style_axes_for_focus()

    def _apply_responsive_layout(self, force: bool = False) -> None:
        super()._apply_responsive_layout(force=force)
        if not self._v11_ready:
            return
        self._fix_sidebar_minimum_size_constraint()
        self._apply_sidebar_form_mode()
        self._style_axes_for_focus()

    def reload_route(self, *_args, **kwargs) -> None:
        super().reload_route(*_args, **kwargs)
        if hasattr(self, "route_path_label"):
            self._update_route_path_display()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
