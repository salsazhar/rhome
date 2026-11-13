"""Inference-engine parameters (``MODEL.tex``).

These are the engine's priors. They are deliberately kept out of ``rhome_core``
and out of the simulator's reach (decision D4): the simulator must not generate
data using the coefficients the engine will use to analyse it, and sharing them
through a common module would be an inverse crime routed around Guardrail 1
rather than through it.

Every value is verified against the section of ``MODEL.tex`` it cites, by
``tests/test_guardrail_parameter_registry.py``. Most carry evidence grade C:
they are required to make the model explicit, not identified by evidence, and
are expected to become athlete-specific once longitudinal data exist.
"""

from __future__ import annotations

from types import MappingProxyType

from rhome_core.parameters import ParameterRegistry

__all__ = [
    "ENGINE_PARAMETERS", "PHI_STIMULUS", "PHI_FATIGUE",
    "PHI_NEUROMUSCULAR", "STEPS_LOCAL_COEFF",
]

ENGINE_PARAMETERS = ParameterRegistry("engine")

# --- per-set impulse scaling ----------------------------------------------
ENGINE_PARAMETERS.register(
    "local_fatigue_scale", 0.06, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Base local-fatigue impulse before bounded within-session curvature.",
)
ENGINE_PARAMETERS.register(
    "neuromuscular_scale", 0.10, "C", "MODEL.tex", "Neuromuscular-strain impulse",
    "Dimensionless scaling constant n0 on the neuromuscular strain impulse.",
)
ENGINE_PARAMETERS.register(
    "systemic_scale", 0.07, "C", "MODEL.tex", "Systemic-fatigue impulse",
    "Dimensionless scaling constant g0 on the systemic load impulse.",
)
ENGINE_PARAMETERS.register(
    "novelty_cap", 1.25, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Maximum novelty/eccentric-damage multiplier on local fatigue.",
)

# --- repetition terms ------------------------------------------------------
ENGINE_PARAMETERS.register(
    "stimulus_rep_plateau", 5, "C", "MODEL.tex", "Per-set muscular stimulus",
    "Repetitions above which the stimulus repetition term saturates at 1.",
)
ENGINE_PARAMETERS.register(
    "stimulus_rep_slope", 0.20, "C", "MODEL.tex", "Per-set muscular stimulus",
    "Slope of the stimulus repetition term below the plateau.",
)
ENGINE_PARAMETERS.register(
    "fatigue_rep_intercept", 0.80, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Intercept of the fatigue repetition term psi_R.",
)
ENGINE_PARAMETERS.register(
    "fatigue_rep_slope", 0.02, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Slope of the fatigue repetition term psi_R.",
)
ENGINE_PARAMETERS.register(
    "fatigue_rep_floor", 0.86, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Lower clip on the fatigue repetition term.",
)
ENGINE_PARAMETERS.register(
    "fatigue_rep_ceiling", 1.20, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Upper clip on the fatigue repetition term.",
)
ENGINE_PARAMETERS.register(
    "neuromuscular_intensity_exponent", 2, "C", "MODEL.tex", "Neuromuscular-strain impulse",
    "Exponent on relative intensity; makes near-maximal loading disproportionately costly.",
)

#: Proximity-to-failure multipliers, indexed by repetitions in reserve.
#: Values above the largest key take the final value.
PHI_STIMULUS: MappingProxyType[int, float] = MappingProxyType(
    {0: 1.00, 1: 0.95, 2: 0.85, 3: 0.72, 4: 0.58, 5: 0.45, 6: 0.30}
)
PHI_FATIGUE: MappingProxyType[int, float] = MappingProxyType(
    {0: 1.35, 1: 1.15, 2: 1.00, 3: 0.90, 4: 0.82, 5: 0.75}
)
PHI_NEUROMUSCULAR: MappingProxyType[int, float] = MappingProxyType(
    {0: 1.30, 1: 1.15, 2: 1.00, 3: 0.90}
)

for _rir, _value in PHI_STIMULUS.items():
    ENGINE_PARAMETERS.register(
        f"phi_stimulus_{_rir}", _value,
        "A" if _rir == 0 else "C", "MODEL.tex", "Per-set muscular stimulus",
        f"Stimulus multiplier at {_rir} repetitions in reserve.",
    )
for _rir, _value in PHI_FATIGUE.items():
    ENGINE_PARAMETERS.register(
        f"phi_fatigue_{_rir}", _value, "B", "MODEL.tex", "Per-set local-fatigue impulse",
        f"Fatigue multiplier at {_rir} repetitions in reserve.",
    )
for _rir, _value in PHI_NEUROMUSCULAR.items():
    ENGINE_PARAMETERS.register(
        f"phi_neuromuscular_{_rir}", _value, "C", "MODEL.tex", "Neuromuscular-strain impulse",
        f"Neuromuscular multiplier at {_rir} repetitions in reserve.",
    )


# --- state evolution -------------------------------------------------------
ENGINE_PARAMETERS.register(
    "local_half_life_h", 30.0, "C", "MODEL.tex", "Time evolution of fatigue states",
    "Local fatigue half-life. The engine holds one value for every muscle; the "
    "population prior spans 24-42 h and per-muscle values are a Phase-3 objective.",
)
ENGINE_PARAMETERS.register(
    "neuromuscular_half_life_h", 24.0, "C", "MODEL.tex", "Time evolution of fatigue states",
    "Neuromuscular strain half-life.",
)
ENGINE_PARAMETERS.register(
    "systemic_half_life_h", 30.0, "C", "MODEL.tex", "Time evolution of fatigue states",
    "Systemic fatigue half-life.",
)
ENGINE_PARAMETERS.register(
    "adaptation_time_constant_days", 42.0, "C", "MODEL.tex", "Slow adaptation / training-capacity state",
    "Time constant of the slow adaptive state.",
)
ENGINE_PARAMETERS.register(
    "adaptation_gain", 0.014, "C", "MODEL.tex", "Slow adaptation / training-capacity state",
    "Gain converting adaptive stimulus into the slow state; A ~ 1 at twelve sets/week.",
)
ENGINE_PARAMETERS.register(
    "load_trace_short_days", 7.0, "C", "MODEL.tex", "Slow adaptation / training-capacity state",
    "Short exponentially weighted load trace, displayed separately from the long one.",
)
ENGINE_PARAMETERS.register(
    "load_trace_long_days", 42.0, "C", "MODEL.tex", "Slow adaptation / training-capacity state",
    "Long exponentially weighted load trace. No injury threshold attaches to their ratio.",
)
ENGINE_PARAMETERS.register(
    "steps_baseline_days", 28.0, "C", "MODEL.tex", "Non-exercise activity and steps",
    "Rolling personal baseline window for daily step count.",
)
ENGINE_PARAMETERS.register(
    "steps_scale", 5000.0, "C", "MODEL.tex", "Non-exercise activity and steps",
    "Steps above baseline per unit of activity amplitude.",
)
ENGINE_PARAMETERS.register(
    "steps_systemic_coeff", 0.02, "C", "MODEL.tex", "Non-exercise activity and steps",
    "Systemic load contributed per unit of activity amplitude.",
)
ENGINE_PARAMETERS.register(
    "novelty_decay_exposures", 4.0, "C", "MODEL.tex", "Per-set local-fatigue impulse",
    "Exposures over which the novelty multiplier decays toward 1.",
    unverifiable_reason=(
        "MODEL.tex specifies the novelty cap and states that its numerical form "
        "is an engineering prior, but does not give the form. This decay "
        "constant is the engine's choice, and the gap is recorded in the L2.2 "
        "build-log entry rather than hidden behind a plausible number."
    ),
)

#: Per-muscle step contribution to local fatigue (``MODEL.tex`` §Non-exercise
#: activity). Non-zero only for lower-limb groups.
STEPS_LOCAL_COEFF = {
    "calves": 0.003, "quads": 0.0016, "glutes": 0.0012, "hamstrings": 0.0008,
}
for _muscle, _value in STEPS_LOCAL_COEFF.items():
    ENGINE_PARAMETERS.register(
        f"steps_local_{_muscle}", _value, "C", "MODEL.tex", "Non-exercise activity and steps",
        f"Local fatigue contributed to {_muscle} per unit of activity amplitude.",
    )


# --- recovery context ------------------------------------------------------
ENGINE_PARAMETERS.register(
    "baseline_window_days", 42.0, "C", "MODEL.tex", "Personal baseline transforms",
    "Rolling window for personal baselines of log-RMSSD, resting HR, sleep "
    "efficiency and temperature.",
)
ENGINE_PARAMETERS.register(
    "sleep_target_h", 7.5, "C", "MODEL.tex", "Personal baseline transforms",
    "Reference sleep duration. Deliberately a target rather than a rolling "
    "mean, so a chronically short-sleeping baseline is not read as optimal.",
)
ENGINE_PARAMETERS.register(
    "rho_hrv_coeff", 0.05, "C", "MODEL.tex", "Recovery multiplier",
    "Weight on the conditioned HRV residual.",
)
ENGINE_PARAMETERS.register(
    "rho_rhr_coeff", -0.04, "C", "MODEL.tex", "Recovery multiplier",
    "Weight on the conditioned resting-HR residual.",
)
ENGINE_PARAMETERS.register(
    "rho_sleep_coeff", 0.04, "C", "MODEL.tex", "Recovery multiplier",
    "Weight on sleep duration relative to target.",
)
ENGINE_PARAMETERS.register(
    "rho_efficiency_coeff", 0.02, "C", "MODEL.tex", "Recovery multiplier",
    "Weight on sleep efficiency relative to personal baseline.",
)
ENGINE_PARAMETERS.register(
    "rho_temperature_coeff", -0.03, "C", "MODEL.tex", "Recovery multiplier",
    "Weight on absolute temperature deviation; departure in either direction "
    "is unfavourable.",
)
ENGINE_PARAMETERS.register(
    "rho_floor", 0.80, "C", "MODEL.tex", "Recovery multiplier",
    "Lower bound on the recovery multiplier. Deliberately conservative.",
)
ENGINE_PARAMETERS.register(
    "rho_ceiling", 1.15, "C", "MODEL.tex", "Recovery multiplier",
    "Upper bound on the recovery multiplier.",
)
ENGINE_PARAMETERS.register(
    "gamma_hrv", 0.30, "C", "MODEL.tex", "Conditioning the autonomic expectation on recent training",
    "Expected HRV depression per standard deviation of systemic load above the "
    "athlete's own normal.",
)
ENGINE_PARAMETERS.register(
    "gamma_rhr", 0.25, "C", "MODEL.tex", "Conditioning the autonomic expectation on recent training",
    "Expected resting-HR elevation per standard deviation of systemic load.",
)
ENGINE_PARAMETERS.register(
    "unexplained_window_days", 14.0, "C", "MODEL.tex", "Confidence",
    "Window over which unexplained autonomic deviation is accumulated.",
)
ENGINE_PARAMETERS.register(
    "unexplained_reference", 1.5, "C", "MODEL.tex", "Confidence",
    "Residual magnitude below which no confidence penalty applies.",
)
ENGINE_PARAMETERS.register(
    "unexplained_floor", 0.6, "C", "MODEL.tex", "Confidence",
    "Floor on the unexplained-deviation confidence component.",
)
ENGINE_PARAMETERS.register(
    "baseline_minimum_observations", 14, "C", "MODEL.tex", "Personal baseline transforms",
    "Observations required before a channel contributes.",
    unverifiable_reason=(
        "MODEL.tex fixes the 42-day window but does not say how few "
        "observations are too few. A standard deviation from three nights is "
        "not a baseline, and a channel computed from one would swamp the "
        "multiplier through pure sampling noise. The minimum is the engine's "
        "choice; below it the channel contributes zero, which is the same "
        "treatment the specification gives missing data."
    ),
)


# --- performance and capacity ----------------------------------------------
ENGINE_PARAMETERS.register(
    "lambda_local", 0.065, "C", "MODEL.tex", "Expected performance under current fatigue",
    "Sensitivity of expressed performance to local fatigue exposure.",
)
ENGINE_PARAMETERS.register(
    "lambda_neuromuscular", 0.045, "C", "MODEL.tex", "Expected performance under current fatigue",
    "Sensitivity of expressed performance to neuromuscular strain.",
)
ENGINE_PARAMETERS.register(
    "lambda_systemic", 0.030, "C", "MODEL.tex", "Expected performance under current fatigue",
    "Sensitivity of expressed performance to systemic fatigue.",
)
ENGINE_PARAMETERS.register(
    "suppression_clip", 0.25, "C", "MODEL.tex", "Expected performance under current fatigue",
    "Numerical guard on total modelled suppression, not a physiological bound.",
)
ENGINE_PARAMETERS.register(
    "capacity_huber_k", 1.345, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Frozen Huber multiplier applied to each exercise-context's robust scale.",
)
ENGINE_PARAMETERS.register(
    "capacity_residual_scale_prior", 0.10, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Prior log-residual scale before four session innovations identify it.",
)
ENGINE_PARAMETERS.register(
    "capacity_learning_rate", 0.2063, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Session learning rate derived from a three-session response half-life.",
)
ENGINE_PARAMETERS.register(
    "capacity_learning_rate_anchor", 0.50, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Session learning rate for standardised low-fatigue anchor efforts.",
)
ENGINE_PARAMETERS.register(
    "capacity_learning_rate_medium", 0.1591, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Session learning rate derived from a four-session response half-life.",
)
ENGINE_PARAMETERS.register(
    "capacity_session_max_move", 0.021, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Largest fractional capacity movement from one ordinary session.",
)
ENGINE_PARAMETERS.register(
    "capacity_anchor_session_max_move", 0.033, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Largest fractional capacity movement from a session containing an anchor.",
)
ENGINE_PARAMETERS.register(
    "capacity_context_prior_weight", 0.25, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Weak exercise-level prior weight when a new equipment context initialises.",
)
ENGINE_PARAMETERS.register(
    "capacity_initial_observations", 3, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Observations whose median initialises estimated capacity.",
)
ENGINE_PARAMETERS.register(
    "capacity_confident_observations", 8, "C", "MODEL.tex", "Estimation of underlying capacity",
    "Observations before capacity confidence is no longer held low.",
)
ENGINE_PARAMETERS.register(
    "body_mass_window_days", 7, "C", "MODEL.tex", "Effective load for bodyweight-involving exercises",
    "Centred median window for smoothed body mass; daily readings carry water "
    "and gut-content noise that would otherwise enter performance directly.",
)

ENGINE_PARAMETERS.register(
    "within_session_fatigue_gamma", 0.25, "C", "MODEL.tex", "Within-session fatigue curvature",
    "Additional fatigue multiplier per prior dose-bearing position.",
)
ENGINE_PARAMETERS.register(
    "within_session_position_cap", 4, "C", "MODEL.tex", "Within-session fatigue curvature",
    "Prior positions counted before the fatigue multiplier saturates.",
)


# --- confidence (L2.6, MODEL.tex §Confidence) -------------------------------
# Every constant in this block is a floor, a scale or a saturation point taken
# verbatim from the section. They are engineering priors: confidence is an
# index of evidence sufficiency, not a probability, and nothing here is
# estimated from data.

ENGINE_PARAMETERS.register(
    "confidence_wearable_floor", 0.60, "C", "MODEL.tex", "Confidence",
    "Confidence with no wearable data at all: the fatigue model runs on training data.",
)
ENGINE_PARAMETERS.register(
    "confidence_wearable_span", 0.40, "C", "MODEL.tex", "Confidence",
    "Range the wearable term covers between total absence and complete data.",
)
ENGINE_PARAMETERS.register(
    "confidence_wearable_window_nights", 7, "C", "MODEL.tex", "Confidence",
    "Nights over which wearable completeness is averaged.",
)
ENGINE_PARAMETERS.register(
    "confidence_baseline_floor", 0.50, "C", "MODEL.tex", "Confidence",
    "Confidence on day zero, before any personal baseline exists.",
)
ENGINE_PARAMETERS.register(
    "confidence_baseline_span", 0.50, "C", "MODEL.tex", "Confidence",
    "Range the baseline-maturity term covers as the 42-day window fills.",
)
ENGINE_PARAMETERS.register(
    "confidence_baseline_days", 42, "C", "MODEL.tex", "Confidence",
    "Days of history at which baselines are treated as mature.",
)
ENGINE_PARAMETERS.register(
    "confidence_intensity_medium", 0.80, "C", "MODEL.tex", "Confidence",
    "Dose-quality weight for a set whose relative intensity was inferred loosely.",
)
ENGINE_PARAMETERS.register(
    "confidence_intensity_low", 0.60, "C", "MODEL.tex", "Confidence",
    "Dose-quality weight for a set outside the tabulated intensity domain.",
)
ENGINE_PARAMETERS.register(
    "confidence_observation_saturation", 8, "C", "MODEL.tex", "Confidence",
    "Eligible observations in 28 days at which density confidence saturates.",
)
ENGINE_PARAMETERS.register(
    "confidence_observation_window_h", 672.0, "C", "MODEL.tex", "Confidence",
    "The 28-day window over which capacity observations are counted.",
    unverifiable_reason="The section states the window in days; hours are the "
                        "engine's internal unit. 28 days appears verbatim.",
)
ENGINE_PARAMETERS.register(
    "confidence_staleness_grace_h", 168.0, "C", "MODEL.tex", "Confidence",
    "Hours since the last observation that are forgiven before staleness bites.",
)
ENGINE_PARAMETERS.register(
    "confidence_staleness_scale_h", 504.0, "C", "MODEL.tex", "Confidence",
    "Three-week decay constant on staleness beyond the grace period.",
)
ENGINE_PARAMETERS.register(
    "confidence_fit_reference_sd", 0.05, "C", "MODEL.tex", "Confidence",
    "Log-residual spread treated as a well-tracked exercise.",
)
ENGINE_PARAMETERS.register(
    "confidence_fit_floor", 0.40, "C", "MODEL.tex", "Confidence",
    "Lower bound on fit confidence, however badly an exercise is tracked.",
)
ENGINE_PARAMETERS.register(
    "confidence_projection_scale_h", 336.0, "C", "MODEL.tex", "Confidence",
    "Decay constant on projection confidence; halves at roughly ten days.",
)
ENGINE_PARAMETERS.register(
    "confidence_band_high", 0.75, "C", "MODEL.tex", "Display and claim discipline",
    "Lower bound of the 'high' display band.",
)
ENGINE_PARAMETERS.register(
    "confidence_band_moderate", 0.50, "C", "MODEL.tex", "Display and claim discipline",
    "Lower bound of the 'moderate' display band.",
)


# --- imputed effort (L2.8 audit fix, MODEL.tex §Working sets logged without
# an effort rating) ---------------------------------------------------------

ENGINE_PARAMETERS.register(
    "imputed_rir_prior", 2, "C", "MODEL.tex",
    "Working sets logged without an effort rating",
    "Reserve assumed for an unrated working set before any personal history exists.",
)
ENGINE_PARAMETERS.register(
    "imputed_rir_window", 30, "C", "MODEL.tex",
    "Working sets logged without an effort rating",
    "Recent rated sets of an exercise the imputed reserve is taken from.",
)
ENGINE_PARAMETERS.register(
    "imputed_rir_minimum", 5, "C", "MODEL.tex",
    "Working sets logged without an effort rating",
    "Rated sets needed before a personal median replaces the next fallback.",
)


# --- capacity gain schedule (L3.3, MODEL.tex §Gain schedule) ----------------

ENGINE_PARAMETERS.register(
    "capacity_gain_cap", 0.50, "C", "MODEL.tex", "Gain schedule",
    "Largest learning rate the schedule will reach while an estimate is young.",
)


# --- capacity maturity (L3.6, MODEL.tex §Capacity maturity) -----------------

ENGINE_PARAMETERS.register(
    "confidence_maturity_floor", 0.45, "C", "MODEL.tex", "Capacity maturity",
    "Confidence in an exercise seen once. Not zero: a weak estimate is not a "
    "worthless one.",
)
ENGINE_PARAMETERS.register(
    "confidence_maturity_span", 0.55, "C", "MODEL.tex", "Capacity maturity",
    "Range the maturity term covers as lifetime observations accumulate.",
)
ENGINE_PARAMETERS.register(
    "confidence_maturity_saturation", 25, "B", "MODEL.tex", "Capacity maturity",
    "Lifetime observations at which maturity saturates. Measured: the engine "
    "beats a recency baseline from about 20 and clearly by 30.",
)
