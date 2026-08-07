from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

try:
    from . import speed_simulation as _base
except ImportError:
    import speed_simulation as _base


DEFAULT_POST_CURVE_PARAMETERS: dict[str, Any] = {
    "use_post_curve_overshoot": True,
    "post_curve_overshoot_kmh": 3.0,
    "post_curve_overshoot_probability_pct": 60.0,
    "post_curve_overshoot_distance_m": 90.0,
}


def _post_curve_boost(
    result: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> tuple[np.ndarray, list[dict[str, float]]]:
    distance_data = result["distance"]
    distance = np.asarray(distance_data["distance_m"], dtype=float)
    base_target = np.asarray(distance_data["base_target_kmh"], dtype=float)
    curve_limit = np.asarray(distance_data["curve_limit_kmh"], dtype=float)
    boost = np.zeros_like(distance)

    if not bool(parameters.get("use_post_curve_overshoot", True)):
        return boost, []

    amplitude = max(0.0, float(parameters.get("post_curve_overshoot_kmh", 3.0)))
    probability = float(
        np.clip(
            float(parameters.get("post_curve_overshoot_probability_pct", 60.0)) / 100.0,
            0.0,
            1.0,
        )
    )
    decay_distance = max(
        20.0,
        float(parameters.get("post_curve_overshoot_distance_m", 90.0)),
    )
    if amplitude <= 0.0 or probability <= 0.0 or len(distance) < 3:
        return boost, []

    # A curve is relevant only if it actually forces the desired speed at least
    # 2 km/h below the normal driver target. This avoids triggering on tiny
    # curvature fluctuations on an otherwise straight road.
    curve_active = np.isfinite(curve_limit) & (curve_limit <= base_target - 2.0)
    exits = np.where(curve_active[:-1] & ~curve_active[1:])[0] + 1
    if exits.size == 0:
        return boost, []

    seed = int(parameters.get("simulation_seed", 42)) + 10_007
    rng = np.random.default_rng(seed)
    events: list[dict[str, float]] = []

    stop_positions = [
        float(item["distance_m"])
        for item in result.get("events", {}).get("traffic_lights", [])
    ]
    overtaking = result.get("events", {}).get("overtaking", [])

    for exit_index in exits:
        if rng.random() > probability:
            continue

        exit_m = float(distance[int(exit_index)])
        if exit_m > float(distance[-1]) - 120.0:
            continue
        if any(abs(exit_m - stop) < 180.0 for stop in stop_positions):
            continue
        if any(
            float(event.get("follow_start_m", math.inf)) - 60.0
            <= exit_m
            <= float(event.get("pass_end_m", -math.inf)) + 60.0
            for event in overtaking
        ):
            continue

        # Driver response: first actively accelerate for about 20 m, then let
        # the extra target speed decay smoothly back to the cruise target.
        rise_distance = min(25.0, max(10.0, decay_distance * 0.22))
        window_end = min(float(distance[-1]), exit_m + rise_distance + 3.0 * decay_distance)
        indexes = np.where((distance >= exit_m) & (distance <= window_end))[0]
        if indexes.size == 0:
            continue

        local_distance = distance[indexes] - exit_m
        local_boost = np.empty_like(local_distance)
        rising = local_distance <= rise_distance
        local_boost[rising] = amplitude * np.sin(
            0.5 * math.pi * local_distance[rising] / max(rise_distance, 1e-6)
        )
        local_boost[~rising] = amplitude * np.exp(
            -(local_distance[~rising] - rise_distance) / decay_distance
        )
        boost[indexes] = np.maximum(boost[indexes], local_boost)
        events.append(
            {
                "curve_exit_m": exit_m,
                "peak_boost_kmh": amplitude,
                "rise_distance_m": rise_distance,
                "decay_distance_m": decay_distance,
            }
        )

    return boost, events


def simulate_speed_profile(
    route: Mapping[str, Any] | _base.PreparedRoute,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    params = _base.merged_parameters(parameters)
    for key, value in DEFAULT_POST_CURVE_PARAMETERS.items():
        params.setdefault(key, value)

    result = _base.simulate_speed_profile(route, params)
    boost, boost_events = _post_curve_boost(result, params)
    result["distance"]["post_curve_boost_kmh"] = boost
    result["events"]["post_curve_overshoot"] = boost_events

    if not boost_events or not np.any(boost > 1e-6):
        return result

    prepared = result["prepared_route"]
    distance_data = result["distance"]
    distance = np.asarray(distance_data["distance_m"], dtype=float)
    road_limit = np.asarray(distance_data["road_limit_kmh"], dtype=float)
    curve_limit = np.asarray(distance_data["curve_limit_kmh"], dtype=float)
    base_target = np.asarray(distance_data["base_target_kmh"], dtype=float)
    old_planned = np.asarray(distance_data["planned_speed_kmh"], dtype=float)

    tolerance = max(0.0, float(params["speed_tolerance_kmh"]))
    hard_cap_kmh = np.minimum.reduce(
        (
            road_limit + tolerance,
            curve_limit + tolerance,
            np.full_like(road_limit, float(params["driver_hard_max_kmh"])),
        )
    )

    # The overshoot raises only the driver's desired speed after a real curve.
    # It never raises the physical/legal cap. On a 30 km/h cruise target this
    # creates a temporary 32-33 km/h desire where the road limit permits it.
    enhanced_target = np.maximum(old_planned, base_target + boost)
    enhanced_target = np.minimum(enhanced_target, hard_cap_kmh)

    stop_positions = np.asarray(
        [float(item["distance_m"]) for item in result["events"]["traffic_lights"]],
        dtype=float,
    )
    if stop_positions.size:
        for position in stop_positions:
            index = int(np.argmin(np.abs(distance - position)))
            enhanced_target[index] = 0.0
    if bool(params["end_stop"]):
        enhanced_target[-1] = 0.0
    if bool(params["start_stop"]):
        enhanced_target[0] = 0.0

    temperament = float(np.clip(params["temperament"], 0.4, 1.8))
    accel = max(0.1, float(params["a_max_mps2"]) * temperament)
    brake = max(
        0.1,
        min(float(params["b_max_mps2"]), float(params["curve_plan_decel_mps2"]))
        * (0.85 + 0.15 * temperament),
    )
    planned_mps = _base._kinematic_spatial_limit(
        enhanced_target / 3.6,
        distance,
        accel,
        brake,
    )

    dwell_durations = np.asarray(
        [float(item["dwell_s"]) for item in result["events"]["traffic_lights"]],
        dtype=float,
    )
    time_result = _base._simulate_time(
        prepared,
        planned_mps,
        hard_cap_kmh / 3.6,
        stop_positions,
        dwell_durations,
        params,
    )

    time_distance = np.asarray(time_result["distance_m"], dtype=float)
    time_speed = np.asarray(time_result["speed_mps"], dtype=float)
    unique_distance, unique_indexes = np.unique(time_distance, return_index=True)
    if len(unique_distance) >= 2:
        actual_distance_speed = np.interp(
            distance,
            unique_distance,
            time_speed[unique_indexes],
        )
    else:
        actual_distance_speed = np.zeros_like(distance)

    result["distance"]["planned_speed_kmh"] = planned_mps * 3.6
    result["distance"]["actual_speed_kmh"] = actual_distance_speed * 3.6
    result["time"] = {
        "time_s": np.asarray(time_result["time_s"]),
        "distance_m": np.asarray(time_result["distance_m"]),
        "speed_kmh": np.asarray(time_result["speed_mps"]) * 3.6,
        "target_kmh": np.asarray(time_result["target_mps"]) * 3.6,
        "acceleration_mps2": np.asarray(time_result["acceleration_mps2"]),
    }
    result["events"]["traffic_light_dwell_intervals_s"] = [
        list(interval) for interval in time_result["dwell_intervals_s"]
    ]

    duration = float(np.asarray(time_result["time_s"])[-1])
    moving = np.asarray(time_result["speed_mps"]) > 0.3
    moving_time = float(np.count_nonzero(moving) * float(params["dt_s"]))
    result["summary"].update(
        {
            "duration_min": duration / 60.0,
            "moving_time_min": moving_time / 60.0,
            "average_speed_kmh": prepared.total_distance_m / max(duration, 1e-6) * 3.6,
            "maximum_speed_kmh": float(np.max(np.asarray(time_result["speed_mps"])) * 3.6),
            "post_curve_overshoots": len(boost_events),
        }
    )
    return result
