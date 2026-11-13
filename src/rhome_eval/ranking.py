"""Ranking tests (``DATA.md`` §19.3).

Six orderings the engine must get right. They are qualitative, and that is the
point: a user does not check a correlation, but they will notice if the model
says an arm session cost them more systemically than a heavy squat day.

Each case is a **matched pair** — two constructed sessions differing in exactly
one thing — pushed through the engine and, separately, through the simulator's
own physiology. Reporting both orderings is what makes this an evaluation
rather than a restatement of the engine's own dose table:

* if the engine ranks the pair correctly and the simulator agrees, the ordering
  is a property of both models and the engine has it right;
* if they disagree, the engine's ordering is wrong about the world this project
  has chosen to model, and the margin says by how much;
* if the *simulator* does not produce the ordering either, the specification is
  asking for something neither model does, which is a finding about the
  specification.

The third case is the one a test comparing the engine against its own
assumptions would never surface.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from rhome_core.exercises import Exercise, ExerciseLibrary, load_library
from rhome_core.intensity import relative_intensity
from rhome_core.muscles import Muscle
from rhome_engine.dose import LoggedSet, amplify_within_session_fatigue, transform_set
from rhome_engine.state import StateEngine

__all__ = [
    "SessionSpec", "RankingCase", "RankingResult", "CASES", "run_rankings",
    "BASELINE_NAME",
]

LIBRARY: ExerciseLibrary = load_library()


@dataclass(frozen=True)
class SessionSpec:
    """A session described the way a programme would describe it."""

    label: str
    sets: tuple[tuple[str, int, int, float], ...]  # exercise_id, sets, reps, rir

    def logged(self) -> list[LoggedSet]:
        out: list[LoggedSet] = []
        number = 0
        for exercise_id, count, reps, rir in self.sets:
            for _ in range(count):
                number += 1
                out.append(
                    LoggedSet(
                        "cmp", exercise_id, number, "working",
                        load_kg=100.0, reps=reps, rir=rir,
                    )
                )
        return out

    @property
    def total_sets(self) -> int:
        return sum(count for _, count, _, _ in self.sets)


@dataclass(frozen=True)
class RankingCase:
    """One ordering §19.3 requires, as a matched pair."""

    name: str
    requirement: str
    higher: SessionSpec
    lower: SessionSpec
    channel: str
    #: Restrict a local-fatigue comparison to these muscles, where the case is
    #: about a specific region rather than the whole body.
    muscles: tuple[Muscle, ...] = ()
    #: True where the pair is matched on set count, so the ordering cannot be
    #: explained by volume alone.
    volume_matched: bool = False


@dataclass(frozen=True)
class RankingResult:
    """What the engine said, and what the simulator's physiology said."""

    case: RankingCase
    engine_higher: float
    engine_lower: float
    truth_higher: float
    truth_lower: float
    #: The trivial competitor (D23): sets counted, weighted only by the
    #: library's authored column for this channel.
    baseline_higher: float = 0.0
    baseline_lower: float = 0.0

    @property
    def engine_margin(self) -> float:
        return self.engine_higher / max(self.engine_lower, 1e-12) - 1.0

    @property
    def truth_margin(self) -> float:
        return self.truth_higher / max(self.truth_lower, 1e-12) - 1.0

    @property
    def engine_correct(self) -> bool:
        return self.engine_higher > self.engine_lower

    @property
    def truth_correct(self) -> bool:
        return self.truth_higher > self.truth_lower

    @property
    def baseline_correct(self) -> bool | None:
        """Whether counting sets alone gets this ordering right.

        ``None`` where the counter ties, which is the interesting answer: on a
        volume-matched pair a set counter has nothing to say, so an ordering
        the engine gets right there is one it actually earned.
        """
        if abs(self.baseline_higher - self.baseline_lower) < 1e-12:
            return None
        return self.baseline_higher > self.baseline_lower

    @property
    def earned(self) -> bool:
        """Correct, and not already free to a set counter."""
        return self.engine_correct and self.baseline_correct is not True

    @property
    def verdict(self) -> str:
        if self.engine_correct and self.truth_correct:
            return "correct"
        if not self.truth_correct:
            return "SPEC WRONG — the simulator does not produce this ordering either"
        return "ENGINE WRONG"


# --- the six cases ------------------------------------------------------------

CASES: tuple[RankingCase, ...] = (
    RankingCase(
        name="failure vs matched-volume non-failure",
        requirement="failure-heavy > matched-volume non-failure fatigue",
        higher=SessionSpec("5×5 to failure", (("back_squat", 5, 5, 0.0),)),
        lower=SessionSpec("5×5 at 3 RIR", (("back_squat", 5, 5, 3.0),)),
        channel="local_fatigue",
        muscles=(Muscle.QUADS, Muscle.GLUTES),
        volume_matched=True,
    ),
    RankingCase(
        name="high volume vs ordinary volume",
        requirement="high-volume > ordinary-volume local fatigue",
        higher=SessionSpec("10×8", (("bench_press", 10, 8, 2.0),)),
        lower=SessionSpec("4×8", (("bench_press", 4, 8, 2.0),)),
        channel="local_fatigue",
        muscles=(Muscle.CHEST,),
    ),
    RankingCase(
        name="lower-body compound vs arm isolation, systemic",
        requirement="large lower-body compound session > arm-isolation session",
        higher=SessionSpec("5×5 squat + 4×8 RDL",
                           (("back_squat", 5, 5, 1.0), ("romanian_deadlift", 4, 8, 2.0))),
        lower=SessionSpec("5×10 curls + 4×12 pressdowns",
                          (("db_curl", 5, 10, 1.0), ("triceps_pressdown", 4, 12, 1.0))),
        channel="systemic",
    ),
    RankingCase(
        name="heavy compound vs isolation, neuromuscular",
        requirement="heavy low-rep compounds > isolation work for neuromuscular strain",
        higher=SessionSpec("5×3 deadlift", (("deadlift", 5, 3, 1.0),)),
        lower=SessionSpec("5×3 lateral raise", (("lateral_raise", 5, 3, 1.0),)),
        channel="neuromuscular",
        volume_matched=True,
    ),
    RankingCase(
        name="deload week vs accumulation week",
        requirement="deload week < accumulation week for acute fatigue",
        higher=SessionSpec("accumulation: 6×8 at 1 RIR",
                           (("back_squat", 3, 8, 1.0), ("leg_press", 3, 8, 1.0))),
        lower=SessionSpec("deload: 3×5 at 4 RIR",
                          (("back_squat", 2, 5, 4.0), ("leg_press", 1, 5, 4.0))),
        channel="local_fatigue",
        muscles=(Muscle.QUADS, Muscle.GLUTES),
    ),
)


# --- evaluation ---------------------------------------------------------------

def _engine_dose(spec: SessionSpec, channel: str, muscles: Sequence[Muscle]) -> float:
    """What the engine's dose model says this session deposits."""
    total = 0.0
    state = StateEngine()
    local_positions: dict[Muscle, int] = defaultdict(int)
    for index, logged in enumerate(spec.logged()):
        exercise = LIBRARY[logged.exercise_id]
        raw = transform_set(
            logged, exercise, novelty=state.novelty_for(logged.exercise_id)
        )
        dose = amplify_within_session_fatigue(raw, local_positions)
        if channel == "local_fatigue":
            selected = muscles or tuple(dose.local_fatigue)
            total += sum(dose.local_fatigue.get(m, 0.0) for m in selected)
        else:
            total += getattr(dose, channel)
        state.apply_dose(dose, index * 0.02, logged.exercise_id)
        for muscle in dose.local_fatigue:
            local_positions[muscle] += 1
    return total


#: What the trivial competitor is, in words, for reports that print it.
BASELINE_NAME = "sets x authored channel weight"


def _baseline_dose(spec: SessionSpec, channel: str, muscles: Sequence[Muscle]) -> float:
    """Sets counted, weighted only by what the library already declares (D23).

    The competitor gets the authored structure: ``c^F`` for local fatigue,
    compoundness for neuromuscular strain, systemic cost for systemic. It does
    not get anything the engine works out — no proximity to failure, no
    repetition modulation, no relative intensity, no novelty, no within-session
    amplification. Those are the engine's claim, so they are what it has to
    earn the ordering with.
    """
    total = 0.0
    for logged in spec.logged():
        exercise = LIBRARY[logged.exercise_id]
        if channel == "local_fatigue":
            contributions = exercise.fatigue_contributions
            selected = muscles or tuple(contributions)
            total += sum(contributions.get(m, 0.0) for m in selected)
        elif channel == "neuromuscular":
            total += exercise.compoundness
        else:
            total += exercise.systemic_cost
    return total


def _truth_dose(spec: SessionSpec, channel: str, muscles: Sequence[Muscle]) -> float:
    """What the simulator's physiology says, run over the same session.

    The simulator is structurally richer — state-dependent accumulation, a
    volume-by-failure interaction, a two-component split — so this is not the
    engine's arithmetic repeated.
    """
    from rhome_sim.athlete import sample_athlete  # noqa: PLC0415
    from rhome_sim.physiology import Physiology  # noqa: PLC0415

    athlete = sample_athlete(20260822)
    physiology = Physiology(athlete)
    physiology.begin_session()

    total = 0.0
    exposures: dict[str, int] = {}
    for logged in spec.logged():
        exercise = LIBRARY[logged.exercise_id]
        intensity, _ = relative_intensity(
            logged.reps, logged.rir, exercise.nuzzo_curve.value
        )
        exposures[logged.exercise_id] = exposures.get(logged.exercise_id, 0) + 1
        impulse = physiology.apply_set(
            exercise, logged.reps, logged.rir, intensity,
            exposures[logged.exercise_id],
        )
        if channel == "local_fatigue":
            selected = muscles or tuple(impulse.local)
            total += sum(impulse.local.get(m, 0.0) for m in selected)
        else:
            total += getattr(impulse, channel)
    return total


def run_rankings(cases: Sequence[RankingCase] = CASES) -> tuple[RankingResult, ...]:
    return tuple(
        RankingResult(
            case=case,
            engine_higher=_engine_dose(case.higher, case.channel, case.muscles),
            engine_lower=_engine_dose(case.lower, case.channel, case.muscles),
            truth_higher=_truth_dose(case.higher, case.channel, case.muscles),
            truth_lower=_truth_dose(case.lower, case.channel, case.muscles),
            baseline_higher=_baseline_dose(case.higher, case.channel, case.muscles),
            baseline_lower=_baseline_dose(case.lower, case.channel, case.muscles),
        )
        for case in cases
    )


# --- the sixth case, which is not a dose comparison ---------------------------

@dataclass(frozen=True)
class DeloadResponse:
    """Expected performance either side of a deload (``DATA.md`` §19.3, last case).

    Unlike the five above this cannot be constructed from a matched pair,
    because it is a claim about a *state* reached by a history rather than
    about a session's dose. It is measured from the run: projected performance
    on the last training day before each deload, against the first after it.

    Constructing it instead would be circular — suppression is monotone in
    fatigue by definition, so a hand-built low-fatigue state would out-project
    a high-fatigue one whatever the engine did.
    """

    episodes: int
    engine_gain: float | None
    truth_gain: float | None
    engine_agreements: int
    #: The trivial competitor (D23): the fractional fall in a decaying set
    #: counter across the same boundary. Anything that decays predicts a
    #: rebound after a week of reduced volume, so this ordering is expected to
    #: be free — and D20 says a score is not a result until that is shown
    #: rather than assumed.
    baseline_gain: float | None = None

    @property
    def engine_correct(self) -> bool | None:
        return None if self.engine_gain is None else self.engine_gain > 0

    @property
    def truth_correct(self) -> bool | None:
        return None if self.truth_gain is None else self.truth_gain > 0

    @property
    def baseline_correct(self) -> bool | None:
        return None if self.baseline_gain is None else self.baseline_gain > 0

    @property
    def earned(self) -> bool:
        """Correct, and not already free to a decaying counter."""
        return self.engine_correct is True and self.baseline_correct is not True


def deload_response(run, label: str = "S3_deload") -> DeloadResponse:
    """Projected and true performance across each deload boundary."""
    import statistics as st  # noqa: PLC0415

    labelled = run.truth.scenario_labels
    days = [r.day_index for r in run.results]
    in_deload = {d: label in labelled.get(d, ()) for d in days}

    # An episode is a contiguous run of deload days. The comparison §19.3 asks
    # for is the *fatigued* state before it against the *fresh* state after —
    # so "before" must be the last session preceding the episode's start, not
    # the last session inside it. Taking it from inside compared the end of a
    # deload against the start of the next block, which is not the claim.
    episodes: list[tuple[int, int]] = []
    start: int | None = None
    for day in days:
        if in_deload.get(day) and start is None:
            start = day
        elif not in_deload.get(day) and start is not None:
            episodes.append((start, day))
            start = None

    engine_gains: list[float] = []
    truth_gains: list[float] = []
    baseline_gains: list[float] = []
    agreements = 0
    by_day = {r.day_index: r for r in run.results}
    truth_capacity = run.truth.expressible

    # The trivial competitor, on the same boundaries: a decaying count of
    # working sets, which knows nothing except that training happened.
    from rhome_eval.state_baselines import decaying_count  # noqa: PLC0415

    counter_by_day = dict(
        zip(
            days,
            decaying_count(
                [
                    sum(
                        1
                        for logged, _dose in by_day[d].doses
                        if logged.set_type in ("working", "backoff")
                    )
                    for d in days
                ]
            ),
        )
    )

    for episode_start, episode_end in episodes:
        before = _projections_in(
            by_day, range(episode_start - 12, episode_start), keep="last"
        )
        after = _projections_in(by_day, range(episode_end, episode_end + 12), keep="first")
        shared = [
            exercise_id for exercise_id in before.keys() & after.keys()
            if before[exercise_id][1] in truth_capacity.get(exercise_id, {})
            and after[exercise_id][1] in truth_capacity.get(exercise_id, {})
        ]
        for exercise_id in shared:
            before_value, before_day = before[exercise_id]
            after_value, after_day = after[exercise_id]
            truth = truth_capacity[exercise_id]
            engine_gain = after_value / before_value - 1
            truth_gain = truth[after_day] / truth[before_day] - 1
            engine_gains.append(engine_gain)
            truth_gains.append(truth_gain)
            agreements += (engine_gain > 0) == (truth_gain > 0)
            counter_before = counter_by_day.get(before_day)
            counter_after = counter_by_day.get(after_day)
            if counter_before:
                baseline_gains.append(counter_before / max(counter_after, 1e-12) - 1.0)

    return DeloadResponse(
        episodes=len(engine_gains),
        engine_gain=st.fmean(engine_gains) if engine_gains else None,
        truth_gain=st.fmean(truth_gains) if truth_gains else None,
        engine_agreements=agreements,
        baseline_gain=st.fmean(baseline_gains) if baseline_gains else None,
    )


def _projections_in(
    by_day, window, keep: str = "last"
) -> dict[str, tuple[float, int]]:
    """The first or last projection for each exercise inside a window."""
    out: dict[str, tuple[float, int]] = {}
    for day in window:
        result = by_day.get(day)
        if result is None:
            continue
        for exercise_id, record in result.projections.items():
            if keep == "first" and exercise_id in out:
                continue
            out[exercise_id] = (record.projected, day)
    return out
