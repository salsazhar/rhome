"""Simulator parameters (``DATA.md`` §10, §16.2).

These are the simulator's own values. They are deliberately **not** the
inference engine's priors, and the two must never be read from a shared place.

That separation is the whole point of the exercise. If the simulator generated
data using the engine's coefficients, the engine would be inverting its own
generator and every evaluation result afterwards would be meaningless. The
prohibition is on the *values*, not merely on the import: sharing them through
``rhome_core`` would be an inverse crime that Guardrail 1 could not see.

So the relationship is one of distribution to point estimate. Where the engine
holds a single population prior — a 30-hour local fatigue half-life for every
muscle — the simulator samples a distinct value per muscle from a distribution
around it. The engine's job is to recover behaviour it cannot observe directly,
and it has to do so with a simpler model than the one that produced the data.
"""

from __future__ import annotations

from rhome_core.parameters import ParameterRegistry

__all__ = ["SIM_PARAMETERS"]

SIM_PARAMETERS = ParameterRegistry("sim")

# --- Athlete A starting state (DATA.md §10) --------------------------------
SIM_PARAMETERS.register(
    "initial_body_mass_kg", 80.0, "C", "DATA.md", "§10",
    "Starting body mass for the synthetic athlete.",
)
SIM_PARAMETERS.register(
    "initial_1rm_bench_kg", 105.0, "C", "DATA.md", "§10",
    "Starting barbell bench press one-repetition maximum.",
)
SIM_PARAMETERS.register(
    "initial_1rm_squat_kg", 155.0, "C", "DATA.md", "§10",
    "Starting back squat one-repetition maximum.",
)
SIM_PARAMETERS.register(
    "initial_1rm_deadlift_kg", 185.0, "C", "DATA.md", "§10",
    "Starting deadlift one-repetition maximum.",
)
SIM_PARAMETERS.register(
    "initial_1rm_overhead_press_kg", 65.0, "C", "DATA.md", "§10",
    "Starting overhead press one-repetition maximum.",
)
SIM_PARAMETERS.register(
    "habitual_steps", 10000.0, "C", "DATA.md", "§10",
    "Habitual daily step count.",
)
SIM_PARAMETERS.register(
    "target_sleep_h", 7.5, "C", "DATA.md", "§10",
    "Mean total sleep time.",
)
SIM_PARAMETERS.register(
    "baseline_rmssd_ms", 60.0, "C", "DATA.md", "§10",
    "Personal nocturnal RMSSD baseline.",
)
SIM_PARAMETERS.register(
    "baseline_resting_hr_bpm", 52.0, "C", "DATA.md", "§10",
    "Personal resting heart-rate baseline.",
)

# --- Latent physiology, sampled per athlete (DATA.md §16.2) ----------------
# The engine holds one population prior; the simulator samples around it, so
# the engine must recover a value it was never given.
SIM_PARAMETERS.register(
    "local_half_life_mean_h", 30.0, "C", "MODEL.tex", "Time evolution of fatigue states",
    "Mean of the per-muscle local fatigue half-life distribution.",
)
SIM_PARAMETERS.register(
    "local_half_life_sd_h", 6.0, "C", "MODEL.tex", "Time evolution of fatigue states",
    "Standard deviation of the per-muscle local fatigue half-life distribution.",
)
SIM_PARAMETERS.register(
    "local_half_life_min_h", 24.0, "C", "MODEL.tex", "Time evolution of fatigue states",
    "Lower truncation of the per-muscle local fatigue half-life distribution.",
)
SIM_PARAMETERS.register(
    "local_half_life_max_h", 42.0, "C", "MODEL.tex", "Time evolution of fatigue states",
    "Upper truncation of the per-muscle local fatigue half-life distribution.",
)
SIM_PARAMETERS.register(
    "rir_observation_noise_sd", 0.9, "B", "MODEL.tex", "From RPE to RIR",
    "Standard deviation of reported-RIR error, in repetitions.",
)
SIM_PARAMETERS.register(
    "rir_logged_clip_max", 8.0, "C", "MODEL.tex", "From RPE to RIR",
    "Upper clip applied to logged RIR.",
)
SIM_PARAMETERS.register(
    "novelty_cap", 1.25, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Maximum exercise-novelty fatigue multiplier.",
)
