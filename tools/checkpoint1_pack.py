"""Generate the Checkpoint 1 visual pack from the written dataset.

Reads the CSVs rather than the in-memory simulation, so the pack shows what the
engine will actually receive.
"""
from __future__ import annotations

import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path("data/synthetic/athlete_a")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "build_log/checkpoint1")
OUT.mkdir(parents=True, exist_ok=True)

INK, ACCENT, VERIFY, GATE, RULE = "#15191B", "#8C2F39", "#2C6E6A", "#8F6314", "#C9D0C9"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": RULE, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": "#5F6A67", "ytick.color": "#5F6A67",
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "600",
    "figure.dpi": 130,
})

def rows(rel):
    with (ROOT / rel).open(encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h))

def f(v, default=np.nan):
    return float(v) if v not in (None, "", "None") else default

daily = rows("observable/daily_recovery.csv")
sets = rows("observable/sets.csv")
workouts = rows("observable/workouts.csv")
latent = rows("hidden/latent_daily.csv")
manifest = rows("hidden/scenario_manifest.csv")
report = json.loads((ROOT / "metadata" / "quality_report.json").read_text())

wk_day = {w["workout_id"]: i for i, w in enumerate(workouts)}
day_of = {w["workout_id"]: int(w["date"][-2:]) for w in workouts}
date_index = {d["date"]: i for i, d in enumerate(daily)}
set_day = [date_index[w["date"]] for w in workouts]
wk_to_day = {w["workout_id"]: date_index[w["date"]] for w in workouts}

# ---------------------------------------------------------------- figure 1
fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True)
days = np.arange(len(daily))

vol = np.zeros(len(daily))
for s in sets:
    if s["set_type"] in ("working", "backoff"):
        vol[wk_to_day[s["workout_id"]]] += 1
axes[0].bar(days, vol, width=1.0, color=ACCENT, linewidth=0)
axes[0].set_ylabel("working sets")
axes[0].set_title("Training volume per day")

hrv = np.array([f(d["hrv_rmssd_ms"]) for d in daily])
axes[1].plot(days, hrv, lw=0.7, color=VERIFY)
axes[1].set_ylabel("RMSSD (ms)"); axes[1].set_title("Nocturnal HRV")

slp = np.array([f(d["total_sleep_min"]) / 60 for d in daily])
axes[2].plot(days, slp, lw=0.7, color="#3C4644")
axes[2].axhline(7.5, color=RULE, lw=1, ls="--")
axes[2].set_ylabel("hours"); axes[2].set_title("Total sleep (dashed = 7.5 h target)")

fat = np.array([np.mean([f(r[c]) for c in r if c.startswith("true_fatigue_")]) for r in latent])
axes[3].plot(days, fat, lw=0.8, color=ACCENT)
axes[3].set_ylabel("mean fatigue"); axes[3].set_xlabel("day")
axes[3].set_title("True local fatigue — hidden from the engine")

palette = {"S1_high_volume": ACCENT, "S2_failure_heavy": "#B0443F", "S3_deload": VERIFY,
           "S4_sleep_restriction": GATE, "S5_sleep_compression": GATE,
           "S6_travel": "#6B7472", "S7_illness": "#7A2E33", "S9_plateau": "#8E9996",
           "S10_pr_window": "#3E8E4C", "S12_missed_block": "#5F6A67"}
for m in manifest:
    c = palette.get(m["scenario"])
    if c:
        for ax in axes:
            ax.axvspan(int(m["first_day"]), int(m["last_day"]), color=c, alpha=0.13, lw=0)
for ax in axes:
    ax.axvline(520, color=INK, lw=1.1, ls=":")
axes[0].text(521, axes[0].get_ylim()[1]*0.9, " holdout →", fontsize=8, color=INK)
fig.suptitle("Two years of Athlete A  ·  shaded bands are scenarios  ·  dotted line is the holdout boundary",
             y=0.995, fontsize=10.5, weight="600")
fig.tight_layout(); fig.savefig(OUT / "01_timeline.png", bbox_inches="tight"); plt.close(fig)

# ---------------------------------------------------------------- figure 2
fig, axes = plt.subplots(2, 3, figsize=(11, 5.6))
ax = axes[0][0]
reps = [int(s["reps"]) for s in sets if s["set_type"] in ("working", "backoff")]
ax.hist(reps, bins=range(1, 27), color=ACCENT, linewidth=0)
ax.set_title("Repetitions per working set"); ax.set_xlabel("reps")

ax = axes[0][1]
rir = [f(s["rir"]) for s in sets if s["set_type"] in ("working","backoff") and s["rir"]]
ax.hist(rir, bins=np.arange(-0.5, 8.5), color=VERIFY, linewidth=0)
ax.set_title("Logged reps in reserve"); ax.set_xlabel("RIR (0 = to failure)")

ax = axes[0][2]
bw = [f(d["bodyweight_kg"]) for d in daily]
tm = [f(r["true_body_mass_kg"]) for r in latent]
ax.plot(days, bw, lw=0.5, color="#9AA5A2", label="scale reading")
ax.plot(days, tm, lw=1.6, color=ACCENT, label="true tissue mass")
ax.legend(fontsize=7, frameon=False); ax.set_title("Body mass"); ax.set_xlabel("day")

ax = axes[1][0]
for eid, colour in (("bench_press", ACCENT), ("back_squat", VERIFY), ("deadlift", "#3C4644")):
    pts = [(wk_to_day[s["workout_id"]], f(s["external_load_kg"]))
           for s in sets if s["exercise_id"] == eid and s["set_type"] == "working"]
    if pts:
        x, y = zip(*pts)
        ax.plot(x, y, ".", ms=1.2, color=colour, label=eid.replace("_", " "))
ax.legend(fontsize=7, frameon=False); ax.set_title("Working loads"); ax.set_xlabel("day")
ax.set_ylabel("kg")

ax = axes[1][1]
sess = Counter(len([s for s in sets if s["workout_id"] == w["workout_id"]]) for w in workouts)
weekly = Counter()
for w in workouts:
    weekly[date_index[w["date"]] // 7] += 1
ax.hist(list(weekly.values()), bins=np.arange(-0.5, 8.5), color="#3C4644", linewidth=0)
ax.set_title("Sessions per week"); ax.set_xlabel("sessions")

ax = axes[1][2]
counts = Counter(s["set_type"] for s in sets)
order = ["working", "warmup", "backoff", "drop"]
ax.bar(order, [counts[o] for o in order], color=[ACCENT, "#9AA5A2", VERIFY, GATE], linewidth=0)
ax.set_title("Set types"); ax.tick_params(axis="x", rotation=20)

fig.tight_layout(); fig.savefig(OUT / "02_distributions.png", bbox_inches="tight"); plt.close(fig)

# ---------------------------------------------------------------- figure 3
fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
def window(scn):
    for m in manifest:
        if m["scenario"] == scn:
            return int(m["first_day"]), int(m["last_day"])
    return None

for ax, (scn, title) in zip(axes, (("S3_deload", "Deload: fatigue falls, adaptation holds"),
                                   ("S7_illness", "Illness: signals move together"),
                                   ("S12_missed_block", "Missed week: quiet, not sick"))):
    a, b = window(scn)
    lo, hi = max(0, a - 18), min(len(daily) - 1, b + 18)
    x = np.arange(lo, hi + 1)
    adapt = np.array([np.mean([f(r[c]) for c in r if c.startswith("true_adaptation_")]) for r in latent])
    ax.plot(x, fat[lo:hi+1] / max(fat.max(), 1e-9), lw=1.4, color=ACCENT, label="fatigue")
    ax.plot(x, adapt[lo:hi+1] / max(adapt.max(), 1e-9), lw=1.4, color=VERIFY, label="adaptation")
    tmp = np.array([f(d["temperature_deviation_c"]) for d in daily])
    ax.plot(x, tmp[lo:hi+1], lw=1.0, color=GATE, label="temp dev (°C)")
    ax.axvspan(a, b, color=INK, alpha=0.08, lw=0)
    ax.set_title(title, fontsize=9.5); ax.set_xlabel("day")
    ax.legend(fontsize=6.5, frameon=False)
fig.tight_layout(); fig.savefig(OUT / "03_scenarios.png", bbox_inches="tight"); plt.close(fig)

print(f"wrote {OUT}/01_timeline.png, 02_distributions.png, 03_scenarios.png")
print(json.dumps({k: report[k] for k in ("days","sessions","sets_dose_bearing","sets_by_type",
                                          "performance_test_sets","personal_records")}, indent=2))
