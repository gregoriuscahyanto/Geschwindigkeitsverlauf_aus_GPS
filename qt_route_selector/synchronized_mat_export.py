from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.io import loadmat, savemat

try:
    from .mat_export import export_matlab_simulation as _base_export
except ImportError:
    from mat_export import export_matlab_simulation as _base_export


# Numeric representation for an intentionally unlimited value.  MATLAB/Simulink
# users can feed the exported vectors directly without special Inf handling.
MAT_NO_LIMIT_SENTINEL = 65_535.0

_EXCLUDED_PREFIXES = (
    "route_",
    "traffic_light_",
    "post_curve_",
    "overtaking_",
    "event_",
    "segment_",
    "osm_signal_",
    "leg_",
    "param_",
    "summary_",
    "comparison_",
    "load_",
)

# These signals are part of the strict simulation contract.  If one of them has
# no usable values at all, exporting a plausible-looking zero vector would hide
# a real data problem, therefore the export is aborted instead.
_REQUIRED_SIGNALS = {
    "time_s",
    "distance_m",
    "lat_deg",
    "lon_deg",
    "elevation_m",
    "grade_pct",
    "curve_radius_m",
    "v_kmh",
    "v_target_kmh",
    "a_mps2",
}

_SCALAR_PREFIXES = ("param_", "summary_")
_SCALAR_NAMES = {
    "trailer_enabled",
    "e_traction_kwh",
    "e_recuperation_kwh",
    "e_net_kwh",
    "e_braking_kwh",
    "p_p95_positive_kw",
    "p_max_kw",
    "p_min_kw",
}


def _flat(value: Any) -> np.ndarray:
    try:
        return np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return np.empty(0, dtype=np.float64)


def _column(value: Any, length: int) -> np.ndarray:
    values = _flat(value)
    if values.size != length:
        raise ValueError(
            f"Synchronisiertes Signal hat Länge {values.size}, erwartet wird {length}."
        )
    return values.reshape(-1, 1)


def _sorted_unique_axis(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # Keep +/-Inf in y here because e.g. an infinite curve radius means
    # deliberately "no curve limit".  It is converted to a finite sentinel only
    # after synchronization.
    valid = np.isfinite(x) & ~np.isnan(y)
    x = x[valid]
    y = y[valid]
    if x.size == 0:
        return x, y
    order = np.argsort(x, kind="stable")
    x = x[order]
    y = y[order]
    x, indexes = np.unique(x, return_index=True)
    return x, y[indexes]


def _interp(route_distance: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    x, y = _sorted_unique_axis(route_distance, values)
    if x.size == 0:
        return np.full(query.size, np.nan, dtype=np.float64)
    finite_y = np.isfinite(y)
    if not np.any(finite_y):
        return np.full(query.size, np.nan, dtype=np.float64)
    x = x[finite_y]
    y = y[finite_y]
    if x.size == 1:
        return np.full(query.size, y[0], dtype=np.float64)
    return np.interp(query, x, y)


def _nearest(route_distance: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    x, y = _sorted_unique_axis(route_distance, values)
    if x.size == 0:
        return np.full(query.size, np.nan, dtype=np.float64)
    if x.size == 1:
        return np.full(query.size, y[0], dtype=np.float64)
    positions = np.searchsorted(x, query, side="left")
    right = np.clip(positions, 0, x.size - 1)
    left = np.clip(positions - 1, 0, x.size - 1)
    use_right = np.abs(query - x[right]) < np.abs(query - x[left])
    return y[np.where(use_right, right, left)]


def _route_field_uses_interpolation(name: str) -> bool:
    continuous_tokens = (
        "lat_deg",
        "lon_deg",
        "elevation",
        "grade",
        "planned",
        "actual",
        "noise",
        "boost",
        "target",
    )
    return any(token in name for token in continuous_tokens)


def _uses_no_limit_sentinel(name: str) -> bool:
    return "curve_radius_m" in name or "limit_kmh" in name


def _uses_nearest_gap_fill(name: str) -> bool:
    tokens = (
        "points",
        "limit_kmh",
        "sample_index",
        "_active",
        "_enabled",
        "_count",
        "seed",
    )
    return any(token in name for token in tokens)


def _nearest_fill(values: np.ndarray, finite: np.ndarray) -> np.ndarray:
    indexes = np.arange(values.size, dtype=int)
    valid_indexes = indexes[finite]
    positions = np.searchsorted(valid_indexes, indexes, side="left")
    right = valid_indexes[np.clip(positions, 0, valid_indexes.size - 1)]
    left = valid_indexes[np.clip(positions - 1, 0, valid_indexes.size - 1)]
    choose_right = np.abs(indexes - right) < np.abs(indexes - left)
    source = np.where(choose_right, right, left)
    result = values.copy()
    missing = ~finite
    result[missing] = values[source[missing]]
    return result


def _finite_signal(name: str, value: Any, length: int) -> np.ndarray | None:
    """Return one finite N-vector, filling only recoverable internal gaps.

    - intentional +Inf for limits/radii becomes MAT_NO_LIMIT_SENTINEL;
    - isolated NaN/-Inf gaps are interpolated (or nearest-filled for discrete
      channels);
    - a completely missing required signal aborts the export;
    - a completely missing optional signal is omitted instead of exporting an
      invented all-zero series.
    """

    values = _flat(value)
    if values.size != length:
        raise ValueError(
            f"MAT-Signal {name!r} hat Länge {values.size}, erwartet wird {length}."
        )

    if _uses_no_limit_sentinel(name):
        values = values.copy()
        values[np.isposinf(values)] = MAT_NO_LIMIT_SENTINEL

    finite = np.isfinite(values)
    if np.all(finite):
        return values.reshape(-1, 1)

    if name in {"time_s", "distance_m"}:
        missing = int(np.count_nonzero(~finite))
        raise ValueError(
            f"MAT-Signal {name!r} enthält {missing} ungültige Werte; "
            "Zeit- und Distanzachse dürfen nicht repariert werden."
        )

    if not np.any(finite):
        if name in _REQUIRED_SIGNALS:
            raise ValueError(
                f"MAT-Signal {name!r} enthält keinen einzigen gültigen Wert. "
                "Der Export wurde abgebrochen, damit keine erfundenen Simulationsdaten entstehen."
            )
        return None

    indexes = np.arange(length, dtype=np.float64)
    if _uses_nearest_gap_fill(name):
        repaired = _nearest_fill(values, finite)
    else:
        repaired = np.interp(indexes, indexes[finite], values[finite])

    if not np.all(np.isfinite(repaired)):
        raise ValueError(f"MAT-Signal {name!r} konnte nicht vollständig repariert werden.")
    return np.asarray(repaired, dtype=np.float64).reshape(-1, 1)


def _synchronized_signals(workspace: Mapping[str, Any]) -> dict[str, np.ndarray]:
    time_s = _flat(workspace.get("time_s", []))
    distance_m = _flat(workspace.get("distance_m", []))
    if time_s.size == 0:
        raise ValueError("MAT-Export enthält keinen Zeitvektor time_s.")
    if distance_m.size != time_s.size:
        raise ValueError(
            "distance_m und time_s müssen für den synchronisierten Simulationseingang "
            "dieselbe Länge besitzen."
        )

    n = time_s.size
    signals: dict[str, np.ndarray] = {
        "sample_index": np.arange(n, dtype=np.float64).reshape(-1, 1),
    }

    # Already time-synchronous arrays from the base exporter.
    for name, value in workspace.items():
        if name.startswith("__") or name == "sim":
            continue
        if name.startswith(_EXCLUDED_PREFIXES):
            continue
        array = _flat(value)
        if array.size == n:
            signals[name] = array.reshape(-1, 1)

    # Convert every route_* series that genuinely lives on route_distance_m to
    # the one master time/distance grid.  Raw route geometry is never kept in
    # the final MAT file.
    route_distance = _flat(workspace.get("route_distance_m", []))
    if route_distance.size >= 1:
        for name, value in workspace.items():
            if not name.startswith("route_") or name == "route_distance_m":
                continue
            source = _flat(value)
            if source.size != route_distance.size:
                continue
            target_name = name[len("route_") :]
            if target_name in signals:
                continue
            if _route_field_uses_interpolation(target_name):
                synchronized = _interp(route_distance, source, distance_m)
            else:
                synchronized = _nearest(route_distance, source, distance_m)
            signals[target_name] = synchronized.reshape(-1, 1)

    # Numeric UI parameters and scalar summaries are useful simulation inputs as
    # well.  Repeat them across the same N samples instead of exporting scalars
    # with a different length.
    for name, value in workspace.items():
        if not (
            name.startswith(_SCALAR_PREFIXES)
            or name in _SCALAR_NAMES
            or (name.startswith(("e_", "p_")) and _flat(value).size == 1)
        ):
            continue
        scalar = _flat(value)
        if scalar.size != 1 or not np.isfinite(scalar[0]):
            continue
        signals.setdefault(name, np.full((n, 1), float(scalar[0]), dtype=np.float64))

    return signals


def _event_signals(
    result: Mapping[str, Any],
    time_s: np.ndarray,
    distance_m: np.ndarray,
) -> dict[str, np.ndarray]:
    """Encode variable-length event lists as N-sample numeric channels."""

    n = time_s.size
    encoded: dict[str, np.ndarray] = {}
    events = result.get("events", {})
    if not isinstance(events, Mapping):
        return encoded

    traffic_stop = np.zeros(n, dtype=np.float64)
    traffic_active = np.zeros(n, dtype=np.float64)
    traffic_dwell_s = np.zeros(n, dtype=np.float64)

    traffic = events.get("traffic_lights", [])
    if isinstance(traffic, (list, tuple)):
        for item in traffic:
            if not isinstance(item, Mapping):
                continue
            try:
                event_distance = float(item.get("distance_m", np.nan))
            except (TypeError, ValueError):
                continue
            if np.isfinite(event_distance) and n:
                traffic_stop[int(np.argmin(np.abs(distance_m - event_distance)))] = 1.0

    intervals = events.get("traffic_light_dwell_intervals_s", [])
    if isinstance(intervals, (list, tuple)):
        for interval in intervals:
            try:
                start_s, end_s = interval
                start_s = float(start_s)
                end_s = float(end_s)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(start_s) or not np.isfinite(end_s) or end_s < start_s:
                continue
            mask = (time_s >= start_s) & (time_s <= end_s)
            traffic_active[mask] = 1.0
            traffic_dwell_s[mask] = max(0.0, end_s - start_s)

    encoded["traffic_light_stop"] = traffic_stop
    encoded["traffic_light_active"] = traffic_active
    encoded["traffic_light_dwell_s"] = traffic_dwell_s

    overtaking_active = np.zeros(n, dtype=np.float64)
    overtaking = events.get("overtaking", [])
    if isinstance(overtaking, (list, tuple)):
        for item in overtaking:
            if not isinstance(item, Mapping):
                continue
            try:
                start_m = float(item.get("follow_start_m", np.nan))
                end_m = float(item.get("pass_end_m", np.nan))
            except (TypeError, ValueError):
                continue
            if np.isfinite(start_m) and np.isfinite(end_m) and end_m >= start_m:
                overtaking_active[(distance_m >= start_m) & (distance_m <= end_m)] = 1.0
    encoded["overtaking_active"] = overtaking_active

    return {name: values.reshape(-1, 1) for name, values in encoded.items()}


def export_matlab_simulation(
    result: Mapping[str, Any],
    output_path: str | Path,
    *,
    route: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    power_data: Mapping[str, Any] | None = None,
    elevation_m: np.ndarray | None = None,
    source_route: str | Path | None = None,
    source_dem: str | Path | None = None,
    comparison: Mapping[str, Any] | None = None,
) -> Path:
    """Export a strict, simulation-ready MAT workspace.

    Every variable written to the final MAT file is a finite N x 1 double vector,
    where N == len(time_s).  There are no raw route/event arrays, no scalar
    variables, no nested structs and no NaN/Inf values.  Route/project metadata
    remains in route_result_*.json, which is the canonical project file.

    For compatibility, every signal is written twice: once under its normal name
    (e.g. ``time_s``) and once as ``input_time_s``.  Both aliases are identical
    N x 1 vectors.
    """

    path = _base_export(
        result,
        output_path,
        route=route,
        parameters=parameters,
        power_data=power_data,
        elevation_m=elevation_m,
        source_route=source_route,
        source_dem=source_dem,
        comparison=comparison,
    )

    loaded = loadmat(path)
    workspace: dict[str, Any] = {
        key: value
        for key, value in loaded.items()
        if not key.startswith("__") and key != "sim"
    }

    raw_signals = _synchronized_signals(workspace)
    master_time = _flat(raw_signals.get("time_s", []))
    master_distance = _flat(raw_signals.get("distance_m", []))
    n = int(master_time.size)
    if n == 0 or master_distance.size != n:
        raise ValueError("Synchronisierter MAT-Export hat keinen gültigen Master-Zeitvektor.")

    raw_signals.update(_event_signals(result, master_time, master_distance))

    strict_signals: dict[str, np.ndarray] = {}
    for name, value in raw_signals.items():
        repaired = _finite_signal(name, value, n)
        if repaired is not None:
            strict_signals[name] = repaired

    missing_required = sorted(_REQUIRED_SIGNALS - strict_signals.keys())
    if missing_required:
        raise ValueError(
            "MAT-Export fehlen erforderliche Simulationssignale: " + ", ".join(missing_required)
        )

    # Final hard contract: every exported parameter has exactly N finite values.
    for name, value in strict_signals.items():
        array = np.asarray(value, dtype=np.float64).reshape(-1)
        if array.size != n:
            raise ValueError(f"MAT-Signal {name!r} hat {array.size} statt {n} Werte.")
        if not np.all(np.isfinite(array)):
            raise ValueError(f"MAT-Signal {name!r} enthält weiterhin NaN oder Inf.")

    final_workspace: dict[str, np.ndarray] = {}
    for name in sorted(strict_signals):
        value = np.asarray(strict_signals[name], dtype=np.float64).reshape(n, 1)
        final_workspace[name] = value
        final_workspace[f"input_{name}"] = value.copy()

    savemat(
        path,
        final_workspace,
        appendmat=False,
        do_compression=True,
        long_field_names=True,
    )
    return path


__all__ = ["MAT_NO_LIMIT_SENTINEL", "export_matlab_simulation"]
