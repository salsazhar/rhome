"""The day loop (``DATA.md`` §9.5).

Runs the engine end to end over the development window and checks it against
the simulator's latent truth. This is the first stage where the engine's parts
are exercised together, which is where ordering errors live: L2.2's
activity-window bug was invisible until the engine ran over real data.
"""

from __future__ import annotations

import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from rhome_core.exercises import load_library
from rhome_engine.dose import LoggedSet
from rhome_engine.ingest import load_sets
from rhome_engine.performance import LeakageError
from rhome_engine.recovery import RecoveryReading
from rhome_engine.session import DayInput, RhomeEngine

LIBRARY = load_library()
DATASET = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "athlete_a"
DEVELOPMENT_DAYS = 520

pytestmark = pytest.mark.skipif(
    not (DATASET / "observable" / "sets.csv").exists(), reason="dataset not generated"
)


def _number(value):
    return float(value) if value not in ("", None, "None") else None


def _days() -> list[DayInput]:
    sets = load_sets(DATASET / "observable" / "sets.csv", LIBRARY).sets
    with (DATASET / "observable" / "workouts.csv").open(encoding="utf-8") as handle:
        workouts = {w["workout_id"]: w for w in csv.DictReader(handle)}
    with (DATASET / "observable" / "daily_recovery.csv").open(encoding="utf-8") as handle:
        daily = list(csv.DictReader(handle))
    with (DATASET / "observable" / "performance_tests.csv").open(encoding="utf-8") as handle:
        anchors = defaultdict(set)
        for row in csv.DictReader(handle):
            anchors[row["date"]].add(row["exercise_id"])

    index = {row["date"]: i for i, row in enumerate(daily)}
    by_day = defaultdict(list)
    for performed in sets:
        by_day[index[workouts[performed.workout_id]["date"]]].append(performed)

    return [
        DayInput(
            day_index=i,
            reading=RecoveryReading(
                _number(row["hrv_rmssd_ms"]), _number(row["resting_hr_bpm"]),
                _number(row["total_sleep_min"]), _number(row["sleep_efficiency"]),
                _number(row["temperature_deviation_c"]),
            ),
            # sets.csv is written in performed session order. Preserve it;
            # alphabetical exercise order is not a valid substitute once the
            # model uses observable within-session position.
            sets=list(by_day.get(i, [])),
            body_mass_kg=_number(row["bodyweight_kg"]),
            steps=_number(row["steps"]),
            anchor_exercise_ids=frozenset(anchors.get(row["date"], set())),
        )
        for i, row in enumerate(daily)
    ]


@pytest.fixture(scope="module")
def run():
    days = _days()
    engine = RhomeEngine(LIBRARY)
    return engine, engine.run(days[:DEVELOPMENT_DAYS])


@pytest.fixture(scope="module")
def truth():
    """Latent capacity, recovered from the simulator's own records.

    The realised value carries capacity, the fatigue acting at the time *and*
    the set's own stochastic shock. All three come out. Dividing by the fatigue
    factor alone — which this did until the Layer 3 audit, here and in
    ``rhome_eval.run`` — leaves a target that varies by 5% between the sets of
    one afternoon, which is not a capacity.
    """
    from rhome_sim.generate import simulate

    simulation = simulate(20260822)
    capacity = defaultdict(dict)
    for day in simulation.days[:DEVELOPMENT_DAYS]:
        for performed in day.sets:
            if performed.fatigue_factor > 0 and performed.performance_shock > 0:
                capacity[performed.exercise_id].setdefault(
                    day.day_index,
                    performed.true_expressible_capacity
                    / performed.performance_shock
                    / performed.fatigue_factor,
                )
    return simulation, capacity


# --- the loop runs (DATA.md §9.5) ------------------------------------------

@pytest.mark.spec("DATA:session-ordering-enforced")
def test_the_development_window_processes_without_a_leakage_error(run):
    engine, results = run
    assert len(results) == DEVELOPMENT_DAYS
    assert sum(1 for r in results if r.trained) > 300
    assert sum(len(r.projections) for r in results) > 1500
    assert sum(len(r.observations) for r in results) > 1500


@pytest.mark.guardrail(2)
@pytest.mark.spec("DATA:session-ordering-enforced")
def test_scoring_a_session_that_was_never_frozen_is_refused():
    """The guardrail, exercised by a caller that gets the order wrong."""
    engine = RhomeEngine(LIBRARY)
    for index in range(3):
        engine.capacity.update_capacity(
            LIBRARY["bench_press"], f"warm{index}", 120.0, engine.state_engine.state
        )
    assert engine.capacity.capacity("bench_press") is not None
    with pytest.raises(LeakageError):
        engine.capacity.score_against_projection(LIBRARY["bench_press"], "never_frozen", 130.0)


@pytest.mark.guardrail(2)
def test_every_scored_observation_had_its_projection_frozen_first(run):
    engine, results = run
    for result in results:
        for observation in result.observations:
            record = engine.capacity.frozen(observation.exercise_id, observation.session_key)
            assert record is not None
            assert record.verify(), "a projection was altered after sealing"
            assert record.frozen_at_h <= result.state.t_h


# --- against the simulator's truth -----------------------------------------

def test_estimated_capacity_lands_near_the_truth(run, truth):
    """The first evidence the engine works at all."""
    engine, _ = run
    _, capacity = truth

    errors = {}
    for exercise_id in ("bench_press", "back_squat", "deadlift", "overhead_press"):
        final_day = max(capacity[exercise_id])
        true_value = capacity[exercise_id][final_day]
        estimate = engine.capacity.capacity(exercise_id)
        errors[exercise_id] = estimate / true_value - 1

    assert all(abs(e) < 0.12 for e in errors.values()), errors
    assert st.mean(abs(e) for e in errors.values()) < 0.06


@pytest.mark.spec("DATA:session-ordering-enforced")
def test_one_step_ahead_residuals_are_approximately_unbiased(run):
    """``DATA.md`` §19.2 calls this the severe criterion.

    An earlier version of the driver scored the *best* set of each session
    against a single pre-session projection. A maximum over several noisy draws
    is high by construction, and it inflated the mean residual to +0.058. The
    first eligible set is what the projection was a claim about.
    """
    _, results = run
    residuals = [o.log_residual for r in results for o in r.observations]
    assert len(residuals) > 1500
    assert abs(st.mean(residuals)) < 0.03, f"mean residual {st.mean(residuals):+.4f}"
    assert st.pstdev(residuals) < 0.12


def test_the_engine_tracks_latent_fatigue_and_recovery(run, truth):
    """Correlation against states the engine was never given.

    The pairing matters and was wrong here until L3.1: the engine's day-N state
    is the close of day N, while the simulator records its latent state on
    waking. Comparing them index for index compares states sixteen hours apart
    across a training session, which read as +0.450 where the answer is +0.949.
    ``rhome_eval`` owns this comparison now; what remains here is a floor, so
    the engine test fails if tracking collapses.
    """
    _, results = run
    simulation, _ = truth
    latent = {d.day_index: d for d in simulation.days}

    engine_fatigue, true_fatigue, engine_rho, true_rho = [], [], [], []
    for result in results[:-1]:
        following = latent[result.day_index + 1]
        engine_fatigue.append(st.mean(result.state.local_fatigue.values()))
        true_fatigue.append(
            st.mean(following.state_on_waking.local_fatigue(m)
                    for m in result.state.local_fatigue)
        )
        engine_rho.append(result.recovery.rho)
        true_rho.append(latent[result.day_index].latent.recovery_propensity)

    assert float(np.corrcoef(engine_fatigue, true_fatigue)[0, 1]) > 0.85
    assert float(np.corrcoef(engine_rho, true_rho)[0, 1]) > 0.50


def test_capacity_error_reflects_the_bounded_update_rather_than_a_defect(run, truth):
    """The engine lags a fast-growing capacity, by design.

    Bounded influence is what stops one bad session rewriting the estimate
    (scenario S11), and lagging genuine change is its price. Recording the
    relationship here keeps it a known trade-off rather than a mystery, and
    L3.3 quantifies it properly.
    """
    engine, _ = run
    _, capacity = truth

    growth, error = [], []
    for exercise_id in ("bench_press", "back_squat", "deadlift",
                        "overhead_press", "weighted_pullup", "leg_press"):
        days = sorted(capacity[exercise_id])
        first, last = capacity[exercise_id][days[0]], capacity[exercise_id][days[-1]]
        growth.append(last / first - 1)
        error.append(engine.capacity.capacity(exercise_id) / last - 1)

    assert float(np.corrcoef(growth, error)[0, 1]) < -0.5, (
        "faster true growth should leave the estimate further behind"
    )


# --- ordering details ------------------------------------------------------

@pytest.mark.spec("MODEL:session-level-capacity-update")
def test_capacity_counts_every_eligible_set_as_session_evidence(run):
    engine, results = run
    eligible = sum(
        1 for r in results for logged, dose in r.doses if dose.eligible_for_performance
    )
    evidence = sum(engine.capacity.observations(e.exercise_id) for e in LIBRARY)
    assert evidence > len(results), "capacity sees less evidence than once a day"
    assert evidence > 0.5 * eligible, (
        f"{evidence} recorded evidence sets from {eligible} eligible sets"
    )


def test_the_recovery_multiplier_is_applied_from_waking(run):
    engine, results = run
    windows = engine.timeline.windows
    assert len(windows) == len(results)
    for index, window in enumerate(windows):
        assert window.start_h == pytest.approx(index * 24.0 + 7.5)


def test_a_rest_day_still_advances_state_and_records_context(run):
    _, results = run
    rest = [r for r in results if not r.trained]
    assert rest
    for result in rest[:20]:
        assert result.recovery.rho > 0
        assert not result.projections


def test_days_without_wearable_data_leave_the_multiplier_neutral(run):
    _, results = run
    blank = [r for r in results if r.recovery.channels_present == 0]
    assert blank, "the dataset should contain fully missing nights"
    for result in blank:
        assert result.recovery.rho == pytest.approx(1.0)


def test_the_observation_record_reports_the_capacity_change_it_caused(run):
    """``capacity_after`` is written once the whole session has been learned from.

    An earlier version filled both capacity fields with the same value and a
    learning rate of zero, so every record claimed the session had changed
    nothing. L2.7 reads these fields to explain a projection, and a record that
    is quietly false is worse than an absent one.
    """
    _, results = run
    records = [o for r in results for o in r.observations]
    moved = [o for o in records if o.capacity_after != o.capacity_before]
    assert len(moved) > 0.9 * len(records), "capacity is barely moving"
    assert all(o.learning_rate > 0 for o in records)
    assert any(o.is_anchor for o in records)
    for o in records[:200]:
        assert o.projected > 0 and o.observed > 0
        assert o.log_residual == pytest.approx(np.log(o.observed / o.projected), abs=1e-9)
