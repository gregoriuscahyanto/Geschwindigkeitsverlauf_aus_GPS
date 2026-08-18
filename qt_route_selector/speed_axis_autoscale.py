from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

import numpy as np
from PySide6.QtCore import QTimer


_PADDING_FRACTION = 0.08


def _finite_values(values: Any) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return np.empty(0, dtype=float)
    return array[np.isfinite(array)]


def padded_y_range(
    value_sets: Iterable[Any],
    *,
    padding_fraction: float = _PADDING_FRACTION,
) -> tuple[float, float] | None:
    """Return a purely data-driven y range for the supplied visible lines.

    No application-specific absolute y limits are used. The range is derived
    from the finite minimum/maximum of the plotted data and enlarged by a
    relative fraction of the actual data span. Constant non-zero lines use their
    own magnitude as the scale. A completely zero-valued set is left to
    pyqtgraph's native auto-range because there is no meaningful data span from
    which an application range could be derived.
    """

    finite_sets = [finite for values in value_sets if (finite := _finite_values(values)).size]
    if not finite_sets:
        return None

    minimum = min(float(np.min(values)) for values in finite_sets)
    maximum = max(float(np.max(values)) for values in finite_sets)
    if not (math.isfinite(minimum) and math.isfinite(maximum)):
        return None

    span = maximum - minimum
    if span > 0.0:
        padding = span * max(0.0, float(padding_fraction))
    else:
        magnitude = abs(maximum)
        if magnitude <= 0.0:
            return None
        padding = magnitude * max(0.0, float(padding_fraction))

    lower = minimum - padding
    upper = maximum + padding
    if not (math.isfinite(lower) and math.isfinite(upper) and upper > lower):
        return None
    return lower, upper


def _item_is_visible(item: Any) -> bool:
    checker = getattr(item, "isVisible", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            pass
    return True


def _item_y_data(item: Any) -> np.ndarray:
    if not _item_is_visible(item):
        return np.empty(0, dtype=float)

    getter = getattr(item, "getData", None)
    if callable(getter):
        try:
            _x, y = getter()
            finite = _finite_values(y)
            if finite.size:
                return finite
        except Exception:
            pass

    y_data = getattr(item, "yData", None)
    return _finite_values(y_data)


def _apply_view_y_range(view: Any, value_sets: Iterable[Any]) -> bool:
    bounds = padded_y_range(value_sets)
    if bounds is None:
        # With no usable span, let pyqtgraph choose a non-degenerate range.
        try:
            view.enableAutoRange(axis=1, enable=True)
        except Exception:
            pass
        return False

    lower, upper = bounds
    try:
        view.enableAutoRange(axis=1, enable=False)
    except Exception:
        pass
    try:
        # Padding is already included above; do not let a second absolute or
        # implementation-specific margin alter the data-derived contract.
        view.setYRange(lower, upper, padding=0.0)
        return True
    except Exception:
        return False


def _plot_data_items(plot: Any) -> list[Any]:
    plot_item = getattr(plot, "plotItem", None)
    if plot_item is None:
        getter = getattr(plot, "getPlotItem", None)
        if callable(getter):
            try:
                plot_item = getter()
            except Exception:
                plot_item = None
    if plot_item is None:
        return []

    getter = getattr(plot_item, "listDataItems", None)
    if not callable(getter):
        return []
    try:
        return list(getter())
    except Exception:
        return []


def _plot_view(plot: Any) -> Any | None:
    plot_item = getattr(plot, "plotItem", None)
    if plot_item is None:
        getter = getattr(plot, "getPlotItem", None)
        if callable(getter):
            try:
                plot_item = getter()
            except Exception:
                plot_item = None
    if plot_item is None:
        return None
    getter = getattr(plot_item, "getViewBox", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            pass
    return getattr(plot_item, "vb", None)


def apply_plot_y_range(plot: Any) -> bool:
    """Fit one ordinary PlotWidget to every visible PlotDataItem with padding."""

    view = _plot_view(plot)
    if view is None:
        return False
    values = [_item_y_data(item) for item in _plot_data_items(plot)]
    values = [value for value in values if value.size]
    if not values:
        return False
    return _apply_view_y_range(view, values)


def speed_axis_upper_bound(
    result: Mapping[str, Any] | None,
    *,
    minimum_kmh: float | None = None,
) -> float:
    """Compatibility helper returning a data-derived speed upper bound.

    The UI no longer uses this function to impose a speed-axis limit. It remains
    available for callers/tests that need a numerical bound, but it has no fixed
    default minimum and no rounded or absolute headroom.
    """

    if not result:
        return float(minimum_kmh) if minimum_kmh is not None else float("nan")

    value_sets: list[Any] = []
    for section_name, key in (
        ("time", "speed_kmh"),
        ("time", "target_kmh"),
        ("distance", "actual_speed_kmh"),
        ("distance", "planned_speed_kmh"),
        ("distance", "road_limit_kmh"),
        ("distance", "surface_limit_kmh"),
    ):
        section = result.get(section_name, {})
        if isinstance(section, Mapping):
            value_sets.append(section.get(key, []))

    summary = result.get("summary", {})
    if isinstance(summary, Mapping):
        value_sets.append([summary.get("maximum_speed_kmh", float("nan"))])

    bounds = padded_y_range(value_sets)
    if bounds is None:
        return float(minimum_kmh) if minimum_kmh is not None else float("nan")
    upper = float(bounds[1])
    if minimum_kmh is not None:
        upper = max(upper, float(minimum_kmh))
    return upper


class SpeedAxisAutoscaleMixin:
    """Data-driven y autoscaling for every currently plotted line.

    Historical simulation layers contain several independent plot implementations,
    including the V8 combined multi-axis ViewBoxes. This mixin deliberately sits
    before those layers in the final MRO and therefore replaces their fixed
    road-limit-based y scaling after they finish drawing.
    """

    _ordinary_plot_names = (
        "speed_plot",
        "longitudinal_plot",
        "elevation_plot",
        "resistance_plot",
    )

    def _apply_ordinary_y_ranges(self) -> None:
        for name in self._ordinary_plot_names:
            plot = getattr(self, name, None)
            if plot is not None:
                apply_plot_y_range(plot)

    def _combined_group_values(self, group: str) -> list[np.ndarray]:
        values: list[np.ndarray] = []
        items = getattr(self, "_combined_items", {})
        if isinstance(items, Mapping):
            for payload in items.values():
                if not isinstance(payload, tuple) or len(payload) != 2:
                    continue
                item, item_group = payload
                if item_group != group:
                    continue
                finite = _item_y_data(item)
                if finite.size:
                    values.append(finite)

        # Horizontal auxiliary reference lines (currently y=0 for acceleration
        # and power) are also visible plot lines and must stay inside the range.
        aux_items = getattr(self, "_combined_aux_items", [])
        for item, item_group in list(aux_items or []):
            if item_group != group or not _item_is_visible(item):
                continue
            getter = getattr(item, "value", None)
            if callable(getter):
                try:
                    value = float(getter())
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value):
                    values.append(np.asarray([value], dtype=float))
        return values

    def _apply_combined_y_ranges(self) -> None:
        views = getattr(self, "_combined_views", {})
        if not isinstance(views, Mapping):
            return
        for group, view in views.items():
            values = self._combined_group_values(str(group))
            if values:
                _apply_view_y_range(view, values)

        sync = getattr(self, "_sync_combined_views", None)
        if callable(sync):
            try:
                sync()
            except Exception:
                pass

    def _apply_all_y_ranges(self) -> None:
        self._apply_ordinary_y_ranges()
        self._apply_combined_y_ranges()

    def _focus_speed_axis(self) -> None:
        # Older layers call this after every plot rebuild. Keep the method name
        # for compatibility, but derive the range from the actually visible
        # speed-plot lines rather than from a road-limit formula.
        plot = getattr(self, "speed_plot", None)
        if plot is not None:
            apply_plot_y_range(plot)

    def _finish_combined_ranges(self, groups: set[str], comparison: bool) -> None:
        # Let V8 keep its x-range/linking setup, then replace every y range with
        # the finite min/max of exactly the lines that V8 just added.
        super()._finish_combined_ranges(groups, comparison)
        self._apply_combined_y_ranges()

    def reset_plot_views(self) -> None:
        super().reset_plot_views()
        self._apply_all_y_ranges()
        # Some historical Qt/pyqtgraph layers defer geometry/AutoRange work.
        # Re-apply the same data-derived ranges after those event-loop turns.
        QTimer.singleShot(0, self._apply_all_y_ranges)
        QTimer.singleShot(50, self._apply_all_y_ranges)

    def _update_plots(self) -> None:
        super()._update_plots()
        self._apply_all_y_ranges()
        QTimer.singleShot(0, self._apply_all_y_ranges)

    def _set_plot_mode(self, mode: str) -> None:
        super()._set_plot_mode(mode)
        self._apply_all_y_ranges()
        QTimer.singleShot(0, self._apply_all_y_ranges)


__all__ = [
    "SpeedAxisAutoscaleMixin",
    "apply_plot_y_range",
    "padded_y_range",
    "speed_axis_upper_bound",
]
