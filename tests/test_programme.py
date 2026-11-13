"""Training programme generation (``DATA.md`` §3.2, §4.2, §9, §18).

The distributions here are requirements, not descriptions. They were reached by
measurement rather than by eye, and these tests are what keep them.
"""

from __future__ import annotations

import statistics as st
from collections import Counter, defaultdict

import pytest

from rhome_core.exercises import load_library
from rhome_core.muscles import REGION_OF, Region
from rhome_core.seeding import RootSeed
from rhome_sim.programme import (
    SESSION_TEMPLATES,
    SUBSTITUTIONS,
    WEEKLY_TEMPLATE,
    Prescription,
    ProgrammeGenerator,
    SessionType,
)

LIBRARY = load_library()
SEEDS = range(6)


def _generator(seed: int) -> ProgrammeGenerator:
    return ProgrammeGenerator(LIBRARY, RootSeed(seed).stream("sim.programme"))


def _plans(seed: int, days: int = 730):
    return _generator(seed).plan_days(days)


@pytest.fixture(scope="module")
def runs():
    return {seed: _plans(seed) for seed in SEEDS}


def _rep_band(reps: int) -> str:
    if reps <= 3: return "1-3"
    if reps <= 6: return "4-6"
    if reps <= 10: return "7-10"
    if reps <= 15: return "11-15"
    return "16-25"


def _rpe_band(target_rir: float) -> str:
    rpe = 10 - target_rir
    if rpe <= 7.25: return "6-7"
    if rpe <= 8.25: return "7.5-8"
    if rpe <= 9.25: return "8.5-9"
    return "9.5-10"


def _weekly_stimulus(plans):
    weekly = defaultdict(lambda: defaultdict(float))
    for plan in plans:
        for prescription in plan.prescriptions:
            exercise = LIBRARY[prescription.exercise_id]
            for muscle, contribution in exercise.stimulus_contributions.items():
                weekly[plan.day_index // 7][muscle] += prescription.sets * contribution
    return weekly


def _parity_deviations(plans):
    weekly = _weekly_stimulus(plans)
    sessions = Counter(p.day_index // 7 for p in plans)
    last_complete = max(w for w in weekly if sessions[w] >= 3)
    ordinary = [w for w in weekly if not (w > 0 and w % 8 == 0) and w < last_complete]

    deviations = []
    for start in range(0, max(ordinary) - 3):
        block = [w for w in range(start, start + 4) if w in ordinary]
        if len(block) < 4:
            continue
        upper = sum(weekly[w][m] for w in block for m in weekly[w]
                    if REGION_OF[m] is Region.UPPER)
        lower = sum(weekly[w][m] for w in block for m in weekly[w]
                    if REGION_OF[m] is Region.LOWER)
        deviations.append(abs(upper - lower) / ((upper + lower) / 2))
    return deviations


# --- scale (DATA.md §4.2) --------------------------------------------------

@pytest.mark.spec("DATA:session-and-set-counts")
@pytest.mark.parametrize("seed", SEEDS)
def test_session_and_set_counts_match_the_specification(runs, seed):
    plans = runs[seed]
    sets = sum(p.total_sets for p in plans)
    assert 470 <= len(plans) <= 510, f"{len(plans)} sessions"
    assert 7500 <= sets <= 8500, f"{sets} working sets"
    assert 14 <= sets / len(plans) <= 18, f"{sets / len(plans):.1f} sets per session"


# --- distributions (DATA.md §9.1, §9.2) ------------------------------------

@pytest.mark.spec("DATA:rep-range-distribution")
@pytest.mark.parametrize("seed", SEEDS)
def test_repetition_bands_match_the_specification(runs, seed):
    """Each prescription's sets spread across its range, as L1.5 will realise."""
    counts, total = Counter(), 0.0
    for plan in runs[seed]:
        for prescription in plan.prescriptions:
            reps = range(prescription.rep_low, prescription.rep_high + 1)
            weight = prescription.sets / len(reps)
            for rep in reps:
                counts[_rep_band(rep)] += weight
                total += weight

    targets = {"1-3": (5, 8), "4-6": (25, 30), "7-10": (35, 40),
               "11-15": (20, 25), "16-25": (5, 10)}
    for band, (low, high) in targets.items():
        pct = 100 * counts[band] / total
        assert low <= pct <= high, f"{band}: {pct:.1f}%, want {low}–{high}%"


@pytest.mark.parametrize("seed", SEEDS)
def test_prescribed_effort_spans_a_plausible_range(runs, seed):
    """Prescribed effort, not realised effort.

    ``DATA.md`` §9.2 describes the effort the athlete actually makes, so the
    authoritative check on that distribution lives in L1.5 where realised sets
    exist (``test_realised_effort_bands_are_close_to_the_specification``).
    The two cannot both match: repetitions are capped at the top of a range on
    easy days, which displaces realised effort away from what was prescribed.
    Prescribed RIR is therefore tuned so the *realised* distribution lands
    correctly, and this test only guards the shape of the plan.
    """
    counts, total = Counter(), 0
    for plan in runs[seed]:
        for prescription in plan.prescriptions:
            counts[_rpe_band(prescription.target_rir)] += prescription.sets
            total += prescription.sets

    for band in ("6-7", "7.5-8", "8.5-9", "9.5-10"):
        pct = 100 * counts[band] / total
        assert 5 <= pct <= 45, f"prescribed RPE {band}: {pct:.1f}%"

    hardest = 100 * counts["9.5-10"] / total
    assert hardest < 30, "ordinary working sets should not mostly be maximal"


# --- upper/lower parity (DATA.md §3.2) -------------------------------------

@pytest.mark.spec("DATA:upper-lower-parity")
def test_upper_lower_parity_holds_across_ordinary_blocks(runs):
    """The hard requirement of ``DATA.md`` §3.2.

    Unrecovered missed sessions were measured to be the sole cause of
    violations; genuine absence therefore lives in the labelled scenarios,
    which §3.2 exempts.
    """
    deviations = [d for seed in SEEDS for d in _parity_deviations(runs[seed])]
    within = sum(1 for d in deviations if d <= 0.10) / len(deviations)

    assert st.median(deviations) < 0.05, f"median {st.median(deviations):.1%}"
    assert within >= 0.95, f"only {within:.1%} of blocks within ±10%"
    assert max(deviations) < 0.20, f"worst block {max(deviations):.1%}"


@pytest.mark.spec("DATA:upper-lower-parity")
def test_the_template_itself_is_balanced_before_any_randomness():
    """Structural balance, independent of misses and substitutions."""
    upper = lower = 0.0
    for rows in SESSION_TEMPLATES.values():
        for exercise_id, sets, *_ in rows:
            for muscle, contribution in LIBRARY[exercise_id].stimulus_contributions.items():
                if REGION_OF[muscle] is Region.UPPER:
                    upper += sets * contribution
                elif REGION_OF[muscle] is Region.LOWER:
                    lower += sets * contribution
    deviation = abs(upper - lower) / ((upper + lower) / 2)
    assert deviation < 0.05, f"templates are {deviation:.1%} out of balance"


# --- weekly volume (DATA.md §9.3) ------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_weekly_volume_per_muscle_is_in_a_plausible_operating_region(runs, seed):
    weekly = _weekly_stimulus(runs[seed])
    ordinary = [w for w in weekly if not (w > 0 and w % 8 == 0)]
    for muscle in LIBRARY.covered_muscles():
        mean = st.mean(weekly[w][muscle] for w in ordinary)
        assert 3.0 <= mean <= 18.0, f"{muscle.value}: {mean:.1f} effective sets/week"


def test_no_muscle_is_left_untrained(runs):
    weekly = _weekly_stimulus(runs[0])
    trained = {m for w in weekly for m in weekly[w] if weekly[w][m] > 0}
    assert trained == set(LIBRARY.covered_muscles())


# --- schedule behaviour (DATA.md §18) --------------------------------------

@pytest.mark.spec("DATA:five-sessions-is-an-average")
def test_weekly_session_count_varies(runs):
    counts = Counter(p.day_index // 7 for p in runs[0])
    distinct = set(counts.values())
    assert len(distinct) > 1, "every week has identical session count; too regular"
    assert st.mean(counts.values()) == pytest.approx(4.8, abs=0.5)


def test_rest_days_carry_no_scheduled_session():
    assert WEEKLY_TEMPLATE.count(SessionType.REST) == 2


def test_make_ups_land_in_the_same_week_as_the_session_they_replace(runs):
    """Rest days sit at template slots 2 and 6, so a make-up never crosses a
    week boundary — which is what preserves weekly volume and hence parity."""
    for plan in runs[0]:
        if plan.notes_code == "rescheduled":
            assert plan.day_index % 7 in (2, 6)


def test_deload_weeks_cut_volume_but_retain_exposure(runs):
    plans = runs[0]
    deload = [p for p in plans if p.is_deload]
    ordinary = [p for p in plans if not p.is_deload]
    assert deload, "no deload weeks were generated"
    assert st.mean(p.total_sets for p in deload) < 0.75 * st.mean(
        p.total_sets for p in ordinary
    )
    for plan in deload:
        assert plan.prescriptions, "a deload must retain some intensity exposure"


def test_deload_sets_are_further_from_failure(runs):
    plans = runs[0]
    deload = [pr.target_rir for p in plans if p.is_deload for pr in p.prescriptions]
    ordinary = [pr.target_rir for p in plans if not p.is_deload for pr in p.prescriptions]
    assert st.mean(deload) > st.mean(ordinary)


def test_substitutions_occur_and_stay_within_the_library(runs):
    substituted = [p for p in runs[0] if p.notes_code == "substitution"]
    assert substituted, "no substitutions were generated"
    for plan in runs[0]:
        for prescription in plan.prescriptions:
            assert prescription.exercise_id in LIBRARY


def test_substitutions_preserve_the_region():
    """A swap must not turn a lower-body day into an upper-body one."""
    for source, targets in SUBSTITUTIONS.items():
        source_regions = LIBRARY[source].regions
        for target in targets:
            assert LIBRARY[target].regions & source_regions, (
                f"{source} -> {target} crosses regions"
            )


# --- templates and validation ----------------------------------------------

def test_every_template_exercise_exists_in_the_library():
    for session_type, rows in SESSION_TEMPLATES.items():
        for exercise_id, *_ in rows:
            assert exercise_id in LIBRARY, f"{session_type.value}: {exercise_id}"


def test_a_template_naming_an_unknown_exercise_is_rejected(monkeypatch):
    monkeypatch.setitem(
        SESSION_TEMPLATES, SessionType.UPPER_A, (("nonexistent_lift", 3, 5, 8, 2.0),)
    )
    with pytest.raises(ValueError, match="not in the exercise library"):
        _generator(0)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(sets=0, rep_low=5, rep_high=8, target_rir=2.0),
        dict(sets=3, rep_low=9, rep_high=5, target_rir=2.0),
        dict(sets=3, rep_low=5, rep_high=8, target_rir=-1.0),
    ],
)
def test_malformed_prescriptions_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Prescription(exercise_id="bench_press", **kwargs)


# --- determinism -----------------------------------------------------------

@pytest.mark.guardrail(4)
def test_programme_generation_is_deterministic():
    first = [(p.day_index, p.session_type, p.total_sets) for p in _plans(4, 200)]
    second = [(p.day_index, p.session_type, p.total_sets) for p in _plans(4, 200)]
    assert first == second


@pytest.mark.guardrail(4)
def test_different_seeds_give_different_schedules():
    assert [(p.day_index, p.total_sets) for p in _plans(1, 200)] != [
        (p.day_index, p.total_sets) for p in _plans(2, 200)
    ]
