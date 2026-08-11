from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.io import savemat

try:
    from .load_collective_curve import cumulative_load_curve
except ImportError:
    from load_collective_curve import cumulative_load_curve


def _double_vector(value: Any, length: int | None = None, fill: float = np.nan) -> np.ndarray:
    """Return an Nx1 float64 array suitable for a MATLAB double variable."""

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
    """Return a 1x1 float64 array."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return np.asarray([[number]], dtype=np.float64)


def _flat(vector: np.ndarray) -> np.ndarray:
    return np.asarray(vector, dtype=np.float64).reshape(-1)


def _interp_finite(distance_m: np.ndarray, values: np.ndarray, query_m: np.ndarray) -> np.ndarray:
    """Interpolate continuous finite values along the route."""

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
    """Nearest-neighbour sampling that preserves meaningful +/-Inf values."""

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


def _add_numeric(prefix: str, value: Any, payload: dict[str, np.ndarray]) -> None:
    """Flatten nested numeric content into individual MATLAB double variables."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            child = _safe_name(f"{prefix}_{key}" if prefix else str(key))
            _add_numeric(child, item, payload)
        return
    if isinstance(value, np.ndarray):
        try:
            array = np.asarray(value, dtype=np.float64)
        except (TypeError, ValueError):
            return
        if array.ndim <= 1:
            payload.setdefault(_safe_name(prefix), _double_vector(array))
        else:
            payload.setdefault(_safe_name(prefix), np.asarray(array, dtype=np.float64))
        return
    if isinstance(value, (bool, int, float, np.number)):
        payload.setdefault(_safe_name(prefix), _double_scalar(value))
        return
    if isinstance(value, (list, tuple)):
        if not value:
            payload.setdefault(_safe_name(prefix), np.empty((0, 1), dtype=np.float64))
            return
        try:
            array = np.asarray(value, dtype=np.float64)
        except (TypeError, ValueError):
            for index, item in enumerate(value, start=1):
                if isinstance(item, (Mapping, list, tuple, np.ndarray)):
                    _add_numeric(_safe_name(f"{prefix}_{index}"), item, payload)
            return
        if array.ndim <= 1:
            payload.setdefault(_safe_name(prefix), _double_vector(array))
        else:
            payload.setdefault(_safe_name(prefix), np.asarray(array, dtype=np.float64))


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
    """Export the simulation directly from Python as individual MATLAB doubles.

    Every top-level variable in the resulting MAT file is numeric float64. No
    MATLAB process, structs, cells, strings, JSON, tables or timetables are used.
    Time-aligned signals use compact names; route-aligned originals use the
    ``route_`` prefix. Numeric parameters, summaries and comparison data are
    flattened into additional individual double variables.
    """

    del source_route, source_dem  # textual metadata is intentionally not exported

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
        # Time-aligned core signals. These are the primary MATLAB analysis arrays.
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
        # Original distance-aligned route data.
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

    payload["e_traction_kwh"] = _double_scalar(power.get("traction_energy_kwh", np.nan))
    payload["e_recuperation_kwh"] = _double_scalar(power.get("recuperation_energy_kwh", np.nan))
    payload["e_net_kwh"] = _double_scalar(power.get("net_energy_kwh", np.nan))
    payload["trailer_enabled"] = _double_scalar(1.0 if power.get("trailer_enabled", False) else 0.0)

    # OSM traffic-light events and simulated dwell intervals.
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

    # Original route coordinates are kept separately from the resampled route arrays.
    if isinstance(route, Mapping):
        coord_lat, coord_lon, coord_ele = _route_coordinates(route)
        payload["route_coordinate_lat_deg"] = coord_lat
        payload["route_coordinate_lon_deg"] = coord_lon
        payload["route_coordinate_elevation_m"] = coord_ele
        _add_numeric("route_extra", route, payload)

    parameter_mapping = parameters if isinstance(parameters, Mapping) else result.get("parameters", {})
    if isinstance(parameter_mapping, Mapping):
        _add_numeric("param", parameter_mapping, payload)

    summary = result.get("summary", {})
    if isinstance(summary, Mapping):
        _add_numeric("summary", summary, payload)

    # Retain any additional numeric simulation/event/comparison values not already
    # represented by the concise variables above. Non-numeric text is deliberately
    # omitted so every MAT workspace variable remains MATLAB class double.
    _add_numeric("extra_distance", distance_data, payload)
    _add_numeric("extra_time", time_data, payload)
    if isinstance(events, Mapping):
        _add_numeric("event", events, payload)
    if isinstance(power, Mapping):
        _add_numeric("power_extra", power, payload)
    if isinstance(comparison, Mapping):
        _add_numeric("comparison", comparison, payload)

    # Enforce the contract: every exported top-level variable is float64.
    for key, value in list(payload.items()):
        array = np.asarray(value, dtype=np.float64)
        if array.ndim == 0:
            array = array.reshape(1, 1)
        elif array.ndim == 1:
            array = array.reshape(-1, 1)
        payload[key] = array

    savemat(path, payload, appendmat=False, do_compression=True, long_field_names=True)
    return path
