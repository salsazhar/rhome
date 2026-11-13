"""Render the state-reconstruction report (``DATA.md`` §19.1, L3.2)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rhome_eval.run import evaluate  # noqa: E402
from rhome_eval.state_metrics import score_states  # noqa: E402
from rhome_eval.window import Window  # noqa: E402
from test_session_driver import _days  # noqa: E402

days = _days()
report = score_states(evaluate(days, Window.DEVELOPMENT), days)

print(f"\nSTATE RECONSTRUCTION — {report.caveat}\n")
print(f"{'channel':16s} {'pearson':>8} {'spearman':>9} {'RMSE':>8} {'direction':>10}"
      f" {'counter':>9} {'advantage':>10}")
for score in report.channels:
    print(f"{score.channel:16s} {score.pearson:+8.3f} {score.spearman:+9.3f} "
          f"{score.rmse:8.4f} {score.directional_accuracy:10.1%} "
          f"{score.baseline_pearson:+9.3f} {score.advantage:+10.3f}")

print(f"\n{'':16s} {'peak ≤1d':>10} {'counter':>9} {'authored':>10} "
      f"{'med peak':>9} {'med cross':>10} {'n':>5}")
for score in report.timing:
    print(f"{score.channel:16s} {score.peak_within_a_day:10.1%} "
          f"{score.baseline_peak_within_a_day:9.1%} "
          f"{score.authored_peak_within_a_day:10.1%} "
          f"{score.median_peak_error:9.1f} {score.median_crossing_error:10.1f} "
          f"{score.sessions:5d}")
print("  'authored' is the counter given the library's own column for the")
print("  channel (D23). Neuromuscular timing was the last claim expected to")
print("  survive the re-audit, and it does not.")

print(f"\n{'muscle':18s} {'pearson':>8} {'spearman':>9} {'direction':>10} "
      f"{'counter':>9} {'c_F counter':>12} {'advantage':>10}")
for score in sorted(report.muscles, key=lambda s: s.pearson):
    best = score.best_attributed
    print(f"{score.muscle.value:18s} {score.pearson:+8.3f} {score.spearman:+9.3f} "
          f"{score.directional_accuracy:10.1%} {score.baseline_pearson:+9.3f} "
          f"{best[1]:+12.3f} {score.attributed_advantage:+10.3f}")
attributed_mean = report.muscle_attributed_baseline_mean
print(f"{'MEAN':18s} {report.muscle_mean:+8.3f} {'':9s} {'':10s} "
      f"{report.muscle_baseline_mean:+9.3f} {attributed_mean:+12.3f} "
      f"{report.muscle_mean - attributed_mean:+10.3f}")

print(f"\nCROSS-SECTIONAL — between muscles within a day, day means removed.")
print("74% of the true latent variance lives here; this is the body map's own claim.")
print(f"\n{'predictor':34s} {'pooled r':>10} {'mean per-day r':>16} {'days':>6}")
for score in report.cross_sectional:
    print(f"{score.name:34s} {score.pooled:+10.3f} {score.per_day_mean:+16.3f} "
          f"{score.days:6d}")

print(f"\nrecovery multiplier clipped on {report.rho_clipped_fraction:.1%} of days, "
      f"longest run {report.rho_longest_clipped_run} days")
for note in report.notes:
    print(f"  · {note}")
