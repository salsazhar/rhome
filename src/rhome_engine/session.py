"""The day loop (``DATA.md`` §9.5, ``MODEL.tex`` §Estimation of underlying capacity).

Drives the engine's parts through one pass over the calendar, in the order the
specification requires. The order is the substance of this module, not an
implementation detail:

1. resolve recovery context on waking, from the systemic load carried *into*
   the day — nocturnal physiology reflects the training that preceded it;
2. extend the recovery timeline, so the day's multiplier applies from waking;
3. advance state to waking and declare the day's activity window;
4. **freeze a projection for every exercise the athlete is about to perform**;
5. ingest the sets;
6. score residuals against the frozen projections;
7. update capacity.

Steps 4 and 6 are separated by the entire session. Nothing between them may
touch a projection, and Guardrail 2 raises if anything tries. That separation is
the only thing standing between an honest performance metric and one that
flatters the model, and it is the reason this loop exists as a named module
rather than as glue inside an evaluation script.
"""

from __future__ import annotations

import statistics as st
from collections import defaultdict, deque
from dataclasses import dataclass, field

from rhome_core.exercises import ExerciseLibrary
from rhome_core.timeline import RecoveryTimeline, RecoveryWindow
from rhome_engine.confidence import ConfidenceEngine, ConfidenceReport
from rhome_engine.dose import (
    LoggedSet,
    SetDose,
    amplify_within_session_fatigue,
    transform_set,
)
from rhome_engine.ledger import Channel, ContributionLedger
from rhome_engine.performance import (
    BodyMassTracker,
    CapacityModel,
    FrozenProjection,
    PerformanceObservation,
    capacity_identity,
    observed_performance,
)
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.recovery import RecoveryContext, RecoveryContextEngine, RecoveryReading
from rhome_engine.projection import (
    DEFAULT_HORIZONS_H,
    CounterfactualSet,
    Projection,
    project,
)
from rhome_engine.state import EngineState, StateEngine
from rhome_engine.trace import TraceBuilder, TraceRecord

__all__ = ["DayInput", "DayResult", "RhomeEngine"]

#: The rolling window the day's step count is judged against.
_STEPS_BASELINE_DAYS = int(ENGINE_PARAMETERS.value("steps_baseline_days"))

#: Hours after midnight at which the athlete wakes and trains. Real timestamps
#: replace these where the log carries them.
WAKE_H = 7.5
TRAIN_H = 17.0


class _EffortHistory:
    """The athlete's own recent logged reserve, per exercise.

    ``MODEL.tex`` §Working sets logged without an effort rating: an unrated set
    is imputed from what this athlete usually reports on that exercise, falling
    back to what they report generally, and only then to a population prior.
    Each fallback is a step further from the person, so each is taken only when
    the one before it has too little to say.
    """

    def __init__(self) -> None:
        self._window = int(ENGINE_PARAMETERS.value("imputed_rir_window"))
        self._minimum = int(ENGINE_PARAMETERS.value("imputed_rir_minimum"))
        self._by_exercise: dict[str, deque[float]] = {}
        self._overall: deque[float] = deque(maxlen=self._window * 4)

    def observe(self, exercise_id: str, rir: float) -> None:
        self._by_exercise.setdefault(
            exercise_id, deque(maxlen=self._window)
        ).append(rir)
        self._overall.append(rir)

    def impute(self, exercise_id: str) -> float:
        own = self._by_exercise.get(exercise_id, ())
        if len(own) >= self._minimum:
            return st.median(own)
        if len(self._overall) >= self._minimum:
            return st.median(self._overall)
        return float(ENGINE_PARAMETERS.value("imputed_rir_prior"))


@dataclass(frozen=True)
class DayInput:
    """One day as the engine receives it."""

    day_index: int
    reading: RecoveryReading
    sets: list[LoggedSet] = field(default_factory=list)
    body_mass_kg: float | None = None
    steps: float | None = None
    anchor_exercise_ids: frozenset[str] = frozenset()


@dataclass
class DayResult:
    """What the engine concluded about one day."""

    day_index: int
    state: EngineState
    recovery: RecoveryContext
    projections: dict[str, FrozenProjection] = field(default_factory=dict)
    observations: list[PerformanceObservation] = field(default_factory=list)
    doses: list[tuple[LoggedSet, SetDose]] = field(default_factory=list)
    activity_amplitude: float = 0.0
    confidence: ConfidenceReport | None = None
    traces: dict[str, TraceRecord] = field(default_factory=dict)

    @property
    def trained(self) -> bool:
        return bool(self.doses)


class RhomeEngine:
    """The engine, driven one day at a time."""

    def __init__(self, library: ExerciseLibrary) -> None:
        self.library = library
        self.timeline = RecoveryTimeline()
        self.ledger = ContributionLedger(
            {
                Channel.LOCAL_FATIGUE: ENGINE_PARAMETERS.value("local_half_life_h"),
                Channel.NEUROMUSCULAR: ENGINE_PARAMETERS.value("neuromuscular_half_life_h"),
                Channel.SYSTEMIC: ENGINE_PARAMETERS.value("systemic_half_life_h"),
            },
            ENGINE_PARAMETERS.value("adaptation_time_constant_days") * 24.0,
        )
        self.state_engine = StateEngine(self.timeline, ledger=self.ledger)
        self.trace_builder = TraceBuilder(self.ledger)
        self.recovery_engine = RecoveryContextEngine()
        self.capacity = CapacityModel()
        self.body_mass = BodyMassTracker()
        self.confidence_engine = ConfidenceEngine()
        self.effort_history = _EffortHistory()
        self._steps_history: list[float] = []

    # --- the loop ----------------------------------------------------------

    def process_day(self, day: DayInput) -> DayResult:
        wake_h = day.day_index * 24.0 + WAKE_H
        train_h = day.day_index * 24.0 + TRAIN_H

        # 1. Recovery context, from the load carried into the day.
        context = self.recovery_engine.step(day.reading, self.state_engine.state.systemic)
        self.confidence_engine.observe_day(context, day.reading.channels_present)

        # 2. The multiplier holds from waking until the next waking.
        self.timeline.append(RecoveryWindow(wake_h, context.rho))

        # 3. Advance to waking, then declare the day's background activity.
        self.state_engine.advance_to(wake_h)
        self.body_mass.observe(day.body_mass_kg)
        amplitude = 0.0
        if day.steps is not None:
            self._steps_history.append(day.steps)
            window = self._steps_history[-_STEPS_BASELINE_DAYS:]
            amplitude = self.state_engine.set_activity_window(
                day.steps, sum(window) / len(window), wake_h
            )

        result = DayResult(
            day_index=day.day_index,
            state=self.state_engine.state,
            recovery=context,
            activity_amplitude=amplitude,
        )
        if not day.sets:
            self.state_engine.advance_to(wake_h + 16.0)
            result.state = self.state_engine.state.copy()
            result.confidence = self.confidence_engine.report(
                self.capacity, self.state_engine.state.t_h
            )
            self._build_traces(result, context)
            return result

        # 4. Freeze every projection BEFORE any of the day's sets are seen.
        self.state_engine.advance_to(train_h)
        session_key = f"d{day.day_index:04d}"
        freeze_inputs = {}
        for logged in day.sets:
            exercise = self.library[logged.exercise_id]
            identity = capacity_identity(exercise, logged.equipment_context)
            freeze_inputs.setdefault(identity, (exercise, logged.equipment_context))
        for identity, (exercise, equipment_context) in sorted(freeze_inputs.items()):
            frozen = self.capacity.freeze(
                exercise, self.state_engine.state, session_key, equipment_context
            )
            if frozen is not None:
                result.projections[identity] = frozen
        smoothed_mass = self.body_mass.smoothed()

        # 5. Ingest the session, capturing the state acting on each set.
        pending: list[tuple[LoggedSet, SetDose, float, EngineState]] = []
        local_positions: dict = defaultdict(int)
        for index, logged in enumerate(day.sets):
            exercise = self.library[logged.exercise_id]
            raw_dose = transform_set(
                logged, exercise,
                novelty=self.state_engine.novelty_for(logged.exercise_id),
                imputed_rir=self.effort_history.impute(logged.exercise_id),
            )
            dose = amplify_within_session_fatigue(raw_dose, local_positions)
            if (reserve := logged.repetitions_in_reserve()) is not None:
                self.effort_history.observe(logged.exercise_id, reserve)
            # The fatigue acting *during* a set is the state before its own dose.
            state_at_set = self.state_engine.state.copy()
            self.state_engine.apply_dose(
                dose, train_h + index * 0.02, logged.exercise_id,
                source=f"set:d{day.day_index:04d}:{logged.exercise_id}:{logged.set_number}",
                label=(
                    f"{exercise.name}, set {logged.set_number}"
                    + (" (effort not logged)" if dose.effort_imputed else "")
                ),
            )
            result.doses.append((logged, dose))
            self.confidence_engine.observe_set(dose, exercise, train_h + index * 0.02)
            observed = observed_performance(logged, dose, exercise, smoothed_mass)
            if observed is not None:
                pending.append((logged, dose, observed, state_at_set))
            if dose.local_fatigue or dose.neuromuscular or dose.systemic:
                for muscle in dose.local_fatigue:
                    local_positions[muscle] += 1

        # 6. Score the residual against the sealed projection, using the *first*
        # eligible set of each exercise. That is the set the pre-session
        # projection was a claim about. Taking the best set instead would
        # compare a maximum over several noisy draws against a single
        # prediction, which is positively biased by construction and was
        # inflating the mean residual by roughly six per cent.
        scored: list[tuple[str, str, str | None, float, float, float, float]] = []
        first_seen: set[str] = set()
        for logged, dose, observed, _state_at_set in pending:
            exercise = self.library[logged.exercise_id]
            identity = capacity_identity(exercise, logged.equipment_context)
            if identity in first_seen:
                continue
            first_seen.add(identity)
            capacity_before = self.capacity.capacity(identity)
            if capacity_before is None:
                continue
            residual, record = self.capacity.score_against_projection(
                exercise, session_key, observed, logged.equipment_context
            )
            scored.append((
                identity, logged.exercise_id, logged.equipment_context,
                observed, record.projected, residual, capacity_before,
            ))

        # 7. Every eligible set contributes evidence, but correlated sets from
        # one exercise-context produce one robust capacity movement.
        grouped: dict[str, list[tuple[LoggedSet, SetDose, float, EngineState]]] = {}
        for logged, dose, observed, state_at_set in pending:
            self.confidence_engine.observe_performance(
                logged.exercise_id, train_h, session_key
            )
            identity = capacity_identity(
                self.library[logged.exercise_id], logged.equipment_context
            )
            grouped.setdefault(identity, []).append((logged, dose, observed, state_at_set))

        updates = {}
        for identity, rows in grouped.items():
            logged = rows[0][0]
            exercise = self.library[logged.exercise_id]
            updates[identity] = self.capacity.update_session(
                exercise,
                session_key,
                [(observed, state, dose.intensity_confidence)
                 for _logged, dose, observed, state in rows],
                equipment_context=logged.equipment_context,
                is_anchor=logged.exercise_id in day.anchor_exercise_ids,
            )

        # The observation record is written last, because ``capacity_after``
        # is only true once every set of the session has been learned from.
        for identity, base_id, _context, observed, projected, residual, before in scored:
            update = updates[identity]
            result.observations.append(
                PerformanceObservation(
                    exercise_id=identity, session_key=session_key,
                    observed=observed, projected=projected, log_residual=residual,
                    capacity_before=before,
                    capacity_after=update.after,
                    learning_rate=update.learning_rate,
                    is_anchor=base_id in day.anchor_exercise_ids,
                    base_exercise_id=base_id,
                )
            )

        self.state_engine.advance_to(wake_h + 16.0)
        result.state = self.state_engine.state.copy()
        result.confidence = self.confidence_engine.report(
            self.capacity, self.state_engine.state.t_h
        )
        self._build_traces(result, context)
        return result

    def _build_traces(self, result: DayResult, context: RecoveryContext) -> None:
        """Explain every channel the day ends with.

        Folding spent impulses happens first and only here: the ledger must be
        stable while a trace is being read from it, and the close of the day is
        the one point at which nothing is mid-computation.
        """
        state = self.state_engine.state
        self.ledger.fold_old(state.t_h, state.rho_clock)
        confidence = result.confidence.fatigue if result.confidence else None

        for muscle in state.local_fatigue:
            if state.local_fatigue[muscle] <= 0.0:
                continue
            record = self.trace_builder.record(
                Channel.LOCAL_FATIGUE, muscle.value, state, context, confidence
            )
            result.traces[record.state_id] = record

        for channel in (Channel.NEUROMUSCULAR, Channel.SYSTEMIC):
            record = self.trace_builder.record(channel, "", state, context, confidence)
            if record.value > 0.0:
                result.traces[record.state_id] = record

    # --- looking forward ---------------------------------------------------

    def project(
        self,
        horizons_h: tuple[float, ...] = DEFAULT_HORIZONS_H,
        *,
        counterfactual: tuple[CounterfactualSet, ...] = (),
        assumed_rho: float = 1.0,
    ) -> Projection:
        """Where the athlete's state goes from here, with or without a session.

        Reads the engine's current state and leaves it untouched.
        """
        return project(
            self.state_engine,
            self.library,
            horizons_h,
            assumed_rho=assumed_rho,
            counterfactual=counterfactual,
            confidence=self.confidence_engine.report(
                self.capacity, self.state_engine.state.t_h
            ),
        )

    def run(self, days: list[DayInput]) -> list[DayResult]:
        return [self.process_day(day) for day in days]
