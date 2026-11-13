"""Per-set dose transformation (``MODEL.tex``).

Golden values are computed by hand from the specification and asserted exactly.
An equation transcribed slightly wrong still produces plausible numbers, so
"looks about right" is not a test.
"""

from __future__ import annotations

import pytest

from rhome_core.exercises import load_library
from rhome_core.intensity import IntensityConfidence
from rhome_core.muscles import Muscle
from rhome_engine.dose import (
    LoggedSet,
    amplify_within_session_fatigue,
    fatigue_rep_term,
    phi,
    stimulus_rep_term,
    transform_set,
)
from rhome_engine.parameters import (
    ENGINE_PARAMETERS,
    PHI_FATIGUE,
    PHI_NEUROMUSCULAR,
    PHI_STIMULUS,
)

LIBRARY = load_library()


def _set(exercise_id="back_squat", reps=5, rir=2.0, set_type="working", **kw):
    return LoggedSet("w1", exercise_id, 1, set_type, kw.pop("load_kg", 140.0), reps, rir=rir, **kw)


# --- golden values, hand-computed from MODEL.tex ---------------------------

def test_a_back_squat_set_reproduces_its_hand_computed_dose():
    """Back squat, 5 repetitions at 2 RIR, familiar movement.

    Relative intensity, interpolating the Nuzzo rows bracketing 7 repetitions
    to failure --- (4.94, 0.90) and (7.15, 0.85)::

        span = (7 - 4.94) / (7.15 - 4.94) = 0.932126697
        u    = 0.90 + span x (0.85 - 0.90) = 0.853393665

    Then, from MODEL.tex::

        stimulus  = c_S x phi_S(2) x phi_R(5)      = 1.00 x 0.85 x 1.00  = 0.85
        fatigue   = d0 x c_F x phi_F(2) x psi_R(5) = 0.06 x 1.00 x 1.00 x 0.90
                                                                          = 0.054
        strain    = n0 x kappa x u^2 x phi_N(2)    = 0.10 x 0.95 x 0.728280748
                                                                          = 0.069186671
        systemic  = g0 x b x phi_F(2) x psi_R(5)   = 0.07 x 0.92 x 1.00 x 0.90
                                                                          = 0.05796

    The strain figure is written out at full precision deliberately. My first
    hand calculation rounded u to 0.8534 before squaring and produced 0.069188,
    which the tolerance caught. The code was right and the arithmetic beside it
    was not, which is the ordinary way round for a golden value to fail.
    """
    dose = transform_set(_set(), LIBRARY["back_squat"])
    assert dose.relative_intensity == pytest.approx(0.853393665, abs=1e-9)
    assert dose.stimulus[Muscle.QUADS] == pytest.approx(0.85, abs=1e-9)
    assert dose.local_fatigue[Muscle.QUADS] == pytest.approx(0.054, abs=1e-9)
    assert dose.neuromuscular == pytest.approx(0.069186671, abs=1e-9)
    assert dose.systemic == pytest.approx(0.05796, abs=1e-9)


@pytest.mark.spec("MODEL:within-session-fatigue-curvature")
def test_local_fatigue_curves_by_observable_muscle_position_and_saturates():
    raw = transform_set(_set(), LIBRARY["back_squat"])
    early = amplify_within_session_fatigue(raw, {})
    fifth = amplify_within_session_fatigue(raw, {Muscle.QUADS: 4})
    later = amplify_within_session_fatigue(raw, {Muscle.QUADS: 40})

    assert early.local_fatigue[Muscle.QUADS] == pytest.approx(0.054)
    assert fifth.local_fatigue[Muscle.QUADS] == pytest.approx(0.108)
    assert later.local_fatigue[Muscle.QUADS] == pytest.approx(0.108)
    assert fifth.stimulus == raw.stimulus
    assert fifth.neuromuscular == raw.neuromuscular
    assert fifth.systemic == raw.systemic


def test_secondary_muscles_receive_half_the_direct_contribution():
    dose = transform_set(_set(), LIBRARY["back_squat"])
    assert dose.stimulus[Muscle.HAMSTRINGS] == pytest.approx(
        dose.stimulus[Muscle.QUADS] * 0.5
    )


def test_stabilisers_take_fatigue_but_earn_no_stimulus():
    dose = transform_set(_set("deadlift", reps=3, rir=1.0), LIBRARY["deadlift"])
    assert Muscle.FOREARMS not in dose.stimulus
    assert dose.local_fatigue[Muscle.FOREARMS] > 0
    assert dose.local_fatigue[Muscle.FOREARMS] == pytest.approx(
        dose.local_fatigue[Muscle.HAMSTRINGS] * 0.20
    )


# --- the multiplier tables -------------------------------------------------

@pytest.mark.parametrize("rir, expected", list(PHI_STIMULUS.items()))
def test_stimulus_multipliers_match_the_specification(rir, expected):
    assert phi(PHI_STIMULUS, rir) == pytest.approx(expected)


@pytest.mark.parametrize("rir, expected", list(PHI_FATIGUE.items()))
def test_fatigue_multipliers_match_the_specification(rir, expected):
    assert phi(PHI_FATIGUE, rir) == pytest.approx(expected)


def test_multipliers_interpolate_for_half_point_effort():
    """RPE is logged in half points, so fractional reserve values occur."""
    assert phi(PHI_FATIGUE, 1.5) == pytest.approx((1.15 + 1.00) / 2)


def test_multipliers_saturate_beyond_the_final_row():
    assert phi(PHI_STIMULUS, 9) == pytest.approx(PHI_STIMULUS[6])
    assert phi(PHI_NEUROMUSCULAR, 7) == pytest.approx(PHI_NEUROMUSCULAR[3])


@pytest.mark.parametrize("reps, expected", [(1, 0.20), (3, 0.60), (5, 1.00), (12, 1.00)])
def test_low_repetition_sets_are_not_full_hypertrophic_doses(reps, expected):
    assert stimulus_rep_term(reps) == pytest.approx(expected)


@pytest.mark.parametrize("reps, expected", [(1, 0.86), (5, 0.90), (12, 1.04), (30, 1.20)])
def test_the_fatigue_repetition_term_is_clipped_at_both_ends(reps, expected):
    assert fatigue_rep_term(reps) == pytest.approx(expected)


# --- the model's central claim ---------------------------------------------

@pytest.mark.spec("MODEL:failure-costs-more-than-it-buys")
def test_failure_raises_fatigue_more_than_it_raises_stimulus():
    """Training to failure costs disproportionately (``RESEARCH.md`` §9.1).

    Encoded as the *shape* of two curves, not as a single coefficient: between
    2 and 0 repetitions in reserve, stimulus rises by 18% and fatigue by 35%.
    """
    stimulus_gain = PHI_STIMULUS[0] / PHI_STIMULUS[2]
    fatigue_gain = PHI_FATIGUE[0] / PHI_FATIGUE[2]
    assert fatigue_gain > stimulus_gain, (
        f"fatigue rises {fatigue_gain:.2f}x against stimulus {stimulus_gain:.2f}x; "
        f"failure must cost more than it buys"
    )


@pytest.mark.spec("MODEL:four-dose-channels")
def test_the_four_channels_are_genuinely_separate():
    """A set can be high in one channel and low in another."""
    heavy = transform_set(_set("deadlift", reps=3, rir=1.0), LIBRARY["deadlift"])
    light = transform_set(_set("lateral_raise", reps=15, rir=1.0, load_kg=12.0),
                          LIBRARY["lateral_raise"])
    assert heavy.neuromuscular > light.neuromuscular * 5
    assert heavy.systemic > light.systemic * 3
    # But the isolation set is not negligible for its own muscle's stimulus.
    assert light.stimulus[Muscle.LATERAL_DELTS] > 0.5 * heavy.stimulus[Muscle.HAMSTRINGS]


@pytest.mark.spec("MODEL:four-dose-channels")
def test_ranking_tests_from_the_evaluation_protocol():
    """``DATA.md`` §19.3, at the level of a single set."""
    failure = transform_set(_set(rir=0.0), LIBRARY["back_squat"])
    submaximal = transform_set(_set(rir=3.0), LIBRARY["back_squat"])
    assert failure.local_fatigue[Muscle.QUADS] > submaximal.local_fatigue[Muscle.QUADS]

    compound = transform_set(_set("back_squat", reps=5, rir=1.0), LIBRARY["back_squat"])
    isolation = transform_set(_set("leg_extension", reps=12, rir=1.0, load_kg=60.0),
                              LIBRARY["leg_extension"])
    assert compound.systemic > isolation.systemic
    assert compound.neuromuscular > isolation.neuromuscular


# --- set type inclusion (MODEL.tex) ----------------------------------------

@pytest.mark.spec("MODEL:set-type-inclusion")
def test_warm_ups_carry_no_dose():
    dose = transform_set(_set(set_type="warmup"), LIBRARY["back_squat"])
    assert not dose.stimulus and not dose.local_fatigue
    assert dose.neuromuscular == 0.0 and dose.systemic == 0.0
    assert dose.excluded_reason


@pytest.mark.spec("MODEL:set-type-inclusion")
def test_drop_segments_carry_full_dose_but_no_performance_information():
    """The work was genuinely performed; the intensity inversion does not apply."""
    working = transform_set(_set(set_type="working"), LIBRARY["back_squat"])
    drop = transform_set(_set(set_type="drop"), LIBRARY["back_squat"])
    assert drop.local_fatigue == working.local_fatigue
    assert drop.eligible_for_performance is False
    assert working.eligible_for_performance is True
    assert "pre-fatigued" in drop.excluded_reason


@pytest.mark.spec("MODEL:set-type-inclusion")
def test_back_off_sets_are_ordinary_working_sets():
    working = transform_set(_set(set_type="working"), LIBRARY["back_squat"])
    backoff = transform_set(_set(set_type="backoff"), LIBRARY["back_squat"])
    assert backoff.local_fatigue == working.local_fatigue
    assert backoff.eligible_for_performance


def test_a_set_outside_the_evidence_domain_still_carries_dose():
    dose = transform_set(_set("calf_raise", reps=25, rir=4.0, load_kg=80.0),
                         LIBRARY["calf_raise"])
    assert dose.intensity_confidence is IntensityConfidence.LOW
    assert dose.local_fatigue[Muscle.CALVES] > 0, "the work was performed"
    assert not dose.eligible_for_performance, "but the inversion does not apply"


def test_a_working_set_without_an_effort_rating_is_imputed_not_discarded():
    """``MODEL.tex`` §Working sets logged without an effort rating.

    Discarding the set is the obvious response and is wrong: the athlete did
    the work and its fatigue is real, so forgetting it makes the model
    optimistic. The Layer 2 audit measured the cost of the old behaviour at
    2.1% of dose-bearing work, on days whose confidence then read *higher*
    than their neighbours.
    """
    unrated = LoggedSet("w", "bench_press", 1, "working", load_kg=100.0, reps=8)
    dose = transform_set(unrated, LIBRARY["bench_press"])

    assert dose.local_fatigue and dose.stimulus
    assert dose.neuromuscular > 0 and dose.systemic > 0
    assert dose.effort_imputed
    assert dose.intensity_confidence is IntensityConfidence.LOW
    assert dose.repetitions_in_reserve == pytest.approx(
        ENGINE_PARAMETERS.value("imputed_rir_prior")
    )


def test_an_imputed_set_never_becomes_a_performance_observation():
    """Imputing a dose and inventing a performance reading are different acts.

    A guessed effort supports an estimate of how much fatigue a set caused. It
    supports nothing at all about what the athlete was capable of.
    """
    unrated = LoggedSet("w", "bench_press", 1, "working", load_kg=100.0, reps=8)
    dose = transform_set(unrated, LIBRARY["bench_press"])
    assert not dose.eligible_for_performance
    assert "no performance estimate" in dose.excluded_reason


def test_the_imputed_effort_comes_from_the_athletes_own_history():
    """Each fallback is a step further from the person, so it is taken later."""
    from rhome_engine.session import _EffortHistory

    history = _EffortHistory()
    assert history.impute("bench_press") == pytest.approx(
        ENGINE_PARAMETERS.value("imputed_rir_prior")
    )

    for _ in range(6):
        history.observe("back_squat", 0.0)
    assert history.impute("bench_press") == pytest.approx(0.0), (
        "with no bench history, the athlete's general habit should be used"
    )

    for _ in range(6):
        history.observe("bench_press", 3.0)
    assert history.impute("bench_press") == pytest.approx(3.0)

def test_explicit_reserve_is_preferred_over_a_derived_one():
    """``DATA.md`` §5.3 makes RIR the primary field."""
    logged = LoggedSet("w1", "back_squat", 1, "working", 140.0, 5, rpe=9.0, rir=2.0)
    assert logged.repetitions_in_reserve() == 2.0


def test_effort_falls_back_to_the_rpe_convention():
    logged = LoggedSet("w1", "back_squat", 1, "working", 140.0, 5, rpe=8.0)
    assert logged.repetitions_in_reserve() == pytest.approx(2.0)


# --- novelty ---------------------------------------------------------------

def test_novelty_inflates_local_fatigue_within_its_cap():
    familiar = transform_set(_set(), LIBRARY["back_squat"], novelty=1.0)
    novel = transform_set(_set(), LIBRARY["back_squat"], novelty=1.25)
    ratio = novel.local_fatigue[Muscle.QUADS] / familiar.local_fatigue[Muscle.QUADS]
    assert ratio == pytest.approx(1.25)

    beyond = transform_set(_set(), LIBRARY["back_squat"], novelty=3.0)
    assert beyond.local_fatigue == novel.local_fatigue, "novelty must be capped"


def test_novelty_touches_only_local_fatigue():
    familiar = transform_set(_set(), LIBRARY["back_squat"], novelty=1.0)
    novel = transform_set(_set(), LIBRARY["back_squat"], novelty=1.25)
    assert novel.stimulus == familiar.stimulus
    assert novel.neuromuscular == familiar.neuromuscular
    assert novel.systemic == familiar.systemic


def test_impossible_sets_are_rejected():
    with pytest.raises(ValueError):
        transform_set(_set(reps=0), LIBRARY["back_squat"])
    with pytest.raises(ValueError):
        phi(PHI_FATIGUE, -1)
