"""Athlete A's latent parameters (``DATA.md`` §10, §16.2).

This module creates the specific individual: the hidden constants that make
this a particular athlete rather than an average one. Every value here is
simulator-only ground truth. The inference engine never sees any of it, and
recovering some of it is exactly what the engine is later scored on.

The design rule is that the simulator must be structurally richer than the
engine (``DATA.md`` §16.2). Concretely:

* the engine assumes one 30-hour local fatigue half-life for every muscle; this
  athlete has sixteen different ones, sampled per muscle;
* the engine assumes reported RIR is unbiased; this athlete systematically
  under-reports proximity to failure on some exercises and over-reports on
  others;
* the engine assumes homoskedastic performance noise; this athlete is more
  variable on high-repetition and unfamiliar movements.

Each of those is a way for the engine to be wrong that it cannot detect from
the observable data alone, which is the point.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

import numpy as np

from rhome_core.exercises import ExerciseLibrary, load_library
from rhome_core.muscles import Muscle
from rhome_sim.parameters import SIM_PARAMETERS

__all__ = ["AthleteParameters", "sample_athlete", "ANCHOR_CAPACITY_KG"]


#: Starting one-repetition-max capacity per exercise, in that exercise's
#: effective-load units.
#:
#: Four of these are specified in ``DATA.md`` §10 (bench, squat, deadlift,
#: overhead press). The rest are simulator design constants chosen to be
#: plausible for a trained but non-elite athlete of that strength, and are
#: deliberately *not* registered as specification parameters: they are the
#: simulator's invention, not values the documents commit to.
#:
#: Conventions. Dumbbell exercises are stated per dumbbell, as they are logged.
#: Bodyweight-involving exercises are stated as effective system load, meaning
#: ``beta * body_mass + external``, so a pull-up capacity of 122 kg for an 80 kg
#: athlete means roughly a 42 kg added-load single.
ANCHOR_CAPACITY_KG: MappingProxyType[str, float] = MappingProxyType(
    {
        # Upper body
        "bench_press": 105.0,
        "incline_db_press": 38.0,
        "weighted_dip": 125.0,
        "overhead_press": 65.0,
        "weighted_pullup": 122.0,
        "lat_pulldown": 92.0,
        "chest_supported_row": 95.0,
        "cable_row": 100.0,
        "lateral_raise": 18.0,
        "reverse_pec_deck": 45.0,
        "db_curl": 24.0,
        "triceps_pressdown": 52.0,
        "wrist_curl": 35.0,
        # Core
        "cable_crunch": 75.0,
        "hanging_leg_raise": 62.0,
        "ab_wheel_rollout": 60.0,
        # Lower body
        "back_squat": 155.0,
        "hack_squat": 180.0,
        "leg_press": 280.0,
        "romanian_deadlift": 150.0,
        "deadlift": 185.0,
        "bulgarian_split_squat": 102.0,
        "leg_extension": 105.0,
        "leg_curl": 80.0,
        "calf_raise": 140.0,
        "back_extension": 94.0,
        "hip_adduction": 90.0,
    }
)


@dataclass(frozen=True)
class AthleteParameters:
    """Simulator-only ground truth for one athlete.

    Never passed to the inference engine, and never written to the observable
    output tables.
    """

    athlete_id: str
    seed: int

    initial_body_mass_kg: float

    #: Per-muscle local fatigue half-life in hours. The engine assumes one
    #: value for all sixteen; recovering the spread is a Phase-3 objective.
    local_half_life_h: MappingProxyType[Muscle, float]
    #: Per-muscle adaptation responsiveness, relative to 1.0.
    adaptation_rate: MappingProxyType[Muscle, float]

    systemic_half_life_h: float
    neuromuscular_half_life_h: float

    #: Starting capacity per exercise, in that exercise's effective-load units.
    initial_capacity_kg: MappingProxyType[str, float]
    #: Baseline multiplicative performance-noise scale per exercise.
    performance_noise_scale: MappingProxyType[str, float]
    #: Systematic RIR reporting bias per exercise, in repetitions. Positive
    #: means the athlete believes they had more left than they did.
    rir_bias: MappingProxyType[str, float]
    #: Repetition endurance per exercise, relative to the population curve.
    #: Nuzzo et al. found large between-person variation in repetitions
    #: achievable at a given percentage of one-repetition maximum; the engine
    #: uses the population curve as its prior, so this is a parameter it can
    #: never observe directly.
    rep_endurance: MappingProxyType[str, float]
    rir_noise_sd: float

    baseline_log_rmssd: float
    baseline_resting_hr_bpm: float
    target_sleep_h: float
    sleep_sd_h: float
    habitual_steps: float

    #: How strongly systemic load depresses nocturnal HRV for this athlete.
    autonomic_load_sensitivity: float
    #: How strongly sleep debt depresses expressible performance.
    sleep_performance_sensitivity: float
    #: How strongly an unfamiliar movement inflates local fatigue.
    novelty_sensitivity: float

    def half_life_spread_h(self) -> float:
        """Range of per-muscle half-lives, the engine's blind spot in one number."""
        values = list(self.local_half_life_h.values())
        return max(values) - min(values)


def _truncated_normal(
    rng: np.random.Generator, mean: float, sd: float, low: float, high: float, size: int
) -> np.ndarray:
    """Sample from a normal distribution truncated to ``[low, high]``.

    Rejection sampling rather than clipping: clipping would pile probability
    mass onto the boundaries, giving several muscles exactly a 24-hour
    half-life, which is not what the specification's truncated normal means.
    """
    out = np.empty(size)
    filled = 0
    while filled < size:
        draw = rng.normal(mean, sd, size=size * 2)
        accepted = draw[(draw >= low) & (draw <= high)]
        take = min(len(accepted), size - filled)
        out[filled : filled + take] = accepted[:take]
        filled += take
    return out


def sample_athlete(
    seed: int,
    athlete_id: str = "athlete_a",
    library: ExerciseLibrary | None = None,
) -> AthleteParameters:
    """Draw one athlete's latent parameters. Deterministic under ``seed``."""
    from rhome_core.seeding import RootSeed

    library = library or load_library()
    root = RootSeed(seed)

    missing = {e.exercise_id for e in library} - set(ANCHOR_CAPACITY_KG)
    if missing:
        raise ValueError(
            f"no starting capacity for {sorted(missing)}; every exercise in the "
            f"library needs one before the athlete can train"
        )

    muscles = list(Muscle)
    half_lives = _truncated_normal(
        root.stream("athlete.local_half_life"),
        SIM_PARAMETERS.value("local_half_life_mean_h"),
        SIM_PARAMETERS.value("local_half_life_sd_h"),
        SIM_PARAMETERS.value("local_half_life_min_h"),
        SIM_PARAMETERS.value("local_half_life_max_h"),
        len(muscles),
    )
    adaptation = root.stream("athlete.adaptation_rate").normal(1.0, 0.15, len(muscles))

    capacity_rng = root.stream("athlete.initial_capacity")
    noise_rng = root.stream("athlete.performance_noise")
    bias_rng = root.stream("athlete.rir_bias")

    endurance_rng = root.stream("athlete.rep_endurance")
    capacities: dict[str, float] = {}
    noise_scales: dict[str, float] = {}
    biases: dict[str, float] = {}
    endurance: dict[str, float] = {}
    for exercise in sorted(library, key=lambda e: e.exercise_id):
        anchor = ANCHOR_CAPACITY_KG[exercise.exercise_id]
        # Individual variation around the anchor: this athlete is relatively
        # stronger at some movements than the anchors alone would suggest.
        capacities[exercise.exercise_id] = float(anchor * capacity_rng.normal(1.0, 0.05))
        # Heteroskedastic by design: less compound movements and less familiar
        # patterns vary more session to session.
        base_noise = 0.030 + 0.020 * (1.0 - exercise.compoundness)
        noise_scales[exercise.exercise_id] = float(abs(noise_rng.normal(base_noise, 0.004)))
        biases[exercise.exercise_id] = float(bias_rng.normal(0.0, 0.35))
        endurance[exercise.exercise_id] = float(
            np.clip(endurance_rng.lognormal(0.0, 0.13), 0.70, 1.40)
        )

    other = root.stream("athlete.other")
    return AthleteParameters(
        athlete_id=athlete_id,
        seed=seed,
        initial_body_mass_kg=SIM_PARAMETERS.value("initial_body_mass_kg"),
        local_half_life_h=MappingProxyType(
            {m: float(h) for m, h in zip(muscles, half_lives)}
        ),
        adaptation_rate=MappingProxyType(
            {m: float(max(0.5, a)) for m, a in zip(muscles, adaptation)}
        ),
        # Sampled around the engine's priors of 30 h and 24 h, not equal to them.
        systemic_half_life_h=float(other.normal(30.0, 3.0)),
        neuromuscular_half_life_h=float(other.normal(24.0, 2.5)),
        initial_capacity_kg=MappingProxyType(capacities),
        performance_noise_scale=MappingProxyType(noise_scales),
        rir_bias=MappingProxyType(biases),
        rep_endurance=MappingProxyType(endurance),
        rir_noise_sd=SIM_PARAMETERS.value("rir_observation_noise_sd"),
        baseline_log_rmssd=float(np.log(SIM_PARAMETERS.value("baseline_rmssd_ms"))),
        baseline_resting_hr_bpm=SIM_PARAMETERS.value("baseline_resting_hr_bpm"),
        target_sleep_h=SIM_PARAMETERS.value("target_sleep_h"),
        sleep_sd_h=float(abs(other.normal(0.75, 0.05))),
        habitual_steps=SIM_PARAMETERS.value("habitual_steps"),
        autonomic_load_sensitivity=float(abs(other.normal(0.35, 0.08))),
        sleep_performance_sensitivity=float(abs(other.normal(0.020, 0.005))),
        novelty_sensitivity=float(abs(other.normal(0.60, 0.15))),
    )
