"""Calibration bands (``DATA.md`` §19.4).

Six states, each evaluated 24 hours after the most recent session. DATA.md
v0.9.0 and D21 option 2 define simulator-centred Grade-C reference bands: the
original bands were calibrated to the linear engine and the simulator itself
missed four of six. The engine and simulator are both reported; the repaired
engine is not fitted away when it remains below the simulator reference.

Both sides are computed, because they are structurally different and the
section says the bands are "checked against the simulator's own suppression":

* engine — :math:`1 - e^{-b}`, with a numerical-stability clip;
* simulator — :math:`b / (1 + b)`, unclipped;

with different λ values behind each. Agreement between them is therefore
evidence, not arithmetic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from rhome_core.exercises import Exercise, load_library
from rhome_core.intensity import relative_intensity
from rhome_core.muscles import Muscle
from rhome_core.timeline import RecoveryTimeline, RecoveryWindow
from rhome_engine.dose import LoggedSet, amplify_within_session_fatigue, transform_set
from rhome_engine.performance import expected_suppression
from rhome_engine.state import StateEngine

__all__ = [
    "Protocol", "CalibrationCase", "CalibrationResult", "CASES", "run_calibration",
    "counter_suppression", "fit_counter_scale", "BASELINE_NAME",
]

LIBRARY = load_library()

#: The exercises the bands are read on. ``DATA.md`` §19.4 expects upper-body
#: suppression to run about a percentage point below lower-body for an
#: equivalent session, and calls that a correct prediction rather than an
#: error, so both are reported.
LOWER = LIBRARY["back_squat"]
UPPER = LIBRARY["bench_press"]

#: Every band in §19.4 is read 24 hours after the most recent session, so the
#: ages below already encode it: an event at age 24 *is* the session a day
#: before the reading. A first version advanced a further 24 hours past the
#: last event, decaying every state twice and reporting the engine at roughly
#: 60% of its calibrated suppression.
READ_AFTER_H = 24.0


#: A session as the bands were originally calibrated: a whole training day,
#: not a few sets of one lift. ``DATA.md`` §19.4 says "one ordinary hard
#: session for that muscle", and an ordinary hard lower-body session is a leg
#: day. Reading the bands against four sets of squats — which is what a first
#: version of this module did — measures a quarter of the dose and reports the
#: engine as half-calibrated when it is nothing of the kind.
LOWER_ORDINARY = (
    ("back_squat", 4, 5, 2.0), ("romanian_deadlift", 3, 8, 2.0),
    ("leg_press", 3, 10, 1.0), ("leg_curl", 3, 12, 1.0), ("calf_raise", 4, 12, 0.0),
)
LOWER_FAILURE = tuple((e, n, r, 0.0) for e, n, r, _ in LOWER_ORDINARY)
LOWER_HIGH_VOLUME = (
    ("back_squat", 5, 6, 1.0), ("romanian_deadlift", 4, 8, 1.0),
    ("leg_press", 4, 10, 1.0), ("leg_curl", 4, 12, 1.0), ("calf_raise", 4, 12, 0.0),
)
LOWER_LIGHT = (
    ("back_squat", 2, 5, 4.0), ("leg_press", 2, 10, 4.0), ("leg_curl", 2, 12, 4.0),
)

UPPER_ORDINARY = (
    ("bench_press", 4, 6, 2.0), ("cable_row", 4, 10, 2.0),
    ("overhead_press", 3, 8, 1.0), ("lateral_raise", 4, 15, 0.0),
)
UPPER_FAILURE = tuple((e, n, r, 0.0) for e, n, r, _ in UPPER_ORDINARY)
UPPER_HIGH_VOLUME = (
    ("bench_press", 5, 6, 1.0), ("cable_row", 5, 10, 1.0),
    ("overhead_press", 4, 8, 1.0), ("lateral_raise", 4, 15, 0.0),
)
UPPER_LIGHT = (
    ("bench_press", 2, 6, 4.0), ("cable_row", 2, 10, 4.0),
)

Session = tuple[tuple[str, int, int, float], ...]


@dataclass(frozen=True)
class Protocol:
    """Whole sessions placed at stated ages, in hours before the reading."""

    label: str
    #: (hours before the reading, lower-body session, upper-body session)
    events: tuple[tuple[float, Session, Session], ...]

    @property
    def oldest_h(self) -> float:
        return max(age for age, *_ in self.events)


@dataclass(frozen=True)
class CalibrationCase:
    """One row of the §19.4 table."""

    name: str
    protocol: Protocol
    lower_bound: float
    upper_bound: float


@dataclass(frozen=True)
class CalibrationResult:
    case: CalibrationCase
    engine_lower_body: float
    engine_upper_body: float
    simulator_lower_body: float
    clip_bound: bool
    #: The trivial competitor (D23): suppression proportional to a decaying
    #: count of working sets, with a single scale fitted across all six bands.
    baseline_lower_body: float = 0.0

    @property
    def in_band(self) -> bool:
        return (
            self.case.lower_bound <= self.engine_lower_body <= self.case.upper_bound
        )

    @property
    def simulator_in_band(self) -> bool:
        return (
            self.case.lower_bound
            <= self.simulator_lower_body
            <= self.case.upper_bound
        )

    @property
    def baseline_in_band(self) -> bool:
        return (
            self.case.lower_bound <= self.baseline_lower_body <= self.case.upper_bound
        )

    @property
    def upper_body_gap(self) -> float:
        """Percentage points by which upper-body sits below lower-body."""
        return (self.engine_lower_body - self.engine_upper_body) * 100.0

    @property
    def verdict(self) -> str:
        if self.clip_bound:
            return "CLIP BOUND — a defect outside S1, S2 and the overload block"
        return "in band" if self.in_band else "OUTSIDE BAND"


CASES: tuple[CalibrationCase, ...] = (
    CalibrationCase(
        "fresh, after a deload week",
        Protocol("light sessions 96 h and 48 h ago",
                 ((96.0, LOWER_LIGHT, UPPER_LIGHT), (48.0, LOWER_LIGHT, UPPER_LIGHT))),
        0.0, 0.015,
    ),
    CalibrationCase(
        "one ordinary hard session",
        Protocol("one session 24 h ago",
                 ((24.0, LOWER_ORDINARY, UPPER_ORDINARY),)),
        0.05, 0.07,
    ),
    CalibrationCase(
        "one failure-heavy session",
        Protocol("one failure session 24 h ago",
                 ((24.0, LOWER_FAILURE, UPPER_FAILURE),)),
        0.08, 0.10,
    ),
    CalibrationCase(
        "ordinary training week, two sessions in 72 h",
        Protocol("sessions 72 h and 24 h ago",
                 ((72.0, LOWER_ORDINARY, UPPER_ORDINARY),
                  (24.0, LOWER_ORDINARY, UPPER_ORDINARY))),
        0.07, 0.09,
    ),
    CalibrationCase(
        "within a failure-heavy block",
        Protocol("failure sessions 72 h and 24 h ago",
                 ((72.0, LOWER_FAILURE, UPPER_FAILURE),
                  (24.0, LOWER_FAILURE, UPPER_FAILURE))),
        0.12, 0.14,
    ),
    CalibrationCase(
        "peak of a deliberate overload block",
        Protocol("high-volume sessions at 96, 72, 48 and 24 h",
                 tuple((age, LOWER_HIGH_VOLUME, UPPER_HIGH_VOLUME)
                       for age in (96.0, 72.0, 48.0, 24.0))),
        0.24, 0.27,
    ),
)


# --- running a protocol -------------------------------------------------------

def _engine_state(protocol: Protocol, upper: bool) -> StateEngine:
    """Run the protocol forward to the reading instant.

    Ages are hours *before* the reading, so the timeline runs from the oldest
    event to zero.
    """
    timeline = RecoveryTimeline()
    timeline.append(RecoveryWindow(0.0, 1.0))
    engine = StateEngine(timeline)
    origin = protocol.oldest_h
    for age, lower_session, upper_session in sorted(protocol.events, reverse=True):
        at_h = origin - age
        local_positions: dict[Muscle, int] = defaultdict(int)
        for index, (exercise_id, sets, reps, rir) in enumerate(
            upper_session if upper else lower_session
        ):
            exercise = LIBRARY[exercise_id]
            for repeat in range(sets):
                logged = LoggedSet("cal", exercise_id, repeat + 1, "working",
                                   load_kg=100.0, reps=reps, rir=rir)
                raw = transform_set(
                    logged, exercise,
                    novelty=engine.novelty_for(exercise_id),
                )
                dose = amplify_within_session_fatigue(raw, local_positions)
                engine.apply_dose(
                    dose,
                    at_h + index * 0.5 + repeat * 0.02, exercise_id,
                )
                for muscle in dose.local_fatigue:
                    local_positions[muscle] += 1
    engine.advance_to(origin)
    return engine


def _simulator_suppression(protocol: Protocol, exercise: Exercise, upper: bool) -> float:
    from rhome_sim.athlete import sample_athlete  # noqa: PLC0415
    from rhome_sim.performance import SIM_PERFORMANCE  # noqa: PLC0415
    from rhome_sim.physiology import Physiology  # noqa: PLC0415

    athlete = sample_athlete(20260822)
    physiology = Physiology(athlete)
    origin = protocol.oldest_h
    exposures: dict[str, int] = {}
    for age, lower_session, upper_session in sorted(protocol.events, reverse=True):
        physiology.advance_to(origin - age)
        physiology.begin_session()
        for exercise_id, sets, reps, rir in (upper_session if upper else lower_session):
            performed = LIBRARY[exercise_id]
            intensity, _ = relative_intensity(reps, rir, performed.nuzzo_curve.value)
            for _ in range(sets):
                exposures[exercise_id] = exposures.get(exercise_id, 0) + 1
                physiology.apply_set(performed, reps, rir, intensity,
                                     exposures[exercise_id])
    physiology.advance_to(origin)

    exposure = sum(
        weight * physiology.state.local_fatigue(muscle)
        for muscle, weight in exercise.performance_weights.items()
    )
    burden = (
        SIM_PERFORMANCE.lambda_local * exposure
        + SIM_PERFORMANCE.lambda_neuromuscular
        * exercise.compoundness
        * physiology.state.neuromuscular
        + SIM_PERFORMANCE.lambda_systemic * physiology.state.systemic
    )
    return 1.0 - 1.0 / (1.0 + max(0.0, burden))


# --- the trivial competitor (D23) -------------------------------------------

#: What the competitor is, in words, for reports that print it.
BASELINE_NAME = "suppression proportional to a decaying set count, one fitted scale"

#: Half-life of the counter, matching the engine's local channel so the
#: comparison is about structure rather than about a tuned time constant.
_COUNTER_HALF_LIFE_H = 30.0


def counter_suppression(protocol: Protocol, *, upper: bool = False) -> float:
    """Decayed count of working sets at the reading, before scaling.

    One state variable, one half-life, no effort, no repetitions, no
    intensity, no muscle attribution beyond which session it was. This is what
    the bands look like if fatigue is simply "how much have you done lately".
    """
    import math  # noqa: PLC0415

    total = 0.0
    for age_h, lower_session, upper_session in protocol.events:
        session = upper_session if upper else lower_session
        sets = sum(count for _, count, _, _ in session)
        total += sets * math.exp(-math.log(2.0) / _COUNTER_HALF_LIFE_H * age_h)
    return total


def fit_counter_scale(cases: Sequence[CalibrationCase]) -> float:
    """One free parameter, least-squares onto the band midpoints.

    Deliberately generous: the competitor is allowed to be calibrated, because
    the question D23 asks is whether the engine's *structure* earns anything,
    not whether a counter happens to come out in the right units.
    """
    numerator = denominator = 0.0
    for case in cases:
        midpoint = (case.lower_bound + case.upper_bound) / 2.0
        counted = counter_suppression(case.protocol)
        numerator += counted * midpoint
        denominator += counted * counted
    return numerator / denominator if denominator else 0.0


def run_calibration(cases: Sequence[CalibrationCase] = CASES) -> tuple[CalibrationResult, ...]:
    from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: PLC0415

    clip = ENGINE_PARAMETERS.value("suppression_clip")
    scale = fit_counter_scale(cases)
    out: list[CalibrationResult] = []
    for case in cases:
        lower_state = _engine_state(case.protocol, upper=False)
        upper_state = _engine_state(case.protocol, upper=True)
        lower_value, lower_terms = expected_suppression(LOWER, lower_state.state)
        upper_value, _ = expected_suppression(UPPER, upper_state.state)
        out.append(
            CalibrationResult(
                case=case,
                engine_lower_body=lower_value,
                engine_upper_body=upper_value,
                simulator_lower_body=_simulator_suppression(
                    case.protocol, LOWER, upper=False
                ),
                clip_bound=sum(lower_terms.values()) >= clip - 1e-12,
                baseline_lower_body=scale * counter_suppression(case.protocol),
            )
        )
    return tuple(out)
