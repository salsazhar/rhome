"""State evolution through continuous time (``MODEL.tex`` §Time evolution,
§Temporal conventions and continuity).

Carries the four dose channels forward between events. Everything here is
first-order exponential decay with impulses, which is the transparent v0 choice:
the fitness-fatigue literature supports the dynamical form while cautioning that
its predictive performance is mixed, so Rhome borrows the structure without the
claim that it is physiologically complete.

Two properties are load-bearing.

**Nothing resets at a calendar boundary.** State evolves in hours from event
timestamps. Two inputs nonetheless arrive as daily aggregates --- the recovery
multiplier and the step count --- and both are reconciled with continuous time
rather than deposited at midnight.

**The recovery multiplier scales the decay rate, not the state.** A good night
does not remove fatigue; it makes fatigue drain faster. That distinction is why
a missing wearable night contributes nothing rather than a penalty: with no
evidence, the multiplier is neutral and the state simply decays at its ordinary
rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rhome_core.muscles import Muscle
from rhome_core.timeline import (
    WAKING_WINDOW_H,
    RecoveryTimeline,
    decay_with_constant_input,
)
from rhome_engine.dose import SetDose
from rhome_engine.parameters import ENGINE_PARAMETERS, STEPS_LOCAL_COEFF

__all__ = ["EngineState", "StateEngine"]


@dataclass
class EngineState:
    """The engine's estimate of the athlete's state at one instant."""

    t_h: float = 0.0
    local_fatigue: dict[Muscle, float] = field(
        default_factory=lambda: {m: 0.0 for m in Muscle}
    )
    neuromuscular: float = 0.0
    systemic: float = 0.0
    adaptation: dict[Muscle, float] = field(
        default_factory=lambda: {m: 0.0 for m in Muscle}
    )
    #: Exponentially weighted load traces, displayed separately. No injury
    #: threshold attaches to their ratio (``MODEL.tex``, Impellizzeri et al.).
    short_load_trace: float = 0.0
    long_load_trace: float = 0.0
    #: The accumulated recovery integral, :math:`\int \rho(s)\,ds`.
    #:
    #: Every recovery-modulated channel decays by
    #: :math:`\exp[-\ln 2 / h \cdot (\Phi(t) - \Phi(t_i))]`, so one number
    #: per state is enough to price any impulse's survival exactly. The
    #: explanation trace reads this rather than integrating :math:`\rho` for
    #: itself, which is what stops a decomposition drifting from the state it
    #: claims to decompose.
    rho_clock: float = 0.0

    def copy(self) -> "EngineState":
        return EngineState(
            t_h=self.t_h,
            local_fatigue=dict(self.local_fatigue),
            neuromuscular=self.neuromuscular,
            systemic=self.systemic,
            adaptation=dict(self.adaptation),
            short_load_trace=self.short_load_trace,
            long_load_trace=self.long_load_trace,
            rho_clock=self.rho_clock,
        )

    def total_local_fatigue(self) -> float:
        return sum(self.local_fatigue.values())


class StateEngine:
    """Evolves the engine's state through time and training input."""

    def __init__(
        self,
        timeline: RecoveryTimeline | None = None,
        state: EngineState | None = None,
        ledger: "ContributionLedger | None" = None,
    ) -> None:
        self.timeline = timeline or RecoveryTimeline()
        self.state = state or EngineState()
        self.ledger = ledger
        self._exposures: dict[str, int] = {}
        #: (start, end, amplitude) of the current background activity window.
        self._activity: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._local_half_life = ENGINE_PARAMETERS.value("local_half_life_h")
        self._neuro_half_life = ENGINE_PARAMETERS.value("neuromuscular_half_life_h")
        self._systemic_half_life = ENGINE_PARAMETERS.value("systemic_half_life_h")
        self._adaptation_tau_h = ENGINE_PARAMETERS.value("adaptation_time_constant_days") * 24.0
        self._adaptation_gain = ENGINE_PARAMETERS.value("adaptation_gain")
        self._short_tau_h = ENGINE_PARAMETERS.value("load_trace_short_days") * 24.0
        self._long_tau_h = ENGINE_PARAMETERS.value("load_trace_long_days") * 24.0

    # --- background activity ----------------------------------------------

    def set_activity_window(
        self, steps: float, baseline_steps: float, wake_h: float
    ) -> float:
        """Declare a day's activity as a background input over the waking window.

        Steps arrive as a daily total but are not deposited at an instant. They
        are held as a constant input rate across sixteen waking hours, and any
        evolution overlapping that window integrates it in closed form.

        Declaring the window rather than applying it immediately matters
        because training happens *inside* it. A session at five in the
        afternoon sits in the middle of a day's walking, and a design that
        applied the whole day's activity before the session could not represent
        that without running time backwards.
        """
        amplitude = max(
            0.0,
            (steps - baseline_steps) / ENGINE_PARAMETERS.value("steps_scale"),
        )
        self._activity = (wake_h, wake_h + WAKING_WINDOW_H, amplitude)
        return amplitude

    def _activity_rate(self, muscle: Muscle | None) -> float:
        """Constant input rate for a channel during the activity window."""
        _, _, amplitude = self._activity
        if amplitude == 0.0:
            return 0.0
        if muscle is None:
            coeff = ENGINE_PARAMETERS.value("steps_systemic_coeff")
        else:
            coeff = STEPS_LOCAL_COEFF.get(muscle.value, 0.0)
        return coeff * amplitude / WAKING_WINDOW_H

    # --- time evolution ----------------------------------------------------

    def advance_to(self, t_h: float) -> None:
        """Evolve to an instant with no new training input.

        The interval is split at recovery-window boundaries and at the edges of
        the activity window, so the recovery multiplier and the background
        activity load are both applied over exactly the spans where they hold.
        """
        if t_h < self.state.t_h - 1e-9:
            raise ValueError(
                f"cannot evolve backwards: {t_h:.3f} precedes {self.state.t_h:.3f}"
            )
        while self.state.t_h < t_h - 1e-12:
            self._advance_segment(min(t_h, self._next_boundary(t_h)))
        self.state.t_h = max(self.state.t_h, t_h)

    def _next_boundary(self, limit: float) -> float:
        """The next instant at which a rate changes."""
        boundaries = [limit]
        start, end, _ = self._activity
        for edge in (start, end):
            if self.state.t_h < edge < limit:
                boundaries.append(edge)
        for window in self.timeline.windows:
            if self.state.t_h < window.start_h < limit:
                boundaries.append(window.start_h)
        return min(boundaries)

    def _advance_segment(self, t_h: float) -> None:
        """Evolve across one span over which every rate is constant."""
        dt = t_h - self.state.t_h
        if dt <= 0:
            return
        rho = self.timeline.rho_at(self.state.t_h)
        start, end, _ = self._activity
        active = start <= self.state.t_h < end

        # Background activity enters as a constant input rate, not an impulse,
        # so its contribution has to be extracted from the closed form: the
        # part of the new value that is not the old value decayed. Recording it
        # at the segment's end is exact from that instant onward, and omitting
        # it would leave the trace's shares summing to less than one on any day
        # the athlete walked.
        local_decay = math.exp(-math.log(2.0) / self._local_half_life * rho * dt)
        systemic_decay = math.exp(-math.log(2.0) / self._systemic_half_life * rho * dt)
        activity_label = "daily activity"

        for muscle in Muscle:
            rate = self._activity_rate(muscle) if active else 0.0
            previous = self.state.local_fatigue[muscle]
            self.state.local_fatigue[muscle] = decay_with_constant_input(
                previous, rate, self._local_half_life, dt, rho,
            )
            if self.ledger is not None and rate > 0.0:
                self.ledger.record(
                    "local_fatigue", muscle.value,
                    self.state.local_fatigue[muscle] - previous * local_decay,
                    t_h, self.state.rho_clock + rho * dt,
                    f"activity:{int(self.state.t_h // 24)}", activity_label,
                )
            # The slow adaptive state is not modulated by recovery context:
            # adaptation is not something a good night's sleep accelerates.
            self.state.adaptation[muscle] *= math.exp(-dt / self._adaptation_tau_h)

        systemic_rate = self._activity_rate(None) if active else 0.0
        previous_systemic = self.state.systemic
        self.state.systemic = decay_with_constant_input(
            previous_systemic, systemic_rate, self._systemic_half_life, dt, rho,
        )
        if self.ledger is not None and systemic_rate > 0.0:
            self.ledger.record(
                "systemic", "",
                self.state.systemic - previous_systemic * systemic_decay,
                t_h, self.state.rho_clock + rho * dt,
                f"activity:{int(self.state.t_h // 24)}", activity_label,
            )
        self.state.neuromuscular *= math.exp(
            -math.log(2.0) / self._neuro_half_life * rho * dt
        )
        self.state.short_load_trace *= math.exp(-dt / self._short_tau_h)
        self.state.long_load_trace *= math.exp(-dt / self._long_tau_h)
        self.state.rho_clock += rho * dt
        self.state.t_h = t_h

    # --- training input ----------------------------------------------------

    def apply_dose(
        self,
        dose: SetDose,
        t_h: float,
        exercise_id: str | None = None,
        source: str | None = None,
        label: str | None = None,
    ) -> None:
        """Apply one set's dose at its own timestamp."""
        self.advance_to(t_h)
        if self.ledger is not None:
            self.ledger.record_set(
                dose, t_h, self.state.rho_clock,
                source or f"set:{exercise_id}@{t_h:.2f}",
                label or (exercise_id or "unnamed set"),
                self._adaptation_gain,
            )
        for muscle, value in dose.local_fatigue.items():
            self.state.local_fatigue[muscle] += value
        for muscle, value in dose.stimulus.items():
            self.state.adaptation[muscle] += self._adaptation_gain * value
        self.state.neuromuscular += dose.neuromuscular
        self.state.systemic += dose.systemic
        self.state.short_load_trace += dose.systemic
        self.state.long_load_trace += dose.systemic
        if exercise_id is not None and dose.local_fatigue:
            self._exposures[exercise_id] = self._exposures.get(exercise_id, 0) + 1

    def fork(self, timeline: RecoveryTimeline) -> "StateEngine":
        """A copy that can be evolved without touching this one.

        Everything that decides how state moves comes across — the state
        itself, the declared activity window, the exposure counts novelty
        depends on — except the ledger, because a hypothetical future has no
        contributors to explain. The recovery timeline is supplied by the
        caller, since a forecast makes its own assumption about it.

        Projection is built on this rather than on its own decay arithmetic. A
        second implementation would agree today and drift after the next change
        to either, and the drift would be silent.
        """
        forked = StateEngine(timeline, state=self.state.copy())
        forked._activity = self._activity
        forked._exposures = dict(self._exposures)
        return forked

    # --- novelty -----------------------------------------------------------

    def exposure_count(self, exercise_id: str) -> int:
        return self._exposures.get(exercise_id, 0)

    def novelty_for(self, exercise_id: str) -> float:
        """Fatigue inflation for an unfamiliar movement.

        ``MODEL.tex`` fixes the cap and states that the numerical form is an
        engineering prior without giving one, so this decay is the engine's
        choice and is recorded as such in the parameter registry.
        """
        cap = ENGINE_PARAMETERS.value("novelty_cap")
        decay = ENGINE_PARAMETERS.value("novelty_decay_exposures")
        return 1.0 + (cap - 1.0) * math.exp(-self.exposure_count(exercise_id) / decay)
