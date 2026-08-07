from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np


GRAVITY_MPS2 = 9.80665


def _trapezoidal_integral(values: np.ndarray, coordinates: np.ndarray) -> float:
    """Integrate compatibly with NumPy 1.26 and NumPy 2.x."""

    trapezoid = getattr(np, "trapezoid", None)
    if callable(trapezoid):
        return float(trapezoid(values, coordinates))
    trapz = getattr(np, "trapz", None)
    if callable(trapz):
        return float(trapz(values, coordinates))
    # Very old/unusual NumPy fallback: explicit trapezoidal rule.
    if len(values) < 2:
        return 0.0
    dx = np.diff(coordinates)
    return float(np.sum((values[:-1] + values[1:]) * 0.5 * dx))


def road_grade(
    distance_m: np.ndarray,
    elevation_m: np.ndarray,
    *,
    smoothing_distance_m: float = 40.0,
    max_abs_grade: float = 0.35,
) -> np.ndarray:
    """Return smoothed road grade dz/ds as a dimensionless fraction.

    Missing elevations are interpolated when at least two finite samples exist.
    The clipping only protects the power model from isolated DEM artefacts; it is
    not intended to replace proper tunnel/bridge elevation handling.
    """

    distance = np.asarray(distance_m, dtype=float)
    elevation = np.asarray(elevation_m, dtype=float)
    if distance.shape != elevation.shape or distance.size < 2:
        return np.zeros_like(distance, dtype=float)

    finite = np.isfinite(distance) & np.isfinite(elevation)
    if np.count_nonzero(finite) < 2:
        return np.zeros_like(distance, dtype=float)

    clean_elevation = elevation.copy()
    clean_elevation[~np.isfinite(clean_elevation)] = np.interp(
        distance[~np.isfinite(clean_elevation)],
        distance[finite],
        elevation[finite],
    )

    positive_steps = np.diff(distance)
    positive_steps = positive_steps[positive_steps > 1e-6]
    if positive_steps.size:
        step = float(np.median(positive_steps))
        half_window = max(0, int(round(max(0.0, smoothing_distance_m) / step / 2.0)))
    else:
        half_window = 0

    if half_window > 0 and clean_elevation.size >= 3:
        kernel_size = 2 * half_window + 1
        padded = np.pad(clean_elevation, (half_window, half_window), mode="edge")
        kernel = np.ones(kernel_size, dtype=float) / float(kernel_size)
        clean_elevation = np.convolve(padded, kernel, mode="valid")

    safe_distance = distance.copy()
    for index in range(1, len(safe_distance)):
        if safe_distance[index] <= safe_distance[index - 1]:
            safe_distance[index] = safe_distance[index - 1] + 1e-3

    grade = np.gradient(clean_elevation, safe_distance, edge_order=1)
    grade[~np.isfinite(grade)] = 0.0
    limit = max(0.01, float(max_abs_grade))
    return np.clip(grade, -limit, limit)


def calculate_resistance_power(
    time_s: np.ndarray,
    speed_kmh: np.ndarray,
    acceleration_mps2: np.ndarray,
    grade_fraction: np.ndarray,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate signed wheel power from longitudinal resistance components.

    Positive power means tractive power is required at the wheels. Negative
    total power means braking/overrun power is required. Trailer inertia,
    climbing, rolling and aerodynamic load are grouped into one explicit
    trailer component so the base vehicle components stay easy to interpret.
    """

    time = np.asarray(time_s, dtype=float)
    speed = np.asarray(speed_kmh, dtype=float) / 3.6
    acceleration = np.asarray(acceleration_mps2, dtype=float)
    grade = np.asarray(grade_fraction, dtype=float)
    if not (time.shape == speed.shape == acceleration.shape == grade.shape):
        raise ValueError("Zeit, Geschwindigkeit, Beschleunigung und Steigung müssen gleich lang sein.")

    speed = np.maximum(0.0, np.nan_to_num(speed, nan=0.0, posinf=0.0, neginf=0.0))
    acceleration = np.nan_to_num(acceleration, nan=0.0, posinf=0.0, neginf=0.0)
    grade = np.nan_to_num(grade, nan=0.0, posinf=0.0, neginf=0.0)

    vehicle_mass = max(1.0, float(parameters.get("vehicle_mass_kg", 1800.0)))
    rolling_coeff = max(0.0, float(parameters.get("rolling_resistance_coeff", 0.015)))
    drag_coefficient = max(0.0, float(parameters.get("air_drag_coefficient", 0.29)))
    frontal_area = max(0.0, float(parameters.get("frontal_area_m2", 2.3)))
    air_density = max(0.0, float(parameters.get("air_density_kg_m3", 1.225)))

    angle = np.arctan(grade)
    sin_angle = np.sin(angle)
    cos_angle = np.cos(angle)

    acceleration_force = vehicle_mass * acceleration
    grade_force = vehicle_mass * GRAVITY_MPS2 * sin_angle
    rolling_force = vehicle_mass * GRAVITY_MPS2 * rolling_coeff * cos_angle
    air_force = 0.5 * air_density * drag_coefficient * frontal_area * speed**2

    trailer_force = np.zeros_like(speed)
    trailer_enabled = bool(parameters.get("use_trailer_model", False))
    trailer_mass = max(0.0, float(parameters.get("trailer_mass_kg", 0.0))) if trailer_enabled else 0.0
    if trailer_mass > 0.0:
        trailer_rolling = max(
            0.0,
            float(parameters.get("trailer_rolling_resistance_coeff", rolling_coeff)),
        )
        trailer_drag_area = max(0.0, float(parameters.get("trailer_drag_area_m2", 1.0)))
        trailer_force = (
            trailer_mass * acceleration
            + trailer_mass * GRAVITY_MPS2 * sin_angle
            + trailer_mass * GRAVITY_MPS2 * trailer_rolling * cos_angle
            + 0.5 * air_density * trailer_drag_area * speed**2
        )

    component_forces = {
        "acceleration": acceleration_force,
        "grade": grade_force,
        "rolling": rolling_force,
        "air": air_force,
        "trailer": trailer_force,
    }
    power_kw = {
        key: force * speed / 1000.0 for key, force in component_forces.items()
    }
    total_kw = sum(power_kw.values(), np.zeros_like(speed))

    if len(time) >= 2:
        traction_energy_kwh = _trapezoidal_integral(
            np.maximum(total_kw, 0.0), time
        ) / 3600.0
        braking_energy_kwh = _trapezoidal_integral(
            np.maximum(-total_kw, 0.0), time
        ) / 3600.0
    else:
        traction_energy_kwh = 0.0
        braking_energy_kwh = 0.0

    positive = total_kw[total_kw > 0.0]
    p95_kw = float(np.percentile(positive, 95.0)) if positive.size else 0.0

    return {
        "time_s": time,
        "grade_fraction": grade,
        "grade_pct": grade * 100.0,
        "acceleration_kw": power_kw["acceleration"],
        "grade_kw": power_kw["grade"],
        "rolling_kw": power_kw["rolling"],
        "air_kw": power_kw["air"],
        "trailer_kw": power_kw["trailer"],
        "total_kw": total_kw,
        "traction_energy_kwh": traction_energy_kwh,
        "braking_energy_kwh": braking_energy_kwh,
        "p95_positive_kw": p95_kw,
        "maximum_kw": float(np.max(total_kw)) if total_kw.size else 0.0,
        "minimum_kw": float(np.min(total_kw)) if total_kw.size else 0.0,
        "trailer_enabled": trailer_enabled and trailer_mass > 0.0,
    }


def load_collective(
    time_s: np.ndarray,
    power_kw: np.ndarray,
    *,
    bin_count: int = 14,
) -> dict[str, np.ndarray]:
    """Create a time-weighted load collective over signed wheel power."""

    time = np.asarray(time_s, dtype=float)
    power = np.asarray(power_kw, dtype=float)
    if time.shape != power.shape or time.size == 0:
        return {
            "centers_kw": np.empty(0),
            "widths_kw": np.empty(0),
            "time_share_pct": np.empty(0),
            "duration_s": np.empty(0),
        }

    weights = np.diff(time, prepend=time[0])
    weights = np.maximum(0.0, np.nan_to_num(weights, nan=0.0))
    valid = np.isfinite(power) & np.isfinite(weights)
    if not np.any(valid) or float(np.sum(weights[valid])) <= 0.0:
        return {
            "centers_kw": np.empty(0),
            "widths_kw": np.empty(0),
            "time_share_pct": np.empty(0),
            "duration_s": np.empty(0),
        }

    values = power[valid]
    value_min = float(np.min(values))
    value_max = float(np.max(values))
    if math.isclose(value_min, value_max, abs_tol=1e-9):
        pad = max(5.0, abs(value_min) * 0.15 + 1.0)
        value_min -= pad
        value_max += pad

    bins = np.linspace(value_min, value_max, max(4, int(bin_count)) + 1)
    duration, edges = np.histogram(values, bins=bins, weights=weights[valid])
    total_duration = float(np.sum(duration))
    centers = (edges[:-1] + edges[1:]) * 0.5
    widths = np.diff(edges)
    shares = duration / max(total_duration, 1e-9) * 100.0
    return {
        "centers_kw": centers,
        "widths_kw": widths,
        "time_share_pct": shares,
        "duration_s": duration,
    }