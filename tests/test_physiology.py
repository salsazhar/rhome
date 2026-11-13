"""True latent physiology (``DATA.md`` §16.2).

These tests establish the properties that make the synthetic dataset a genuine
test of the engine rather than a circular one.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_sim.athlete import sample_athlete
from rhome_sim.physiology import LatentState, Physiology, SIM_PHYSIOLOGY

SEED = 20260822


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture
def physiology():
    return Physiology(sample_athlete(SEED))


def _hard_session(physiology, library, sets=4, reps=5, rir=1.0, exercise="back_squat"):
    physiology.begin_session()
    for _ in range(sets):
        physiology.apply_set(
            library[exercise], reps=reps, true_rir=rir,
            relative_intensity=0.85, exposure_count=50,
        )


# --- invariants ------------------------------------------------------------

def test_initial_state_is_empty():
    state = LatentState.initial()
    assert all(state.local_fatigue(m) == 0.0 for m in Muscle)
    assert state.systemic == 0.0 and state.neuromuscular == 0.0


def test_fatigue_is_never_negative_and_decays_monotonically(physiology, library):
    _hard_session(physiology, library)
    previous = physiology.state.local_fatigue(Muscle.QUADS)
    for hours in range(6, 400, 6):
        physiology.advance_to(float(hours))
        current = physiology.state.local_fatigue(Muscle.QUADS)
        assert 0.0 <= current <= previous
        previous = current


def test_time_cannot_run_backwards(physiology):
    physiology.advance_to(50.0)
    with pytest.raises(ValueError, match="backwards"):
        physiology.advance_to(20.0)


def test_zero_elapsed_time_changes_nothing(physiology, library):
    _hard_session(physiology, library)
    before = physiology.state.local_fatigue(Muscle.QUADS)
    physiology.advance_to(physiology.state.t_h)
    assert physiology.state.local_fatigue(Muscle.QUADS) == before


@pytest.mark.parametrize("reps, rir", [(0, 1.0), (-1, 1.0), (5, -0.5)])
def test_impossible_sets_are_rejected(physiology, library, reps, rir):
    with pytest.raises(ValueError):
        physiology.apply_set(
            library["back_squat"], reps=reps, true_rir=rir,
            relative_intensity=0.8, exposure_count=10,
        )


# --- structural difference 1: two-component recovery ----------------------

@pytest.mark.spec("DATA:simulator-not-algebraic-mirror")
def test_local_fatigue_has_two_components(physiology, library):
    _hard_session(physiology, library)
    fast = physiology.state.fatigue_fast[Muscle.QUADS]
    slow = physiology.state.fatigue_slow[Muscle.QUADS]
    assert fast > 0 and slow > 0
    assert slow > fast, "damaging work should load the slow component preferentially"


@pytest.mark.spec("DATA:simulator-not-algebraic-mirror")
def test_a_single_exponential_cannot_fit_the_recovery_curve(physiology, library):
    """The engine fits one exponential to a sum of two.

    The best single-exponential fit must leave visible structure in the
    residuals, otherwise the two-component model is decorative and the engine
    could recover it exactly.
    """
    _hard_session(physiology, library)
    start = physiology.state.local_fatigue(Muscle.QUADS)

    hours = np.arange(2.0, 96.0, 2.0)
    observed = []
    for hour in hours:
        clone = Physiology(physiology.athlete, state=physiology.state.copy())
        clone.advance_to(clone.state.t_h + float(hour))
        observed.append(clone.state.local_fatigue(Muscle.QUADS))
    observed = np.array(observed)

    # Best single exponential in log space.
    log_ratio = np.log(observed / start)
    rate = -float(np.sum(hours * log_ratio) / np.sum(hours**2))
    predicted = start * np.exp(-rate * hours)

    relative_error = np.abs(predicted - observed) / observed
    assert relative_error.max() > 0.10, (
        f"a single exponential fits to within {relative_error.max():.1%}; the "
        f"two-component structure would be recoverable and therefore vacuous"
    )


@pytest.mark.spec("RESEARCH:residual-fatigue-tail")
def test_a_demanding_session_leaves_a_meaningful_tail_at_48_to_72_hours(
    physiology, library
):
    """``RESEARCH.md`` §9.2: fatigue persists 48-72 h after demanding work."""
    _hard_session(physiology, library, sets=5, rir=0.0)
    peak = physiology.state.local_fatigue(Muscle.QUADS)

    fractions = {}
    for hour in (24.0, 48.0, 72.0):
        clone = Physiology(physiology.athlete, state=physiology.state.copy())
        clone.advance_to(clone.state.t_h + hour)
        fractions[hour] = clone.state.local_fatigue(Muscle.QUADS) / peak

    assert 0.35 <= fractions[24.0] <= 0.70, f"24 h: {fractions[24.0]:.0%}"
    assert 0.15 <= fractions[48.0] <= 0.50, f"48 h: {fractions[48.0]:.0%}"
    assert 0.05 <= fractions[72.0] <= 0.35, f"72 h: {fractions[72.0]:.0%}"


# --- structural difference 2: state-dependent accumulation ----------------

@pytest.mark.spec("DATA:nonlinear-fatigue-accumulation")
def test_the_same_session_costs_more_when_the_muscle_is_already_fatigued(library):
    """The engine's impulses are independent of current state; these are not."""
    athlete = sample_athlete(SEED)

    fresh = Physiology(athlete)
    _hard_session(fresh, library, sets=2)
    fresh_cost = fresh.state.local_fatigue(Muscle.QUADS)

    tired = Physiology(athlete)
    _hard_session(tired, library, sets=4)
    tired.advance_to(24.0)
    before = tired.state.local_fatigue(Muscle.QUADS)
    _hard_session(tired, library, sets=2)
    tired_cost = tired.state.local_fatigue(Muscle.QUADS) - before

    assert tired_cost > fresh_cost * 1.02, (
        f"identical work cost {tired_cost:.4f} when fatigued versus "
        f"{fresh_cost:.4f} when fresh; the difference must be real"
    )


@pytest.mark.spec("DATA:nonlinear-fatigue-accumulation")
def test_fatigue_accumulates_supralinearly_within_a_session(physiology, library):
    """Ten sets must cost more than ten times one set."""
    one = Physiology(physiology.athlete)
    _hard_session(one, library, sets=1)
    single = one.state.local_fatigue(Muscle.QUADS)

    many = Physiology(physiology.athlete)
    _hard_session(many, library, sets=10)
    total = many.state.local_fatigue(Muscle.QUADS)

    assert total > single * 10.0, (
        f"{total:.4f} for ten sets versus {single * 10:.4f} for ten times one; "
        f"accumulation is linear and therefore mirrors the engine"
    )


# --- structural difference 3: volume by proximity to failure --------------

@pytest.mark.spec("DATA:nonlinear-fatigue-accumulation")
def test_volume_and_proximity_to_failure_interact(library):
    """Required explicitly by ``DATA.md`` §16.2.

    The engine multiplies its effort and repetition terms independently, so
    volume and failure cannot interact in it. Here they must.
    """
    athlete = sample_athlete(SEED)

    def cost(sets: int, rir: float) -> float:
        physiology = Physiology(athlete)
        _hard_session(physiology, library, sets=sets, rir=rir)
        return physiology.state.local_fatigue(Muscle.QUADS)

    # Ratio of failure work to submaximal work, at low and high volume.
    low_volume_ratio = cost(2, 0.0) / cost(2, 3.0)
    high_volume_ratio = cost(8, 0.0) / cost(8, 3.0)

    assert high_volume_ratio > low_volume_ratio * 1.05, (
        f"failure penalty is {low_volume_ratio:.2f}x at low volume and "
        f"{high_volume_ratio:.2f}x at high volume; these must differ or the "
        f"terms are separable exactly as the engine assumes"
    )


def test_session_boundaries_do_not_change_state(physiology, library):
    """Beginning a session resets accumulators only, never the state itself."""
    _hard_session(physiology, library)
    before = physiology.state.copy()
    physiology.begin_session()
    assert physiology.state.local_fatigue(Muscle.QUADS) == before.local_fatigue(Muscle.QUADS)
    assert physiology.state.systemic == before.systemic


# --- structural difference 4: systemic drag on local recovery -------------

@pytest.mark.spec("DATA:simulator-not-algebraic-mirror")
def test_high_systemic_load_slows_local_recovery(library):
    """A coupling the engine does not model: it modulates recovery only via
    wearable context, never via its own systemic state."""
    athlete = sample_athlete(SEED)

    isolated = Physiology(athlete)
    isolated.begin_session()
    isolated.apply_set(library["leg_extension"], reps=10, true_rir=1.0,
                       relative_intensity=0.72, exposure_count=50)
    start_isolated = isolated.state.local_fatigue(Muscle.QUADS)
    isolated.advance_to(24.0)
    isolated_retained = isolated.state.local_fatigue(Muscle.QUADS) / start_isolated

    loaded = Physiology(athlete)
    loaded.begin_session()
    loaded.apply_set(library["leg_extension"], reps=10, true_rir=1.0,
                     relative_intensity=0.72, exposure_count=50)
    loaded.state.systemic = 1.5  # a heavy day elsewhere in the body
    start_loaded = loaded.state.local_fatigue(Muscle.QUADS)
    loaded.advance_to(24.0)
    loaded_retained = loaded.state.local_fatigue(Muscle.QUADS) / start_loaded

    assert loaded_retained > isolated_retained * 1.05, (
        "systemic load must slow local recovery"
    )


# --- structural difference 5: novelty --------------------------------------

def test_novelty_inflates_fatigue_and_decays_with_exposure(physiology):
    first = physiology.novelty_multiplier(0)
    fifth = physiology.novelty_multiplier(5)
    familiar = physiology.novelty_multiplier(40)
    assert first > fifth > familiar
    assert familiar == pytest.approx(1.0, abs=0.02)
    assert first <= SIM_PHYSIOLOGY.novelty_cap


def test_novelty_rejects_a_negative_exposure_count(physiology):
    with pytest.raises(ValueError):
        physiology.novelty_multiplier(-1)


def test_an_unfamiliar_movement_costs_more_than_a_familiar_one(library):
    athlete = sample_athlete(SEED)
    novel, familiar = Physiology(athlete), Physiology(athlete)
    for physiology, exposures in ((novel, 0), (familiar, 50)):
        physiology.begin_session()
        physiology.apply_set(library["back_squat"], reps=8, true_rir=2.0,
                             relative_intensity=0.78, exposure_count=exposures)
    assert novel.state.local_fatigue(Muscle.QUADS) > familiar.state.local_fatigue(Muscle.QUADS)


# --- channel behaviour -----------------------------------------------------

def test_channels_rank_as_the_evaluation_requires(library):
    """``DATA.md`` §19.3 orderings, at the level of the true state."""
    athlete = sample_athlete(SEED)

    def session(exercise, reps, rir, intensity, sets=4):
        physiology = Physiology(athlete)
        physiology.begin_session()
        for _ in range(sets):
            physiology.apply_set(library[exercise], reps=reps, true_rir=rir,
                                 relative_intensity=intensity, exposure_count=50)
        return physiology.state

    squat = session("back_squat", 5, 1.0, 0.85)
    curl = session("db_curl", 12, 1.0, 0.68)
    assert squat.systemic > curl.systemic, "large compound > isolation systemically"
    assert squat.neuromuscular > curl.neuromuscular, "heavy compound > isolation for strain"

    failure = session("back_squat", 5, 0.0, 0.85)
    submaximal = session("back_squat", 5, 3.0, 0.85)
    assert failure.local_fatigue(Muscle.QUADS) > submaximal.local_fatigue(Muscle.QUADS)


def test_stabilisers_accrue_fatigue_but_no_adaptation(library):
    athlete = sample_athlete(SEED)
    physiology = Physiology(athlete)
    physiology.begin_session()
    physiology.apply_set(library["deadlift"], reps=5, true_rir=1.0,
                         relative_intensity=0.85, exposure_count=50)
    assert physiology.state.local_fatigue(Muscle.FOREARMS) > 0
    assert physiology.state.adaptation[Muscle.FOREARMS] == 0.0


def test_adaptation_persists_far_longer_than_fatigue(library):
    """Deloads work because fatigue falls while adaptation barely moves."""
    athlete = sample_athlete(SEED)
    physiology = Physiology(athlete)
    _hard_session(physiology, library, sets=6)
    fatigue_before = physiology.state.local_fatigue(Muscle.QUADS)
    adaptation_before = physiology.state.adaptation[Muscle.QUADS]

    physiology.advance_to(24.0 * 10)
    fatigue_retained = physiology.state.local_fatigue(Muscle.QUADS) / fatigue_before
    adaptation_retained = physiology.state.adaptation[Muscle.QUADS] / adaptation_before

    # After ten days a 42-day adaptation constant retains exp(-240/1008) ~ 79%,
    # while fatigue has essentially resolved. The separation is the point.
    assert fatigue_retained < 0.05, f"fatigue retained {fatigue_retained:.1%}"
    assert adaptation_retained > 0.70, f"adaptation retained {adaptation_retained:.1%}"
    assert adaptation_retained > fatigue_retained * 15, (
        "adaptation must outlast fatigue by a wide margin, or deloads cannot work"
    )


def test_impulse_record_reports_its_multipliers(library):
    athlete = sample_athlete(SEED)
    physiology = Physiology(athlete)
    physiology.begin_session()
    impulse = physiology.apply_set(library["back_squat"], reps=5, true_rir=0.0,
                                   relative_intensity=0.88, exposure_count=0)
    assert impulse.novelty_multiplier > 1.0
    assert impulse.state_amplification == pytest.approx(1.0), "fresh muscle, no amplification"
    assert impulse.neuromuscular > 0 and impulse.systemic > 0
    assert set(impulse.local) == set(library["back_squat"].fatigue_contributions)


# --- determinism -----------------------------------------------------------

@pytest.mark.guardrail(4)
def test_physiology_is_deterministic(library):
    def run():
        physiology = Physiology(sample_athlete(SEED))
        _hard_session(physiology, library, sets=5)
        physiology.advance_to(36.0)
        return physiology.state.local_fatigue_all()

    assert run() == run()
