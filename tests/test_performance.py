"""Performance generation chain (``DATA.md`` §9.5).

The causal ordering tested here is what makes the dataset evidence rather than
a description of the answer.
"""

from __future__ import annotations

import math
import statistics as st
from collections import Counter

import pytest

from rhome_core.exercises import load_library
from rhome_core.seeding import RootSeed
from rhome_sim.athlete import sample_athlete
from rhome_sim.performance import (
    PerformanceModel,
    true_max_reps,
    true_relative_intensity,
)
from rhome_sim.physiology import Physiology
from rhome_sim.programme import Prescription, ProgrammeGenerator, SessionPlan, SessionType
from rhome_sim.recovery import RecoveryModel

SEED = 20260822
LIBRARY = load_library()


def _rig(seed: int = SEED):
    root = RootSeed(seed)
    athlete = sample_athlete(seed)
    return (
        athlete,
        Physiology(athlete),
        PerformanceModel(athlete, LIBRARY, root.stream("sim.performance")),
    )


def _two_years(seed: int = SEED):
    root = RootSeed(seed)
    athlete = sample_athlete(seed)
    physiology = Physiology(athlete)
    programme = ProgrammeGenerator(LIBRARY, root.stream("sim.programme"))
    performance = PerformanceModel(athlete, LIBRARY, root.stream("sim.performance"))
    recovery = RecoveryModel(athlete, root.stream("sim.recovery"))
    plans = {p.day_index: p for p in programme.plan_days(730)}

    sets = []
    for day in range(730):
        latent = recovery.step(day, systemic_load=physiology.state.systemic)
        physiology.advance_to(day * 24.0 + 8.0, recovery_propensity=latent.recovery_propensity)
        plan = plans.get(day)
        if plan is None:
            continue
        physiology.advance_to(day * 24.0 + 17.0, recovery_propensity=latent.recovery_propensity)
        sets.extend(performance.realise_session(plan, physiology, athlete.initial_body_mass_kg))
    return athlete, performance, sets


@pytest.fixture(scope="module")
def run():
    return _two_years()


# --- the relative-intensity curve ------------------------------------------

def test_relative_intensity_falls_monotonically_with_repetitions():
    previous = 1.01
    for reps in range(1, 40):
        current = true_relative_intensity(reps)
        assert 0.0 < current < previous
        previous = current


def test_a_single_repetition_is_the_one_repetition_maximum():
    assert true_relative_intensity(1) == pytest.approx(1.0, abs=0.01)


def test_the_curve_and_its_inverse_agree():
    for reps in (1, 3, 5, 8, 12, 20):
        intensity = true_relative_intensity(reps)
        assert true_max_reps(intensity) == pytest.approx(reps, rel=0.02)


@pytest.mark.spec("DATA:simulator-richer-than-engine")
def test_endurance_scales_achievable_repetitions():
    """Nuzzo et al. report large between-person variation here, so this is a
    parameter the engine's population prior cannot capture."""
    assert true_max_reps(0.80, 0.8) < true_max_reps(0.80, 1.0) < true_max_reps(0.80, 1.3)


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5])
def test_impossible_relative_intensities_are_rejected(bad):
    with pytest.raises(ValueError):
        true_max_reps(bad)


# --- the causal ordering ---------------------------------------------------

@pytest.mark.spec("DATA:causal-performance-chain")
def test_fatigue_reduces_expressible_capacity():
    athlete, physiology, performance = _rig()
    exercise = LIBRARY["back_squat"]
    fresh, fresh_factor = performance.expressible_capacity(exercise, physiology)

    physiology.begin_session()
    for _ in range(5):
        physiology.apply_set(exercise, reps=5, true_rir=0.0,
                             relative_intensity=0.85, exposure_count=50)
    tired, tired_factor = performance.expressible_capacity(exercise, physiology)

    assert tired < fresh
    assert tired_factor < fresh_factor < 1.0 + 1e-9


@pytest.mark.spec("DATA:causal-performance-chain")
def test_the_same_session_yields_fewer_repetitions_when_fatigued():
    """Observable output must follow from hidden state, not sit beside it."""
    prescription = Prescription("back_squat", 3, 8, 10, 1.5)

    _, fresh_physiology, fresh_performance = _rig()
    fresh = fresh_performance.realise_prescription(
        prescription, fresh_physiology, 80.0, session_shock=1.0
    )

    _, tired_physiology, tired_performance = _rig()
    tired_physiology.begin_session()
    for _ in range(8):
        tired_physiology.apply_set(LIBRARY["back_squat"], reps=6, true_rir=0.0,
                                   relative_intensity=0.85, exposure_count=50)
    tired = tired_performance.realise_prescription(
        prescription, tired_physiology, 80.0, session_shock=1.0
    )

    assert sum(s.reps for s in tired) <= sum(s.reps for s in fresh)
    assert tired[0].fatigue_factor < fresh[0].fatigue_factor


@pytest.mark.spec("DATA:no-observable-depends-on-later-latent")
def test_true_rir_follows_from_the_set_that_was_performed():
    """RIR is derived, never assigned: capable minus performed."""
    _, physiology, performance = _rig()
    sets = performance.realise_prescription(
        Prescription("bench_press", 3, 4, 6, 2.0), physiology, 80.0, session_shock=1.0
    )
    for performed in sets:
        capable = true_max_reps(
            performed.true_relative_intensity,
            performance.athlete.rep_endurance[performed.exercise_id],
        )
        assert performed.true_rir == pytest.approx(max(0.0, capable - performed.reps), abs=0.01)


@pytest.mark.spec("DATA:no-observable-depends-on-later-latent")
def test_repetitions_never_exceed_what_was_physically_possible(run):
    _, performance, sets = run
    for performed in sets:
        capable = true_max_reps(
            performed.true_relative_intensity,
            performance.athlete.rep_endurance[performed.exercise_id],
        )
        assert performed.reps <= math.floor(capable) + 1e-9
        assert performed.true_rir >= 0.0


@pytest.mark.spec("DATA:causal-performance-chain")
def test_within_session_fatigue_shows_in_later_sets():
    _, physiology, performance = _rig()
    sets = performance.realise_prescription(
        Prescription("back_squat", 5, 8, 10, 1.0), physiology, 80.0, session_shock=1.0
    )
    assert sets[-1].true_expressible_capacity < sets[0].true_expressible_capacity


# --- observation noise (MODEL.tex) -----------------------------------------

@pytest.mark.spec("MODEL:rir-observation-noise")
def test_logged_effort_is_the_truth_corrupted_by_documented_noise(run):
    athlete, _, sets = run
    errors = [(10.0 - s.logged_rpe) - s.true_rir for s in sets]
    assert st.pstdev(errors) == pytest.approx(athlete.rir_noise_sd, rel=0.30)
    assert abs(st.mean(errors)) < 0.25, "aggregate reporting bias should be small"


@pytest.mark.spec("MODEL:rir-observation-noise")
def test_logged_effort_differs_from_truth_on_most_sets(run):
    _, _, sets = run
    exact = sum(1 for s in sets if abs((10.0 - s.logged_rpe) - s.true_rir) < 1e-9)
    assert exact / len(sets) < 0.30, "observation noise is not being applied"


def test_logged_effort_stays_on_the_half_point_scale(run):
    _, _, sets = run
    for performed in sets:
        assert 2.0 <= performed.logged_rpe <= 10.0
        assert abs(performed.logged_rpe * 2 - round(performed.logged_rpe * 2)) < 1e-9


# --- realised distributions (DATA.md §9.1, §9.2) ---------------------------

def _rep_band(reps: int) -> str:
    if reps <= 3: return "1-3"
    if reps <= 6: return "4-6"
    if reps <= 10: return "7-10"
    if reps <= 15: return "11-15"
    return "16-25"


def _rpe_band(rpe: float) -> str:
    if rpe <= 7.25: return "6-7"
    if rpe <= 8.25: return "7.5-8"
    if rpe <= 9.25: return "8.5-9"
    return "9.5-10"


@pytest.mark.spec("DATA:rep-range-distribution")
def test_realised_repetition_bands_match_the_specification(run):
    _, _, sets = run
    counts = Counter(_rep_band(s.reps) for s in sets)
    targets = {"1-3": (10, 15), "4-6": (24, 29), "7-10": (31, 37),
               "11-15": (18, 22), "16-25": (5, 9)}
    for band, (low, high) in targets.items():
        pct = 100 * counts[band] / len(sets)
        assert low <= pct <= high, f"realised {band}: {pct:.1f}%, documented {low}-{high}%"


@pytest.mark.spec("DATA:rpe-distribution")
def test_true_effort_distribution_matches_the_specification(run):
    """What the athlete actually trains at (``DATA.md`` §9.2.1, true column)."""
    _, _, sets = run
    counts = Counter(min(3, round(s.true_rir)) for s in sets)
    documented = {0: (10, 14), 1: (28, 33), 2: (35, 39), 3: (18, 23)}
    for rir, (low, high) in documented.items():
        pct = 100 * counts[rir] / len(sets)
        assert low <= pct <= high, f"true RIR {rir}: {pct:.1f}%, documented {low}-{high}%"


@pytest.mark.spec("DATA:rpe-distribution")
def test_logged_effort_distribution_matches_the_specification(run):
    """What the log contains (``DATA.md`` §9.2.1, logged column).

    Materially flatter than true effort, because reported RIR carries roughly
    0.9 repetitions of estimation error. That smearing is irreversible at the
    level of a single set, and is a floor on how well any engine can estimate
    relative intensity.
    """
    _, _, sets = run
    counts = Counter(min(3, int(s.logged_rir)) for s in sets)
    documented = {0: (17, 25), 1: (22, 28), 2: (24, 28), 3: (24, 35)}
    for rir, (low, high) in documented.items():
        pct = 100 * counts[rir] / len(sets)
        assert low <= pct <= high, f"logged RIR {rir}: {pct:.1f}%, documented {low}-{high}%"


@pytest.mark.spec("DATA:rpe-distribution")
def test_the_log_is_flatter_than_the_training(run):
    """The property §9.2.2 exists to warn the engine about.

    An athlete training almost entirely at 1-2 RIR produces a log spanning 0-4,
    and no engine can invert that.
    """
    _, _, sets = run
    true_spread = st.pstdev([s.true_rir for s in sets])
    logged_spread = st.pstdev([float(s.logged_rir) for s in sets])
    assert logged_spread > true_spread * 1.10, (
        "estimation error must visibly widen the recorded distribution"
    )


def test_effort_is_recorded_as_whole_repetitions(run):
    """Half-point logging places two reportable values in the 9.5-10 band and
    piles the error tail onto RPE 10 (``DATA.md`` §9.2.3)."""
    _, _, sets = run
    for performed in sets:
        assert performed.logged_rir == round(performed.logged_rir)
        assert 0 <= performed.logged_rir <= 8
        assert performed.logged_rpe == pytest.approx(10.0 - performed.logged_rir)


def test_maximal_is_not_the_most_common_entry(run):
    """The defect whole-number logging was adopted to remove."""
    _, _, sets = run
    counts = Counter(int(s.logged_rir) for s in sets)
    assert counts[1] > counts[0], (
        "more sets logged at failure than at one repetition in reserve; "
        "no real training log looks like that"
    )


def test_true_effort_sits_where_a_trained_athlete_trains(run):
    _, _, sets = run
    rirs = [s.true_rir for s in sets]
    assert 1.2 <= st.mean(rirs) <= 2.6, f"mean true RIR {st.mean(rirs):.2f}"
    assert 0.02 <= sum(1 for r in rirs if r < 0.5) / len(rirs) <= 0.25


# --- progression and adaptation (DATA.md §9.4) -----------------------------

@pytest.mark.spec("DATA:progression-from-capacity")
def test_capacity_grows_by_a_plausible_amount_over_two_years(run):
    athlete, performance, _ = run
    for exercise_id in ("bench_press", "back_squat", "deadlift"):
        gain = performance.state[exercise_id].capacity_kg / athlete.initial_capacity_kg[exercise_id] - 1
        assert 0.05 <= gain <= 0.35, f"{exercise_id} gained {gain:.1%} in two years"


@pytest.mark.spec("DATA:progression-from-capacity")
def test_working_loads_follow_capacity_rather_than_a_fixed_schedule(run):
    _, performance, sets = run
    early = [s.load_kg for s in sets[:400] if s.exercise_id == "bench_press"]
    late = [s.load_kg for s in sets[-400:] if s.exercise_id == "bench_press"]
    assert early and late
    assert st.mean(late) > st.mean(early), "load must progress"
    assert st.mean(late) < st.mean(early) * 1.6, "progression must stay plausible"


def test_loads_land_on_realistic_increments(run):
    _, _, sets = run
    for performed in sets:
        equipment = LIBRARY[performed.exercise_id].equipment.value
        step = {"barbell": 2.5, "machine": 5.0, "cable": 2.5,
                "dumbbell": 2.0, "bodyweight": 2.5}[equipment]
        assert abs(performed.load_kg / step - round(performed.load_kg / step)) < 1e-6


def test_bodyweight_exercises_use_effective_system_load():
    _, physiology, performance = _rig()
    pullup = LIBRARY["weighted_pullup"]
    assert performance.effective_load(pullup, 20.0, 80.0) == pytest.approx(100.0)
    bench = LIBRARY["bench_press"]
    assert performance.effective_load(bench, 100.0, 80.0) == pytest.approx(100.0)


# --- shocks ---------------------------------------------------------------

def test_occasional_sessions_carry_an_unexplained_shock(run):
    """Scenario S11: a conspicuously bad session with no observable cause."""
    _, _, sets = run
    shocks = [s.performance_shock for s in sets]
    assert min(shocks) < 0.90, "no session was unusually poor"
    assert max(shocks) > 1.08, "no session was unusually good"
    assert 0.95 < st.median(shocks) < 1.05, "shocks must be centred, not a trend"


def test_personal_records_are_flagged_from_prior_logs_only():
    _, physiology, performance = _rig()
    first = performance.realise_prescription(
        Prescription("bench_press", 2, 4, 6, 2.0), physiology, 80.0, session_shock=1.0
    )
    flags = performance.mark_personal_records(first)
    assert flags[0] is False, "the first ever set cannot be a personal record"
    assert len(flags) == len(first)


# --- determinism -----------------------------------------------------------

@pytest.mark.guardrail(4)
def test_performance_generation_is_deterministic():
    def run_once():
        _, physiology, performance = _rig(11)
        plan = SessionPlan(0, SessionType.UPPER_A,
                           (Prescription("bench_press", 3, 4, 6, 2.0),))
        return [(s.reps, s.load_kg, s.true_rir) for s in
                performance.realise_session(plan, physiology, 80.0)]

    assert run_once() == run_once()
