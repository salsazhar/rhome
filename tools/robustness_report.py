"""Render the robustness suite (``DATA.md`` §19.8, L3.7)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rhome_eval.robustness import (  # noqa: E402
    LOWER, bad_hrv_night, bad_session, compare_steps_to_a_session,
    first_day_with, first_day_with_wearables, high_step_days, run_perturbed,
    systematic_overperformance, upper_lower_parity, withhold_wearables,
)
from test_session_driver import _days  # noqa: E402

days = _days()
print("\nROBUSTNESS — DATA.md §19.8\n")

target = first_day_with_wearables(days)
run = run_perturbed(days, bad_hrv_night(target))
print(f"1. one bad HRV night (day {target}): rho "
      f"{run.clean_results[target].recovery.rho:.3f} → "
      f"{run.perturbed_results[target].recovery.rho:.3f}")
for offset in (0, 3, 14, 60):
    print(f"     local fatigue shift +{offset:2d} d  {run.fatigue_shift(target + offset):+8.3%}")

target = first_day_with(days, "bench_press", after=300)
run = run_perturbed(days, bad_session(target, "bench_press"))
print(f"\n2. one poor session (bench at 60%, day {target})")
for offset in (0, 7, 30, 120):
    print(f"     capacity shift +{offset:3d} d  "
          f"{run.capacity_shift_at('bench_press', min(target + offset, 519)):+8.3%}")

run = run_perturbed(days, systematic_overperformance(300, "bench_press", 1.10))
print("\n3. sustained +10% on bench from day 300")
for offset in (7, 30, 90, 200):
    print(f"     capacity shift +{offset:3d} d  "
          f"{run.capacity_shift_at('bench_press', min(300 + offset, 519)):+8.3%}")

run = run_perturbed(days, withhold_wearables(300, 14))
print("\n4. wearables withheld for 14 days")
print(f"     confidence shift        {run.confidence_shift(307):+8.4f}")
print(f"     fatigue shift in gap    {run.fatigue_shift(307):+8.3%}")
print(f"     fatigue shift after     {run.fatigue_shift(340):+8.3%}")

comparison = compare_steps_to_a_session(days)
print(f"\n5. one day at 25,000 steps against five hard squat sets, from clean")
print(f"     systemic   {comparison.steps_systemic:.4f} vs {comparison.session_systemic:.4f}"
      f"   ratio {comparison.systemic_ratio:.2f}")
print(f"     quads      {comparison.steps_quads:.4f} vs {comparison.session_quads:.4f}"
      f"   ratio {comparison.local_ratio:.2f}")

run = run_perturbed(days, high_step_days(300, 7))
parity = upper_lower_parity(run.clean_results)
print(f"\n6. upper/lower parity across {parity.blocks} blocks of 28 days")
print(f"     median ratio {parity.median_ratio:.3f}  spread {parity.spread:.3f}"
      f"  drift {parity.drift:+.3f}  max deviation {parity.max_deviation:.3f}")
