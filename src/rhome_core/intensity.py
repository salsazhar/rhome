"""Relative intensity from repetitions and effort (``MODEL.tex`` §Estimating
relative intensity).

A logged set carries an implicit statement about how heavy it was. Five
repetitions with one left in reserve implies roughly a six-repetition maximum
load, and the population relationship between repetitions-to-failure and
percentage of one-repetition maximum turns that into a number.

Rhome inverts the meta-regression of Nuzzo et al. (2024) rather than using a
single Epley-style formula, because that analysis --- 952 repetitions-to-failure
tests across 7,289 individuals --- quantified both the mean relationship and the
substantial variation around it. A universal conversion equation would assert a
precision the evidence does not support.

This module provides the **population** curve only. The simulator deliberately
uses a different functional form with per-athlete deviations; keeping the two
apart is what stops the engine inverting its own generator.
"""

from __future__ import annotations

from bisect import bisect_left
from enum import StrEnum
from types import MappingProxyType
from rhome_core.parameters import CORE_PARAMETERS

__all__ = [
    "IntensityConfidence",
    "NUZZO_GENERAL",
    "EXERCISE_ENDURANCE_FACTOR",
    "DOMAIN_MIN_REPS",
    "DOMAIN_MAX_REPS",
    "DOMAIN_MIN_INTENSITY",
    "rir_from_rpe",
    "relative_intensity",
    "reps_to_failure",
]


class IntensityConfidence(StrEnum):
    """How far a set sits from the region the evidence covers."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Mean repetitions to failure at each percentage of one-repetition maximum,
#: from the general model of Nuzzo et al. (2024). Grade A.
NUZZO_GENERAL: tuple[tuple[float, float], ...] = (
    (0.95, 3.28), (0.90, 4.94), (0.85, 7.15), (0.80, 9.75), (0.75, 12.37),
    (0.70, 14.80), (0.65, 17.11), (0.60, 19.53), (0.55, 22.43), (0.50, 25.99),
)

DOMAIN_MIN_REPS = CORE_PARAMETERS.value("nuzzo_domain_min_reps")
DOMAIN_MAX_REPS = CORE_PARAMETERS.value("nuzzo_domain_max_reps")
DOMAIN_MIN_INTENSITY = CORE_PARAMETERS.value("nuzzo_high_rep_clip")
#: One maximal repetition is 100% of a one-repetition maximum by definition.
DEFINITIONAL_ANCHOR_REPS = 1.0
DEFINITIONAL_ANCHOR_INTENSITY = CORE_PARAMETERS.value("nuzzo_near_maximal_anchor")

#: Exercise-specific adjustment, as a multiplier on repetitions achievable at a
#: given relative intensity.
#:
#: Nuzzo et al. report exercise as a material moderator: leg press permits more
#: repetitions than bench press across the loading spectrum. **The paper's
#: exercise-specific tables are not reproduced in this project's documents**, so
#: these factors express the reported direction rather than the reported curves,
#: and are Grade C rather than Grade A. Replacing them with the published tables
#: is a documented improvement, not a change of approach.
EXERCISE_ENDURANCE_FACTOR: MappingProxyType[str, float] = MappingProxyType(
    {"general": 1.00, "bench": 0.88, "leg_press": 1.18}
)

_INTENSITIES = tuple(u for u, _ in NUZZO_GENERAL)
_REPS = tuple(n for _, n in NUZZO_GENERAL)


def rir_from_rpe(rpe: float) -> float:
    """Repetitions in reserve implied by a rating of perceived exertion.

    The resistance-training RPE scale ties 10 to zero repetitions in reserve
    and 9 to approximately one (Zourdos et al., 2016). The mapping is a
    convention, not a measurement, and the value it produces is treated as a
    noisy observation throughout.
    """
    if not 0.0 <= rpe <= 10.0:
        raise ValueError(f"RPE must lie in [0, 10], got {rpe}")
    return max(0.0, 10.0 - rpe)


def _interpolate_general(reps: float) -> float:
    """Piecewise-linear inversion of the tabulated relationship."""
    index = bisect_left(_REPS, reps)
    if index == 0:
        return _INTENSITIES[0]
    if index >= len(_REPS):
        return _INTENSITIES[-1]
    n_low, n_high = _REPS[index - 1], _REPS[index]
    u_low, u_high = _INTENSITIES[index - 1], _INTENSITIES[index]
    span = (reps - n_low) / (n_high - n_low)
    return u_low + span * (u_high - u_low)


def relative_intensity(
    reps: int | float,
    rir: float,
    curve: str = "general",
) -> tuple[float, IntensityConfidence]:
    """Estimate relative intensity, with a confidence label.

    Returns the fraction of one-repetition maximum the set implies, and how far
    it sits from the region the evidence covers. Confidence is not decoration:
    a set outside the tabulated domain still contributes to the fatigue,
    strain and systemic channels, and is excluded only from performance
    estimation, because the inversion assumes a set taken from a
    non-pre-fatigued state.
    """
    if reps < 1:
        raise ValueError(f"a set must have at least one repetition, got {reps}")
    if rir < 0:
        raise ValueError(f"repetitions in reserve cannot be negative, got {rir}")
    if curve not in EXERCISE_ENDURANCE_FACTOR:
        raise ValueError(f"unknown curve {curve!r}")

    factor = EXERCISE_ENDURANCE_FACTOR[curve]
    implied = reps + rir
    # Express the athlete's repetitions on the general curve's scale before
    # inverting, so an exercise permitting more repetitions maps to a lower
    # relative intensity for the same set.
    equivalent = implied / factor

    if equivalent < DOMAIN_MIN_REPS:
        # Extended linearly to the definitional anchor rather than clipped.
        # Clipping would make a true single indistinguishable from a heavy
        # triple and would stop the model ever observing 100% of maximum,
        # which matters because low-fatigue singles are the most informative
        # capacity anchors available.
        span = DOMAIN_MIN_REPS - DEFINITIONAL_ANCHOR_REPS
        fraction = (max(DEFINITIONAL_ANCHOR_REPS, equivalent) - DEFINITIONAL_ANCHOR_REPS) / span
        intensity = DEFINITIONAL_ANCHOR_INTENSITY - 0.05 * fraction
        return min(1.0, intensity), IntensityConfidence.MEDIUM

    if equivalent > DOMAIN_MAX_REPS:
        # Below roughly half of maximum the relationship flattens and
        # between-person variation becomes large. Clip; do not extrapolate.
        return DOMAIN_MIN_INTENSITY, IntensityConfidence.LOW

    return _interpolate_general(equivalent), IntensityConfidence.HIGH


def reps_to_failure(intensity: float, curve: str = "general") -> float:
    """Repetitions the population curve expects at a relative intensity."""
    if not 0.0 < intensity <= 1.0:
        raise ValueError(f"relative intensity must lie in (0, 1], got {intensity}")
    factor = EXERCISE_ENDURANCE_FACTOR[curve]
    if intensity >= _INTENSITIES[0]:
        span = DOMAIN_MIN_REPS - DEFINITIONAL_ANCHOR_REPS
        fraction = (DEFINITIONAL_ANCHOR_INTENSITY - intensity) / 0.05
        return (DEFINITIONAL_ANCHOR_REPS + fraction * span) * factor
    if intensity <= _INTENSITIES[-1]:
        return DOMAIN_MAX_REPS * factor
    for index in range(1, len(_INTENSITIES)):
        if intensity >= _INTENSITIES[index]:
            u_high, u_low = _INTENSITIES[index - 1], _INTENSITIES[index]
            n_high, n_low = _REPS[index - 1], _REPS[index]
            span = (u_high - intensity) / (u_high - u_low)
            return (n_high + span * (n_low - n_high)) * factor
    return DOMAIN_MAX_REPS * factor
