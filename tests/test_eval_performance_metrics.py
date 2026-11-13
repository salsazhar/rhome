"""Performance and capacity scoring (``DATA.md`` §19.2, L3.3).

§19.2 calls one-step-ahead residuals the severe criterion. These tests cover
the scoring, and — following D20 and D19 — that each measure can fail, and that
none of them is confounded by something other than the model's skill.
"""

from __future__ import annotations

import pytest

from rhome_eval.performance_metrics import (
    APPROVED_ROBUSTNESS_LIMITS,
    LOCAL_CONTROL_DAYS,
    SETTLED_AFTER,
    ScenarioResponse,
    choose_capacity_candidate,
    score_accuracy_robustness,
    score_performance,
)
from rhome_eval.run import evaluate, run_engine
from rhome_eval.window import Window


@pytest.fixture(scope="module")
def days():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    return _days()


@pytest.fixture(scope="module")
def report(days):
    return score_performance(evaluate(days, Window.DEVELOPMENT))


# --- the severe criterion -----------------------------------------------------

@pytest.mark.spec("DATA:performance-scored")
def test_the_gate_is_that_the_engine_beats_recency_once_settled(report):
    """An engine that cannot beat a moving average has not earned its complexity."""
    assert report.beats_recency_when_settled
    rungs = {r.name: r for r in report.ladder_settled}
    assert rungs["median of last 3"].verdict == "engine better"
    assert rungs["last observation"].verdict == "engine better"
    assert rungs["mean of last 5"].verdict in ("tie", "engine better"), (
        "a five-set moving average is the strongest simple predictor here; "
        "losing to it would mean the model adds nothing"
    )


@pytest.mark.spec("DATA:performance-scored")
def test_residual_bias_is_reported_sliced_before_it_is_pooled(report):
    """A pooled mean of +0.0119 was two opposite biases meeting in the middle."""
    assert abs(report.bias) < 0.02
    assert len(report.drift) >= 5
    assert len(report.by_experience) >= 6

    early = report.by_experience[0][2]
    late = report.by_experience[-1][2]
    assert early > late, "the warm-up transient should still be visible, not hidden"
    assert abs(late) < 0.02


@pytest.mark.spec("DATA:performance-scored")
def test_calibration_is_reported_across_all_three_fatigue_channels(report):
    assert set(report.calibration) == {"local_fatigue", "neuromuscular", "systemic"}
    for name, bins in report.calibration.items():
        assert len(bins) == 4, name
        assert sum(b.count for b in bins) == report.n
        assert max(abs(b.mean_residual) for b in bins) < 0.05, (
            f"{name}: a large bias in one fatigue bin would mean the "
            f"suppression term is mis-scaled"
        )


def test_autocorrelation_is_reported_and_is_mostly_the_warm_up(report):
    """+0.274 across all sets, roughly halving once the warm-up is excluded."""
    assert report.autocorrelation is not None
    assert 0.0 < report.autocorrelation < 0.35


# --- capacity ------------------------------------------------------------------

@pytest.mark.spec("DATA:performance-scored")
def test_capacity_is_compared_after_one_global_scale(report):
    """Both sides are kilograms — of different things.

    The engine's capacity is whatever makes projections match observations; the
    simulator's is a neutral one-repetition capacity. A single scale across all
    exercises takes mean absolute error from about 11% to about 4.5%, and what
    survives is the part that is not definitional.
    """
    import statistics as st

    raw = st.fmean(abs(s.mean_relative_error) for s in report.capacity)
    aligned = st.fmean(abs(s.aligned_mean_error) for s in report.capacity)
    assert raw > aligned * 1.5, (
        "if the scale changes little, the offset was not definitional after all"
    )
    assert aligned < 0.08
    assert all(s.pearson is not None and s.pearson > 0.3 for s in report.capacity)


def test_the_scale_is_one_parameter_not_one_per_exercise(report):
    """Twenty-seven fitted scales would flatter every per-exercise figure."""
    signs = [s.aligned_mean_error > 0 for s in report.capacity]
    assert 0 < sum(signs) < len(signs), (
        "after a single global scale, errors must still spread either side of "
        "zero; all-positive or all-negative would mean the scale absorbed them"
    )


# --- scenario response ---------------------------------------------------------

@pytest.mark.spec("DATA:performance-scored")
def test_scenario_response_is_measured_against_a_local_control(report):
    """The global comparison was confounded by the time drift.

    Bias runs from +0.051 in the first hundred days to −0.014 in the last,
    while the high-volume block sits at days 70–91 and the illness block at
    370–375. Measured against a global mean, a scenario's "response" was mostly
    its position in the record: high volume read as WRONG WAY and became
    correct once controlled locally.
    """
    assert LOCAL_CONTROL_DAYS > 0
    labels = {s.label: s for s in report.scenarios}
    assert "S1_high_volume" in labels
    assert labels["S1_high_volume"].direction_correct is True
    assert labels["S3_deload"].direction_correct is True
    for scenario in report.scenarios:
        assert scenario.span[0] <= scenario.span[1]


def test_a_difference_inside_its_own_interval_is_not_a_verdict():
    """A bare sign test called four episodes wrong on differences of 0.003."""
    noise = ScenarioResponse(
        label="S9_plateau", days=200, mean_residual=0.0033,
        mean_residual_elsewhere=0.0, interval=0.0088,
    )
    assert noise.direction_correct is None
    assert noise.verdict == "no detectable difference"

    real = ScenarioResponse(
        label="S1_high_volume", days=88, mean_residual=-0.0223,
        mean_residual_elsewhere=0.0, interval=0.0142,
    )
    assert real.direction_correct is True


def test_at_least_the_two_largest_episodes_resolve(report):
    """If nothing resolves, the metric has no power and should say so."""
    resolved = [s for s in report.scenarios if s.direction_correct is not None]
    assert len(resolved) >= 2


# --- the open item from L3.2 ---------------------------------------------------

def test_the_clipping_cost_is_measured(report):
    """L3.2 left this: what does ρ sitting on a bound actually cost?"""
    clipped, free = report.rho_clipped_residual
    assert clipped is not None and free is not None
    assert abs(clipped - free) < 0.03, (
        "if clipped days carried a much larger residual, the bounds would be "
        "costing real accuracy and should be widened"
    )


def test_scoring_refuses_a_run_with_no_truth(days):
    with pytest.raises(ValueError, match="no truth attached"):
        score_performance(run_engine(days, Window.DEVELOPMENT))


def test_the_settled_threshold_is_the_measured_one():
    assert SETTLED_AFTER == 20


# --- S11 at session scale (Layer 3 audit, LIM-22) ----------------------------

@pytest.mark.spec("DATA:capacity-robust-to-one-bad-day")
@pytest.mark.spec("DATA:accuracy-robustness-gate")
def test_one_bad_session_passes_the_frozen_robustness_floor(days, report):
    """``DATA.md`` §19.7, measured on a session rather than on a single set.

    The repaired estimator aggregates the session's correlated set evidence
    once, then enforces explicit ordinary and anchor session caps. DATA.md
    v0.8.0 freezes v0's measured behaviour as the non-inferiority floor.
    """
    from rhome_eval.performance_metrics import (
        clip_bounded_displacement,
        single_bad_day_displacement,
    )

    measured = []
    settled_measured = []
    for exercise_id, day_index in (
        ("bench_press", 203), ("back_squat", 204), ("deadlift", 207),
        ("back_squat", 218), ("deadlift", 214),
    ):
        immediate, settled, eligible = single_bad_day_displacement(
            days, day_index, exercise_id
        )
        assert eligible >= 1, f"no eligible sets on day {day_index}; check is vacuous"

        # The anchor cap is the conservative bound whether or not this
        # particular session held an anchor.
        bound = clip_bounded_displacement(eligible, anchor=True)
        assert abs(immediate) <= bound + 1e-9, (
            f"{exercise_id} day {day_index}: moved {immediate:.3%} on {eligible} "
            f"eligible sets, beyond the session bound of {bound:.3%}."
        )
        assert abs(settled) < 0.005, (
            f"{exercise_id} day {day_index}: still displaced {settled:.3%} after "
            f"90 days. One session must not permanently depress capacity."
        )
        measured.append(abs(immediate))
        settled_measured.append(abs(settled))

    assert len(measured) == 5
    score = score_accuracy_robustness(
        "frozen v0", report.mae, measured, settled_measured
    )
    assert score.robustness_passes, score


@pytest.mark.spec("DATA:accuracy-robustness-gate")
def test_accuracy_cannot_buy_a_robustness_failure():
    stable = score_accuracy_robustness(
        "stable v0", 0.3152,
        [0.010, APPROVED_ROBUSTNESS_LIMITS.median_immediate,
         APPROVED_ROBUSTNESS_LIMITS.worst_immediate],
        [0.001, 0.002, 0.004],
    )
    fragile = score_accuracy_robustness(
        "fitted rate and clip", 0.1604, [0.522], [0.010]
    )

    assert stable.robustness_passes
    assert not fragile.robustness_passes
    assert choose_capacity_candidate((fragile, stable)) is stable


@pytest.mark.spec("DATA:capacity-robust-to-one-bad-day")
def test_the_response_to_a_bad_session_does_not_depend_on_how_bad_it_was(days):
    """The consequence of clipping, and the reason the 40% stand-in misled.

    Scenario S11's own magnitude is a median 13.9% shortfall. The stand-in used
    40%. Both innovations exceed the clip, so both are clipped to the same
    value and produce the same displacement — which means the stand-in's choice
    of severity was never doing anything, and a reader would reasonably have
    assumed a 40% miss was a harder test than the scenario.
    """
    from rhome_eval.performance_metrics import single_bad_day_displacement

    mild, _, _ = single_bad_day_displacement(days, 204, "back_squat", factor=0.861)
    severe, _, _ = single_bad_day_displacement(days, 204, "back_squat", factor=0.60)
    assert mild == pytest.approx(severe, abs=1e-9), (
        f"a 14% miss moved capacity {mild:.4%} and a 40% miss {severe:.4%}; if "
        f"these differ the clip is no longer binding and S11's severity matters"
    )


# --- the rest of DATA.md §19.7, registered at the Layer 3 audit ---------------
# §19.7 was the only subsection of §19 never entered in the conformance map, so
# coverage read 100% while five of its requirements went unregistered. These
# close four of the five; the S11 requirement above is the fifth.

@pytest.mark.spec("DATA:drop-segments-excluded-from-capacity")
def test_no_drop_or_clipped_high_rep_set_reaches_the_capacity_update(days):
    """§19.7, measured over the whole window rather than on one constructed set.

    ``DATA.md`` §5.3 calls the drop segments "a deliberate trap": they begin
    pre-fatigued, so an engine treating them as fresh would mis-estimate
    capacity. The unit test proves ``eligible_for_performance`` is False for a
    constructed drop. This proves none slipped through in 520 days of real
    sessions, which is the claim §19.7 actually makes.
    """
    from rhome_engine.session import RhomeEngine
    from rhome_core.exercises import load_library
    from rhome_core.intensity import IntensityConfidence

    results = RhomeEngine(load_library()).run(days[:520])

    drops = clipped = eligible_drops = eligible_clipped = 0
    for result in results:
        for logged, dose in result.doses:
            if logged.set_type == "drop":
                drops += 1
                eligible_drops += dose.eligible_for_performance
            if dose.intensity_confidence is IntensityConfidence.LOW:
                clipped += 1
                eligible_clipped += dose.eligible_for_performance

    assert drops > 50, f"only {drops} drop segments; the check is near-vacuous"
    assert clipped > 20, f"only {clipped} low-confidence sets; the check is near-vacuous"
    assert eligible_drops == 0, f"{eligible_drops} of {drops} drop segments were eligible"
    assert eligible_clipped == 0, (
        f"{eligible_clipped} of {clipped} sets whose relative intensity fell "
        f"outside the tabulated domain were eligible for performance"
    )


@pytest.mark.spec("DATA:capacity-flat-through-plateau")
def test_estimated_capacity_stays_flat_through_the_plateau(days):
    """§19.7: through S9 the engine must not extrapolate prior progress.

    S9 runs days 450-499, inside the development window. The existing plateau
    test is simulator-side — it checks that *true* capacity flattens. This is
    the engine-side half, which is what §19.7 asks: given a log in which the
    athlete stopped improving, the estimate must stop improving too.

    The comparison is against a period of genuine growth, not against the fifty
    days immediately before. A first version used days 400-449 as the reference
    and failed on its own guard, because the estimate was already flat there —
    it would have "shown" growth stopping in a window where there was none.
    """
    import statistics as st

    from rhome_core.exercises import load_library
    from rhome_engine.session import RhomeEngine

    results = RhomeEngine(load_library()).run(days[:520])

    def capacity_at(exercise_id: str, day: int) -> float | None:
        value = None
        for result in results[: day + 1]:
            for observation in result.observations:
                if observation.exercise_id == exercise_id:
                    value = observation.capacity_after
        return value

    lifts = ("bench_press", "back_squat", "deadlift", "overhead_press")
    growth, plateau = [], []
    for exercise_id in lifts:
        points = {d: capacity_at(exercise_id, d) for d in (100, 199, 450, 499)}
        assert all(v for v in points.values()), exercise_id
        # Per fifty days, so the two windows are commensurable.
        growth.append((points[199] / points[100] - 1) / 2.0)
        plateau.append(points[499] / points[450] - 1)

    growing = st.fmean(growth)
    flat = st.fmean(plateau)
    assert growing > 0.01, (
        f"the reference window grew only {growing:.2%} per fifty days; without "
        f"real growth to contrast against, this test cannot show growth stopping"
    )
    assert flat < growing, (
        f"capacity grew {flat:.2%} through the plateau against {growing:.2%} per "
        f"fifty days while the athlete was genuinely improving; the engine is "
        f"extrapolating prior progress"
    )
    assert abs(flat) < 0.02, f"capacity moved {flat:.2%} through a plateau"


@pytest.mark.spec("DATA:rebound-attributed-to-fatigue")
def test_the_deload_rebound_decomposes_exactly_and_is_measured_against_a_control(days):
    """§19.7, "verified by decomposing the projected change".

    Projected performance is ``capacity x (1 - suppression)``, so the change
    across a deload factors *exactly* into a capacity part and a fatigue part
    in log space. That exactness is asserted here because it is a hard
    constraint: if the two parts stop summing to the whole, the decomposition
    is describing a number the engine did not produce.

    What the decomposition then says is recorded rather than asserted as a
    pass, because it currently fails §19.7 — see LIM-23. Across a deload the
    engine moves capacity +1.16% against +0.37% over matched ordinary gaps, an
    excess of +0.79% +/- 0.24%, while the fatigue term contributes +0.34%. §19.7
    requires reduced fatigue to dominate; capacity dominates it by 3.4x.

    The control is the substance. A bare "capacity rose across the deload"
    proves nothing, since capacity rises across any three weeks of training —
    which is exactly how L3.4 got this metric wrong three times. Only the
    excess over a matched ordinary stretch is attributable to the deload.
    """
    import math
    import statistics as st

    from rhome_core.exercises import load_library
    from rhome_engine.session import RhomeEngine

    results = RhomeEngine(load_library()).run(days[:520])
    by_day = {r.day_index: r for r in results}

    def across(gap_start: int, gap_end: int, span: int = 8):
        before, after = {}, {}
        for day in range(gap_start - span, gap_start):
            for exercise_id, record in getattr(
                by_day.get(day), "projections", {}
            ).items():
                before[exercise_id] = (record, day)
        for day in range(gap_end, gap_end + span):
            for exercise_id, record in getattr(
                by_day.get(day), "projections", {}
            ).items():
                after.setdefault(exercise_id, (record, day))
        rows = []
        for exercise_id in before.keys() & after.keys():
            (first, first_day), (last, last_day) = before[exercise_id], after[exercise_id]
            if first.projected <= 0 or last.projected <= 0:
                continue
            total = math.log(last.projected) - math.log(first.projected)
            from_capacity = math.log(last.capacity) - math.log(first.capacity)
            from_fatigue = math.log(1 - last.suppression) - math.log(1 - first.suppression)
            assert total == pytest.approx(from_capacity + from_fatigue, abs=1e-9), (
                "projected = capacity x (1 - suppression), so the decomposition "
                "is exact by construction. If it is not, one of the three is "
                "not the number it claims to be."
            )
            rows.append((last_day - first_day, from_capacity, from_fatigue))
        return rows

    # S3 deload blocks wholly inside the development window.
    deload = across(92, 100) + across(180, 195)
    control = []
    for start in range(240, 460, 20):
        if any(abs(start - boundary) < 40 for boundary in (92, 180, 515)):
            continue
        control += across(start, start + 14)

    assert len(deload) > 20, f"only {len(deload)} deload pairs; the check is vacuous"
    assert len(control) > 100, f"only {len(control)} control pairs; the check is vacuous"

    deload_capacity = st.fmean(r[1] for r in deload)
    control_capacity = st.fmean(r[1] for r in control)
    deload_fatigue = st.fmean(r[2] for r in deload)

    excess = deload_capacity - control_capacity
    interval = 1.96 * math.sqrt(
        st.pvariance([r[1] for r in deload]) / len(deload)
        + st.pvariance([r[1] for r in control]) / len(control)
    )
    assert deload_fatigue > 0, (
        f"reduced fatigue contributed {deload_fatigue:+.4f} across a deload; a "
        f"rest week must not make the engine think the athlete is more fatigued"
    )
    # Pinned as the known state, so closing LIM-23 fails this and forces the
    # test to be re-pointed at §19.7's requirement rather than at the defect.
    assert excess > interval, (
        f"the deload no longer produces an excess capacity movement "
        f"({excess:+.4f} +/- {interval:.4f}). LIM-23 may be closed; re-point "
        f"this test at §19.7's requirement that fatigue dominate."
    )


@pytest.mark.spec("DATA:bodyweight-capacity-in-system-load")
def test_a_body_mass_change_moves_pullup_capacity_in_system_load_units(days):
    """§19.7's last requirement, and the one easiest to get backwards.

    A pull-up's system load is body mass plus any added weight. If the athlete
    gains 4 kg and keeps adding the same plates for the same repetitions, they
    are moving more total load — their *system-load* capacity has risen — but
    they are not stronger in any sense the user should be told about.

    The requirement is that the estimate move in system-load units, which is
    what makes the number meaningful, and that the movement track the mass
    change rather than being reported as a strength gain. Run twice over the
    same log with body mass shifted, and the difference must be the mass.
    """
    from dataclasses import replace

    from rhome_engine.session import RhomeEngine
    from rhome_core.exercises import load_library

    library = load_library()
    window = [d for d in days[:520]]
    heavier = [
        replace(d, body_mass_kg=None if d.body_mass_kg is None else d.body_mass_kg + 4.0)
        for d in window
    ]
    assert heavier != window, "the perturbation changed nothing"

    base = RhomeEngine(library)
    base.run(window)
    lifted = RhomeEngine(library)
    lifted.run(heavier)

    before = base.capacity.capacity("weighted_pullup")
    after = lifted.capacity.capacity("weighted_pullup")
    assert before and after, "no pull-up capacity established"

    moved = after - before
    assert moved > 0, (
        f"carrying 4 kg more body mass for the same repetitions did not raise "
        f"system-load capacity ({before:.2f} -> {after:.2f})"
    )
    assert 1.0 < moved < 6.0, (
        f"capacity moved {moved:.2f} kg for a 4 kg mass change. It should track "
        f"the mass in system-load units, not be amplified into a strength claim."
    )

    # And the same change must NOT move a barbell lift, which carries no body mass.
    bench_before = base.capacity.capacity("bench_press")
    bench_after = lifted.capacity.capacity("bench_press")
    assert bench_after == pytest.approx(bench_before, rel=1e-9), (
        "a body-mass change moved bench-press capacity; body mass must enter "
        "only where the exercise carries it"
    )
