"""Robustness under perturbation (``DATA.md`` §19.8).

Six requirements, each measured the same way: run the engine over the
development window twice, once with one thing changed, and compare. A
robustness claim tested on a constructed toy state is a claim about the
arithmetic; tested by perturbing a real 520-day record it is a claim about the
engine.

The pairing matters. Both runs see the same log, the same seeds and the same
everything except the perturbation, so any difference is attributable. Nothing
here reads latent truth — these are questions about the engine's own
behaviour — but the harness owns them because they need a full run to answer.
"""

from __future__ import annotations

import statistics as st
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Callable, Sequence

from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_engine.session import DayInput, RhomeEngine

__all__ = [
    "PerturbedRun",
    "run_perturbed",
    "bad_hrv_night",
    "bad_session",
    "systematic_overperformance",
    "withhold_wearables",
    "high_step_days",
    "upper_lower_parity",
]

LIBRARY = load_library()
DEV_DAYS = 520

Perturbation = Callable[[DayInput], DayInput]


@dataclass
class PerturbedRun:
    """A clean run and a perturbed one, over the same log."""

    clean: RhomeEngine
    perturbed: RhomeEngine
    clean_results: tuple
    perturbed_results: tuple

    def state_shift(self, day_index: int, channel: str) -> float:
        """Relative change in a whole-body channel on one day."""
        before = getattr(self.clean_results[day_index].state, channel)
        after = getattr(self.perturbed_results[day_index].state, channel)
        return after / max(before, 1e-12) - 1.0

    def fatigue_shift(self, day_index: int, muscles: Sequence[Muscle] = ()) -> float:
        clean = self.clean_results[day_index].state.local_fatigue
        dirty = self.perturbed_results[day_index].state.local_fatigue
        selected = muscles or tuple(clean)
        before = sum(clean[m] for m in selected)
        after = sum(dirty[m] for m in selected)
        return after / max(before, 1e-12) - 1.0

    def capacity_shift(self, exercise_id: str) -> float:
        before = self.clean.capacity.capacity(exercise_id)
        after = self.perturbed.capacity.capacity(exercise_id)
        if before is None or after is None:
            raise ValueError(f"no capacity for {exercise_id}")
        return after / before - 1.0

    def capacity_shift_at(self, exercise_id: str, day_index: int) -> float:
        """Capacity displacement as at a given day, from the observation record."""
        def latest(results) -> float | None:
            value = None
            for result in results[: day_index + 1]:
                for observation in result.observations:
                    if observation.exercise_id == exercise_id:
                        value = observation.capacity_after
            return value

        before, after = latest(self.clean_results), latest(self.perturbed_results)
        if before is None or after is None:
            return 0.0
        return after / before - 1.0

    def confidence_shift(self, day_index: int) -> float:
        return (
            self.perturbed_results[day_index].confidence.fatigue.value
            - self.clean_results[day_index].confidence.fatigue.value
        )


class PerturbationDidNothing(AssertionError):
    """The perturbation left the input unchanged, so the run proves nothing."""


def run_perturbed(days: Sequence[DayInput], perturbation: Perturbation) -> PerturbedRun:
    """Run clean and perturbed over the same window, and check the change landed.

    The check is not defensive tidiness. A first attempt at the bad-HRV test
    targeted day 300, which happens to be one of the eight nights with no
    wearable data at all — so there was no HRV to halve, the two runs were
    identical, and the result read as a perfect 0.000% shift at every horizon.
    A perturbation that silently does nothing reports robustness, which is the
    vacuous pass this project has now found four times.
    """
    window = [d for d in days if d.day_index < DEV_DAYS]
    perturbed_input = [perturbation(d) for d in window]
    if perturbed_input == window:
        raise PerturbationDidNothing(
            "the perturbed input is identical to the clean input; the target "
            "day may not carry the field being perturbed"
        )

    clean = RhomeEngine(LIBRARY)
    clean_results = clean.run(list(window))
    dirty = RhomeEngine(LIBRARY)
    dirty_results = dirty.run(perturbed_input)
    return PerturbedRun(clean, dirty, tuple(clean_results), tuple(dirty_results))


def first_day_with_wearables(days: Sequence[DayInput], after: int = 200) -> int:
    """A day carrying a full wearable reading, for perturbations that need one."""
    for day in days:
        if day.day_index > after and day.reading.channels_present == 5:
            return day.day_index
    raise ValueError("no complete wearable night found")


def first_day_with(days: Sequence[DayInput], exercise_id: str, after: int = 200) -> int:
    for day in days:
        if day.day_index > after and any(
            s.exercise_id == exercise_id and s.set_type in ("working", "backoff")
            for s in day.sets
        ):
            return day.day_index
    raise ValueError(f"no session with {exercise_id} after day {after}")


# --- the six perturbations ----------------------------------------------------

def bad_hrv_night(day_index: int, factor: float = 0.55) -> Perturbation:
    """One night's heart-rate variability collapses."""
    def perturb(day: DayInput) -> DayInput:
        if day.day_index != day_index or day.reading.hrv_rmssd_ms is None:
            return day
        return replace(
            day, reading=replace(day.reading, hrv_rmssd_ms=day.reading.hrv_rmssd_ms * factor)
        )
    return perturb


def bad_session(day_index: int, exercise_id: str, factor: float = 0.6) -> Perturbation:
    """One session's loads on one exercise collapse."""
    def perturb(day: DayInput) -> DayInput:
        if day.day_index != day_index:
            return day
        return replace(day, sets=[
            replace(s, load_kg=s.load_kg * factor) if s.exercise_id == exercise_id else s
            for s in day.sets
        ])
    return perturb


def systematic_overperformance(
    from_day: int, exercise_id: str, factor: float = 1.10
) -> Perturbation:
    """Every set of one exercise gets heavier, from a day onward.

    §19.8 requires that repeated systematic residuals *can* move capacity. The
    Huber clip bounds one session's influence; it must not bound a run of them.
    """
    def perturb(day: DayInput) -> DayInput:
        if day.day_index < from_day:
            return day
        return replace(day, sets=[
            replace(s, load_kg=s.load_kg * factor) if s.exercise_id == exercise_id else s
            for s in day.sets
        ])
    return perturb


def withhold_wearables(from_day: int, days_count: int = 14) -> Perturbation:
    """A block of nights with no wearable data at all."""
    from rhome_engine.recovery import RecoveryReading  # noqa: PLC0415

    def perturb(day: DayInput) -> DayInput:
        if not from_day <= day.day_index < from_day + days_count:
            return day
        return replace(day, reading=RecoveryReading())
    return perturb


def high_step_days(from_day: int, days_count: int = 7, steps: float = 25000.0) -> Perturbation:
    """A week of very high step counts."""
    def perturb(day: DayInput) -> DayInput:
        if not from_day <= day.day_index < from_day + days_count:
            return day
        return replace(day, steps=steps)
    return perturb


# --- parity -------------------------------------------------------------------

UPPER = (
    Muscle.CHEST, Muscle.LATS, Muscle.UPPER_BACK, Muscle.ANTERIOR_DELTS,
    Muscle.LATERAL_DELTS, Muscle.POSTERIOR_DELTS, Muscle.BICEPS, Muscle.TRICEPS,
)
LOWER = (
    Muscle.QUADS, Muscle.HAMSTRINGS, Muscle.GLUTES, Muscle.CALVES,
    Muscle.ADDUCTORS, Muscle.SPINAL_ERECTORS,
)


@dataclass(frozen=True)
class ParityResult:
    """Upper against lower fatigue, over rolling blocks.

    §19.8 asks that parity be *preserved* across normal training blocks. That
    is a question about stability, not about the ratio being one: lower-body
    muscles carry more fatigue per muscle because compound lifts load several
    of them at once, and a ratio of 1.0 would mean the model had stopped
    distinguishing a squat day from a bench day.

    A first version scored distance from 1.0 with a ±0.5 tolerance, which
    passed on every block while measuring nothing — the ratio sits near 0.69
    throughout and never approaches the bound.
    """

    blocks: int
    median_ratio: float
    spread: float
    drift: float
    max_deviation: float


def upper_lower_parity(results: Sequence, block_days: int = 28) -> ParityResult:
    ratios: list[float] = []
    for start in range(0, len(results) - block_days, block_days):
        block = results[start : start + block_days]
        upper = st.fmean(
            st.fmean(r.state.local_fatigue[m] for m in UPPER) for r in block
        )
        lower = st.fmean(
            st.fmean(r.state.local_fatigue[m] for m in LOWER) for r in block
        )
        if lower > 0:
            ratios.append(upper / lower)
    if not ratios:
        return ParityResult(0, 0.0, 0.0, 0.0, 0.0)

    median = st.median(ratios)
    half = len(ratios) // 2
    drift = st.fmean(ratios[half:]) - st.fmean(ratios[:half])
    return ParityResult(
        blocks=len(ratios),
        median_ratio=median,
        spread=st.pstdev(ratios),
        drift=drift,
        max_deviation=max(abs(r - median) for r in ratios),
    )


@dataclass(frozen=True)
class StepComparison:
    """What a day of heavy walking deposits, next to five hard squat sets.

    §19.8 requires high step counts to affect lower and systemic load
    *modestly, not as resistance volume*. "Modestly" needs a reference, and the
    reference has to be commensurable.

    A first version compared *seven days* of walking against *one* inserted
    session, as relative shifts in an already-elevated state, and reported
    walking at 5.4× a squat session — which read as a clear failure of this
    requirement. It was a failure of the comparison: seven days accumulate
    while one session decays, and a relative shift depends on what the state
    already held. Measured per day, against the same five sets, on a clean
    state, walking is a sixth of a session systemically and a twenty-fifth of
    it locally.
    """

    steps_systemic: float
    session_systemic: float
    steps_quads: float
    session_quads: float
    amplitude: float

    @property
    def systemic_ratio(self) -> float:
        return self.steps_systemic / max(self.session_systemic, 1e-12)

    @property
    def local_ratio(self) -> float:
        return self.steps_quads / max(self.session_quads, 1e-12)


def compare_steps_to_a_session(
    days: Sequence[DayInput], steps: float = 25000.0
) -> StepComparison:
    """One very high step day against five hard squat sets, from a clean state."""
    from rhome_core.timeline import RecoveryTimeline, RecoveryWindow  # noqa: PLC0415
    from rhome_engine.dose import LoggedSet, transform_set  # noqa: PLC0415
    from rhome_engine.state import StateEngine  # noqa: PLC0415

    baseline = st.median([d.steps for d in days if d.steps is not None])
    read_at = 23.5

    walking = StateEngine(RecoveryTimeline([RecoveryWindow(0.0, 1.0)]))
    amplitude = walking.set_activity_window(steps, baseline, 7.5)
    walking.advance_to(read_at)

    lifting = StateEngine(RecoveryTimeline([RecoveryWindow(0.0, 1.0)]))
    squat = LIBRARY["back_squat"]
    for index in range(5):
        logged = LoggedSet("cmp", "back_squat", index + 1, "working",
                           load_kg=140.0, reps=5, rir=1.0)
        lifting.apply_dose(transform_set(logged, squat), 17.0 + index * 0.02, "back_squat")
    lifting.advance_to(read_at)

    return StepComparison(
        steps_systemic=walking.state.systemic,
        session_systemic=lifting.state.systemic,
        steps_quads=walking.state.local_fatigue[Muscle.QUADS],
        session_quads=lifting.state.local_fatigue[Muscle.QUADS],
        amplitude=amplitude,
    )
