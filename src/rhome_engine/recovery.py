"""Recovery context from wearable data (``MODEL.tex`` §Recovery context).

Turns five nightly measurements into one multiplier on the rate at which
fatigue drains. The multiplier is deliberately conservative — bounded to
[0.80, 1.15] — because HRV and resting heart rate are noisy and non-specific,
and a large swing from a single reading would be a claim the evidence does not
support.

The important structure here is that the autonomic channels are **conditioned
on recent training** before they are used. A rolling personal baseline answers
"is this unusual for you?" but not "is this unusual *given what you did
yesterday?*", and those are different questions. A depressed RMSSD after a heavy
squat session is the expected consequence of training the model already knows
about; the same reading on a rest day is information about something it cannot
see. Only the second should move the multiplier much.

The expectation is not a forecast, and Rhome does not predict wearable data. Its
accuracy is not the point: it exists to split a reading into the part recent
training accounts for and the part it does not. The residual is the useful half.
"""

from __future__ import annotations

import math
import statistics as st
from collections import deque
from dataclasses import dataclass, field

from rhome_engine.parameters import ENGINE_PARAMETERS

__all__ = ["RecoveryReading", "ChannelPartition", "RecoveryContext", "RecoveryContextEngine"]


@dataclass(frozen=True)
class RecoveryReading:
    """One night's wearable summary. Any field may be absent."""

    hrv_rmssd_ms: float | None = None
    resting_hr_bpm: float | None = None
    total_sleep_min: float | None = None
    sleep_efficiency: float | None = None
    temperature_deviation_c: float | None = None

    @property
    def channels_present(self) -> int:
        return sum(
            value is not None
            for value in (
                self.hrv_rmssd_ms, self.resting_hr_bpm, self.total_sleep_min,
                self.sleep_efficiency, self.temperature_deviation_c,
            )
        )


@dataclass(frozen=True)
class ChannelPartition:
    """How one autonomic reading divides between training and everything else."""

    observed_z: float
    expected_z: float
    residual_z: float

    @property
    def explained_share(self) -> float:
        """Fraction of the deviation recent training accounts for.

        Zero where the deviation is entirely unexplained, and one where
        training predicted all of it. Undefined for a reading at baseline,
        which is reported as fully explained because there is nothing to
        explain.
        """
        if abs(self.observed_z) < 1e-9:
            return 1.0
        return max(0.0, min(1.0, 1.0 - abs(self.residual_z) / abs(self.observed_z)))


@dataclass(frozen=True)
class RecoveryContext:
    """The multiplier, and everything needed to explain it."""

    rho: float
    contributions: dict[str, float] = field(default_factory=dict)
    partitions: dict[str, ChannelPartition] = field(default_factory=dict)
    raw_z: dict[str, float] = field(default_factory=dict)
    channels_used: int = 0
    channels_present: int = 0
    unexplained_rms: float = 0.0
    explanation_confidence: float = 1.0

    @property
    def is_neutral(self) -> bool:
        return self.channels_used == 0


class _RollingBaseline:
    """A personal baseline over a fixed window, ignoring missing days."""

    def __init__(self, window_days: int) -> None:
        self._values: deque[float] = deque(maxlen=window_days)

    def observe(self, value: float | None) -> None:
        if value is not None:
            self._values.append(value)

    def z(self, value: float | None, minimum: int) -> float | None:
        """Standardise against the window, or return ``None`` if it cannot.

        A standard deviation computed from three nights is not a baseline, and
        a channel standardised against one would swamp the multiplier through
        sampling noise alone.
        """
        if value is None or len(self._values) < minimum:
            return None
        spread = st.pstdev(self._values)
        if spread < 1e-9:
            return 0.0
        return (value - st.mean(self._values)) / spread


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class RecoveryContextEngine:
    """Maintains personal baselines and produces the daily recovery context."""

    def __init__(self) -> None:
        window = int(ENGINE_PARAMETERS.value("baseline_window_days"))
        self._minimum = ENGINE_PARAMETERS.value("baseline_minimum_observations")
        self._log_rmssd = _RollingBaseline(window)
        self._resting_hr = _RollingBaseline(window)
        self._efficiency = _RollingBaseline(window)
        self._temperature = _RollingBaseline(window)
        self._systemic = _RollingBaseline(window)
        self._residuals: deque[float] = deque(
            maxlen=int(ENGINE_PARAMETERS.value("unexplained_window_days"))
        )

    def observe(self, reading: RecoveryReading, systemic_load: float) -> None:
        """Fold a day into the baselines. Called after the context is computed."""
        if reading.hrv_rmssd_ms is not None and reading.hrv_rmssd_ms > 0:
            self._log_rmssd.observe(math.log(reading.hrv_rmssd_ms))
        self._resting_hr.observe(reading.resting_hr_bpm)
        self._efficiency.observe(reading.sleep_efficiency)
        self._temperature.observe(reading.temperature_deviation_c)
        self._systemic.observe(systemic_load)

    def context(self, reading: RecoveryReading, systemic_load: float) -> RecoveryContext:
        """Compute the recovery multiplier for one day.

        Channels that are missing, or whose baseline is too thin to stand on,
        contribute nothing. That is the specification's treatment of missing
        data: absence of evidence lowers confidence, and never stands in for
        evidence of a problem.
        """
        p = ENGINE_PARAMETERS.value
        raw: dict[str, float] = {}
        contributions: dict[str, float] = {}
        partitions: dict[str, ChannelPartition] = {}

        log_rmssd = math.log(reading.hrv_rmssd_ms) if reading.hrv_rmssd_ms else None
        z_hrv = self._log_rmssd.z(log_rmssd, self._minimum)
        z_rhr = self._resting_hr.z(reading.resting_hr_bpm, self._minimum)
        z_eff = self._efficiency.z(reading.sleep_efficiency, self._minimum)
        z_temp = self._temperature.z(reading.temperature_deviation_c, self._minimum)
        z_systemic = self._systemic.z(systemic_load, self._minimum) or 0.0
        z_systemic = _clip(z_systemic, -3.0, 3.0)

        # Sleep is measured against a target rather than a rolling mean, so a
        # chronically short-sleeping baseline is not read as intrinsically fine.
        z_sleep = None
        if reading.total_sleep_min is not None:
            z_sleep = _clip(
                (reading.total_sleep_min / 60.0 - p("sleep_target_h")) / 1.0, -3.0, 2.0
            )

        for name, z, gamma, coeff in (
            ("hrv", z_hrv, -p("gamma_hrv"), p("rho_hrv_coeff")),
            ("resting_hr", z_rhr, p("gamma_rhr"), p("rho_rhr_coeff")),
        ):
            if z is None:
                continue
            observed = _clip(z, -3.0, 3.0)
            expected = gamma * z_systemic
            residual = _clip(observed - expected, -3.0, 3.0)
            raw[name] = observed
            partitions[name] = ChannelPartition(observed, expected, residual)
            contributions[name] = coeff * residual

        if z_sleep is not None:
            raw["sleep"] = z_sleep
            contributions["sleep"] = p("rho_sleep_coeff") * z_sleep
        if z_eff is not None:
            raw["sleep_efficiency"] = _clip(z_eff, -3.0, 3.0)
            contributions["sleep_efficiency"] = p("rho_efficiency_coeff") * raw["sleep_efficiency"]
        if z_temp is not None:
            raw["temperature"] = _clip(z_temp, -3.0, 3.0)
            contributions["temperature"] = p("rho_temperature_coeff") * abs(raw["temperature"])

        rho = _clip(1.0 + sum(contributions.values()), p("rho_floor"), p("rho_ceiling"))

        autonomic = [part.residual_z for part in partitions.values()]
        if autonomic:
            self._residuals.append(math.sqrt(sum(r * r for r in autonomic) / len(autonomic)))
        recent = (
            math.sqrt(sum(r * r for r in self._residuals) / len(self._residuals))
            if self._residuals else 0.0
        )
        reference = p("unexplained_reference")
        explanation_confidence = _clip(
            reference / max(reference, recent), p("unexplained_floor"), 1.0
        )

        return RecoveryContext(
            rho=rho,
            contributions=contributions,
            partitions=partitions,
            raw_z=raw,
            channels_used=len(contributions),
            channels_present=reading.channels_present,
            unexplained_rms=recent,
            explanation_confidence=explanation_confidence,
        )

    def step(self, reading: RecoveryReading, systemic_load: float) -> RecoveryContext:
        """Compute the context for a day, then fold it into the baselines.

        The ordering matters: a reading must be standardised against the days
        *before* it, not against a window that already contains it.
        """
        context = self.context(reading, systemic_load)
        self.observe(reading, systemic_load)
        return context
