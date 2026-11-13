"""Assembling an evaluation run (``DATA.md`` §19).

This module is where the two sides of the project finally meet. The ordering it
enforces is the point: **the engine is run to completion before any latent
series is read.** Not because reading truth earlier would break anything
mechanically, but because a harness that has the answers in hand while the
engine is still working is one refactor away from using them.

``rhome_eval`` is the only package permitted this view, and it is the last
place where the discipline of the whole build can quietly fail.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from rhome_core.exercises import ExerciseLibrary, load_library
from rhome_core.muscles import Muscle
from rhome_engine.session import DayInput, DayResult, RhomeEngine
from rhome_eval.alignment import ScaleAlignment, fit_alignment
from rhome_eval.baselines import Prediction
from rhome_eval.window import (
    HoldoutSeal,
    SealError,
    Window,
    holdout_seal,
    open_holdout,
)

__all__ = ["LatentSeries", "EvaluationRun", "run_engine", "attach_truth", "evaluate"]

#: The channels compared against latent truth, in engine-side names.
CHANNELS = ("local_fatigue", "neuromuscular", "systemic")

#: The engine's day-N state is captured at the close of day N — waking plus
#: sixteen hours, after that day's session. The simulator records its latent
#: state **on waking**, before the day's training. So the engine's day N lines
#: up with the simulator's day N+1, and comparing them index for index compares
#: states sixteen hours apart across a training session.
#:
#: This was not obvious and cost real numbers. Every latent correlation
#: reported before L3.1 was computed on the unshifted pairing: local fatigue
#: read +0.447 where it is +0.949, neuromuscular +0.277 where it is +0.956, and
#: directional accuracy sat at 43% — below chance, which was the clue. A
#: sixteen-hour offset across the one event that moves the state inverts the
#: day-to-day differences almost perfectly.
LATENT_OFFSET_DAYS = 1


@dataclass(frozen=True)
class LatentSeries:
    """What was actually true, by day, in the simulator's own units."""

    days: tuple[int, ...]
    local_fatigue: Mapping[Muscle, tuple[float, ...]]
    local_fatigue_total: tuple[float, ...]
    neuromuscular: tuple[float, ...]
    systemic: tuple[float, ...]
    recovery_propensity: tuple[float, ...]
    #: True neutral capacity per exercise, by day, where the exercise was trained.
    #:
    #: The simulator's chain is capacity → fatigue → **stochastic shock** →
    #: load, so the realised value carries all three and every one must be
    #: removed to recover capacity. Dividing by the fatigue factor alone leaves
    #: the shock in, which is what this did until the Layer 3 audit: a quantity
    #: that must be constant across one day's sets varied by 5.12% within a
    #: day, and the §19.2 capacity correlation read +0.690 where it is +0.973.
    #: The shock is per set and roughly symmetric, so it destroyed correlation
    #: without moving the mean error — which is why every check that looked at
    #: the mean passed.
    capacity: Mapping[str, Mapping[int, float]]
    #: True *expressible* capacity — neutral capacity after the fatigue acting
    #: at the time, and **only** that. This is what "expected performance"
    #: means in §19.3, and the distinction matters twice over: neutral capacity
    #: does not jump across a deload, and comparing against it made the
    #: deload-rebound test look like a failure; and the shock must come out
    #: here too, while the fatigue factor must not.
    expressible: Mapping[str, Mapping[int, float]]
    scenario_labels: Mapping[int, tuple[str, ...]]

    def channel(self, name: str, *, paired: bool = True) -> tuple[float, ...]:
        """The latent series, shifted to pair with the engine's by default."""
        values = self.local_fatigue_total if name == "local_fatigue" else getattr(self, name)
        return values[LATENT_OFFSET_DAYS:] if paired else values

    def muscle(self, muscle: Muscle, *, paired: bool = True) -> tuple[float, ...]:
        values = self.local_fatigue[muscle]
        return values[LATENT_OFFSET_DAYS:] if paired else values


@dataclass
class EvaluationRun:
    """One window, scored. Estimates and truth, aligned and side by side."""

    window: Window
    results: tuple[DayResult, ...]
    library: ExerciseLibrary
    engine: RhomeEngine
    truth: LatentSeries | None = None
    alignment: ScaleAlignment | None = None
    seal: HoldoutSeal = field(default_factory=HoldoutSeal)

    @property
    def days(self) -> tuple[int, ...]:
        return tuple(r.day_index for r in self.results)

    def estimated(self, name: str, *, paired: bool = True) -> tuple[float, ...]:
        """The engine's series, trimmed to pair with latent truth by default.

        ``paired=False`` gives the untrimmed series, for reporting the engine's
        own output rather than comparing it.
        """
        if name == "local_fatigue":
            values = tuple(sum(r.state.local_fatigue.values()) for r in self.results)
        else:
            values = tuple(getattr(r.state, name) for r in self.results)
        return values[: len(values) - LATENT_OFFSET_DAYS] if paired else values

    def estimated_muscle(self, muscle: Muscle, *, paired: bool = True) -> tuple[float, ...]:
        values = tuple(r.state.local_fatigue[muscle] for r in self.results)
        return values[: len(values) - LATENT_OFFSET_DAYS] if paired else values

    def aligned(self, name: str) -> tuple[float, ...]:
        """Estimates in the simulator's units, for an RMSE that means something."""
        if self.alignment is None:
            raise ValueError("no alignment fitted for this run")
        return tuple(self.alignment.apply(name, self.estimated(name)))

    def predictions(self) -> tuple[Prediction, ...]:
        """Every scored set, ordered, with how much history preceded it."""
        seen: dict[str, int] = defaultdict(int)
        out: list[Prediction] = []
        for result in self.results:
            for observation in result.observations:
                out.append(
                    Prediction(
                        exercise_id=observation.exercise_id,
                        day=result.day_index,
                        observed=observation.observed,
                        projected=observation.projected,
                        prior_observations=seen[observation.exercise_id],
                    )
                )
                seen[observation.exercise_id] += 1
        return tuple(out)

    def residuals(self) -> tuple[tuple[int, float], ...]:
        return tuple(
            (r.day_index, o.log_residual) for r in self.results for o in r.observations
        )

    @property
    def caveat(self) -> str:
        """What must accompany any number from this run."""
        if self.window is Window.DEVELOPMENT:
            return "development window; the engine was built against this data"
        return self.seal.note()


# --- the ordering ------------------------------------------------------------

def run_engine(
    days: Sequence[DayInput],
    window: Window,
    library: ExerciseLibrary | None = None,
    *,
    seal: HoldoutSeal | None = None,
) -> EvaluationRun:
    """Run the engine over a window, with no access to truth.

    Truth is attached afterwards, by a separate call. Splitting it in two is
    what makes the ordering visible: nothing in this function could consult a
    latent series even if someone tried to make it.

    The seal is checked *here* rather than only in ``evaluate``. The first
    version guarded the convenience wrapper alone, and two of this module's own
    tests promptly ran the engine across the holdout to exercise an unrelated
    code path — a harness leaking its own holdout through its test suite. A
    guard that only covers the polite entry point is not a guard.
    """
    if window.is_sealed and seal is None:
        raise SealError(
            f"the {window.value} window is sealed. Open it deliberately with "
            f"open_holdout(reason), or use evaluate(..., reason=...), which "
            f"records the opening."
        )
    library = library or load_library()
    engine = RhomeEngine(library)
    selected = [d for d in days if d.day_index in window.days]
    if not selected:
        raise ValueError(f"no days fall inside the {window.value} window")
    results = engine.run(selected)
    return EvaluationRun(
        window=window, results=tuple(results), library=library, engine=engine
    )


def latent_series(simulation, window: Window) -> LatentSeries:
    """Extract what was true, for the days in one window."""
    days = [d for d in simulation.days if d.day_index in window.days]
    per_muscle: dict[Muscle, list[float]] = {m: [] for m in Muscle}
    capacity: dict[str, dict[int, float]] = defaultdict(dict)
    expressible: dict[str, dict[int, float]] = defaultdict(dict)

    for day in days:
        for muscle in Muscle:
            per_muscle[muscle].append(day.state_on_waking.local_fatigue(muscle))
        for performed in day.sets:
            if performed.fatigue_factor > 0 and performed.performance_shock > 0:
                # The set's own good-day/bad-day roll is recorded separately by
                # the simulator, so it can be divided out rather than carried
                # into the target. Both series therefore describe the same
                # quantity on every set of a day, which is what lets the first
                # set be taken without the choice mattering — and what makes
                # the within-day spread a usable check that it is right.
                unshocked = (
                    performed.true_expressible_capacity / performed.performance_shock
                )
                capacity[performed.exercise_id].setdefault(
                    day.day_index, unshocked / performed.fatigue_factor
                )
                expressible.setdefault(performed.exercise_id, {}).setdefault(
                    day.day_index, unshocked
                )

    return LatentSeries(
        days=tuple(d.day_index for d in days),
        local_fatigue={m: tuple(v) for m, v in per_muscle.items()},
        local_fatigue_total=tuple(
            sum(per_muscle[m][i] for m in Muscle) for i in range(len(days))
        ),
        neuromuscular=tuple(d.state_on_waking.neuromuscular for d in days),
        systemic=tuple(d.state_on_waking.systemic for d in days),
        recovery_propensity=tuple(d.latent.recovery_propensity for d in days),
        capacity={k: dict(v) for k, v in capacity.items()},
        expressible={k: dict(v) for k, v in expressible.items()},
        scenario_labels={d.day_index: tuple(d.scenario_labels) for d in days},
    )


def attach_truth(
    run: EvaluationRun, simulation, alignment: ScaleAlignment | None = None
) -> EvaluationRun:
    """Attach latent truth to a completed run, and align the scales.

    An alignment may be supplied — and on the holdout it must be, fitted on the
    development window and passed in unchanged. Fitting one on the holdout
    would estimate a parameter from the data being used to test, which is the
    failure the holdout exists to prevent.
    """
    truth = latent_series(simulation, run.window)
    if len(truth.days) != len(run.days):
        raise ValueError(
            f"{len(run.days)} engine days against {len(truth.days)} latent days"
        )
    if len(truth.days) <= LATENT_OFFSET_DAYS:
        raise ValueError("too few days to pair across the waking offset")

    if alignment is None:
        if run.window is Window.HOLDOUT:
            raise ValueError(
                "the holdout requires an alignment fitted on the development "
                "window; fitting one here would tune a parameter on the test set"
            )
        alignment = fit_alignment(
            {c: run.estimated(c) for c in CHANNELS},
            {c: truth.channel(c) for c in CHANNELS},
            fitted_on=run.window.value,
        )
    elif not alignment.verify():
        raise ValueError("the supplied alignment fails its own digest check")

    run.truth = truth
    run.alignment = alignment
    return run


def evaluate(
    days: Sequence[DayInput],
    window: Window = Window.DEVELOPMENT,
    *,
    simulation=None,
    alignment: ScaleAlignment | None = None,
    reason: str = "",
    record_opening: bool = True,
) -> EvaluationRun:
    """Run the engine over a window and score it. The whole harness, in one call.

    Opening the holdout requires a stated reason and is recorded, because the
    value of a holdout is destroyed by the first unrecorded look and nothing
    afterwards can tell you it happened.
    """
    if window.is_sealed:
        seal = open_holdout(reason, record=record_opening)
    else:
        seal = holdout_seal()

    run = run_engine(days, window, seal=seal)
    run.seal = seal

    if simulation is None:
        from rhome_sim.generate import simulate  # noqa: PLC0415

        simulation = simulate(20260822)
    return attach_truth(run, simulation, alignment)
