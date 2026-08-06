from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np


DRIVER_PROFILES: dict[str, dict[str, Any]] = {
    "normalo": {
        "label": "Normalo",
        "note": "ausgewogen und defensiv",
        "Kp": 1.1,
        "a_max_mps2": 2.8,
        "b_max_mps2": 3.0,
        "j_max_mps3": 1.2,
        "max_lat_accel_mps2": 2.2,
        "use_driver_noise": True,
        "noise_std_kmh": 1.8,
        "noise_tau_s": 3.5,
        "speed_bias_kmh": 0.0,
        "use_trailer_model": False,
    },
    "rennfahrer": {
        "label": "Rennfahrer",
        "note": "dynamisch",
        "Kp": 1.5,
        "a_max_mps2": 4.8,
        "b_max_mps2": 4.0,
        "j_max_mps3": 2.0,
        "max_lat_accel_mps2": 2.8,
        "use_driver_noise": True,
        "noise_std_kmh": 2.5,
        "noise_tau_s": 2.0,
        "speed_bias_kmh": 2.0,
        "use_trailer_model": False,
    },
    "handwerker": {
        "label": "Handwerker",
        "note": "zügig und pragmatisch",
        "Kp": 1.3,
        "a_max_mps2": 3.6,
        "b_max_mps2": 3.2,
        "j_max_mps3": 1.6,
        "max_lat_accel_mps2": 2.5,
        "use_driver_noise": True,
        "noise_std_kmh": 2.0,
        "noise_tau_s": 3.0,
        "speed_bias_kmh": 1.0,
        "use_trailer_model": False,
    },
    "rentner": {
        "label": "Rentner",
        "note": "ruhig und defensiv, ohne Fahrerrauschen",
        "Kp": 0.75,
        "a_max_mps2": 1.5,
        "b_max_mps2": 2.0,
        "j_max_mps3": 0.55,
        "max_lat_accel_mps2": 1.4,
        "use_driver_noise": False,
        "noise_std_kmh": 0.0,
        "noise_tau_s": 10.0,
        "speed_bias_kmh": 0.0,
        "use_trailer_model": False,
    },
    "rentner_anhaenger": {
        "label": "Rentner + Anhänger",
        "note": "ruhige Fahrt mit Anhänger, ohne Fahrerrauschen",
        "Kp": 0.65,
        "a_max_mps2": 1.2,
        "b_max_mps2": 2.0,
        "j_max_mps3": 0.40,
        "max_lat_accel_mps2": 1.25,
        "use_driver_noise": False,
        "noise_std_kmh": 0.0,
        "noise_tau_s": 15.0,
        "speed_bias_kmh": 0.0,
        "use_trailer_model": True,
    },
}


DEFAULT_PARAMETERS: dict[str, Any] = {
    "driver_profile": "normalo",
    "dt_s": 0.2,
    "sample_distance_m": 5.0,
    "driver_cruise_kmh": 130.0,
    "driver_hard_max_kmh": 140.0,
    "speed_bias_kmh": 0.0,
    "speed_tolerance_kmh": 1.0,
    "temperament": 1.0,
    "Kp": 1.1,
    "a_max_mps2": 2.8,
    "b_max_mps2": 3.0,
    "j_max_mps3": 1.2,
    "start_stop": True,
    "end_stop": True,
    "apply_curve_speed": True,
    "max_lat_accel_mps2": 2.2,
    "min_curve_radius_m": 8.0,
    "max_curve_radius_m": 5000.0,
    "curve_sample_distance_m": 12.0,
    "curve_smooth_distance_m": 25.0,
    "curve_plan_decel_mps2": 1.8,
    "use_surface_limit": True,
    "use_traffic_lights": True,
    "traffic_light_count": 0,
    "traffic_light_dwell_min_s": 20.0,
    "traffic_light_dwell_max_s": 60.0,
    "traffic_light_plan_decel_mps2": 1.8,
    "traffic_light_stop_tolerance_m": 2.0,
    "use_overtaking": False,
    "overtaking_count": 0,
    "overtaking_slow_speed_kmh": 70.0,
    "overtaking_intensity_kmh": 20.0,
    "overtaking_follow_distance_m": 180.0,
    "overtaking_pass_distance_m": 100.0,
    "use_driver_noise": True,
    "noise_std_kmh": 1.8,
    "noise_tau_s": 3.5,
    "simulation_seed": 42,
    "use_trailer_model": False,
    "vehicle_mass_kg": 1800.0,
    "trailer_mass_kg": 1200.0,
    "rolling_resistance_coeff": 0.015,
    "max_drive_force_n": 5200.0,
    "max_brake_force_n": 9000.0,
}


SURFACE_FACTORS: dict[str, float] = {
    "": 1.0,
    "asphalt": 1.0,
    "concrete": 1.0,
    "concrete:plates": 0.92,
    "paved": 0.95,
    "paving_stones": 0.82,
    "sett": 0.76,
    "cobblestone": 0.66,
    "compacted": 0.78,
    "fine_gravel": 0.72,
    "gravel": 0.62,
    "unpaved": 0.55,
    "ground": 0.50,
    "dirt": 0.45,
    "earth": 0.45,
    "sand": 0.35,
    "mud": 0.25,
}


@dataclass(frozen=True)
class PreparedRoute:
    distance_m: np.ndarray
    x_m: np.ndarray
    y_m: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    maxspeed_kmh: np.ndarray
    surface: np.ndarray
    highway: np.ndarray
    detected_signal_distances_m: np.ndarray
    total_distance_m: float


def profile_parameters(name: str) -> dict[str, Any]:
    profile = DRIVER_PROFILES.get(name, DRIVER_PROFILES["normalo"])
    values = dict(DEFAULT_PARAMETERS)
    values.update({key: value for key, value in profile.items() if key not in {"label", "note"}})
    values["driver_profile"] = name if name in DRIVER_PROFILES else "normalo"
    return values


def merged_parameters(values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(values or {})
    profile_name = str(raw.get("driver_profile", DEFAULT_PARAMETERS["driver_profile"]))
    merged = profile_parameters(profile_name)
    merged.update(raw)
    return merged


def load_route_result(path: str | Path) -> dict[str, Any]:
    route_path = Path(path).expanduser().resolve()
    with route_path.open("r", encoding="utf-8") as handle:
        route = json.load(handle)
    if not isinstance(route, dict):
        raise ValueError("route_result.json enthält kein JSON-Objekt.")
    return route


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    value = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    value = min(1.0, max(0.0, value))
    return radius * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


def _coordinate_arrays(route: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    coordinates = route.get("coordinates", [])
    if len(coordinates) < 2:
        raise ValueError("Die Route enthält weniger als zwei Koordinaten.")
    lat = np.asarray([float(point["latitude"]) for point in coordinates], dtype=float)
    lon = np.asarray([float(point["longitude"]) for point in coordinates], dtype=float)
    return lat, lon


def _raw_distances(route: Mapping[str, Any], lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    segment_lookup: dict[int, float] = {}
    for segment in route.get("segments", []):
        try:
            index = int(segment.get("from_index", -1))
            distance = float(segment.get("distance_m", 0.0))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(lat) - 1 and distance > 0.0:
            segment_lookup[index] = distance

    distances = np.zeros(len(lat) - 1, dtype=float)
    for index in range(len(distances)):
        distances[index] = segment_lookup.get(
            index,
            _haversine_m(lat[index], lon[index], lat[index + 1], lon[index + 1]),
        )
        if not math.isfinite(distances[index]) or distances[index] <= 0.0:
            distances[index] = 0.1
    return np.concatenate(([0.0], np.cumsum(distances)))


def _local_xy(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    radius = 6_378_137.0
    lat0 = math.radians(float(np.mean(lat)))
    lon0 = math.radians(float(lon[0]))
    x = radius * math.cos(lat0) * (np.radians(lon) - lon0)
    y = radius * (np.radians(lat) - math.radians(float(lat[0])))
    return x, y


def _attribute_by_sample(
    route: Mapping[str, Any],
    raw_distance: np.ndarray,
    sample_distance: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_segments = len(raw_distance) - 1
    maxspeed = np.full(n_segments, 30.0, dtype=float)
    surface = np.full(n_segments, "", dtype=object)
    highway = np.full(n_segments, "", dtype=object)

    for segment in route.get("segments", []):
        try:
            start = max(0, int(segment.get("from_index", 0)))
            end = min(n_segments, int(segment.get("to_index", start + 1)))
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = min(n_segments, start + 1)
        try:
            limit = float(segment.get("maxspeed_kmh", 30.0))
        except (TypeError, ValueError):
            limit = 30.0
        if not math.isfinite(limit) or limit <= 0:
            limit = 30.0
        maxspeed[start:end] = limit
        surface[start:end] = str(segment.get("surface", "") or "").lower()
        highway[start:end] = str(segment.get("highway", "") or "").lower()

    sample_index = np.searchsorted(raw_distance, sample_distance, side="right") - 1
    sample_index = np.clip(sample_index, 0, n_segments - 1)
    return maxspeed[sample_index], surface[sample_index], highway[sample_index]


def prepare_route(route: Mapping[str, Any], sample_distance_m: float = 5.0) -> PreparedRoute:
    sample_distance_m = max(1.0, float(sample_distance_m))
    lat, lon = _coordinate_arrays(route)
    raw_distance = _raw_distances(route, lat, lon)
    total_distance = float(raw_distance[-1])
    if total_distance <= 0.0:
        raise ValueError("Die Route besitzt keine positive Streckenlänge.")

    distance = np.arange(0.0, total_distance, sample_distance_m, dtype=float)
    if distance.size == 0 or not math.isclose(float(distance[-1]), total_distance, abs_tol=1e-6):
        distance = np.append(distance, total_distance)

    raw_x, raw_y = _local_xy(lat, lon)
    x = np.interp(distance, raw_distance, raw_x)
    y = np.interp(distance, raw_distance, raw_y)
    sample_lat = np.interp(distance, raw_distance, lat)
    sample_lon = np.interp(distance, raw_distance, lon)
    maxspeed, surface, highway = _attribute_by_sample(route, raw_distance, distance)

    signal_distances = []
    for signal in route.get("traffic_signals", []):
        try:
            value = float(signal.get("distance_from_start_m", math.nan))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and 0.0 < value < total_distance:
            signal_distances.append(value)

    return PreparedRoute(
        distance_m=distance,
        x_m=x,
        y_m=y,
        latitude=sample_lat,
        longitude=sample_lon,
        maxspeed_kmh=maxspeed,
        surface=surface,
        highway=highway,
        detected_signal_distances_m=np.asarray(sorted(set(signal_distances)), dtype=float),
        total_distance_m=total_distance,
    )


def _curve_radius(route: PreparedRoute, parameters: Mapping[str, Any]) -> np.ndarray:
    distance = route.distance_m
    radius = np.full(distance.shape, np.inf, dtype=float)
    sample_offset = max(2.0, float(parameters["curve_sample_distance_m"]))
    minimum = max(1.0, float(parameters["min_curve_radius_m"]))
    maximum = max(minimum, float(parameters["max_curve_radius_m"]))

    for index, position in enumerate(distance):
        left = int(np.searchsorted(distance, position - sample_offset, side="left"))
        right = int(np.searchsorted(distance, position + sample_offset, side="right") - 1)
        if left >= index or right <= index or right >= len(distance):
            continue
        ax = route.x_m[left] - route.x_m[index]
        ay = route.y_m[left] - route.y_m[index]
        bx = route.x_m[right] - route.x_m[index]
        by = route.y_m[right] - route.y_m[index]
        a = math.hypot(ax, ay)
        b = math.hypot(bx, by)
        c = math.hypot(route.x_m[right] - route.x_m[left], route.y_m[right] - route.y_m[left])
        twice_area = abs(ax * by - bx * ay)
        if min(a, b, c) < 0.5 or twice_area < 1e-6:
            continue
        value = a * b * c / (2.0 * twice_area)
        radius[index] = min(max(value, minimum), maximum)

    smooth = max(0.0, float(parameters["curve_smooth_distance_m"]))
    if smooth > 0.0:
        smoothed = np.full(radius.shape, np.inf, dtype=float)
        for index, position in enumerate(distance):
            left = int(np.searchsorted(distance, position - smooth, side="left"))
            right = int(np.searchsorted(distance, position + smooth, side="right"))
            smoothed[index] = float(np.min(radius[left:right])) if right > left else radius[index]
        radius = smoothed
    return radius


def _surface_factor(values: np.ndarray) -> np.ndarray:
    result = np.ones(len(values), dtype=float)
    for index, value in enumerate(values):
        text = str(value).strip().lower()
        result[index] = SURFACE_FACTORS.get(text, 0.90 if text else 1.0)
    return result


def _choose_event_positions(
    route: PreparedRoute,
    requested: int,
    detected: np.ndarray,
    rng: np.random.Generator,
    *,
    minimum_spacing_m: float = 120.0,
) -> np.ndarray:
    requested = max(0, int(requested))
    if requested == 0 or route.total_distance_m < 100.0:
        return np.empty(0, dtype=float)

    selected: list[float] = []
    if detected.size:
        order = rng.permutation(len(detected))
        for raw_index in order:
            value = float(detected[int(raw_index)])
            if all(abs(value - old) >= minimum_spacing_m for old in selected):
                selected.append(value)
            if len(selected) >= requested:
                break

    attempts = 0
    lower = min(100.0, route.total_distance_m * 0.15)
    upper = max(lower, route.total_distance_m - lower)
    while len(selected) < requested and attempts < requested * 100 + 100:
        attempts += 1
        value = float(rng.uniform(lower, upper))
        if all(abs(value - old) >= minimum_spacing_m for old in selected):
            selected.append(value)

    return np.asarray(sorted(selected), dtype=float)


def _overtaking_events(
    route: PreparedRoute,
    parameters: Mapping[str, Any],
    stop_positions: np.ndarray,
    rng: np.random.Generator,
) -> list[dict[str, float]]:
    count = max(0, int(parameters["overtaking_count"]))
    if not bool(parameters["use_overtaking"]) or count == 0:
        return []

    valid = np.where(
        (route.maxspeed_kmh >= 50.0)
        & (route.distance_m > 250.0)
        & (route.distance_m < route.total_distance_m - 250.0)
    )[0]
    if valid.size == 0:
        return []

    rng.shuffle(valid)
    centers: list[float] = []
    for index in valid:
        center = float(route.distance_m[int(index)])
        if any(abs(center - stop) < 250.0 for stop in stop_positions):
            continue
        if any(abs(center - old) < 400.0 for old in centers):
            continue
        centers.append(center)
        if len(centers) >= count:
            break

    follow = max(20.0, float(parameters["overtaking_follow_distance_m"]))
    passed = max(20.0, float(parameters["overtaking_pass_distance_m"]))
    return [
        {
            "center_m": center,
            "follow_start_m": max(0.0, center - follow),
            "pass_end_m": min(route.total_distance_m, center + passed),
        }
        for center in sorted(centers)
    ]


def _apply_driver_noise(
    target_kmh: np.ndarray,
    route: PreparedRoute,
    parameters: Mapping[str, Any],
    rng: np.random.Generator,
) -> np.ndarray:
    if not bool(parameters["use_driver_noise"]):
        return np.zeros_like(target_kmh)
    std = max(0.0, float(parameters["noise_std_kmh"]))
    tau = max(0.1, float(parameters["noise_tau_s"]))
    tolerance = max(0.0, float(parameters["speed_tolerance_kmh"]))
    if std <= 0.0 or tolerance <= 0.0:
        return np.zeros_like(target_kmh)

    noise = np.zeros_like(target_kmh)
    for index in range(1, len(noise)):
        ds = max(0.1, float(route.distance_m[index] - route.distance_m[index - 1]))
        dt = ds / max(float(target_kmh[index - 1]) / 3.6, 1.0)
        alpha = math.exp(-dt / tau)
        noise[index] = alpha * noise[index - 1] + math.sqrt(max(0.0, 1.0 - alpha * alpha)) * std * rng.normal()
        noise[index] = float(np.clip(noise[index], -tolerance, tolerance))
    return noise


def _kinematic_spatial_limit(
    target_mps: np.ndarray,
    distance: np.ndarray,
    accel_mps2: float,
    brake_mps2: float,
) -> np.ndarray:
    speed = np.maximum(0.0, target_mps.copy())
    accel = max(0.05, accel_mps2)
    brake = max(0.05, brake_mps2)
    for _ in range(2):
        for index in range(len(speed) - 2, -1, -1):
            ds = max(0.0, float(distance[index + 1] - distance[index]))
            speed[index] = min(speed[index], math.sqrt(max(0.0, speed[index + 1] ** 2 + 2.0 * brake * ds)))
        for index in range(len(speed) - 1):
            ds = max(0.0, float(distance[index + 1] - distance[index]))
            speed[index + 1] = min(speed[index + 1], math.sqrt(max(0.0, speed[index] ** 2 + 2.0 * accel * ds)))
    return speed


def _simulate_time(
    route: PreparedRoute,
    planned_mps: np.ndarray,
    hard_cap_mps: np.ndarray,
    stop_positions: np.ndarray,
    dwell_durations: np.ndarray,
    parameters: Mapping[str, Any],
) -> dict[str, np.ndarray | list[tuple[float, float]]]:
    dt = max(0.05, float(parameters["dt_s"]))
    temperament = float(np.clip(parameters["temperament"], 0.4, 1.8))
    kp = max(0.05, float(parameters["Kp"]) * temperament)
    accel = max(0.1, float(parameters["a_max_mps2"]) * temperament)
    brake = max(0.1, float(parameters["b_max_mps2"]) * (0.85 + 0.15 * temperament))
    jerk = max(0.05, float(parameters["j_max_mps3"]) * temperament)
    plan_decel = max(0.1, float(parameters["traffic_light_plan_decel_mps2"]))
    stop_tolerance = max(0.5, float(parameters["traffic_light_stop_tolerance_m"]))

    if bool(parameters["use_trailer_model"]):
        mass = max(100.0, float(parameters["vehicle_mass_kg"]) + float(parameters["trailer_mass_kg"]))
        rolling = max(0.0, float(parameters["rolling_resistance_coeff"])) * 9.81
        accel = min(accel, max(0.1, float(parameters["max_drive_force_n"]) / mass - rolling))
        brake = min(brake, max(0.1, float(parameters["max_brake_force_n"]) / mass + rolling))

    end_stop = route.total_distance_m if bool(parameters["end_stop"]) else math.inf
    all_stops = list(float(value) for value in stop_positions)
    all_dwell = list(float(value) for value in dwell_durations)
    if math.isfinite(end_stop):
        all_stops.append(end_stop)
        all_dwell.append(0.0)

    time_values = [0.0]
    distance_values = [0.0]
    speed_values = [0.0 if bool(parameters["start_stop"]) else float(planned_mps[0])]
    acceleration_values = [0.0]
    target_values = [float(planned_mps[0])]
    dwell_intervals: list[tuple[float, float]] = []

    x = 0.0
    v = speed_values[0]
    a = 0.0
    stop_index = 0
    maximum_steps = int(max(20_000, route.total_distance_m / max(0.2, dt * 0.5)))

    for _ in range(maximum_steps):
        if x >= route.total_distance_m - 0.25 and (not bool(parameters["end_stop"]) or v < 0.4):
            break

        lookahead_x = min(route.total_distance_m, x + max(5.0, v * 0.7))
        target = max(
            float(np.interp(x, route.distance_m, planned_mps)),
            float(np.interp(lookahead_x, route.distance_m, planned_mps)),
        )
        cap = float(np.interp(x, route.distance_m, hard_cap_mps))

        next_stop = all_stops[stop_index] if stop_index < len(all_stops) else math.inf
        distance_to_stop = next_stop - x
        if distance_to_stop >= -stop_tolerance:
            stop_cap = math.sqrt(max(0.0, 2.0 * plan_decel * max(0.0, distance_to_stop)))
            target = min(target, stop_cap)

        if next_stop < math.inf and abs(distance_to_stop) <= stop_tolerance and v < 0.55:
            x = min(next_stop, route.total_distance_m)
            v = 0.0
            a = 0.0
            dwell = all_dwell[stop_index]
            if dwell > 0.0:
                start_time = time_values[-1]
                hold_steps = max(1, int(round(dwell / dt)))
                for _hold in range(hold_steps):
                    time_values.append(time_values[-1] + dt)
                    distance_values.append(x)
                    speed_values.append(0.0)
                    acceleration_values.append(0.0)
                    target_values.append(0.0)
                dwell_intervals.append((start_time, time_values[-1]))
            stop_index += 1
            if x >= route.total_distance_m - 0.25:
                break
            continue

        desired_acceleration = float(np.clip(kp * (target - v), -brake, accel))
        acceleration_change = float(np.clip(desired_acceleration - a, -jerk * dt, jerk * dt))
        a = float(np.clip(a + acceleration_change, -brake, accel))
        new_v = max(0.0, v + a * dt)
        new_v = min(new_v, cap)
        new_x = min(route.total_distance_m, x + max(0.0, (v + new_v) * 0.5 * dt))

        if next_stop < math.inf and new_x > next_stop:
            new_x = next_stop
            if new_v < 1.0:
                new_v = 0.0

        x, v = new_x, new_v
        time_values.append(time_values[-1] + dt)
        distance_values.append(x)
        speed_values.append(v)
        acceleration_values.append(a)
        target_values.append(target)

    return {
        "time_s": np.asarray(time_values, dtype=float),
        "distance_m": np.asarray(distance_values, dtype=float),
        "speed_mps": np.asarray(speed_values, dtype=float),
        "acceleration_mps2": np.asarray(acceleration_values, dtype=float),
        "target_mps": np.asarray(target_values, dtype=float),
        "dwell_intervals_s": dwell_intervals,
    }


def simulate_speed_profile(
    route: Mapping[str, Any] | PreparedRoute,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    params = merged_parameters(parameters)
    prepared = route if isinstance(route, PreparedRoute) else prepare_route(route, params["sample_distance_m"])
    rng = np.random.default_rng(int(params["simulation_seed"]))
    temperament = float(np.clip(params["temperament"], 0.4, 1.8))

    road_limit = np.maximum(5.0, prepared.maxspeed_kmh.astype(float))
    surface_limit = road_limit * (_surface_factor(prepared.surface) if params["use_surface_limit"] else 1.0)
    driver_limit = min(
        float(params["driver_cruise_kmh"]) + float(params["speed_bias_kmh"]) + (temperament - 1.0) * 2.0,
        float(params["driver_hard_max_kmh"]),
    )
    base_target = np.minimum.reduce((road_limit, surface_limit, np.full_like(road_limit, driver_limit)))

    radius = _curve_radius(prepared, params)
    if bool(params["apply_curve_speed"]):
        lat_accel = max(0.2, float(params["max_lat_accel_mps2"]) * math.sqrt(temperament))
        curve_limit = np.sqrt(lat_accel * radius) * 3.6
    else:
        curve_limit = np.full_like(base_target, np.inf)
    target = np.minimum(base_target, curve_limit)

    requested_lights = int(params["traffic_light_count"]) if bool(params["use_traffic_lights"]) else 0
    stop_positions = _choose_event_positions(
        prepared,
        requested_lights,
        prepared.detected_signal_distances_m,
        rng,
    )
    dwell_min = max(0.0, float(params["traffic_light_dwell_min_s"]))
    dwell_max = max(dwell_min, float(params["traffic_light_dwell_max_s"]))
    dwell_durations = rng.uniform(dwell_min, dwell_max, size=len(stop_positions)) if len(stop_positions) else np.empty(0)

    overtaking = _overtaking_events(prepared, params, stop_positions, rng)
    slow_speed = max(5.0, float(params["overtaking_slow_speed_kmh"]))
    intensity = max(0.0, float(params["overtaking_intensity_kmh"]))
    for event in overtaking:
        follow_mask = (prepared.distance_m >= event["follow_start_m"]) & (prepared.distance_m < event["center_m"])
        pass_mask = (prepared.distance_m >= event["center_m"]) & (prepared.distance_m <= event["pass_end_m"])
        target[follow_mask] = np.minimum(target[follow_mask], slow_speed)
        pass_desire = np.minimum(road_limit[pass_mask], slow_speed + intensity)
        target[pass_mask] = np.maximum(target[pass_mask], pass_desire)

    noise = _apply_driver_noise(target, prepared, params, rng)
    target = target + noise
    hard_cap_kmh = np.minimum.reduce(
        (
            road_limit + float(params["speed_tolerance_kmh"]),
            curve_limit + float(params["speed_tolerance_kmh"]),
            np.full_like(road_limit, float(params["driver_hard_max_kmh"])),
        )
    )
    target = np.clip(target, 0.0, hard_cap_kmh)

    if bool(params["start_stop"]):
        target[0] = 0.0
    if bool(params["end_stop"]):
        target[-1] = 0.0
    if len(stop_positions):
        stop_indexes = np.asarray(
            [int(np.argmin(np.abs(prepared.distance_m - position))) for position in stop_positions],
            dtype=int,
        )
        target[stop_indexes] = 0.0

    accel = max(0.1, float(params["a_max_mps2"]) * temperament)
    brake = max(
        0.1,
        min(float(params["b_max_mps2"]), float(params["curve_plan_decel_mps2"]))
        * (0.85 + 0.15 * temperament),
    )
    planned_mps = _kinematic_spatial_limit(target / 3.6, prepared.distance_m, accel, brake)
    time_result = _simulate_time(
        prepared,
        planned_mps,
        hard_cap_kmh / 3.6,
        stop_positions,
        dwell_durations,
        params,
    )

    time_distance = np.asarray(time_result["distance_m"])
    time_speed = np.asarray(time_result["speed_mps"])
    unique_distance, unique_indexes = np.unique(time_distance, return_index=True)
    if len(unique_distance) >= 2:
        actual_distance_speed = np.interp(prepared.distance_m, unique_distance, time_speed[unique_indexes])
    else:
        actual_distance_speed = np.zeros_like(prepared.distance_m)

    duration = float(np.asarray(time_result["time_s"])[-1])
    moving = np.asarray(time_result["speed_mps"]) > 0.3
    moving_time = float(np.count_nonzero(moving) * float(params["dt_s"]))
    average_speed = prepared.total_distance_m / max(duration, 1e-6) * 3.6

    return {
        "prepared_route": prepared,
        "parameters": params,
        "distance": {
            "distance_m": prepared.distance_m,
            "road_limit_kmh": road_limit,
            "surface_limit_kmh": surface_limit,
            "curve_limit_kmh": curve_limit,
            "base_target_kmh": base_target,
            "planned_speed_kmh": planned_mps * 3.6,
            "actual_speed_kmh": actual_distance_speed * 3.6,
            "noise_kmh": noise,
            "curve_radius_m": radius,
            "latitude": prepared.latitude,
            "longitude": prepared.longitude,
        },
        "time": {
            "time_s": np.asarray(time_result["time_s"]),
            "distance_m": np.asarray(time_result["distance_m"]),
            "speed_kmh": np.asarray(time_result["speed_mps"]) * 3.6,
            "target_kmh": np.asarray(time_result["target_mps"]) * 3.6,
            "acceleration_mps2": np.asarray(time_result["acceleration_mps2"]),
        },
        "events": {
            "traffic_lights": [
                {"distance_m": float(position), "dwell_s": float(dwell)}
                for position, dwell in zip(stop_positions, dwell_durations)
            ],
            "traffic_light_dwell_intervals_s": [list(interval) for interval in time_result["dwell_intervals_s"]],
            "overtaking": overtaking,
        },
        "summary": {
            "distance_km": prepared.total_distance_m / 1000.0,
            "duration_min": duration / 60.0,
            "moving_time_min": moving_time / 60.0,
            "average_speed_kmh": average_speed,
            "maximum_speed_kmh": float(np.max(np.asarray(time_result["speed_mps"])) * 3.6),
            "traffic_light_stops": len(stop_positions),
            "overtaking_events": len(overtaking),
            "detected_traffic_lights": int(len(prepared.detected_signal_distances_m)),
        },
    }


def _serializable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, PreparedRoute):
        return {
            "total_distance_m": value.total_distance_m,
            "detected_signal_distances_m": value.detected_signal_distances_m.tolist(),
        }
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def export_simulation(result: Mapping[str, Any], output_prefix: str | Path) -> tuple[Path, Path]:
    prefix = Path(output_prefix).expanduser().resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")

    json_path.write_text(
        json.dumps(_serializable(dict(result)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    time_data = result["time"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["time_s", "distance_m", "speed_kmh", "target_kmh", "acceleration_mps2"]
        )
        for row in zip(
            time_data["time_s"],
            time_data["distance_m"],
            time_data["speed_kmh"],
            time_data["target_kmh"],
            time_data["acceleration_mps2"],
        ):
            writer.writerow([float(value) for value in row])
    return json_path, csv_path
