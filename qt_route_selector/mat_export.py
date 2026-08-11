from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.io import savemat

try:
    from .load_collective_curve import cumulative_load_curve
except ImportError:
    from load_collective_curve import cumulative_load_curve


def _double_vector(value: Any, length: int | None = None, fill: float = np.nan) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        array = np.empty(0, dtype=np.float64)
    if length is not None and array.size != length:
        result = np.full(length, fill, dtype=np.float64)
        if array.size:
            count = min(length, array.size)
            result[:count] = array[:count]
        array = result
    return np.asarray(array, dtype=np.float64).reshape(-1, 1)


def _double_scalar(value: Any, default: float = np.nan) -> np.ndarray:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return np.asarray([[number]], dtype=np.float64)


def _flat(vector: np.ndarray) -> np.ndarray:
    return np.asarray(vector, dtype=np.float64).reshape(-1)


def _interp_finite(distance_m: np.ndarray, values: np.ndarray, query_m: np.ndarray) -> np.ndarray:
    query = _flat(query_m)
    if query.size == 0:
        return np.empty((0, 1), dtype=np.float64)
    distance = _flat(distance_m)
    data = _flat(values)
    if distance.size != data.size or distance.size == 0:
        return _double_vector([], query.size)
    finite = np.isfinite(distance) & np.isfinite(data)
    if not np.any(finite):
        return _double_vector([], query.size)
    x = distance[finite]
    y = data[finite]
    order = np.argsort(x, kind="stable")
    x = x[order]
    y = y[order]
    x, indexes = np.unique(x, return_index=True)
    y = y[indexes]
    if x.size == 1:
        return _double_vector(np.full(query.size, y[0], dtype=np.float64))
    return _double_vector(np.interp(query, x, y))


def _nearest_values(distance_m: np.ndarray, values: np.ndarray, query_m: np.ndarray) -> np.ndarray:
    query = _flat(query_m)
    if query.size == 0:
        return np.empty((0, 1), dtype=np.float64)
    distance = _flat(distance_m)
    data = _flat(values)
    if distance.size != data.size or distance.size == 0:
        return _double_vector([], query.size)
    valid = np.isfinite(distance) & ~np.isnan(data)
    if not np.any(valid):
        return _double_vector([], query.size)
    x = distance[valid]
    y = data[valid]
    order = np.argsort(x, kind="stable")
    x = x[order]
    y = y[order]
    x, indexes = np.unique(x, return_index=True)
    y = y[indexes]
    if x.size == 1:
        return _double_vector(np.full(query.size, y[0], dtype=np.float64))
    positions = np.searchsorted(x, query, side="left")
    right = np.clip(positions, 0, x.size - 1)
    left = np.clip(positions - 1, 0, x.size - 1)
    choose_right = np.abs(query - x[right]) < np.abs(query - x[left])
    return _double_vector(y[np.where(choose_right, right, left)])


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(name)).strip("_") or "value"
    if not cleaned[0].isalpha():
        cleaned = f"v_{cleaned}"
    return cleaned[:63]


def _is_number(value: Any) -> bool:
    return isinstance(value, (bool, int, float, np.number))


def _add_scalar_mapping(
    prefix: str,
    mapping: Mapping[str, Any],
    payload: dict[str, np.ndarray],
) -> None:
    """Flatten only compact numeric scalars/arrays from a mapping."""
    for key, value in mapping.items():
        name = _safe_name(f"{prefix}_{key}" if prefix else str(key))
        if _is_number(value):
            payload.setdefault(name, _double_scalar(value))
        elif isinstance(value, np.ndarray):
            try:
                array = np.asarray(value, dtype=np.float64)
            except (TypeError, ValueError):
                continue
            if array.ndim == 0:
                payload.setdefault(name, _double_scalar(array.item()))
            elif array.ndim == 1:
                payload.setdefault(name, _double_vector(array))
            else:
                payload.setdefault(name, array)
        elif isinstance(value, Mapping):
            _add_scalar_mapping(name, value, payload)
        elif isinstance(value, (list, tuple)) and value:
            try:
                array = np.asarray(value, dtype=np.float64)
            except (TypeError, ValueError):
                continue
            if array.ndim <= 1:
                payload.setdefault(name, _double_vector(array))
            else:
                payload.setdefault(name, array)


def _add_record_arrays(
    prefix: str,
    records: Sequence[Any],
    payload: dict[str, np.ndarray],
) -> None:
    """Store a list of records column-wise instead of one variable per record."""
    rows = [row for row in records if isinstance(row, Mapping)]
    if not rows:
        return
    keys = sorted({str(key) for row in rows for key in row.keys()})
    for key in keys:
        values = [row.get(key) for row in rows]
        name = _safe_name(f"{prefix}_{key}")
        if all(value is None or _is_number(value) for value in values):
            if any(_is_number(value) for value in values):
                payload.setdefault(
                    name,
                    _double_vector(
                        [np.nan if value is None else float(value) for value in values]
                    ),
                )
            continue

        converted: list[np.ndarray] = []
        shape: tuple[int, ...] | None = None
        valid = True
        for value in values:
            if value is None:
                valid = False
                break
            try:
                array = np.asarray(value, dtype=np.float64)
            except (TypeError, ValueError):
                valid = False
                break
            if array.ndim == 0:
                array = array.reshape(1)
            if shape is None:
                shape = array.shape
            elif array.shape != shape:
                valid = False
                break
            converted.append(array)
        if valid and converted:
            stacked = np.stack(converted, axis=0)
            if stacked.ndim == 2 and stacked.shape[1] == 1:
                stacked = stacked.reshape(-1, 1)
            payload.setdefault(name, np.asarray(stacked, dtype=np.float64))


def _add_optional_numeric_series(
    mapping: Mapping[str, Any],
    excluded: set[str],
    prefix: str,
    payload: dict[str, np.ndarray],
    expected_length: int,
) -> None:
    for key, value in mapping.items():
        if key in excluded:
            continue
        try:
            array = np.asarray(value, dtype=np.float64)
        except (TypeError, ValueError):
            continue
        if array.ndim != 1 or array.size != expected_length:
            continue
        payload.setdefault(_safe_name(f"{prefix}_{key}"), _double_vector(array))


def _route_coordinates(route: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lat: list[float] = []
    lon: list[float] = []
    ele: list[float] = []
    for point in route.get("coordinates", []) or []:
        if not isinstance(point, Mapping):
            continue
        try:
            lat.append(float(point.get("latitude", np.nan)))
            lon.append(float(point.get("longitude", np.nan)))
        except (TypeError, ValueError):
            continue
        elevation = np.nan
        for key in ("elevation_m", "elevation", "ele"):
            if point.get(key) is not None:
                try:
                    elevation = float(point[key])
                except (TypeError, ValueError):
                    pass
                break
        ele.append(elevation)
    return _double_vector(lat), _double_vector(lon), _double_vector(ele)


def _stack_comparison_series(
    prefix: str,
    records: Sequence[Any],
    payload: dict[str, np.ndarray],
) -> None:
    """Compact same-shaped numeric comparison data into matrices."""
    rows = [row for row in records if isinstance(row, Mapping)]
    if not rows:
        return
    payload.setdefault(f"{prefix}_count", _double_scalar(len(rows)))

    parameter_rows = [row.get("parameters", {}) for row in rows]
    if all(isinstance(item, Mapping) for item in parameter_rows):
        keys = sorted({str(key) for row in parameter_rows for key in row.keys()})
        for key in keys:
            values = [row.get(key) for row in parameter_rows]
            if all(value is None or _is_number(value) for value in values) and any(
                _is_number(value) for value in values
            ):
                payload.setdefault(
                    _safe_name(f"{prefix}_param_{key}"),
                    _double_vector(
                        [np.nan if value is None else float(value) for value in values]
                    ),
                )

    series_paths = {
        "time_s": ("time", "time_s"),
        "distance_m": ("time", "distance_m"),
        "v_kmh": ("time", "speed_kmh"),
        "v_target_kmh": ("time", "target_kmh"),
        "a_mps2": ("time", "acceleration_mps2"),
    }
    for target, (section, key) in series_paths.items():
        arrays: list[np.ndarray] = []
        expected: int | None = None
        for row in rows:
            container = row.get(section, {})
            if not isinstance(container, Mapping):
                arrays = []
                break
            try:
                array = np.asarray(container.get(key, []), dtype=np.float64).reshape(-1)
            except (TypeError, ValueError):
                arrays = []
                break
            if expected is None:
                expected = array.size
            if array.size != expected:
                arrays = []
                break
            arrays.append(array)
        if arrays and expected:
            payload.setdefault(
                _safe_name(f"{prefix}_{target}"),
                np.asarray(np.vstack(arrays), dtype=np.float64),
            )


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
    """Export a compact MAT file made only of named MATLAB double arrays."""
    del source_route, source_dem

    path = Path(output_path).expanduser().resolve()
    if path.suffix.lower() != ".mat":
        path = path.with_suffix(".mat")
    path.parent.mkdir(parents=True, exist_ok=True)

    distance_data = result.get("distance", {})
    time_data = result.get("time", {})
    events = result.get("events", {})
    if not isinstance(distance_data, Mapping) or not isinstance(time_data, Mapping):
        raise ValueError("Simulation enthält keine gültigen Distanz-/Zeitdaten.")

    route_distance = _double_vector(distance_data.get("distance_m", []))
    time_s = _double_vector(time_data.get("time_s", []))
    n_route = route_distance.size
    n_time = time_s.size
    if n_route == 0 or n_time == 0:
        raise ValueError("Simulation enthält keine exportierbaren Strecken-/Zeitreihen.")

    time_distance = _double_vector(time_data.get("distance_m", []), n_time)
    route_lat = _double_vector(distance_data.get("latitude", []), n_route)
    route_lon = _double_vector(distance_data.get("longitude", []), n_route)
    route_elevation = _double_vector(elevation_m if elevation_m is not None else [], n_route)
    route_radius = _double_vector(distance_data.get("curve_radius_m", []), n_route)

    power = power_data if isinstance(power_data, Mapping) else {}
    route_grade_fraction = _double_vector(power.get("grade_spatial", []), n_route, fill=0.0)
    route_grade_pct = route_grade_fraction * 100.0

    payload: dict[str, np.ndarray] = {
        "time_s": time_s,
        "distance_m": time_distance,
        "lat_deg": _interp_finite(route_distance, route_lat, time_distance),
        "lon_deg": _interp_finite(route_distance, route_lon, time_distance),
        "elevation_m": _interp_finite(route_distance, route_elevation, time_distance),
        "curve_radius_m": _nearest_values(route_distance, route_radius, time_distance),
        "grade_pct": _interp_finite(route_distance, route_grade_pct, time_distance),
        "v_kmh": _double_vector(time_data.get("speed_kmh", []), n_time),
        "v_target_kmh": _double_vector(time_data.get("target_kmh", []), n_time),
        "a_mps2": _double_vector(time_data.get("acceleration_mps2", []), n_time),
        "v_road_limit_kmh": _nearest_values(
            route_distance, _double_vector(distance_data.get("road_limit_kmh", []), n_route), time_distance
        ),
        "v_surface_limit_kmh": _nearest_values(
            route_distance, _double_vector(distance_data.get("surface_limit_kmh", []), n_route), time_distance
        ),
        "v_curve_limit_kmh": _nearest_values(
            route_distance, _double_vector(distance_data.get("curve_limit_kmh", []), n_route), time_distance
        ),
        "v_base_target_kmh": _interp_finite(
            route_distance, _double_vector(distance_data.get("base_target_kmh", []), n_route), time_distance
        ),
        "v_planned_kmh": _interp_finite(
            route_distance, _double_vector(distance_data.get("planned_speed_kmh", []), n_route), time_distance
        ),
        "v_actual_kmh": _interp_finite(
            route_distance, _double_vector(distance_data.get("actual_speed_kmh", []), n_route), time_distance
        ),
        "v_noise_kmh": _interp_finite(
            route_distance, _double_vector(distance_data.get("noise_kmh", []), n_route), time_distance
        ),
        "route_distance_m": route_distance,
        "route_lat_deg": route_lat,
        "route_lon_deg": route_lon,
        "route_elevation_m": route_elevation,
        "route_curve_radius_m": route_radius,
        "route_grade_pct": route_grade_pct,
        "route_v_road_limit_kmh": _double_vector(distance_data.get("road_limit_kmh", []), n_route),
        "route_v_surface_limit_kmh": _double_vector(distance_data.get("surface_limit_kmh", []), n_route),
        "route_v_curve_limit_kmh": _double_vector(distance_data.get("curve_limit_kmh", []), n_route),
        "route_v_base_target_kmh": _double_vector(distance_data.get("base_target_kmh", []), n_route),
        "route_v_planned_kmh": _double_vector(distance_data.get("planned_speed_kmh", []), n_route),
        "route_v_actual_kmh": _double_vector(distance_data.get("actual_speed_kmh", []), n_route),
        "route_v_noise_kmh": _double_vector(distance_data.get("noise_kmh", []), n_route),
    }

    distance_core = {
        "distance_m", "latitude", "longitude", "curve_radius_m",
        "road_limit_kmh", "surface_limit_kmh", "curve_limit_kmh",
        "base_target_kmh", "planned_speed_kmh", "actual_speed_kmh", "noise_kmh",
    }
    time_core = {"time_s", "distance_m", "speed_kmh", "target_kmh", "acceleration_mps2"}
    _add_optional_numeric_series(distance_data, distance_core, "route", payload, n_route)
    _add_optional_numeric_series(time_data, time_core, "time", payload, n_time)

    power_names = {
        "total_kw": "p_total_kw",
        "acceleration_kw": "p_acceleration_kw",
        "grade_kw": "p_grade_kw",
        "rolling_kw": "p_rolling_kw",
        "air_kw": "p_air_kw",
        "trailer_kw": "p_trailer_kw",
        "traction_power_kw": "p_traction_kw",
        "recuperation_power_kw": "p_recuperation_kw",
        "cumulative_traction_energy_kwh": "e_traction_cum_kwh",
        "cumulative_recuperation_energy_kwh": "e_recuperation_cum_kwh",
        "cumulative_net_energy_kwh": "e_net_cum_kwh",
    }
    for source, target in power_names.items():
        payload[target] = _double_vector(power.get(source, []), n_time)

    scalar_power_names = {
        "traction_energy_kwh": "e_traction_kwh",
        "recuperation_energy_kwh": "e_recuperation_kwh",
        "net_energy_kwh": "e_net_kwh",
        "braking_energy_kwh": "e_braking_kwh",
        "p95_positive_kw": "p_p95_positive_kw",
        "maximum_kw": "p_max_kw",
        "minimum_kw": "p_min_kw",
    }
    for source, target in scalar_power_names.items():
        payload[target] = _double_scalar(power.get(source, np.nan))
    payload["trailer_enabled"] = _double_scalar(1.0 if power.get("trailer_enabled", False) else 0.0)

    traffic_dist: list[float] = []
    traffic_dwell: list[float] = []
    if isinstance(events, Mapping):
        for event in events.get("traffic_lights", []) or []:
            if not isinstance(event, Mapping):
                continue
            try:
                traffic_dist.append(float(event.get("distance_m", np.nan)))
                traffic_dwell.append(float(event.get("dwell_s", np.nan)))
            except (TypeError, ValueError):
                continue
    payload["traffic_light_distance_m"] = _double_vector(traffic_dist)
    payload["traffic_light_dwell_s"] = _double_vector(traffic_dwell)

    interval_start: list[float] = []
    interval_end: list[float] = []
    if isinstance(events, Mapping):
        for interval in events.get("traffic_light_dwell_intervals_s", []) or []:
            try:
                start, end = interval
                interval_start.append(float(start))
                interval_end.append(float(end))
            except (TypeError, ValueError):
                continue
    payload["traffic_light_start_s"] = _double_vector(interval_start)
    payload["traffic_light_end_s"] = _double_vector(interval_end)

    if isinstance(events, Mapping):
        for key, value in events.items():
            if key in {"traffic_lights", "traffic_light_dwell_intervals_s"}:
                continue
            prefix = {
                "post_curve_overshoot": "post_curve",
                "overtaking": "overtaking",
            }.get(str(key), _safe_name(f"event_{key}"))
            if isinstance(value, (list, tuple)) and value and all(
                isinstance(item, Mapping) for item in value
            ):
                _add_record_arrays(prefix, value, payload)
            elif isinstance(value, Mapping):
                _add_scalar_mapping(prefix, value, payload)
            elif isinstance(value, (list, tuple, np.ndarray)):
                try:
                    array = np.asarray(value, dtype=np.float64)
                except (TypeError, ValueError):
                    continue
                payload.setdefault(prefix, array if array.ndim > 1 else _double_vector(array))
            elif _is_number(value):
                payload.setdefault(prefix, _double_scalar(value))

    total_power = payload["p_total_kw"]
    if np.any(np.isfinite(total_power)):
        collective = cumulative_load_curve(_flat(time_s), _flat(total_power))
        if isinstance(collective, Mapping):
            payload["load_pos_time_share_pct"] = _double_vector(
                collective.get("positive_time_share_pct", [])
            )
            payload["load_pos_kw"] = _double_vector(collective.get("positive_load", []))
            payload["load_neg_time_share_pct"] = _double_vector(
                collective.get("negative_time_share_pct", [])
            )
            payload["load_neg_kw"] = _double_vector(collective.get("negative_load", []))

    if isinstance(route, Mapping):
        coord_lat, coord_lon, coord_ele = _route_coordinates(route)
        payload["route_coordinate_lat_deg"] = coord_lat
        payload["route_coordinate_lon_deg"] = coord_lon
        payload["route_coordinate_elevation_m"] = coord_ele

        for key, value in route.items():
            if key == "coordinates":
                continue
            prefix = {
                "segments": "segment",
                "traffic_signals": "osm_signal",
                "legs": "leg",
                "metadata": "route_meta",
                "selection": "route_selection",
                "summary": "route_summary",
            }.get(str(key), _safe_name(f"route_{key}"))
            if isinstance(value, (list, tuple)) and value and all(
                isinstance(item, Mapping) for item in value
            ):
                _add_record_arrays(prefix, value, payload)
            elif isinstance(value, Mapping):
                _add_scalar_mapping(prefix, value, payload)
            elif _is_number(value):
                payload.setdefault(prefix, _double_scalar(value))

    parameter_mapping = parameters if isinstance(parameters, Mapping) else result.get("parameters", {})
    if isinstance(parameter_mapping, Mapping):
        _add_scalar_mapping("param", parameter_mapping, payload)

    summary = result.get("summary", {})
    if isinstance(summary, Mapping):
        _add_scalar_mapping("summary", summary, payload)

    if isinstance(comparison, Mapping):
        results = comparison.get("results", [])
        if isinstance(results, (list, tuple)):
            _stack_comparison_series("comparison", results, payload)
        configs = comparison.get("configs", [])
        if isinstance(configs, (list, tuple)) and configs and all(
            isinstance(item, Mapping) for item in configs
        ):
            _add_record_arrays("comparison_config", configs, payload)
        resistance = comparison.get("resistance", [])
        if isinstance(resistance, (list, tuple)) and resistance and all(
            isinstance(item, Mapping) for item in resistance
        ):
            _add_record_arrays("comparison_power", resistance, payload)

    for key, value in list(payload.items()):
        array = np.asarray(value, dtype=np.float64)
        if array.ndim == 0:
            array = array.reshape(1, 1)
        elif array.ndim == 1:
            array = array.reshape(-1, 1)
        payload[key] = array

    savemat(path, payload, appendmat=False, do_compression=True, long_field_names=True)
    return path
