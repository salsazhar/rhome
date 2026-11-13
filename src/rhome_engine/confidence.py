"""Per-channel confidence (``MODEL.tex`` §Confidence).

Confidence in v0 is a bounded, deterministic, decomposable index of *evidence
sufficiency*. It is not a probability, and `RESEARCH.md` §17 forbids presenting
it as one: it does not say how likely a state estimate is to be correct, only
how much evidence stands behind it.

A single global number would be actively misleading, because the conditions
that undermine one channel leave the others alone. A fortnight away from the
gym makes fatigue states *more* certain — they have decayed to near zero —
while making capacity estimates stale. So confidence is reported per channel,
and every channel reports the component currently holding it down. "Limited:
no wearable data for six of the last seven nights" tells the athlete what to
do; a bare 0.43 does not.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from rhome_core.exercises import CoefficientSource, Exercise
from rhome_core.intensity import IntensityConfidence
from rhome_core.parameters import CORE_PARAMETERS
from rhome_engine.dose import SetDose
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.performance import CapacityModel
from rhome_engine.recovery import RecoveryContext

__all__ = [
    "Band",
    "Component",
    "Confidence",
    "ConfidenceReport",
    "ConfidenceEngine",
]

_WEARABLE_CHANNELS = 5
LN2 = math.log(2.0)


class Band(StrEnum):
    """The three-band display label (``MODEL.tex`` §Display and claim discipline)."""

    HIGH = "high"
    MODERATE = "moderate"
    LIMITED = "limited"


def _band(value: float) -> Band:
    if value >= ENGINE_PARAMETERS.value("confidence_band_high"):
        return Band.HIGH
    if value >= ENGINE_PARAMETERS.value("confidence_band_moderate"):
        return Band.MODERATE
    return Band.LIMITED


@dataclass(frozen=True)
class Component:
    """One reason confidence is where it is."""

    name: str
    value: float
    detail: str


@dataclass(frozen=True)
class Confidence:
    """One channel's confidence, with the components that produced it."""

    value: float
    components: tuple[Component, ...]

    @property
    def band(self) -> Band:
        return _band(self.value)

    @property
    def binding_reason(self) -> Component:
        """The component holding confidence down.

        Ties break toward the earlier component, so the label is stable from
        day to day rather than flickering between two equal causes.
        """
        return min(self.components, key=lambda c: c.value)

    @property
    def label(self) -> str:
        return f"{self.band.value}: {self.binding_reason.detail}"


@dataclass(frozen=True)
class ConfidenceReport:
    """Confidence across every channel at one instant."""

    fatigue: Confidence
    neuromuscular: Confidence
    systemic: Confidence
    capacity: dict[str, Confidence] = field(default_factory=dict)

    def projection(self, horizon_h: float) -> Confidence:
        """Confidence in a state projected ``horizon_h`` hours ahead.

        Falls with horizon because the projection assumes no training, and the
        further out it reaches the less that assumption is worth.
        """
        if horizon_h < 0:
            raise ValueError("a projection horizon cannot be negative")
        scale = ENGINE_PARAMETERS.value("confidence_projection_scale_h")
        decay = math.exp(-horizon_h / scale)
        days = horizon_h / 24.0
        return Confidence(
            value=self.fatigue.value * decay,
            components=(
                *self.fatigue.components,
                Component(
                    "projection horizon",
                    decay,
                    f"projected {days:.0f} days ahead, assuming no training",
                ),
            ),
        )


class ConfidenceEngine:
    """Accumulates the evidence each confidence component summarises."""

    def __init__(self) -> None:
        self._nights: deque[int] = deque(
            maxlen=ENGINE_PARAMETERS.value("confidence_wearable_window_nights")
        )
        self._days_observed = 0
        self._explanation = 1.0
        self._unexplained_rms = 0.0
        # Dose quality is a ratio of two sums that decay at the same rate, so
        # it is carried as two accumulators rather than a list of every set
        # ever performed. Between events both are multiplied by the same
        # factor, which leaves the ratio unchanged — that is the point: an
        # absence of training must not degrade dose quality.
        self._dose_weighted = 0.0
        self._dose_total = 0.0
        self._dose_at_h = 0.0
        self._performances: dict[str, deque[float]] = {}
        #: Lifetime *sessions* containing this exercise — not sets. The
        #: ablation that set the saturation counted scored observations, one
        #: per exercise per session, and counting sets instead would saturate
        #: after about nine sessions rather than twenty-five.
        self._lifetime: dict[str, int] = {}
        self._counted: set[tuple[str, str]] = set()

    # --- accumulating evidence ---------------------------------------------

    def observe_day(self, context: RecoveryContext, reading_channels: int) -> None:
        self._nights.append(reading_channels)
        self._days_observed += 1
        self._explanation = context.explanation_confidence
        self._unexplained_rms = context.unexplained_rms

    def observe_set(self, dose: SetDose, exercise: Exercise, at_h: float) -> None:
        r"""Fold one set into dose quality, weighted by what will survive of it.

        A set that contributed nothing to the state — a warm-up, or a set with
        no effort recorded — is skipped rather than counted at some default
        weight. The section weights each set by its surviving contribution
        $\sigma_i$, and a zero contribution is a zero weight. Counting them at
        weight one instead put 1 848 warm-ups into the average at the lowest
        quality grade and held dose confidence at 0.69 for the whole record,
        for sets that never touched a single state variable.
        """
        surviving = sum(dose.local_fatigue.values())
        if surviving <= 0.0:
            return
        self._decay_dose_to(at_h)
        quality = _intensity_weight(dose.intensity_confidence) * _source_weight(
            exercise.coefficient_source
        )
        self._dose_weighted += surviving * quality
        self._dose_total += surviving

    def observe_performance(
        self, exercise_id: str, at_h: float, session_key: str | None = None
    ) -> None:
        """Record that an eligible capacity observation happened.

        Density counts every eligible set; maturity counts sessions, because
        that is what the ablation measured. Several sets of one exercise in one
        session are one session's worth of evidence about that exercise.
        """
        self._performances.setdefault(exercise_id, deque()).append(at_h)
        key = (exercise_id, session_key if session_key is not None else str(at_h))
        if key not in self._counted:
            self._counted.add(key)
            self._lifetime[exercise_id] = self._lifetime.get(exercise_id, 0) + 1

    def _decay_dose_to(self, at_h: float) -> None:
        if self._dose_total <= 0.0:
            self._dose_at_h = at_h
            return
        elapsed = max(0.0, at_h - self._dose_at_h)
        self._dose_at_h = at_h
        half_life = ENGINE_PARAMETERS.value("local_half_life_h")
        factor = math.exp(-LN2 * elapsed / half_life)
        self._dose_weighted *= factor
        self._dose_total *= factor
        # The magnitude of these sums is not free to change: it is what decides
        # how much an old set counts against a new one. Only a floor is
        # applied, and both sums are scaled by the same constant to reach it,
        # so the ratio is exact and a set from four years ago still counts for
        # nothing beside a set from today. Renormalising to one instead — the
        # obvious way to avoid underflow — silently restored full weight to
        # evidence that had decayed away.
        floor = 1e-250
        if 0.0 < self._dose_total < floor:
            rescale = floor / self._dose_total
            self._dose_weighted *= rescale
            self._dose_total = floor

    # --- components ---------------------------------------------------------

    def wearable_completeness(self) -> Component:
        if not self._nights:
            fraction = 0.0
        else:
            fraction = sum(self._nights) / (len(self._nights) * _WEARABLE_CHANNELS)
        value = (
            ENGINE_PARAMETERS.value("confidence_wearable_floor")
            + ENGINE_PARAMETERS.value("confidence_wearable_span") * fraction
        )
        blank = sum(1 for n in self._nights if n == 0)
        if blank:
            detail = f"no wearable data on {blank} of the last {len(self._nights)} nights"
        elif fraction < 1.0:
            detail = f"{fraction:.0%} of wearable channels present over the last week"
        else:
            detail = "complete wearable data"
        return Component("wearable completeness", value, detail)

    def baseline_maturity(self) -> Component:
        target = ENGINE_PARAMETERS.value("confidence_baseline_days")
        maturity = min(1.0, self._days_observed / target)
        value = (
            ENGINE_PARAMETERS.value("confidence_baseline_floor")
            + ENGINE_PARAMETERS.value("confidence_baseline_span") * maturity
        )
        detail = (
            "personal baselines are established"
            if maturity >= 1.0
            else f"{self._days_observed} of {target} days of personal baseline"
        )
        return Component("baseline maturity", value, detail)

    def dose_quality(self) -> Component:
        if self._dose_total <= 0.0:
            return Component("dose quality", 1.0, "no training on record yet")
        value = self._dose_weighted / self._dose_total
        detail = (
            "effort and exercise costs are well determined"
            if value > 0.95
            else "some sets have loosely determined effort or exercise cost"
        )
        return Component("dose quality", value, detail)

    def explanation(self) -> Component:
        detail = (
            "autonomic readings behave as the model expects"
            if self._explanation > 0.95
            else (
                f"autonomic readings have run {self._unexplained_rms:.1f} standard "
                f"deviations from expectation"
            )
        )
        return Component("unexplained autonomic deviation", self._explanation, detail)

    def observation_density(self, exercise_id: str, at_h: float) -> Component:
        times = self._performances.get(exercise_id, ())
        window = ENGINE_PARAMETERS.value("confidence_observation_window_h")
        recent = [t for t in times if at_h - t <= window]
        saturation = ENGINE_PARAMETERS.value("confidence_observation_saturation")
        density = min(1.0, len(recent) / saturation)

        if times:
            since = at_h - max(times)
            grace = ENGINE_PARAMETERS.value("confidence_staleness_grace_h")
            scale = ENGINE_PARAMETERS.value("confidence_staleness_scale_h")
            staleness = math.exp(-max(0.0, since - grace) / scale)
        else:
            since = math.inf
            staleness = 1.0

        value = density * staleness
        if not times:
            detail = "never performed"
        elif since > ENGINE_PARAMETERS.value("confidence_staleness_grace_h"):
            detail = f"not trained for {since / 24:.0f} days"
        elif len(recent) < saturation:
            detail = f"{len(recent)} of {saturation} recent sets on this exercise"
        else:
            detail = "trained often and recently"
        return Component("observation density", value, detail)

    def capacity_maturity(self, exercise_id: str) -> Component:
        """Whether the engine has seen enough of this exercise to have an opinion.

        Distinct from observation density, which counts the last 28 days and is
        a statement about recency. The two come apart: an athlete returning to
        a lift after a year satisfies density within a fortnight on an estimate
        resting on four observations.

        The Checkpoint 2 ablation measured where that matters — the engine does
        not beat a recency baseline below about twenty lifetime observations —
        and through that whole period capacity confidence read ``high``,
        because density was satisfied and nothing else was watching.
        """
        seen = self._lifetime.get(exercise_id, 0)
        saturation = ENGINE_PARAMETERS.value("confidence_maturity_saturation")
        floor = ENGINE_PARAMETERS.value("confidence_maturity_floor")
        span = ENGINE_PARAMETERS.value("confidence_maturity_span")
        value = floor + span * min(1.0, seen / saturation)
        detail = (
            "enough history on this exercise to judge it"
            if seen >= saturation
            else f"{seen} of {saturation} sets on this exercise all-time"
        )
        return Component("capacity maturity", value, detail)

    def fit_quality(self, exercise_id: str, capacity: CapacityModel) -> Component:
        spread = capacity.residual_spread(exercise_id)
        reference = ENGINE_PARAMETERS.value("confidence_fit_reference_sd")
        floor = ENGINE_PARAMETERS.value("confidence_fit_floor")
        if spread is None:
            return Component("fit quality", 1.0, "too few results to judge fit yet")
        value = min(1.0, max(floor, reference / max(spread, reference)))
        detail = (
            "results land close to prediction"
            if value > 0.95
            else f"results scatter {spread / reference:.1f}× wider than expected"
        )
        return Component("fit quality", value, detail)

    # --- the report ---------------------------------------------------------

    def report(self, capacity: CapacityModel, at_h: float) -> ConfidenceReport:
        self._decay_dose_to(at_h)
        state_components = (
            self.wearable_completeness(),
            self.baseline_maturity(),
            self.dose_quality(),
            self.explanation(),
        )
        # No training-recency term, deliberately. An absence of training is
        # informative about fatigue rather than a gap in the evidence
        # (``DATA.md`` §19.5), so a missed-session block must not degrade it.
        state_value = math.prod(c.value for c in state_components)
        state = Confidence(state_value, state_components)

        per_exercise = {}
        for exercise_id in self._performances:
            # Maturity last: ties break toward the earlier component, and a
            # saturated term reported as the binding reason reads as a
            # constraint when nothing is constraining.
            components = (
                self.observation_density(exercise_id, at_h),
                self.fit_quality(exercise_id, capacity),
                self.capacity_maturity(exercise_id),
            )
            per_exercise[exercise_id] = Confidence(
                math.prod(c.value for c in components), components
            )

        return ConfidenceReport(
            fatigue=state, neuromuscular=state, systemic=state, capacity=per_exercise
        )


def _intensity_weight(confidence: IntensityConfidence | None) -> float:
    # A set logged with no effort rating at all is weaker evidence than one
    # whose rating merely sat outside the tabulated domain, but the section
    # defines no fourth grade. It takes the low weight, which is the most
    # cautious value available rather than a new parameter invented here.
    if confidence is None or confidence is IntensityConfidence.LOW:
        return ENGINE_PARAMETERS.value("confidence_intensity_low")
    if confidence is IntensityConfidence.MEDIUM:
        return ENGINE_PARAMETERS.value("confidence_intensity_medium")
    return 1.0


def _source_weight(source: CoefficientSource) -> float:
    if source is CoefficientSource.DERIVED:
        return CORE_PARAMETERS.value("derived_coefficient_confidence")
    return 1.0
