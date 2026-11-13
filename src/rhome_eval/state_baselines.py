"""Baselines for latent-state reconstruction (``DATA.md`` §19.1).

The performance side learned this at Checkpoint 2: a residual reported without
a reference point does not say whether the machinery earned its place. The
state side learned it at L3.1, one stage later and the same way.

Corrected for a pairing error, the engine's aggregate channels correlate
+0.949 to +0.973 with latent truth. **A decaying count of working sets — which
knows nothing about exercise, repetitions, effort, muscles or recovery context
— scores +0.911 to +0.945 on the same series.** Almost all of a headline
correlation is "did you train recently, and how much", because both series are
driven by the same training log.

**That argument was wrong about attribution, and L3.17 measured it.** This
module used to say a counter "cannot attribute" — no way to distinguish chest
from quadriceps — so it must give every muscle the same series, collapsing to
+0.520 against the engine's +0.966. The premise is false. A counter cannot
*infer* an attribution, but it does not have to: the exercise-to-muscle map is
authored data sitting in the library, and handing it to a counter costs
nothing. Given ``c^F`` and nothing else — no repetitions, no effort, no
novelty, no wearables, no recovery multiplier — a decaying counter scores
**+0.955 longitudinally and +0.934 cross-sectionally** against the engine's
+0.965 and +0.941.

So the +0.520 figure measured the absence of a lookup table, not the presence
of a model, and the engine's per-muscle advantage over a competent trivial
competitor is **+0.010**.

This is why D23 exists: *a trivial competitor must be given every structure the
engine is not claiming credit for.* The engine claims to infer fatigue
physiology from a log. It does not claim to have invented the muscle map. So
the map goes to the competitor, and what the engine must earn is whatever the
map plus exponential decay cannot already do.

Both are kept below. The unattributed counter is still the right competitor for
the *aggregate* channels, where there is nothing to attribute; the attributed
one is the only honest competitor for a per-muscle claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

__all__ = [
    "StateBaseline", "decaying_count", "STATE_BASELINES", "compare_to_baselines",
    "MuscleBaseline", "MUSCLE_BASELINES",
]

LN2 = math.log(2.0)


def decaying_count(
    per_day: Sequence[float], half_life_h: float = 30.0
) -> tuple[float, ...]:
    """A single exponentially decaying accumulator over a daily quantity.

    One state variable, one parameter. Whatever this achieves is the floor any
    fatigue model has to clear before its structure has been shown to matter.
    """
    if half_life_h <= 0:
        raise ValueError("half-life must be positive")
    decay = math.exp(-LN2 / half_life_h * 24.0)
    state = 0.0
    out: list[float] = []
    for value in per_day:
        state = state * decay + value
        out.append(state)
    return tuple(out)


@dataclass(frozen=True)
class StateBaseline:
    """One trivial predictor of a latent channel."""

    name: str
    #: Maps a day's logged sets to a single number.
    per_day: Callable[[Sequence], float]
    half_life_h: float = 30.0

    def series(self, days: Sequence) -> tuple[float, ...]:
        return decaying_count(
            [self.per_day(getattr(d, "sets", ())) for d in days], self.half_life_h
        )


def _working(sets: Sequence) -> list:
    return [s for s in sets if getattr(s, "set_type", None) in ("working", "backoff")]


STATE_BASELINES: tuple[StateBaseline, ...] = (
    StateBaseline("working sets, 30 h", lambda s: float(len(_working(s)))),
    StateBaseline("working sets, 8 h", lambda s: float(len(_working(s))), 8.0),
    StateBaseline("working sets, 120 h", lambda s: float(len(_working(s))), 120.0),
    StateBaseline("trained yes/no, 30 h", lambda s: 1.0 if _working(s) else 0.0),
    StateBaseline("total repetitions, 30 h",
                  lambda s: sum(getattr(x, "reps", 0) for x in _working(s)) / 100.0),
)


@dataclass(frozen=True)
class StateComparison:
    """What the engine scored, and what a counter scored, on the same series."""

    channel: str
    engine: float | None
    baselines: dict[str, float | None]

    @property
    def best_baseline(self) -> tuple[str, float] | None:
        scored = {k: v for k, v in self.baselines.items() if v is not None}
        if not scored:
            return None
        name = max(scored, key=lambda k: scored[k])
        return name, scored[name]

    @property
    def advantage(self) -> float | None:
        best = self.best_baseline
        return None if best is None or self.engine is None else self.engine - best[1]


def compare_to_baselines(
    channel: str,
    engine_series: Sequence[float],
    truth_series: Sequence[float],
    days: Sequence,
    *,
    offset: int = 1,
) -> StateComparison:
    """Score the engine and every counter against the same latent series.

    ``offset`` trims the baselines the same way the harness pairs the engine
    against truth, so all three series describe the same instants.
    """
    from rhome_eval.metrics import pearson  # noqa: PLC0415

    scores: dict[str, float | None] = {}
    for baseline in STATE_BASELINES:
        series = baseline.series(days)
        trimmed = series[: len(series) - offset] if offset else series
        scores[baseline.name] = (
            pearson(trimmed, truth_series) if len(trimmed) == len(truth_series) else None
        )
    return StateComparison(
        channel=channel, engine=pearson(engine_series, truth_series), baselines=scores
    )


# --- per-muscle competitors (D23) ------------------------------------------

@dataclass(frozen=True)
class MuscleBaseline:
    """A trivial predictor that attributes, because the map is authored data.

    One state variable per muscle, one half-life, and a weight table read
    straight from the exercise library. There is no inference here at all: no
    repetitions, no effort, no proximity to failure, no novelty, no wearables,
    no recovery multiplier, no within-session anything. Whatever this reaches
    is the floor a per-muscle fatigue model has to clear before its structure
    has been shown to matter.
    """

    name: str
    #: Weight per muscle for one performed set of an exercise.
    weights: Callable[[object], Mapping[object, float]]
    half_life_h: float = 30.0

    def series(self, days: Sequence, library) -> dict:
        from rhome_core.muscles import Muscle  # noqa: PLC0415

        decay_per_day = math.exp(-LN2 / self.half_life_h * 24.0)
        state = {muscle: 0.0 for muscle in Muscle}
        out: dict = {muscle: [] for muscle in Muscle}
        previous: int | None = None

        for day in days:
            index = getattr(day, "day_index", None)
            step = 1 if previous is None or index is None else max(0, index - previous)
            previous = index
            if step:
                factor = decay_per_day ** step
                for muscle in state:
                    state[muscle] *= factor
            for performed in _working(getattr(day, "sets", ())):
                exercise = library.exercises.get(getattr(performed, "exercise_id", None))
                if exercise is None:
                    continue
                for muscle, weight in self.weights(exercise).items():
                    state[muscle] += weight
            for muscle in state:
                out[muscle].append(state[muscle])

        return {muscle: tuple(values) for muscle, values in out.items()}


MUSCLE_BASELINES: tuple[MuscleBaseline, ...] = (
    # The competitor D20 should have had. c^F is read from the library, so this
    # shares the engine's muscle map and nothing else.
    MuscleBaseline("c_F-weighted counter, 30 h", lambda ex: ex.fatigue_contributions),
    # Coarser still: membership of the primary set, no tiering.
    MuscleBaseline(
        "primary-muscle counter, 30 h",
        lambda ex: {muscle: 1.0 for muscle in ex.primary_muscles},
    ),
)
