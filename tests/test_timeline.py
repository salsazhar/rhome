"""Continuous-time evolution (``MODEL.tex`` §Temporal conventions).

The specification requires that no state show an implausible discontinuity at a
calendar boundary, while two inputs arrive as daily aggregates. These tests
check that reconciliation directly.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from rhome_core.timeline import (
    LN2,
    WAKING_WINDOW_H,
    RecoveryTimeline,
    RecoveryWindow,
    decay,
    decay_factor,
    decay_with_constant_input,
    hours_between,
)


# --- decay fundamentals ----------------------------------------------------

def test_one_half_life_halves_the_state():
    assert decay(1.0, 30.0, 30.0) == pytest.approx(0.5)
    assert decay(1.0, 30.0, 60.0) == pytest.approx(0.25)


def test_no_elapsed_time_leaves_the_state_unchanged():
    assert decay(0.7, 30.0, 0.0) == pytest.approx(0.7)


def test_decay_is_monotone_and_never_negative():
    previous = 1.0
    for hours in range(0, 200, 5):
        current = decay(1.0, 30.0, float(hours))
        assert 0.0 <= current <= previous
        previous = current


def test_a_favourable_recovery_context_decays_fatigue_faster():
    fast = decay(1.0, 30.0, 1.15 * 24)   # rho at its documented ceiling
    slow = decay(1.0, 30.0, 0.80 * 24)   # rho at its documented floor
    assert fast < slow


@pytest.mark.parametrize("bad_half_life", [0.0, -1.0])
def test_non_positive_half_life_is_rejected(bad_half_life):
    with pytest.raises(ValueError):
        decay_factor(bad_half_life, 1.0)


# --- constant input: closed form vs numerical integration ------------------

@pytest.mark.spec("MODEL:constant-input-closed-form")
@pytest.mark.parametrize("rho", [0.80, 1.00, 1.15])
@pytest.mark.parametrize("half_life", [24.0, 30.0, 42.0])
def test_closed_form_agrees_with_numerical_integration(rho, half_life):
    """The closed form must match slow explicit integration.

    Rhome runs this over two years, where integration error would accumulate,
    so the analytic solution is used. That makes it worth proving correct.
    """
    start, rate, duration = 0.35, 0.02 / WAKING_WINDOW_H, WAKING_WINDOW_H

    steps = 200_000
    dt = duration / steps
    gamma = rho * LN2 / half_life
    numerical = start
    for _ in range(steps):
        numerical += (rate - gamma * numerical) * dt

    analytic = decay_with_constant_input(start, rate, half_life, duration, rho)
    assert analytic == pytest.approx(numerical, rel=1e-5)


def test_constant_input_with_no_input_reduces_to_plain_decay():
    assert decay_with_constant_input(1.0, 0.0, 30.0, 24.0, 1.0) == pytest.approx(
        decay(1.0, 30.0, 24.0)
    )


def test_constant_input_approaches_its_steady_state():
    """Sustained input settles at rate/gamma rather than growing without bound."""
    rate, half_life, rho = 0.05, 30.0, 1.0
    gamma = rho * LN2 / half_life
    settled = decay_with_constant_input(0.0, rate, half_life, 5000.0, rho)
    assert settled == pytest.approx(rate / gamma, rel=1e-6)


def test_zero_decay_coefficient_does_not_divide_by_zero():
    """rho = 0 is forbidden by the model's clip, but must not crash the maths."""
    assert decay_with_constant_input(1.0, 0.5, 30.0, 10.0, rho=0.0) == pytest.approx(6.0)


def test_negative_duration_is_rejected():
    with pytest.raises(ValueError):
        decay_with_constant_input(1.0, 0.1, 30.0, -1.0)


# --- sleep-anchored recovery windows ---------------------------------------

@pytest.mark.spec("MODEL:sleep-anchored-recovery-window")
def test_multiplier_holds_from_waking_until_the_next_waking():
    timeline = RecoveryTimeline(
        [RecoveryWindow(0.0, 1.00), RecoveryWindow(24.0, 0.85), RecoveryWindow(48.0, 1.10)]
    )
    assert timeline.rho_at(0.0) == 1.00
    assert timeline.rho_at(23.9) == 1.00
    assert timeline.rho_at(24.0) == 0.85
    assert timeline.rho_at(47.9) == 0.85
    assert timeline.rho_at(1000.0) == 1.10, "the last window extends indefinitely"


@pytest.mark.spec("MODEL:sleep-anchored-recovery-window")
def test_multiplier_is_neutral_before_any_wearable_data():
    timeline = RecoveryTimeline([RecoveryWindow(100.0, 0.85)])
    assert timeline.rho_at(0.0) == 1.0
    assert timeline.integrated_rho(0.0, 100.0) == pytest.approx(100.0)


def test_integration_sums_overlaps_window_by_window():
    timeline = RecoveryTimeline(
        [RecoveryWindow(0.0, 1.00), RecoveryWindow(24.0, 0.85), RecoveryWindow(48.0, 1.10)]
    )
    assert timeline.integrated_rho(0.0, 72.0) == pytest.approx(24 * 1.00 + 24 * 0.85 + 24 * 1.10)
    assert timeline.integrated_rho(12.0, 36.0) == pytest.approx(12 * 1.00 + 12 * 0.85)


def test_integration_is_additive_across_a_split_point():
    timeline = RecoveryTimeline(
        [RecoveryWindow(0.0, 1.00), RecoveryWindow(24.0, 0.85), RecoveryWindow(48.0, 1.10)]
    )
    whole = timeline.integrated_rho(5.0, 70.0)
    parts = timeline.integrated_rho(5.0, 30.0) + timeline.integrated_rho(30.0, 70.0)
    assert whole == pytest.approx(parts)


def test_empty_interval_integrates_to_zero_and_reversed_is_rejected():
    timeline = RecoveryTimeline([RecoveryWindow(0.0, 0.9)])
    assert timeline.integrated_rho(10.0, 10.0) == 0.0
    with pytest.raises(ValueError):
        timeline.integrated_rho(10.0, 5.0)


def test_duplicate_window_starts_are_rejected():
    with pytest.raises(ValueError, match="distinct start times"):
        RecoveryTimeline([RecoveryWindow(0.0, 1.0), RecoveryWindow(0.0, 0.9)])


def test_windows_may_be_supplied_unsorted():
    timeline = RecoveryTimeline([RecoveryWindow(48.0, 1.1), RecoveryWindow(0.0, 1.0),
                                 RecoveryWindow(24.0, 0.85)])
    assert [w.rho for w in timeline.windows] == [1.0, 0.85, 1.1]


def test_negative_multiplier_is_rejected():
    with pytest.raises(ValueError):
        RecoveryWindow(0.0, -0.1)


def test_timeline_can_be_built_from_wake_times():
    origin = datetime(2026, 1, 1, 0, 0)
    wakes = [origin + timedelta(days=d, hours=7, minutes=30) for d in range(3)]
    timeline = RecoveryTimeline.from_sleep_ends(wakes, [1.0, 0.85, 1.1], origin)
    assert timeline.rho_at(hours_between(origin, wakes[1]) + 1) == 0.85


def test_mismatched_wake_times_and_multipliers_are_rejected():
    origin = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="but 1 multipliers"):
        RecoveryTimeline.from_sleep_ends([origin, origin + timedelta(days=1)], [1.0], origin)


# --- the continuity requirement --------------------------------------------

@pytest.mark.spec("MODEL:no-calendar-discontinuity")
def test_state_is_continuous_across_midnight():
    """``MODEL.tex`` requires this to be tested directly.

    Evaluate across midnight on a day with no training and no change in
    wearable availability, and require smoothness. Windows are anchored to
    waking, so midnight is an ordinary instant carrying no special meaning.
    """
    origin = datetime(2026, 1, 1, 0, 0)
    wakes = [origin + timedelta(days=d, hours=7, minutes=30) for d in range(4)]
    timeline = RecoveryTimeline.from_sleep_ends(wakes, [1.02, 0.94, 1.06, 0.98], origin)

    midnight = hours_between(origin, datetime(2026, 1, 3, 0, 0))
    grid = [midnight + step / 60.0 for step in range(-90, 91)]  # 90 min either side
    values = [timeline.decay_between(1.0, 30.0, 0.0, t) for t in grid]

    steps = [b - a for a, b in zip(values, values[1:])]
    assert all(s < 0 for s in steps), "state must fall monotonically without input"

    # No step may stand out against its neighbours: a discontinuity would show
    # as a single outsized jump.
    largest, typical = max(map(abs, steps)), sorted(map(abs, steps))[len(steps) // 2]
    assert largest < 1.05 * typical, "discontinuity detected at the day boundary"


@pytest.mark.spec("MODEL:no-calendar-discontinuity")
def test_a_change_of_recovery_window_steps_the_rate_not_the_state():
    """Evidence arrives nightly, so the decay *rate* may step. The state may not."""
    timeline = RecoveryTimeline([RecoveryWindow(0.0, 1.10), RecoveryWindow(24.0, 0.80)])
    just_before = timeline.decay_between(1.0, 30.0, 0.0, 24.0 - 1e-7)
    just_after = timeline.decay_between(1.0, 30.0, 0.0, 24.0 + 1e-7)
    assert just_after == pytest.approx(just_before, abs=1e-8)
    assert timeline.rho_at(23.0) != timeline.rho_at(25.0)


def test_waking_window_matches_the_registered_parameter():
    from rhome_core.parameters import CORE_PARAMETERS

    assert WAKING_WINDOW_H == CORE_PARAMETERS.value("waking_window_h")
