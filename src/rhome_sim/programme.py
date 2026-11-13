"""Training programme generation (``DATA.md`` §3.2, §8, §9).

Decides what Athlete A sets out to do: which days they train, which exercises,
how many sets, and at what target repetitions and proximity to failure.

This module produces *intentions*. What the athlete actually achieves depends on
their realised performance on the day, which is L1.5's concern. The separation
matters because a programme that always went to plan would remove exactly the
variation the engine needs to model — real training is a plan, imperfectly met.

Two constraints shape everything here.

``DATA.md`` §3.2 requires upper and lower primary effective-set stimulus to stay
within roughly ±10% of one another across every ordinary rolling four-week
block. It is a hard requirement, and it is easy to violate accidentally: upper
bodies have more small muscles and therefore attract more isolation work.

``DATA.md`` §9.3 asks most major muscle groups to receive 10–14 effective sets
per week. Satisfying both at once constrains the templates considerably, so
they were tuned by measurement rather than by eye.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from rhome_core.exercises import ExerciseLibrary
from rhome_core.muscles import REGION_OF, Region

__all__ = [
    "SessionType",
    "Prescription",
    "SessionPlan",
    "WEEKLY_TEMPLATE",
    "SESSION_TEMPLATES",
    "SUBSTITUTIONS",
    "ProgrammeGenerator",
]


class SessionType(StrEnum):
    UPPER_A = "upper_a"
    LOWER_A = "lower_a"
    UPPER_B = "upper_b"
    LOWER_B = "lower_b"
    FULL_BODY = "full_body"
    REST = "rest"


#: Day of week (0 = Monday) to session type. Approximately five lifting
#: sessions per week with explicit upper/lower parity, per ``DATA.md`` §3.2.
WEEKLY_TEMPLATE: tuple[SessionType, ...] = (
    SessionType.UPPER_A,
    SessionType.LOWER_A,
    SessionType.REST,
    SessionType.UPPER_B,
    SessionType.LOWER_B,
    SessionType.FULL_BODY,
    SessionType.REST,
)


@dataclass(frozen=True)
class Prescription:
    """One exercise as planned: sets, a repetition range, and a target effort."""

    exercise_id: str
    sets: int
    rep_low: int
    rep_high: int
    target_rir: float

    def __post_init__(self) -> None:
        if self.sets < 1:
            raise ValueError(f"{self.exercise_id}: sets must be positive")
        if self.rep_low > self.rep_high:
            raise ValueError(f"{self.exercise_id}: inverted repetition range")
        if self.target_rir < 0:
            raise ValueError(f"{self.exercise_id}: target RIR cannot be negative")


@dataclass(frozen=True)
class SessionPlan:
    """What the athlete intends to do on one day."""

    day_index: int
    session_type: SessionType
    prescriptions: tuple[Prescription, ...]
    is_deload: bool = False
    notes_code: str | None = None

    @property
    def total_sets(self) -> int:
        return sum(p.sets for p in self.prescriptions)


# Templates are (exercise_id, sets, rep_low, rep_high, target_rir).
# Compound movements sit in the lower and middle repetition ranges and further
# from failure; isolation work sits higher and closer to it, which is both how
# people train and what produces the §9.1 and §9.2 distributions.
SESSION_TEMPLATES: dict[SessionType, tuple[tuple[str, int, int, int, float], ...]] = {
    SessionType.UPPER_A: (
        ("bench_press", 1, 2, 3, 2.5),
        ("bench_press", 2, 4, 6, 2.0),
        ("overhead_press", 4, 4, 6, 2.5),
        ("incline_db_press", 3, 8, 10, 1.5),
        ("triceps_pressdown", 2, 8, 10, 0.5),
        ("lateral_raise", 2, 12, 15, 0.5),
    ),
    SessionType.UPPER_B: (
        ("weighted_pullup", 3, 4, 6, 2.0),
        ("chest_supported_row", 2, 4, 6, 2.2),
        ("cable_row", 2, 8, 10, 1.5),
        ("db_curl", 4, 8, 10, 1.0),
        ("reverse_pec_deck", 2, 12, 15, 0.5),
        ("wrist_curl", 2, 16, 20, 0.5),
    ),
    SessionType.LOWER_A: (
        ("back_squat", 2, 2, 3, 2.5),
        ("back_squat", 2, 4, 6, 2.0),
        ("romanian_deadlift", 2, 4, 6, 3.0),
        ("leg_press", 2, 8, 10, 2.0),
        ("leg_curl", 2, 8, 10, 0.5),
        ("calf_raise", 5, 12, 15, 0.5),
        ("ab_wheel_rollout", 3, 8, 12, 1.5),
    ),
    SessionType.LOWER_B: (
        ("deadlift", 2, 2, 3, 2.5),
        ("deadlift", 2, 4, 6, 2.0),
        ("bulgarian_split_squat", 2, 8, 10, 1.5),
        ("leg_extension", 2, 8, 10, 0.5),
        ("back_extension", 3, 8, 10, 2.0),
        ("hip_adduction", 4, 12, 15, 1.0),
        ("calf_raise", 4, 16, 20, 0.5),
    ),
    SessionType.FULL_BODY: (
        ("weighted_dip", 3, 4, 6, 2.0),
        ("hack_squat", 3, 4, 6, 2.5),
        ("lat_pulldown", 2, 8, 10, 1.5),
        ("hanging_leg_raise", 3, 8, 10, 1.0),
        ("leg_curl", 2, 10, 13, 1.0),
        ("cable_crunch", 2, 12, 15, 0.5),
        ("lateral_raise", 2, 16, 20, 0.5),
    ),
}

#: Plausible like-for-like swaps (``DATA.md`` §8.4). Substitutions happen for
#: equipment availability, planned variation and travel, never at random.
SUBSTITUTIONS: dict[str, tuple[str, ...]] = {
    "bench_press": ("incline_db_press", "weighted_dip"),
    "incline_db_press": ("bench_press", "weighted_dip"),
    "weighted_dip": ("incline_db_press",),
    "overhead_press": ("lateral_raise",),
    "weighted_pullup": ("lat_pulldown",),
    "lat_pulldown": ("weighted_pullup",),
    "chest_supported_row": ("cable_row",),
    "cable_row": ("chest_supported_row",),
    "back_squat": ("hack_squat", "leg_press"),
    "hack_squat": ("leg_press", "back_squat"),
    "leg_press": ("hack_squat",),
    "romanian_deadlift": ("back_extension", "deadlift"),
    "deadlift": ("romanian_deadlift",),
    "bulgarian_split_squat": ("leg_press",),
    "reverse_pec_deck": ("lateral_raise",),
    "cable_crunch": ("hanging_leg_raise", "ab_wheel_rollout"),
    "hanging_leg_raise": ("cable_crunch", "ab_wheel_rollout"),
    "ab_wheel_rollout": ("cable_crunch",),
}


class ProgrammeGenerator:
    """Produces the sequence of session plans for the athlete.

    Ordinary weeks follow the template. Deload weeks reduce volume while
    retaining some intensity exposure. Sessions are occasionally missed or
    shifted for non-physiological reasons, because a schedule that never
    slipped would be its own kind of unrealistic.
    """

    #: Probability an ordinary lifting session is not performed as scheduled.
    MISS_PROBABILITY = 0.050
    #: Probability a missed session is made up on the next rest day rather than
    #: lost. Set to 1.0 deliberately.
    #:
    #: Measurement showed unrecovered misses to be the sole cause of upper/lower
    #: parity violations: with misses removed, every rolling four-week block
    #: falls inside the ±10% DATA.md §3.2 requires, and with them roughly one
    #: block in fifteen does not. Substitutions and light weeks were negligible
    #: by comparison.
    #:
    #: Rest days fall on template slots 2 and 6, so every make-up lands in the
    #: same week as the session it replaces. Ordinary life therefore shifts
    #: sessions within a week rather than removing them, which is also what
    #: athletes actually do.
    #:
    #: Genuine absence is not thereby removed from the dataset — it belongs to
    #: the labelled scenarios S6 (travel) and S12 (missed-session block), which
    #: §3.2 explicitly exempts from the parity requirement. Keeping true
    #: absence inside labelled scenarios makes it something the evaluation can
    #: reason about rather than background noise.
    MAKEUP_PROBABILITY = 1.0
    #: Probability an exercise is substituted on a given day.
    SUBSTITUTION_PROBABILITY = 0.045
    #: Every Nth week the athlete plans one session off. Real training averages
    #: five sessions a week rather than guaranteeing them (DATA.md §18), and a
    #: *planned* omission that rotates through session types stays region-
    #: balanced, where an unlucky run of skipped upper days does not.
    LIGHT_WEEK_PERIOD = 5
    #: Deload every N weeks during ordinary training.
    DELOAD_PERIOD_WEEKS = 8
    #: Volume retained during a deload (``DATA.md`` S3: reduce 40–60%).
    DELOAD_VOLUME_FRACTION = 0.5
    #: Extra repetitions in reserve during a deload.
    DELOAD_RIR_ADDITION = 1.5

    #: How strongly the athlete protects the region they have neglected. Real
    #: athletes prioritise what they have skipped, and without this the
    #: upper/lower parity requirement of DATA.md §3.2 fails on any four-week
    #: block where missed sessions happen to fall on one side.
    REGION_CORRECTION = 5.0

    def __init__(self, library: ExerciseLibrary, rng: np.random.Generator) -> None:
        self.library = library
        self.rng = rng
        self._validate_templates()
        self._trailing: list[tuple[int, float, float]] = []

    def _session_region_stimulus(self, session_type: SessionType) -> tuple[float, float]:
        """Primary-equivalent stimulus this session delivers to each region."""
        upper = lower = 0.0
        for exercise_id, sets, *_ in SESSION_TEMPLATES[session_type]:
            for muscle, contribution in self.library[exercise_id].stimulus_contributions.items():
                if REGION_OF[muscle] is Region.UPPER:
                    upper += sets * contribution
                elif REGION_OF[muscle] is Region.LOWER:
                    lower += sets * contribution
        return upper, lower

    def _miss_probability(self, day_index: int, session_type: SessionType) -> float:
        """Miss probability, adjusted to protect the neglected region.

        A session is less likely to be skipped when its region is behind over
        the trailing four weeks, and more likely when it is ahead.
        """
        imbalance = self._region_imbalance(day_index)
        if imbalance == 0.0:
            return self.MISS_PROBABILITY

        session_upper, session_lower = self._session_region_stimulus(session_type)
        if session_upper == session_lower:
            return self.MISS_PROBABILITY

        # Positive when the session's dominant region is the one that is ahead.
        leans_upper = session_upper > session_lower
        signed = imbalance if leans_upper else -imbalance
        factor = float(np.clip(1.0 + self.REGION_CORRECTION * signed, 0.15, 3.0))
        return min(0.5, self.MISS_PROBABILITY * factor)

    def _region_imbalance(self, day_index: int, window_days: int = 28) -> float:
        """Trailing upper-minus-lower stimulus, as a fraction of the mean.

        Positive means upper is ahead.
        """
        window = [r for r in self._trailing if day_index - r[0] <= window_days]
        upper = sum(r[1] for r in window)
        lower = sum(r[2] for r in window)
        if upper + lower <= 0:
            return 0.0
        return (upper - lower) / ((upper + lower) / 2.0)

    def _slot_to_omit(self, day_index: int, lifting_slots: list[int]) -> int:
        """Choose the light week's omitted session to leave parity least harmed.

        Minimises the imbalance that *remains* after the omission, rather than
        favouring whichever session leans hardest toward the region that is
        ahead. When the athlete is already balanced, every omission harms
        parity, and the least harmful is the most region-neutral session — the
        full-body day. Picking the most lopsided session in that situation
        creates the imbalance it was meant to prevent.
        """
        window = [r for r in self._trailing if day_index - r[0] <= 28]
        current = sum(r[1] for r in window) - sum(r[2] for r in window)

        best_slot, best_residual = lifting_slots[0], None
        for slot in lifting_slots:
            upper, lower = self._session_region_stimulus(WEEKLY_TEMPLATE[slot])
            residual = abs(current - (upper - lower))
            if best_residual is None or residual < best_residual:
                best_slot, best_residual = slot, residual
        return best_slot

    def _record(self, day_index: int, session_type: SessionType) -> None:
        upper, lower = self._session_region_stimulus(session_type)
        self._trailing.append((day_index, upper, lower))

    def _validate_templates(self) -> None:
        """Fail loudly if a template names an exercise the library lacks."""
        for session_type, template in SESSION_TEMPLATES.items():
            for exercise_id, *_ in template:
                if exercise_id not in self.library:
                    raise ValueError(
                        f"{session_type.value} prescribes {exercise_id!r}, which is "
                        f"not in the exercise library"
                    )
        for source, targets in SUBSTITUTIONS.items():
            for target in (source, *targets):
                if target not in self.library:
                    raise ValueError(f"substitution names unknown exercise {target!r}")

    def _substitute(self, exercise_id: str) -> tuple[str, bool]:
        options = SUBSTITUTIONS.get(exercise_id)
        if not options or self.rng.random() >= self.SUBSTITUTION_PROBABILITY:
            return exercise_id, False
        return str(self.rng.choice(options)), True

    def plan_day(
        self,
        day_index: int,
        *,
        is_deload: bool = False,
        volume_multiplier: float = 1.0,
        rir_offset: float = 0.0,
        force_rest: bool = False,
        _session_type_override: "SessionType | None" = None,
    ) -> SessionPlan | None:
        """Plan one day. Returns ``None`` on a rest day or a missed session.

        The scenario engine drives blocks through ``volume_multiplier`` and
        ``rir_offset`` rather than through separate code paths, so a scenario
        day and an ordinary day are generated by identical logic.
        """
        session_type = _session_type_override or WEEKLY_TEMPLATE[
            day_index % len(WEEKLY_TEMPLATE)
        ]
        if session_type is SessionType.REST or force_rest:
            return None
        if _session_type_override is None and self.rng.random() < self.MISS_PROBABILITY:
            return None

        multiplier = volume_multiplier
        rir_add = rir_offset
        if is_deload:
            multiplier *= self.DELOAD_VOLUME_FRACTION
            rir_add += self.DELOAD_RIR_ADDITION

        prescriptions: list[Prescription] = []
        substituted = False
        for exercise_id, sets, rep_low, rep_high, target_rir in SESSION_TEMPLATES[session_type]:
            chosen, was_substituted = self._substitute(exercise_id)
            substituted |= was_substituted

            planned_sets = int(round(sets * multiplier))
            if is_deload:
                # A deload cuts volume but keeps at least one exposure, so
                # intensity is retained as DATA.md S3 requires.
                planned_sets = max(1, planned_sets)
            if planned_sets < 1:
                continue

            prescriptions.append(
                Prescription(
                    exercise_id=chosen,
                    sets=planned_sets,
                    rep_low=rep_low,
                    rep_high=rep_high,
                    target_rir=max(0.0, target_rir + rir_add),
                )
            )

        if not prescriptions:
            return None

        return SessionPlan(
            day_index=day_index,
            session_type=session_type,
            prescriptions=tuple(prescriptions),
            is_deload=is_deload,
            notes_code="substitution" if substituted else None,
        )

    def is_deload_week(self, day_index: int) -> bool:
        week = day_index // 7
        return week > 0 and week % self.DELOAD_PERIOD_WEEKS == 0

    def plan_days(self, n_days: int) -> list[SessionPlan]:
        """Plan a run of consecutive days.

        Rest days are skipped, and a missed session is usually rescheduled onto
        the next rest day rather than lost.
        """
        plans: list[SessionPlan] = []
        # A queue, not a single slot: the week has two rest days, and holding
        # only one pending session silently loses the second miss of a week.
        pending: list[SessionType] = []

        lifting_slots = [
            i for i, t in enumerate(WEEKLY_TEMPLATE) if t is not SessionType.REST
        ]

        for day_index in range(n_days):
            slot = day_index % len(WEEKLY_TEMPLATE)
            scheduled = WEEKLY_TEMPLATE[slot]
            week = day_index // len(WEEKLY_TEMPLATE)
            is_deload = self.is_deload_week(day_index)

            # Planned light week: one session off, chosen as the one whose
            # region is currently ahead. Rotating blindly through the slots
            # would be region-neutral only on average, and DATA.md §3.2 asks
            # for parity in *every* four-week block, not on average.
            if week % self.LIGHT_WEEK_PERIOD == self.LIGHT_WEEK_PERIOD - 1:
                if slot == self._slot_to_omit(day_index, lifting_slots):
                    continue

            if scheduled is SessionType.REST:
                if pending:
                    make_up = pending.pop(0)
                    plan = self._plan_session(day_index, make_up, is_deload)
                    if plan is not None:
                        self._record(day_index, make_up)
                        plans.append(
                            SessionPlan(
                                day_index=plan.day_index,
                                session_type=plan.session_type,
                                prescriptions=plan.prescriptions,
                                is_deload=plan.is_deload,
                                notes_code="rescheduled",
                            )
                        )
                continue

            if self.rng.random() < self._miss_probability(day_index, scheduled):
                if len(pending) < 2 and self.rng.random() < self.MAKEUP_PROBABILITY:
                    pending.append(scheduled)
                continue

            plan = self._plan_session(day_index, scheduled, is_deload)
            if plan is not None:
                plans.append(plan)
                self._record(day_index, scheduled)

        return plans

    def _plan_session(
        self, day_index: int, session_type: SessionType, is_deload: bool
    ) -> SessionPlan | None:
        """Build one session of a given type, bypassing the schedule."""
        return self.plan_day(
            day_index, is_deload=is_deload, _session_type_override=session_type
        )
