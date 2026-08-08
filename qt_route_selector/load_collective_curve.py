from __future__ import annotations

import numpy as np


def _empty_curve() -> dict[str, np.ndarray]:
    empty = np.empty(0, dtype=float)
    return {
        "time_share_pct": empty.copy(),
        "load": empty.copy(),
        "positive_time_share_pct": empty.copy(),
        "positive_load": empty.copy(),
        "negative_time_share_pct": empty.copy(),
        "negative_load": empty.copy(),
    }


def _branch_curve(
    values: np.ndarray,
    durations: np.ndarray,
    *,
    total_duration: float,
    descending: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Return one signed load branch starting exactly at x=0 with its peak."""

    if values.size == 0 or total_duration <= 0.0:
        return np.empty(0, dtype=float), np.empty(0, dtype=float)

    order = np.argsort(values, kind="stable")
    if descending:
        order = order[::-1]
    ordered_values = values[order]
    ordered_durations = durations[order]

    # x=0 is the peak itself. Repeating the first load value at the end of the
    # first time interval represents that the peak was present for that sample
    # duration instead of shifting the peak away from zero.
    cumulative = np.cumsum(ordered_durations) / total_duration * 100.0
    x = np.concatenate(([0.0], cumulative))
    y = np.concatenate(([ordered_values[0]], ordered_values))
    return x, y


def cumulative_load_curve(
    time_s: np.ndarray,
    load_values: np.ndarray,
    *,
    positive_only: bool = False,
    normalize: bool = False,
) -> dict[str, np.ndarray]:
    """Return a signed, time-weighted cumulative load-duration collective.

    Positive and negative loads are accumulated independently from their most
    severe values towards zero:

    * positive branch: maximum positive load -> lower positive loads
    * negative branch: minimum (most negative) load -> less negative loads

    Both branches start exactly at ``x = 0 %`` with their respective peak. The
    x-axis remains the share of the *complete valid driving time*, so the end of
    each branch also tells how much of the trip was spent at that sign of load.
    When ``positive_only`` is enabled, only the positive branch is returned.

    For backwards compatibility, ``time_share_pct`` and ``load`` refer to the
    positive branch when available (or the negative branch for an all-negative
    signal). New plotting code should prefer the explicit positive/negative keys.
    """

    time = np.asarray(time_s, dtype=float)
    load = np.asarray(load_values, dtype=float)
    if time.shape != load.shape or time.size == 0:
        return _empty_curve()

    weights = np.diff(time, prepend=time[0])
    weights = np.maximum(
        0.0,
        np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0),
    )
    valid = np.isfinite(load) & np.isfinite(weights) & (weights >= 0.0)
    if not np.any(valid):
        return _empty_curve()

    values = load[valid]
    durations = weights[valid]
    total_duration = float(np.sum(durations))
    if total_duration <= 0.0:
        return _empty_curve()

    positive_mask = values > 0.0
    negative_mask = values < 0.0

    positive_x, positive_y = _branch_curve(
        values[positive_mask],
        durations[positive_mask],
        total_duration=total_duration,
        descending=True,
    )

    if positive_only:
        negative_x = np.empty(0, dtype=float)
        negative_y = np.empty(0, dtype=float)
    else:
        negative_x, negative_y = _branch_curve(
            values[negative_mask],
            durations[negative_mask],
            total_duration=total_duration,
            descending=False,
        )

    if normalize:
        candidates: list[float] = []
        if positive_y.size:
            candidates.append(float(np.max(np.abs(positive_y))))
        if negative_y.size:
            candidates.append(float(np.max(np.abs(negative_y))))
        reference = max(candidates, default=0.0)
        if reference > 1e-12:
            positive_y = positive_y / reference
            negative_y = negative_y / reference

    if positive_x.size:
        legacy_x, legacy_y = positive_x.copy(), positive_y.copy()
    else:
        legacy_x, legacy_y = negative_x.copy(), negative_y.copy()

    return {
        "time_share_pct": legacy_x,
        "load": legacy_y,
        "positive_time_share_pct": positive_x,
        "positive_load": positive_y,
        "negative_time_share_pct": negative_x,
        "negative_load": negative_y,
    }
