"""Missing and malformed data (``DATA.md`` §17).

Real data is incomplete, so synthetic data must be too. A generator that
produced a complete record every night would let the engine assume the presence
of data it will frequently not have.

One property here matters more than the rates, and `DATA.md` §17 states it
directly: **missingness must not be concentrated only in adverse scenarios.**

If gaps clustered on bad days — the ring left off while ill, the scale skipped
during a hard week — then absence of data would itself carry information about
the athlete's state, and an engine could learn to read a missing night as a
warning sign. That would be a spurious signal invented by the generator, and it
would score well on this dataset and fail on real data, where a ring goes
uncharged for reasons that have nothing to do with training.

A small association with travel is retained, because it is genuinely true that
people are less consistent away from home. It is deliberately mild, and a test
requires most missing nights to fall on ordinary days.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from rhome_sim.recovery import WearableReading

__all__ = [
    "MissingnessConstants",
    "SIM_MISSINGNESS",
    "MissingnessModel",
    "MISSABLE_FIELDS",
]

#: Wearable fields that can individually go missing. Steps come from the phone
#: rather than the ring and survive a night it was not worn, so they are not
#: included.
MISSABLE_FIELDS: tuple[str, ...] = (
    "hrv_rmssd_ms",
    "resting_hr_bpm",
    "total_sleep_min",
    "sleep_efficiency",
    "temperature_deviation_c",
)


@dataclass(frozen=True)
class MissingnessConstants:
    """Simulator missingness constants (decision D8: not specification values)."""

    #: Nights losing exactly one metric (``DATA.md`` §17: 3-5%).
    partial_night_probability: float = 0.038
    #: Nights with no wearable data at all (§17: 1-2%).
    full_night_probability: float = 0.014
    #: How much more likely a gap is while travelling. Deliberately mild: a
    #: strong association would let absence of data signal the athlete's state.
    travel_multiplier: float = 1.8

    #: Chance a body-mass gap begins on any given day. Gaps come in blocks
    #: because people stop weighing themselves for a stretch, not for one day.
    bodyweight_gap_start_probability: float = 0.010
    bodyweight_gap_days: tuple[int, int] = (3, 14)
    #: Baseline chance of simply not stepping on the scale.
    bodyweight_skip_probability: float = 0.08

    #: Chance a set is logged without an effort rating (§17).
    missing_effort_probability: float = 0.018


SIM_MISSINGNESS = MissingnessConstants()


class MissingnessModel:
    """Removes data from an otherwise complete record."""

    def __init__(
        self,
        rng: np.random.Generator,
        constants: MissingnessConstants = SIM_MISSINGNESS,
    ) -> None:
        self.rng = rng
        self.k = constants
        self._bodyweight_gap_remaining = 0

    def apply_to_wearable(
        self, reading: WearableReading, *, travelling: bool = False
    ) -> tuple[WearableReading, str]:
        """Return the reading with fields removed, and its missingness label.

        The label matches ``DATA.md`` §5.1's ``wearable_missingness`` column:
        ``none``, ``partial`` or ``full``.
        """
        scale = self.k.travel_multiplier if travelling else 1.0
        draw = self.rng.random()

        if draw < self.k.full_night_probability * scale:
            blanked = {field: None for field in MISSABLE_FIELDS}
            return replace(reading, **blanked, body_mass_kg=None), "full"

        if draw < (self.k.full_night_probability + self.k.partial_night_probability) * scale:
            field = str(self.rng.choice(MISSABLE_FIELDS))
            return replace(reading, **{field: None}), "partial"

        return reading, "none"

    def apply_to_body_mass(self, reading: WearableReading) -> WearableReading:
        """Drop body mass, in blocks rather than scattered days.

        Someone who stops weighing themselves stops for a while. Scattered
        single-day gaps would let a simple interpolation recover the series,
        which is not the problem real data poses.
        """
        if self._bodyweight_gap_remaining > 0:
            self._bodyweight_gap_remaining -= 1
            return replace(reading, body_mass_kg=None)

        if self.rng.random() < self.k.bodyweight_gap_start_probability:
            low, high = self.k.bodyweight_gap_days
            self._bodyweight_gap_remaining = int(self.rng.integers(low, high + 1)) - 1
            return replace(reading, body_mass_kg=None)

        if self.rng.random() < self.k.bodyweight_skip_probability:
            return replace(reading, body_mass_kg=None)

        return reading

    def effort_is_missing(self) -> bool:
        """Whether a set was logged without an effort rating."""
        return bool(self.rng.random() < self.k.missing_effort_probability)


# --- malformed input fixture (DATA.md §17) ---------------------------------

@dataclass(frozen=True)
class DirtyRow:
    """One deliberately malformed input row, and what is wrong with it."""

    fields: dict[str, object]
    defect: str
    #: Whether a correct parser should reject the row outright, or repair it.
    expected: str  # "reject" | "repair"


def raw_dirty_rows() -> tuple[DirtyRow, ...]:
    """A fixture of malformed set rows for parser tests.

    Kept separate from the generated dataset (``DATA.md`` §17) so that the
    clean data stays clean. Every real ingestion path meets rows like these
    eventually, and the engine should fail on them loudly rather than quietly
    coercing a negative load to zero and carrying on.

    Each row states whether a correct parser should reject it or repair it.
    That distinction is the point: some defects are unrecoverable, and others
    have exactly one sensible reading.

    Only defects detectable from the row itself appear here. Two entries were
    removed on building the parser: a load recorded in pounds, and twenty
    repetitions at a near-maximal load. Both are real failure modes, but
    neither is decidable without the athlete's history --- a 220 kg bench press
    is implausible for this athlete and unremarkable for a world-class one.
    Contextual plausibility belongs where capacity is known, not in a parser,
    and putting it here would have meant a parser making claims it cannot
    support.
    """
    base = {
        "workout_id": "w_0042",
        "exercise_id": "bench_press",
        "set_number": 2,
        "set_type": "working",
        "external_load_kg": 100.0,
        "reps": 5,
        "rpe": 8.0,
        "rir": None,
        "is_pr": False,
    }

    def row(defect: str, expected: str, **overrides) -> DirtyRow:
        return DirtyRow({**base, **overrides}, defect, expected)

    return (
        row("negative external load", "reject", external_load_kg=-20.0),
        row("zero repetitions on a working set", "reject", reps=0),
        row("negative repetitions", "reject", reps=-3),
        row("RPE above the scale maximum", "reject", rpe=12.0),
        row("RPE below the scale minimum", "reject", rpe=1.0),
        row("negative repetitions in reserve", "reject", rpe=None, rir=-1.0),
        row("unknown exercise identifier", "reject", exercise_id="nonexistent_lift"),
        row("unknown set type", "reject", set_type="superset"),
        row("missing workout identifier", "reject", workout_id=""),
        row("non-numeric load", "reject", external_load_kg="heavy"),
        row("load beyond any human capacity", "reject", external_load_kg=900.0),
        row("repetitions beyond any plausible set", "reject", reps=300),
        row("RPE and RIR both present and contradicting each other", "repair",
            rpe=8.0, rir=4.0),
        row("repetitions recorded as a float", "repair", reps=5.0),
        row("set number duplicated within the exercise", "repair", set_number=2),
        row("whitespace and casing in a categorical field", "repair",
            set_type="  Working "),
    )
