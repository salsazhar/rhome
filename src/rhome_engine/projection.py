"""Forward projection and counterfactual sessions (``MODEL.tex`` §Projection).

Every fatigue channel decays analytically, so the no-training future is
available in closed form. What matters in building it is not the arithmetic but
where the arithmetic comes from: a projector that re-derives decay would agree
with the engine today and drift from it after the next change to either.

So a projection is the engine's own state evolution, run on a **copy**. The
same ``StateEngine.advance_to`` that produced the present produces the future,
and applying a counterfactual set uses the same ``transform_set`` and
``apply_dose`` a real set would. Nothing here knows a half-life.

Three assumptions are made explicit because each could quietly bias a result.

**The recovery multiplier resets to neutral.** The timeline's last window
extends indefinitely, so projecting without intervention would carry last
night's context forward for a week. ``MODEL.tex`` names $\\rho = 1$ as the
neutral forecast, and a projection that inherited a poor night would forecast
slow recovery for seven days on one night's evidence.

**Background activity contributes nothing, which is the same as assuming a
typical day.** Activity amplitude is the *excess* over the athlete's rolling
step baseline, so an ordinary future day has amplitude zero by construction.
An activity window still running at the moment of projection continues, since
it is already declared.

**Nothing is written to the ledger.** The explanation trace decomposes states
that happened. A projection is a claim about states that have not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rhome_core.exercises import ExerciseLibrary
from rhome_core.muscles import Muscle
from rhome_core.timeline import RecoveryTimeline, RecoveryWindow
from rhome_engine.confidence import Confidence, ConfidenceReport
from rhome_engine.dose import LoggedSet, transform_set
from rhome_engine.state import EngineState, StateEngine
from rhome_engine.trace import display_value

__all__ = ["CounterfactualSet", "ProjectedPoint", "Projection", "project"]

#: The horizons ``PRODUCT.md`` asks for. Others may be requested.
DEFAULT_HORIZONS_H: tuple[float, ...] = (24.0, 72.0, 168.0)

NEUTRAL_RHO = 1.0


@dataclass(frozen=True)
class CounterfactualSet:
    """A set the athlete has not performed, placed at a proposed time."""

    logged: LoggedSet
    #: Hours from the projection's origin.
    at_h: float

    def __post_init__(self) -> None:
        if self.at_h < 0:
            raise ValueError("a counterfactual set cannot be placed in the past")


@dataclass(frozen=True)
class ProjectedPoint:
    """The state at one horizon, and how much the model claims to know of it."""

    horizon_h: float
    local_fatigue: dict[Muscle, float]
    neuromuscular: float
    systemic: float
    adaptation: dict[Muscle, float]
    confidence: Confidence | None = None

    @property
    def total_local_fatigue(self) -> float:
        return sum(self.local_fatigue.values())

    def display(self, muscle: Muscle) -> float:
        return display_value(self.local_fatigue[muscle])


@dataclass(frozen=True)
class Projection:
    """A forward path, with its assumptions stated alongside it."""

    origin_h: float
    assumed_rho: float
    points: tuple[ProjectedPoint, ...] = ()
    counterfactual: tuple[CounterfactualSet, ...] = ()
    #: The state at the origin, so a caller can compare without recomputing.
    origin: ProjectedPoint | None = None

    @property
    def is_counterfactual(self) -> bool:
        return bool(self.counterfactual)

    def at(self, horizon_h: float) -> ProjectedPoint:
        for point in self.points:
            if point.horizon_h == horizon_h:
                return point
        raise KeyError(f"no projected point at {horizon_h} h")

    def assumptions(self) -> tuple[str, ...]:
        """What the caller is taking on trust, in words.

        A projection with its assumptions detached from it is a number without
        a claim attached, and this one rests on three.
        """
        lines = [
            f"recovery context assumed neutral (rho = {self.assumed_rho:.2f})",
            "background activity assumed typical, which adds nothing above baseline",
        ]
        lines.append(
            f"{len(self.counterfactual)} proposed sets included"
            if self.counterfactual
            else "no training assumed"
        )
        return tuple(lines)


def _point(state: EngineState, horizon_h: float, confidence: Confidence | None) -> ProjectedPoint:
    return ProjectedPoint(
        horizon_h=horizon_h,
        local_fatigue=dict(state.local_fatigue),
        neuromuscular=state.neuromuscular,
        systemic=state.systemic,
        adaptation=dict(state.adaptation),
        confidence=confidence,
    )


def project(
    source: StateEngine,
    library: ExerciseLibrary,
    horizons_h: tuple[float, ...] = DEFAULT_HORIZONS_H,
    *,
    assumed_rho: float = NEUTRAL_RHO,
    counterfactual: tuple[CounterfactualSet, ...] = (),
    confidence: ConfidenceReport | None = None,
) -> Projection:
    """Propagate the engine's state forward, optionally through proposed sets.

    The source engine is forked, never advanced. A projection that moved the
    present would corrupt the estimate it was asked to extrapolate from, and
    the corruption would be invisible: the next real day would simply evolve
    from a state that had already had an imagined week applied to it.
    """
    if any(h < 0 for h in horizons_h):
        raise ValueError("a projection horizon cannot be negative")
    if assumed_rho <= 0:
        raise ValueError("the assumed recovery multiplier must be positive")

    origin_h = source.state.t_h
    engine = source.fork(RecoveryTimeline([RecoveryWindow(origin_h, assumed_rho)]))

    origin_point = _point(engine.state, 0.0, confidence.fatigue if confidence else None)

    schedule = sorted(counterfactual, key=lambda c: c.at_h)
    ordered = sorted(set(horizons_h))
    points: list[ProjectedPoint] = []
    index = 0

    for horizon in ordered:
        while index < len(schedule) and schedule[index].at_h <= horizon:
            proposed = schedule[index]
            exercise = library[proposed.logged.exercise_id]
            dose = transform_set(
                proposed.logged, exercise,
                novelty=engine.novelty_for(proposed.logged.exercise_id),
            )
            engine.apply_dose(dose, origin_h + proposed.at_h, proposed.logged.exercise_id)
            index += 1
        engine.advance_to(origin_h + horizon)
        points.append(
            _point(
                engine.state, horizon,
                confidence.projection(horizon) if confidence else None,
            )
        )

    return Projection(
        origin_h=origin_h,
        assumed_rho=assumed_rho,
        points=tuple(points),
        counterfactual=tuple(schedule),
        origin=origin_point,
    )
