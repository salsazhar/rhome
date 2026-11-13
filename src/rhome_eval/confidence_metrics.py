"""Confidence and trace integrity as a suite (``DATA.md`` §19.5–19.6, L3.6).

L2.6 and L2.7 tested these properties as they were built, on constructed inputs
and on the development run. This module runs them as an evaluation: over the
whole window, from the harness, with the same reporting discipline as every
other Layer 3 stage.

The addition it makes is the one the drift investigation specified. Capacity
confidence read ``high`` through the entire period in which the engine's
performance prediction was worse than a median-of-the-last-three baseline,
because its only observation term counted the last 28 days — a recency check —
while what mattered was how many times the exercise had ever been seen. That is
now a separate component, and this module measures whether it fixed the thing
it was added for.
"""

from __future__ import annotations

import statistics as st
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from rhome_engine.confidence import Band
from rhome_eval.run import EvaluationRun

__all__ = ["ExperienceBand", "ConfidenceReport", "TraceReport", "score_confidence",
           "score_traces"]

#: Sessions of an exercise below which the engine has been measured not to beat
#: a recency baseline (Checkpoint 2 ablation).
NOT_YET_COMPETITIVE = 20


@dataclass(frozen=True)
class ExperienceBand:
    """Capacity confidence, sliced by how much history stands behind it."""

    lower: int
    upper: int
    n: int
    mean_confidence: float
    bands: dict[str, int]
    binding: dict[str, int]

    @property
    def high_fraction(self) -> float:
        return self.bands.get(Band.HIGH.value, 0) / max(1, self.n)


@dataclass(frozen=True)
class ConfidenceReport:
    """``DATA.md`` §19.5, measured over a window."""

    days: int = 0
    fatigue_bands: dict[str, int] = field(default_factory=dict)
    binding_always_lowest: bool = True
    early_bound_by_maturity: float = 0.0
    wearable_gap_days: int = 0
    wearable_gap_penalty: float = 0.0
    experience: tuple[ExperienceBand, ...] = ()
    caveat: str = ""

    @property
    def high_before_competitive(self) -> float:
        """Share of capacity readings that claim high confidence too early.

        The number the maturity component was added to move. Before it, 88% of
        the first ten sessions of an exercise read ``high`` while the engine was
        losing to a moving average.
        """
        early = [b for b in self.experience if b.upper <= NOT_YET_COMPETITIVE]
        total = sum(b.n for b in early)
        if not total:
            return 0.0
        return sum(b.bands.get(Band.HIGH.value, 0) for b in early) / total


@dataclass(frozen=True)
class TraceReport:
    """``DATA.md`` §19.6, measured over a window."""

    traces: int = 0
    worst_share_error: float = 0.0
    worst_reconstruction_error: float = 0.0
    distinct_drivers: int = 0
    boundary_violations: tuple[str, ...] = ()
    graded_parameters: int = 0
    grade_counts: dict[str, int] = field(default_factory=dict)
    caveat: str = ""


def score_confidence(run: EvaluationRun) -> ConfidenceReport:
    reports = [r.confidence for r in run.results if r.confidence]
    bands: dict[str, int] = defaultdict(int)
    binding_ok = True
    for report in reports:
        bands[report.fatigue.band.value] += 1
        lowest = min(c.value for c in report.fatigue.components)
        if abs(report.fatigue.binding_reason.value - lowest) > 1e-12:
            binding_ok = False

    early = [r for r in run.results[:41] if r.confidence]
    by_maturity = sum(
        1 for r in early
        if r.confidence.fatigue.binding_reason.name == "baseline maturity"
    )

    blank = [r for r in run.results if r.recovery.channels_present == 0]
    complete = [r for r in run.results if r.recovery.channels_present == 5]
    penalty = 0.0
    if blank and complete:
        penalty = st.fmean(
            c.confidence.fatigue.value for c in complete
        ) - st.fmean(b.confidence.fatigue.value for b in blank)

    seen: dict[str, int] = defaultdict(int)
    buckets: dict[int, list] = defaultdict(list)
    for result in run.results:
        for observation in result.observations:
            seen[observation.exercise_id] += 1
            entry = result.confidence.capacity.get(observation.exercise_id)
            if entry is not None:
                buckets[min((seen[observation.exercise_id] - 1) // 10, 3)].append(entry)

    experience: list[ExperienceBand] = []
    for index in sorted(buckets):
        entries = buckets[index]
        band_counts: dict[str, int] = defaultdict(int)
        binding_counts: dict[str, int] = defaultdict(int)
        for entry in entries:
            band_counts[entry.band.value] += 1
            binding_counts[entry.binding_reason.name] += 1
        experience.append(
            ExperienceBand(
                lower=index * 10 + 1,
                upper=(index + 1) * 10 if index < 3 else 999,
                n=len(entries),
                mean_confidence=st.fmean(e.value for e in entries),
                bands=dict(band_counts),
                binding=dict(binding_counts),
            )
        )

    return ConfidenceReport(
        days=len(reports),
        fatigue_bands=dict(bands),
        binding_always_lowest=binding_ok,
        early_bound_by_maturity=by_maturity / max(1, len(early)),
        wearable_gap_days=len(blank),
        wearable_gap_penalty=penalty,
        experience=tuple(experience),
        caveat=run.caveat,
    )


def score_traces(run: EvaluationRun) -> TraceReport:
    from rhome_engine.trace import ClaimBoundaryError, check_claim_boundaries  # noqa: PLC0415

    traces = [t for r in run.results for t in r.traces.values()]
    if not traces:
        return TraceReport(caveat=run.caveat)

    drivers = {t.driver for t in traces if t.driver}
    violations: list[str] = []
    for driver in drivers:
        try:
            check_claim_boundaries(driver)
        except ClaimBoundaryError as error:
            violations.append(str(error))

    grades: dict[str, int] = defaultdict(int)
    for parameter in traces[-1].parameters:
        grades[parameter.grade] += 1

    return TraceReport(
        traces=len(traces),
        worst_share_error=max(abs(t.share_total() - 1.0) for t in traces),
        worst_reconstruction_error=max(
            abs(t.reconstruct() - t.value) / max(t.value, 1e-12) for t in traces
        ),
        distinct_drivers=len(drivers),
        boundary_violations=tuple(violations),
        graded_parameters=len(traces[-1].parameters),
        grade_counts=dict(grades),
        caveat=run.caveat,
    )
