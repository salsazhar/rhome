"""Performance generation chain (``DATA.md`` §9.5).

This is the module that decides whether the synthetic dataset is a real test.

Every observable set is produced as a *consequence* of hidden state, in a fixed
causal order: latent capacity, then the fatigue acting at that moment, then a
stochastic shock, and only then the load and repetitions actually performed,
the true repetitions in reserve, and finally the noisy value the athlete logs.

Assigning a performance number alongside the set — rather than deriving the set
from it — would make the dataset a description of the answer rather than
evidence for it.

Three structural differences from the engine live here, on top of those
established in L1.2 and L1.3.

**A different repetitions-to-failure curve.** The engine inverts the tabulated
Nuzzo population relationship. This uses a smooth exponential of different
shape, then scales it by an athlete-specific endurance factor per exercise.
Nuzzo et al. reported large between-person variation precisely here, so the
engine's population prior is systematically wrong for this athlete by an amount
it cannot observe.

**A different fatigue-to-performance form.** The engine multiplies capacity by
``exp(-Σλx)``. This uses the hyperbolic ``1/(1 + Σλx)``. The two agree to first
order and diverge as fatigue accumulates, which is exactly where the engine's
predictions matter most.

**Heteroskedastic, occasionally extreme shocks.** Ordinary day-to-day variation
scales with the exercise, and a small fraction of sessions carry a much larger
shock with no observable cause — scenario S11's "random bad day", which must
not permanently move the engine's capacity estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from rhome_core.exercises import Exercise, ExerciseKind, ExerciseLibrary
from rhome_core.muscles import Muscle
from rhome_sim.athlete import AthleteParameters
from rhome_sim.physiology import Physiology
from rhome_sim.programme import Prescription, SessionPlan

__all__ = [
    "PerformanceConstants",
    "SIM_PERFORMANCE",
    "RealisedSet",
    "PerformanceModel",
    "true_relative_intensity",
    "true_max_reps",
]


@dataclass(frozen=True)
class PerformanceConstants:
    """Simulator performance constants (decision D8: not specification values)."""

    #: Fatigue sensitivities. Near the engine's priors but not equal to them,
    #: and applied through a different functional form.
    lambda_local: float = 0.075
    lambda_neuromuscular: float = 0.050
    lambda_systemic: float = 0.035

    #: Probability a session carries an unexplained large negative shock.
    bad_day_probability: float = 0.020
    bad_day_scale: float = 0.055
    #: Probability of an unusually good day.
    good_day_probability: float = 0.020
    good_day_scale: float = 0.040

    #: Load increments by equipment, in kilograms.
    load_increment: tuple[tuple[str, float], ...] = (
        ("barbell", 2.5), ("machine", 5.0), ("cable", 2.5),
        ("dumbbell", 2.0), ("bodyweight", 2.5),
    )

    #: Fractional gain in capacity per unit of adaptive stimulus, applied once
    #: per session. Calibrated so a trained athlete gains roughly 10-20% on the
    #: main lifts across two years, which is what the training literature
    #: describes for someone already past the novice phase.
    adaptation_to_capacity: float = 0.00013
    #: Learning gain on an unfamiliar movement, decaying with exposure.
    novelty_learning_rate: float = 0.004
    novelty_learning_exposures: float = 12.0


SIM_PERFORMANCE = PerformanceConstants()

# Smooth relative-intensity curve. Deliberately a different functional form
# from the engine's tabulated Nuzzo interpolation, though calibrated to sit
# close to it through the middle of the range.
# A + B = 1.0 exactly, so a single maximal repetition is 100% of the
# one-repetition maximum by construction and the curve inverts cleanly.
# With A = 0.30 the curve returned 1.02 at one repetition, was clipped to
# 1.00, and inverting that clipped value gave 1.51 repetitions.
_A, _B, _C = 0.28, 0.72, 0.055


def true_relative_intensity(reps_to_failure: float) -> float:
    """Fraction of one-repetition maximum a set of ``n`` maximal reps implies."""
    if reps_to_failure < 1:
        raise ValueError("repetitions to failure must be at least 1")
    return min(1.0, _A + _B * math.exp(-_C * (reps_to_failure - 1.0)))


def true_max_reps(relative_intensity: float, endurance: float = 1.0) -> float:
    """Repetitions achievable at a relative intensity, for this athlete."""
    if not 0.0 < relative_intensity <= 1.0:
        raise ValueError("relative intensity must lie in (0, 1]")
    if relative_intensity <= _A + 1e-9:
        return 60.0 * endurance
    ratio = (relative_intensity - _A) / _B
    reps = 1.0 - math.log(min(1.0, ratio)) / _C
    return max(1.0, reps * endurance)


@dataclass(frozen=True)
class RealisedSet:
    """One performed set: what was observed, and the truth behind it."""

    # --- observable ---
    exercise_id: str
    set_number: int
    set_type: str
    load_kg: float
    reps: int
    logged_rpe: float | None
    logged_rir: float | None
    # --- simulator-only ---
    true_rir: float
    true_relative_intensity: float
    true_expressible_capacity: float
    performance_shock: float
    fatigue_factor: float
    is_pr: bool = False


@dataclass
class _ExerciseState:
    """Progression and learning state for one exercise."""

    capacity_kg: float
    exposures: int = 0
    working_load: dict[tuple[int, int], float] = field(default_factory=dict)


class PerformanceModel:
    """Turns session plans into performed sets, driven by hidden state."""

    def __init__(
        self,
        athlete: AthleteParameters,
        library: ExerciseLibrary,
        rng: np.random.Generator,
        constants: PerformanceConstants = SIM_PERFORMANCE,
    ) -> None:
        self.athlete = athlete
        self.library = library
        self.rng = rng
        self.k = constants
        self._increment = dict(constants.load_increment)
        self.state: dict[str, _ExerciseState] = {
            exercise_id: _ExerciseState(capacity_kg=capacity)
            for exercise_id, capacity in athlete.initial_capacity_kg.items()
        }
        self._best: dict[str, float] = {}

    # --- effective load ----------------------------------------------------

    def effective_load(self, exercise: Exercise, external_kg: float, body_mass_kg: float) -> float:
        """System load: body mass counts where the exercise carries it."""
        if exercise.bodyweight_fraction is None:
            return external_kg
        return exercise.bodyweight_fraction * body_mass_kg + external_kg

    def _external_from_effective(
        self, exercise: Exercise, effective_kg: float, body_mass_kg: float
    ) -> float:
        if exercise.bodyweight_fraction is None:
            return effective_kg
        return effective_kg - exercise.bodyweight_fraction * body_mass_kg

    def _round_to_increment(self, exercise: Exercise, load_kg: float) -> float:
        step = self._increment[exercise.equipment.value]
        return round(load_kg / step) * step

    def _clamp_external(self, exercise: Exercise, load_kg: float) -> float:
        """Keep external load physically meaningful for the exercise kind.

        Negative external load means assistance, which only exists for the
        assisted kinds. A bodyweight movement whose own weight already exceeds
        the target simply gets no added load: the athlete performs fewer
        repetitions instead, which the repetition model already handles.
        """
        if exercise.exercise_kind is ExerciseKind.ASSISTED_REPS:
            return load_kg
        if exercise.exercise_kind is ExerciseKind.REPS_ONLY:
            return max(0.0, load_kg)
        return max(self._increment[exercise.equipment.value], load_kg)

    # --- the causal chain --------------------------------------------------

    def expressible_capacity(self, exercise: Exercise, physiology: Physiology) -> tuple[float, float]:
        """Step 1–2: neutral capacity, reduced by the fatigue acting now.

        Uses the hyperbolic form ``1/(1 + Σλx)`` rather than the engine's
        exponential. They agree to first order and diverge as fatigue
        accumulates.
        """
        capacity = self.state[exercise.exercise_id].capacity_kg
        exposure = sum(
            weight * physiology.state.local_fatigue(muscle)
            for muscle, weight in exercise.performance_weights.items()
        )
        burden = (
            self.k.lambda_local * exposure
            + self.k.lambda_neuromuscular * exercise.compoundness * physiology.state.neuromuscular
            + self.k.lambda_systemic * physiology.state.systemic
        )
        factor = 1.0 / (1.0 + max(0.0, burden))
        return capacity * factor, factor

    def _session_shock(self) -> float:
        """Step 3: a bounded stochastic shock, occasionally much larger.

        The rare large negative shock is scenario S11: a conspicuous bad
        session with no observable cause, which must not permanently depress
        the engine's capacity estimate.
        """
        draw = self.rng.random()
        if draw < self.k.bad_day_probability:
            return float(math.exp(-abs(self.rng.normal(0.0, self.k.bad_day_scale)) - 0.03))
        if draw < self.k.bad_day_probability + self.k.good_day_probability:
            return float(math.exp(abs(self.rng.normal(0.0, self.k.good_day_scale)) + 0.01))
        return 1.0

    def realise_prescription(
        self,
        prescription: Prescription,
        physiology: Physiology,
        body_mass_kg: float,
        session_shock: float,
        set_offset: int = 0,
    ) -> list[RealisedSet]:
        """Perform one prescribed exercise, set by set."""
        exercise = self.library[prescription.exercise_id]
        state = self.state[exercise.exercise_id]
        endurance = self.athlete.rep_endurance[exercise.exercise_id]
        key = (prescription.rep_low, prescription.rep_high)

        neutral, _ = self.expressible_capacity(exercise, physiology)
        if key not in state.working_load:
            # First exposure at this rep range: pick a load that puts the
            # midpoint of the range at roughly the prescribed effort.
            # Loaded toward the upper part of the range rather than its midpoint.
            # A midpoint load leaves the athlete able to exceed the range on
            # ordinary days, and since repetitions are capped there, the surplus
            # appears as inflated repetitions in reserve.
            target_fail = (0.35 * prescription.rep_low + 0.65 * prescription.rep_high) + prescription.target_rir
            implied = true_relative_intensity(max(1.0, target_fail / endurance))
            state.working_load[key] = self._clamp_external(
                exercise,
                self._round_to_increment(
                    exercise, self._external_from_effective(
                        exercise, implied * state.capacity_kg, body_mass_kg
                    )
                ),
            )

        external = state.working_load[key]
        effective = self.effective_load(exercise, external, body_mass_kg)
        performed: list[RealisedSet] = []
        noise_scale = self.athlete.performance_noise_scale[exercise.exercise_id]

        for index in range(prescription.sets):
            expressible, factor = self.expressible_capacity(exercise, physiology)
            set_shock = float(self.rng.lognormal(0.0, noise_scale)) * session_shock
            realised = expressible * set_shock

            # Step 4: how many repetitions are feasible, and how many the
            # athlete chooses to perform within the prescribed range.
            intensity = min(1.0, effective / max(realised, 1e-6))
            capable = true_max_reps(intensity, endurance)
            # Double progression: perform as many repetitions as the target
            # effort allows, up to the top of the prescribed range. Choosing a
            # repetition count at random within the range would mean the top of
            # the range was almost never reached across every set, so the load
            # would never advance and would fall steadily behind capacity.
            afforded = math.floor(capable - prescription.target_rir + 0.5)
            reps = int(max(1, min(prescription.rep_high, afforded, math.floor(capable))))

            # Step 5: true repetitions in reserve follow from what happened.
            true_rir = max(0.0, capable - reps)

            # Step 6: what the athlete believes and logs.
            #
            # Recorded as a whole number of repetitions in reserve, which is
            # what the athlete's logger accepts. The granularity matters: an
            # RPE band of 9.5-10 spans 0 to 0.5 RIR, so half-point logging puts
            # two values into it and whole-number logging puts one. Under
            # half-points the reporting-error tail piled onto RPE 10 hard
            # enough to make "maximal" the most common entry in the log.
            reported = (
                true_rir
                + self.athlete.rir_bias[exercise.exercise_id]
                + self.rng.normal(0.0, self.athlete.rir_noise_sd)
            )
            reported = float(np.clip(round(reported), 0.0, 8.0))

            performed.append(
                RealisedSet(
                    exercise_id=exercise.exercise_id,
                    set_number=set_offset + index + 1,
                    set_type="working",
                    load_kg=round(external, 2),
                    reps=reps,
                    # RIR is what the athlete records; RPE is derived from it
                    # for display, per the Zourdos convention.
                    logged_rir=reported,
                    logged_rpe=10.0 - reported,
                    true_rir=round(true_rir, 3),
                    true_relative_intensity=round(intensity, 8),
                    true_expressible_capacity=round(realised, 3),
                    performance_shock=round(set_shock, 4),
                    fatigue_factor=round(factor, 4),
                )
            )

            physiology.apply_set(
                exercise=exercise,
                reps=reps,
                true_rir=true_rir,
                relative_intensity=max(0.05, intensity),
                exposure_count=state.exposures,
            )

            # A lifter who lands *at* the bottom of the range strips weight
            # before the next set, anticipating the shortfall rather than
            # waiting for it. Reacting only after a set has already gone short
            # is too late: that set is already recorded below the prescribed
            # band, which is where the repetition distribution leaks.
            if reps <= prescription.rep_low and index + 1 < prescription.sets:
                external = self._clamp_external(
                    exercise,
                    self._round_to_increment(
                        exercise, external - self._increment[exercise.equipment.value]
                    ),
                )
                effective = self.effective_load(exercise, external, body_mass_kg)

        state.exposures += 1
        self._progress(exercise, prescription, performed)
        return performed

    # --- progression and adaptation ---------------------------------------

    def _progress(
        self, exercise: Exercise, prescription: Prescription, performed: list[RealisedSet]
    ) -> None:
        """Double progression: add load once the top of the range is met.

        Load is retained when effort ran higher than intended, and reduced
        after a clearly failed progression, per ``DATA.md`` §9.4.
        """
        key = (prescription.rep_low, prescription.rep_high)
        step = self._increment[exercise.equipment.value]
        reps = [s.reps for s in performed]
        rirs = [s.true_rir for s in performed]

        # Judged on the top set, as a lifter does: "I hit six on my first set,
        # so I add weight next time." Requiring *every* set to reach the top of
        # the range means within-session fatigue blocks progression almost
        # always, and the load drifts below capacity.
        if performed[0].reps >= prescription.rep_high and rirs[0] >= prescription.target_rir - 0.5:
            # Take a double step when every set finished comfortably clear of
            # the intended effort. A single step per session lets the load fall
            # steadily behind a growing capacity, which inflates repetitions in
            # reserve and smears the logged-effort distribution.
            comfortable = rirs[0] > prescription.target_rir + 1.0
            self.state[exercise.exercise_id].working_load[key] = self._clamp_external(
                exercise,
                self.state[exercise.exercise_id].working_load[key]
                + step * (2 if comfortable else 1),
            )
        elif max(reps) < prescription.rep_low or performed[0].reps < prescription.rep_low - 1:
            # Judged on the first set, not the last. Repetitions falling away
            # across a session is ordinary fatigue; a *first* set below the
            # intended range means the load itself is too heavy, and leaving it
            # there pushes those sets into a lower band than prescribed.
            self.state[exercise.exercise_id].working_load[key] = self._clamp_external(
                exercise, self.state[exercise.exercise_id].working_load[key] - step
            )

    def apply_adaptation(self, physiology: Physiology, multiplier: float = 1.0) -> None:
        """Convert accumulated adaptive stimulus into capacity.

        Capacity grows from adaptation and from familiarity with the movement.
        The engine never sees either; it must infer capacity from performance.
        """
        for exercise_id, state in self.state.items():
            exercise = self.library[exercise_id]
            stimulus = sum(
                weight * physiology.state.adaptation[muscle] * self.athlete.adaptation_rate[muscle]
                for muscle, weight in exercise.stimulus_contributions.items()
            )
            total_weight = sum(exercise.stimulus_contributions.values()) or 1.0
            gain = self.k.adaptation_to_capacity * stimulus / total_weight
            learning = self.k.novelty_learning_rate * math.exp(
                -state.exposures / self.k.novelty_learning_exposures
            )
            state.capacity_kg *= 1.0 + multiplier * (gain + learning)

    def realise_session(
        self,
        plan: SessionPlan,
        physiology: Physiology,
        body_mass_kg: float,
        adaptation_multiplier: float = 1.0,
        force_bad_session: bool = False,
    ) -> list[RealisedSet]:
        """Perform a whole session in the documented causal order.

        ``adaptation_multiplier`` suppresses capacity growth for the plateau
        scenario; ``force_bad_session`` guarantees the unexplained negative
        shock that scenario S11 requires on a specific day, rather than leaving
        it to chance.
        """
        physiology.begin_session()
        shock = (
            float(math.exp(-abs(self.rng.normal(0.10, self.k.bad_day_scale)) - 0.05))
            if force_bad_session
            else self._session_shock()
        )
        sets: list[RealisedSet] = []
        for prescription in plan.prescriptions:
            sets.extend(
                self.realise_prescription(
                    prescription, physiology, body_mass_kg, shock, set_offset=0
                )
            )
        self.apply_adaptation(physiology, multiplier=adaptation_multiplier)
        return sets

    def mark_personal_records(self, sets: list[RealisedSet]) -> list[bool]:
        """Observable PR flags, from prior logs only — never from latent truth."""
        flags = []
        for performed in sets:
            estimate = performed.load_kg * (1.0 + performed.reps / 30.0)
            best = self._best.get(performed.exercise_id)
            is_pr = best is not None and estimate > best * 1.001
            self._best[performed.exercise_id] = max(best or 0.0, estimate)
            flags.append(bool(is_pr))
        return flags
