"""Continuous-time state evolution (``MODEL.tex`` §Temporal conventions).

Every state in Rhome evolves in continuous hours from event timestamps. No
state is reset, rebased or recomputed at a calendar boundary. Two inputs
nonetheless arrive as daily aggregates — the recovery context and the step
count — and this module is where they are reconciled with continuous time.

Two conventions do the work.

The recovery multiplier is anchored to the **sleep episode**, not the calendar
day: the value from the night ending at ``sleep_end`` applies until the next
``sleep_end``. This removes the midnight discontinuity, and prevents a night's
autonomic data retroactively altering the decay of the previous evening's
training, which would be a mild form of look-ahead.

Daily step load is spread across a **waking window** rather than deposited at
one instant, using the closed-form solution for constant input into an
exponentially decaying state.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from rhome_core.parameters import CORE_PARAMETERS

__all__ = [
    "LN2",
    "WAKING_WINDOW_H",
    "decay_factor",
    "decay",
    "decay_with_constant_input",
    "hours_between",
    "RecoveryWindow",
    "RecoveryTimeline",
]

LN2 = math.log(2.0)

#: Hours over which a day's activity load is distributed, from waking.
WAKING_WINDOW_H = CORE_PARAMETERS.value("waking_window_h")


def hours_between(start: datetime, end: datetime) -> float:
    """Elapsed hours, which may be fractional or negative."""
    return (end - start).total_seconds() / 3600.0


def decay_factor(half_life_h: float, integrated_rho_h: float) -> float:
    """The surviving fraction after an accumulated recovery exposure.

    ``integrated_rho_h`` is the integral of the recovery multiplier over the
    interval, in multiplier-hours. Under a constant multiplier this is simply
    ``rho * dt``; across several recovery windows the exponent accumulates,
    as ``MODEL.tex`` specifies.
    """
    if half_life_h <= 0:
        raise ValueError(f"half-life must be positive, got {half_life_h}")
    if integrated_rho_h < 0:
        raise ValueError("integrated recovery exposure cannot be negative")
    return math.exp(-LN2 / half_life_h * integrated_rho_h)


def decay(value: float, half_life_h: float, integrated_rho_h: float) -> float:
    """Evolve a state forward with no new input."""
    return value * decay_factor(half_life_h, integrated_rho_h)


def decay_with_constant_input(
    value: float,
    rate_per_h: float,
    half_life_h: float,
    duration_h: float,
    rho: float = 1.0,
) -> float:
    """Evolve a state receiving constant input, in closed form.

    For decay coefficient ``g = rho * ln2 / half_life`` and constant input
    ``c``::

        X(t + dt) = X e^{-g dt} + (c / g)(1 - e^{-g dt})

    No numerical integration is required, which matters because this runs over
    two years of data and any integration error would accumulate.
    """
    if duration_h < 0:
        raise ValueError("duration cannot be negative")
    if duration_h == 0:
        return value
    if rho < 0:
        raise ValueError("recovery multiplier cannot be negative")

    gamma = rho * LN2 / half_life_h
    if gamma == 0:
        # No decay: input simply accumulates. Reached only if rho is zero,
        # which the model's clip forbids, but the maths must not divide by it.
        return value + rate_per_h * duration_h

    survived = math.exp(-gamma * duration_h)
    return value * survived + (rate_per_h / gamma) * (1.0 - survived)


@dataclass(frozen=True)
class RecoveryWindow:
    """One sleep-anchored interval over which the recovery multiplier holds."""

    start_h: float
    rho: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.rho) or self.rho < 0:
            raise ValueError(f"recovery multiplier must be finite and non-negative, got {self.rho}")


class RecoveryTimeline:
    """A piecewise-constant recovery multiplier over continuous time.

    Each window runs from its own start until the next window begins; the last
    extends indefinitely. Before the first window the multiplier is neutral,
    since no wearable evidence exists yet.

    The multiplier is piecewise constant, so the *rate* of decay steps at each
    waking. State trajectories remain continuous, which is the property that
    matters: the evidence genuinely does arrive once per night.
    """

    def __init__(
        self, windows: list[RecoveryWindow] | None = None, default_rho: float = 1.0
    ) -> None:
        if default_rho < 0:
            raise ValueError("default recovery multiplier cannot be negative")
        self._default_rho = float(default_rho)
        ordered = sorted(windows or [], key=lambda w: w.start_h)
        starts = [w.start_h for w in ordered]
        if len(set(starts)) != len(starts):
            raise ValueError("recovery windows must have distinct start times")
        self._windows = tuple(ordered)
        self._starts = tuple(starts)

    @property
    def windows(self) -> tuple[RecoveryWindow, ...]:
        return self._windows

    def append(self, window: RecoveryWindow) -> None:
        """Add a window after the last one.

        The engine learns each night's recovery context as the night arrives,
        so the timeline grows forward rather than being known in advance.
        Appending out of order is refused: a window inserted behind the present
        would retroactively change decay that has already been applied.
        """
        if self._starts and window.start_h <= self._starts[-1]:
            raise ValueError(
                f"window at {window.start_h:.2f} does not follow the last at "
                f"{self._starts[-1]:.2f}; recovery context cannot be inserted "
                f"behind state that has already evolved"
            )
        self._windows = self._windows + (window,)
        self._starts = self._starts + (window.start_h,)

    def rho_at(self, t_h: float) -> float:
        """The multiplier in force at an instant."""
        index = bisect_right(self._starts, t_h) - 1
        if index < 0:
            return self._default_rho
        return self._windows[index].rho

    def integrated_rho(self, t0_h: float, t1_h: float) -> float:
        """Integrate the multiplier over ``[t0, t1]``, in multiplier-hours.

        This is the quantity the decay exponent needs. Summing overlaps window
        by window is what keeps a state continuous when it spans several nights.
        """
        if t1_h < t0_h:
            raise ValueError("interval end precedes its start")
        if t1_h == t0_h:
            return 0.0

        total = 0.0
        cursor = t0_h

        # The portion before any window carries the neutral default.
        if self._windows and cursor < self._starts[0]:
            boundary = min(t1_h, self._starts[0])
            total += self._default_rho * (boundary - cursor)
            cursor = boundary
        elif not self._windows:
            return self._default_rho * (t1_h - t0_h)

        index = max(0, bisect_right(self._starts, cursor) - 1)
        while cursor < t1_h and index < len(self._windows):
            window_end = (
                self._starts[index + 1] if index + 1 < len(self._windows) else math.inf
            )
            boundary = min(t1_h, window_end)
            total += self._windows[index].rho * (boundary - cursor)
            cursor = boundary
            index += 1
        return total

    def decay_between(self, value: float, half_life_h: float, t0_h: float, t1_h: float) -> float:
        """Evolve a state from one instant to another with no new input."""
        return decay(value, half_life_h, self.integrated_rho(t0_h, t1_h))

    @classmethod
    def from_sleep_ends(
        cls, sleep_ends: list[datetime], rhos: list[float], origin: datetime
    ) -> "RecoveryTimeline":
        """Build a timeline from nightly wake times and their multipliers."""
        if len(sleep_ends) != len(rhos):
            raise ValueError(
                f"got {len(sleep_ends)} sleep-end times but {len(rhos)} multipliers"
            )
        return cls(
            [
                RecoveryWindow(hours_between(origin, end), rho)
                for end, rho in zip(sleep_ends, rhos)
            ]
        )
