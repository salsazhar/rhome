"""Performance prediction and capacity reconstruction (``DATA.md`` §19.2).

The section calls one-step-ahead residuals the severe criterion: *a model that
fits historical observations but has biased or poor one-step-ahead residuals
fails this criterion.* This module computes them, and everything §19.2 asks to
be computed alongside them.

Three things it does that a naive scoring pass would not.

**Capacity is compared after one global scale.** The first version of this
module asserted that no alignment was needed because both sides are kilograms.
They are kilograms of different things: the engine's capacity is whatever makes
its projections match observations, while the simulator's is a neutral
one-repetition capacity. A single scale fitted across all exercises — one
parameter, not one per exercise — takes the mean absolute error from 11.06% to
4.55%, which is the measure of how much of the gap was definitional. What
survives it is reported, because that part is not.

**Residuals are sliced before they are pooled.** Checkpoint 2 found a pooled
mean of +0.0119 that was two opposite biases meeting in the middle, so bias is
reported by fatigue bin, by time block, and by how much history the engine had
of the exercise. The pooled figure is printed last, not first.

**Every figure arrives with the ablation ladder.** D20.
"""

from __future__ import annotations

import math
import statistics as st
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from rhome_eval import metrics as m
from rhome_eval.baselines import LadderRung, ablation_ladder
from rhome_eval.run import EvaluationRun

__all__ = [
    "AccuracyRobustnessScore",
    "CapacityScore",
    "RobustnessLimits",
    "ScenarioResponse",
    "PerformanceReport",
    "APPROVED_ROBUSTNESS_LIMITS",
    "choose_capacity_candidate",
    "score_performance",
    "score_accuracy_robustness",
    "single_bad_day_displacement",
    "clip_bounded_displacement",
]

#: Prior observations of an exercise beyond which the engine is treated as
#: settled. Measured, not assumed: the drift investigation found the engine
#: does not beat a recency baseline below roughly twenty.
SETTLED_AFTER = 20


@dataclass(frozen=True)
class RobustnessLimits:
    """The athlete-approved S11 non-inferiority floor (DATA.md v0.8.0)."""

    median_immediate: float
    worst_immediate: float
    worst_after_90_days: float


APPROVED_ROBUSTNESS_LIMITS = RobustnessLimits(
    median_immediate=0.021,
    worst_immediate=0.033,
    worst_after_90_days=0.005,
)


@dataclass(frozen=True)
class AccuracyRobustnessScore:
    """One candidate scored on both sides of the lexicographic gate."""

    name: str
    mae: float
    median_immediate: float
    worst_immediate: float
    worst_after_90_days: float
    limits: RobustnessLimits = APPROVED_ROBUSTNESS_LIMITS

    @property
    def robustness_passes(self) -> bool:
        return (
            self.median_immediate <= self.limits.median_immediate
            and self.worst_immediate <= self.limits.worst_immediate
            and self.worst_after_90_days < self.limits.worst_after_90_days
        )


def score_accuracy_robustness(
    name: str,
    mae: float,
    immediate_displacements: Sequence[float],
    displacements_after_90_days: Sequence[float],
    *,
    limits: RobustnessLimits = APPROVED_ROBUSTNESS_LIMITS,
) -> AccuracyRobustnessScore:
    """Score a candidate without allowing accuracy to average away fragility."""
    if not name:
        raise ValueError("candidate name must not be empty")
    if not math.isfinite(mae) or mae < 0:
        raise ValueError("candidate MAE must be finite and non-negative")
    if not immediate_displacements or not displacements_after_90_days:
        raise ValueError("the S11 battery must contain immediate and 90-day results")

    immediate = [abs(value) for value in immediate_displacements]
    later = [abs(value) for value in displacements_after_90_days]
    if not all(math.isfinite(value) for value in (*immediate, *later)):
        raise ValueError("S11 displacements must be finite")
    return AccuracyRobustnessScore(
        name=name,
        mae=mae,
        median_immediate=st.median(immediate),
        worst_immediate=max(immediate),
        worst_after_90_days=max(later),
        limits=limits,
    )


def choose_capacity_candidate(
    candidates: Sequence[AccuracyRobustnessScore],
) -> AccuracyRobustnessScore:
    """Return the most accurate *eligible* candidate, never the fragile one."""
    eligible = [candidate for candidate in candidates if candidate.robustness_passes]
    if not eligible:
        raise ValueError("no capacity-estimator candidate passes the robustness gate")
    return min(eligible, key=lambda candidate: (candidate.mae, candidate.name))


@dataclass(frozen=True)
class CapacityScore:
    """The engine's capacity trend against the simulator's true neutral capacity."""

    exercise_id: str
    n: int
    pearson: float | None
    rmse_kg: float | None
    #: Before the global scale — dominated by the definitional offset.
    mean_relative_error: float | None
    final_relative_error: float | None
    #: After the global scale. This is the part that is not definitional.
    aligned_mean_error: float | None = None


@dataclass(frozen=True)
class ScenarioResponse:
    """Whether the engine moved the right way during a labelled episode."""

    label: str
    days: int
    mean_residual: float | None
    #: Residual on ordinary days *near this episode*, not across the record.
    #: The global comparison was confounded: bias runs from +0.051 early to
    #: −0.014 late, so a scenario landing in the first hundred days inherits
    #: the warm-up and reads as an effect of the scenario.
    mean_residual_elsewhere: float | None
    span: tuple[int, int] = (0, 0)
    #: 95% interval on the difference between the two means.
    interval: float | None = None

    @property
    def difference(self) -> float | None:
        if self.mean_residual is None or self.mean_residual_elsewhere is None:
            return None
        return self.mean_residual - self.mean_residual_elsewhere

    @property
    def direction_correct(self) -> bool | None:
        """Whether the engine moved the right way, or ``None`` if unresolved.

        A bare sign test reported four episodes as wrong when their differences
        were 0.003 on samples of a dozen sets — noise dressed as failure, which
        is the over-claiming counterpart of a vacuous pass. A verdict is only
        returned when the difference clears its own confidence interval.

        Suppression means observed performance falls *below* projection during
        a high-fatigue block; a deload rebound means it rises above.
        """
        difference = self.difference
        if difference is None or self.interval is None:
            return None
        if abs(difference) <= self.interval:
            return None
        return difference > 0 if self.label in ("S3_deload",) else difference < 0

    @property
    def verdict(self) -> str:
        correct = self.direction_correct
        if correct is None:
            return "no detectable difference"
        return "correct" if correct else "WRONG WAY"


@dataclass(frozen=True)
class PerformanceReport:
    """Everything §19.2 asks for."""

    n: int = 0
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    autocorrelation: float | None = None
    drift: tuple[tuple[int, int, float], ...] = ()
    by_experience: tuple[tuple[int, int, float], ...] = ()
    calibration: dict[str, tuple] = field(default_factory=dict)
    capacity: tuple[CapacityScore, ...] = ()
    scenarios: tuple[ScenarioResponse, ...] = ()
    ladder_all: tuple[LadderRung, ...] = ()
    ladder_settled: tuple[LadderRung, ...] = ()
    rho_clipped_residual: tuple[float | None, float | None] = (None, None)
    caveat: str = ""

    @property
    def beats_recency_when_settled(self) -> bool:
        """The gate. An engine that cannot beat recency has not earned itself."""
        rungs = {r.name: r for r in self.ladder_settled}
        others = [r for r in rungs.values() if r.name != "engine"]
        return bool(others) and all(r.verdict != "baseline better" for r in others)


def score_performance(run: EvaluationRun) -> PerformanceReport:
    if run.truth is None:
        raise ValueError("this run has no truth attached; call attach_truth first")

    residuals: list[float] = []
    days: list[int] = []
    experience: list[int] = []
    conditioners: dict[str, list[float]] = {
        "local_fatigue": [], "neuromuscular": [], "systemic": []
    }
    rho_clipped: list[float] = []
    rho_free: list[float] = []
    by_label: dict[str, list[float]] = defaultdict(list)
    labelled_any: list[float] = []

    from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: PLC0415

    floor = ENGINE_PARAMETERS.value("rho_floor")
    ceiling = ENGINE_PARAMETERS.value("rho_ceiling")

    seen: dict[str, int] = defaultdict(int)
    for result in run.results:
        clipped = (
            abs(result.recovery.rho - floor) < 1e-9
            or abs(result.recovery.rho - ceiling) < 1e-9
        )
        labels = run.truth.scenario_labels.get(result.day_index, ())
        for observation in result.observations:
            residuals.append(observation.log_residual)
            days.append(result.day_index)
            experience.append(seen[observation.exercise_id])
            seen[observation.exercise_id] += 1
            conditioners["local_fatigue"].append(sum(result.state.local_fatigue.values()))
            conditioners["neuromuscular"].append(result.state.neuromuscular)
            conditioners["systemic"].append(result.state.systemic)
            (rho_clipped if clipped else rho_free).append(observation.log_residual)
            for label in labels:
                by_label[label].append(observation.log_residual)
            if labels and labels != ("S0_ordinary",):
                labelled_any.append(observation.log_residual)

    scenarios = _scenario_responses(run, residuals, days)

    predictions = run.predictions()
    return PerformanceReport(
        n=len(residuals),
        mae=m.mae(residuals),
        rmse=math.sqrt(st.fmean([v * v for v in residuals])) if residuals else None,
        bias=m.bias(residuals),
        autocorrelation=m.autocorrelation(residuals),
        drift=m.drift_by_block(residuals, days),
        by_experience=_by_experience(residuals, experience),
        calibration={
            name: m.calibration_bins(residuals, values)
            for name, values in conditioners.items()
        },
        capacity=_capacity_scores(run),
        scenarios=scenarios,
        ladder_all=ablation_ladder(predictions),
        ladder_settled=ablation_ladder(predictions, minimum_prior=SETTLED_AFTER),
        rho_clipped_residual=(m.bias(rho_clipped), m.bias(rho_free)),
        caveat=run.caveat,
    )


#: Days either side of an episode used as its local control.
LOCAL_CONTROL_DAYS = 45


def _scenario_responses(
    run: EvaluationRun, residuals: Sequence[float], days: Sequence[int]
) -> tuple[ScenarioResponse, ...]:
    """Each episode against ordinary days *near it*, not across the record.

    Comparing to a global mean was confounded. The bias runs from +0.051 in the
    first hundred days to −0.014 in the last, and the high-volume block sits at
    days 70–91 while the illness block sits at 370–375. Measured that way, a
    scenario's "response" was mostly its position in the record.
    """
    labelled: dict[int, tuple[str, ...]] = run.truth.scenario_labels
    by_label: dict[str, list[float]] = defaultdict(list)
    span: dict[str, list[int]] = defaultdict(list)
    for residual, day in zip(residuals, days):
        for label in labelled.get(day, ()):
            if label == "S0_ordinary":
                continue
            by_label[label].append(residual)
            span[label].append(day)

    out: list[ScenarioResponse] = []
    for label, values in sorted(by_label.items()):
        lower, upper = min(span[label]), max(span[label])
        control = [
            residual
            for residual, day in zip(residuals, days)
            if lower - LOCAL_CONTROL_DAYS <= day <= upper + LOCAL_CONTROL_DAYS
            and label not in labelled.get(day, ())
        ]
        interval = None
        if len(values) > 1 and len(control) > 1:
            interval = 1.96 * math.sqrt(
                st.pvariance(values) / len(values) + st.pvariance(control) / len(control)
            )
        out.append(
            ScenarioResponse(
                label=label, days=len(values),
                mean_residual=m.bias(values),
                mean_residual_elsewhere=m.bias(control),
                span=(lower, upper), interval=interval,
            )
        )
    return tuple(out)


def _by_experience(
    residuals: Sequence[float], experience: Sequence[int], step: int = 10
) -> tuple[tuple[int, int, float], ...]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for residual, count in zip(residuals, experience):
        grouped[min(count // step, 7) * step].append(residual)
    return tuple(
        (start, len(values), st.fmean(values))
        for start, values in sorted(grouped.items())
        if len(values) >= m.MINIMUM_SAMPLE
    )


def _capacity_scale(pairs: Sequence[tuple[float, float]]) -> float:
    """One scale across every exercise, least squares through the origin."""
    denominator = sum(a * a for a, _ in pairs)
    return 1.0 if denominator <= 0 else sum(a * b for a, b in pairs) / denominator


def _capacity_scores(run: EvaluationRun) -> tuple[CapacityScore, ...]:
    """Engine capacity against true neutral capacity, in kilograms.

    The engine's estimate moves with every eligible set; the truth is known only
    on days the exercise was trained. Comparison happens on those days, which is
    every day the question is answerable.
    """
    out: list[CapacityScore] = []
    tracked: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for result in run.results:
        for observation in result.observations:
            tracked[observation.exercise_id].append(
                (result.day_index, observation.capacity_before)
            )

    everything = [
        (v, run.truth.capacity[exercise_id][d])
        for exercise_id, series in tracked.items()
        for d, v in series
        if d in run.truth.capacity.get(exercise_id, {})
        and run.truth.capacity[exercise_id][d] > 0
    ]
    scale = _capacity_scale(everything)

    for exercise_id, series in sorted(tracked.items()):
        truth = run.truth.capacity.get(exercise_id, {})
        pairs = [(v, truth[d]) for d, v in series if d in truth and truth[d] > 0]
        if len(pairs) < m.MINIMUM_SAMPLE:
            continue
        estimated = [a for a, _ in pairs]
        actual = [b for _, b in pairs]
        relative = [a / b - 1 for a, b in pairs]
        out.append(
            CapacityScore(
                exercise_id=exercise_id,
                n=len(pairs),
                pearson=m.pearson(estimated, actual),
                rmse_kg=m.rmse(estimated, actual),
                mean_relative_error=st.fmean(relative),
                final_relative_error=relative[-1],
                aligned_mean_error=st.fmean([a * scale / b - 1 for a, b in pairs]),
            )
        )
    return tuple(out)


def single_bad_day_displacement(
    days: Sequence,
    day_index: int,
    exercise_id: str,
    factor: float = 0.861,
) -> tuple[float, float, int]:
    """How far one anomalous *session* moves the capacity estimate.

    Returns ``(displacement, settled_displacement, eligible_sets)``: the shift
    immediately after the session, the shift ninety days later, and how many
    eligible sets the engine actually learned from that day.

    ``DATA.md`` §19.7 originally set the requirement at under 1% once the
    estimate was established. Its stand-in applied one ``update_capacity``
    call while the old engine updated once per eligible set, so it never
    measured a session. The approved repair now aggregates those correlated
    sets into one update and enforces explicit ordinary/anchor session caps of
    2.1%/3.3%; this instrument checks that mechanism end to end.

    The default ``factor`` is the magnitude scenario S11 actually applies —
    ``exp(-|N(0.10, 0.055)| - 0.05)``, a median 13.9% shortfall — rather than
    the 40% the old stand-in used. It makes no difference to the answer, and
    that remains useful because any innovation beyond the robust clip is
    clipped to the same value. The returned eligible-set count proves the
    session held performance evidence; it no longer multiplies state updates.
    """
    from rhome_eval.robustness import bad_session, run_perturbed  # noqa: PLC0415

    run = run_perturbed(days, bad_session(day_index, exercise_id, factor))
    eligible = sum(
        1
        for logged, dose in run.clean_results[day_index].doses
        if logged.exercise_id == exercise_id and dose.eligible_for_performance
    )
    settled_day = min(len(run.clean_results) - 1, day_index + 90)
    return (
        run.capacity_shift_at(exercise_id, day_index),
        run.capacity_shift_at(exercise_id, settled_day),
        eligible,
    )


def clip_bounded_displacement(eligible_sets: int, *, anchor: bool = False) -> float:
    """The explicit maximum capacity movement from one correlated session."""
    from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: PLC0415

    if eligible_sets < 0:
        raise ValueError("eligible_sets cannot be negative")
    return ENGINE_PARAMETERS.value(
        "capacity_anchor_session_max_move" if anchor
        else "capacity_session_max_move"
    )
