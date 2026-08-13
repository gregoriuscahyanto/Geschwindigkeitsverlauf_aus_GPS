from __future__ import annotations

import copy
import math
from typing import Any, Callable, Mapping

import numpy as np

try:
    from . import speed_simulation as _simulation
except ImportError:
    import speed_simulation as _simulation


POLICY_OBEY = "obey"
POLICY_IGNORE = "ignore"
POLICY_GERMANY_POINTS = "germany_points"

POLICY_LABELS = {
    POLICY_OBEY: "Geschwindigkeitslimit beachten",
    POLICY_IGNORE: "Ohne Rücksicht auf Geschwindigkeitslimit",
    POLICY_GERMANY_POINTS: "Deutschland: max. Punkte",
}

# Conservative passenger-car envelope for Germany. It deliberately uses the
# stricter common bound when inner/outer locality is not known from the route:
# <=20 km/h over -> no point, <=30 -> at most one point, above -> up to two.
_GERMANY_PASSENGER_CAR_MAX_OVER_KMH = {
    0: 20.0,
    1: 30.0,
    2: math.inf,
}

Simulator = Callable[
    [Mapping[str, Any] | _simulation.PreparedRoute, Mapping[str, Any] | None],
    dict[str, Any],
]


def normalize_policy(value: Any) -> str:
    text = str(value or POLICY_OBEY).strip().lower()
    return text if text in POLICY_LABELS else POLICY_OBEY


def germany_max_overspeed_kmh(max_points: Any) -> float:
    try:
        points = int(max_points)
    except (TypeError, ValueError):
        points = 0
    points = min(2, max(0, points))
    return float(_GERMANY_PASSENGER_CAR_MAX_OVER_KMH[points])


def conservative_germany_points(overspeed_kmh: np.ndarray | float) -> np.ndarray:
    over = np.maximum(0.0, np.asarray(overspeed_kmh, dtype=float))
    return np.where(
        over <= 20.0 + 1e-9,
        0.0,
        np.where(over <= 30.0 + 1e-9, 1.0, 2.0),
    )


def _effective_limit_value(
    legal_limit_kmh: float,
    parameters: Mapping[str, Any],
    policy: str,
) -> float:
    legal = max(5.0, float(legal_limit_kmh))
    hard_max = max(5.0, float(parameters.get("driver_hard_max_kmh", 140.0)))
    if policy == POLICY_IGNORE:
        return hard_max
    if policy == POLICY_GERMANY_POINTS:
        allowance = germany_max_overspeed_kmh(parameters.get("max_speeding_points", 0))
        if math.isinf(allowance):
            return hard_max
        # The established model uses speed_tolerance_kmh both as a driver-noise
        # band and as a final hard-cap allowance. Reserve that band inside the
        # selected point envelope so noise cannot cross the configured limit.
        tolerance = max(0.0, float(parameters.get("speed_tolerance_kmh", 0.0)))
        nominal_allowance = max(0.0, allowance - tolerance)
        return min(hard_max, legal + nominal_allowance)
    return legal


def _policy_route(
    route: Mapping[str, Any],
    parameters: Mapping[str, Any],
    policy: str,
) -> dict[str, Any]:
    adjusted = copy.deepcopy(dict(route))
    for segment in adjusted.get("segments", []) or []:
        if not isinstance(segment, dict):
            continue
        try:
            legal = float(segment.get("maxspeed_kmh", 30.0))
        except (TypeError, ValueError):
            legal = 30.0
        if not math.isfinite(legal) or legal <= 0.0:
            legal = 30.0
        segment["maxspeed_kmh"] = _effective_limit_value(legal, parameters, policy)
    return adjusted


def _policy_prepared_route(
    route: _simulation.PreparedRoute,
    parameters: Mapping[str, Any],
    policy: str,
) -> _simulation.PreparedRoute:
    limits = np.asarray(route.maxspeed_kmh, dtype=float).copy()
    for index, legal in enumerate(limits):
        limits[index] = _effective_limit_value(float(legal), parameters, policy)
    return _simulation.PreparedRoute(
        distance_m=np.asarray(route.distance_m).copy(),
        x_m=np.asarray(route.x_m).copy(),
        y_m=np.asarray(route.y_m).copy(),
        latitude=np.asarray(route.latitude).copy(),
        longitude=np.asarray(route.longitude).copy(),
        maxspeed_kmh=limits,
        surface=np.asarray(route.surface).copy(),
        highway=np.asarray(route.highway).copy(),
        detected_signal_distances_m=np.asarray(route.detected_signal_distances_m).copy(),
        total_distance_m=float(route.total_distance_m),
    )


def _nearest_spatial_values(
    source_distance: np.ndarray,
    source_values: np.ndarray,
    query_distance: np.ndarray,
) -> np.ndarray:
    source_distance = np.asarray(source_distance, dtype=float).reshape(-1)
    source_values = np.asarray(source_values, dtype=float).reshape(-1)
    query_distance = np.asarray(query_distance, dtype=float).reshape(-1)
    if source_distance.size == 0 or source_distance.size != source_values.size:
        return np.full(query_distance.shape, np.nan, dtype=float)
    positions = np.searchsorted(source_distance, query_distance, side="right") - 1
    positions = np.clip(positions, 0, source_distance.size - 1)
    return source_values[positions]


def simulate_with_policy(
    simulator: Simulator,
    route: Mapping[str, Any] | _simulation.PreparedRoute,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the policy around any compatible established speed simulator."""

    params = _simulation.merged_parameters(parameters)
    policy = normalize_policy(params.get("speed_limit_policy", POLICY_OBEY))
    try:
        max_points = min(2, max(0, int(params.get("max_speeding_points", 0))))
    except (TypeError, ValueError):
        max_points = 0
    params["speed_limit_policy"] = policy
    params["max_speeding_points"] = max_points

    if isinstance(route, _simulation.PreparedRoute):
        legal_prepared = route
        adjusted_route: Mapping[str, Any] | _simulation.PreparedRoute = _policy_prepared_route(
            route, params, policy
        )
    else:
        sample_distance = max(1.0, float(params.get("sample_distance_m", 5.0)))
        legal_prepared = _simulation.prepare_route(route, sample_distance)
        adjusted_route = _policy_route(route, params, policy)

    result = simulator(adjusted_route, params)
    distance = result.get("distance", {})
    time = result.get("time", {})
    summary = result.get("summary", {})

    spatial_distance = np.asarray(distance.get("distance_m", []), dtype=float)
    effective_limit = np.asarray(distance.get("road_limit_kmh", []), dtype=float).copy()
    legal_limit = np.asarray(legal_prepared.maxspeed_kmh, dtype=float)
    legal_distance = np.asarray(legal_prepared.distance_m, dtype=float)
    if legal_limit.size != spatial_distance.size or not np.allclose(
        legal_distance, spatial_distance, rtol=0.0, atol=1e-6
    ):
        legal_limit = _nearest_spatial_values(legal_distance, legal_limit, spatial_distance)

    distance["road_limit_kmh"] = legal_limit
    distance["speed_policy_limit_kmh"] = effective_limit
    actual_spatial = np.asarray(distance.get("actual_speed_kmh", []), dtype=float)
    spatial_over = np.maximum(0.0, actual_spatial - legal_limit)
    distance["speeding_over_kmh"] = spatial_over
    distance["speeding_points"] = conservative_germany_points(spatial_over)

    time_distance = np.asarray(time.get("distance_m", []), dtype=float)
    time_speed = np.asarray(time.get("speed_kmh", []), dtype=float)
    time_legal = _nearest_spatial_values(spatial_distance, legal_limit, time_distance)
    time_effective = _nearest_spatial_values(spatial_distance, effective_limit, time_distance)
    time_over = np.maximum(0.0, time_speed - time_legal)
    time["road_limit_kmh"] = time_legal
    time["speed_policy_limit_kmh"] = time_effective
    time["speeding_over_kmh"] = time_over
    time["speeding_points"] = conservative_germany_points(time_over)

    summary["speed_limit_policy"] = policy
    summary["configured_max_speeding_points"] = float(max_points)
    summary["max_speeding_over_kmh"] = float(np.nanmax(time_over)) if time_over.size else 0.0
    points = np.asarray(time["speeding_points"], dtype=float)
    summary["max_speeding_points_estimated"] = float(np.nanmax(points)) if points.size else 0.0
    return result


def simulate_speed_profile(
    route: Mapping[str, Any] | _simulation.PreparedRoute,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the base simulator with the configured speed-limit policy."""

    return simulate_with_policy(_simulation.simulate_speed_profile, route, parameters)


def install_integrated_speed_profile_policy() -> None:
    """Wrap the enhanced simulator used by the integrated GUI exactly once."""

    try:
        from ._internal.simulation_layers import integrated_speed_profile_v4 as layer
    except ImportError:
        try:
            from _internal.simulation_layers import integrated_speed_profile_v4 as layer
        except ImportError:
            return

    if bool(getattr(layer, "_speed_limit_policy_installed", False)):
        return
    original = getattr(layer, "_enhanced_simulate", None)
    if not callable(original):
        return

    def wrapped(
        route: Mapping[str, Any] | _simulation.PreparedRoute,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return simulate_with_policy(original, route, parameters)

    layer._enhanced_simulate = wrapped
    layer._speed_limit_policy_installed = True


__all__ = [
    "POLICY_GERMANY_POINTS",
    "POLICY_IGNORE",
    "POLICY_LABELS",
    "POLICY_OBEY",
    "conservative_germany_points",
    "germany_max_overspeed_kmh",
    "install_integrated_speed_profile_policy",
    "normalize_policy",
    "simulate_speed_profile",
    "simulate_with_policy",
]
