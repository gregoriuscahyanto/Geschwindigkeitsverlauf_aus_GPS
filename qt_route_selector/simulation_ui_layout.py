from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)


_OVERSHOOT_KEYS = (
    "use_post_curve_overshoot",
    "post_curve_overshoot_kmh",
    "post_curve_overshoot_probability_pct",
    "post_curve_overshoot_distance_m",
)

_CHECKBOX_STYLE = (
    "QCheckBox {"
    " spacing:7px; padding:3px 8px 3px 5px; min-height:22px;"
    " border:1px solid palette(mid); border-radius:5px;"
    " background:palette(base); font-weight:600;"
    "}"
    "QCheckBox:checked {"
    " border:1px solid palette(highlight);"
    " background:palette(alternate-base);"
    "}"
    "QCheckBox:hover { border:1px solid palette(highlight); }"
    "QCheckBox::indicator { width:18px; height:18px; }"
)


class SimulationUiLayoutMixin:
    """Current sidebar organization without changing simulation semantics.

    The historical UI grew in several inheritance layers. This mixin only moves
    or hides already existing widgets after construction, so parameter keys,
    persistence, calculations and exports keep using exactly the same controls.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._simulation_ui_layout_ready = False
        self._collapsible_group_buttons: dict[QGroupBox, QToolButton] = {}
        self._collapsible_group_state: dict[QGroupBox, dict[str, Any]] = {}
        super().__init__(*args, **kwargs)
        self._reorganize_simulation_sidebar()
        self._simulation_ui_layout_ready = True
        self._place_project_controls_in_route()
        self._style_parameter_checkboxes()
        self._install_collapsible_parameter_cards()

    @staticmethod
    def _group(window: QWidget, title: str) -> QGroupBox | None:
        return next(
            (group for group in window.findChildren(QGroupBox) if group.title() == title),
            None,
        )

    @classmethod
    def _group_form(cls, window: QWidget, title: str) -> QFormLayout | None:
        """Return the form inside a parameter card, even when wrapped in a page.

        The old tab-to-card conversion creates a QGroupBox with a QVBoxLayout and
        puts the former tab page inside it. Therefore the QFormLayout is usually
        one level below the group rather than being the group's direct layout.
        """

        group = cls._group(window, title)
        if group is None:
            return None
        direct = group.layout()
        if isinstance(direct, QFormLayout):
            return direct
        return next(iter(group.findChildren(QFormLayout)), None)

    @staticmethod
    def _form_containing(window: QWidget, widget: QWidget) -> tuple[QFormLayout | None, int]:
        for form in window.findChildren(QFormLayout):
            row, _role = form.getWidgetPosition(widget)
            if row >= 0:
                return form, row
        return None, -1

    @staticmethod
    def _form_row_widgets(form: QFormLayout, row: int) -> list[QWidget]:
        widgets: list[QWidget] = []
        for role in (
            QFormLayout.ItemRole.LabelRole,
            QFormLayout.ItemRole.FieldRole,
            QFormLayout.ItemRole.SpanningRole,
        ):
            item = form.itemAt(row, role)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QWidget) and widget not in widgets:
                widgets.append(widget)
        return widgets

    def _move_form_control(self, key: str, target: QFormLayout) -> None:
        widget = getattr(self, "_control_widgets", {}).get(key)
        if not isinstance(widget, QWidget):
            return
        source, row = self._form_containing(self, widget)
        if source is None or source is target or row < 0:
            return

        row_widgets = self._form_row_widgets(source, row)
        label_widget = next((item for item in row_widgets if item is not widget), None)
        for item in row_widgets:
            source.removeWidget(item)

        if label_widget is not None:
            target.addRow(label_widget, widget)
        else:
            target.addRow(widget)
        source.invalidate()
        target.invalidate()

    def _hide_form_control(self, key: str) -> None:
        """Remove one control row from the visible UI but keep its model value.

        Keeping the widget in _control_widgets preserves route-file compatibility
        and deterministic simulations while avoiding a misleading control in the
        wrong parameter card.
        """

        widget = getattr(self, "_control_widgets", {}).get(key)
        if not isinstance(widget, QWidget):
            return
        source, row = self._form_containing(self, widget)
        if source is None or row < 0:
            widget.hide()
            return
        for item in self._form_row_widgets(source, row):
            source.removeWidget(item)
            item.hide()
        source.invalidate()

    def _move_overshoot_controls_to_curves(self) -> None:
        target = self._group_form(self, "Kurven")
        if target is None:
            return
        for key in _OVERSHOOT_KEYS:
            self._move_form_control(key, target)

    def _remove_random_seed_from_noise_card(self) -> None:
        # simulation_seed is a global deterministic simulation seed, not a
        # driver-noise parameter. Keep the value for reproducibility/persistence
        # but do not present it inside the Rauschen card.
        self._hide_form_control("simulation_seed")

    def _detach_persistence_controls_from_driver(self) -> None:
        save_button = getattr(self, "settings_save_button", None)
        status = getattr(self, "_settings_status_label", None)
        if not isinstance(save_button, QPushButton):
            return

        for preserved in (save_button, status):
            if not isinstance(preserved, QWidget):
                continue
            form, row = self._form_containing(self, preserved)
            if form is None or row < 0:
                continue
            for widget in self._form_row_widgets(form, row):
                form.removeWidget(widget)
                if widget is not preserved:
                    widget.hide()
                    widget.deleteLater()

    def _show_advanced_groups_directly(self) -> None:
        # V10 intentionally put these groups behind a single "Weitere Parameter"
        # disclosure. The current UI shows the cards directly instead.
        disclosure = getattr(self, "advanced_parameters_button", None)
        if isinstance(disclosure, QToolButton):
            disclosure.hide()
        setter = getattr(self, "_set_advanced_parameters_visible", None)
        if callable(setter):
            setter(True)
        for title in ("Ampeln", "Überholen", "Rauschen"):
            group = self._group(self, title)
            if group is not None:
                group.show()

    def _reorganize_simulation_sidebar(self) -> None:
        self._detach_persistence_controls_from_driver()
        self._move_overshoot_controls_to_curves()
        self._remove_random_seed_from_noise_card()
        self._show_advanced_groups_directly()

    @staticmethod
    def _set_checkbox_state_text(widget: QCheckBox, checked: bool) -> None:
        widget.setText("Ein" if checked else "Aus")

    def _style_parameter_checkboxes(self) -> None:
        """Make boolean controls visibly recognizable and easy to click."""

        controls = getattr(self, "_control_widgets", {})
        for widget in controls.values():
            if not isinstance(widget, QCheckBox) or widget.isHidden():
                continue
            widget.setMinimumWidth(72)
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
            widget.setStyleSheet(_CHECKBOX_STYLE)
            self._set_checkbox_state_text(widget, widget.isChecked())
            if not bool(widget.property("clearCheckboxStateTextConnected")):
                widget.toggled.connect(
                    lambda checked, current=widget: self._set_checkbox_state_text(
                        current, bool(checked)
                    )
                )
                widget.setProperty("clearCheckboxStateTextConnected", True)

    def _refresh_control_highlights(self, changed: set[str]) -> None:
        # V13 restores each widget's original stylesheet whenever parameters are
        # recalculated. Re-apply the accessibility styling afterwards so the
        # checkboxes stay visible instead of reverting to the tiny native mark.
        super()._refresh_control_highlights(changed)
        self._style_parameter_checkboxes()

    def _place_project_controls_in_route(self) -> None:
        if not self._simulation_ui_layout_ready:
            return
        route = self._group(self, "Route")
        layout = route.layout() if route is not None else None
        save_button = getattr(self, "settings_save_button", None)
        status = getattr(self, "_settings_status_label", None)
        if not isinstance(layout, QGridLayout) or not isinstance(save_button, QPushButton):
            return

        # Remove all movable route widgets first. The inherited responsive
        # reflow may call this method repeatedly when the sidebar width changes.
        dem_title = getattr(self, "_dem_title_label", None)
        dem_status = getattr(self, "dem_status_label", None)
        smoothing_title = getattr(self, "_smoothing_title_label", None)
        smoothing_spin = getattr(self, "elevation_smoothing_spin", None)
        for widget in (save_button, status, dem_title, dem_status, smoothing_title, smoothing_spin):
            if isinstance(widget, QWidget):
                layout.removeWidget(widget)

        compact = bool(getattr(self, "_route_card_compact", False))
        layout.addWidget(save_button, 2, 0, 1, 3)
        if isinstance(status, QLabel):
            status.setWordWrap(True)
            layout.addWidget(status, 3, 0, 1, 3)

        base_row = 4
        if compact:
            if isinstance(dem_title, QWidget):
                layout.addWidget(dem_title, base_row, 0, 1, 3)
            if isinstance(dem_status, QWidget):
                layout.addWidget(dem_status, base_row + 1, 0, 1, 3)
            if isinstance(smoothing_title, QWidget):
                layout.addWidget(smoothing_title, base_row + 2, 0, 1, 3)
            if isinstance(smoothing_spin, QWidget):
                layout.addWidget(smoothing_spin, base_row + 3, 0, 1, 3)
        else:
            if isinstance(dem_title, QWidget):
                layout.addWidget(dem_title, base_row, 0)
            if isinstance(dem_status, QWidget):
                layout.addWidget(dem_status, base_row, 1, 1, 2)
            if isinstance(smoothing_title, QWidget):
                layout.addWidget(smoothing_title, base_row + 1, 0)
            if isinstance(smoothing_spin, QWidget):
                layout.addWidget(smoothing_spin, base_row + 1, 1, 1, 2)

        layout.invalidate()
        route.updateGeometry()

    def _reflow_route_card(self, compact: bool) -> None:
        super()._reflow_route_card(compact)
        self._place_project_controls_in_route()

    def _sidebar_parameter_groups(self) -> list[QGroupBox]:
        scroll = getattr(self, "parameter_scroll_area", None)
        content = scroll.widget() if scroll is not None and hasattr(scroll, "widget") else None
        if content is None:
            return []

        result: list[QGroupBox] = []
        for group in content.findChildren(QGroupBox):
            if not group.title().strip():
                continue
            parent = group.parentWidget()
            layout = parent.layout() if parent is not None else None
            if layout is None or layout.indexOf(group) < 0:
                continue
            # Only top-level cards in the sidebar get a disclosure arrow. Nested
            # technical groups keep their own behavior.
            ancestor = parent
            nested_group = False
            while ancestor is not None and ancestor is not content:
                if isinstance(ancestor, QGroupBox):
                    nested_group = True
                    break
                ancestor = ancestor.parentWidget()
            if not nested_group:
                result.append(group)
        return result

    def _install_collapsible_parameter_cards(self) -> None:
        for group in self._sidebar_parameter_groups():
            if group in self._collapsible_group_buttons:
                continue
            button = QToolButton(group)
            button.setAutoRaise(True)
            button.setCheckable(True)
            button.setChecked(True)
            button.setArrowType(Qt.ArrowType.DownArrow)
            button.setToolTip(f"{group.title()} auf- oder zuklappen")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(24, 20)
            button.setStyleSheet(
                "QToolButton { border:0; padding:0; background:transparent; }"
                "QToolButton:hover { background:palette(alternate-base); border-radius:4px; }"
            )
            button.toggled.connect(
                lambda expanded, current=group: self._set_parameter_group_expanded(
                    current, bool(expanded)
                )
            )
            self._collapsible_group_buttons[group] = button
            self._collapsible_group_state[group] = {
                "minimum_height": group.minimumHeight(),
                "maximum_height": group.maximumHeight(),
                "children": {},
            }
            group.installEventFilter(self)
            self._position_group_toggle(group)
            button.raise_()

    def _position_group_toggle(self, group: QGroupBox) -> None:
        button = self._collapsible_group_buttons.get(group)
        if button is None:
            return
        button.move(max(4, group.width() - button.width() - 8), 2)
        button.raise_()

    def _set_parameter_group_expanded(self, group: QGroupBox, expanded: bool) -> None:
        button = self._collapsible_group_buttons.get(group)
        state = self._collapsible_group_state.get(group)
        if button is None or state is None:
            return

        button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        direct_children = [
            child
            for child in group.findChildren(
                QWidget,
                options=Qt.FindChildOption.FindDirectChildrenOnly,
            )
            if child is not button
        ]

        if not expanded:
            state["children"] = {child: child.isVisible() for child in direct_children}
            for child in direct_children:
                child.hide()
            group.setMinimumHeight(32)
            group.setMaximumHeight(32)
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            visible_state = state.get("children", {})
            for child in direct_children:
                if visible_state.get(child, True):
                    child.show()
            group.setMinimumHeight(int(state.get("minimum_height", 0)))
            group.setMaximumHeight(int(state.get("maximum_height", 16_777_215)))
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            group.updateGeometry()

        self._position_group_toggle(group)
        scroll = getattr(self, "parameter_scroll_area", None)
        content = scroll.widget() if scroll is not None and hasattr(scroll, "widget") else None
        if content is not None:
            content.updateGeometry()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if isinstance(watched, QGroupBox) and watched in self._collapsible_group_buttons:
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                self._position_group_toggle(watched)
        return super().eventFilter(watched, event)


__all__ = ["SimulationUiLayoutMixin"]
