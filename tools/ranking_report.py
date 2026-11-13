"""Render the ranking tests (``DATA.md`` §19.3, L3.4)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rhome_eval.ranking import (  # noqa: E402
    BASELINE_NAME, deload_response, run_rankings,
)
from rhome_eval.run import evaluate  # noqa: E402
from rhome_eval.window import Window  # noqa: E402
from test_session_driver import _days  # noqa: E402

print("\nRANKING TESTS — DATA.md §19.3\n")
print(f"Trivial competitor (D23): {BASELINE_NAME}. It gets the library's own")
print("columns and nothing the engine works out — no proximity to failure, no")
print("repetition modulation, no relative intensity, no novelty.\n")
print(f"{'ordering':46s} {'engine':>9} {'truth':>9} {'expressed':>10} "
      f"{'counter':>8}  verdict")
ratios = []
earned = 0
for result in run_rankings():
    ratio = result.engine_margin / result.truth_margin
    ratios.append(ratio)
    earned += result.earned
    correct = result.baseline_correct
    counter = "ties" if correct is None else ("right" if correct else "wrong")
    print(f"{result.case.name:46s} {result.engine_margin:+9.1%} "
          f"{result.truth_margin:+9.1%} {ratio:10.0%} {counter:>8}  {result.verdict}")

response = deload_response(evaluate(_days(), Window.DEVELOPMENT))
ratio = response.engine_gain / response.truth_gain
ratios.append(ratio)
earned += response.earned
correct = response.baseline_correct
counter = "ties" if correct is None else ("right" if correct else "wrong")
print(f"{'post-deload vs pre-deload performance':46s} {response.engine_gain:+9.1%} "
      f"{response.truth_gain:+9.1%} {ratio:10.0%} {counter:>8}  "
      f"{'correct' if response.engine_correct and response.truth_correct else 'FAILED'}"
      f"   ({response.engine_agreements}/{response.episodes} pairs agree)")

total = len(ratios)
print(f"\n{total}/{total} orderings correct. The engine expresses "
      f"{sum(ratios) / total:.0%} of the true contrast on average.")
print(f"\n**{earned}/{total} of those orderings are EARNED** — correct, and not")
print("already free to a counter that has the library's authored columns. The")
print("rest are orderings a set counter produces without any fatigue model at")
print("all, so getting them right is necessary but says nothing on its own (D23).")
