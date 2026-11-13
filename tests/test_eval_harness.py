"""The evaluation harness (``DATA.md`` §19, L3.1).

``rhome_eval`` is the only package permitted to see both the engine's estimates
and the simulator's truth, so it is also the last place the discipline of the
whole build can quietly fail. These tests cover the mechanics of the harness
and the three protections built into it: the ordering, the frozen alignment,
and the seal on the holdout.
"""

from __future__ import annotations

import math

import pytest

from rhome_core.muscles import Muscle
from rhome_eval import metrics as m
from rhome_eval.alignment import AlignmentError, ScaleAlignment, fit_alignment
from rhome_eval.baselines import Prediction, ablation_ladder
from rhome_eval.run import (
    CHANNELS,
    LATENT_OFFSET_DAYS,
    attach_truth,
    evaluate,
    run_engine,
)
from rhome_eval.window import HoldoutSeal, SealError, Window, open_holdout

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def days():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    return _days()


@pytest.fixture(scope="module")
def run(days):
    return evaluate(days, Window.DEVELOPMENT)


class _StubDay:
    """The smallest thing ``latent_series`` will read, for seal tests."""

    def __init__(self, day_index: int) -> None:
        self.day_index = day_index
        self.sets = ()
        self.scenario_labels = ()
        self.latent = type("L", (), {"recovery_propensity": 1.0})()
        self.state_on_waking = type(
            "S", (), {
                "local_fatigue": staticmethod(lambda muscle: 0.5),
                "neuromuscular": 0.3,
                "systemic": 0.4,
            },
        )()


def _stub_simulation(window: Window):
    return type("Sim", (), {"days": [_StubDay(d) for d in window.days]})()


def _stub_run(window: Window):
    """An EvaluationRun with engine results faked, so no sealed day is processed."""
    from rhome_eval.run import EvaluationRun

    class _Result:
        def __init__(self, day_index: int) -> None:
            self.day_index = day_index
            self.observations = ()
            self.state = type(
                "St", (), {
                    "local_fatigue": {mu: 0.4 for mu in Muscle},
                    "neuromuscular": 0.25,
                    "systemic": 0.35,
                },
            )()

    return EvaluationRun(
        window=window,
        results=tuple(_Result(d) for d in window.days),
        library=None,
        engine=None,
    )


# --- metric primitives, checked against hand-known answers -------------------

def test_the_primitives_agree_with_cases_computed_by_hand():
    straight = list(range(12))
    assert m.pearson(straight, straight) == pytest.approx(1.0)
    assert m.pearson(straight, [-v for v in straight]) == pytest.approx(-1.0)
    assert m.spearman(straight, [v ** 3 for v in straight]) == pytest.approx(1.0)
    assert m.rmse([1, 2, 3, 4, 5, 6, 7, 8], [2, 3, 4, 5, 6, 7, 8, 9]) == pytest.approx(1.0)
    assert m.mae([1, -1] * 5) == pytest.approx(1.0)
    assert m.bias([1, -1] * 5) == pytest.approx(0.0)


def test_a_metric_refuses_a_sample_too_small_to_mean_anything():
    """The vacuous-pass failure this project has now found three times."""
    assert m.pearson([1, 2, 3], [1, 2, 3]) is None
    assert m.mae([0.1, 0.2]) is None
    assert m.autocorrelation([1.0, 2.0, 3.0]) is None
    assert m.calibration_bins([0.1] * 10, [1.0] * 10) == ()


def test_directional_accuracy_ignores_days_where_nothing_moved():
    """A channel that never moves would otherwise score perfectly."""
    flat = [5.0] * 12
    assert m.directional_accuracy(flat, list(range(12))) is None

    rising = [0, 1, 2, 1, 0, 1, 2, 3, 2, 1, 2, 3]
    assert m.directional_accuracy(rising, rising) == pytest.approx(1.0)
    assert m.directional_accuracy(rising, [-v for v in rising]) == pytest.approx(0.0)


def test_spearman_handles_ties_without_distortion():
    assert m.spearman([1, 1, 2, 2, 3, 3, 4, 4], [1, 1, 2, 2, 3, 3, 4, 4]) == pytest.approx(1.0)


def test_drift_by_block_finds_a_bias_a_pooled_mean_hides():
    """The shape Checkpoint 2 found: two opposite biases meeting in the middle."""
    residuals = [0.05] * 50 + [-0.05] * 50
    days = list(range(50)) + list(range(100, 150))
    assert m.bias(residuals) == pytest.approx(0.0)

    blocks = m.drift_by_block(residuals, days)
    assert len(blocks) == 2
    assert blocks[0][2] == pytest.approx(0.05)
    assert blocks[1][2] == pytest.approx(-0.05)


def test_calibration_bins_split_the_sample_evenly():
    residuals = [0.01 * i for i in range(80)]
    conditioner = list(range(80))
    bins = m.calibration_bins(residuals, conditioner, bins=4)
    assert len(bins) == 4
    assert sum(b.count for b in bins) == 80
    assert [b.mean_residual for b in bins] == sorted(b.mean_residual for b in bins)


# --- the waking offset -------------------------------------------------------

def test_the_latent_offset_is_applied_and_matters(run):
    """The harness's first finding, kept as a test.

    The engine's day-N state is the close of day N; the simulator records its
    latent state on waking, before that day's training. Pairing them index for
    index compares states sixteen hours apart across a session, and inverts the
    day-to-day differences almost perfectly — directional accuracy came out at
    43%, below chance, which is what gave it away.
    """
    assert LATENT_OFFSET_DAYS == 1
    for channel in CHANNELS:
        paired = m.pearson(run.aligned(channel), run.truth.channel(channel))
        unpaired = m.pearson(
            run.estimated(channel, paired=False), run.truth.channel(channel, paired=False)
        )
        assert paired > 0.90, f"{channel}: {paired:.3f}"
        assert paired - unpaired > 0.4, f"{channel} barely changed; is the offset applied?"

    for channel in CHANNELS:
        assert m.directional_accuracy(
            run.aligned(channel), run.truth.channel(channel)
        ) > 0.85


def test_paired_series_are_the_same_length(run):
    for channel in CHANNELS:
        assert len(run.estimated(channel)) == len(run.truth.channel(channel))
        assert len(run.estimated(channel, paired=False)) == len(run.days)
    assert len(run.estimated_muscle(Muscle.CHEST)) == len(run.truth.muscle(Muscle.CHEST))


# --- scale alignment ---------------------------------------------------------

def test_alignment_is_a_scale_through_the_origin():
    """An intercept would absorb a constant error the evaluation must report."""
    alignment = fit_alignment({"x": [1.0, 2.0, 3.0, 4.0]}, {"x": [2.0, 4.0, 6.0, 8.0]})
    assert alignment.scales["x"] == pytest.approx(2.0)

    offset = fit_alignment({"x": [1.0, 2.0, 3.0, 4.0]}, {"x": [3.0, 5.0, 7.0, 9.0]})
    assert offset.scales["x"] != pytest.approx(2.0), (
        "a constant offset must not be absorbed into the scale as though it fitted"
    )


@pytest.mark.spec("DATA:scale-alignment-frozen")
def test_an_alignment_is_content_addressed(run):
    assert run.alignment.verify()
    tampered = ScaleAlignment(
        scales={**run.alignment.scales, "systemic": 99.0},
        fitted_on=run.alignment.fitted_on,
        n_points=run.alignment.n_points,
        digest=run.alignment.digest,
    )
    assert not tampered.verify()


def test_a_channel_with_no_signal_cannot_be_aligned():
    with pytest.raises(AlignmentError):
        fit_alignment({"x": [0.0] * 8}, {"x": [1.0] * 8})
    with pytest.raises(AlignmentError):
        fit_alignment({"x": [1.0] * 8}, {"y": [1.0] * 8})


def test_applying_an_unfitted_channel_is_refused(run):
    with pytest.raises(AlignmentError):
        run.alignment.apply("no_such_channel", [1.0])


# --- the ordering ------------------------------------------------------------

@pytest.mark.spec("DATA:evaluation-through-dedicated-code")
def test_the_engine_runs_before_any_truth_is_read(days):
    """Split into two calls so the ordering is visible, not merely intended."""
    bare = run_engine(days, Window.DEVELOPMENT)
    assert bare.truth is None
    assert bare.alignment is None
    assert len(bare.results) == len(Window.DEVELOPMENT.days)
    with pytest.raises(ValueError):
        bare.aligned("systemic")

    from rhome_sim.generate import simulate

    attached = attach_truth(bare, simulate(20260822))
    assert attached.truth is not None
    assert attached.alignment.verify()


def test_a_development_run_says_so(run):
    assert "development" in run.caveat
    assert "built against this data" in run.caveat


# --- the holdout seal --------------------------------------------------------

def test_opening_the_holdout_requires_a_stated_reason():
    with pytest.raises(SealError):
        open_holdout("", record=False)
    with pytest.raises(SealError):
        open_holdout("   ", record=False)


def test_the_holdout_cannot_be_evaluated_without_being_opened(days):
    """It is opened once, deliberately, and the opening is recorded."""
    seal = open_holdout("unit test", record=False)
    assert seal.count >= 1
    assert "unit test" in seal.reasons


def test_a_reopened_holdout_reports_itself_as_weaker():
    once = HoldoutSeal(openings=("2026-08-23T00:00:00+00:00",), reasons=("first",))
    twice = HoldoutSeal(
        openings=("2026-08-23T00:00:00+00:00", "2026-09-01T00:00:00+00:00"),
        reasons=("first", "second"),
    )
    assert once.is_first and "opened once" in once.note()
    assert not twice.is_first
    assert "weaker claim" in twice.note()


def test_running_the_holdout_without_opening_it_is_refused(days):
    """The guard sits on ``run_engine``, not only on the convenience wrapper.

    It did not, at first. Two tests in this file promptly ran the engine across
    the holdout to exercise an unrelated code path — a harness leaking its own
    holdout through its test suite. A guard that covers only the polite entry
    point is not a guard.
    """
    with pytest.raises(SealError, match="sealed"):
        run_engine(days, Window.HOLDOUT)


def test_the_holdout_refuses_an_alignment_fitted_on_itself():
    """Fitting a nuisance parameter on the test set is the failure it exists to stop.

    Exercised on a hand-built run rather than by processing holdout days, so
    the test costs nothing from the seal it is testing.
    """
    run = _stub_run(Window.HOLDOUT)
    with pytest.raises(ValueError, match="tune a parameter on the test set"):
        attach_truth(run, _stub_simulation(Window.HOLDOUT))


@pytest.mark.spec("DATA:scale-alignment-frozen")
def test_a_development_alignment_transfers_to_a_sealed_window(run):
    stub = _stub_run(Window.HOLDOUT)
    attached = attach_truth(stub, _stub_simulation(Window.HOLDOUT), run.alignment)
    assert attached.alignment.digest == run.alignment.digest
    assert attached.alignment.fitted_on == "development"


# --- the ablation ladder -----------------------------------------------------

@pytest.mark.spec("PRODUCT:ablation-ladder")
def test_the_ladder_scores_every_predictor_on_the_same_sets(run):
    rungs = ablation_ladder(run.predictions())
    assert len(rungs) >= 4
    assert rungs[0].name == "engine"
    assert len({r.n for r in rungs}) == 1, "the sample must be matched across predictors"
    assert all(r.mae > 0 for r in rungs)


def test_the_ladder_reports_which_predictor_actually_won(run):
    rungs = {r.name: r for r in ablation_ladder(run.predictions())}
    assert rungs["engine"].verdict == "reference"
    assert rungs["last observation"].verdict == "engine better"
    for rung in rungs.values():
        if rung.versus_engine is not None:
            assert rung.interval > 0


@pytest.mark.spec("PRODUCT:ablation-ladder")
def test_the_ladder_answer_depends_on_how_much_history_the_engine_had(run):
    """Reporting only the pooled figure reports half a result."""
    pooled = {r.name: r for r in ablation_ladder(run.predictions())}
    settled = {r.name: r for r in ablation_ladder(run.predictions(), minimum_prior=20)}

    assert settled["engine"].mae < pooled["engine"].mae
    assert settled["engine"].n < pooled["engine"].n
    assert settled["median of last 3"].verdict == "engine better"


def test_a_perfect_predictor_beats_every_baseline():
    predictions = [
        Prediction("bench", day, observed=100.0 + day, projected=100.0 + day,
                   prior_observations=day)
        for day in range(60)
    ]
    rungs = {r.name: r for r in ablation_ladder(predictions)}
    assert rungs["engine"].mae == pytest.approx(0.0, abs=1e-12)
    assert all(r.verdict == "engine better" for r in rungs.values() if r.name != "engine")


# --- state baselines (the same lesson as the ablation ladder, one stage later)

@pytest.mark.spec("DATA:state-baselines-reported")
def test_a_decaying_set_count_nearly_matches_the_engine_on_aggregate_channels(run, days):
    """The check that stopped a good number being over-read.

    Corrected for the pairing error, the engine's aggregate channels correlate
    +0.95 with latent truth — which reads as a strong result until a decaying
    count of working sets, knowing nothing about exercise, repetitions, effort,
    muscles or recovery context, scores +0.91 on the same series.

    Almost all of it is "did you train recently, and how much". Both series are
    driven by the same training log, so a high correlation of levels is close to
    free.
    """
    from rhome_eval.state_baselines import compare_to_baselines

    window_days = [d for d in days if d.day_index in Window.DEVELOPMENT.days]
    for channel in CHANNELS:
        comparison = compare_to_baselines(
            channel, run.aligned(channel), run.truth.channel(channel), window_days
        )
        best = comparison.best_baseline
        assert best is not None
        assert best[1] > 0.85, (
            f"{channel}: the counter scores {best[1]:+.3f}; if this ever falls, "
            f"the point of this test has changed"
        )
        assert comparison.advantage < 0.15, (
            f"{channel}: the engine's aggregate advantage is only "
            f"{comparison.advantage:+.3f}, and reporting the raw correlation "
            f"without that context overstates it"
        )


@pytest.mark.spec("DATA:state-baselines-reported")
def test_the_engine_earns_its_keep_on_per_muscle_attribution(run, days):
    """Where the structure actually shows.

    A global counter has no way to tell chest from quadriceps, so it must give
    every muscle the same series. Per model muscle group it collapses; the
    engine does not. This is also what the product displays — the body map is
    per muscle, not an aggregate.
    """
    from rhome_eval.state_baselines import decaying_count

    window_days = [d for d in days if d.day_index in Window.DEVELOPMENT.days]
    counter = decaying_count([
        sum(1 for s in d.sets if s.set_type in ("working", "backoff"))
        for d in window_days
    ])
    counter = counter[:-1]

    engine_scores, counter_scores = [], []
    for muscle in Muscle:
        engine_scores.append(m.pearson(run.estimated_muscle(muscle), run.truth.muscle(muscle)))
        counter_scores.append(m.pearson(counter, run.truth.muscle(muscle)))

    engine_mean = sum(engine_scores) / len(engine_scores)
    counter_mean = sum(counter_scores) / len(counter_scores)

    assert engine_mean > 0.90, f"per-muscle mean {engine_mean:+.3f}"
    assert counter_mean < 0.70, f"the counter should collapse here, got {counter_mean:+.3f}"
    assert engine_mean - counter_mean > 0.30
    assert min(engine_scores) > 0.85, "no muscle should be badly tracked"


def test_a_baseline_needs_its_half_life_to_be_right():
    """The counter is not free of assumptions; it has exactly one."""
    from rhome_eval.state_baselines import decaying_count

    impulses = [1.0] + [0.0] * 10
    fast = decaying_count(impulses, half_life_h=8.0)
    slow = decaying_count(impulses, half_life_h=120.0)
    assert fast[3] < slow[3]
    assert fast[0] == slow[0] == pytest.approx(1.0)

    with pytest.raises(ValueError):
        decaying_count(impulses, half_life_h=0.0)


# --- the target itself (Layer 3 audit) ---------------------------------------

@pytest.mark.spec("DATA:performance-scored")
def test_the_capacity_target_is_constant_within_a_day(days):
    """A metric with a hard floor, aimed at the harness rather than the engine.

    ``DATA.md`` §19.2 scores estimated capacity against "the simulator's true
    neutral capacity". Neutral capacity cannot change between the first and
    last set of one afternoon, so its within-day spread is a check that needs
    no interpretation: any spread at all means the target carries something
    that is not capacity.

    It carried the per-set stochastic shock until the Layer 3 audit. The spread
    was 5.12% at the median and 24.31% at worst, and the §19.2 correlation read
    +0.690 where it is +0.973. Nothing else noticed, because the shock is
    roughly symmetric: it destroys a correlation without moving a mean, and
    every check in place looked at the mean.

    D19 is the lesson being encoded, not the arithmetic. The reason this test
    can be trusted where a threshold could not is that zero spread is the only
    defensible value, so there is no number to argue about.
    """
    from rhome_sim.generate import simulate

    from rhome_eval.run import latent_series

    truth = latent_series(simulate(20260822), Window.DEVELOPMENT)

    # The series is one value per (exercise, day), so rebuild the per-set view
    # it was reduced from and check every set of a day agrees with it.
    simulation = simulate(20260822)
    spreads: list[float] = []
    checked = 0
    for day in simulation.days[:520]:
        by_exercise: dict[str, list[float]] = {}
        for performed in day.sets:
            if performed.fatigue_factor > 0 and performed.performance_shock > 0:
                by_exercise.setdefault(performed.exercise_id, []).append(
                    performed.true_expressible_capacity
                    / performed.performance_shock
                    / performed.fatigue_factor
                )
        for exercise_id, values in by_exercise.items():
            if len(values) < 2 or max(values) <= 0:
                continue
            checked += 1
            spreads.append((max(values) - min(values)) / max(values))
            # ...and the reduced series must be one of them, not a fresh draw.
            assert truth.capacity[exercise_id][day.day_index] == pytest.approx(
                values[0], rel=1e-9
            )

    assert checked > 500, f"only {checked} multi-set cells; the check is vacuous"
    worst = max(spreads)
    assert worst < 1e-3, (
        f"true neutral capacity varies by {worst:.4%} within a single day across "
        f"{checked} cells. It cannot. Something that is not capacity is in the "
        f"target — the per-set performance_shock, when this last failed."
    )


@pytest.mark.spec("DATA:performance-scored")
def test_expressible_keeps_the_fatigue_factor_and_drops_only_the_shock(days):
    """The other half of the same fix, and the one easy to overcorrect.

    ``expressible`` is capacity *after* the fatigue acting at the time, so the
    fatigue factor must stay. Dividing it out as well would compare a
    performance gain against a neutral-capacity gain, which is precisely the
    measurement error L3.4 recorded as its second of three.
    """
    from rhome_sim.generate import simulate

    from rhome_eval.run import latent_series

    simulation = simulate(20260822)
    truth = latent_series(simulation, Window.DEVELOPMENT)

    compared = 0
    for day in simulation.days[:520]:
        for performed in day.sets:
            if performed.fatigue_factor <= 0 or performed.performance_shock <= 0:
                continue
            expressible = truth.expressible[performed.exercise_id].get(day.day_index)
            capacity = truth.capacity[performed.exercise_id].get(day.day_index)
            if expressible is None or capacity is None:
                continue
            compared += 1
            assert expressible == pytest.approx(
                capacity * performed.fatigue_factor, rel=1e-9
            ), "expressible must be neutral capacity times the fatigue factor"
            break

    assert compared > 300, f"only {compared} days compared; the check is vacuous"
