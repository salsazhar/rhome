"""Specification-to-test conformance mapping (Guardrail 5).

The documents in ``rhome_docs/`` are the source of truth, and the implementation
rule in their README is that code must not silently diverge from them. Silent
divergence is the failure mode this module exists to prevent.

Tests declare the clause they cover with a marker::

    @pytest.mark.spec("MODEL:failure-fatigue-multiplier")
    def test_failure_multiplier_at_zero_rir():
        ...

The registry below lists every clause considered testable. The report generated
at each layer checkpoint shows which clauses have tests and which do not, so a
clause nobody implemented appears as a visible gap rather than an absence
nobody noticed.

Clauses are registered as a stage implements them. An empty covering-test list
is an honest statement that the work has not been done yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Clause", "CLAUSES", "register", "coverage_report"]


@dataclass(frozen=True)
class Clause:
    """One testable statement from the specification."""

    clause_id: str
    document: str
    section: str
    statement: str
    layer: str


CLAUSES: dict[str, Clause] = {}


def register(clause_id: str, document: str, section: str, statement: str, layer: str) -> None:
    """Add a clause to the registry."""
    if clause_id in CLAUSES:
        raise ValueError(f"clause already registered: {clause_id}")
    CLAUSES[clause_id] = Clause(clause_id, document, section, statement, layer)


@dataclass
class Coverage:
    """Which tests cover which clauses, and what is missing."""

    covered: dict[str, list[str]] = field(default_factory=dict)
    uncovered: list[str] = field(default_factory=list)
    unknown_clauses: dict[str, list[str]] = field(default_factory=dict)

    @property
    def coverage_fraction(self) -> float:
        total = len(self.covered) + len(self.uncovered)
        return len(self.covered) / total if total else 1.0


def coverage_report(marked_tests: dict[str, list[str]]) -> Coverage:
    """Compare declared test markers against the clause registry.

    ``marked_tests`` maps clause id to the test node ids claiming it.
    """
    report = Coverage()
    for clause_id in sorted(CLAUSES):
        tests = marked_tests.get(clause_id, [])
        if tests:
            report.covered[clause_id] = sorted(tests)
        else:
            report.uncovered.append(clause_id)
    for clause_id, tests in sorted(marked_tests.items()):
        if clause_id not in CLAUSES:
            report.unknown_clauses[clause_id] = sorted(tests)
    return report


# --- L0.1 clauses -----------------------------------------------------------
register(
    "ARCH:sim-engine-separation",
    "DATA.md",
    "§2",
    "The simulator and inference engine are separate; the engine never reads "
    "simulator-only latent columns or scenario labels.",
    "L0.1",
)
register(
    "ARCH:eval-sole-exception",
    "BUILD_PLAN.md",
    "§4 Guardrail 1",
    "Evaluation is the only package permitted to import both the simulator "
    "and the engine.",
    "L0.1",
)
register(
    "DATA:deterministic-seed",
    "DATA.md",
    "§20",
    "The generator must be deterministic under a fixed seed.",
    "L0.1",
)


# --- L0.2 clauses -----------------------------------------------------------
register(
    "ARCH:parameters-match-docs",
    "BUILD_PLAN.md",
    "§4 Guardrail 3",
    "Every specification value lives in one versioned registry and is checked "
    "against the document it came from.",
    "L0.2",
)
register(
    "DATA:sixteen-model-groups",
    "DATA.md",
    "§7.1",
    "The model maintains state for sixteen muscle groups.",
    "L0.2",
)
register(
    "DATA:display-taxonomy-maps-to-model",
    "DATA.md",
    "§7.2",
    "A finer display taxonomy maps many-to-one onto the model groups; adding a "
    "display label requires no model change.",
    "L0.2",
)
register(
    "MODEL:no-calendar-discontinuity",
    "MODEL.tex",
    "Temporal conventions and continuity",
    "State evolves in continuous hours and is never reset or rebased at a "
    "calendar boundary.",
    "L0.2",
)
register(
    "MODEL:sleep-anchored-recovery-window",
    "MODEL.tex",
    "Recovery-context windows",
    "The recovery multiplier from the night ending at sleep_end applies until "
    "the next sleep_end, not from midnight to midnight.",
    "L0.2",
)
register(
    "MODEL:constant-input-closed-form",
    "MODEL.tex",
    "Distribution of daily activity load",
    "Daily activity load is distributed across the waking window and integrated "
    "in closed form.",
    "L0.2",
)


# --- L0.3 clauses -----------------------------------------------------------
register(
    "DATA:exercise-library-covers-model",
    "DATA.md",
    "§7.1",
    "Every model muscle group receives load from some exercise in the library.",
    "L0.3",
)
register(
    "DATA:upper-lower-parity-feasible",
    "DATA.md",
    "§3.2",
    "Upper and lower primary effective-set stimulus stay within ~10% of one "
    "another; the exercise pool must make that achievable.",
    "L0.3",
)
register(
    "DATA:exercise-kind-dose-eligibility",
    "DATA.md",
    "§5.4.1",
    "Only repetition-based exercise kinds enter the resistance dose model; "
    "time- and distance-based kinds are recorded but excluded.",
    "L0.3",
)
register(
    "MODEL:performance-weights-normalised",
    "MODEL.tex",
    "Expected performance under current fatigue",
    "Performance-relevance weights are the fatigue-contribution vector "
    "normalised to unit sum, including stabilisers.",
    "L0.3",
)
register(
    "MODEL:derivation-matches-curated",
    "MODEL.tex",
    "Validation and status",
    "Derived coefficients agree with curated values within 0.15 for at least "
    "80% of the curated library.",
    "L0.3",
)
register(
    "MODEL:systemic-cost-not-mass-alone",
    "MODEL.tex",
    "Systemic cost from recruited mass",
    "Systemic cost is driven by movement pattern and equipment, with recruited "
    "muscle mass entering only as a modulator.",
    "L0.3",
)


# --- L1.1 clauses -----------------------------------------------------------
register(
    "DATA:athlete-starting-state",
    "DATA.md",
    "§10",
    "Athlete A starts from the documented body mass, one-repetition maxima, "
    "habitual steps, sleep and autonomic baselines.",
    "L1.1",
)
register(
    "DATA:simulator-richer-than-engine",
    "DATA.md",
    "§16.2",
    "The simulator samples per-muscle recovery parameters and exercise-specific "
    "RIR bias around population priors, so the engine cannot invert its own "
    "generator.",
    "L1.1",
)
register(
    "DATA:heteroskedastic-performance-noise",
    "DATA.md",
    "§16.2",
    "Performance noise is heteroskedastic, larger on less compound and less "
    "familiar movements.",
    "L1.1",
)


# --- L1.2 clauses -----------------------------------------------------------
register(
    "DATA:nonlinear-fatigue-accumulation",
    "DATA.md",
    "§16.2",
    "The simulator accumulates fatigue non-linearly, with interaction between "
    "volume and proximity to failure.",
    "L1.2",
)
register(
    "DATA:simulator-not-algebraic-mirror",
    "MODEL.tex",
    "Simulator versus inference engine",
    "The simulator and estimator are not algebraic mirrors of one another.",
    "L1.2",
)
register(
    "RESEARCH:residual-fatigue-tail",
    "RESEARCH.md",
    "9.2",
    "Demanding sessions leave meaningful residual fatigue across 48-72 hours.",
    "L1.2",
)


# --- L1.3 clauses -----------------------------------------------------------
register(
    "DATA:recovery-variables-correlated",
    "DATA.md",
    "§11",
    "Recovery variables are correlated and state-dependent; they are not "
    "sampled independently.",
    "L1.3",
)
register(
    "DATA:hrv-not-a-load-readout",
    "DATA.md",
    "§11.3",
    "A single hard workout must not force HRV downward every time.",
    "L1.3",
)
register(
    "DATA:latent-stress-unobserved",
    "DATA.md",
    "§16.2",
    "A latent day-level stress variable perturbs several channels together and "
    "is never directly observed.",
    "L1.3",
)
register(
    "DATA:wearable-measurement-error",
    "DATA.md",
    "§11.6",
    "Wearable observations are measurements of latent signals, not the latent "
    "signals themselves.",
    "L1.3",
)
register(
    "DATA:sleep-stage-invariant",
    "DATA.md",
    "§18",
    "Sleep stages sum to less than or equal to total sleep time.",
    "L1.3",
)


# --- L1.4 clauses -----------------------------------------------------------
register(
    "DATA:upper-lower-parity", "DATA.md", "§3.2",
    "Upper and lower primary effective-set stimulus stay within approximately "
    "10% of one another across ordinary rolling four-week blocks.", "L1.4",
)
register(
    "DATA:session-and-set-counts", "DATA.md", "§4.2",
    "470-510 lifting sessions, 14-18 working sets per session, "
    "7500-8500 working sets in total.", "L1.4",
)
register(
    "DATA:rep-range-distribution", "DATA.md", "§9.1",
    "Working-set repetitions follow the documented band distribution.", "L1.4",
)
register(
    "DATA:rpe-distribution", "DATA.md", "§9.2",
    "Working-set effort follows the documented RPE band distribution.", "L1.4",
)
register(
    "DATA:five-sessions-is-an-average", "DATA.md", "§18",
    "Five lifting sessions per week is an average, not an invariant, and no "
    "artificial reset occurs at a week boundary.", "L1.4",
)


# --- L1.5 clauses -----------------------------------------------------------
register(
    "DATA:causal-performance-chain", "DATA.md", "§9.5",
    "Observable sets are generated from latent capacity, then fatigue, then a "
    "stochastic shock, then load and repetitions, then true RIR, then "
    "observation noise -- in that order.", "L1.5",
)
register(
    "DATA:no-observable-depends-on-later-latent", "DATA.md", "§9.5",
    "No observable quantity depends on a latent value computed after it.", "L1.5",
)
register(
    "MODEL:rir-observation-noise", "MODEL.tex", "From RPE to RIR",
    "Logged RIR is the true value corrupted by observation error with a "
    "standard deviation of 0.9 repetitions, clipped to a plausible range.", "L1.5",
)
register(
    "DATA:progression-from-capacity", "DATA.md", "§9.4",
    "Progression arises from latent capacity and programme logic rather than "
    "fixed weekly increments.", "L1.5",
)


# --- L1.6 clauses -----------------------------------------------------------
register(
    "DATA:scenario-library-complete", "DATA.md", "§13",
    "All thirteen scenarios S0-S12 appear in the dataset with a recorded "
    "manifest.", "L1.6",
)
register(
    "DATA:scenario-intended-effects", "DATA.md", "§13",
    "Each scenario produces its documented effect on the latent state.", "L1.6",
)
register(
    "DATA:scenarios-in-both-windows", "DATA.md", "§15",
    "Scenario families appear in both the development and holdout windows, "
    "with different combinations and stochastic realisations.", "L1.6",
)
register(
    "DATA:manifest-is-simulator-only", "DATA.md", "§6.3",
    "The scenario manifest is available to evaluation code and never to the "
    "inference engine.", "L1.6",
)


# --- L1.7 clauses -----------------------------------------------------------
register(
    "DATA:missingness-rates", "DATA.md", "§17",
    "3-5% of nights lose one wearable metric, 1-2% lose all of them, with "
    "occasional missing body mass and effort ratings.", "L1.7",
)
register(
    "DATA:missingness-not-concentrated", "DATA.md", "§17",
    "Missingness must not be concentrated only in adverse scenarios.", "L1.7",
)
register(
    "DATA:raw-dirty-fixture", "DATA.md", "§17",
    "A separate fixture of malformed and duplicate rows exists for parser "
    "tests, outside the clean dataset.", "L1.7",
)


# --- L1.8 clauses -----------------------------------------------------------
register(
    "DATA:output-layout", "DATA.md", "§20",
    "The dataset is written to the documented directory layout, with observable "
    "and hidden tables physically separated.", "L1.8",
)
register(
    "DATA:generation-config", "DATA.md", "§20",
    "generation_config.json records the seed, dataset version, simulator "
    "parameters, scenario schedule, athlete parameters and commit hash.", "L1.8",
)
register(
    "DATA:reproducible-under-seed", "DATA.md", "§20",
    "The generator is deterministic under a fixed seed and reproduces the "
    "dataset byte for byte.", "L1.8",
)
register(
    "DATA:realism-invariants", "DATA.md", "§18",
    "Loads change in realistic increments, impossible set combinations are "
    "absent, sleep stages sum within total sleep, and body mass moves slowly.",
    "L1.8",
)


# --- L0.4 clauses -----------------------------------------------------------
register(
    "MODEL:nuzzo-inversion", "MODEL.tex", "Estimating relative intensity",
    "Relative intensity is estimated by inverting the Nuzzo meta-regression by "
    "piecewise-linear interpolation, not by a single conversion formula.", "L0.4",
)
register(
    "MODEL:intensity-domain-policy", "MODEL.tex", "Domain of validity and edge-case policy",
    "Near-maximal sets extend linearly to the definitional anchor; high-repetition "
    "sets are clipped and never extrapolated; both carry a confidence label.", "L0.4",
)
register(
    "MODEL:rpe-to-rir", "MODEL.tex", "From RPE to RIR",
    "RIR is taken as max(0, 10 - RPE) when not logged explicitly.", "L0.4",
)
register(
    "ARCH:build-log-self-checking", "BUILD_PLAN.md", "§3",
    "No checkpoint may be marked passed while a preceding stage is incomplete; "
    "every completed stage has a build-log entry and every entry an index row.",
    "L0.4",
)


# --- L2.1 clauses -----------------------------------------------------------
register(
    "MODEL:four-dose-channels", "MODEL.tex", "Per-set muscular stimulus",
    "Each set is decomposed into adaptive stimulus, local fatigue, "
    "neuromuscular strain and systemic load as separate quantities.", "L2.1",
)
register(
    "MODEL:failure-costs-more-than-it-buys", "MODEL.tex", "Per-set local-fatigue impulse",
    "The proximity-to-failure curve rises more steeply for fatigue than for "
    "stimulus, so training to failure costs disproportionately.", "L2.1",
)
register(
    "MODEL:set-type-inclusion", "MODEL.tex", "Set types and inclusion rules",
    "Warm-ups carry no dose; drop segments carry full dose but are excluded "
    "from performance estimation.", "L2.1",
)
register(
    "DATA:parser-rejects-and-repairs", "DATA.md", "§17",
    "Malformed rows are rejected with a stated reason where unrecoverable, and "
    "repaired where exactly one reading is sensible.", "L2.1",
)


# --- L2.2 clauses -----------------------------------------------------------
register(
    "MODEL:engine-continuous-evolution", "MODEL.tex", "Time evolution of fatigue states",
    "Fatigue states decay exponentially in continuous time, with the recovery "
    "multiplier scaling the decay rate rather than the state.", "L2.2",
)
register(
    "MODEL:engine-no-calendar-reset", "MODEL.tex", "Temporal conventions and continuity",
    "Engine state shows no discontinuity at a calendar boundary, though the "
    "recovery multiplier and step count arrive as daily aggregates.", "L2.2",
)
register(
    "MODEL:load-traces-separate", "MODEL.tex", "Slow adaptation / training-capacity state",
    "Short and long load traces are maintained independently and no threshold "
    "attaches to their ratio.", "L2.2",
)


# --- L2.3 clauses -----------------------------------------------------------
register(
    "MODEL:recovery-multiplier", "MODEL.tex", "Recovery multiplier",
    "The recovery multiplier combines five channels against personal baselines "
    "and is bounded to [0.80, 1.15].", "L2.3",
)
register(
    "MODEL:conditional-autonomic-expectation", "MODEL.tex", "Conditioning the autonomic expectation on recent training",
    "Autonomic channels enter the multiplier as residuals after subtracting "
    "what recent systemic load predicts.", "L2.3",
)
register(
    "MODEL:missing-data-is-not-a-penalty", "MODEL.tex", "Recovery multiplier",
    "Missing wearable variables contribute zero rather than an imputed "
    "pathological state; confidence falls instead.", "L2.3",
)
register(
    "MODEL:unexplained-deviation-lowers-confidence", "MODEL.tex", "Confidence",
    "Persistent unexplained autonomic deviation reduces confidence rather than "
    "moving the recovery multiplier.", "L2.3",
)


# --- L2.4 clauses -----------------------------------------------------------
register(
    "MODEL:frozen-projection-ordering", "MODEL.tex", "Estimation of underlying capacity",
    "A projection is persisted before its session is ingested; the residual is "
    "scored against the persisted value; capacity updates only afterwards.", "L2.4",
)
register(
    "MODEL:bounded-capacity-influence", "MODEL.tex", "Estimation of underlying capacity",
    "A Huberised update plus explicit ordinary and anchor session caps bounds "
    "the influence of any one correlated session on estimated capacity.", "L2.4",
)
register(
    "MODEL:fatigue-corrected-capacity", "MODEL.tex", "Estimation of underlying capacity",
    "The fatigue acting at the time is removed before an observation updates "
    "capacity, so training while tired does not depress the estimate.", "L2.4",
)
register(
    "MODEL:effective-load-bodyweight", "MODEL.tex", "Effective load for bodyweight-involving exercises",
    "Bodyweight-involving exercises use beta x smoothed body mass plus external "
    "load; daily scale noise is smoothed first.", "L2.4",
)


# --- L2.5 clauses -----------------------------------------------------------
register(
    "DATA:session-ordering-enforced", "DATA.md", "§9.5",
    "The day loop freezes every projection before ingesting the session, "
    "scores residuals against the frozen values, and updates capacity only "
    "afterwards.", "L2.5",
)
register(
    "MODEL:session-level-capacity-update", "MODEL.tex", "Estimation of underlying capacity",
    "Every eligible set contributes fatigue-corrected evidence, but correlated "
    "sets from one exercise-context produce one robust session update.", "L3.14",
)
register(
    "MODEL:scale-aware-capacity-clip", "MODEL.tex", "Estimation of underlying capacity",
    "The Huber clip is a frozen multiplier times the exercise-context's robust "
    "recent session-innovation scale, with an explicit prior floor.", "L3.14",
)
register(
    "MODEL:equipment-context-capacity-identity", "MODEL.tex", "Estimation of underlying capacity",
    "Cable and machine capacity is keyed by equipment context; free-weight and "
    "bodyweight capacity remains shared across locations.", "L3.14",
)
register(
    "MODEL:within-session-fatigue-curvature", "MODEL.tex", "Within-session fatigue curvature",
    "Local fatigue is amplified by observable prior dose-bearing sets for each "
    "muscle, saturating without reading the hidden state.", "L3.14",
)
register(
    "DATA:session-order-preserved", "DATA.md", "§9.5",
    "Ingestion preserves the source's performed set order because session "
    "position is an observable model input.", "L3.14",
)

register(
    "DATA:confidence-survives-missed-training", "DATA.md", "§19.5",
    "Confidence in fatigue does not fall during a missed-session block: an "
    "absence of training is informative about fatigue, not a gap in evidence. "
    "Capacity confidence does fall.", "L2.6",
)
register(
    "DATA:confidence-tracks-wearable-gaps", "DATA.md", "§19.5",
    "Confidence falls when wearable channels are withheld and recovers when "
    "they return; it rises over the first 42 days as baselines mature, bound "
    "by baseline maturity throughout; the reported binding reason is always "
    "the lowest-scoring component.", "L2.6",
)

register(
    "DATA:trace-decomposition-exact", "DATA.md", "§19.6",
    "Contributor shares for any state sum to 1.0 within numerical tolerance, "
    "and reconstructing a state from its listed contributors reproduces the "
    "reported value.", "L2.7",
)
register(
    "DATA:trace-parameters-declared", "DATA.md", "§19.6",
    "Every parameter appearing in a computation appears in the trace's "
    "parameter block, with an evidence grade.", "L2.7",
)
register(
    "RESEARCH:claim-boundaries-enforced", "RESEARCH.md", "§17",
    "No driver string is emitted that is not derivable from the trace, and "
    "none violates the claim boundaries. Enforced by test, not by review.", "L2.7",
)

register(
    "MODEL:unrated-set-imputed", "MODEL.tex",
    "Working sets logged without an effort rating",
    "A working set with no effort rating contributes its full dose at an "
    "imputed reserve, carries low intensity confidence so that confidence in "
    "every state it touches falls, and never becomes a performance "
    "observation.", "L2.7a",
)

register(
    "MODEL:projection-monotone-without-training", "MODEL.tex", "Projection",
    "With no training assumed, every fatigue channel decays monotonically "
    "toward zero.", "L2.8",
)
register(
    "MODEL:projection-neutral-recovery", "MODEL.tex", "Projection",
    "Where no future wearable data are known, the forecast assumes a neutral "
    "recovery multiplier rather than carrying the last observed one forward.",
    "L2.8",
)
register(
    "MODEL:projection-counterfactual", "MODEL.tex", "Projection",
    "Counterfactual workouts are inserted as future impulses at their "
    "proposed times, and decay thereafter like any other.", "L2.8",
)
register(
    "MODEL:projection-confidence-widens", "MODEL.tex", "Projection",
    "Projections carry a confidence that falls with the horizon, so a 7-day "
    "projection is not presented with the authority of the current state.",
    "L2.8",
)

register(
    "DATA:evaluation-through-dedicated-code", "DATA.md", "§19",
    "The engine is evaluated against latent state only through dedicated "
    "evaluation code, which runs the engine to completion before reading any "
    "latent series.", "L3.1",
)
register(
    "DATA:scale-alignment-frozen", "DATA.md", "§19.1",
    "RMSE is reported after scale normalisation, fitted once on the "
    "development window, content-addressed, and applied unchanged to the "
    "holdout.", "L3.1",
)
register(
    "PRODUCT:ablation-ladder", "PRODUCT.md", "§15",
    "Every performance figure is reported alongside baselines that use only "
    "the athlete's own past performance, scored on a matched sample.", "L3.1",
)

register(
    "DATA:state-baselines-reported", "DATA.md", "§19.1",
    "Latent-state reconstruction figures are reported alongside what a "
    "decaying count of working sets achieves on the same series, since a high "
    "correlation of levels is nearly free when both are driven by the same "
    "training log.", "L3.1",
)

register(
    "DATA:state-reconstruction-scored", "DATA.md", "§19.1",
    "Each latent channel is scored on correlation, RMSE after scale "
    "normalisation, directional accuracy, peak timing after high-load "
    "sessions, and recovery-crossing timing — each against a trivial "
    "baseline.", "L3.2",
)

register(
    "MODEL:capacity-gain-schedule", "MODEL.tex", "Gain schedule",
    "The capacity learning rate is scaled by the running-mean gain while the "
    "estimate is young, preserving the ratios between ordinary, anchor and "
    "low-confidence rates, and returning to the base rate once settled.",
    "L3.3",
)
register(
    "DATA:performance-scored", "DATA.md", "§19.2",
    "One-step-ahead residuals, bias by period and by experience, calibration "
    "across fatigue bins, autocorrelation, capacity against true neutral "
    "capacity after scale alignment, scenario response, and robustness to a "
    "single bad day.", "L3.3",
)
register(
    "DATA:accuracy-robustness-gate", "DATA.md", "§19.2",
    "A capacity-estimator candidate must pass the frozen S11 median, worst and "
    "ninety-day stability limits before matched one-step-ahead accuracy may "
    "rank it; a lower MAE cannot compensate for fragility.", "L3.13",
)

register(
    "DATA:ranking-orderings", "DATA.md", "§19.3",
    "The engine correctly ranks the six orderings: failure over matched-volume "
    "non-failure, high over ordinary volume, lower-body compound over arm "
    "isolation systemically, heavy compounds over isolation for neuromuscular "
    "strain, accumulation over deload for acute fatigue, and post-deload over "
    "pre-deload for expected performance.", "L3.4",
)

register(
    "DATA:calibration-bands", "DATA.md", "§19.4",
    "The simulator falls inside all six versioned Grade-C reference bands; "
    "the engine gap is reported, upper-body runs below lower-body, and the "
    "numerical-stability clip does not bind during ordinary training.", "L3.14",
)

register(
    "MODEL:capacity-maturity", "MODEL.tex", "Capacity maturity",
    "Confidence in an exercise's capacity rises with lifetime sessions of it, "
    "separately from the 28-day recency term, so it does not read high while "
    "the engine is not yet competitive on that exercise.", "L3.6",
)
register(
    "DATA:confidence-suite", "DATA.md", "§19.5",
    "Confidence behaviour measured across the window: the binding reason is "
    "always the lowest component, baseline maturity binds while the windows "
    "fill, and a missing wearable night costs confidence.", "L3.6",
)
register(
    "DATA:trace-suite", "DATA.md", "§19.6",
    "Trace integrity measured across the window: shares sum to one, states "
    "reconstruct, no driver crosses a claim boundary, and every trace "
    "discloses its evidence grades.", "L3.6",
)

register(
    "DATA:robustness-suite", "DATA.md", "§19.8",
    "One bad wearable night does not dominate state; one bad session does not "
    "permanently depress capacity; repeated systematic residuals do move it; "
    "missing wearables cost confidence; high step counts are not resistance "
    "volume; upper/lower parity is preserved across blocks.", "L3.7",
)


# --- DATA.md §19.7, registered at the Layer 3 audit -------------------------
# The only subsection of §19 that had never been registered. Coverage read
# 100% throughout, because coverage is measured against the register and
# nobody had asked whether the register was complete — D15's rule about a
# guardrail asserting its own scope, applied to the map rather than to a test.
register(
    "DATA:capacity-robust-to-one-bad-day", "DATA.md", "§19.7",
    "One anomalously poor session produces a large negative residual and does "
    "not permanently depress estimated capacity, once the estimate is "
    "established.", "L3.3",
)
register(
    "DATA:capacity-flat-through-plateau", "DATA.md", "§19.7",
    "Through scenario S9 the engine's estimated capacity stays approximately "
    "flat; it does not extrapolate prior progress.", "L3.3",
)
register(
    "DATA:rebound-attributed-to-fatigue", "DATA.md", "§19.7",
    "Post-deload performance gains are attributed principally to reduced "
    "fatigue rather than to a sudden capacity increase, verified by "
    "decomposing the projected change.", "L3.4",
)
register(
    "DATA:drop-segments-excluded-from-capacity", "DATA.md", "§19.7",
    "Drop segments and clipped high-repetition sets are absent from the "
    "capacity update.", "L2.4",
)
register(
    "DATA:bodyweight-capacity-in-system-load", "DATA.md", "§19.7",
    "A body-mass change moves estimated pull-up capacity in system-load units "
    "and is not misreported as a strength change.", "L2.4",
)


# --- L3.9 -------------------------------------------------------------------
register(
    "DATA:library-pinned-to-dataset", "DATA.md", "§20",
    "The generation config records the exercise library the dataset was "
    "generated against, content-addressed, so a dataset cannot be silently "
    "attributed to a library that did not produce it.", "L3.9",
)
register(
    "DATA:library-labels-fold-to-model-groups", "DATA.md", "§7.3",
    "Muscle labels finer than the sixteen model groups fold into them per D16, "
    "and where a fold collapses two labels onto one group the highest tier "
    "wins, so no structure is counted twice.", "L3.9",
)
register(
    "DATA:vocabulary-extraction-bounded", "DATA.md", "§15",
    "The L3.10 disclosure is bounded to the sorted distinct exercise-name "
    "strings from the sealed log, enforced by checking the extractor's own "
    "source rather than by convention.", "L3.10",
)
register(
    "DATA:mapping-frozen-before-use", "DATA.md", "§16",
    "The logged-name to library-id mapping is reviewed and frozen before any "
    "real-data run, and an unreviewed or incomplete mapping is refused.", "L3.10",
)
register(
    "DATA:real-ingest-round-trips", "DATA.md", "§5",
    "The real-data adapter reads Spotr and Oura into the engine's schema "
    "losing nothing the sources express, inventing nothing they do not, and "
    "resolving no exercise name itself.", "L3.11",
)


# --- L3.16 clauses ----------------------------------------------------------
register(
    "ARCH:model-version-freeze-stamp", "BUILD_PLAN.md",
    "§L3.11 The validation regime changes once logging is continuous",
    "Every model version is stamped with the date it was frozen, and an "
    "evaluation can state which sessions post-date that stamp. The stamp is "
    "derived from the code and parameters actually present, never declared.",
    "L3.16",
)


# --- L3.17 clauses ----------------------------------------------------------
register(
    "DATA:cross-sectional-muscle-reconstruction", "DATA.md", "§19.1",
    "Per-muscle local fatigue is scored between muscles within a day with day "
    "means removed, not only longitudinally, because the within-day contrast "
    "is the majority of the true latent variance.",
    "L3.17",
)
register(
    "DATA:attributed-baseline-required", "DATA.md", "§19.1",
    "Every per-muscle figure carries a trivial competitor that shares the "
    "authored exercise-to-muscle map and carries no inferred information "
    "(D23). An unattributed global accumulator is not a sufficient competitor "
    "for a per-muscle claim.",
    "L3.17",
)
