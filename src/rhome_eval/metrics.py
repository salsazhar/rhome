"""Scoring primitives (``DATA.md`` §19).

Deliberately small functions with no knowledge of the engine or the simulator.
Each takes two sequences and returns a number, so a metric can be tested
against a case whose answer is known by hand rather than only against the
system that produced it.

Every function returns ``None`` rather than a number when its sample is too
small to mean anything. A metric that returns 1.0 from two points is the
vacuous-pass failure this project has now found three times, and returning
``None`` makes the caller decide what to do about it instead of hiding it.
"""

from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "pearson", "spearman", "rmse", "mae", "bias",
    "directional_accuracy", "peak_timing_error", "crossing_timing_error",
    "autocorrelation", "CalibrationBin", "calibration_bins", "drift_by_block",
]

MINIMUM_SAMPLE = 8


def _paired(a: Sequence[float], b: Sequence[float]) -> tuple[list[float], list[float]] | None:
    if len(a) != len(b):
        raise ValueError(f"unequal series: {len(a)} against {len(b)}")
    if len(a) < MINIMUM_SAMPLE:
        return None
    return list(a), list(b)


def pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    pair = _paired(a, b)
    if pair is None:
        return None
    x, y = pair
    mx, my = st.mean(x), st.mean(y)
    dx = [v - mx for v in x]
    dy = [v - my for v in y]
    denominator = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return None if denominator == 0.0 else sum(p * q for p, q in zip(dx, dy)) / denominator


def _ranks(values: Sequence[float]) -> list[float]:
    """Average ranks, so ties do not distort the correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
            stop += 1
        shared = (index + stop) / 2 + 1
        for position in range(index, stop + 1):
            ranks[order[position]] = shared
        index = stop + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    pair = _paired(a, b)
    return None if pair is None else pearson(_ranks(pair[0]), _ranks(pair[1]))


def rmse(a: Sequence[float], b: Sequence[float]) -> float | None:
    pair = _paired(a, b)
    if pair is None:
        return None
    x, y = pair
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(x, y)) / len(x))


def mae(values: Sequence[float]) -> float | None:
    return None if len(values) < MINIMUM_SAMPLE else st.mean(abs(v) for v in values)


def bias(values: Sequence[float]) -> float | None:
    return None if len(values) < MINIMUM_SAMPLE else st.mean(values)


def directional_accuracy(a: Sequence[float], b: Sequence[float]) -> float | None:
    """How often the two series move the same way from one step to the next.

    Days where either series is flat are excluded rather than counted as
    agreement: a channel that never moves would otherwise score perfectly.
    """
    pair = _paired(a, b)
    if pair is None:
        return None
    x, y = pair
    agree = considered = 0
    for i in range(1, len(x)):
        dx, dy = x[i] - x[i - 1], y[i] - y[i - 1]
        if dx == 0.0 or dy == 0.0:
            continue
        considered += 1
        agree += (dx > 0) == (dy > 0)
    return None if considered < MINIMUM_SAMPLE else agree / considered


def peak_timing_error(
    a: Sequence[float], b: Sequence[float], around: int, span: int = 5
) -> int | None:
    """Difference in where each series peaks, in a window after ``around``.

    ``DATA.md`` §19.1 asks for peak timing after high-load sessions. A model
    that reproduces the size of a fatigue spike but places it a day late is
    wrong in a way correlation is slow to notice.
    """
    lower, upper = around, min(around + span, len(a))
    if upper - lower < 3 or len(a) != len(b):
        return None
    window_a = list(a[lower:upper])
    window_b = list(b[lower:upper])
    return window_a.index(max(window_a)) - window_b.index(max(window_b))


def crossing_timing_error(
    a: Sequence[float], b: Sequence[float], threshold_a: float, threshold_b: float
) -> int | None:
    """Difference in when each series first falls below its own threshold.

    The thresholds differ because the two series are in different units; the
    caller supplies each. Returns ``None`` if either never crosses, which is
    itself worth reporting rather than papering over.
    """
    def first_below(series: Sequence[float], threshold: float) -> int | None:
        for index, value in enumerate(series):
            if value < threshold:
                return index
        return None

    index_a = first_below(a, threshold_a)
    index_b = first_below(b, threshold_b)
    return None if index_a is None or index_b is None else index_a - index_b


def autocorrelation(values: Sequence[float], lag: int = 1) -> float | None:
    """Serial correlation of a residual series.

    ``DATA.md`` §19.2 asks for this because residuals that are correlated with
    their own past are residuals the model could still have explained.
    """
    if len(values) < MINIMUM_SAMPLE + lag:
        return None
    return pearson(values[:-lag], values[lag:])


@dataclass(frozen=True)
class CalibrationBin:
    """One slice of a conditioning variable, and the residuals inside it."""

    lower: float
    upper: float
    count: int
    mean_residual: float
    sd_residual: float


def calibration_bins(
    residuals: Sequence[float], conditioner: Sequence[float], bins: int = 4
) -> tuple[CalibrationBin, ...]:
    """Residual bias sliced by a conditioning variable (``DATA.md`` §19.2).

    A model with an overall mean residual of zero can still be badly wrong: too
    high when fatigued and too low when fresh, meeting in the middle. Checkpoint
    2 found exactly that shape over time, so slicing is not optional.
    """
    if len(residuals) != len(conditioner):
        raise ValueError("residuals and conditioner must be the same length")
    if len(residuals) < MINIMUM_SAMPLE * bins:
        return ()

    ordered = sorted(zip(conditioner, residuals))
    size = len(ordered) // bins
    out: list[CalibrationBin] = []
    for index in range(bins):
        start = index * size
        stop = len(ordered) if index == bins - 1 else (index + 1) * size
        chunk = ordered[start:stop]
        values = [r for _, r in chunk]
        out.append(
            CalibrationBin(
                lower=chunk[0][0], upper=chunk[-1][0], count=len(chunk),
                mean_residual=st.mean(values),
                sd_residual=st.pstdev(values) if len(values) > 1 else 0.0,
            )
        )
    return tuple(out)


def drift_by_block(
    residuals: Sequence[float], days: Sequence[int], block_days: int = 100
) -> tuple[tuple[int, int, float], ...]:
    """Mean residual per block of calendar time (``DATA.md`` §19.2, time drift).

    Returns ``(block_start, count, mean)``. This is the metric that exposed the
    warm-up transient at Checkpoint 2, where the pooled mean read as unbiased
    and was two opposite biases meeting in the middle.
    """
    if len(residuals) != len(days):
        raise ValueError("residuals and days must be the same length")
    grouped: dict[int, list[float]] = {}
    for residual, day in zip(residuals, days):
        grouped.setdefault((day // block_days) * block_days, []).append(residual)
    return tuple(
        (start, len(values), st.mean(values))
        for start, values in sorted(grouped.items())
        if len(values) >= MINIMUM_SAMPLE
    )
