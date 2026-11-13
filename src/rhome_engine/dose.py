"""Per-set dose transformation (``MODEL.tex`` §§Per-set stimulus, fatigue,
strain and systemic impulse).

Converts one logged set into four separate quantities: adaptive stimulus per
muscle, local fatigue per muscle, neuromuscular strain, and systemic load.

Keeping them separate is the product's central modelling claim. More work
raises both stimulus and fatigue, but not proportionally: the proximity-to-
failure curve for fatigue rises far more steeply near failure than the stimulus
curve does, which is how the model encodes that training to failure costs more
than it buys.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from rhome_core.exercises import Exercise, ExerciseKind
from rhome_core.intensity import IntensityConfidence, relative_intensity, rir_from_rpe
from rhome_core.muscles import Muscle
from rhome_engine.parameters import (
    ENGINE_PARAMETERS,
    PHI_FATIGUE,
    PHI_NEUROMUSCULAR,
    PHI_STIMULUS,
)

__all__ = [
    "LoggedSet", "SetDose", "amplify_within_session_fatigue", "phi",
    "stimulus_rep_term", "fatigue_rep_term", "transform_set",
]

#: Set types contributing to the dose channels, and to performance estimation.
_DOSE_TYPES = frozenset({"working", "backoff", "drop"})
_PERFORMANCE_TYPES = frozenset({"working", "backoff"})


@dataclass(frozen=True)
class LoggedSet:
    """One set as recorded, after parsing and before interpretation."""

    workout_id: str
    exercise_id: str
    set_number: int
    set_type: str
    load_kg: float
    reps: int
    rpe: float | None = None
    rir: float | None = None
    is_pr: bool = False
    equipment_context: str | None = None

    @property
    def effort_recorded(self) -> bool:
        return self.rir is not None or self.rpe is not None

    def repetitions_in_reserve(self) -> float | None:
        """Effort as repetitions in reserve.

        Explicitly logged RIR is preferred over RPE. Where only RPE exists the
        Zourdos convention applies, and the result is treated as a noisy
        observation throughout rather than as ground truth.
        """
        if self.rir is not None:
            return self.rir
        if self.rpe is not None:
            return rir_from_rpe(self.rpe)
        return None


@dataclass(frozen=True)
class SetDose:
    """What one set contributed, and how much the model trusts it."""

    stimulus: dict[Muscle, float] = field(default_factory=dict)
    local_fatigue: dict[Muscle, float] = field(default_factory=dict)
    neuromuscular: float = 0.0
    systemic: float = 0.0
    relative_intensity: float | None = None
    intensity_confidence: IntensityConfidence | None = None
    repetitions_in_reserve: float | None = None
    #: Whether the set may inform performance estimation.
    eligible_for_performance: bool = False
    #: Why a set contributed nothing, where it did not.
    excluded_reason: str | None = None
    #: Whether proximity to failure was imputed rather than logged. Surfaced in
    #: the trace so a displayed number resting on guessed effort says so.
    effort_imputed: bool = False


def amplify_within_session_fatigue(
    dose: SetDose,
    local_positions: dict[Muscle, int],
) -> SetDose:
    """Curve local fatigue by prior muscle position, never by hidden state."""
    if not dose.local_fatigue:
        return dose
    gamma = ENGINE_PARAMETERS.value("within_session_fatigue_gamma")
    cap = int(ENGINE_PARAMETERS.value("within_session_position_cap"))
    return replace(
        dose,
        local_fatigue={
            muscle: value * (1.0 + gamma * min(local_positions.get(muscle, 0), cap))
            for muscle, value in dose.local_fatigue.items()
        },
        # Position is muscle-specific. Applying the global session index to
        # these whole-body channels made an arm exercise late in a workout
        # multiply an unrelated squat's cost. Their existing accumulation is
        # retained until a similarly observable position can be defined.
        neuromuscular=dose.neuromuscular,
        systemic=dose.systemic,
    )


def phi(table, rir: float) -> float:
    """Look up a proximity-to-failure multiplier, interpolating between rows.

    ``MODEL.tex`` defines these by linear interpolation, which matters because
    RPE is logged in half points and produces fractional reserve values.
    """
    if rir < 0:
        raise ValueError("repetitions in reserve cannot be negative")
    keys = sorted(table)
    if rir >= keys[-1]:
        return table[keys[-1]]
    lower = int(rir)
    upper = min(lower + 1, keys[-1])
    span = rir - lower
    return table[lower] + span * (table[upper] - table[lower])


def stimulus_rep_term(reps: int) -> float:
    """Very low-repetition sets are not full hypertrophic doses.

    A single near-maximal repetition and a hard set of eight both reach zero
    reserve, and treating them as equal muscular stimulus would be implausible.
    """
    plateau = ENGINE_PARAMETERS.value("stimulus_rep_plateau")
    slope = ENGINE_PARAMETERS.value("stimulus_rep_slope")
    return 1.0 if reps >= plateau else slope * reps


def fatigue_rep_term(reps: int) -> float:
    """Fatigue rises mildly with repetitions, within clipped bounds."""
    value = (
        ENGINE_PARAMETERS.value("fatigue_rep_intercept")
        + ENGINE_PARAMETERS.value("fatigue_rep_slope") * reps
    )
    return min(
        max(value, ENGINE_PARAMETERS.value("fatigue_rep_floor")),
        ENGINE_PARAMETERS.value("fatigue_rep_ceiling"),
    )


def transform_set(
    logged: LoggedSet,
    exercise: Exercise,
    novelty: float = 1.0,
    imputed_rir: float | None = None,
) -> SetDose:
    """Turn one logged set into its four dose channels.

    Warm-ups contribute nothing. Sets whose relative intensity falls outside
    the evidence's domain still contribute their full dose — the work was
    genuinely performed — and are excluded only from performance estimation,
    because the intensity inversion assumes a set taken from a non-pre-fatigued
    state.
    """
    if logged.reps < 1:
        raise ValueError(f"set {logged.set_number}: repetitions must be positive")

    if logged.set_type not in _DOSE_TYPES:
        return SetDose(excluded_reason=f"set type {logged.set_type!r} carries no dose")
    if not exercise.bears_dose:
        return SetDose(
            excluded_reason=f"exercise kind {exercise.exercise_kind.value!r} carries no dose"
        )

    # A working set with no effort rating is imputed rather than discarded
    # (``MODEL.tex`` §Working sets logged without an effort rating). The work
    # happened and its fatigue is real; forgetting it makes the model
    # optimistic, which is the more harmful direction of error here. The set is
    # marked down to LOW confidence, which lowers confidence in every state it
    # touches, and it never becomes a performance observation.
    rir = logged.repetitions_in_reserve()
    imputed = False
    if rir is None:
        rir = (
            imputed_rir
            if imputed_rir is not None
            else float(ENGINE_PARAMETERS.value("imputed_rir_prior"))
        )
        imputed = True

    intensity, confidence = relative_intensity(logged.reps, rir, exercise.nuzzo_curve.value)
    if imputed:
        confidence = IntensityConfidence.LOW

    cap = ENGINE_PARAMETERS.value("novelty_cap")
    novelty = min(max(1.0, novelty), cap)

    stimulus_factor = phi(PHI_STIMULUS, rir) * stimulus_rep_term(logged.reps)
    fatigue_factor = (
        ENGINE_PARAMETERS.value("local_fatigue_scale")
        * phi(PHI_FATIGUE, rir)
        * fatigue_rep_term(logged.reps)
        * novelty
    )

    neuromuscular = (
        ENGINE_PARAMETERS.value("neuromuscular_scale")
        * exercise.compoundness
        * intensity ** ENGINE_PARAMETERS.value("neuromuscular_intensity_exponent")
        * phi(PHI_NEUROMUSCULAR, rir)
    )
    systemic = (
        ENGINE_PARAMETERS.value("systemic_scale")
        * exercise.systemic_cost
        * phi(PHI_FATIGUE, rir)
        * fatigue_rep_term(logged.reps)
    )

    eligible = (
        logged.set_type in _PERFORMANCE_TYPES
        and confidence is not IntensityConfidence.LOW
    )
    reason = None
    if not eligible:
        if imputed:
            reason = (
                "effort was not recorded, so the dose is imputed and the set "
                "supports no performance estimate"
            )
        elif logged.set_type == "drop":
            reason = "drop segments begin pre-fatigued, so the intensity inversion does not apply"
        else:
            reason = "relative intensity is outside the evidence's domain"

    return SetDose(
        stimulus={m: c * stimulus_factor for m, c in exercise.stimulus_contributions.items()},
        local_fatigue={m: c * fatigue_factor for m, c in exercise.fatigue_contributions.items()},
        neuromuscular=neuromuscular,
        systemic=systemic,
        relative_intensity=intensity,
        intensity_confidence=confidence,
        repetitions_in_reserve=rir,
        eligible_for_performance=eligible,
        excluded_reason=reason,
        effort_imputed=imputed,
    )
