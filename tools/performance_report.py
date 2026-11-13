"""Render the performance and capacity report (``DATA.md`` §19.2, L3.3)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rhome_eval.performance_metrics import score_performance  # noqa: E402
from rhome_eval.run import evaluate  # noqa: E402
from rhome_eval.window import Window  # noqa: E402
from test_session_driver import _days  # noqa: E402

report = score_performance(evaluate(_days(), Window.DEVELOPMENT))

print(f"\nPERFORMANCE AND CAPACITY — {report.caveat}\n")
print(f"one-step-ahead: n={report.n}  MAE {report.mae:.4f}  RMSE {report.rmse:.4f}  "
      f"bias {report.bias:+.4f}  autocorrelation {report.autocorrelation:+.3f}")

print("\nABLATION LADDER — all sets")
for rung in report.ladder_all:
    tail = "" if rung.versus_engine is None else f"  Δ {rung.versus_engine:+.5f}±{rung.interval:.5f}"
    print(f"  {rung.name:22s} n={rung.n:4d} MAE {rung.mae:.4f} RMSE {rung.rmse:.4f} "
          f"bias {rung.bias:+.4f}  {rung.verdict}{tail}")
print(f"\nABLATION LADDER — 20+ prior observations   [GATE: "
      f"{'PASS' if report.beats_recency_when_settled else 'FAIL'}]")
for rung in report.ladder_settled:
    tail = "" if rung.versus_engine is None else f"  Δ {rung.versus_engine:+.5f}±{rung.interval:.5f}"
    print(f"  {rung.name:22s} n={rung.n:4d} MAE {rung.mae:.4f}  {rung.verdict}{tail}")

print("\nBIAS BY TIME BLOCK")
for start, n, mean in report.drift:
    print(f"  days {start:3d}-{start+99:3d}  n={n:4d}  {mean:+.4f}")
print("\nBIAS BY EXPERIENCE OF THE EXERCISE")
for start, n, mean in report.by_experience:
    print(f"  observations {start:2d}-{start+9:2d}  n={n:4d}  {mean:+.4f}")

print("\nCALIBRATION ACROSS FATIGUE BINS")
for name, bins in report.calibration.items():
    cells = "  ".join(f"{b.mean_residual:+.4f}" for b in bins)
    print(f"  {name:16s} {cells}")

import statistics as st
print("\nCAPACITY AGAINST TRUE NEUTRAL CAPACITY")
print(f"  {'exercise':24s} {'n':>4} {'r':>7} {'raw err':>9} {'after scale':>12}")
ranked = sorted(report.capacity, key=lambda s: s.aligned_mean_error)
for score in ranked[:4] + ranked[-4:]:
    print(f"  {score.exercise_id:24s} {score.n:4d} {score.pearson:+7.3f} "
          f"{score.mean_relative_error:+9.2%} {score.aligned_mean_error:+12.2%}")
print(f"  {'MEAN |error|':24s} {'':4s} "
      f"{st.fmean(s.pearson for s in report.capacity):+7.3f} "
      f"{st.fmean(abs(s.mean_relative_error) for s in report.capacity):9.2%} "
      f"{st.fmean(abs(s.aligned_mean_error) for s in report.capacity):12.2%}")

print("\nRESPONSE DURING LABELLED EPISODES  (vs ordinary days within 45 days)")
for scenario in report.scenarios:
    print(f"  {scenario.label:22s} n={scenario.days:4d} days {scenario.span[0]:3d}-"
          f"{scenario.span[1]:3d}  {scenario.difference:+.4f}"
          f"±{scenario.interval:.4f}   {scenario.verdict}")

clipped, free = report.rho_clipped_residual
print(f"\nRECOVERY-MULTIPLIER CLIPPING COST")
print(f"  residual on clipped days {clipped:+.4f}   on unclipped days {free:+.4f}   "
      f"difference {clipped - free:+.4f}")
