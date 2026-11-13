"""Performance and capacity (``MODEL.tex`` §Performance model).

Three quantities that are easy to confuse and must not be:

**Observed performance** is what a set implies about capacity right now:
effective load divided by the relative intensity the set implies.

**Estimated capacity** is the slow underlying trend, updated with bounded
influence so no single session rewrites it.

**Projected performance** is capacity reduced by the fatigue acting at a moment,
and it is the only one of the three that can be scored, because it is a claim
about something not yet observed.

The ordering rule of ``DATA.md`` §9.5 is enforced structurally rather than by
convention. A projection is *frozen* before a session is revealed; the frozen
record is immutable and content-addressed; and a residual can only be scored
against a projection that was frozen strictly before the session it predicts.
Recomputing a projection after seeing its own session is the one mistake that
would invalidate every performance metric in the project while making all of
them look better, so it is made impossible rather than merely discouraged.
"""

from __future__ import annotations

import hashlib
import math
import statistics as st
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

from rhome_core.exercises import Equipment, Exercise
from rhome_core.intensity import IntensityConfidence
from rhome_core.muscles import Muscle
from rhome_engine.dose import LoggedSet, SetDose
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.state import EngineState

__all__ = [
    "BodyMassTracker",
    "FrozenProjection",
    "PerformanceObservation",
    "SessionCapacityUpdate",
    "CapacityModel",
    "capacity_identity",
    "effective_load",
    "observed_performance",
    "expected_suppression",
]


class LeakageError(RuntimeError):
    """Raised when the ordering that prevents target leakage is violated."""


# --- effective load --------------------------------------------------------

class BodyMassTracker:
    """Smoothed body mass for bodyweight-involving exercises.

    Daily scale readings carry roughly a kilogram of water, glycogen and
    gut-content noise. Feeding that straight into performance would inject
    day-to-day variation into an estimate of strength, so a centred median over
    a short window is used instead.
    """

    def __init__(self) -> None:
        self._window = int(ENGINE_PARAMETERS.value("body_mass_window_days"))
        self._recent: deque[float] = deque(maxlen=self._window)
        self._last_known: float | None = None

    def observe(self, body_mass_kg: float | None) -> None:
        if body_mass_kg is not None:
            self._recent.append(body_mass_kg)
            self._last_known = body_mass_kg

    def smoothed(self) -> float | None:
        """The current estimate, or ``None`` if nothing has ever been recorded."""
        if self._recent:
            return st.median(self._recent)
        return self._last_known


def effective_load(exercise: Exercise, external_kg: float, body_mass_kg: float | None) -> float | None:
    """System load: body mass counts where the exercise carries it."""
    if exercise.bodyweight_fraction is None:
        return external_kg
    if body_mass_kg is None:
        return None
    return exercise.bodyweight_fraction * body_mass_kg + external_kg


def observed_performance(
    logged: LoggedSet, dose: SetDose, exercise: Exercise, body_mass_kg: float | None
) -> float | None:
    """Capacity implied by one set, or ``None`` where it cannot be inferred."""
    if not dose.eligible_for_performance or not dose.relative_intensity:
        return None
    load = effective_load(exercise, logged.load_kg, body_mass_kg)
    if load is None or load <= 0:
        return None
    return load / dose.relative_intensity


# --- expected performance --------------------------------------------------

def performance_weights(exercise: Exercise) -> dict[Muscle, float]:
    """``omega_me``: the fatigue vector normalised to unit sum."""
    return exercise.performance_weights


def expected_suppression(exercise: Exercise, state: EngineState) -> tuple[float, dict[str, float]]:
    """Fractional reduction in expressible performance, and its breakdown."""
    p = ENGINE_PARAMETERS.value
    local_exposure = sum(
        weight * state.local_fatigue[muscle]
        for muscle, weight in exercise.performance_weights.items()
    )
    terms = {
        "local": p("lambda_local") * local_exposure,
        "neuromuscular": p("lambda_neuromuscular") * exercise.compoundness * state.neuromuscular,
        "systemic": p("lambda_systemic") * state.systemic,
    }
    exponent = min(max(sum(terms.values()), 0.0), p("suppression_clip"))
    return 1.0 - math.exp(-exponent), terms


# --- the frozen projection -------------------------------------------------

@dataclass(frozen=True)
class FrozenProjection:
    """A prediction, sealed before its session is revealed.

    Content-addressed: any alteration changes the digest, so a projection
    cannot be quietly rewritten after the fact.
    """

    exercise_id: str
    session_key: str
    frozen_at_h: float
    capacity: float
    projected: float
    suppression: float
    terms: dict[str, float]
    digest: str = ""

    def compute_digest(self) -> str:
        payload = "|".join(
            [
                self.exercise_id, self.session_key, f"{self.frozen_at_h:.6f}",
                f"{self.capacity:.9f}", f"{self.projected:.9f}",
                f"{self.suppression:.9f}",
                ",".join(f"{k}={v:.9f}" for k, v in sorted(self.terms.items())),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def verify(self) -> bool:
        return self.digest == self.compute_digest()


@dataclass(frozen=True)
class PerformanceObservation:
    """One scored set: what was predicted, what happened, and the difference."""

    exercise_id: str
    session_key: str
    observed: float
    projected: float
    log_residual: float
    capacity_before: float
    capacity_after: float
    learning_rate: float
    is_anchor: bool = False
    #: Library id without an equipment-context suffix.
    base_exercise_id: str = ""


@dataclass
class _ExerciseCapacity:
    capacity: float | None = None
    observations: int = 0
    sessions: int = 0
    warmup: list[float] = field(default_factory=list)
    innovations: deque[float] = field(default_factory=lambda: deque(maxlen=20))


@dataclass(frozen=True)
class SessionCapacityUpdate:
    """The one capacity movement an exercise-context may make in a session."""

    capacity_id: str
    before: float | None
    after: float | None
    learning_rate: float
    huber_clip: float
    innovation: float | None
    evidence_sets: int
    session_cap: float


_CONTEXTUAL_EQUIPMENT = frozenset({Equipment.CABLE, Equipment.MACHINE})


def capacity_identity(exercise: Exercise, equipment_context: str | None = None) -> str:
    """Return the comparable load scale on which capacity is estimated."""
    context = equipment_context.strip() if equipment_context else ""
    if exercise.equipment not in _CONTEXTUAL_EQUIPMENT or not context:
        return exercise.exercise_id
    return f"{exercise.exercise_id}::{context}"


class CapacityModel:
    """Estimates underlying capacity, and enforces the ordering that protects it."""

    def __init__(self) -> None:
        self._state: dict[str, _ExerciseCapacity] = {}
        self._frozen: dict[tuple[str, str], FrozenProjection] = {}
        self._latest_by_exercise: dict[str, float] = {}
        self._residuals_by_exercise: dict[str, deque[float]] = {}
        #: Sessions where a freeze was attempted, including those that produced
        #: nothing because capacity did not yet exist. Distinguishing "no
        #: projection because there was nothing to predict" from "no projection
        #: because nobody froze one" is what keeps the guard meaningful.
        self._freeze_attempted: set[tuple[str, str]] = set()
        self._scored: set[tuple[str, str]] = set()

    # --- capacity ----------------------------------------------------------

    def capacity(self, exercise_id: str, equipment_context: str | None = None) -> float | None:
        capacity_id = (
            f"{exercise_id}::{equipment_context.strip()}"
            if equipment_context and equipment_context.strip()
            else exercise_id
        )
        entry = self._state.get(capacity_id)
        if entry is not None:
            return entry.capacity
        return self._latest_by_exercise.get(exercise_id)

    def observations(self, exercise_id: str, equipment_context: str | None = None) -> int:
        capacity_id = (
            f"{exercise_id}::{equipment_context.strip()}"
            if equipment_context and equipment_context.strip()
            else exercise_id
        )
        if capacity_id in self._state:
            return self._state[capacity_id].observations
        prefix = f"{exercise_id}::"
        return sum(
            entry.observations for key, entry in self._state.items()
            if key.startswith(prefix)
        )

    def is_confident(self, exercise_id: str) -> bool:
        return self.observations(exercise_id) >= ENGINE_PARAMETERS.value(
            "capacity_confident_observations"
        )

    def residual_spread(self, exercise_id: str) -> float | None:
        """Robust spread of the last twenty log residuals (``MODEL.tex`` §Confidence).

        The median absolute deviation, scaled to agree with the standard
        deviation on normal data. A plain standard deviation would let one
        genuinely bad session — an illness, a missed meal — read as a model
        that is not tracking the exercise, which is the opposite of what fit
        confidence is meant to report.
        """
        residuals = self._residuals_by_exercise.setdefault(
            exercise_id, deque(maxlen=20)
        )
        if len(residuals) < 4:
            return None
        centre = st.median(residuals)
        deviation = st.median([abs(r - centre) for r in residuals])
        return 1.4826 * deviation

    # --- projection --------------------------------------------------------

    def project(
        self,
        exercise: Exercise,
        state: EngineState,
        equipment_context: str | None = None,
    ) -> tuple[float, float, dict] | None:
        """Expected performance now, or ``None`` before capacity is established."""
        capacity = self.capacity(capacity_identity(exercise, equipment_context))
        if capacity is None:
            return None
        suppression, terms = expected_suppression(exercise, state)
        return capacity * (1.0 - suppression), suppression, terms

    def freeze(
        self,
        exercise: Exercise,
        state: EngineState,
        session_key: str,
        equipment_context: str | None = None,
    ) -> FrozenProjection | None:
        """Seal a prediction before its session is revealed.

        Refuses to overwrite an existing projection for the same session. A
        second freeze would be a recomputation, which is exactly the thing the
        ordering rule exists to prevent.
        """
        identity = capacity_identity(exercise, equipment_context)
        key = (identity, session_key)
        self._freeze_attempted.add(key)
        if key in self._frozen:
            raise LeakageError(
                f"a projection for {identity} in session {session_key} "
                f"is already frozen; re-freezing would discard the prediction the "
                f"session is meant to test"
            )
        projected = self.project(exercise, state, equipment_context)
        if projected is None:
            return None
        value, suppression, terms = projected
        record = FrozenProjection(
            exercise_id=identity, session_key=session_key,
            frozen_at_h=state.t_h, capacity=self.capacity(identity),
            projected=value, suppression=suppression, terms=dict(terms),
        )
        record = FrozenProjection(**{**record.__dict__, "digest": record.compute_digest()})
        self._frozen[key] = record
        return record

    def frozen(self, exercise_id: str, session_key: str) -> FrozenProjection | None:
        return self._frozen.get((exercise_id, session_key))

    # --- scoring and update ------------------------------------------------

    def score_against_projection(
        self,
        exercise: Exercise,
        session_key: str,
        observed: float,
        equipment_context: str | None = None,
    ) -> tuple[float, FrozenProjection]:
        """Score one observation against its sealed projection.

        Scoring and updating are separate operations because they answer
        different questions and use different data. The residual measures a
        prediction against the *first* eligible set, which is what the
        pre-session projection was a claim about; capacity, by contrast, learns
        from every eligible set, each corrected for the fatigue acting when it
        was performed.
        """
        identity = capacity_identity(exercise, equipment_context)
        record = self._frozen.get((identity, session_key))
        if record is None:
            raise LeakageError(
                f"no frozen projection for {identity} in session "
                f"{session_key}; a residual scored against a projection made "
                f"after the fact measures nothing"
            )
        if not record.verify():
            raise LeakageError(
                f"the frozen projection for {identity} in session "
                f"{session_key} has been altered since it was sealed"
            )
        residual = math.log(observed) - math.log(record.projected)
        self._residuals_by_exercise.setdefault(
            exercise.exercise_id, deque(maxlen=20)
        ).append(residual)
        self._scored.add((identity, session_key))
        return residual, record

    @staticmethod
    def learning_rate_for(
        confidence: IntensityConfidence = IntensityConfidence.HIGH,
        is_anchor: bool = False,
    ) -> float:
        """How fast one session's evidence moves capacity.

        An anchor test is a deliberate measurement and earns the fastest rate;
        a session whose median relative intensity was inferred loosely earns the
        slowest. Exposed because the explanation trace has to report the rate
        that was actually applied rather than the default.
        """
        if is_anchor:
            return ENGINE_PARAMETERS.value("capacity_learning_rate_anchor")
        if confidence is IntensityConfidence.MEDIUM:
            return ENGINE_PARAMETERS.value("capacity_learning_rate_medium")
        return ENGINE_PARAMETERS.value("capacity_learning_rate")

    @staticmethod
    def gain_scheduled(rate: float, sessions: int) -> float:
        """Scale a learning rate by the running-mean gain while young."""
        base = ENGINE_PARAMETERS.value("capacity_learning_rate")
        cap = ENGINE_PARAMETERS.value("capacity_gain_cap")
        multiplier = max(1.0, (1.0 / max(1, sessions)) / base)
        return min(cap, rate * multiplier)

    def robust_scale(
        self, exercise: Exercise, equipment_context: str | None = None
    ) -> float:
        """Per-context robust scale of recent session innovations."""
        identity = capacity_identity(exercise, equipment_context)
        entry = self._state.setdefault(identity, _ExerciseCapacity())
        prior = ENGINE_PARAMETERS.value("capacity_residual_scale_prior")
        if len(entry.innovations) < 4:
            return prior
        centre = st.median(entry.innovations)
        mad = st.median(abs(value - centre) for value in entry.innovations)
        return max(prior, 1.4826 * mad)

    def huber_clip(
        self, exercise: Exercise, equipment_context: str | None = None
    ) -> float:
        return (
            ENGINE_PARAMETERS.value("capacity_huber_k")
            * self.robust_scale(exercise, equipment_context)
        )

    @staticmethod
    def _corrected_observation(
        exercise: Exercise, observed: float, state_at_set: EngineState
    ) -> float:
        suppression, _ = expected_suppression(exercise, state_at_set)
        return observed / max(1e-9, 1.0 - suppression)

    def update_session(
        self,
        exercise: Exercise,
        session_key: str,
        evidence: Sequence[tuple[float, EngineState, IntensityConfidence]],
        *,
        equipment_context: str | None = None,
        is_anchor: bool = False,
    ) -> SessionCapacityUpdate:
        """Apply one robust update to the session's correlated set evidence."""
        identity = capacity_identity(exercise, equipment_context)
        entry = self._state.setdefault(identity, _ExerciseCapacity())
        if not evidence:
            return SessionCapacityUpdate(
                identity, entry.capacity, entry.capacity, 0.0, 0.0, None, 0, 0.0
            )

        corrected_logs = [
            math.log(self._corrected_observation(exercise, observed, state))
            for observed, state, _confidence in evidence
        ]
        # The pre-session projection is scored against the first eligible set,
        # but capacity learns once from the whole session. A median makes the
        # repeated sets robust evidence without pretending they are
        # independent updates; the state at each set removes the fatigue the
        # engine believes was acting at that moment first.
        session_log = st.median(corrected_logs)
        before = entry.capacity

        if entry.capacity is None:
            entry.sessions += 1
            entry.warmup.extend(math.exp(value) for value in corrected_logs)
            if len(entry.warmup) >= ENGINE_PARAMETERS.value("capacity_initial_observations"):
                session_capacity = st.median(entry.warmup)
                prior = self._latest_by_exercise.get(exercise.exercise_id)
                weight = (
                    ENGINE_PARAMETERS.value("capacity_context_prior_weight")
                    if equipment_context and prior is not None else 0.0
                )
                entry.capacity = (
                    math.exp(
                        (math.log(session_capacity) + weight * math.log(prior))
                        / (1.0 + weight)
                    )
                    if weight else session_capacity
                )
                entry.observations = len(entry.warmup)
                self._latest_by_exercise[exercise.exercise_id] = entry.capacity
            return SessionCapacityUpdate(
                identity, before, entry.capacity, 0.0, 0.0, None,
                len(evidence), 0.0,
            )

        key = (identity, session_key)
        if key not in self._frozen and key not in self._freeze_attempted:
            raise LeakageError(
                f"capacity update for {identity} in session {session_key} without "
                "a frozen projection; the prediction must be sealed before the "
                "session that tests it is seen"
            )

        rates = [
            self.learning_rate_for(confidence, is_anchor)
            for _observed, _state, confidence in evidence
        ]
        rate = self.gain_scheduled(st.median(rates), entry.sessions)
        clip = self.huber_clip(exercise, equipment_context)
        innovation = session_log - math.log(entry.capacity)
        raw_delta = rate * max(-clip, min(clip, innovation))
        cap_fraction = (
            ENGINE_PARAMETERS.value("capacity_anchor_session_max_move")
            if is_anchor
            else ENGINE_PARAMETERS.value("capacity_session_max_move")
        )
        log_cap = math.log1p(cap_fraction)
        delta = max(-log_cap, min(log_cap, raw_delta))
        entry.capacity = math.exp(math.log(entry.capacity) + delta)
        entry.observations += len(evidence)
        entry.sessions += 1
        entry.innovations.append(innovation)
        self._latest_by_exercise[exercise.exercise_id] = entry.capacity
        return SessionCapacityUpdate(
            identity, before, entry.capacity, rate, clip, innovation,
            len(evidence), cap_fraction,
        )

    def update_capacity(
        self,
        exercise: Exercise,
        session_key: str,
        observed: float,
        state_at_set: EngineState,
        confidence: IntensityConfidence = IntensityConfidence.HIGH,
        is_anchor: bool = False,
        equipment_context: str | None = None,
    ) -> float | None:
        """Compatibility wrapper: one observation is one session's evidence."""
        update = self.update_session(
            exercise, session_key, [(observed, state_at_set, confidence)],
            equipment_context=equipment_context, is_anchor=is_anchor,
        )
        return update.after

    def score_and_update(
        self,
        exercise: Exercise,
        session_key: str,
        observed: float,
        state_at_session: EngineState,
        confidence: IntensityConfidence = IntensityConfidence.HIGH,
        is_anchor: bool = False,
        equipment_context: str | None = None,
    ) -> PerformanceObservation | None:
        """Score then update, in that order. Convenience for a single set."""
        identity = capacity_identity(exercise, equipment_context)
        entry = self._state.setdefault(identity, _ExerciseCapacity())
        if entry.capacity is None:
            self.update_capacity(
                exercise, session_key, observed, state_at_session, confidence,
                is_anchor, equipment_context,
            )
            return None

        residual, record = self.score_against_projection(
            exercise, session_key, observed, equipment_context
        )
        before = entry.capacity
        update = self.update_session(
            exercise, session_key, [(observed, state_at_session, confidence)],
            equipment_context=equipment_context, is_anchor=is_anchor,
        )
        return PerformanceObservation(
            exercise_id=identity, session_key=session_key,
            observed=observed, projected=record.projected, log_residual=residual,
            capacity_before=before, capacity_after=update.after,
            learning_rate=update.learning_rate, is_anchor=is_anchor,
            base_exercise_id=exercise.exercise_id,
        )
