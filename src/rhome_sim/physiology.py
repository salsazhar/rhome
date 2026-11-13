"""True latent physiology (``DATA.md`` §16.2).

This is the ground truth the inference engine is later scored against. It must
be structurally richer than the engine's model, because an engine inverting its
own generator proves nothing.

Five structural differences are built in here. Each is a real modelling choice
rather than added noise, and each gives the engine something it cannot recover
exactly no matter how much data it sees.

**Two-component recovery.** The engine models local fatigue as a single
exponential. Here it has a fast component with a roughly seven-hour half-life
and a slow component with the athlete's own sampled half-life, and damaging work
loads the slow component preferentially. A single exponential fitted to a sum of
two can match the middle of the curve or its tails, but not both.

**State-dependent accumulation.** In the engine, ten sets deliver ten times the
impulse of one. Here a set landing on already-fatigued tissue does more, so the
same session costs more when it follows a hard one.

**Volume interacting with proximity to failure.** Required explicitly by
``DATA.md`` §16.2. The engine multiplies its effort and repetition terms
independently; here the failure penalty grows with the near-failure work already
performed in the session, so five sets to failure cost more than five times one.

**Systemic drag on local recovery.** The engine modulates recovery only through
wearable-derived context. Here a high systemic load also slows local recovery
directly, coupling channels the engine treats as independent.

**Smooth functional forms.** Where the engine interpolates lookup tables, this
uses continuous functions with different curvature. The two agree in the middle
of the range and diverge at its edges.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rhome_core.exercises import Exercise
from rhome_core.muscles import Muscle
from rhome_core.timeline import LN2
from rhome_sim.athlete import AthleteParameters

__all__ = [
    "SimConstants",
    "SIM_PHYSIOLOGY",
    "LatentState",
    "SetImpulse",
    "Physiology",
]


@dataclass(frozen=True)
class SimConstants:
    """Simulator physiology constants.

    Deliberately not registered as specification parameters (decision D8): the
    documents describe the *engine's* model, and these are the simulator's own
    invention. Registering them would imply a commitment the documents never
    make.
    """

    #: Half-life of the fast, metabolic fatigue component.
    fast_half_life_h: float = 7.0
    #: Fraction of a set's fatigue entering the slow component at baseline.
    slow_fraction_base: float = 0.52
    #: How much eccentric demand shifts fatigue into the slow component.
    slow_fraction_eccentric: float = 0.22
    #: How much proximity to failure shifts fatigue into the slow component.
    slow_fraction_failure: float = 0.18

    #: Scale of the per-set local fatigue impulse.
    local_scale: float = 0.115
    #: Amplification of a set's cost by fatigue already present.
    state_dependence: float = 0.30
    #: Growth of the failure penalty with near-failure work already done.
    volume_failure_interaction: float = 0.055

    neuromuscular_scale: float = 0.105
    neuromuscular_intensity_exponent: float = 2.4
    neuromuscular_compoundness_exponent: float = 1.2

    systemic_scale: float = 0.072
    systemic_cost_exponent: float = 1.1
    #: Coupling from neuromuscular strain into systemic load.
    systemic_neuromuscular_coupling: float = 0.12

    #: How much systemic load slows local recovery.
    systemic_recovery_drag: float = 0.28

    adaptation_time_constant_h: float = 42.0 * 24.0
    adaptation_gain: float = 0.0135
    #: Saturation of adaptive stimulus within a session.
    adaptation_saturation: float = 6.0

    #: Peak novelty multiplier decay constant, in exposures.
    novelty_decay_exposures: float = 3.0
    novelty_cap: float = 1.40


SIM_PHYSIOLOGY = SimConstants()


@dataclass
class LatentState:
    """The athlete's true hidden state at one instant."""

    t_h: float
    fatigue_fast: dict[Muscle, float] = field(default_factory=dict)
    fatigue_slow: dict[Muscle, float] = field(default_factory=dict)
    systemic: float = 0.0
    neuromuscular: float = 0.0
    adaptation: dict[Muscle, float] = field(default_factory=dict)

    @classmethod
    def initial(cls, t_h: float = 0.0) -> "LatentState":
        return cls(
            t_h=t_h,
            fatigue_fast={m: 0.0 for m in Muscle},
            fatigue_slow={m: 0.0 for m in Muscle},
            adaptation={m: 0.0 for m in Muscle},
        )

    def local_fatigue(self, muscle: Muscle) -> float:
        """Total local fatigue. The engine sees only this sum, never the split."""
        return self.fatigue_fast[muscle] + self.fatigue_slow[muscle]

    def local_fatigue_all(self) -> dict[Muscle, float]:
        return {m: self.local_fatigue(m) for m in Muscle}

    def copy(self) -> "LatentState":
        return LatentState(
            t_h=self.t_h,
            fatigue_fast=dict(self.fatigue_fast),
            fatigue_slow=dict(self.fatigue_slow),
            systemic=self.systemic,
            neuromuscular=self.neuromuscular,
            adaptation=dict(self.adaptation),
        )


@dataclass(frozen=True)
class SetImpulse:
    """What one set actually did, recorded for the hidden latent tables."""

    local: dict[Muscle, float]
    stimulus: dict[Muscle, float]
    neuromuscular: float
    systemic: float
    novelty_multiplier: float
    state_amplification: float
    interaction_multiplier: float


def _effort_term(true_rir: float) -> float:
    """Smooth proximity-to-failure cost, normalised to 1.0 at 2 RIR.

    The engine interpolates a six-point lookup table. This is a continuous
    exponential with different curvature: the two agree near 2 RIR and diverge
    at both ends.
    """
    return math.exp(-0.16 * (true_rir - 2.0))


def _volume_term(reps: int) -> float:
    """Saturating repetition cost.

    The engine uses a clipped linear ramp. This saturates, so the marginal cost
    of the twentieth repetition is far below that of the fifth.
    """
    return 0.72 + 0.28 * (1.0 - math.exp(-reps / 7.0))


class Physiology:
    """Evolves the true latent state through time and training."""

    def __init__(
        self,
        athlete: AthleteParameters,
        constants: SimConstants = SIM_PHYSIOLOGY,
        state: LatentState | None = None,
    ) -> None:
        self.athlete = athlete
        self.k = constants
        self.state = state or LatentState.initial()
        #: Near-failure work performed per muscle in the current session.
        self._session_hard_work: dict[Muscle, float] = {m: 0.0 for m in Muscle}

    # --- time evolution ----------------------------------------------------

    def advance_to(self, t_h: float, recovery_propensity: float = 1.0) -> None:
        """Evolve state forward with no new training input.

        ``recovery_propensity`` is the athlete's true recovery quality over the
        interval, supplied by the recovery model. It is *not* the engine's
        wearable-derived multiplier, which is an estimate of this.
        """
        if t_h < self.state.t_h:
            raise ValueError(
                f"cannot evolve backwards: {t_h:.2f} precedes {self.state.t_h:.2f}"
            )
        dt = t_h - self.state.t_h
        if dt == 0:
            return
        if recovery_propensity <= 0:
            raise ValueError("recovery propensity must be positive")

        # Systemic load drags on local recovery: a structural coupling the
        # engine does not model.
        drag = 1.0 / (1.0 + self.k.systemic_recovery_drag * self.state.systemic)
        rate = recovery_propensity * drag

        for muscle in Muscle:
            fast = LN2 / self.k.fast_half_life_h
            slow = LN2 / self.athlete.local_half_life_h[muscle]
            self.state.fatigue_fast[muscle] *= math.exp(-rate * fast * dt)
            self.state.fatigue_slow[muscle] *= math.exp(-rate * slow * dt)
            self.state.adaptation[muscle] *= math.exp(-dt / self.k.adaptation_time_constant_h)

        self.state.systemic *= math.exp(
            -recovery_propensity * LN2 / self.athlete.systemic_half_life_h * dt
        )
        self.state.neuromuscular *= math.exp(
            -recovery_propensity * LN2 / self.athlete.neuromuscular_half_life_h * dt
        )
        self.state.t_h = t_h

    # --- training input ----------------------------------------------------

    def begin_session(self) -> None:
        """Reset within-session accumulators.

        Session boundaries affect only the volume-by-failure interaction, never
        the state itself, so nothing is discontinuous at a session boundary.
        """
        self._session_hard_work = {m: 0.0 for m in Muscle}

    def novelty_multiplier(self, exposure_count: int) -> float:
        """Fatigue inflation for an unfamiliar movement.

        Decays with repeated exposure. ``exposure_count`` is how many times the
        athlete has performed this exercise before.
        """
        if exposure_count < 0:
            raise ValueError("exposure count cannot be negative")
        excess = self.athlete.novelty_sensitivity * math.exp(
            -exposure_count / self.k.novelty_decay_exposures
        )
        return min(1.0 + excess, self.k.novelty_cap)

    def apply_set(
        self,
        exercise: Exercise,
        reps: int,
        true_rir: float,
        relative_intensity: float,
        exposure_count: int,
    ) -> SetImpulse:
        """Apply one working set and return what it did."""
        if reps < 1:
            raise ValueError("a set must have at least one repetition")
        if true_rir < 0:
            raise ValueError("true RIR cannot be negative")
        if not 0.0 < relative_intensity <= 1.0:
            raise ValueError("relative intensity must lie in (0, 1]")

        effort = _effort_term(true_rir)
        volume = _volume_term(reps)
        novelty = self.novelty_multiplier(exposure_count)
        failure_proximity = max(0.0, (3.0 - true_rir) / 3.0)

        eccentric = exercise.eccentric_demand or 0.5
        slow_fraction = min(
            0.95,
            self.k.slow_fraction_base
            + self.k.slow_fraction_eccentric * eccentric
            + self.k.slow_fraction_failure * failure_proximity,
        )

        local: dict[Muscle, float] = {}
        amplifications: list[float] = []
        interactions: list[float] = []

        for muscle, contribution in exercise.fatigue_contributions.items():
            # Fatigued tissue takes more damage from the same work.
            amplification = 1.0 + self.k.state_dependence * self.state.local_fatigue(muscle)
            # Near-failure work compounds within a session.
            interaction = 1.0 + (
                self.k.volume_failure_interaction
                * self._session_hard_work[muscle]
                * failure_proximity
            )
            amplifications.append(amplification)
            interactions.append(interaction)

            impulse = (
                self.k.local_scale
                * contribution
                * effort
                * volume
                * novelty
                * amplification
                * interaction
            )
            self.state.fatigue_fast[muscle] += impulse * (1.0 - slow_fraction)
            self.state.fatigue_slow[muscle] += impulse * slow_fraction
            local[muscle] = impulse
            self._session_hard_work[muscle] += contribution * failure_proximity

        # Adaptive stimulus, with diminishing returns as session volume grows.
        stimulus: dict[Muscle, float] = {}
        for muscle, contribution in exercise.stimulus_contributions.items():
            raw = contribution * effort * min(1.0, reps / 5.0)
            saturated = raw / (1.0 + self.state.adaptation[muscle] / self.k.adaptation_saturation)
            self.state.adaptation[muscle] += self.k.adaptation_gain * saturated
            stimulus[muscle] = saturated

        neuromuscular = (
            self.k.neuromuscular_scale
            * exercise.compoundness ** self.k.neuromuscular_compoundness_exponent
            * relative_intensity ** self.k.neuromuscular_intensity_exponent
            * effort
        )
        self.state.neuromuscular += neuromuscular

        systemic = (
            self.k.systemic_scale
            * exercise.systemic_cost ** self.k.systemic_cost_exponent
            * effort
            * volume
            * (1.0 + self.k.systemic_neuromuscular_coupling * self.state.neuromuscular)
        )
        self.state.systemic += systemic

        return SetImpulse(
            local=local,
            stimulus=stimulus,
            neuromuscular=neuromuscular,
            systemic=systemic,
            novelty_multiplier=novelty,
            state_amplification=sum(amplifications) / len(amplifications),
            interaction_multiplier=sum(interactions) / len(interactions),
        )
