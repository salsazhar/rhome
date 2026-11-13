"""End-to-end audit of Layer 2 — the inference engine.

Independent of the test suite. The tests say the code does what each stage's
author expected; this runs the finished engine over the development window and
asks whether the documented properties hold of the thing that came out.

Two rules carried over from the Layer 1 audit, both of which caught real
defects there:

* every check reports its measured value, so a marginal pass reads as marginal;
* a check with an empty sample fails rather than passing vacuously.
"""
from __future__ import annotations

import csv
import math
import statistics as st
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np

from rhome_core.architecture import check_import_boundaries, source_root
from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_core.intensity import IntensityConfidence
from rhome_core.parameters import CORE_PARAMETERS, parameter_reads
from rhome_core.timeline import RecoveryTimeline, RecoveryWindow
from rhome_engine.confidence import Band, ConfidenceEngine
from rhome_engine.dose import LoggedSet, transform_set
from rhome_engine.ledger import Channel
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.performance import CapacityModel, LeakageError
from rhome_engine.recovery import RecoveryContext, RecoveryReading
from rhome_engine.session import RhomeEngine
from rhome_engine.state import StateEngine
from rhome_engine.trace import ClaimBoundaryError, check_claim_boundaries

results: list[tuple[str, str, bool, str]] = []


def check(stage: str, requirement: str, ok: bool, detail: str, *, n: int | None = None) -> None:
    if n is not None and n == 0:
        results.append((stage, requirement, False, f"VACUOUS: no samples ({detail})"))
        return
    results.append((stage, requirement, bool(ok), detail))


LIBRARY = load_library()
DEV_DAYS = 520

from test_session_driver import DATASET, _days  # noqa: E402

if not (DATASET / "observable" / "sets.csv").exists():
    sys.exit("dataset not generated; run tools/generate_dataset.py first")

DAYS = _days()
engine = RhomeEngine(LIBRARY)
RESULTS = engine.run(DAYS[:DEV_DAYS])

# === L2.1 — dose transformation ============================================
# MODEL.tex: the dose channels depend only on (reps, RIR, exercise). Absolute
# load enters the performance channel alone. This is the invariance the whole
# load-blind design rests on.
base = LoggedSet("w", "bench_press", 1, "working", load_kg=60.0, reps=8, rpe=8.0)
heavy = LoggedSet("w", "bench_press", 1, "working", load_kg=160.0, reps=8, rpe=8.0)
d_light = transform_set(base, LIBRARY["bench_press"])
d_heavy = transform_set(heavy, LIBRARY["bench_press"])
identical = (
    d_light.local_fatigue == d_heavy.local_fatigue
    and d_light.stimulus == d_heavy.stimulus
    and d_light.neuromuscular == d_heavy.neuromuscular
    and d_light.systemic == d_heavy.systemic
)
check("L2.1", "dose is invariant to absolute load", identical,
      f"60kg vs 160kg at 8 reps @ RPE 8")

doses = [(logged, dose) for r in RESULTS for logged, dose in r.doses]
warmups = [d for logged, d in doses if logged.set_type == "warmup"]
check("L2.1", "warm-up sets carry no dose",
      all(not d.local_fatigue and d.neuromuscular == 0 for d in warmups),
      f"{len(warmups)} warm-up sets", n=len(warmups))

# Since the Layer 2 audit's finding, an unrated *working* set is imputed
# rather than discarded; an unrated warm-up still carries nothing, because a
# warm-up carries nothing regardless of what was recorded about it.
unrated_dose = [
    d for logged, d in doses
    if not logged.effort_recorded and logged.set_type in ("working", "backoff")
]
check("L2.1", "an unrated working set is imputed and marked down",
      all(d.local_fatigue and d.effort_imputed
          and d.intensity_confidence is IntensityConfidence.LOW
          and not d.eligible_for_performance
          for d in unrated_dose),
      f"{len(unrated_dose)} imputed sets", n=len(unrated_dose))

# Scoped to sets that *can* be transformed. The first version of this check
# asked it of every working set and failed on 115: a working set with no effort
# rating cannot have a dose computed and correctly gets none. The check's
# premise was wrong, not the code — but chasing it down found what follows.
working = [
    d for logged, d in doses
    if logged.set_type in ("working", "backoff") and logged.effort_recorded
]
check("L2.1", "all four channels are separately populated",
      all(d.local_fatigue and d.stimulus and d.neuromuscular > 0 and d.systemic > 0
          for d in working),
      f"{len(working)} transformable sets", n=len(working))

# How much of the athlete's training rests on a guessed effort. Not a pass/fail
# on arithmetic: a standing measurement of how far the record is from complete.
# It was the audit's opening question, when these sets were dropped entirely.
unrated_working = [
    logged for logged, _ in doses
    if logged.set_type in ("working", "backoff") and not logged.effort_recorded
]
dropped_fraction = len(unrated_working) / max(1, len(working) + len(unrated_working))
check("L2.1", "work resting on an imputed effort stays a small minority",
      dropped_fraction < 0.05,
      f"{len(unrated_working)} sets, {dropped_fraction:.1%} of dose-bearing work")

affected = {
    r.day_index
    for r in RESULTS
    for logged, _ in r.doses
    if logged.set_type in ("working", "backoff") and not logged.effort_recorded
}
worst = max(
    (r for r in RESULTS if r.day_index in affected),
    key=lambda r: sum(
        1 for logged, _ in r.doses
        if logged.set_type in ("working", "backoff") and not logged.effort_recorded
    ),
    default=None,
)
if worst is not None:
    missing = sum(
        1 for logged, _ in worst.doses
        if logged.set_type in ("working", "backoff") and not logged.effort_recorded
    )
    present = sum(1 for logged, _ in worst.doses if logged.set_type in ("working", "backoff"))
    neighbours = [
        RESULTS[i].confidence.fatigue.value
        for i in (worst.day_index - 1, worst.day_index + 1)
        if 0 <= i < len(RESULTS) and RESULTS[i].confidence
    ]
    # DATA.md §19.5 makes confidence an index of evidence sufficiency. A day
    # that lost a fifth of its session to unrated sets has less evidence
    # behind it, so confidence must not read higher than its neighbours.
    check("L2.6", "confidence falls on a day whose sets went unrated",
          worst.confidence.fatigue.value <= min(neighbours),
          f"day {worst.day_index}: {missing}/{present} unrated, confidence "
          f"{worst.confidence.fatigue.value:.4f} vs neighbours "
          f"{', '.join(f'{v:.4f}' for v in neighbours)}",
          n=len(affected))

# === L2.2 — state evolution ================================================
# MODEL.tex: exponential decay at the channel half-life, modulated by rho.
tl = RecoveryTimeline()
tl.append(RecoveryWindow(0.0, 1.0))
probe = StateEngine(tl)
probe.state.local_fatigue[Muscle.CHEST] = 1.0
probe.advance_to(ENGINE_PARAMETERS.value("local_half_life_h"))
halved = probe.state.local_fatigue[Muscle.CHEST]
check("L2.2", "local fatigue halves at its half-life", abs(halved - 0.5) < 1e-9,
      f"{halved:.6f} after 30 h")

try:
    probe.advance_to(0.0)
    backwards = False
except ValueError:
    backwards = True
check("L2.2", "time cannot run backwards", backwards, "ValueError raised")

active = StateEngine(RecoveryTimeline())
amplitude = active.set_activity_window(16000, 8000, 7.5)
active.advance_to(7.5)
at_wake = active.state.systemic
active.advance_to(15.5)
mid = active.state.systemic
active.advance_to(23.5)
end = active.state.systemic
check("L2.2", "daily activity accrues across the window, not at an instant",
      at_wake == 0.0 and 0 < mid < end, f"0 → {mid:.4f} → {end:.4f}")

novelty_new = active.novelty_for("never_done")
for _ in range(40):
    active._exposures["familiar"] = active._exposures.get("familiar", 0) + 1
novelty_old = active.novelty_for("familiar")
check("L2.2", "novelty inflates an unfamiliar movement and decays with exposure",
      novelty_new > novelty_old > 1.0 - 1e-9,
      f"{novelty_new:.3f} new vs {novelty_old:.3f} after 40 exposures")

# === L2.3 — recovery context ===============================================
rhos = [r.recovery.rho for r in RESULTS]
floor = ENGINE_PARAMETERS.value("rho_floor")
ceiling = ENGINE_PARAMETERS.value("rho_ceiling")
check("L2.3", f"rho stays inside [{floor}, {ceiling}]",
      min(rhos) >= floor - 1e-12 and max(rhos) <= ceiling + 1e-12,
      f"{min(rhos):.3f}–{max(rhos):.3f}")

blank = [r for r in RESULTS if r.recovery.channels_present == 0]
check("L2.3", "a night with no wearable data leaves rho neutral",
      all(r.recovery.rho == 1.0 for r in blank), f"{len(blank)} blank nights",
      n=len(blank))

# MODEL.tex §12.2: the expectation is conditioned on recent training, so what
# survives in rho should be what training does *not* explain.
load = [r.state.systemic for r in RESULTS]
corr_load = float(np.corrcoef(rhos, load)[0, 1])
check("L2.3", "conditioning leaves rho nearly uncorrelated with training load",
      abs(corr_load) < 0.15, f"corr = {corr_load:+.3f}")

used = [r for r in RESULTS if r.recovery.channels_used > 0]
check("L2.3", "rho actually moves when wearables are present",
      st.pstdev([r.recovery.rho for r in used]) > 0.01,
      f"sd {st.pstdev([r.recovery.rho for r in used]):.4f} over {len(used)} days",
      n=len(used))

# === L2.4 / L2.5 — performance, capacity, and the day loop =================
observations = [o for r in RESULTS for o in r.observations]
projections = sum(len(r.projections) for r in RESULTS)
check("L2.5", "the development window runs with no leakage error", True,
      f"{DEV_DAYS} days, {projections} projections, {len(observations)} scored")

sealed_ok = all(
    (record := engine.capacity.frozen(o.exercise_id, o.session_key)) is not None
    and record.verify()
    for o in observations
)
check("L2.4", "every scored projection was sealed and is unaltered", sealed_ok,
      f"{len(observations)} verified digests", n=len(observations))

try:
    engine.capacity.score_against_projection(LIBRARY["bench_press"], "no_such_session", 100.0)
    guard = False
except LeakageError:
    guard = True
check("L2.4", "scoring without a frozen projection is refused", guard,
      "LeakageError raised")

residuals = [o.log_residual for o in observations]
mean_res = st.mean(residuals)
check("L2.5", "one-step-ahead residuals are approximately unbiased",
      abs(mean_res) < 0.03, f"mean {mean_res:+.4f}, sd {st.pstdev(residuals):.4f}")

check("L2.5", "capacity records every eligible set but moves once per session",
      sum(engine.capacity.observations(e.exercise_id) for e in LIBRARY) > 2 * DEV_DAYS,
      f"{sum(engine.capacity.observations(e.exercise_id) for e in LIBRARY)} evidence sets")

check("L2.5", "the observation record reports a real capacity movement",
      sum(1 for o in observations if o.capacity_after != o.capacity_before)
      > 0.9 * len(observations)
      and all(o.learning_rate > 0 for o in observations),
      f"{sum(1 for o in observations if o.capacity_after != o.capacity_before)}"
      f"/{len(observations)} moved")

# Against the simulator's latent truth. rhome_eval is the only package allowed
# to see both sides; this tool is evaluation, and reads truth for no other
# purpose than to report it.
from rhome_sim.generate import simulate  # noqa: E402

SIM = simulate(20260822)
truth_capacity: dict[str, dict[int, float]] = defaultdict(dict)
for day in SIM.days[:DEV_DAYS]:
    for performed in day.sets:
        if performed.fatigue_factor > 0:
            truth_capacity[performed.exercise_id][day.day_index] = (
                performed.true_expressible_capacity / performed.fatigue_factor
            )

errors = {}
for exercise_id, series in truth_capacity.items():
    estimate = engine.capacity.capacity(exercise_id)
    if estimate is None:
        continue
    errors[exercise_id] = estimate / series[max(series)] - 1
mean_abs = st.mean(abs(e) for e in errors.values())
check("L2.5", "estimated capacity lands near the latent truth", mean_abs < 0.10,
      f"mean |error| {mean_abs:.1%} over {len(errors)} exercises", n=len(errors))

latent = {d.day_index: d for d in SIM.days}
corr_rho = float(np.corrcoef(
    [r.recovery.rho for r in RESULTS],
    [latent[r.day_index].latent.recovery_propensity for r in RESULTS],
)[0, 1])
check("L2.3", "rho tracks the simulator's hidden recovery state", corr_rho > 0.5,
      f"corr = {corr_rho:+.3f}")

# The engine's day-N state is the close of day N; the simulator's is on
# waking. Pairing them index for index compares states sixteen hours apart
# across a session, and read as +0.450 where the answer is +0.949. L3.1 found
# it; this check paired them wrongly until then.
corr_fatigue = float(np.corrcoef(
    [st.mean(r.state.local_fatigue.values()) for r in RESULTS[:-1]],
    [st.mean(latent[r.day_index + 1].state_on_waking.local_fatigue(m)
             for m in r.state.local_fatigue) for r in RESULTS[:-1]],
)[0, 1])
check("L2.2", "local fatigue tracks the simulator's hidden state", corr_fatigue > 0.85,
      f"corr = {corr_fatigue:+.3f}")

# Bounded influence (scenario S11): one bad session must not rewrite capacity.
# The repaired estimator makes the product limit explicit at session scale;
# maturity may alter responsiveness below the cap, never the cap itself.
SETTLED_OBSERVATIONS = 20
bounded = CapacityModel()
bounded_state = StateEngine(RecoveryTimeline())
for index in range(SETTLED_OBSERVATIONS):
    # Freeze first, as the day loop does. Writing this the other way round is
    # what Guardrail 2 exists to stop, and it stopped this script.
    bounded.freeze(LIBRARY["bench_press"], bounded_state.state, f"warm{index}")
    bounded.update_capacity(LIBRARY["bench_press"], f"warm{index}", 120.0, bounded_state.state)
before = bounded.capacity("bench_press")
bounded.freeze(LIBRARY["bench_press"], bounded_state.state, "bad_day")
bounded.update_capacity(LIBRARY["bench_press"], "bad_day", before * 0.6, bounded_state.state)
moved = abs(bounded.capacity("bench_press") / before - 1)
ordinary_limit = ENGINE_PARAMETERS.value("capacity_session_max_move")
check("L2.4", "one anomalous session stays inside the approved 2.1% bound",
      moved <= ordinary_limit,
      f"{moved:.3%} from a 40% miss, limit {ordinary_limit:.3%}, "
      f"{SETTLED_OBSERVATIONS} prior observations")

# The hard product bound also applies while the estimate is young.
young = CapacityModel()
young_state = StateEngine(RecoveryTimeline())
for index in range(3):
    young.freeze(LIBRARY["bench_press"], young_state.state, f"y{index}")
    young.update_capacity(LIBRARY["bench_press"], f"y{index}", 120.0, young_state.state)
young_before = young.capacity("bench_press")
young.freeze(LIBRARY["bench_press"], young_state.state, "bad")
young.update_capacity(LIBRARY["bench_press"], "bad", young_before * 0.6, young_state.state)
young_moved = abs(young.capacity("bench_press") / young_before - 1)
check("L2.4", "a young estimate retains the same hard session bound",
      young_moved <= ordinary_limit and abs(young_moved - moved) < 1e-12,
      f"{young_moved:.3%} at 3 prior observations vs {moved:.3%} at "
      f"{SETTLED_OBSERVATIONS}")

# === L2.6 — confidence =====================================================
confidences = [r.confidence for r in RESULTS if r.confidence]
check("L2.6", "every day carries a confidence report", len(confidences) == DEV_DAYS,
      f"{len(confidences)}/{DEV_DAYS}")

components = [c for report in confidences for c in report.fatigue.components]
check("L2.6", "every confidence component lies in (0, 1]",
      all(0.0 < c.value <= 1.0 for c in components),
      f"{len(components)} components, min {min(c.value for c in components):.3f}",
      n=len(components))

binding_ok = all(
    report.fatigue.binding_reason.value == min(c.value for c in report.fatigue.components)
    for report in confidences
)
check("L2.6", "the binding reason is always the lowest component", binding_ok,
      f"{len(confidences)} days")

band_ok = all(
    (report.fatigue.band is Band.HIGH and report.fatigue.value >= 0.75)
    or (report.fatigue.band is Band.MODERATE and 0.50 <= report.fatigue.value < 0.75)
    or (report.fatigue.band is Band.LIMITED and report.fatigue.value < 0.50)
    for report in confidences
)
check("L2.6", "display bands follow the documented thresholds", band_ok,
      dict(Counter(r.fatigue.band.value for r in confidences)))

# §19.5 expects baseline maturity to bind while the windows fill. Days
# carrying imputed sets are legitimate exceptions — a marked-down set can make
# dose quality the weaker term — so the check requires that every exception has
# one rather than requiring none.
early = RESULTS[:41]
by_maturity = [
    r for r in early if r.confidence.fatigue.binding_reason.name == "baseline maturity"
]
exceptions_explained = all(
    any(dose.effort_imputed for _, dose in r.doses)
    for r in early
    if r.confidence.fatigue.binding_reason.name != "baseline maturity"
)
check("L2.6", "baseline maturity binds while baselines fill",
      len(by_maturity) >= 38 and exceptions_explained
      and early[0].confidence.fatigue.value < early[-1].confidence.fatigue.value,
      f"{len(by_maturity)}/41 days; "
      f"{early[0].confidence.fatigue.value:.3f} → "
      f"{early[-1].confidence.fatigue.value:.3f}")

# DATA.md §19.5, the counter-intuitive one: not training is informative about
# fatigue, so C_F must not fall across a missed-session block.
quiet = ConfidenceEngine()
quiet_capacity = CapacityModel()
full = RecoveryReading(58.0, 52.0, 450.0, 0.90, 0.0)
for day in range(60):
    quiet.observe_day(RecoveryContext(rho=1.0), full.channels_present)
    quiet.observe_set(transform_set(base, LIBRARY["bench_press"]), LIBRARY["bench_press"],
                      day * 24.0)
    quiet.observe_performance("bench_press", day * 24.0)
before_gap = quiet.report(quiet_capacity, 59 * 24.0)
for day in range(60, 74):
    quiet.observe_day(RecoveryContext(rho=1.0), full.channels_present)
after_gap = quiet.report(quiet_capacity, 73 * 24.0)
check("L2.6", "fatigue confidence holds through a missed-session block",
      abs(after_gap.fatigue.value - before_gap.fatigue.value) < 1e-9,
      f"{before_gap.fatigue.value:.9f} → {after_gap.fatigue.value:.9f}")
check("L2.6", "capacity confidence does fall over the same block",
      after_gap.capacity["bench_press"].value < before_gap.capacity["bench_press"].value,
      f"{before_gap.capacity['bench_press'].value:.3f} → "
      f"{after_gap.capacity['bench_press'].value:.3f}")

final = confidences[-1]
ratios = [final.projection(h).value / final.fatigue.value for h in (0, 72, 168, 336)]
check("L2.6", "projection confidence falls monotonically with horizon",
      ratios == sorted(ratios, reverse=True) and abs(ratios[0] - 1.0) < 1e-12,
      " → ".join(f"{r:.2f}" for r in ratios))

# === L2.7 — explanation trace ==============================================
traces = [t for r in RESULTS for t in r.traces.values()]
worst_share = max(abs(t.share_total() - 1.0) for t in traces)
check("L2.7", "contributor shares sum to one", worst_share < 1e-9,
      f"worst {worst_share:.2e} over {len(traces)} traces", n=len(traces))

worst_recon = max(
    abs(t.reconstruct() - t.value) / max(t.value, 1e-12) for t in traces
)
check("L2.7", "a state rebuilds from the contributors it lists", worst_recon < 1e-9,
      f"worst relative error {worst_recon:.2e}")

check("L2.7", "every trace carries a graded parameter block",
      all(t.parameters and all(p.grade in "ABC" for p in t.parameters) for t in traces),
      f"{len(traces[-1].parameters)} parameters, grades {traces[-1].grades()}")

drivers = {t.driver for t in traces if t.driver}
violations = []
for driver in drivers:
    try:
        check_claim_boundaries(driver)
    except ClaimBoundaryError as error:
        violations.append(str(error))
check("L2.7", "no driver string crosses a claim boundary", not violations,
      f"{len(drivers)} distinct strings, {len(violations)} violations", n=len(drivers))

forbidden = [
    "Your CNS is 72% fatigued.",
    "Your chest is exactly 64% recovered biologically.",
    "An HRV of X means you should not train.",
    "Your ACWR is 1.4, therefore injury risk is high.",
    "You are overtrained.",
    "Your wearable proves you are ill.",
]
caught = 0
for phrase in forbidden:
    try:
        check_claim_boundaries(phrase)
    except ClaimBoundaryError:
        caught += 1
check("L2.7", "the checker rejects every forbidden example in RESEARCH.md §17",
      caught == len(forbidden), f"{caught}/{len(forbidden)} rejected")

check("L2.7", "the ledger stays bounded over a long record",
      engine.ledger.size() < 40000,
      f"{engine.ledger.size()} entries after {DEV_DAYS} days")

# === guardrails ============================================================
violations = check_import_boundaries()
check("G1", "no package imports across the boundary or reads sealed data",
      not violations, f"{len(violations)} violations")

known = {p.name for p in CORE_PARAMETERS} | {p.name for p in ENGINE_PARAMETERS}
unread = known - parameter_reads(source_root(), known) - {"muscle_mass_weights"}
check("G3", "every registered parameter is read by the code", not unread,
      f"{len(known)} registered, {len(unread)} unread")

second = RhomeEngine(LIBRARY)
repeat = second.run(_days()[:DEV_DAYS])
same = all(
    abs(a.state.local_fatigue[m] - b.state.local_fatigue[m]) < 1e-15
    for a, b in zip(RESULTS, repeat) for m in a.state.local_fatigue
) and all(
    abs(a.recovery.rho - b.recovery.rho) < 1e-15 for a, b in zip(RESULTS, repeat)
)
check("G4", "a second identical run reproduces the first exactly", same,
      f"{DEV_DAYS} days compared bit for bit")

conformance = (ROOT / "build_log" / "conformance.md").read_text(encoding="utf-8")
covered = int(conformance.split("**Covered:**")[1].split()[0])
uncovered = int(conformance.split("**Uncovered:**")[1].split()[0])
check("G5", "every registered specification clause has a test", uncovered == 0,
      f"{covered} covered, {uncovered} uncovered")

# === the sealed real data ==================================================
seal = subprocess.run(
    [sys.executable, "tools/seal_real_data.py", "verify"],
    cwd=ROOT, capture_output=True, text=True,
)
check("seal", "the athlete's export is unread and unchanged", seal.returncode == 0,
      seal.stdout.strip().splitlines()[-1] if seal.stdout.strip() else "no manifest")

engine_source = "\n".join(
    p.read_text(encoding="utf-8") for p in (ROOT / "src" / "rhome_engine").rglob("*.py")
)
check("seal", "no engine module names the vault", "data/real" not in engine_source,
      "checked every rhome_engine module")

# === build log and tests ===================================================
index = (ROOT / "build_log" / "INDEX.md").read_text(encoding="utf-8")
import re  # noqa: E402

done = re.findall(r"^\| (L2\.\d+) \|[^|]*\| ✅", index, re.M)
entries = {p.name.split("_")[0] for p in (ROOT / "build_log").glob("L2.*.md")}
check("meta", "every completed L2 stage has a build-log entry",
      set(done) <= entries, f"{len(done)} complete: {', '.join(done)}")

proc = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
    cwd=ROOT, capture_output=True, text=True,
)
last = proc.stdout.strip().splitlines()[-1] if proc.stdout else "no output"
check("meta", "full test suite passes", proc.returncode == 0, last)

# === output ================================================================
passed = sum(1 for *_, ok, _ in results if ok)
print(f"\n{'':5}{'STAGE':7}{'REQUIREMENT':64}{'MEASURED':30}")
print("-" * 112)
current = None
for stage, requirement, ok, detail in results:
    if stage != current:
        print()
        current = stage
    print(f"{'PASS' if ok else 'FAIL':5}{stage:7}{requirement:64}{detail}")
print("-" * 112)
print(f"{passed}/{len(results)} checks passed")
failures = [(s, r, d) for s, r, ok, d in results if not ok]
if failures:
    print("\nFAILURES:")
    for s, r, d in failures:
        print(f"  {s}  {r} -> {d}")
sys.exit(1 if failures else 0)
