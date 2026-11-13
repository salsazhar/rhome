"""Recovery physiology and wearable generation (``DATA.md`` §11, §16.2).

Wearable data in Rhome is not sampled independently per channel. It is
generated as a set of correlated, imperfect *measurements* of a hidden daily
recovery state, which is itself driven by training load, sleep, an unobserved
stress process and chance.

That ordering is what makes the dataset a real test. The engine sees five noisy
numbers each morning and must infer something about recovery; it never sees the
recovery state itself, and no combination of the five recovers it exactly.

Three properties are deliberate and are asserted by test.

**HRV is not a training-load readout.** A hard session shifts the *distribution*
of tomorrow's RMSSD downward, but the day-to-day autonomic noise is large enough
that plenty of hard sessions are followed by a normal or elevated reading.
Bellenger et al. found vagal indices moving in both directions under
accumulating load, and an engine that treats one low night as proof of
under-recovery should be punished by this data.

**The latent stress process is never observed.** A day-level stress variable
perturbs sleep, HRV and resting HR together, so the engine sees three channels
move in concert with no visible cause. Required by ``DATA.md`` §16.2.

**Measurement error sits on top of everything.** The wearable's reading is not
the latent value. The engine that trusts a single night's RMSSD to two decimal
places is trusting the noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from rhome_sim.athlete import AthleteParameters

__all__ = [
    "RecoveryConstants",
    "SIM_RECOVERY",
    "LatentDay",
    "WearableReading",
    "RecoveryModel",
]


@dataclass(frozen=True)
class RecoveryConstants:
    """Simulator recovery constants (decision D8: not specification values)."""

    # --- latent stress process ---
    #: Day-to-day persistence of the unobserved stress state.
    stress_persistence: float = 0.82
    stress_innovation_sd: float = 0.42

    # --- sleep ---
    sleep_persistence: float = 0.35
    #: How much stress shortens sleep, in hours per unit of stress.
    sleep_stress_effect: float = 0.32
    #: How much a heavy training day lengthens sleep.
    sleep_training_effect: float = 0.10
    sleep_efficiency_mean: float = 0.905
    sleep_efficiency_sd: float = 0.030
    #: Sleep-stage fractions of total sleep time.
    rem_fraction: float = 0.225
    deep_fraction: float = 0.165
    stage_noise_sd: float = 0.045

    # --- autonomic ---
    #: Persistence of the log-RMSSD deviation from personal baseline.
    hrv_persistence: float = 0.55
    #: Day-to-day autonomic noise. Large by design: this is what prevents HRV
    #: from acting as a training-load readout.
    hrv_innovation_sd: float = 0.135
    #: Sensitivity of next-morning HRV to the previous day's systemic load,
    #: multiplied by the athlete's own responsiveness. Calibrated so a hard
    #: session shifts the distribution by roughly 0.2 sd -- detectable across
    #: dozens of observations, uninformative on any single night. Roughly three
    #: hard sessions in ten are still followed by an above-baseline reading.
    hrv_load_sensitivity: float = 0.24
    #: Starting estimate of the athlete's habitual systemic load. HRV responds
    #: to load *relative to* this, not to absolute load, because a personal
    #: baseline already reflects habitual training. Without it, a consistently
    #: training athlete's RMSSD would settle below their own documented
    #: baseline, and a deload could never produce the autonomic rebound
    #: scenario S3 requires.
    habitual_systemic_load: float = 0.45
    #: How quickly the habitual reference tracks the athlete's actual load. A
    #: fixed reference leaves the deviation off-centre whenever real training
    #: load differs from the guess, which pushed observed RMSSD below the
    #: athlete's own stated baseline.
    habitual_load_adaptation: float = 0.012
    #: Bound on the log-RMSSD deviation. A trained adult's nightly RMSSD spans
    #: roughly 0.6x to 1.7x their baseline; without a bound the compounding of
    #: two autoregressive processes produced excursions beyond twice baseline,
    #: which no wearable record resembles.
    log_rmssd_deviation_limit: float = 0.52
    hrv_sleep_effect: float = 0.055
    hrv_stress_effect: float = -0.075
    rhr_persistence: float = 0.50
    rhr_innovation_sd: float = 1.35
    #: Resting HR responds to recovery, imperfectly and with its own noise.
    rhr_recovery_effect: float = -2.2
    rhr_stress_effect: float = 0.95

    # --- temperature ---
    temperature_sd: float = 0.16
    temperature_stress_effect: float = 0.05

    # --- steps ---
    steps_sd_fraction: float = 0.22

    # --- recovery propensity ---
    #: Weights mapping the latent state onto true recovery quality.
    propensity_sleep_weight: float = 0.055
    propensity_stress_weight: float = -0.070
    propensity_load_weight: float = -0.040
    propensity_floor: float = 0.68
    propensity_ceiling: float = 1.28

    # --- measurement error (RESEARCH.md §13.3) ---
    rmssd_measurement_cv: float = 0.06
    rhr_measurement_sd: float = 0.7
    sleep_measurement_sd_min: float = 12.0
    efficiency_measurement_sd: float = 0.015
    body_mass_measurement_sd: float = 0.7


SIM_RECOVERY = RecoveryConstants()


@dataclass
class LatentDay:
    """Hidden truth for one day. Never written to the observable tables."""

    day_index: int
    stress: float
    #: Sleep the athlete actually obtained, before measurement error.
    true_sleep_h: float
    true_sleep_efficiency: float
    #: Deviation of true log-RMSSD from personal baseline.
    true_log_rmssd_deviation: float
    true_resting_hr: float
    true_temperature_deviation: float
    true_steps: float
    #: True recovery quality over the day; drives fatigue decay.
    recovery_propensity: float
    #: Systemic load carried into the day, the driver of autonomic response.
    systemic_load: float


@dataclass
class WearableReading:
    """What the device reported: the latent value plus measurement error."""

    day_index: int
    total_sleep_min: float
    sleep_efficiency: float
    rem_sleep_min: float
    deep_sleep_min: float
    hrv_rmssd_ms: float
    resting_hr_bpm: float
    temperature_deviation_c: float
    steps: int
    body_mass_kg: float | None = None


class RecoveryModel:
    """Generates the hidden recovery state and its noisy observation."""

    def __init__(
        self,
        athlete: AthleteParameters,
        rng: np.random.Generator,
        constants: RecoveryConstants = SIM_RECOVERY,
    ) -> None:
        self.athlete = athlete
        self.rng = rng
        self.k = constants
        self._stress = 0.0
        self._habitual_load = constants.habitual_systemic_load
        self._sleep_deviation = 0.0
        self._hrv_deviation = 0.0
        self._rhr_deviation = 0.0

    # --- latent state ------------------------------------------------------

    def step(
        self,
        day_index: int,
        systemic_load: float,
        *,
        stress_shock: float = 0.0,
        sleep_override_h: float | None = None,
        temperature_offset: float = 0.0,
        steps_override: float | None = None,
        propensity_bonus: float = 0.0,
    ) -> LatentDay:
        """Advance one day and return the hidden truth for it.

        ``systemic_load`` is the load carried *into* this day, that is, the
        systemic fatigue state on waking. Nocturnal physiology on the morning of
        a day reflects the training that preceded it, so the caller passes the
        state as it stands at the start of the day, not the training that will
        happen during it.

        The override arguments exist for the scenario engine (L1.6) — sleep
        restriction, illness, travel — and are not used in ordinary days.
        ``propensity_bonus`` is applied *here* rather than by the caller, so the
        latent record carries the recovery quality that actually drove the
        simulation. A bonus applied downstream would leave the hidden ground
        truth disagreeing with the state it produced.
        """
        k = self.k

        # Unobserved stress: autoregressive, and the engine never sees it.
        self._stress = (
            k.stress_persistence * self._stress
            + k.stress_innovation_sd * self.rng.normal()
            + stress_shock
        )

        # Sleep: serially correlated, shortened by stress, lengthened a little
        # after heavy training.
        self._sleep_deviation = (
            k.sleep_persistence * self._sleep_deviation
            + self.athlete.sleep_sd_h * math.sqrt(1 - k.sleep_persistence**2)
            * self.rng.normal()
        )
        true_sleep = (
            self.athlete.target_sleep_h
            + self._sleep_deviation
            - k.sleep_stress_effect * self._stress
            + k.sleep_training_effect * systemic_load
        )
        if sleep_override_h is not None:
            true_sleep = sleep_override_h + 0.25 * self.rng.normal()
        true_sleep = float(np.clip(true_sleep, 3.0, 11.0))

        efficiency = float(
            np.clip(
                k.sleep_efficiency_mean
                + k.sleep_efficiency_sd * self.rng.normal()
                - 0.010 * max(0.0, self._stress),
                0.70,
                0.99,
            )
        )

        sleep_debt = true_sleep - self.athlete.target_sleep_h

        # Autonomic response. Training load enters through the athlete's own
        # sensitivity, but the innovation term is large enough that a hard
        # session does not reliably produce a low reading.
        self._hrv_deviation = (
            k.hrv_persistence * self._hrv_deviation
            + k.hrv_innovation_sd * self.rng.normal()
            + k.hrv_sleep_effect * sleep_debt
            + k.hrv_stress_effect * self._stress
            - self.athlete.autonomic_load_sensitivity
            * k.hrv_load_sensitivity
            * (systemic_load - self._habitual_load)
        )
        self._hrv_deviation = float(
            np.clip(
                self._hrv_deviation,
                -k.log_rmssd_deviation_limit,
                k.log_rmssd_deviation_limit,
            )
        )

        self._rhr_deviation = (
            k.rhr_persistence * self._rhr_deviation
            + k.rhr_innovation_sd * self.rng.normal()
            + k.rhr_recovery_effect * (self._hrv_deviation * 0.5)
            + k.rhr_stress_effect * self._stress
        )
        true_rhr = self.athlete.baseline_resting_hr_bpm + self._rhr_deviation

        temperature = (
            k.temperature_sd * self.rng.normal()
            + k.temperature_stress_effect * self._stress
            + temperature_offset
        )

        steps = (
            steps_override
            if steps_override is not None
            else self.athlete.habitual_steps
            * (1.0 + k.steps_sd_fraction * self.rng.normal())
        )
        steps = float(max(0.0, steps))

        propensity = float(
            np.clip(
                1.0
                + k.propensity_sleep_weight * sleep_debt
                + k.propensity_stress_weight * self._stress
                + k.propensity_load_weight * (systemic_load - self._habitual_load)
                - 0.25 * abs(temperature)
                + propensity_bonus,
                k.propensity_floor,
                k.propensity_ceiling,
            )
        )

        # The habitual reference drifts toward the load the athlete actually
        # carries, so the deviation stays centred on their own normal.
        self._habitual_load += k.habitual_load_adaptation * (systemic_load - self._habitual_load)

        return LatentDay(
            day_index=day_index,
            stress=self._stress,
            true_sleep_h=true_sleep,
            true_sleep_efficiency=efficiency,
            true_log_rmssd_deviation=self._hrv_deviation,
            true_resting_hr=true_rhr,
            true_temperature_deviation=temperature,
            true_steps=steps,
            recovery_propensity=propensity,
            systemic_load=systemic_load,
        )

    # --- observation -------------------------------------------------------

    def observe(self, day: LatentDay, body_mass_kg: float | None = None) -> WearableReading:
        """Measure the latent day. The reading is not the truth.

        Noise magnitudes follow ``RESEARCH.md`` §13.3, which derives them from
        Oura validation studies. They exist so the engine cannot trust a single
        night's reading to more precision than a real device provides.
        """
        k = self.k

        true_rmssd = math.exp(self.athlete.baseline_log_rmssd + day.true_log_rmssd_deviation)
        measured_rmssd = true_rmssd * math.exp(
            k.rmssd_measurement_cv * self.rng.normal() - 0.5 * k.rmssd_measurement_cv**2
        )

        true_sleep_min = day.true_sleep_h * 60.0
        measured_sleep = true_sleep_min + k.sleep_measurement_sd_min * self.rng.normal()
        measured_sleep = float(np.clip(measured_sleep, 120.0, 720.0))

        measured_efficiency = float(
            np.clip(
                day.true_sleep_efficiency + k.efficiency_measurement_sd * self.rng.normal(),
                0.60,
                1.0,
            )
        )

        # Stages co-vary with total sleep but carry large stage-level error,
        # per Svensson et al.: global measures are usable, staging less so.
        rem = measured_sleep * max(
            0.05, k.rem_fraction + k.stage_noise_sd * self.rng.normal()
        )
        deep = measured_sleep * max(
            0.04, k.deep_fraction + k.stage_noise_sd * self.rng.normal()
        )
        if rem + deep > measured_sleep * 0.85:
            scale = (measured_sleep * 0.85) / (rem + deep)
            rem, deep = rem * scale, deep * scale

        measured_mass = (
            body_mass_kg + k.body_mass_measurement_sd * self.rng.normal()
            if body_mass_kg is not None
            else None
        )

        return WearableReading(
            day_index=day.day_index,
            total_sleep_min=round(measured_sleep, 1),
            sleep_efficiency=round(measured_efficiency, 4),
            rem_sleep_min=round(rem, 1),
            deep_sleep_min=round(deep, 1),
            hrv_rmssd_ms=round(measured_rmssd, 2),
            resting_hr_bpm=round(day.true_resting_hr + k.rhr_measurement_sd * self.rng.normal(), 1),
            temperature_deviation_c=round(day.true_temperature_deviation, 3),
            steps=int(round(day.true_steps)),
            body_mass_kg=round(measured_mass, 2) if measured_mass is not None else None,
        )
