"""Generate the Checkpoint 2 visual pack and CSVs from the engine's own output.

Reads only the observable dataset. Nothing here opens the simulator's hidden
files: the point of this gate is to show what the engine produces from what an
athlete would actually give it. Comparison against latent truth is Layer 3's
job and is deliberately not previewed here.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rhome_core.exercises import load_library  # noqa: E402
from rhome_core.muscles import Muscle  # noqa: E402
from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: E402
from rhome_engine.session import RhomeEngine  # noqa: E402
from rhome_engine.trace import display_value  # noqa: E402
from test_session_driver import _days  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "build_log/checkpoint2")
OUT.mkdir(parents=True, exist_ok=True)

INK, ACCENT, VERIFY, GATE, RULE = "#15191B", "#8C2F39", "#2C6E6A", "#8F6314", "#C9D0C9"
MUTED = "#5F6A67"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": RULE, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "600",
    "figure.dpi": 130,
})

DEV_DAYS = 520
LIBRARY = load_library()
engine = RhomeEngine(LIBRARY)
RESULTS = engine.run(_days()[:DEV_DAYS])
days = np.array([r.day_index for r in RESULTS])
trained = np.array([r.trained for r in RESULTS])


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


# === 1. estimated state over time ==========================================
# Two resolutions deliberately. At 520 days the daily rise-and-fall is the only
# thing visible and it drowns everything else, so the detail panel shows one
# training block at full resolution and the summary panel shows the whole
# window as weekly means.
fig, axes = plt.subplots(3, 1, figsize=(11, 8.6))

DETAIL = slice(200, 290)
detail = RESULTS[DETAIL]
detail_days = [r.day_index for r in detail]
shown = [Muscle.QUADS, Muscle.CHEST, Muscle.LATS, Muscle.HAMSTRINGS]
colours = [ACCENT, VERIFY, GATE, MUTED]
for muscle, colour in zip(shown, colours):
    axes[0].plot(detail_days, [display_value(r.state.local_fatigue[muscle]) for r in detail],
                 lw=1.2, color=colour, label=muscle.value.replace("_", " "))
for r in detail:
    if r.trained:
        axes[0].axvline(r.day_index, color=RULE, lw=2.4, alpha=0.35, zorder=0)
axes[0].set_xlim(detail_days[0], detail_days[-1])
axes[0].set_ylabel("fatigue index (0–100)")
axes[0].set_xlabel("day")
axes[0].set_title("Ninety days at full resolution · grey bars are training days")
axes[0].legend(frameon=False, ncol=4, loc="upper right", fontsize=8)


def weekly(values):
    trimmed = np.array(values[: len(values) // 7 * 7]).reshape(-1, 7)
    return trimmed.mean(axis=1)


weeks = np.arange(DEV_DAYS // 7) * 7
axes[1].plot(weeks, weekly([sum(r.state.local_fatigue.values()) for r in RESULTS]),
             lw=1.3, color=ACCENT, label="total local fatigue")
axes[1].plot(weeks, weekly([r.state.neuromuscular * 8 for r in RESULTS]),
             lw=1.1, color=VERIFY, label="neuromuscular strain (×8)")
axes[1].plot(weeks, weekly([r.state.systemic * 8 for r in RESULTS]),
             lw=1.1, color=GATE, label="systemic load (×8)")
axes[1].axvspan(DETAIL.start, DETAIL.stop, color=RULE, alpha=0.3, zorder=0)
axes[1].set_xlim(0, DEV_DAYS)
axes[1].set_ylabel("latent units")
axes[1].set_xlabel("day")
axes[1].set_title("The whole window as weekly means · shaded span is the panel above")
axes[1].legend(frameon=False, ncol=3, loc="upper right", fontsize=8)

floor_rho = ENGINE_PARAMETERS.value("rho_floor")
ceiling_rho = ENGINE_PARAMETERS.value("rho_ceiling")
rhos = [r.recovery.rho for r in RESULTS]
axes[2].plot(days, rhos, lw=0.8, color=INK)
axes[2].axhline(1.0, color=RULE, lw=0.8)
axes[2].axhline(floor_rho, color=ACCENT, lw=0.8, ls="--")
axes[2].axhline(ceiling_rho, color=ACCENT, lw=0.8, ls="--")
clipped = [d for d, v in zip(days, rhos)
           if abs(v - floor_rho) < 1e-9 or abs(v - ceiling_rho) < 1e-9]
axes[2].scatter(clipped, [rhos[d] for d in clipped], s=8, color=ACCENT, zorder=3)
for r in RESULTS:
    if r.recovery.channels_present == 0:
        axes[2].axvline(r.day_index, color=GATE, lw=1.6, alpha=0.5)
axes[2].set_xlim(0, DEV_DAYS)
axes[2].set_ylabel("ρ")
axes[2].set_xlabel("day")
axes[2].set_title(f"Recovery context · {len(clipped)} days ({len(clipped)/DEV_DAYS:.0%}) "
                  f"sit on a clip bound · gold rules are nights with no wearable data")

fig.suptitle("Estimated state across 520 days", x=0.005, ha="left",
             fontsize=13, fontweight="600")
save(fig, "01_state_over_time.png")

# === 2. confidence =========================================================
fig, axes = plt.subplots(2, 1, figsize=(11, 5.8), sharex=True,
                         gridspec_kw={"height_ratios": [2.2, 1]})

values = [r.confidence.fatigue.value for r in RESULTS]
axes[0].axhspan(0.75, 1.02, color=VERIFY, alpha=0.07)
axes[0].axhspan(0.50, 0.75, color=GATE, alpha=0.08)
axes[0].axhspan(0.0, 0.50, color=ACCENT, alpha=0.08)
axes[0].plot(days, values, lw=1.0, color=INK)
axes[0].set_ylim(0.35, 1.02)
axes[0].set_ylabel("confidence in fatigue")
axes[0].set_title("Confidence, with the three display bands shaded")
for y, label in ((0.88, "high"), (0.62, "moderate"), (0.43, "limited")):
    axes[0].text(DEV_DAYS * 0.995, y, label, ha="right", va="center",
                 fontsize=8, color=MUTED)

reasons = ["baseline maturity", "dose quality", "wearable completeness",
           "unexplained autonomic deviation"]
reason_colour = dict(zip(reasons, [GATE, VERIFY, ACCENT, MUTED]))
for reason in reasons:
    mask = [r.day_index for r in RESULTS
            if r.confidence.fatigue.binding_reason.name == reason]
    axes[1].scatter(mask, [reasons.index(reason)] * len(mask), s=3,
                    color=reason_colour[reason])
axes[1].set_yticks(range(len(reasons)))
axes[1].set_yticklabels([r.replace("unexplained autonomic deviation",
                                   "autonomic surprise") for r in reasons], fontsize=8)
axes[1].set_xlabel("day of the development window")
axes[1].set_title("What is holding confidence down, each day")

fig.suptitle("How much the engine claims to know", x=0.005, ha="left",
             fontsize=13, fontweight="600")
save(fig, "02_confidence.png")

# === 3. one day, explained =================================================
# A local-fatigue state, chosen because it is the case where attribution is
# informative. Systemic load draws a few per cent from each of hundreds of
# sets — true, and a poor illustration of what a decomposition is for.
candidates = [
    (r, t) for r in RESULTS if r.trained
    for t in r.traces.values()
    if t.state_id.startswith("F.") and t.contributors and t.value > 0.4
]
subject, record = max(candidates, key=lambda pair: pair[1].contributors[0].share)
named = [c for c in record.contributors if not c.is_residual][:8]

fig = plt.figure(figsize=(11, 6.6))
grid = fig.add_gridspec(2, 2, height_ratios=[1.45, 1], width_ratios=[1.7, 1],
                        hspace=0.62, wspace=0.28)

ax = fig.add_subplot(grid[0, :])
positions = np.arange(len(named))
ax.barh(positions, [c.share for c in named], color=ACCENT, alpha=0.85, height=0.62)
ax.set_yticks(positions)
ax.set_yticklabels([f"{c.label}  ({c.age_h:.0f} h ago)" for c in named], fontsize=8)
ax.invert_yaxis()
ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
ax.set_xlabel("share of the current state")
muscle_name = record.state_id.split(".")[1].replace("_", " ")
ax.set_title(f"{muscle_name} fatigue on day {subject.day_index} — "
             f"index {record.display_value:.0f}/100, "
             f"{len(record.contributors)} contributors, shares summing to "
             f"{record.share_total():.6f}")
residual = sum(c.share for c in record.contributors if c.is_residual)
ax.text(0.99, 0.04, f"older training, folded into one entry: {residual:.1%}",
        transform=ax.transAxes, ha="right", fontsize=8, color=MUTED)

# The projection panel shows the path and the *authority* attached to it. It
# deliberately draws no uncertainty band: v0 produces a confidence index, not a
# quantified interval, and shading one would imply a number the model does not
# compute. MODEL.tex puts the widening-uncertainty requirement on the
# interface, and this is the data the interface has to work with.
ax = fig.add_subplot(grid[1, 0])
horizons = (0.0, 12.0, 24.0, 48.0, 72.0, 120.0, 168.0, 240.0, 336.0)
forecast = engine.project(horizons)
muscle = Muscle(record.state_id.split(".")[1])
path = [display_value(p.local_fatigue[muscle]) for p in forecast.points]
band_colour = {"high": VERIFY, "moderate": GATE, "limited": ACCENT}
for left, right, point in zip(horizons, horizons[1:], forecast.points[1:]):
    ax.axvspan(left, right, color=band_colour[point.confidence.band.value],
               alpha=0.13, lw=0, zorder=0)
ax.plot(horizons, path, lw=1.6, color=INK, zorder=3)
ax.scatter(horizons, path, s=14, color=INK, zorder=4)
for point, value in zip(forecast.points, path):
    if point.horizon_h in (72.0, 168.0, 336.0):
        ax.annotate(f"C {point.confidence.value:.2f}", (point.horizon_h, value),
                    textcoords="offset points", xytext=(0, 9), ha="center",
                    fontsize=7.5, color=MUTED)
ax.set_xlabel("hours ahead")
ax.set_ylabel("fatigue index")
ax.set_title(f"Projection from the end of the window, {muscle_name}\n"
             f"shading is the confidence band, not an uncertainty interval",
             fontsize=9.5)

ax = fig.add_subplot(grid[1, 1])
grades = record.grades()
ax.bar(list(grades), list(grades.values()),
       color=[VERIFY, GATE, ACCENT], alpha=0.85, width=0.55)
ax.set_title("Evidence grades behind this number", fontsize=9.5)
ax.set_ylabel("parameters")
for key, value in grades.items():
    ax.text(list(grades).index(key), value + 0.4, str(value), ha="center", fontsize=8)

fig.suptitle("One displayed number, taken apart", x=0.005, ha="left",
             fontsize=13, fontweight="600")
fig.text(0.005, -0.03, f"driver: {record.driver}", fontsize=8.5, color=MUTED,
         style="italic")
save(fig, "03_one_day_explained.png")

# === 4. performance ========================================================
fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.1),
                         gridspec_kw={"width_ratios": [1.35, 1, 1.15]})

main = ["back_squat", "deadlift", "bench_press", "overhead_press"]
history: dict[str, list[tuple[int, float]]] = {e: [] for e in main}
for r in RESULTS:
    for o in r.observations:
        if o.exercise_id in history:
            history[o.exercise_id].append((r.day_index, o.capacity_after))
for exercise_id, colour in zip(main, [ACCENT, VERIFY, GATE, MUTED]):
    series = history[exercise_id]
    axes[0].plot([d for d, _ in series], [v for _, v in series], lw=1.1,
                 color=colour, label=exercise_id.replace("_", " "))
axes[0].set_xlabel("day")
axes[0].set_ylabel("estimated capacity (kg)")
axes[0].set_title("Estimated capacity, four main lifts")
axes[0].legend(frameon=False, fontsize=8)

residuals = [o.log_residual for r in RESULTS for o in r.observations]
axes[1].hist(residuals, bins=45, color=VERIFY, alpha=0.75)
axes[1].axvline(0.0, color=INK, lw=1.0)
axes[1].axvline(float(np.mean(residuals)), color=ACCENT, lw=1.2, ls="--")
axes[1].set_xlabel("log residual (observed − projected)")
axes[1].set_ylabel("sets")
axes[1].set_title(f"One-step-ahead residuals\nn={len(residuals)}, "
                  f"mean {np.mean(residuals):+.4f}, sd {np.std(residuals):.4f}",
                  fontsize=9.5)

# The pooled mean above conceals a drift, which is the reason this panel
# exists: a single unbiased-looking number can be two opposite biases meeting
# in the middle.
blocks, means, counts = [], [], []
for lower in range(0, DEV_DAYS, 100):
    block = [o.log_residual for r in RESULTS[lower:lower + 100] for o in r.observations]
    if block:
        blocks.append(lower + 50)
        means.append(float(np.mean(block)))
        counts.append(len(block))
axes[2].axhline(0.0, color=INK, lw=0.9)
axes[2].plot(blocks, means, lw=1.4, color=ACCENT, marker="o", ms=4)
axes[2].fill_between(blocks, 0, means, color=ACCENT, alpha=0.12)
axes[2].set_xlabel("day (100-day blocks)")
axes[2].set_ylabel("mean log residual")
axes[2].set_title("Residual bias is not stationary\nabove zero = engine under-predicting",
                  fontsize=9.5)

fig.suptitle("Performance, predicted before each session and scored after",
             x=0.005, ha="left", fontsize=13, fontweight="600")
save(fig, "04_performance.png")

# === CSVs ==================================================================
with (OUT / "daily_state.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(
        ["day", "trained", "sets", "rho", "wearable_channels",
         *[f"fatigue_{m.value}" for m in Muscle],
         "neuromuscular", "systemic", "confidence", "confidence_band",
         "binding_reason"]
    )
    for r in RESULTS:
        writer.writerow([
            r.day_index, int(r.trained), len(r.doses), f"{r.recovery.rho:.4f}",
            r.recovery.channels_present,
            *[f"{r.state.local_fatigue[m]:.6f}" for m in Muscle],
            f"{r.state.neuromuscular:.6f}", f"{r.state.systemic:.6f}",
            f"{r.confidence.fatigue.value:.4f}", r.confidence.fatigue.band.value,
            r.confidence.fatigue.binding_reason.name,
        ])

with (OUT / "performance_observations.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["day", "exercise_id", "session_key", "projected", "observed",
                     "log_residual", "capacity_before", "capacity_after",
                     "learning_rate", "is_anchor"])
    for r in RESULTS:
        for o in r.observations:
            writer.writerow([
                r.day_index, o.exercise_id, o.session_key, f"{o.projected:.3f}",
                f"{o.observed:.3f}", f"{o.log_residual:+.6f}",
                f"{o.capacity_before:.3f}", f"{o.capacity_after:.3f}",
                f"{o.learning_rate:.3f}", int(o.is_anchor),
            ])

with (OUT / "trace_example.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["state_id", "value", "display_value", "confidence", "band",
                     "driver", "source", "label", "impulse_at_origin",
                     "surviving", "share", "age_h"])
    for state_id in sorted(subject.traces):
        t = subject.traces[state_id]
        for c in t.contributors:
            writer.writerow([
                t.state_id, f"{t.value:.6f}", f"{t.display_value:.2f}",
                f"{t.confidence.value:.4f}", t.confidence.band.value, t.driver,
                c.source, c.label, f"{c.impulse:.6f}", f"{c.surviving:.6f}",
                f"{c.share:.6f}", f"{c.age_h:.2f}",
            ])

with (OUT / "projection.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["horizon_h", *[f"fatigue_{m.value}" for m in Muscle],
                     "neuromuscular", "systemic", "confidence", "band"])
    for p in forecast.points:
        writer.writerow([
            f"{p.horizon_h:.0f}",
            *[f"{p.local_fatigue[m]:.6f}" for m in Muscle],
            f"{p.neuromuscular:.6f}", f"{p.systemic:.6f}",
            f"{p.confidence.value:.4f}", p.confidence.band.value,
        ])

print(f"\n{DEV_DAYS} days · {sum(trained)} sessions · "
      f"{sum(len(r.doses) for r in RESULTS)} sets · "
      f"{sum(len(r.observations) for r in RESULTS)} scored · "
      f"{sum(len(r.traces) for r in RESULTS)} traces")
print("bands:", dict(Counter(r.confidence.fatigue.band.value for r in RESULTS)))
print("CSVs: daily_state, performance_observations, trace_example, projection")
