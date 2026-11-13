"""Performance and capacity (``MODEL.tex`` §Performance model).

The stage where target leakage would enter if it entered anywhere. Leakage is
invisible in results: it does not break anything, it simply makes every metric
better than it should be. So the ordering that prevents it is tested by trying
to violate it.
"""

from __future__ import annotations

import math
import statistics as st

import pytest

from rhome_core.exercises import load_library
from rhome_core.intensity import IntensityConfidence
from rhome_engine.dose import LoggedSet, transform_set
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.performance import (
    BodyMassTracker,
    CapacityModel,
    FrozenProjection,
    LeakageError,
    effective_load,
    expected_suppression,
    capacity_identity,
    observed_performance,
)
from rhome_engine.state import StateEngine

LIBRARY = load_library()
BENCH = LIBRARY["bench_press"]
PULLUP = LIBRARY["weighted_pullup"]
PULLDOWN = LIBRARY["lat_pulldown"]


#: Observations after which the gain schedule has returned to the base rate
#: and an estimate is genuinely settled (``MODEL.tex`` §Gain schedule).
SETTLED_OBSERVATIONS = 20


def _established(exercise=BENCH, load=100.0, reps=5, rir=2.0, observations=None):
    """A capacity model past its warm-up, and a fresh state engine.

    This built *three* observations until L3.3 — the bare minimum to
    initialise, and not remotely "past its warm-up". The docstring had been
    wrong since L2.4; the gain schedule only made it visible, by behaving
    differently at n=3 than at n=20 as it is designed to.
    """
    model = CapacityModel()
    state = StateEngine()
    for index in range(observations or SETTLED_OBSERVATIONS):
        logged = LoggedSet("w", exercise.exercise_id, 1, "working", load, reps, rir=rir)
        dose = transform_set(logged, exercise)
        model.freeze(exercise, state.state, f"warmup{index}")
        model.update_capacity(
            exercise, f"warmup{index}",
            observed_performance(logged, dose, exercise, None), state.state,
        )
    return model, state


def _fatigued(exercise=BENCH, sets=4):
    state = StateEngine()
    for index in range(sets):
        dose = transform_set(
            LoggedSet("w", exercise.exercise_id, index + 1, "working", 100.0, 5, rir=0.0),
            exercise,
        )
        state.apply_dose(dose, 17.0 + index * 0.1, exercise.exercise_id)
    state.advance_to(41.0)
    return state


# --- Guardrail 2: the ordering that prevents leakage -----------------------

@pytest.mark.guardrail(2)
@pytest.mark.spec("MODEL:frozen-projection-ordering")
def test_a_residual_cannot_be_scored_without_a_frozen_projection():
    """Scoring against a projection made after the fact measures nothing."""
    model, state = _established()
    with pytest.raises(LeakageError, match="no frozen projection"):
        model.score_and_update(BENCH, "unfrozen_session", 120.0, state.state)


@pytest.mark.guardrail(2)
@pytest.mark.spec("MODEL:frozen-projection-ordering")
def test_a_projection_cannot_be_refrozen_for_the_same_session():
    """A second freeze is a recomputation, which is the leak itself."""
    model, state = _established()
    model.freeze(BENCH, state.state, "session_1")
    with pytest.raises(LeakageError, match="already frozen"):
        model.freeze(BENCH, state.state, "session_1")


@pytest.mark.guardrail(2)
@pytest.mark.spec("MODEL:frozen-projection-ordering")
def test_the_frozen_projection_is_unchanged_by_ingesting_its_own_session():
    """The property Guardrail 2 exists to guarantee."""
    model, state = _established()
    record = model.freeze(BENCH, state.state, "session_1")
    sealed = record.projected
    digest = record.digest

    model.score_and_update(BENCH, "session_1", 150.0, state.state)

    after = model.frozen("bench_press", "session_1")
    assert after.projected == sealed, "the prediction moved after seeing the outcome"
    assert after.digest == digest
    assert after.verify()


@pytest.mark.guardrail(2)
def test_a_tampered_projection_is_detected():
    """Content-addressing, demonstrated rejecting an alteration."""
    model, state = _established()
    record = model.freeze(BENCH, state.state, "session_1")
    assert record.verify()

    forged = FrozenProjection(
        **{**record.__dict__, "projected": record.projected * 1.2}
    )
    assert not forged.verify(), "an altered projection kept its digest"

    model._frozen[("bench_press", "session_1")] = forged
    with pytest.raises(LeakageError, match="altered since it was sealed"):
        model.score_and_update(BENCH, "session_1", 150.0, state.state)


@pytest.mark.guardrail(2)
def test_capacity_does_not_move_before_the_residual_is_scored():
    model, state = _established()
    before = model.capacity("bench_press")
    model.freeze(BENCH, state.state, "session_1")
    assert model.capacity("bench_press") == before, "freezing must not change capacity"

    result = model.score_and_update(BENCH, "session_1", 130.0, state.state)
    assert result.capacity_before == before
    assert model.capacity("bench_press") != before


# --- capacity behaviour (MODEL.tex) ----------------------------------------

@pytest.mark.spec("MODEL:equipment-context-capacity-identity")
def test_only_fixed_equipment_splits_capacity_by_context():
    assert capacity_identity(BENCH, "Main gym") == "bench_press"
    assert capacity_identity(BENCH, "Second gym") == "bench_press"
    assert capacity_identity(PULLDOWN, "Main gym") == "lat_pulldown::Main gym"
    assert capacity_identity(PULLDOWN, "Second gym") == "lat_pulldown::Second gym"


@pytest.mark.spec("MODEL:session-level-capacity-update")
def test_repeated_sets_produce_one_capacity_movement_not_pseudo_replication():
    single, state = _established()
    repeated, _ = _established()
    base = single.capacity("bench_press")
    evidence = (base * 1.03, state.state, IntensityConfidence.HIGH)

    single.freeze(BENCH, state.state, "s")
    once = single.update_session(BENCH, "s", [evidence])
    repeated.freeze(BENCH, state.state, "s")
    many = repeated.update_session(BENCH, "s", [evidence] * 4)

    assert many.after == pytest.approx(once.after)
    assert many.evidence_sets == 4 and once.evidence_sets == 1
    assert repeated.observations("bench_press") == single.observations("bench_press") + 3


@pytest.mark.spec("MODEL:session-level-capacity-update")
def test_initialisation_remembers_distinct_sessions_not_only_evidence_sets():
    model = CapacityModel()
    state = StateEngine()
    evidence = (100.0, state.state, IntensityConfidence.HIGH)

    for index in range(3):
        model.freeze(BENCH, state.state, f"initial{index}")
        model.update_session(BENCH, f"initial{index}", [evidence])

    model.freeze(BENCH, state.state, "next")
    update = model.update_session(BENCH, "next", [(103.0, *evidence[1:])])
    base = ENGINE_PARAMETERS.value("capacity_learning_rate")
    assert update.learning_rate == pytest.approx(model.gain_scheduled(base, 3))
    assert update.learning_rate < ENGINE_PARAMETERS.value("capacity_gain_cap")


@pytest.mark.spec("MODEL:scale-aware-capacity-clip")
def test_huber_clip_uses_a_per_exercise_robust_session_scale():
    model, state = _established(observations=3)
    prior_clip = model.huber_clip(BENCH)
    base = model.capacity("bench_press")
    for index, factor in enumerate((0.5, 2.0, 0.5, 2.0)):
        model.freeze(BENCH, state.state, f"scale{index}")
        model.update_session(
            BENCH, f"scale{index}",
            [(base * factor, state.state, IntensityConfidence.HIGH)],
        )
    assert model.huber_clip(BENCH) > prior_clip

@pytest.mark.spec("MODEL:bounded-capacity-influence")
def test_one_anomalous_session_barely_moves_capacity():
    """Scenario S11: a conspicuously bad day must not rewrite the estimate."""
    model, state = _established()
    before = model.capacity("bench_press")
    model.freeze(BENCH, state.state, "bad_day")
    model.score_and_update(BENCH, "bad_day", before * 0.6, state.state)
    change = abs(model.capacity("bench_press") / before - 1)
    assert change <= ENGINE_PARAMETERS.value("capacity_session_max_move"), (
        f"a single terrible session moved capacity {change:.1%}"
    )


@pytest.mark.spec("MODEL:bounded-capacity-influence")
def test_a_run_of_consistent_residuals_does_move_capacity():
    """Bounded influence must not mean frozen: real change has to register."""
    model, state = _established()
    before = model.capacity("bench_press")
    for index in range(30):
        model.freeze(BENCH, state.state, f"s{index}")
        model.score_and_update(BENCH, f"s{index}", before * 1.15, state.state)
    assert model.capacity("bench_press") > before * 1.05


@pytest.mark.spec("MODEL:bounded-capacity-influence")
def test_anchors_carry_more_weight_than_ordinary_sets():
    ordinary, state = _established()
    anchored, _ = _established()
    base = ordinary.capacity("bench_press")

    ordinary.freeze(BENCH, state.state, "s")
    ordinary.score_and_update(BENCH, "s", base * 1.03, state.state)
    anchored.freeze(BENCH, state.state, "s")
    anchored.score_and_update(BENCH, "s", base * 1.2, state.state, is_anchor=True)

    assert anchored.capacity("bench_press") > ordinary.capacity("bench_press")


def test_medium_confidence_sets_carry_less_weight():
    ordinary, state = _established()
    hedged, _ = _established()
    base = ordinary.capacity("bench_press")

    ordinary.freeze(BENCH, state.state, "s")
    ordinary.score_and_update(BENCH, "s", base * 1.2, state.state)
    hedged.freeze(BENCH, state.state, "s")
    hedged.score_and_update(BENCH, "s", base * 1.03, state.state,
                            confidence=IntensityConfidence.MEDIUM)

    assert hedged.capacity("bench_press") < ordinary.capacity("bench_press")


@pytest.mark.spec("MODEL:fatigue-corrected-capacity")
def test_training_while_fatigued_does_not_depress_the_capacity_estimate():
    """The correction that stops a hard week reading as detraining."""
    fresh_model, fresh_state = _established()
    tired_model, _ = _established()
    tired_state = _fatigued()

    base = fresh_model.capacity("bench_press")
    observed = base * 0.93  # the same slightly poor session in both cases

    fresh_model.freeze(BENCH, fresh_state.state, "s")
    fresh_model.score_and_update(BENCH, "s", observed, fresh_state.state)

    tired_model.freeze(BENCH, tired_state.state, "s")
    tired_model.score_and_update(BENCH, "s", observed, tired_state.state)

    assert tired_model.capacity("bench_press") > fresh_model.capacity("bench_press"), (
        "an identical result should be read more kindly when the athlete was tired"
    )


def test_capacity_is_initialised_from_the_median_of_early_observations():
    model = CapacityModel()
    state = StateEngine()
    for index, value in enumerate((100.0, 250.0, 110.0)):
        assert model.capacity("bench_press") is None
        model.score_and_update(BENCH, f"s{index}", value, state.state)
    assert model.capacity("bench_press") == pytest.approx(110.0), (
        "the median resists an early outlier where a mean would not"
    )


def test_capacity_confidence_is_held_low_until_enough_observations():
    """Counted from a genuinely new exercise, not from an established one."""
    threshold = ENGINE_PARAMETERS.value("capacity_confident_observations")
    model, state = _established(observations=threshold - 1)
    assert not model.is_confident("bench_press")

    model.freeze(BENCH, state.state, "one_more")
    model.update_capacity(BENCH, "one_more", 120.0, state.state)
    assert model.is_confident("bench_press")


# --- expected performance --------------------------------------------------

def test_fatigue_suppresses_projected_performance():
    model, fresh = _established()
    tired = _fatigued()
    fresh_suppression, _ = expected_suppression(BENCH, fresh.state)
    tired_suppression, _ = expected_suppression(BENCH, tired.state)
    assert fresh_suppression == pytest.approx(0.0, abs=1e-9)
    assert tired_suppression > fresh_suppression


def test_suppression_is_bounded_by_the_numerical_guard():
    state = StateEngine()
    for muscle in state.state.local_fatigue:
        state.state.local_fatigue[muscle] = 50.0
    state.state.neuromuscular = 50.0
    state.state.systemic = 50.0
    suppression, _ = expected_suppression(BENCH, state.state)
    assert suppression == pytest.approx(
        1 - math.exp(-ENGINE_PARAMETERS.value("suppression_clip"))
    )


def test_the_suppression_breakdown_names_its_three_channels():
    _, terms = expected_suppression(BENCH, _fatigued().state)
    assert set(terms) == {"local", "neuromuscular", "systemic"}
    assert all(value >= 0 for value in terms.values())


def test_no_projection_before_capacity_exists():
    model = CapacityModel()
    assert model.project(BENCH, StateEngine().state) is None
    assert model.freeze(BENCH, StateEngine().state, "s") is None


# --- effective load (MODEL.tex) --------------------------------------------

@pytest.mark.spec("MODEL:effective-load-bodyweight")
def test_bodyweight_exercises_include_body_mass():
    assert effective_load(PULLUP, 20.0, 80.0) == pytest.approx(100.0)
    assert effective_load(BENCH, 100.0, 80.0) == pytest.approx(100.0)


@pytest.mark.spec("MODEL:effective-load-bodyweight")
def test_a_bodyweight_exercise_without_body_mass_yields_no_observation():
    """Body mass is never imputed from population statistics."""
    logged = LoggedSet("w", "weighted_pullup", 1, "working", 20.0, 5, rir=2.0)
    dose = transform_set(logged, PULLUP)
    assert observed_performance(logged, dose, PULLUP, None) is None


@pytest.mark.spec("MODEL:effective-load-bodyweight")
def test_body_mass_is_smoothed_before_it_reaches_performance():
    """Daily readings carry roughly a kilogram of water and gut-content noise."""
    tracker = BodyMassTracker()
    for value in (80.0, 80.2, 79.8, 80.1, 79.9, 80.3):
        tracker.observe(value)
    settled = tracker.smoothed()
    assert 79.8 <= settled <= 80.3

    # A heavy meal the night before should barely move the estimate, where
    # taking the latest reading would move it by more than a kilogram.
    tracker.observe(82.5)
    assert abs(tracker.smoothed() - settled) < 0.25, (
        "a single high reading moved the smoothed estimate materially"
    )
    assert tracker.smoothed() != 82.5, "the latest reading is not the estimate"


def test_body_mass_falls_back_to_the_last_known_value():
    tracker = BodyMassTracker()
    assert tracker.smoothed() is None
    tracker.observe(82.0)
    for _ in range(20):
        tracker.observe(None)
    assert tracker.smoothed() == pytest.approx(82.0)


# --- observed performance --------------------------------------------------

def test_a_heavier_set_at_the_same_effort_implies_more_capacity():
    light = LoggedSet("w", "bench_press", 1, "working", 90.0, 5, rir=2.0)
    heavy = LoggedSet("w", "bench_press", 1, "working", 110.0, 5, rir=2.0)
    assert observed_performance(light, transform_set(light, BENCH), BENCH, None) < \
           observed_performance(heavy, transform_set(heavy, BENCH), BENCH, None)


def test_the_same_load_left_further_from_failure_implies_more_capacity():
    hard = LoggedSet("w", "bench_press", 1, "working", 100.0, 5, rir=0.0)
    easy = LoggedSet("w", "bench_press", 1, "working", 100.0, 5, rir=3.0)
    assert observed_performance(easy, transform_set(easy, BENCH), BENCH, None) > \
           observed_performance(hard, transform_set(hard, BENCH), BENCH, None)


def test_ineligible_sets_yield_no_observation():
    drop = LoggedSet("w", "bench_press", 1, "drop", 60.0, 8, rir=0.0)
    assert observed_performance(drop, transform_set(drop, BENCH), BENCH, None) is None


# --- the gain schedule (L3.3, MODEL.tex §Gain schedule) ---------------------

@pytest.mark.spec("MODEL:capacity-gain-schedule")
def test_the_gain_schedule_scales_the_rate_without_flattening_the_distinctions():
    """Scaling, not replacing. The first attempt replaced and lost these."""
    model = CapacityModel()
    base = ENGINE_PARAMETERS.value("capacity_learning_rate")
    anchor = ENGINE_PARAMETERS.value("capacity_learning_rate_anchor")

    # Session aggregation can initialise from three eligible sets in the first
    # session, so the first scheduled update sees n=1. Both rates meet the
    # explicit 0.50 cap for the first two scheduled sessions; after that the
    # anchor distinction returns.
    for observations in (1, 2):
        assert model.gain_scheduled(base, observations) == pytest.approx(
            ENGINE_PARAMETERS.value("capacity_gain_cap")
        )
        assert model.gain_scheduled(anchor, observations) == pytest.approx(
            ENGINE_PARAMETERS.value("capacity_gain_cap")
        )
    for observations in (3, 5, 8, 20, 100):
        scaled_base = model.gain_scheduled(base, observations)
        scaled_anchor = model.gain_scheduled(anchor, observations)
        assert scaled_anchor > scaled_base, (
            f"at n={observations} an anchor test must still count for more"
        )
        assert scaled_base >= base
        assert scaled_base <= ENGINE_PARAMETERS.value("capacity_gain_cap")
        assert scaled_anchor <= ENGINE_PARAMETERS.value("capacity_gain_cap")


@pytest.mark.spec("MODEL:capacity-gain-schedule")
def test_the_schedule_returns_to_the_base_rate_once_the_estimate_is_settled():
    model = CapacityModel()
    base = ENGINE_PARAMETERS.value("capacity_learning_rate")
    assert model.gain_scheduled(base, 1) > base
    assert model.gain_scheduled(base, 4) > base
    assert model.gain_scheduled(base, 5) == pytest.approx(base)
    assert model.gain_scheduled(base, 60) == pytest.approx(base)


@pytest.mark.spec("MODEL:capacity-gain-schedule")
def test_one_bad_session_has_the_same_hard_bound_at_every_maturity():
    """Responsiveness may change with maturity; S11's session cap may not."""
    def displacement(prior: int) -> float:
        model, state = _established(observations=prior)
        before = model.capacity("bench_press")
        model.freeze(BENCH, state.state, "bad_day")
        model.update_capacity(BENCH, "bad_day", before * 0.6, state.state)
        return abs(model.capacity("bench_press") / before - 1)

    young = displacement(3)
    tenth = displacement(10)
    settled = displacement(SETTLED_OBSERVATIONS)

    limit = ENGINE_PARAMETERS.value("capacity_session_max_move")
    assert young == pytest.approx(tenth)
    assert tenth == pytest.approx(settled)
    assert young <= limit
