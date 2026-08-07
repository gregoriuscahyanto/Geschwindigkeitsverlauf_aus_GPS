from __future__ import annotations

import numpy as np


def cumulative_load_curve(
    time_s: np.ndarray,
    load_values: np.ndarray,
    *,
    positive_only: bool = False,
    normalize: bool = False,
) -> dict[str, np.ndarray]:
    """Return a time-weighted cumulative load-duration curve.

    The load samples are sorted from high to low. The x-axis is cumulative
    driving-time share in percent and the y-axis is the corresponding load.
    This is the load-duration / cumulative collective representation commonly
    used for duty-cycle comparisons.
    """

    time = np.asarray(time_s, dtype=float)
    load = np.asarray(load_values, dtype=float)
    if time.shape != load.shape or time.size == 0:
        return {
            "time_share_pct": np.empty(0, dtype=float),
            "load": np.empty(0, dtype=float),
        }

    weights = np.diff(time, prepend=time[0])
    weights = np.maximum(0.0, np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0))
    valid = np.isfinite(load) & np.isfinite(weights) & (weights >= 0.0)
    if positive_only:
        valid &= load > 0.0
    if not np.any(valid):
        return {
            "time_share_pct": np.empty(0, dtype=float),
            "load": np.empty(0, dtype=float),
        }

    values = load[valid]
    durations = weights[valid]
    positive_duration = float(np.sum(durations))
    if positive_duration <= 0.0:
        return {
            "time_share_pct": np.empty(0, dtype=float),
            "load": np.empty(0, dtype=float),
        }

    order = np.argsort(values, kind="stable")[::-1]
    values = values[order]
    durations = durations[order]

    cumulative = np.cumsum(durations) / positive_duration * 100.0
    # A strictly positive first x value keeps the same data usable with an
    # optional logarithmic time-share axis.
    minimum_share = max(1e-4, 100.0 / max(1.0, float(len(cumulative)) * 100.0))
    cumulative = np.maximum(cumulative, minimum_share)

    if normalize:
        reference = float(np.max(np.abs(values))) if values.size else 0.0
        if reference > 1e-12:
            values = values / reference

    return {
        "time_share_pct": cumulative,
        "load": values,
    }
