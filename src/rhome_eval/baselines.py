"""The ablation ladder (``PRODUCT.md`` §15).

Checkpoint 2 reported the engine's residual without a reference point, and the
comparison — run only when the athlete asked directly whether performance was
good — reversed the reading. A median-of-the-last-three baseline beat the
engine on the pooled sample.

So the ladder lives in the harness rather than being produced on request. Every
performance number this project reports is accompanied by what a predictor with
no model at all would have achieved on the same sets, because a residual
without that comparison does not say whether the machinery earned its place.
"""

from __future__ import annotations

import math
import statistics as st
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Sequence

__all__ = ["Prediction", "LadderRung", "ablation_ladder", "BASELINES"]


@dataclass(frozen=True)
class Prediction:
    """One scored set: what happened, and what the engine said would."""

    exercise_id: str
    day: int
    observed: float
    projected: float
    #: How many observations of this exercise preceded it.
    prior_observations: int


@dataclass(frozen=True)
class LadderRung:
    """One predictor's showing on a shared sample."""

    name: str
    n: int
    mae: float
    rmse: float
    bias: float
    #: Paired difference in absolute error against the engine, with a 95%
    #: interval. Negative means the engine did better.
    versus_engine: float | None = None
    interval: float | None = None

    @property
    def verdict(self) -> str:
        if self.versus_engine is None or self.interval is None:
            return "reference"
        if self.versus_engine > self.interval:
            return "engine better"
        if self.versus_engine < -self.interval:
            return "baseline better"
        return "tie"


def _last_observation(history: Sequence[float]) -> float | None:
    return history[-1] if history else None


def _median_of_last(k: int) -> Callable[[Sequence[float]], float | None]:
    def predictor(history: Sequence[float]) -> float | None:
        return st.median(history[-k:]) if len(history) >= k else None
    return predictor


def _mean_of_last(k: int) -> Callable[[Sequence[float]], float | None]:
    def predictor(history: Sequence[float]) -> float | None:
        return st.fmean(history[-k:]) if len(history) >= k else None
    return predictor


#: Predictors that use only the athlete's own past performance on that
#: exercise. None of them knows anything about fatigue, effort or wearables.
BASELINES: dict[str, Callable[[Sequence[float]], float | None]] = {
    "last observation": _last_observation,
    "median of last 3": _median_of_last(3),
    "median of last 5": _median_of_last(5),
    "mean of last 5": _mean_of_last(5),
}


def ablation_ladder(
    predictions: Sequence[Prediction],
    *,
    minimum_prior: int = 0,
    baselines: dict[str, Callable[[Sequence[float]], float | None]] | None = None,
) -> tuple[LadderRung, ...]:
    """Score the engine and every baseline on the same sets.

    ``minimum_prior`` restricts the sample to sets where the engine had at
    least that many prior observations of the exercise. It exists because the
    answer genuinely depends on it: the engine loses on the pooled sample and
    wins comfortably once it has seen an exercise twenty times, and reporting
    only one of those is reporting half a result.

    The sample is matched across predictors — a set is scored by everyone or by
    nobody. An unmatched comparison silently excludes each baseline's own
    warm-up and flatters it.
    """
    baselines = BASELINES if baselines is None else baselines
    history: dict[str, list[float]] = defaultdict(list)

    rows: list[tuple[float, dict[str, float]]] = []
    for prediction in sorted(predictions, key=lambda p: (p.day, p.exercise_id)):
        past = history[prediction.exercise_id]
        candidates = {name: fn(past) for name, fn in baselines.items()}
        eligible = (
            prediction.prior_observations >= minimum_prior
            and all(value is not None and value > 0 for value in candidates.values())
            and prediction.projected > 0
            and prediction.observed > 0
        )
        if eligible:
            rows.append((
                prediction.observed,
                {"engine": prediction.projected,
                 **{k: v for k, v in candidates.items() if v is not None}},
            ))
        past.append(prediction.observed)

    if not rows:
        return ()

    errors: dict[str, list[float]] = defaultdict(list)
    for observed, predicted in rows:
        for name, value in predicted.items():
            errors[name].append(math.log(observed / value))

    engine_absolute = [abs(v) for v in errors["engine"]]
    rungs: list[LadderRung] = []
    for name, values in errors.items():
        absolute = [abs(v) for v in values]
        rung = LadderRung(
            name=name, n=len(values),
            mae=st.fmean(absolute),
            rmse=math.sqrt(st.fmean([v * v for v in values])),
            bias=st.fmean(values),
        )
        if name != "engine":
            paired = [b - a for a, b in zip(engine_absolute, absolute)]
            spread = st.pstdev(paired) if len(paired) > 1 else 0.0
            rung = LadderRung(
                **{**rung.__dict__,
                   "versus_engine": st.fmean(paired),
                   "interval": 1.96 * spread / math.sqrt(len(paired))}
            )
        rungs.append(rung)

    return tuple(sorted(rungs, key=lambda r: (r.name != "engine", r.mae)))
