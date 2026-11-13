"""The holdout run (``DATA.md`` §15, L3.8). Opens the holdout — once.

**Running this opens the holdout and records the opening.** It writes its report
to ``build_log/holdout_result.txt`` *and* prints it, in one invocation, because
the first time it was used the report was captured by running it a second time
— and the seal duly recorded two openings. Anything that tempts a second run is
a defect in this tool.

Every metric Layer 3 built, re-run on days 520–729, which no version of the
engine has seen. The development figures sit beside them, because the question
is not "does the engine work" but "does it work on data it was not built
against".

The scale alignment is the one fitted on development, passed in unchanged. A
fresh one would tune a nuisance parameter on the test set.
"""
from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rhome_eval import metrics as m  # noqa: E402
from rhome_eval.baselines import ablation_ladder  # noqa: E402
from rhome_eval.confidence_metrics import score_confidence, score_traces  # noqa: E402
from rhome_eval.performance_metrics import SETTLED_AFTER, score_performance  # noqa: E402
from rhome_eval.run import CHANNELS, evaluate  # noqa: E402
from rhome_eval.state_metrics import score_states  # noqa: E402
from rhome_eval.window import Window, holdout_seal  # noqa: E402
from test_session_driver import _days  # noqa: E402


class _Tee:
    """Write to the report and the terminal at once, so neither needs a re-run."""

    def __init__(self, path: Path) -> None:
        self.handle = path.open("w", encoding="utf-8")

    def write(self, text: str) -> None:
        self.handle.write(text)
        sys.__stdout__.write(text)

    def flush(self) -> None:
        self.handle.flush()
        sys.__stdout__.flush()


sys.stdout = _Tee(ROOT / "build_log" / "holdout_result.txt")

REASON = (
    "L3.8 holdout run: the v0 engine, frozen after L3.7, evaluated once on "
    "days 520-729. Known limitations recorded in build_log/LIMITATIONS.md "
    "before the run."
)

days = _days()
print(f"\nBefore: {holdout_seal().note()}")

development = evaluate(days, Window.DEVELOPMENT)
holdout = evaluate(days, Window.HOLDOUT, alignment=development.alignment, reason=REASON)

print(f"After:  {holdout.seal.note()}")
print(f"\nAlignment: fitted on {holdout.alignment.fitted_on}, "
      f"digest {holdout.alignment.digest[:16]} — identical: "
      f"{holdout.alignment.digest == development.alignment.digest}")

dev_state, hold_state = score_states(development, days), score_states(holdout, days)
dev_perf, hold_perf = score_performance(development), score_performance(holdout)
dev_conf, hold_conf = score_confidence(development), score_confidence(holdout)
dev_trace, hold_trace = score_traces(development), score_traces(holdout)


def line(label: str, dev, hold, fmt: str = "{:+.3f}") -> None:
    d = fmt.format(dev) if dev is not None else "—"
    h = fmt.format(hold) if hold is not None else "—"
    print(f"  {label:44s} {d:>12} {h:>12}")


print(f"\n{'':46s} {'development':>12} {'HOLDOUT':>12}")
print("  " + "-" * 70)
print("  STATE RECONSTRUCTION")
for index, channel in enumerate(CHANNELS):
    line(f"    {channel} correlation",
         dev_state.channels[index].pearson, hold_state.channels[index].pearson)
    line(f"    {channel} vs set counter",
         dev_state.channels[index].baseline_pearson,
         hold_state.channels[index].baseline_pearson)
line("    per-muscle mean", dev_state.muscle_mean, hold_state.muscle_mean)
line("    per-muscle, set counter",
     dev_state.muscle_baseline_mean, hold_state.muscle_baseline_mean)
line("    recovery multiplier clipped",
     dev_state.rho_clipped_fraction, hold_state.rho_clipped_fraction, "{:.1%}")

print("\n  PERFORMANCE")
line("    one-step-ahead MAE", dev_perf.mae, hold_perf.mae, "{:.4f}")
line("    residual bias", dev_perf.bias, hold_perf.bias, "{:+.4f}")
line("    residual autocorrelation", dev_perf.autocorrelation, hold_perf.autocorrelation)
line("    scored sets", dev_perf.n, hold_perf.n, "{:d}")

print(f"\n  ABLATION LADDER, {SETTLED_AFTER}+ prior observations")
for name in ("engine", "mean of last 5", "median of last 3", "last observation"):
    d = next((r for r in dev_perf.ladder_settled if r.name == name), None)
    h = next((r for r in hold_perf.ladder_settled if r.name == name), None)
    verdict = f"  ({h.verdict})" if h and h.name != "engine" else ""
    line(f"    {name} MAE", d.mae if d else None, h.mae if h else None, "{:.4f}")
    if verdict:
        print(f"  {'':44s} {'':12} {verdict}")

print("\n  CONFIDENCE AND TRACE")
line("    binding reason always lowest",
     float(dev_conf.binding_always_lowest), float(hold_conf.binding_always_lowest), "{:.0f}")
line("    high before competitive",
     dev_conf.high_before_competitive, hold_conf.high_before_competitive, "{:.1%}")
line("    worst share error",
     dev_trace.worst_share_error, hold_trace.worst_share_error, "{:.2e}")
line("    driver boundary violations",
     len(dev_trace.boundary_violations), len(hold_trace.boundary_violations), "{:d}")

print(f"\n  {holdout.caveat}")
