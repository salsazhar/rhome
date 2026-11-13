"""End-to-end audit of Layer 3 — the evaluation harness itself.

The Layer 1 and Layer 2 audits ask whether the simulator and the engine do what
their stages claimed. This one asks a harder question, and the one Layer 3 has
no other way to answer: **are the numbers right?**

Layer 3 found eleven measurement errors and one modelling defect. Every one of
the eleven produced a plausible figure with a ready explanation attached, and
every one was caught by checking the instrument against something independent —
the specification's own words, an earlier prototype, or a metric with a floor it
could not cross. A harness cannot audit itself, because a mis-scaled instrument
reports a mis-scaled number with complete internal consistency.

So this tool re-derives every ``DATA.md`` §19 metric by a **different route**
and compares:

* truth comes from the **written hidden CSVs**, not from re-running ``simulate``
  in memory as ``rhome_eval.run`` does. A disagreement means either the
  generator or the writer is wrong, and nothing else in the project would say so;
* the engine is driven from a **loader written here**, not from the test
  suite's ``_days`` fixture that every existing report imports;
* correlation, RMSE, directional accuracy, the ablation ladder and the decaying
  counter are **implemented here from their definitions**, not imported from
  ``rhome_eval.metrics``;
* and every re-derived figure is then compared against what ``rhome_eval``
  reports for the same quantity, with the disagreement printed.

Three rules, carried from the earlier audits and extended:

* every check reports its measured value, so a marginal pass reads as marginal;
* every check reports its **sample size**, and a check with an empty sample
  FAILS rather than passing vacuously;
* a check that compares the harness against this file states the tolerance it
  used, because "agrees" without a tolerance is not a claim.

Run: ``python3 tools/layer3_audit.py``
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import statistics as st
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATASET = ROOT / "data" / "synthetic" / "athlete_a"
OBSERVABLE = DATASET / "observable"
HIDDEN = DATASET / "hidden"

DEV_DAYS = 520
HOLDOUT_FIRST, HOLDOUT_LAST = 520, 729

# --- reporting ---------------------------------------------------------------

results: list[tuple[str, str, bool, str]] = []


def check(
    section: str, requirement: str, ok: bool, detail: str, *, n: int | None = None
) -> None:
    """Record one check. An empty sample is a failure, never a pass."""
    if n is not None and n == 0:
        results.append((section, requirement, False, f"VACUOUS: n=0 ({detail})"))
        return
    prefix = "" if n is None else f"n={n}  "
    results.append((section, requirement, bool(ok), prefix + detail))


def agrees(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


# =============================================================================
# metrics, implemented here from their definitions
# =============================================================================

def a_pearson(x, y) -> float | None:
    if len(x) != len(y) or len(x) < 8:
        return None
    mx, my = st.fmean(x), st.fmean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return None if sxx <= 0 or syy <= 0 else sxy / math.sqrt(sxx * syy)


def a_ranks(v) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = shared
        i = j + 1
    return out


def a_spearman(x, y) -> float | None:
    if len(x) != len(y) or len(x) < 8:
        return None
    return a_pearson(a_ranks(x), a_ranks(y))


def a_rmse(x, y) -> float | None:
    if len(x) != len(y) or len(x) < 8:
        return None
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(x, y)) / len(x))


def a_directional(x, y) -> tuple[float | None, int]:
    """Agreement of step-to-step direction. Flat steps excluded, and counted."""
    if len(x) != len(y) or len(x) < 8:
        return None, 0
    agree = considered = 0
    for i in range(1, len(x)):
        dx, dy = x[i] - x[i - 1], y[i] - y[i - 1]
        if dx == 0.0 or dy == 0.0:
            continue
        considered += 1
        agree += (dx > 0) == (dy > 0)
    return (agree / considered if considered else None), considered


def a_decaying_count(per_day, half_life_h: float = 30.0):
    decay = math.exp(-math.log(2.0) / half_life_h * 24.0)
    s = 0.0
    out = []
    for v in per_day:
        s = s * decay + v
        out.append(s)
    return out


def a_scale_through_origin(x, y) -> float | None:
    den = sum(v * v for v in x)
    return None if den <= 0 else sum(a * b for a, b in zip(x, y)) / den


# =============================================================================
# A. Provenance — is the artefact under test the one that was signed?
# =============================================================================

for manifest_path in (
    ROOT / "data" / "synthetic_checksums_v0.1.1.json",
    DATASET / "metadata" / "checksums.json",
):
    claimed = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatched = []
    for relative, digest in claimed.items():
        candidate = DATASET / relative
        if not candidate.exists():
            mismatched.append(f"{relative}: MISSING")
        elif hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
            mismatched.append(f"{relative}: DIGEST CHANGED")
    check(
        "A prov",
        f"dataset matches {manifest_path.name}",
        not mismatched,
        "; ".join(mismatched) if mismatched else "every file byte-identical",
        n=len(claimed),
    )

schema = json.loads((DATASET / "metadata" / "schema_version.json").read_text())
config = json.loads((DATASET / "metadata" / "generation_config.json").read_text())
check(
    "A prov",
    "generation config records seed, version and commit (DATA.md §20)",
    all(k in config for k in ("seed", "dataset_version"))
    and any("commit" in k for k in config),
    f"keys: {sorted(config)[:6]}... version={schema.get('dataset_version')}",
    n=len(config),
)

from rhome_eval.window import (  # noqa: E402
    DEVELOPMENT_DAYS,
    HOLDOUT_DAYS,
    holdout_seal,
)

seal = holdout_seal()
check(
    "A prov",
    "holdout opened at most once (DATA.md §15)",
    seal.count <= 1,
    f"{seal.count} openings recorded: {[o[:19] for o in seal.openings]}",
)
check(
    "A prov",
    "the window constants are the documented split",
    tuple(DEVELOPMENT_DAYS) == tuple(range(0, DEV_DAYS))
    and tuple(HOLDOUT_DAYS) == tuple(range(HOLDOUT_FIRST, HOLDOUT_LAST + 1)),
    f"development {DEVELOPMENT_DAYS}, holdout {HOLDOUT_DAYS}",
)

real_manifest = json.loads((ROOT / "data" / "real_manifest.json").read_text())
sealed_ok, sealed_detail = True, []
for relative, entry in real_manifest["files"].items():
    candidate = ROOT / "data" / "real" / relative
    if not candidate.exists():
        sealed_ok = False
        sealed_detail.append(f"{relative}: MISSING")
    elif hashlib.sha256(candidate.read_bytes()).hexdigest() != entry["sha256"]:
        sealed_ok = False
        sealed_detail.append(f"{relative}: CHANGED")
check(
    "A prov",
    "the athlete's sealed export is unmoved (D9)",
    sealed_ok,
    "; ".join(sealed_detail) if sealed_detail else "all files unchanged",
    n=len(real_manifest["files"]),
)

# The seal covers data/real/. The originals it was copied from are elsewhere.
unsealed_copies = [
    p
    for p in (ROOT / "real_oura", ROOT / "spotr_data")
    if p.exists()
]
check(
    "A prov",
    "no second, unsealed copy of the athlete's export exists in the tree",
    not unsealed_copies,
    (
        "UNSEALED ORIGINALS PRESENT: "
        + ", ".join(f"{p.name}/" for p in unsealed_copies)
        + " — not covered by data/real_manifest.json nor by Guardrail 1's markers"
        if unsealed_copies
        else "only data/real/ holds the export"
    ),
)


# =============================================================================
# B. An independent loader, and an independent engine run
# =============================================================================

from rhome_core.exercises import load_library  # noqa: E402
from rhome_core.muscles import Muscle  # noqa: E402
from rhome_engine.dose import LoggedSet, transform_set  # noqa: E402
from rhome_engine.ingest import load_sets  # noqa: E402
from rhome_engine.recovery import RecoveryReading  # noqa: E402
from rhome_engine.session import TRAIN_H, WAKE_H, DayInput, RhomeEngine  # noqa: E402

LIBRARY = load_library()


def _num(value):
    return float(value) if value not in ("", None, "None") else None


def audit_days() -> list[DayInput]:
    """Build the engine's input from the written CSVs, independently.

    Deliberately not ``tests.test_session_driver._days``: every existing Layer 3
    report imports that one fixture, so an error inside it would be invisible to
    all of them at once.
    """
    ingested = load_sets(OBSERVABLE / "sets.csv", LIBRARY)
    with (OBSERVABLE / "workouts.csv").open(encoding="utf-8") as handle:
        workouts = {row["workout_id"]: row for row in csv.DictReader(handle)}
    with (OBSERVABLE / "daily_recovery.csv").open(encoding="utf-8") as handle:
        daily = list(csv.DictReader(handle))
    anchors: dict[str, set[str]] = defaultdict(set)
    with (OBSERVABLE / "performance_tests.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            anchors[row["date"]].add(row["exercise_id"])

    by_date = {row["date"]: i for i, row in enumerate(daily)}
    by_day: dict[int, list[LoggedSet]] = defaultdict(list)
    for performed in ingested.sets:
        by_day[by_date[workouts[performed.workout_id]["date"]]].append(performed)

    return [
        DayInput(
            day_index=i,
            reading=RecoveryReading(
                _num(row["hrv_rmssd_ms"]),
                _num(row["resting_hr_bpm"]),
                _num(row["total_sleep_min"]),
                _num(row["sleep_efficiency"]),
                _num(row["temperature_deviation_c"]),
            ),
            # The independent loader must preserve the observable row order,
            # which is the performed session order used by fatigue curvature.
            sets=list(by_day.get(i, [])),
            body_mass_kg=_num(row["bodyweight_kg"]),
            steps=_num(row["steps"]),
            anchor_exercise_ids=frozenset(anchors.get(row["date"], set())),
        )
        for i, row in enumerate(daily)
    ], ingested


DAYS, INGEST = audit_days()

sys.path.insert(0, str(ROOT / "tests"))
from test_session_driver import _days as harness_days  # noqa: E402

HARNESS_DAYS = harness_days()
check(
    "B load",
    "this loader reproduces the fixture every report is built on",
    DAYS == HARNESS_DAYS,
    f"{len(DAYS)} days, {sum(len(d.sets) for d in DAYS)} sets"
    + ("" if DAYS == HARNESS_DAYS else "  — LOADERS DISAGREE"),
    n=len(DAYS),
)
check(
    "B load",
    "ingest rejects nothing from the clean dataset",
    not INGEST.rejected,
    f"{len(INGEST.rejected)} rejected, {len(INGEST.repaired)} repaired",
    n=len(INGEST.sets),
)

ENGINE = RhomeEngine(LIBRARY)
RESULTS = ENGINE.run(DAYS[:DEV_DAYS])
check(
    "B load",
    "the engine completes the development window",
    len(RESULTS) == DEV_DAYS,
    f"{len(RESULTS)} days, {sum(len(r.observations) for r in RESULTS)} scored sets",
    n=len(RESULTS),
)


# =============================================================================
# C. Truth, read from the written hidden tables
# =============================================================================

with (HIDDEN / "latent_daily.csv").open(encoding="utf-8") as handle:
    LATENT_ROWS = list(csv.DictReader(handle))
with (HIDDEN / "latent_sets.csv").open(encoding="utf-8") as handle:
    LATENT_SETS = list(csv.DictReader(handle))
with (OBSERVABLE / "workouts.csv").open(encoding="utf-8") as handle:
    WORKOUT_DATE = {r["workout_id"]: r["date"] for r in csv.DictReader(handle)}
DATE_INDEX = {r["date"]: int(r["day_index"]) for r in LATENT_ROWS}

MUSCLES = [m.value for m in Muscle]
check(
    "C truth",
    "the hidden table carries one fatigue column per model group",
    all(f"true_fatigue_{m}" in LATENT_ROWS[0] for m in MUSCLES),
    f"{len(MUSCLES)} groups, {len(LATENT_ROWS)} days",
    n=len(MUSCLES),
)

DEV_LATENT = [r for r in LATENT_ROWS if int(r["day_index"]) < DEV_DAYS]
truth_local = {
    m: [float(r[f"true_fatigue_{m}"]) for r in DEV_LATENT] for m in MUSCLES
}
truth_channel = {
    "local_fatigue": [sum(truth_local[m][i] for m in MUSCLES) for i in range(len(DEV_LATENT))],
    "neuromuscular": [float(r["true_neuromuscular_strain"]) for r in DEV_LATENT],
    "systemic": [float(r["true_systemic_fatigue"]) for r in DEV_LATENT],
}

# Cross-check the written table against the in-memory simulation the harness
# uses. These are two different routes to the same quantity and nothing else in
# the project compares them.
from rhome_eval.run import CHANNELS, latent_series  # noqa: E402
from rhome_eval.window import Window  # noqa: E402
from rhome_sim.generate import simulate  # noqa: E402

SIMULATION = simulate(20260822)
MEM_TRUTH = latent_series(SIMULATION, Window.DEVELOPMENT)
worst_gap = 0.0
for channel in CHANNELS:
    written = truth_channel[channel]
    memory = MEM_TRUTH.channel(channel, paired=False)
    worst_gap = max(
        worst_gap, max(abs(a - b) for a, b in zip(written, memory))
    )
#: Tolerance for any figure re-derived from the written tables. The hidden
#: CSVs are written to six decimal places, so a metric computed from disk
#: cannot match one computed in memory more closely than the rounding allows.
#: Stated rather than tuned: it is measured here and used below.
DISK_TOLERANCE = 1e-5

check(
    "C truth",
    "written hidden tables agree with the in-memory simulation",
    worst_gap < DISK_TOLERANCE,
    f"worst absolute disagreement across three channels: {worst_gap:.3e}. "
    f"The hidden tables are rounded to 6 dp, so truth-from-disk and "
    f"truth-from-simulate() are not the same object; every comparison below "
    f"uses a tolerance of {DISK_TOLERANCE:.0e}.",
    n=len(DEV_LATENT) * len(CHANNELS),
)


# =============================================================================
# D. §19.1 — state reconstruction, re-derived
# =============================================================================

LATENT_OFFSET = 1


def est_channel(name: str, paired: bool = True):
    if name == "local_fatigue":
        values = [sum(r.state.local_fatigue.values()) for r in RESULTS]
    else:
        values = [getattr(r.state, name) for r in RESULTS]
    return values[: len(values) - LATENT_OFFSET] if paired else values


def est_muscle(muscle: Muscle, paired: bool = True):
    values = [r.state.local_fatigue[muscle] for r in RESULTS]
    return values[: len(values) - LATENT_OFFSET] if paired else values


def truth_paired(name: str):
    return truth_channel[name][LATENT_OFFSET:]


# The offset is a claim about which instants line up. Verified rather than
# assumed: a wrong offset was the single largest measurement error in Layer 3.
for channel in CHANNELS:
    scores = {}
    for offset in (0, 1, 2):
        estimated = est_channel(channel, paired=False)
        estimated = estimated[: len(estimated) - offset] if offset else estimated
        scores[offset] = a_pearson(estimated, truth_channel[channel][offset:])
    best = max(scores, key=lambda k: scores[k])
    check(
        "D 19.1",
        f"{channel}: the +1 day pairing is the best available",
        best == LATENT_OFFSET,
        "  ".join(f"offset{o} {scores[o]:+.4f}" for o in sorted(scores))
        + f"  → best is offset{best}",
        n=len(truth_paired(channel)),
    )

# The residual misalignment the offset cannot remove.
engine_close_h = WAKE_H + 16.0
sim_wake_h = 8.0
residual_gap_h = (24.0 + sim_wake_h) - engine_close_h
check(
    "D 19.1",
    "the paired instants are the same instant",
    abs(residual_gap_h) < 0.5,
    f"engine day-N state at {engine_close_h:.1f} h; simulator day-N+1 waking at "
    f"{24.0 + sim_wake_h:.1f} h → {residual_gap_h:+.1f} h apart, across the "
    f"overnight recovery. No integer offset closes it.",
)

ALIGNMENT_SCALES = {
    c: a_scale_through_origin(est_channel(c), truth_paired(c)) for c in CHANNELS
}
counter = a_decaying_count(
    [
        sum(1 for s in d.sets if s.set_type in ("working", "backoff"))
        for d in DAYS[:DEV_DAYS]
    ]
)
counter_paired = counter[: len(counter) - LATENT_OFFSET]

channel_scores = {}
for channel in CHANNELS:
    aligned = [v * ALIGNMENT_SCALES[channel] for v in est_channel(channel)]
    truth = truth_paired(channel)
    direction, considered = a_directional(aligned, truth)
    channel_scores[channel] = {
        "pearson": a_pearson(aligned, truth),
        "spearman": a_spearman(aligned, truth),
        "rmse": a_rmse(aligned, truth),
        "direction": direction,
        "direction_n": considered,
        "baseline": a_pearson(counter_paired, truth),
    }
    s = channel_scores[channel]
    check(
        "D 19.1",
        f"{channel}: directional accuracy is above chance (hard floor, D19)",
        s["direction"] is not None and s["direction"] > 0.5,
        f"{s['direction']:.1%} on {considered} moving steps  "
        f"(r={s['pearson']:+.4f}, rho={s['spearman']:+.4f}, RMSE={s['rmse']:.4f})",
        n=considered,
    )
    check(
        "D 19.1",
        f"{channel}: engine beats the decaying set counter (D20)",
        s["pearson"] is not None
        and s["baseline"] is not None
        and s["pearson"] > s["baseline"],
        f"engine {s['pearson']:+.4f}  counter {s['baseline']:+.4f}  "
        f"advantage {s['pearson'] - s['baseline']:+.4f}",
        n=len(truth),
    )

muscle_scores = {}
for muscle in Muscle:
    truth = truth_local[muscle.value][LATENT_OFFSET:]
    muscle_scores[muscle] = {
        "pearson": a_pearson(est_muscle(muscle), truth),
        "baseline": a_pearson(counter_paired, truth),
    }
scored = [v for v in muscle_scores.values() if v["pearson"] is not None]
mean_engine = st.fmean(v["pearson"] for v in scored)
mean_counter = st.fmean(v["baseline"] for v in scored)
worst = min(muscle_scores.items(), key=lambda kv: kv[1]["pearson"] or 2)
check(
    "D 19.1",
    "per-muscle attribution: every group beats the counter (D20)",
    all(v["pearson"] > v["baseline"] for v in scored),
    f"mean engine {mean_engine:+.4f} vs counter {mean_counter:+.4f}; "
    f"worst group {worst[0].value} at {worst[1]['pearson']:+.4f}",
    n=len(scored),
)
check(
    "D 19.1",
    "every model group is scored, none silently dropped",
    len(scored) == len(list(Muscle)),
    f"{len(scored)} of {len(list(Muscle))} groups had a computable correlation",
    n=len(scored),
)

# --- timing (§19.1) ----------------------------------------------------------

TIMING_WINDOW = 6


def peak_and_crossing(series, start: int):
    window = list(series[start : start + TIMING_WINDOW])
    if len(window) < 3:
        return None
    peak = window.index(max(window))
    if window[peak] <= 0:
        return None
    crossing = next(
        (o for o in range(peak + 1, len(window)) if window[o] < window[peak] * 0.5), None
    )
    return peak, crossing


counts = [
    sum(1 for s in d.sets if s.set_type in ("working", "backoff"))
    for d in DAYS[:DEV_DAYS]
]
trained = [c for c in counts if c > 0]
threshold = sorted(trained)[int(len(trained) * 0.75)]
heavy_days = [i for i, c in enumerate(counts) if c >= threshold]

for channel in CHANNELS:
    aligned = [v * ALIGNMENT_SCALES[channel] for v in est_channel(channel)]
    truth = truth_paired(channel)
    peak_errors, crossing_errors, counter_errors = [], [], []
    for start in heavy_days:
        if start + TIMING_WINDOW > len(aligned):
            continue
        left, right = peak_and_crossing(aligned, start), peak_and_crossing(truth, start)
        if left is None or right is None:
            continue
        peak_errors.append(left[0] - right[0])
        if left[1] is not None and right[1] is not None:
            crossing_errors.append(left[1] - right[1])
        counted = peak_and_crossing(counter_paired, start)
        if counted is not None:
            counter_errors.append(counted[0] - right[0])
    within = (
        sum(1 for e in peak_errors if abs(e) <= 1) / len(peak_errors)
        if peak_errors
        else None
    )
    counter_within = (
        sum(1 for e in counter_errors if abs(e) <= 1) / len(counter_errors)
        if counter_errors
        else None
    )
    check(
        "D 19.1",
        f"{channel}: peak timing lands within a day, and beats the counter",
        within is not None
        and within >= 0.8
        and counter_within is not None
        and within >= counter_within,
        f"engine {within:.1%} within ±1 d (median {st.median(peak_errors):+.1f}), "
        f"counter {counter_within:.1%}; crossing median "
        f"{st.median(crossing_errors) if crossing_errors else float('nan'):+.1f} "
        f"on {len(crossing_errors)} crossings",
        n=len(peak_errors),
    )


# =============================================================================
# E. §19.2 — performance prediction, re-derived
# =============================================================================

residuals, res_days, res_experience = [], [], []
seen: dict[str, int] = defaultdict(int)
predictions: list[tuple[int, str, float, float, int]] = []
for result in RESULTS:
    for observation in result.observations:
        # Re-derive the residual from its own definition rather than reading
        # the field the engine stored.
        recomputed = math.log(observation.observed) - math.log(observation.projected)
        residuals.append(recomputed)
        res_days.append(result.day_index)
        res_experience.append(seen[observation.exercise_id])
        predictions.append(
            (
                result.day_index,
                observation.exercise_id,
                observation.observed,
                observation.projected,
                seen[observation.exercise_id],
            )
        )
        seen[observation.exercise_id] += 1

stored = [o.log_residual for r in RESULTS for o in r.observations]
worst_residual_gap = max(abs(a - b) for a, b in zip(residuals, stored))
check(
    "E 19.2",
    "stored residuals equal log(observed) - log(projected)",
    worst_residual_gap < 1e-12,
    f"worst disagreement {worst_residual_gap:.3e}",
    n=len(residuals),
)

audit_mae = st.fmean(abs(v) for v in residuals)
audit_rmse = math.sqrt(st.fmean(v * v for v in residuals))
audit_bias = st.fmean(residuals)
audit_autocorr = a_pearson(residuals[:-1], residuals[1:])
check(
    "E 19.2",
    "one-step-ahead residuals are approximately unbiased (DATA.md §22)",
    abs(audit_bias) < 0.02,
    f"MAE {audit_mae:.4f}  RMSE {audit_rmse:.4f}  bias {audit_bias:+.4f}  "
    f"lag-1 autocorrelation {audit_autocorr:+.4f}",
    n=len(residuals),
)

# Bias sliced before it is pooled — a pooled zero can be two opposite biases.
blocks: dict[int, list[float]] = defaultdict(list)
for residual, day in zip(residuals, res_days):
    blocks[(day // 100) * 100].append(residual)
block_means = {k: st.fmean(v) for k, v in sorted(blocks.items()) if len(v) >= 8}
drift_span = max(block_means.values()) - min(block_means.values())
check(
    "E 19.2",
    "time drift is reported, and its span is stated not hidden by pooling",
    drift_span < 0.10,
    "  ".join(f"d{k}:{v:+.4f}" for k, v in block_means.items())
    + f"  span {drift_span:.4f} vs pooled {audit_bias:+.4f}",
    n=sum(len(v) for v in blocks.values()),
)

# --- the ablation ladder, re-implemented -------------------------------------

def audit_ladder(minimum_prior: int = 0):
    history: dict[str, list[float]] = defaultdict(list)
    rows = []
    for day, exercise_id, observed, projected, prior in sorted(
        predictions, key=lambda p: (p[0], p[1])
    ):
        past = history[exercise_id]
        candidates = {
            "last observation": past[-1] if past else None,
            "median of last 3": st.median(past[-3:]) if len(past) >= 3 else None,
            "median of last 5": st.median(past[-5:]) if len(past) >= 5 else None,
            "mean of last 5": st.fmean(past[-5:]) if len(past) >= 5 else None,
        }
        if (
            prior >= minimum_prior
            and all(v is not None and v > 0 for v in candidates.values())
            and projected > 0
            and observed > 0
        ):
            rows.append((observed, {"engine": projected, **candidates}))
        past.append(observed)
    if not rows:
        return {}, 0
    errors: dict[str, list[float]] = defaultdict(list)
    for observed, predicted in rows:
        for name, value in predicted.items():
            errors[name].append(math.log(observed / value))
    engine_abs = [abs(v) for v in errors["engine"]]
    out = {}
    for name, values in errors.items():
        absolute = [abs(v) for v in values]
        entry = {"mae": st.fmean(absolute), "n": len(values)}
        if name != "engine":
            paired = [b - a for a, b in zip(engine_abs, absolute)]
            spread = st.pstdev(paired)
            entry["delta"] = st.fmean(paired)
            entry["interval"] = 1.96 * spread / math.sqrt(len(paired))
            entry["verdict"] = (
                "engine better"
                if entry["delta"] > entry["interval"]
                else "baseline better"
                if entry["delta"] < -entry["interval"]
                else "tie"
            )
        out[name] = entry
    return out, len(rows)


for label, minimum in (("all sets", 0), ("20+ prior observations", 20)):
    ladder, n = audit_ladder(minimum)
    losses = [k for k, v in ladder.items() if v.get("verdict") == "baseline better"]
    ties = [k for k, v in ladder.items() if v.get("verdict") == "tie"]
    detail = "  ".join(
        f"{k}:{v['mae']:.4f}" + (f"[{v['verdict']}]" if "verdict" in v else "")
        for k, v in sorted(ladder.items(), key=lambda kv: kv[1]["mae"])
    )
    check(
        "E 19.2",
        f"ablation ladder ({label}): the engine loses to nothing (D20)",
        not losses,
        detail + (f"  LOSES TO {losses}" if losses else "") + f"  ties: {ties or 'none'}",
        n=n,
    )
    check(
        "E 19.2",
        f"ablation ladder ({label}): the engine's win is not merely a tie",
        not ties,
        f"tied against {ties}" if ties else "beats every baseline outright",
        n=n,
    )

# --- capacity (§19.2) --------------------------------------------------------

# Truth read from latent_sets.csv, an independent route to the same quantity.
# The simulator's chain is capacity -> fatigue -> stochastic shock -> load, and
# ``RealisedSet`` records the shock as its own field. Dividing the realised
# value by ``fatigue_factor`` alone therefore leaves the shock in the "truth".
# Tested against a hard floor: a quantity called *neutral capacity* must be
# constant across the sets of one day, and its spread says whether it is.
def capacity_target(divide_shock: bool, keep: str) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = defaultdict(dict)
    for row in LATENT_SETS:
        factor = float(row["fatigue_factor"])
        if factor <= 0:
            continue
        day = DATE_INDEX[WORKOUT_DATE[row["workout_id"]]]
        value = float(row["true_expressible_capacity"]) / factor
        if divide_shock:
            value /= float(row["performance_shock"])
        if keep == "first":
            out[row["exercise_id"]].setdefault(day, value)
        else:
            out[row["exercise_id"]][day] = value
    return out


def within_day_spread(divide_shock: bool) -> list[float]:
    grouped: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in LATENT_SETS:
        factor = float(row["fatigue_factor"])
        if factor <= 0:
            continue
        value = float(row["true_expressible_capacity"]) / factor
        if divide_shock:
            value /= float(row["performance_shock"])
        grouped[
            (row["exercise_id"], DATE_INDEX[WORKOUT_DATE[row["workout_id"]]])
        ].append(value)
    return sorted(
        (max(v) - min(v)) / max(v)
        for v in grouped.values()
        if len(v) > 1 and max(v) > 0
    )


as_used = within_day_spread(False)
shock_free = within_day_spread(True)

# What the harness ACTUALLY uses, re-derived independently from the CSVs and
# checked in both directions: it must match the shock-free target and must not
# match the contaminated one. Checking only that it matches the right answer
# would pass just as well if both expressions happened to coincide, which is
# D17's lesson applied to a target instead of a parameter.
audit_clean = capacity_target(True, "first")
audit_dirty = capacity_target(False, "last")
harness_capacity = MEM_TRUTH.capacity


def _relative_gap(reference) -> float:
    worst = 0.0
    for exercise_id, series in harness_capacity.items():
        for day, value in series.items():
            other = reference.get(exercise_id, {}).get(day)
            if other:
                worst = max(worst, abs(value - other) / other)
    return worst


gap_clean = _relative_gap(audit_clean)
gap_dirty = _relative_gap(audit_dirty)
check(
    "E 19.2",
    "the harness's capacity target has the per-set shock removed",
    gap_clean < DISK_TOLERANCE and gap_dirty > 0.01,
    f"against an independent shock-free rebuild: {gap_clean:.3e} — matches. "
    f"Against the pre-fix expression (cap / fatigue_factor, last set of the "
    f"day): {gap_dirty:.2%} — differs, so the fix is live and not a coincidence.",
    n=sum(len(v) for v in harness_capacity.values()),
)
check(
    "E 19.2",
    "the capacity target is constant within a day, as 'neutral capacity' must be",
    st.median(shock_free) < 0.005 and st.median(as_used) > 0.005,
    f"the target in use has a within-day spread of median "
    f"{st.median(shock_free):.4%}, max {max(shock_free):.4%} — the 6 dp "
    f"rounding floor of the CSV. Leaving the shock in, as this did before the "
    f"L3 audit, gives median {st.median(as_used):.4%}, p90 "
    f"{as_used[int(0.9 * len(as_used))]:.4%}, max {max(as_used):.4%}.",
    n=len(shock_free),
)

# expressible must keep the fatigue factor and lose only the shock.
# Both series are pinned to the FIRST set of each day, so the comparison must
# be too: within a session the fatigue factor falls set by set, and comparing
# against a later set's factor measures that fall rather than this identity.
expressible_gap = 0.0
compared = 0
first_seen: set[tuple[str, int]] = set()
for row in LATENT_SETS:
    factor = float(row["fatigue_factor"])
    shock = float(row["performance_shock"])
    if factor <= 0 or shock <= 0:
        continue
    day = DATE_INDEX[WORKOUT_DATE[row["workout_id"]]]
    key = (row["exercise_id"], day)
    if key in first_seen:
        continue
    first_seen.add(key)
    expected = MEM_TRUTH.capacity.get(row["exercise_id"], {}).get(day)
    actual = MEM_TRUTH.expressible.get(row["exercise_id"], {}).get(day)
    if expected is None or actual is None:
        continue
    compared += 1
    expressible_gap = max(
        expressible_gap, abs(actual - expected * factor) / max(actual, 1e-12)
    )
check(
    "E 19.2",
    "LatentSeries.expressible is capacity times the fatigue factor, nothing more",
    expressible_gap < DISK_TOLERANCE,
    f"worst relative disagreement {expressible_gap:.3e} against "
    f"capacity x fatigue_factor, on the first set of each day. Dividing the "
    f"fatigue factor out here too would "
    f"compare a performance gain against a neutral-capacity gain, which is "
    f"L3.4's second measurement error.",
    n=compared,
)

truth_capacity_last = audit_clean

# The engine's own capacity estimate at each scored set, for the comparison.
tracked: dict[str, list[tuple[int, float]]] = defaultdict(list)
for result in RESULTS:
    for observation in result.observations:
        tracked[observation.exercise_id].append(
            (result.day_index, observation.capacity_before)
        )

def capacity_scores(truth_by_exercise):
    everything = [
        (v, truth_by_exercise[e][d])
        for e, series in tracked.items()
        for d, v in series
        if d in truth_by_exercise.get(e, {}) and truth_by_exercise[e][d] > 0
    ]
    scale = a_scale_through_origin(
        [a for a, _ in everything], [b for _, b in everything]
    )
    rows = []
    for exercise_id, series in sorted(tracked.items()):
        truth = truth_by_exercise.get(exercise_id, {})
        pairs = [(v, truth[d]) for d, v in series if d in truth and truth[d] > 0]
        if len(pairs) < 8:
            continue
        rows.append(
            (
                exercise_id,
                len(pairs),
                a_pearson([a for a, _ in pairs], [b for _, b in pairs]),
                st.fmean([a / b - 1 for a, b in pairs]),
                st.fmean([a * scale / b - 1 for a, b in pairs]),
            )
        )
    return scale, rows


capacity_scale, capacity_rows = capacity_scores(truth_capacity_last)
dirty_scale, dirty_rows = capacity_scores(audit_dirty)
raw_error = st.fmean(abs(r[3]) for r in capacity_rows)
aligned_error = st.fmean(abs(r[4]) for r in capacity_rows)
mean_r = st.fmean(r[2] for r in capacity_rows)
dirty_r = st.fmean(r[2] for r in dirty_rows)
dirty_aligned = st.fmean(abs(r[4]) for r in dirty_rows)
worst_row = min(capacity_rows, key=lambda r: r[2])
worst_dirty = next(r for r in dirty_rows if r[0] == worst_row[0])
check(
    "E 19.2",
    "capacity tracks true neutral capacity after one global scale",
    aligned_error < 0.08 and mean_r > 0.5,
    f"mean r {mean_r:+.4f}; |error| {raw_error:.2%} raw → {aligned_error:.2%} "
    f"after a single scale of {capacity_scale:.4f}",
    n=len(capacity_rows),
)
check(
    "E 19.2",
    "capacity correlation is measured against a target with no noise in it",
    mean_r > 0.90,
    f"mean r {mean_r:+.4f} across {len(capacity_rows)} exercises, worst "
    f"{worst_row[0]} at {worst_row[2]:+.3f}. Against the pre-fix contaminated "
    f"target the same run reads {dirty_r:+.4f}, worst {worst_dirty[2]:+.3f} — "
    f"the shock destroyed correlation without moving the mean error "
    f"({dirty_aligned:.2%} vs {aligned_error:.2%}), which is why every check "
    f"that looked at a mean passed.",
    n=len(capacity_rows),
)
check(
    "E 19.2",
    "the capacity scale is one parameter, not one per exercise",
    True,
    f"one scale ({capacity_scale:.4f}) applied to all {len(capacity_rows)} "
    f"exercises; a per-exercise scale would fit away the error being reported",
    n=len(capacity_rows),
)


# =============================================================================
# F. §19.3 — ranking, re-derived with novelty matched on both sides
# =============================================================================

from rhome_core.intensity import relative_intensity  # noqa: E402
from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: E402
from rhome_eval.ranking import CASES as RANKING_CASES  # noqa: E402
from rhome_eval.ranking import run_rankings  # noqa: E402
from rhome_sim.athlete import sample_athlete  # noqa: E402
from rhome_sim.physiology import Physiology  # noqa: E402

NOVELTY_CAP = ENGINE_PARAMETERS.value("novelty_cap")
NOVELTY_DECAY = ENGINE_PARAMETERS.value("novelty_decay_exposures")


def engine_dose_total(spec, channel, muscles, with_novelty: bool) -> float:
    total = 0.0
    exposures: dict[str, int] = {}
    local_positions: dict[object, int] = defaultdict(int)
    gamma = ENGINE_PARAMETERS.value("within_session_fatigue_gamma")
    position_cap = int(ENGINE_PARAMETERS.value("within_session_position_cap"))
    for logged in spec.logged():
        exercise = LIBRARY[logged.exercise_id]
        novelty = 1.0
        if with_novelty:
            novelty = 1.0 + (NOVELTY_CAP - 1.0) * math.exp(
                -exposures.get(logged.exercise_id, 0) / NOVELTY_DECAY
            )
        dose = transform_set(logged, exercise, novelty=novelty)
        exposures[logged.exercise_id] = exposures.get(logged.exercise_id, 0) + 1
        if channel == "local_fatigue":
            selected = muscles or tuple(dose.local_fatigue)
            total += sum(
                dose.local_fatigue.get(m, 0.0)
                * (1.0 + gamma * min(local_positions.get(m, 0), position_cap))
                for m in selected
            )
        else:
            total += getattr(dose, channel)
        for muscle in dose.local_fatigue:
            local_positions[muscle] += 1
    return total


def truth_dose_total(spec, channel, muscles) -> float:
    physiology = Physiology(sample_athlete(20260822))
    physiology.begin_session()
    total = 0.0
    exposures: dict[str, int] = {}
    for logged in spec.logged():
        exercise = LIBRARY[logged.exercise_id]
        intensity, _ = relative_intensity(
            logged.reps, logged.rir, exercise.nuzzo_curve.value
        )
        exposures[logged.exercise_id] = exposures.get(logged.exercise_id, 0) + 1
        impulse = physiology.apply_set(
            exercise, logged.reps, logged.rir, intensity, exposures[logged.exercise_id]
        )
        if channel == "local_fatigue":
            selected = muscles or tuple(impulse.local)
            total += sum(impulse.local.get(m, 0.0) for m in selected)
        else:
            total += getattr(impulse, channel)
    return total


novelty_one, matched = [], []
wrong_way = []
for case in RANKING_CASES:
    truth_h = truth_dose_total(case.higher, case.channel, case.muscles)
    truth_l = truth_dose_total(case.lower, case.channel, case.muscles)
    truth_margin = truth_h / max(truth_l, 1e-12) - 1
    for with_novelty, bucket in ((False, novelty_one), (True, matched)):
        eh = engine_dose_total(case.higher, case.channel, case.muscles, with_novelty)
        el = engine_dose_total(case.lower, case.channel, case.muscles, with_novelty)
        bucket.append((eh / max(el, 1e-12) - 1) / truth_margin)
    eh = engine_dose_total(case.higher, case.channel, case.muscles, True)
    el = engine_dose_total(case.lower, case.channel, case.muscles, True)
    if not (eh > el and truth_h > truth_l):
        wrong_way.append(case.name)

check(
    "F 19.3",
    "every constructed ordering is correct in engine and simulator alike",
    not wrong_way,
    f"{len(RANKING_CASES) - len(wrong_way)}/{len(RANKING_CASES)} correct"
    + (f"; WRONG: {wrong_way}" if wrong_way else ""),
    n=len(RANKING_CASES),
)
check(
    "F 19.3",
    "no contrast moves farther from truth than the frozen v0 baseline",
    all(
        abs(current - 1.0) <= abs(frozen - 1.0) + 0.001
        for current, frozen in zip(
            matched, (0.576, 0.788, 0.764, 0.688, 0.681)
        )
    ),
    "repaired "
    + "  ".join(f"{r:.3f}" for r in matched)
    + " vs frozen v0 0.576  0.788  0.764  0.688  0.681",
    n=len(matched),
)
check(
    "F 19.3",
    "the novelty-matched path is distinguishable from a novelty=1 control",
    any(abs(a - b) > 0.005 for a, b in zip(novelty_one, matched)),
    f"novelty=1 {[round(r, 4) for r in novelty_one]} vs matched "
    f"{[round(r, 4) for r in matched]}; a bypass cannot pass by coincidence",
    n=len(matched),
)

harness_rankings = run_rankings()
harness_ratios = [r.engine_margin / r.truth_margin for r in harness_rankings]
check(
    "F 19.3",
    "this file reproduces rhome_eval.ranking exactly (tolerance 1e-9)",
    all(agrees(a, b, 1e-9) for a, b in zip(matched, harness_ratios)),
    f"audit {[round(r, 4) for r in matched]} vs harness "
    f"{[round(r, 4) for r in harness_ratios]}",
    n=len(harness_ratios),
)


# =============================================================================
# G. §19.4 — calibration bands, re-derived
# =============================================================================

from rhome_eval.calibration import CASES as CAL_CASES  # noqa: E402
from rhome_eval.calibration import run_calibration  # noqa: E402

CAL_RESULTS = run_calibration()
outside = [
    (r.case.name, r.engine_lower_body, r.case.lower_bound, r.case.upper_bound)
    for r in CAL_RESULTS
    if not r.in_band
]
overshoot = max(
    (
        max(
            r.case.lower_bound - r.engine_lower_body,
            r.engine_lower_body - r.case.upper_bound,
        )
        for r in CAL_RESULTS
        if not r.in_band
    ),
    default=0.0,
)
check(
    "G 19.4",
    "the repaired engine's documented absolute-calibration gap is reproduced",
    len(outside) == 4
    and all(
        r.engine_lower_body < r.simulator_lower_body
        for r in CAL_RESULTS[1:]
    ),
    f"{len(CAL_RESULTS) - len(outside)}/{len(CAL_RESULTS)} in band; "
    + (
        f"outside: {[(n, f'{v:.2%}', f'{lo:.1%}-{hi:.1%}') for n, v, lo, hi in outside]}, "
        f"worst overshoot {overshoot:.2%}"
        if outside
        else "all in band"
    ),
    n=len(CAL_RESULTS),
)
check(
    "G 19.4",
    "the numerical-stability clip binds in no calibration case (§19.4)",
    not any(r.clip_bound for r in CAL_RESULTS),
    f"{sum(1 for r in CAL_RESULTS if r.clip_bound)} cases clip-bound",
    n=len(CAL_RESULTS),
)
check(
    "G 19.4",
    "upper-body sits below lower-body, as §19.4 predicts",
    all(r.upper_body_gap > 0 for r in CAL_RESULTS),
    "gaps (pp): " + "  ".join(f"{r.upper_body_gap:.2f}" for r in CAL_RESULTS),
    n=len(CAL_RESULTS),
)
# The bands are "checked against the simulator's own suppression". Report the
# gap rather than only the engine's own number.
# §19.4: the bands are "checked against the simulator's own suppression". So
# the simulator has to satisfy them too, or the bands describe the engine
# rather than the world the engine is reconstructing.
sim_outside = [
    (r.case.name, r.simulator_lower_body, r.case.lower_bound, r.case.upper_bound)
    for r in CAL_RESULTS
    if not (r.case.lower_bound <= r.simulator_lower_body <= r.case.upper_bound)
]
check(
    "G 19.4",
    "the SIMULATOR lands inside every documented band (§19.4, D21 option 2)",
    not sim_outside,
    f"{len(CAL_RESULTS) - len(sim_outside)}/{len(CAL_RESULTS)} in band. "
    + "  ".join(
        f"{r.case.name.split(',')[0][:16]}: eng {r.engine_lower_body:.2%} / sim "
        f"{r.simulator_lower_body:.2%} / band {r.case.lower_bound:.1%}-{r.case.upper_bound:.1%}"
        for r in CAL_RESULTS
    )
    + ". DATA.md v0.9.0 makes the simulator-centred bands binding and leaves "
    "the repaired engine's compressed accumulated suppression visible.",
    n=len(CAL_RESULTS),
)
# §19.4's table header reads "evaluated 24 h after the most recent session".
bad_ages = [
    (c.name, min(age for age, *_ in c.protocol.events))
    for c in CAL_CASES
    if min(age for age, *_ in c.protocol.events) != 24.0
]
check(
    "G 19.4",
    "every band is read 24 h after the most recent session, as the table says",
    not bad_ages,
    f"cases whose newest event is not at 24 h: "
    + (", ".join(f"{n} ({h:.0f} h)" for n, h in bad_ages) if bad_ages else "none")
    + ". §19.4's table header applies to every row.",
    n=len(CAL_CASES),
)


# =============================================================================
# H. §19.5 — confidence behaviour
# =============================================================================

binding_wrong = 0
for result in RESULTS:
    if not result.confidence:
        continue
    lowest = min(c.value for c in result.confidence.fatigue.components)
    if abs(result.confidence.fatigue.binding_reason.value - lowest) > 1e-12:
        binding_wrong += 1
check(
    "H 19.5",
    "the binding reason is always the lowest-scoring component",
    binding_wrong == 0,
    f"{binding_wrong} days where it was not",
    n=len(RESULTS),
)

blank = [r for r in RESULTS if r.recovery.channels_present == 0]
complete = [r for r in RESULTS if r.recovery.channels_present == 5]
penalty = st.fmean(r.confidence.fatigue.value for r in complete) - st.fmean(
    r.confidence.fatigue.value for r in blank
)
check(
    "H 19.5",
    "confidence falls when every wearable channel is withheld",
    penalty > 0,
    f"complete nights {st.fmean(r.confidence.fatigue.value for r in complete):.4f} "
    f"vs blank nights {st.fmean(r.confidence.fatigue.value for r in blank):.4f} "
    f"→ {penalty:+.4f} on {len(blank)} blank nights",
    n=len(blank),
)

# §19 names particular scenarios as acceptance criteria. A criterion whose
# scenario lives only in the holdout cannot be evaluated at all during
# development, and whatever stands in for it is a constructed substitute.
scenario_days: dict[str, list[int]] = defaultdict(list)
for row in LATENT_ROWS:
    for label in row["scenario_labels"].split("|"):
        if label and label != "S0_ordinary":
            scenario_days[label].append(int(row["day_index"]))

NAMED_BY_19 = {
    "S12_missed_block": "§19.5 confidence must not fall during the missed block",
    "S11_bad_day": "§19.2/§19.7 approved 2.1% median, 3.3% worst gate",
    "S10_pr_window": "§19.7 PR-window gains attributed to reduced fatigue",
    "S9_plateau": "§19.7 estimated capacity stays flat",
    "S3_deload": "§19.7 deload rebound attributed to reduced fatigue",
    "S1_high_volume": "§19.4 overload block calibration band",
    "S2_failure_heavy": "§19.4 failure-heavy block calibration band",
}
holdout_only = {
    label: (min(days), max(days))
    for label, days in scenario_days.items()
    if min(days) >= DEV_DAYS
}
unevaluable = sorted(set(NAMED_BY_19) & set(holdout_only))
check(
    "H 19.5",
    "every scenario §19 names as a criterion occurs in the development window",
    not unevaluable,
    "holdout-only: "
    + ", ".join(f"{k} (days {holdout_only[k][0]}-{holdout_only[k][1]})" for k in sorted(holdout_only))
    + f". Of these, {unevaluable} are named directly by DATA.md §19, so those "
    f"criteria can only be checked against a constructed substitute. "
    f"DATA.md §15: 'Scenario families should appear in both windows.'",
    n=len(scenario_days),
)

scenario_labels = {int(r["day_index"]): r["scenario_labels"] for r in DEV_LATENT}
missed = [r for r in RESULTS if "S12" in scenario_labels.get(r.day_index, "")]
if missed:
    nearby = [
        r
        for r in RESULTS
        if min(abs(r.day_index - m.day_index) for m in missed) <= 30
        and "S12" not in scenario_labels.get(r.day_index, "")
    ]
    inside = st.fmean(r.confidence.fatigue.value for r in missed)
    outside = st.fmean(r.confidence.fatigue.value for r in nearby)
    check(
        "H 19.5",
        "fatigue confidence does not fall during the missed-session block (S12)",
        inside >= outside - 0.02,
        f"inside {inside:.4f} vs neighbouring days {outside:.4f} → {inside - outside:+.4f}",
        n=len(missed),
    )
else:
    # A long training-free stretch is the same physical situation, and it is
    # the nearest thing the development window contains.
    gaps: list[list[int]] = []
    run_of_rest: list[int] = []
    for result in RESULTS:
        if result.trained:
            if run_of_rest:
                gaps.append(run_of_rest)
            run_of_rest = []
        else:
            run_of_rest.append(result.day_index)
    if run_of_rest:
        gaps.append(run_of_rest)
    longest = max(gaps, key=len) if gaps else []
    by_day = {r.day_index: r for r in RESULTS}
    if longest:
        inside = st.fmean(by_day[d].confidence.fatigue.value for d in longest)
        outside = st.fmean(
            by_day[d].confidence.fatigue.value
            for d in range(max(0, longest[0] - 30), longest[0])
            if d in by_day
        )
        check(
            "H 19.5",
            "the development window contains an analogue of the missed block",
            len(longest) >= 7,
            f"S12 is 10 days and holdout-only. The LONGEST training-free stretch "
            f"anywhere in the 520-day development window is {len(longest)} days "
            f"(from day {longest[0]}); confidence across it moved "
            f"{inside - outside:+.4f} ({inside:.4f} vs {outside:.4f} over the "
            f"preceding 30 days). §19.5's criterion has no development analogue.",
            n=len(longest),
        )
    else:
        check("H 19.5", "fatigue confidence holds across a rest block", False,
              "no training-free stretch of 5+ days in the development window", n=0)

# Capacity confidence must not read `high` before the engine is competitive.
from rhome_engine.confidence import Band  # noqa: E402

seen_ex: dict[str, int] = defaultdict(int)
early_bands: list[str] = []
for result in RESULTS:
    for observation in result.observations:
        seen_ex[observation.exercise_id] += 1
        entry = result.confidence.capacity.get(observation.exercise_id)
        if entry is not None and seen_ex[observation.exercise_id] <= 10:
            early_bands.append(entry.band.value)
high_early = sum(1 for b in early_bands if b == Band.HIGH.value)
check(
    "H 19.5",
    "no `high` capacity confidence in an exercise's first ten sessions (LIM-C3)",
    high_early == 0,
    f"{high_early} of {len(early_bands)} early readings said high",
    n=len(early_bands),
)


# =============================================================================
# I. §19.6 — trace integrity, and the ledger's fold-and-residual arithmetic
# =============================================================================

TRACES = [t for r in RESULTS for t in r.traces.values()]
worst_share = max(abs(t.share_total() - 1.0) for t in TRACES)
worst_reconstruction = max(
    abs(t.reconstruct() - t.value) / max(t.value, 1e-12) for t in TRACES
)
check(
    "I 19.6",
    "contributor shares sum to 1.0 (hard constraint, D19)",
    worst_share < 1e-9,
    f"worst deviation from unity {worst_share:.3e}",
    n=len(TRACES),
)
check(
    "I 19.6",
    "a state reconstructs exactly from its listed contributors",
    worst_reconstruction < 1e-9,
    f"worst relative reconstruction error {worst_reconstruction:.3e}",
    n=len(TRACES),
)

from rhome_engine.trace import ClaimBoundaryError, check_claim_boundaries  # noqa: E402

drivers = {t.driver for t in TRACES if t.driver}
violations = []
for driver in drivers:
    try:
        check_claim_boundaries(driver)
    except ClaimBoundaryError as error:
        violations.append(str(error))
check(
    "I 19.6",
    "no emitted driver string crosses a RESEARCH.md §17 claim boundary",
    not violations,
    f"{len(drivers)} distinct drivers checked; violations: {violations or 'none'}",
    n=len(drivers),
)

# --- the ledger's fold, audited directly -------------------------------------
# The residual entry is the part with no independent check anywhere: folding is
# supposed to CONSERVE surviving mass, not merely to tidy up.

from rhome_engine.ledger import Channel, ContributionLedger, Impulse  # noqa: E402

HALF_LIVES = {
    Channel.LOCAL_FATIGUE: ENGINE_PARAMETERS.value("local_half_life_h"),
    Channel.NEUROMUSCULAR: ENGINE_PARAMETERS.value("neuromuscular_half_life_h"),
    Channel.SYSTEMIC: ENGINE_PARAMETERS.value("systemic_half_life_h"),
}
probe = ContributionLedger(HALF_LIVES, ENGINE_PARAMETERS.value("adaptation_time_constant_days") * 24.0)
for i in range(40):
    probe.record(Channel.LOCAL_FATIGUE, "quads", 1.0, i * 24.0, i * 24.0, f"s{i}", f"set {i}")
now = 40 * 24.0
before_entries = probe.size()
before_mass = sum(
    c.surviving for c in probe.contributions(Channel.LOCAL_FATIGUE, "quads", 1.0, now, now)
)
probe.fold_old(now, now)
after_entries = probe.size()
after_mass = sum(
    c.surviving for c in probe.contributions(Channel.LOCAL_FATIGUE, "quads", 1.0, now, now)
)
check(
    "I ledger",
    "folding conserves surviving mass exactly",
    abs(after_mass - before_mass) < 1e-12 * max(before_mass, 1.0),
    f"{before_entries} entries → {after_entries}; mass {before_mass:.12f} → "
    f"{after_mass:.12f}  (delta {after_mass - before_mass:+.3e})",
    n=before_entries,
)

# Fold twice: a residual re-expressed at a new clock must not gain or lose mass.
probe.fold_old(now + 24.0, now + 24.0)
twice_mass = sum(
    c.surviving
    for c in probe.contributions(Channel.LOCAL_FATIGUE, "quads", 1.0, now + 24.0, now + 24.0)
)
expected = after_mass * math.exp(-math.log(2.0) / HALF_LIVES[Channel.LOCAL_FATIGUE] * 24.0)
check(
    "I ledger",
    "a re-expressed residual decays like any other contributor",
    abs(twice_mass - expected) < 1e-9 * max(expected, 1.0),
    f"after a second fold {twice_mass:.12f}, expected {expected:.12f} "
    f"(delta {twice_mass - expected:+.3e})",
    n=probe.size(),
)

# Impulse is a plain dataclass, so `e not in spent` is VALUE equality. Two
# genuinely distinct sets recorded with identical fields would be indistinct.
collide = ContributionLedger(HALF_LIVES, 1008.0)
for _ in range(2):
    collide.record(Channel.LOCAL_FATIGUE, "quads", 1.0, 0.0, 0.0, "same", "same")
collide.record(Channel.LOCAL_FATIGUE, "quads", 1.0, 5000.0, 5000.0, "recent", "recent")
kept_before = collide.size()
collide.fold_old(5000.0, 5000.0)
check(
    "I ledger",
    "two identically-valued impulses are folded as two, not collapsed to one",
    collide.size() == 2,
    f"{kept_before} entries before the fold, {collide.size()} after "
    f"(expected 2: one residual + one live). Impulse uses value equality in "
    f"`e not in spent`, so identical sets are interchangeable.",
    n=kept_before,
)

# Activity must be a contributor, or shares fall short on any day with walking.
walked = [r for r in RESULTS if r.activity_amplitude > 0 and r.trained]
if walked:
    sample = walked[len(walked) // 2]
    share_error = max(abs(t.share_total() - 1.0) for t in sample.traces.values())
    check(
        "I ledger",
        "background activity is recorded as a contributor, not lost",
        share_error < 1e-9,
        f"day {sample.day_index} (amplitude {sample.activity_amplitude:.4f}): "
        f"worst share deviation {share_error:.3e} across {len(sample.traces)} traces",
        n=len(walked),
    )
else:
    check("I ledger", "background activity is a contributor", False, "no walking day", n=0)


# =============================================================================
# J. Guardrail 2 — the frozen projection, audited as a mechanism
# =============================================================================

frozen_records = [f for r in RESULTS for f in r.projections.values()]
bad_digests = [f for f in frozen_records if not f.verify()]
check(
    "J G2",
    "every frozen projection verifies its own content digest",
    not bad_digests,
    f"{len(bad_digests)} failed verification",
    n=len(frozen_records),
)
distinct = {(f.exercise_id, f.session_key) for f in frozen_records}
check(
    "J G2",
    "no session key carries two projections for the same exercise",
    len(distinct) == len(frozen_records),
    f"{len(frozen_records)} records, {len(distinct)} distinct keys",
    n=len(frozen_records),
)
# The freeze must precede the session it predicts. The engine places sets from
# TRAIN_H onward, so a projection frozen at or after TRAIN_H + 0.02 saw a set.
late = [f for f in frozen_records if f.frozen_at_h % 24.0 > TRAIN_H + 1e-9]
check(
    "J G2",
    "every projection was frozen before the first set of its session",
    not late,
    f"{len(late)} frozen at or after the session's first set "
    f"(sets begin at hour {TRAIN_H:.2f}); all freezes at hour "
    f"{sorted({round(f.frozen_at_h % 24.0, 3) for f in frozen_records})}",
    n=len(frozen_records),
)
# ...and whether anything would have STOPPED a late freeze.
performance_src = (ROOT / "src" / "rhome_engine" / "performance.py").read_text()
compares_time = any(
    "frozen_at_h" in line and any(op in line for op in ("<", ">", "<=", ">="))
    for line in performance_src.splitlines()
)
check(
    "J G2",
    "the ordering is ENFORCED, not merely observed to hold",
    compares_time,
    "frozen_at_h is stored and hashed but never compared to the session's set "
    "times; the ordering rests on statement order in RhomeEngine.process_day, "
    "which is a convention, not a guardrail"
    if not compares_time
    else "a temporal comparison exists",
)


# =============================================================================
# J2. §19.7 — the capacity-estimator tests, registered at this audit
# =============================================================================
# The only subsection of §19 never entered in the conformance map. Coverage read
# 100% throughout, because coverage is measured against the register and nobody
# asked whether the register was complete. Registering it exposed two failing
# acceptance criteria immediately.

from rhome_eval.performance_metrics import (  # noqa: E402
    clip_bounded_displacement,
    single_bad_day_displacement,
)

s11_rows = []
for _exercise, _day in (
    ("bench_press", 203), ("back_squat", 204), ("deadlift", 207),
    ("back_squat", 218), ("deadlift", 214), ("bench_press", 210),
):
    immediate, settled, eligible = single_bad_day_displacement(DAYS, _day, _exercise)
    s11_rows.append((_exercise, _day, eligible, immediate, settled))

worst_s11 = max(abs(r[3]) for r in s11_rows)
worst_settled = max(abs(r[4]) for r in s11_rows)
check(
    "J2 19.7",
    "one bad session passes the approved immediate robustness limits",
    st.median([abs(r[3]) for r in s11_rows]) <= 0.021
    and worst_s11 <= 0.033,
    f"median {st.median([abs(r[3]) for r in s11_rows]):.3%}, worst "
    f"{worst_s11:.3%} across sessions of {sorted({r[2] for r in s11_rows})} "
    f"eligible sets; explicit ordinary/anchor session bounds are "
    f"{clip_bounded_displacement(1):.3%}/"
    f"{clip_bounded_displacement(1, anchor=True):.3%}.",
    n=len(s11_rows),
)
check(
    "J2 19.7",
    "one bad session does not PERMANENTLY depress capacity",
    worst_settled < 0.005,
    f"worst residual displacement after 90 days: {worst_settled:.3%}. The "
    f"spirit of §19.7 holds even where the letter does not.",
    n=len(s11_rows),
)
check(
    "J2 19.7",
    "the bad-session bound is independent of pseudo-replicated set count",
    clip_bounded_displacement(1) == clip_bounded_displacement(5),
    "one correlated session receives one update and one explicit bound; its "
    "eligible sets contribute evidence, not repeated capacity movements.",
    n=len(s11_rows),
)

# S9 plateau, engine side.
def _capacity_at(exercise_id: str, day: int):
    value = None
    for result in RESULTS[: day + 1]:
        for observation in result.observations:
            if observation.exercise_id == exercise_id:
                value = observation.capacity_after
    return value


_lifts = ("bench_press", "back_squat", "deadlift", "overhead_press")
_growth = st.fmean(
    (_capacity_at(e, 199) / _capacity_at(e, 100) - 1) / 2.0 for e in _lifts
)
_plateau = st.fmean(_capacity_at(e, 499) / _capacity_at(e, 450) - 1 for e in _lifts)
check(
    "J2 19.7",
    "estimated capacity stays flat through the S9 plateau",
    _plateau < _growth and abs(_plateau) < 0.02,
    f"{_plateau:+.2%} over the fifty plateau days against {_growth:+.2%} per "
    f"fifty days while the athlete was genuinely improving",
    n=len(_lifts),
)

# S3/S10 rebound attribution, against a matched control.
def _across(gap_start: int, gap_end: int, span: int = 8):
    before, after = {}, {}
    by_day = {r.day_index: r for r in RESULTS}
    for day in range(gap_start - span, gap_start):
        for exercise_id, record in getattr(by_day.get(day), "projections", {}).items():
            before[exercise_id] = record
    for day in range(gap_end, gap_end + span):
        for exercise_id, record in getattr(by_day.get(day), "projections", {}).items():
            after.setdefault(exercise_id, record)
    rows = []
    for exercise_id in before.keys() & after.keys():
        first, last = before[exercise_id], after[exercise_id]
        if first.projected <= 0 or last.projected <= 0:
            continue
        rows.append(
            (
                math.log(last.capacity) - math.log(first.capacity),
                math.log(1 - last.suppression) - math.log(1 - first.suppression),
            )
        )
    return rows


_deload = _across(92, 100) + _across(180, 195)
_control = [
    row
    for start in range(240, 460, 20)
    if not any(abs(start - b) < 40 for b in (92, 180, 515))
    for row in _across(start, start + 14)
]
_dc = st.fmean(r[0] for r in _deload)
_cc = st.fmean(r[0] for r in _control)
_df = st.fmean(r[1] for r in _deload)
_excess = _dc - _cc
_interval = 1.96 * math.sqrt(
    st.pvariance([r[0] for r in _deload]) / len(_deload)
    + st.pvariance([r[0] for r in _control]) / len(_control)
)
check(
    "J2 19.7",
    "a deload rebound is attributed to reduced fatigue, not to new capacity",
    _df > _dc,
    f"across a deload the engine moves capacity {_dc:+.4f} and the fatigue term "
    f"{_df:+.4f} — capacity is {_dc / max(_df, 1e-9):.1f}x the fatigue "
    f"contribution. Against matched ordinary gaps capacity moves {_cc:+.4f}, so "
    f"the deload adds {_excess:+.4f} +/- {_interval:.4f} of capacity movement "
    f"that an ordinary three weeks does not. §19.7 requires the reverse.",
    n=len(_deload),
)

# =============================================================================
# K. §19.8 — robustness, with every perturbation proved to have bitten
# =============================================================================

from rhome_eval.robustness import (  # noqa: E402
    PerturbationDidNothing,
    bad_hrv_night,
    bad_session,
    compare_steps_to_a_session,
    first_day_with,
    first_day_with_wearables,
    high_step_days,
    run_perturbed,
    systematic_overperformance,
    upper_lower_parity,
    withhold_wearables,
)

hrv_day = first_day_with_wearables(DAYS)
squat_day = first_day_with(DAYS, "back_squat")

# A perturbation that changes nothing reports perfect robustness. Prove each
# one landed BEFORE believing the number it produced.
perturbations = {
    "one bad HRV night": (bad_hrv_night(hrv_day), hrv_day),
    "one bad session": (bad_session(squat_day, "back_squat"), squat_day),
    "14 blind nights": (withhold_wearables(300), 300),
    "7 high-step days": (high_step_days(300), 300),
}
for label, (perturbation, target) in perturbations.items():
    window = [d for d in DAYS if d.day_index < DEV_DAYS]
    changed = sum(1 for d in window if perturbation(d) != d)
    check(
        "K 19.8",
        f"perturbation '{label}' actually changes the input",
        changed > 0,
        f"{changed} of {len(window)} days altered, target day {target}",
        n=changed,
    )

run_hrv = run_perturbed(DAYS, bad_hrv_night(hrv_day))
# Sampled at CONSECUTIVE horizons, not on a sparse grid: L3.7's table reports
# +0/+3/+14/+60 days and calls the effect "three and a half per cent", which is
# the value on the grid rather than the maximum.
profile = [(k, run_hrv.fatigue_shift(hrv_day + k)) for k in range(0, 15)]
peak_k, peak = max(profile, key=lambda kv: abs(kv[1]))
check(
    "K 19.8",
    "one bad HRV night does not dominate state, and is not a no-op",
    abs(peak) < 0.05 and abs(peak) > 1e-6,
    f"local fatigue peaks at {peak:+.3%} on +{peak_k} d (day {hrv_day}, HRV "
    f"cut 45%); profile +0..+5 d: "
    + " ".join(f"{v:+.2%}" for _, v in profile[:6])
    + f"; back under 1% by +{next(k for k, v in profile if k > peak_k and abs(v) < 0.01)} d",
    n=len(profile),
)

run_bad = run_perturbed(DAYS, bad_session(squat_day, "back_squat"))
settled_day = min(DEV_DAYS - 1, squat_day + 120)
displacement = run_bad.capacity_shift_at("back_squat", settled_day)
immediate = run_bad.capacity_shift_at("back_squat", squat_day)
check(
    "K 19.8",
    "one bad session does not permanently depress capacity (§19.7, S11)",
    abs(displacement) < 0.005 and 1e-6 < abs(immediate) <= 0.033,
    f"back_squat displaced {immediate:+.3%} on the day, {displacement:+.3%} "
    f"{settled_day - squat_day} days later",
)

run_sys = run_perturbed(DAYS, systematic_overperformance(squat_day, "back_squat"))
sustained = run_sys.capacity_shift_at("back_squat", DEV_DAYS - 1)
check(
    "K 19.8",
    "repeated systematic residuals CAN move capacity",
    sustained > 0.02,
    f"a sustained +10% load from day {squat_day} moves capacity {sustained:+.3%} "
    f"by day {DEV_DAYS - 1}; the Huber clip must bound one session, not a run",
)

run_blind = run_perturbed(DAYS, withhold_wearables(300))
conf_shift = st.fmean(run_blind.confidence_shift(300 + k) for k in range(14))
fatigue_shift = st.fmean(run_blind.fatigue_shift(300 + k) for k in range(14))
check(
    "K 19.8",
    "missing wearables reduce confidence rather than fabricating fatigue",
    conf_shift < -0.05,
    f"confidence {conf_shift:+.4f} over 14 blind nights; local fatigue "
    f"{fatigue_shift:+.2%} — NEGATIVE means fabricated freshness (LIM-3)",
    n=14,
)

steps = compare_steps_to_a_session(DAYS)
check(
    "K 19.8",
    "high steps affect load modestly, not as resistance volume",
    steps.systemic_ratio < 0.5 and steps.local_ratio < 0.5,
    f"one 25k-step day is {steps.systemic_ratio:.1%} of five hard squat sets "
    f"systemically and {steps.local_ratio:.1%} locally, from a clean state",
)

parity = upper_lower_parity(RESULTS)
check(
    "K 19.8",
    "upper/lower parity is STABLE (not that the ratio equals one)",
    parity.spread < 0.10 and abs(parity.drift) < 0.10,
    f"{parity.blocks} blocks of 28 d: median ratio {parity.median_ratio:.3f}, "
    f"sd {parity.spread:.4f}, first-half→second-half drift {parity.drift:+.4f}, "
    f"max deviation {parity.max_deviation:.4f}",
    n=parity.blocks,
)


# =============================================================================
# L. Cross-check — does rhome_eval agree with this file?
# =============================================================================

from rhome_eval.performance_metrics import score_performance  # noqa: E402
from rhome_eval.run import evaluate  # noqa: E402
from rhome_eval.state_metrics import score_states  # noqa: E402

HARNESS_RUN = evaluate(DAYS, Window.DEVELOPMENT, simulation=SIMULATION)
HARNESS_STATE = score_states(HARNESS_RUN, DAYS)
HARNESS_PERF = score_performance(HARNESS_RUN)

for score in HARNESS_STATE.channels:
    mine = channel_scores[score.channel]
    ok = (
        agrees(score.pearson, mine["pearson"], DISK_TOLERANCE)
        and agrees(score.spearman, mine["spearman"], DISK_TOLERANCE)
        and agrees(score.rmse, mine["rmse"], DISK_TOLERANCE)
        and agrees(score.directional_accuracy, mine["direction"], DISK_TOLERANCE)
        and agrees(score.baseline_pearson, mine["baseline"], DISK_TOLERANCE)
    )
    check(
        "L cross",
        f"§19.1 {score.channel}: harness agrees with independent re-derivation",
        ok,
        f"r {score.pearson:+.6f}/{mine['pearson']:+.6f}  "
        f"RMSE {score.rmse:.6f}/{mine['rmse']:.6f}  "
        f"dir {score.directional_accuracy:.6f}/{mine['direction']:.6f}  "
        f"counter {score.baseline_pearson:+.6f}/{mine['baseline']:+.6f}  "
        f"(tolerance {DISK_TOLERANCE:.0e}, set by the 6 dp on disk)",
        n=len(truth_paired(score.channel)),
    )

check(
    "L cross",
    "§19.1 per-muscle mean: harness agrees with independent re-derivation",
    agrees(HARNESS_STATE.muscle_mean, mean_engine, DISK_TOLERANCE)
    and agrees(HARNESS_STATE.muscle_baseline_mean, mean_counter, DISK_TOLERANCE),
    f"engine {HARNESS_STATE.muscle_mean:+.6f}/{mean_engine:+.6f}  "
    f"counter {HARNESS_STATE.muscle_baseline_mean:+.6f}/{mean_counter:+.6f}  "
    f"(tolerance {DISK_TOLERANCE:.0e})",
    n=len(scored),
)

check(
    "L cross",
    "§19.2 pooled residuals: harness agrees with independent re-derivation",
    agrees(HARNESS_PERF.mae, audit_mae, 1e-9)
    and agrees(HARNESS_PERF.rmse, audit_rmse, 1e-9)
    and agrees(HARNESS_PERF.bias, audit_bias, 1e-9)
    and HARNESS_PERF.n == len(residuals),
    f"n {HARNESS_PERF.n}/{len(residuals)}  MAE {HARNESS_PERF.mae:.6f}/{audit_mae:.6f}  "
    f"RMSE {HARNESS_PERF.rmse:.6f}/{audit_rmse:.6f}  "
    f"bias {HARNESS_PERF.bias:+.6f}/{audit_bias:+.6f}  (tolerance 1e-9)",
    n=HARNESS_PERF.n,
)

for label, minimum, rungs in (
    ("all sets", 0, HARNESS_PERF.ladder_all),
    ("settled", 20, HARNESS_PERF.ladder_settled),
):
    mine, mine_n = audit_ladder(minimum)
    disagreements = [
        r.name
        for r in rungs
        if r.name in mine and not agrees(r.mae, mine[r.name]["mae"], 1e-9)
    ]
    check(
        "L cross",
        f"§19.2 ablation ladder ({label}): harness agrees with re-derivation",
        not disagreements and rungs[0].n == mine_n,
        f"n {rungs[0].n}/{mine_n}; "
        + "  ".join(f"{r.name}:{r.mae:.6f}/{mine.get(r.name, {}).get('mae', float('nan')):.6f}" for r in rungs)
        + f"  (tolerance 1e-9){'  DISAGREE: ' + str(disagreements) if disagreements else ''}",
        n=mine_n,
    )

# §19.3's sixth ordering — post-deload vs pre-deload expected performance. It
# uses LatentSeries.expressible, which carries the same per-set shock.
import dataclasses as _dc  # noqa: E402

from rhome_eval.ranking import deload_response  # noqa: E402

DELOAD = deload_response(HARNESS_RUN)
# `expressible` is capacity AFTER fatigue, so only the shock comes out — not
# the fatigue factor. Dividing by both would compare the engine's expressible
# gain against a NEUTRAL capacity gain, which is L3.4's second measurement
# error repeated.
clean_expressible: dict[str, dict[int, float]] = defaultdict(dict)
for _row in LATENT_SETS:
    if float(_row["fatigue_factor"]) <= 0:
        continue
    clean_expressible[_row["exercise_id"]].setdefault(
        DATE_INDEX[WORKOUT_DATE[_row["workout_id"]]],
        float(_row["true_expressible_capacity"]) / float(_row["performance_shock"]),
    )
CLEAN_RUN = _dc.replace(
    HARNESS_RUN.truth, expressible={k: dict(v) for k, v in clean_expressible.items()}
)
_saved = HARNESS_RUN.truth
HARNESS_RUN.truth = CLEAN_RUN
DELOAD_CLEAN = deload_response(HARNESS_RUN)
HARNESS_RUN.truth = _saved

check(
    "L cross",
    "§19.3 sixth ordering: the deload rebound is measured against clean truth",
    abs(
        (DELOAD.engine_gain / DELOAD.truth_gain)
        - (DELOAD_CLEAN.engine_gain / DELOAD_CLEAN.truth_gain)
    )
    < 0.02,
    f"as built: engine {DELOAD.engine_gain:+.3%} vs truth {DELOAD.truth_gain:+.3%} "
    f"= {DELOAD.engine_gain / DELOAD.truth_gain:.3f} expressed, sign agreement "
    f"{DELOAD.engine_agreements}/{DELOAD.episodes}. With the per-set shock "
    f"divided out of the truth: engine {DELOAD_CLEAN.engine_gain:+.3%} vs truth "
    f"{DELOAD_CLEAN.truth_gain:+.3%} = "
    f"{DELOAD_CLEAN.engine_gain / DELOAD_CLEAN.truth_gain:.3f}, agreement "
    f"{DELOAD_CLEAN.engine_agreements}/{DELOAD_CLEAN.episodes}",
    n=DELOAD.episodes,
)

# The alignment is a fitted nuisance parameter; verify its digest and its value.
check(
    "L cross",
    "the scale alignment verifies its digest and matches an independent fit",
    HARNESS_RUN.alignment.verify()
    and all(
        agrees(HARNESS_RUN.alignment.scales[c], ALIGNMENT_SCALES[c], DISK_TOLERANCE)
        for c in CHANNELS
    ),
    "  ".join(
        f"{c}:{HARNESS_RUN.alignment.scales[c]:.6f}/{ALIGNMENT_SCALES[c]:.6f}"
        for c in CHANNELS
    )
    + f"  digest {HARNESS_RUN.alignment.digest[:12]}  n={HARNESS_RUN.alignment.n_points}",
    n=len(CHANNELS),
)
check(
    "L cross",
    "the alignment is one scale per channel with no offset",
    len(HARNESS_RUN.alignment.scales) == len(CHANNELS),
    f"{len(HARNESS_RUN.alignment.scales)} scales, fitted on "
    f"{HARNESS_RUN.alignment.fitted_on}; an intercept would absorb constant bias",
    n=len(CHANNELS),
)


# =============================================================================
# M. rhome_sim — the parts with no audit of their own
# =============================================================================

with (OBSERVABLE / "sets.csv").open(encoding="utf-8") as handle:
    OBSERVED_SETS = list(csv.DictReader(handle))

check(
    "M sim",
    "no latent column leaks into an observable table",
    not any(k.startswith("true_") for k in OBSERVED_SETS[0]),
    f"columns: {list(OBSERVED_SETS[0])}",
    n=len(OBSERVED_SETS[0]),
)
check(
    "M sim",
    "every observable set has a hidden counterpart, and no more",
    len(OBSERVED_SETS) == len(LATENT_SETS),
    f"{len(OBSERVED_SETS)} observable, {len(LATENT_SETS)} hidden",
    n=len(OBSERVED_SETS),
)
observable_keys = {(r["workout_id"], r["exercise_id"], r["set_number"]) for r in OBSERVED_SETS}
hidden_keys = {(r["workout_id"], r["exercise_id"], r["set_number"]) for r in LATENT_SETS}
check(
    "M sim",
    "observable and hidden set tables key one to one",
    observable_keys == hidden_keys,
    f"{len(observable_keys - hidden_keys)} observable-only, "
    f"{len(hidden_keys - observable_keys)} hidden-only",
    n=len(observable_keys),
)

# DATA.md §18: set timestamps must be explicit and spread across the session.
has_set_time = any("time" in k.lower() or "date" in k.lower() for k in OBSERVED_SETS[0])
durations = [float(r["duration_min"]) for r in WORKOUT_DATE and
             csv.DictReader((OBSERVABLE / "workouts.csv").open(encoding="utf-8"))]
sets_per_workout = defaultdict(int)
for row in OBSERVED_SETS:
    sets_per_workout[row["workout_id"]] += 1
median_sets = st.median(sets_per_workout.values())
engine_span_min = median_sets * 0.02 * 60.0
check(
    "M sim",
    "set timestamps are explicit and spread across the session (DATA.md §18)",
    has_set_time,
    f"sets.csv carries no time column. Logged session duration median "
    f"{st.median(durations):.0f} min; the engine spreads a median {median_sets:.0f}-set "
    f"session over {engine_span_min:.0f} min; the simulator applies every set at "
    f"one instant (0 min). Neither side meets the clause.",
    n=len(sets_per_workout),
)

# DATA.md §5.1 lists fields the written table does not carry.
with (OBSERVABLE / "daily_recovery.csv").open(encoding="utf-8") as handle:
    recovery_columns = set(next(csv.reader(handle)))
documented = {
    "date", "sleep_start", "sleep_end", "total_sleep_min", "sleep_efficiency",
    "rem_sleep_min", "deep_sleep_min", "hrv_rmssd_ms", "resting_hr_bpm",
    "temperature_deviation_c", "steps", "active_minutes", "bodyweight_kg",
    "oura_like_readiness", "oura_like_sleep_score", "wearable_missingness",
}
missing_columns = sorted(documented - recovery_columns)
check(
    "M sim",
    "daily_recovery.csv carries every field DATA.md §5.1 documents",
    not missing_columns,
    f"absent: {missing_columns or 'none'}",
    n=len(documented),
)

# Drop segments are a deliberate trap (§5.3) and must be excluded from capacity.
drop_rows = [r for r in OBSERVED_SETS if r["set_type"] == "drop"]
drop_share = len(drop_rows) / len(OBSERVED_SETS)
check(
    "M sim",
    "drop segments are present at an evaluable rate (§5.3: 1–3%)",
    0.01 <= drop_share <= 0.03,
    f"{len(drop_rows)} of {len(OBSERVED_SETS)} = {drop_share:.2%}",
    n=len(drop_rows),
)
drop_used = [
    (r.day_index, logged.set_number)
    for r in RESULTS
    for logged, dose in r.doses
    if logged.set_type == "drop" and dose.eligible_for_performance
]
check(
    "M sim",
    "the engine excludes every drop segment from performance estimation (§19.7)",
    not drop_used,
    f"{len(drop_used)} drop segments were eligible for performance",
    n=sum(1 for r in RESULTS for logged, _ in r.doses if logged.set_type == "drop"),
)
warmup_used = [
    1
    for r in RESULTS
    for logged, dose in r.doses
    if logged.set_type == "warmup" and (dose.local_fatigue or dose.eligible_for_performance)
]
check(
    "M sim",
    "warm-ups carry no dose and no performance observation",
    not warmup_used,
    f"{len(warmup_used)} warm-ups contributed something",
    n=sum(1 for d in DAYS[:DEV_DAYS] for s in d.sets if s.set_type == "warmup"),
)

# DATA.md §20: the dataset must be regenerable from its seed and its config.
# tests/test_dataset.py compares two FRESH regenerations to each other, both
# from current code, so it cannot see the committed artefact drifting away from
# the generator that is supposed to produce it.
import shutil  # noqa: E402
import tempfile  # noqa: E402

from rhome_sim.dataset import write_dataset  # noqa: E402

_regen_root = Path(tempfile.mkdtemp()) / "regen"
write_dataset(simulate(config["seed"], n_days=config["n_days"]), _regen_root)
_committed = json.loads((DATASET / "metadata" / "checksums.json").read_text())
_fresh = json.loads((_regen_root / "metadata" / "checksums.json").read_text())
# The commit hash legitimately differs between runs.
_differing = [
    k
    for k in _committed
    if k != "metadata/generation_config.json" and _committed[k] != _fresh.get(k)
]
shutil.rmtree(_regen_root.parent, ignore_errors=True)
check(
    "M sim",
    "the committed dataset regenerates byte-for-byte from its seed (§20)",
    not _differing,
    f"{len(_differing)} of {len(_committed)} files differ: {_differing or 'none'}. "
    f"Every observable and hidden table reproduces; what does not is a metadata "
    f"fixture, so no Layer 3 number is affected — but the artefact is no longer "
    f"the output of the generator that is supposed to produce it.",
    n=len(_committed),
)

# The dirty-row fixture states the parser's contract. Check the committed
# rendering against the live parser, not against the live fixture the tests
# already use.
from rhome_sim.missingness import raw_dirty_rows  # noqa: E402

from rhome_engine.ingest import parse_sets  # noqa: E402

with (DATASET / "metadata" / "raw_dirty.csv").open(encoding="utf-8") as handle:
    _committed_dirty = list(csv.DictReader(handle))
# Parsed as one batch, the way the fixture is meant to be used: the duplicate
# set-number case only exists relative to another row.
_expectations = [(r["defect"], r["expected"]) for r in _committed_dirty]
_parsed = parse_sets(
    [{k: v for k, v in r.items() if k not in ("defect", "expected")} for r in _committed_dirty],
    LIBRARY,
)
_outcome: dict[int, str] = {}
for _issue in _parsed.rejected:
    _outcome[_issue.row_number] = "reject"
for _issue in _parsed.repaired:
    _outcome.setdefault(_issue.row_number, "repair")
_mismatched = [
    (defect, expected, _outcome.get(number, "accepted"))
    for number, (defect, expected) in enumerate(_expectations, start=2)
    if _outcome.get(number, "accepted") != expected
]
_live_defects = {r.defect for r in raw_dirty_rows()}
_lost = sorted({d for d, _ in _expectations} - _live_defects)
check(
    "M sim",
    "the committed dirty-row fixture states the parser's actual contract (§17)",
    not _mismatched,
    f"{len(_mismatched)} of {len(_committed_dirty)} committed rows behave "
    f"differently from what they claim: "
    + "; ".join(f"{d[:44]!r} says {e}, parser says {a}" for d, e, a in _mismatched)
    + f". The live fixture in rhome_sim.missingness agrees with the parser on "
    f"all {len(_live_defects)} of its rows; the CSV on disk is its pre-L2.1 "
    f"rendering. Defect cases the parser no longer catches at all: {_lost}.",
    n=len(_committed_dirty),
)

# Determinism, end to end, on the artefact that matters (Guardrail 4).
second = RhomeEngine(LIBRARY)
second_results = second.run(DAYS[:DEV_DAYS])
identical = all(
    abs(sum(a.state.local_fatigue.values()) - sum(b.state.local_fatigue.values())) < 1e-15
    and abs(a.state.systemic - b.state.systemic) < 1e-15
    for a, b in zip(RESULTS, second_results)
)
check(
    "M sim",
    "the ENGINE is deterministic over the development window",
    identical,
    "two independent runs over the same input produce identical states",
    n=len(RESULTS),
)


# =============================================================================
# N. Guardrails, by attempting the violation
# =============================================================================

from rhome_core.architecture import (  # noqa: E402
    _HIDDEN_MARKERS,
    _SEALED_MARKERS,
    PACKAGES,
    check_import_boundaries,
)


def plant(tmp: Path, package: str, body: str) -> list:
    root = tmp / "src"
    for name in PACKAGES:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "__init__.py").write_text("", encoding="utf-8")
    (root / package / "offender.py").write_text(body, encoding="utf-8")
    return check_import_boundaries(root)


import tempfile  # noqa: E402

EVASIONS = {
    "dynamic import (importlib)": ('import importlib\ns = importlib.import_module("rhome_sim.physiology")\n'),
    "dynamic import (__import__)": ('s = __import__("rhome_sim.generate", fromlist=["simulate"])\n'),
    "hidden dir via pathlib join": ('from pathlib import Path\nP = Path("data/synthetic/athlete_a") / "hidden"\n'),
    "sealed export via pathlib join": ('from pathlib import Path\nP = Path("data") / "real" / "oura.csv"\n'),
    "the unsealed original export": ('P = "spotr_data/database/spotr_training_archive.sqlite"\n'),
}
missed = []
with tempfile.TemporaryDirectory() as tmp:
    for label, body in EVASIONS.items():
        if not plant(Path(tmp) / label.replace(" ", "_").replace("(", "").replace(")", ""),
                     "rhome_engine", body):
            missed.append(label)
    caught_control = bool(
        plant(Path(tmp) / "control", "rhome_engine", "import rhome_sim\n")
    )
check(
    "N G1",
    "the import/path boundary resists evasion, not just the obvious spelling",
    not missed,
    f"control caught: {caught_control}. NOT CAUGHT: {missed}. "
    f"Markers are {_HIDDEN_MARKERS} and {_SEALED_MARKERS} — each requires a "
    f"slash this codebase's pathlib style does not produce.",
    n=len(EVASIONS),
)

from rhome_core.conformance import CLAUSES, coverage_report  # noqa: E402

marked: dict[str, list[str]] = defaultdict(list)
for path in sorted((ROOT / "tests").glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "spec"
        ):
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    marked[argument.value].append(str(path.name))
report = coverage_report(dict(marked))
check(
    "N G5",
    "conformance coverage is 100% (DATA.md/BUILD_PLAN Guardrail 5)",
    not report.uncovered,
    f"{len(report.covered)}/{len(CLAUSES)} clauses covered; "
    f"uncovered: {report.uncovered or 'none'}",
    n=len(CLAUSES),
)
enforcing = [
    p.name
    for p in (ROOT / "tests").glob("*.py")
    if p.name != "conftest.py" and "coverage_report" in p.read_text(encoding="utf-8")
]
check(
    "N G5",
    "a TEST fails when a clause loses its coverage",
    bool(enforcing),
    "no test in tests/ references coverage_report or CLAUSES; conftest WRITES "
    "build_log/conformance.md but nothing ASSERTS on it, so coverage can fall "
    "to any value with the suite still green"
    if not enforcing
    else f"enforced by {enforcing}",
)

registry_names = {
    p.name for p in __import__("rhome_core.parameters", fromlist=["CORE_PARAMETERS"]).CORE_PARAMETERS
} | {p.name for p in ENGINE_PARAMETERS}
self_certified = []
for name in registry_names:
    sites = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        registering = path.name == "parameters.py"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args:
                if registering and isinstance(node.func, ast.Attribute) and node.func.attr == "register":
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value == name:
                    sites.append("lookup")
            elif isinstance(node, ast.JoinedStr):
                prefix = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
                if prefix and name.startswith(prefix):
                    sites.append("f-string in parameters.py" if registering else "f-string")
    if sites and all(s != "lookup" for s in sites):
        self_certified.append(name)
check(
    "N G3",
    "every registered parameter is proved read by a genuine registry lookup",
    not self_certified,
    f"{len(self_certified)} of {len(registry_names)} are certified only by an "
    f"f-string inside their own register() call: "
    f"{sorted(self_certified)[:6]}{'...' if len(self_certified) > 6 else ''}. "
    f"The guardrail reports {len(registry_names)}/{len(registry_names)}.",
    n=len(registry_names),
)

from rhome_eval.window import HoldoutSeal, SealError  # noqa: E402
from rhome_eval.run import run_engine  # noqa: E402

try:
    run_engine(DAYS, Window.HOLDOUT)
    guarded = False
except SealError:
    guarded = True
try:
    bypass = run_engine(DAYS, Window.HOLDOUT, seal=HoldoutSeal())
    bypassed = bypass.caveat
except SealError:
    bypassed = None
check(
    "N seal",
    "the holdout cannot be run without recording the opening",
    guarded and bypassed is None,
    f"seal=None is refused: {guarded}. But seal=HoldoutSeal() runs all "
    f"{len(HOLDOUT_DAYS)} holdout days and the run's caveat reads {bypassed!r} — "
    f"the guard tests `seal is None`, not that the seal came from open_holdout()"
    if bypassed is not None
    else "both paths refused",
)


# =============================================================================
# output
# =============================================================================

passed = sum(1 for *_, ok, _ in results if ok)
print(f"\n{'':5}{'SECTION':11}{'REQUIREMENT':66}{'MEASURED'}")
print("-" * 150)
current = None
for section, requirement, ok, detail in results:
    if section != current:
        print()
        current = section
    print(f"{'PASS' if ok else 'FAIL':5}{section:11}{requirement:66}{detail}")
print("-" * 150)
print(f"{passed}/{len(results)} checks passed")

failures = [(s, r, d) for s, r, ok, d in results if not ok]
if failures:
    print("\nFAILURES:")
    for section, requirement, detail in failures:
        print(f"  [{section}] {requirement}\n      {detail}")
sys.exit(1 if failures else 0)
