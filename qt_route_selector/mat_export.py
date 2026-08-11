from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.io import savemat

try:
    from .load_collective_curve import cumulative_load_curve
except ImportError:
    from load_collective_curve import cumulative_load_curve


MAT_EXPORT_VERSION = "1.0"


def _jsonable(value: Any) -> Any:
    """Convert simulation objects into a lossless-enough JSON representation."""

    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return {
            str(key): _jsonable(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _mat_field_name(name: str) -> str:
    """Return a MATLAB-struct-compatible field name (<= 63 characters)."""

    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(name)).strip("_") or "value"
    if not cleaned[0].isalpha():
        cleaned = f"f_{cleaned}"
    return cleaned[:63]


def _mat_value(value: Any) -> Any:
    if value is None:
        return np.nan
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value
    if isinstance(value, Mapping):
        return {_mat_field_name(str(key)): _mat_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if not value:
            return np.empty((0, 1), dtype=float)
        if all(isinstance(item, (bool, int, float, np.number)) for item in value):
            return np.asarray(value)
        if all(isinstance(item, str) for item in value):
            return np.asarray(value, dtype=object)
        # Complex heterogeneous lists are retained in the JSON mirrors below.
        return json.dumps(_jsonable(value), ensure_ascii=False)
    if isinstance(value, (str, bool, int, float)):
        return value
    return json.dumps(_jsonable(value), ensure_ascii=False)


def _float_array(value: Any, length: int | None = None, fill: float = np.nan) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        array = np.empty(0, dtype=float)
    if length is None:
        return array
    if array.size == length:
        return array
    result = np.full(length, fill, dtype=float)
    if array.size:
        count = min(length, array.size)
        result[:count] = array[:count]
    return result


def _interp_finite(distance_m: np.ndarray, values: np.ndarray, query_m: np.ndarray) -> np.ndarray:
    if query_m.size == 0:
        return np.empty(0, dtype=float)
    distance = np.asarray(distance_m, dtype=float).reshape(-1)
    data = np.asarray(values, dtype=float).reshape(-1)
    if distance.size != data.size or distance.size == 0:
        return np.full(query_m.shape, np.nan, dtype=float)
    finite = np.isfinite(distance) & np.isfinite(data)
    if np.count_nonzero(finite) == 0:
        return np.full(query_m.shape, np.nan, dtype=float)
    x = distance[finite]
    y = data[finite]
    order = np.argsort(x, kind="stable")
    x = x[order]
    y = y[order]
    x, indexes = np.unique(x, return_index=True)
    y = y[indexes]
    if x.size == 1:
        return np.full(query_m.shape, float(y[0]), dtype=float)
    return np.interp(query_m, x, y)


def _numeric_struct(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Keep scalar/array-like fields easy to consume as a MATLAB struct."""

    result: dict[str, Any] = {}
    for key, value in mapping.items():
        field = _mat_field_name(str(key))
        if isinstance(value, np.ndarray):
            result[field] = value
        elif isinstance(value, np.generic):
            result[field] = value.item()
        elif value is None or isinstance(value, (str, bool, int, float)):
            result[field] = _mat_value(value)
        elif isinstance(value, (list, tuple)) and all(
            isinstance(item, (bool, int, float, np.number)) for item in value
        ):
            result[field] = np.asarray(value)
        elif isinstance(value, Mapping):
            result[field] = _mat_value(value)
    return result


def _event_tables(events: Mapping[str, Any]) -> dict[str, Any]:
    traffic_rows: list[list[float]] = []
    for event in events.get("traffic_lights", []) or []:
        if not isinstance(event, Mapping):
            continue
        try:
            traffic_rows.append(
                [float(event.get("distance_m", np.nan)), float(event.get("dwell_s", np.nan))]
            )
        except (TypeError, ValueError):
            continue

    dwell_rows: list[list[float]] = []
    for interval in events.get("traffic_light_dwell_intervals_s", []) or []:
        try:
            start, end = interval
            dwell_rows.append([float(start), float(end)])
        except (TypeError, ValueError):
            continue

    return {
        "traffic_lights_columns": np.asarray(["distance_m", "dwell_s"], dtype=object),
        "traffic_lights": np.asarray(traffic_rows, dtype=float).reshape((-1, 2)),
        "traffic_light_intervals_columns": np.asarray(["start_s", "end_s"], dtype=object),
        "traffic_light_intervals": np.asarray(dwell_rows, dtype=float).reshape((-1, 2)),
        "json": json.dumps(_jsonable(events), ensure_ascii=False),
    }


def _route_coordinate_table(route: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    rows: list[list[float]] = []
    for point in route.get("coordinates", []) or []:
        if not isinstance(point, Mapping):
            continue
        try:
            latitude = float(point.get("latitude", np.nan))
            longitude = float(point.get("longitude", np.nan))
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
        rows.append([latitude, longitude, elevation])
    return (
        np.asarray(["latitude_deg", "longitude_deg", "elevation_m"], dtype=object),
        np.asarray(rows, dtype=float).reshape((-1, 3)),
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
    comparison: Mapping[str, Any] | None = None,
) -> Path:
    """Write one comprehensive MATLAB MAT v5 file for the current simulation.

    The file contains convenient numeric structs/tables for MATLAB analysis and
    JSON mirrors of the raw route/simulation data so no source information is
    silently discarded when it does not map naturally to a numeric matrix.
    """

    path = Path(output_path).expanduser().resolve()
    if path.suffix.lower() != ".mat":
        path = path.with_suffix(".mat")
    path.parent.mkdir(parents=True, exist_ok=True)

    distance_data = result.get("distance", {})
    time_data = result.get("time", {})
    events = result.get("events", {})
    summary = result.get("summary", {})
    if not isinstance(distance_data, Mapping) or not isinstance(time_data, Mapping):
        raise ValueError("Simulation enthält keine gültigen Distanz-/Zeitdaten.")

    spatial_distance = _float_array(distance_data.get("distance_m", []))
    time_s = _float_array(time_data.get("time_s", []))
    time_distance = _float_array(time_data.get("distance_m", []), len(time_s))
    if spatial_distance.size == 0 or time_s.size == 0:
        raise ValueError("Simulation enthält keine exportierbaren Strecken-/Zeitreihen.")

    n_distance = spatial_distance.size
    n_time = time_s.size
    latitude = _float_array(distance_data.get("latitude", []), n_distance)
    longitude = _float_array(distance_data.get("longitude", []), n_distance)
    radius = _float_array(distance_data.get("curve_radius_m", []), n_distance)
    elevation = _float_array(elevation_m if elevation_m is not None else [], n_distance)

    power = dict(power_data or {})
    grade_spatial = _float_array(power.get("grade_spatial", []), n_distance, fill=0.0)
    grade_pct_spatial = grade_spatial * 100.0

    distance_struct = _numeric_struct(distance_data)
    distance_struct.update(
        {
            "elevation_m": elevation,
            "grade_fraction": grade_spatial,
            "grade_pct": grade_pct_spatial,
        }
    )

    time_struct = _numeric_struct(time_data)
    contextual_spatial_keys = (
        "road_limit_kmh",
        "surface_limit_kmh",
        "curve_limit_kmh",
        "base_target_kmh",
        "planned_speed_kmh",
        "actual_speed_kmh",
        "noise_kmh",
    )
    time_struct.update(
        {
            "latitude": _interp_finite(spatial_distance, latitude, time_distance),
            "longitude": _interp_finite(spatial_distance, longitude, time_distance),
            "elevation_m": _interp_finite(spatial_distance, elevation, time_distance),
            "curve_radius_m": _interp_finite(spatial_distance, radius, time_distance),
            "grade_fraction": _interp_finite(spatial_distance, grade_spatial, time_distance),
            "grade_pct": _interp_finite(spatial_distance, grade_pct_spatial, time_distance),
        }
    )
    for key in contextual_spatial_keys:
        time_struct[key] = _interp_finite(
            spatial_distance,
            _float_array(distance_data.get(key, []), n_distance),
            time_distance,
        )

    distance_columns = [
        "distance_m",
        "latitude_deg",
        "longitude_deg",
        "elevation_m",
        "curve_radius_m",
        "grade_pct",
        "road_limit_kmh",
        "surface_limit_kmh",
        "curve_limit_kmh",
        "base_target_kmh",
        "planned_speed_kmh",
        "actual_speed_kmh",
        "noise_kmh",
    ]
    distance_table = np.column_stack(
        [
            spatial_distance,
            latitude,
            longitude,
            elevation,
            radius,
            grade_pct_spatial,
            _float_array(distance_data.get("road_limit_kmh", []), n_distance),
            _float_array(distance_data.get("surface_limit_kmh", []), n_distance),
            _float_array(distance_data.get("curve_limit_kmh", []), n_distance),
            _float_array(distance_data.get("base_target_kmh", []), n_distance),
            _float_array(distance_data.get("planned_speed_kmh", []), n_distance),
            _float_array(distance_data.get("actual_speed_kmh", []), n_distance),
            _float_array(distance_data.get("noise_kmh", []), n_distance),
        ]
    )

    power_struct = _numeric_struct(power)
    power_series_keys = (
        "total_kw",
        "acceleration_kw",
        "grade_kw",
        "rolling_kw",
        "air_kw",
        "trailer_kw",
        "traction_power_kw",
        "recuperation_power_kw",
        "cumulative_traction_energy_kwh",
        "cumulative_recuperation_energy_kwh",
        "cumulative_net_energy_kwh",
    )
    power_series = {
        key: _float_array(power.get(key, []), n_time) for key in power_series_keys
    }

    time_columns = [
        "time_s",
        "distance_m",
        "latitude_deg",
        "longitude_deg",
        "elevation_m",
        "curve_radius_m",
        "speed_kmh",
        "target_kmh",
        "acceleration_mps2",
        "road_limit_kmh",
        "surface_limit_kmh",
        "curve_limit_kmh",
        "grade_pct",
        "total_kw",
        "acceleration_kw",
        "grade_kw",
        "rolling_kw",
        "air_kw",
        "trailer_kw",
        "traction_power_kw",
        "recuperation_power_kw",
        "cumulative_traction_energy_kwh",
        "cumulative_recuperation_energy_kwh",
        "cumulative_net_energy_kwh",
    ]
    time_table = np.column_stack(
        [
            time_s,
            time_distance,
            time_struct["latitude"],
            time_struct["longitude"],
            time_struct["elevation_m"],
            time_struct["curve_radius_m"],
            _float_array(time_data.get("speed_kmh", []), n_time),
            _float_array(time_data.get("target_kmh", []), n_time),
            _float_array(time_data.get("acceleration_mps2", []), n_time),
            time_struct["road_limit_kmh"],
            time_struct["surface_limit_kmh"],
            time_struct["curve_limit_kmh"],
            time_struct["grade_pct"],
            *[power_series[key] for key in power_series_keys],
        ]
    )

    if power_series["total_kw"].size == n_time and np.any(np.isfinite(power_series["total_kw"])):
        load_collective = cumulative_load_curve(time_s, power_series["total_kw"])
    else:
        load_collective = {}

    route_data = dict(route or {})
    route_columns, route_coordinates = _route_coordinate_table(route_data)
    event_mapping = events if isinstance(events, Mapping) else {}

    metadata = {
        "format_version": MAT_EXPORT_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_route": str(source_route or ""),
        "description": (
            "GPS-Routenplaner: vollständiger Route-, Fahrdynamik-, Höhen-, Kurven-, "
            "Leistungs- und Energieexport"
        ),
    }

    payload: dict[str, Any] = {
        "metadata": metadata,
        "summary": _numeric_struct(summary if isinstance(summary, Mapping) else {}),
        "parameters": _numeric_struct(parameters or result.get("parameters", {})),
        "distance": distance_struct,
        "time": time_struct,
        "power": power_struct,
        "events": _event_tables(event_mapping),
        "load_collective": _numeric_struct(load_collective),
        "distance_columns": np.asarray(distance_columns, dtype=object),
        "distance_table": distance_table,
        "time_columns": np.asarray(time_columns, dtype=object),
        "time_table": time_table,
        "route_coordinate_columns": route_columns,
        "route_coordinates": route_coordinates,
        "route_json": json.dumps(_jsonable(route_data), ensure_ascii=False),
        "simulation_json": json.dumps(_jsonable(result), ensure_ascii=False),
        "events_json": json.dumps(_jsonable(event_mapping), ensure_ascii=False),
        "comparison_json": json.dumps(_jsonable(comparison or {}), ensure_ascii=False),
    }

    savemat(
        path,
        payload,
        appendmat=False,
        format="5",
        long_field_names=True,
        do_compression=True,
        oned_as="column",
    )
    return path
