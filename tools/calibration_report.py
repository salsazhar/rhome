"""Render the calibration bands (``DATA.md`` §19.4, L3.5)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: E402
from rhome_eval.calibration import BASELINE_NAME, run_calibration  # noqa: E402
from rhome_eval.run import evaluate  # noqa: E402
from rhome_eval.window import Window  # noqa: E402
from test_session_driver import _days  # noqa: E402

print("\nCALIBRATION BANDS — DATA.md §19.4")
print("Suppression of projected performance, 24 h after the most recent session.\n")
print(f"Trivial competitor (D23): {BASELINE_NAME}.\n")
print(f"{'state':46s} {'band':>14} {'engine':>8} {'simulator':>10} "
      f"{'counter':>8} {'up gap':>8}  engine / sim / counter")
results = run_calibration()
for result in results:
    print(f"{result.case.name:46s} "
          f"{result.case.lower_bound:5.1%}–{result.case.upper_bound:<7.1%} "
          f"{result.engine_lower_body:8.2%} {result.simulator_lower_body:10.2%} "
          f"{result.baseline_lower_body:8.2%} "
          f"{result.upper_body_gap:7.1f}pp  "
          f"{'in' if result.in_band else 'OUT'} / "
          f"{'in' if result.simulator_in_band else 'OUT'} / "
          f"{'in' if result.baseline_in_band else 'OUT'}")

engine_passed = sum(1 for r in results if r.in_band)
simulator_passed = sum(1 for r in results if r.simulator_in_band)
counter_passed = sum(1 for r in results if r.baseline_in_band)
print(f"\nengine {engine_passed}/{len(results)} in band; simulator "
      f"{simulator_passed}/{len(results)} in band; counter "
      f"{counter_passed}/{len(results)} in band.")
print("The counter is allowed one fitted scale, so it lands in the right units")
print("and the comparison is about structure. This is the one place in the D23")
print("re-audit where the engine is ahead of it — and both trail the simulator,")
print("which is what D21 already recorded.")

run = evaluate(_days(), Window.DEVELOPMENT)
clip = ENGINE_PARAMETERS.value("suppression_clip")
bound = sum(
    1 for result in run.results for record in result.projections.values()
    if sum(record.terms.values()) >= clip - 1e-12
)
total = sum(len(result.projections) for result in run.results)
print(f"Numerical-stability clip ({clip}) binds on {bound} of {total} projections "
      f"across the development window.")
print("§19.4 requires it not to bind outside S1, S2 and the overload block.")
