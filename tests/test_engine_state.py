"""Engine state evolution (``MODEL.tex`` §Time evolution, §Temporal conventions)."""

from __future__ import annotations

import math

import pytest

from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_core.timeline import WAKING_WINDOW_H, RecoveryTimeline, RecoveryWindow
from rhome_engine.dose import LoggedSet, transform_set
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.state import EngineState, StateEngine

LIBRARY = load_library()
LOCAL_HALF_LIFE = ENGINE_PARAMETERS.value("local_half_life_h")


def _session(engine, at_h=17.0, sets=4, exercise="back_squat", rir=1.0, reps=5,
             spacing_h=0.1):
    """Apply a session's sets, spaced through the session by default.

    ``spacing_h=0`` places every set at the same instant, which is what a test
    comparing raw impulse sums needs: with spacing, the state decays between
    sets and totals are no longer simple multiples.
    """
    for index in range(sets):
        dose = transform_set(
            LoggedSet("w", exercise, index + 1, "working", 140.0, reps, rir=rir),
            LIBRARY[exercise],
        )
        engine.apply_dose(dose, at_h + index * spacing_h, exercise)


# --- decay fundamentals ----------------------------------------------------

@pytest.mark.spec("MODEL:engine-continuous-evolution")
def test_fatigue_halves_over_one_half_life():
    engine = StateEngine()
    _session(engine, sets=1)
    peak = engine.state.local_fatigue[Muscle.QUADS]
    engine.advance_to(17.0 + LOCAL_HALF_LIFE)
    assert engine.state.local_fatigue[Muscle.QUADS] == pytest.approx(peak * 0.5, rel=1e-6)


@pytest.mark.spec("MODEL:engine-continuous-evolution")
def test_state_decays_monotonically_and_stays_non_negative():
    engine = StateEngine()
    _session(engine)
    previous = engine.state.total_local_fatigue()
    for hour in range(20, 400, 6):
        engine.advance_to(float(hour))
        current = engine.state.total_local_fatigue()
        assert 0.0 <= current <= previous + 1e-12
        previous = current


def test_time_cannot_run_backwards():
    engine = StateEngine()
    engine.advance_to(50.0)
    with pytest.raises(ValueError, match="backwards"):
        engine.advance_to(20.0)


def test_advancing_to_the_present_changes_nothing():
    engine = StateEngine()
    _session(engine)
    before = engine.state.total_local_fatigue()
    engine.advance_to(engine.state.t_h)
    assert engine.state.total_local_fatigue() == pytest.approx(before)


# --- the recovery multiplier scales the rate, not the state ----------------

@pytest.mark.spec("MODEL:engine-continuous-evolution")
def test_the_recovery_multiplier_scales_the_decay_rate():
    """A good night does not remove fatigue; it makes fatigue drain faster."""
    results = {}
    for rho in (0.80, 1.00, 1.15):
        engine = StateEngine(RecoveryTimeline([RecoveryWindow(0.0, rho)]))
        _session(engine, sets=1)
        peak = engine.state.local_fatigue[Muscle.QUADS]
        engine.advance_to(17.0 + 24.0)
        results[rho] = engine.state.local_fatigue[Muscle.QUADS]
        assert results[rho] < peak
    assert results[1.15] < results[1.00] < results[0.80]


def test_a_neutral_multiplier_is_the_absence_of_evidence_not_a_penalty():
    """With no wearable data the multiplier is 1 and the state simply decays."""
    engine = StateEngine(RecoveryTimeline())
    _session(engine, sets=1)
    peak = engine.state.local_fatigue[Muscle.QUADS]
    engine.advance_to(17.0 + LOCAL_HALF_LIFE)
    assert engine.state.local_fatigue[Muscle.QUADS] == pytest.approx(peak * 0.5, rel=1e-6)


def test_the_multiplier_is_integrated_across_windows_it_spans():
    engine = StateEngine(
        RecoveryTimeline([RecoveryWindow(0.0, 1.10), RecoveryWindow(24.0, 0.85)])
    )
    _session(engine, at_h=1.0, sets=1)
    peak = engine.state.local_fatigue[Muscle.QUADS]
    engine.advance_to(49.0)

    exposure = 1.10 * 23.0 + 0.85 * 25.0
    expected = peak * math.exp(-math.log(2.0) / LOCAL_HALF_LIFE * exposure)
    assert engine.state.local_fatigue[Muscle.QUADS] == pytest.approx(expected, rel=1e-9)


def test_adaptation_is_not_modulated_by_recovery_context():
    """A good night's sleep does not accelerate adaptation."""
    fast = StateEngine(RecoveryTimeline([RecoveryWindow(0.0, 1.15)]))
    slow = StateEngine(RecoveryTimeline([RecoveryWindow(0.0, 0.80)]))
    for engine in (fast, slow):
        _session(engine, sets=2)
        engine.advance_to(17.0 + 24 * 30)
    assert fast.state.adaptation[Muscle.QUADS] == pytest.approx(
        slow.state.adaptation[Muscle.QUADS], rel=1e-9
    )


# --- continuity (MODEL.tex) ------------------------------------------------

@pytest.mark.spec("MODEL:engine-no-calendar-reset")
def test_state_is_continuous_across_midnight():
    """Required directly by ``MODEL.tex``.

    Evaluated on a fine grid across midnight on a day with no training and no
    change in wearable availability. Recovery windows are anchored to waking,
    so midnight carries no meaning.
    """
    wakes = [day * 24.0 + 7.5 for day in range(4)]
    timeline = RecoveryTimeline(
        [RecoveryWindow(w, r) for w, r in zip(wakes, (1.02, 0.94, 1.06, 0.98))]
    )
    engine = StateEngine(timeline)
    _session(engine, at_h=17.0)

    midnight = 48.0
    values = []
    for step in range(-90, 91):
        engine.advance_to(midnight + step / 60.0)
        values.append(engine.state.total_local_fatigue())

    steps = [b - a for a, b in zip(values, values[1:])]
    assert all(s < 0 for s in steps), "state must fall monotonically without input"
    largest, typical = max(map(abs, steps)), sorted(map(abs, steps))[len(steps) // 2]
    assert largest < 1.05 * typical, "discontinuity detected at the day boundary"


@pytest.mark.spec("MODEL:engine-no-calendar-reset")
def test_a_change_of_recovery_window_steps_the_rate_not_the_state():
    engine = StateEngine(
        RecoveryTimeline([RecoveryWindow(0.0, 1.10), RecoveryWindow(24.0, 0.80)])
    )
    _session(engine, at_h=1.0, sets=1)
    engine.advance_to(24.0 - 1e-6)
    before = engine.state.total_local_fatigue()
    engine.advance_to(24.0 + 1e-6)
    # Tolerance sits above the 2 microsecond step used to straddle the
    # boundary; the point is that the state does not jump, not that it freezes.
    assert engine.state.total_local_fatigue() == pytest.approx(before, abs=1e-7)


# --- background activity ---------------------------------------------------

def test_habitual_activity_contributes_nothing():
    engine = StateEngine()
    amplitude = engine.set_activity_window(10_000, 10_000, 7.5)
    assert amplitude == 0.0
    engine.advance_to(7.5 + WAKING_WINDOW_H)
    assert engine.state.systemic == 0.0


def test_activity_above_baseline_adds_systemic_and_lower_limb_load():
    engine = StateEngine()
    engine.set_activity_window(25_000, 10_000, 7.5)
    engine.advance_to(7.5 + WAKING_WINDOW_H)
    assert engine.state.systemic > 0
    assert engine.state.local_fatigue[Muscle.CALVES] > 0
    assert engine.state.local_fatigue[Muscle.QUADS] > 0
    assert engine.state.local_fatigue[Muscle.CHEST] == 0.0, "steps are not upper-body load"
    assert engine.state.local_fatigue[Muscle.CALVES] > engine.state.local_fatigue[Muscle.HAMSTRINGS]


def test_steps_are_not_resistance_volume():
    """A very high step day must cost meaningfully less than a session.

    Compared at the same instant, so the two are not being measured after
    different amounts of decay. Twenty-five thousand steps against a ten
    thousand baseline is an extreme day, and it still costs well under half a
    four-set squat session.
    """
    end = 7.5 + WAKING_WINDOW_H

    walking = StateEngine()
    walking.set_activity_window(25_000, 10_000, 7.5)
    walking.advance_to(end)

    training = StateEngine()
    _session(training, at_h=17.0)
    training.advance_to(end)

    assert walking.state.systemic < training.state.systemic * 0.5
    assert walking.state.local_fatigue[Muscle.QUADS] < (
        training.state.local_fatigue[Muscle.QUADS] * 0.1
    ), "walking must be nothing like a squat session for the quadriceps"


@pytest.mark.spec("MODEL:engine-no-calendar-reset")
def test_training_may_happen_inside_the_activity_window():
    """A session at five in the afternoon sits in the middle of a day's walking.

    An earlier design applied the whole day's activity across the waking window
    before the session, which made this ordering impossible without running
    time backwards.
    """
    engine = StateEngine()
    engine.set_activity_window(22_000, 10_000, 7.5)
    _session(engine, at_h=17.0)
    engine.advance_to(7.5 + WAKING_WINDOW_H)
    assert engine.state.local_fatigue[Muscle.QUADS] > 0
    assert engine.state.systemic > 0


def test_activity_is_spread_rather_than_deposited_at_one_instant():
    engine = StateEngine()
    engine.set_activity_window(30_000, 10_000, 7.5)
    engine.advance_to(7.5 + 1.0)
    after_one_hour = engine.state.systemic
    engine.advance_to(7.5 + WAKING_WINDOW_H)
    after_full_day = engine.state.systemic
    assert 0 < after_one_hour < after_full_day * 0.25


# --- load traces (MODEL.tex) -----------------------------------------------

@pytest.mark.spec("MODEL:load-traces-separate")
def test_the_two_load_traces_decay_independently():
    engine = StateEngine()
    _session(engine, spacing_h=0.0)
    short_peak = engine.state.short_load_trace
    long_peak = engine.state.long_load_trace
    assert short_peak == pytest.approx(long_peak), (
        "the traces receive identical input and differ only in how they decay"
    )

    engine.advance_to(17.0 + 24 * 14)
    assert engine.state.short_load_trace < engine.state.long_load_trace
    assert engine.state.long_load_trace > long_peak * 0.5


def test_no_ratio_is_computed_between_the_traces():
    """``MODEL.tex`` is explicit that no threshold attaches to their ratio."""
    state = EngineState()
    assert not hasattr(state, "acwr")
    assert not any("ratio" in name for name in vars(state))


# --- novelty ---------------------------------------------------------------

def test_novelty_starts_at_the_cap_and_decays_with_exposure():
    engine = StateEngine()
    cap = ENGINE_PARAMETERS.value("novelty_cap")
    assert engine.novelty_for("new_lift") == pytest.approx(cap)

    for _ in range(20):
        _session(engine, sets=1, exercise="back_squat")
    assert engine.exposure_count("back_squat") == 20
    assert engine.novelty_for("back_squat") == pytest.approx(1.0, abs=0.02)


def test_novelty_never_exceeds_its_cap():
    engine = StateEngine()
    for exposures in range(0, 30):
        assert 1.0 <= engine.novelty_for(f"lift_{exposures}") <= ENGINE_PARAMETERS.value("novelty_cap")


# --- accumulation ----------------------------------------------------------

def test_repeated_sessions_accumulate_fatigue():
    engine = StateEngine()
    _session(engine, at_h=17.0)
    after_one = engine.state.local_fatigue[Muscle.QUADS]
    _session(engine, at_h=17.0 + 48.0)
    assert engine.state.local_fatigue[Muscle.QUADS] > after_one


def test_the_engine_accumulates_linearly_in_set_count():
    """Unlike the simulator, which is state-dependent. This is the
    misspecification the inverse-crime audit records."""
    one = StateEngine(); _session(one, sets=1, spacing_h=0.0)
    ten = StateEngine(); _session(ten, sets=10, spacing_h=0.0)
    assert ten.state.local_fatigue[Muscle.QUADS] == pytest.approx(
        one.state.local_fatigue[Muscle.QUADS] * 10, rel=1e-9
    )


def test_state_can_be_copied_without_aliasing():
    engine = StateEngine()
    _session(engine)
    snapshot = engine.state.copy()
    _session(engine, at_h=100.0)
    assert snapshot.local_fatigue[Muscle.QUADS] != engine.state.local_fatigue[Muscle.QUADS]
