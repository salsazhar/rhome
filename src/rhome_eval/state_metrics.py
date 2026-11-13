"""State reconstruction, scored (``DATA.md`` §19.1).

The section asks for five things per latent channel: correlation, RMSE after
scale normalisation, directional accuracy, peak timing after high-load
sessions, and recovery-crossing timing.

Two choices shape how they are computed here.

**Timing metrics are unit-free by construction.** A peak is an index and a
crossing is a fraction of each series' own peak, so neither needs the scale
alignment. That matters: alignment is a fitted nuisance parameter, and a metric
that avoids depending on one is a stronger metric.

**Every figure carries what a counter achieved.** D20: a decaying count of
working sets reaches +0.911 on aggregate local fatigue, so a correlation
reported alone says almost nothing about whether the model's structure earned
its place. Where a baseline cannot be constructed — the timing metrics, which a
single global accumulator can attempt but not attribute — that is said rather
than left as an absence.
"""

from __future__ import annotations

import statistics as st
from dataclasses import dataclass, field
from typing import Sequence

from rhome_core.muscles import Muscle
from rhome_eval import metrics as m
from rhome_eval.run import CHANNELS, EvaluationRun
from rhome_eval.state_baselines import MUSCLE_BASELINES, decaying_count

__all__ = [
    "ChannelScore",
    "MuscleScore",
    "CrossSectionalScore",
    "TimingScore",
    "StateReport",
    "score_states",
]

#: Fraction of a session's own peak at which recovery is called (``DATA.md``
#: §19.1, recovery-crossing timing). Half is chosen because it is the one
#: threshold that needs no justification beyond the half-life it mirrors.
CROSSING_FRACTION = 0.5

#: How many days after a session the peak and crossing are looked for.
TIMING_WINDOW_DAYS = 6


@dataclass(frozen=True)
class ChannelScore:
    """One aggregate channel against latent truth."""

    channel: str
    pearson: float | None
    spearman: float | None
    rmse: float | None
    directional_accuracy: float | None
    baseline_pearson: float | None
    baseline_name: str

    @property
    def advantage(self) -> float | None:
        if self.pearson is None or self.baseline_pearson is None:
            return None
        return self.pearson - self.baseline_pearson


@dataclass(frozen=True)
class MuscleScore:
    """One model muscle group. No alignment: correlation needs no scale."""

    muscle: Muscle
    pearson: float | None
    spearman: float | None
    directional_accuracy: float | None
    #: The single unattributed accumulator, kept for continuity with L3.1.
    baseline_pearson: float | None
    #: Counters that share the authored muscle map (D23), by name. These are
    #: the honest competitors for a per-muscle claim; the one above is not.
    attributed_baselines: dict = field(default_factory=dict)

    @property
    def best_attributed(self) -> tuple[str, float] | None:
        scored = {k: v for k, v in self.attributed_baselines.items() if v is not None}
        if not scored:
            return None
        name = max(scored, key=lambda k: scored[k])
        return name, scored[name]

    @property
    def attributed_advantage(self) -> float | None:
        best = self.best_attributed
        return None if best is None or self.pearson is None else self.pearson - best[1]


@dataclass(frozen=True)
class CrossSectionalScore:
    """Agreement *between muscles within a day*, day means removed.

    The longitudinal figure is dominated by "did you train recently", which is
    common to every muscle and therefore free. This asks the question the body
    map actually makes: on a given day, does the engine put the muscles in the
    right order? 74% of the true latent variance lives here.

    It was reported at +0.941 in the L3.15 diagnostic and in three build-log
    entries before any code computed it. This is that code.
    """

    name: str
    pooled: float | None
    per_day_mean: float | None
    days: int


@dataclass(frozen=True)
class TimingScore:
    """When the engine thinks a spike peaked and cleared, against when it did."""

    channel: str
    sessions: int
    peak_errors: tuple[int, ...] = ()
    crossing_errors: tuple[int, ...] = ()
    #: The same errors for the decaying set counter. It has a series, so it can
    #: attempt timing even though it cannot attribute — and D20 says a score
    #: without its trivial competitor beside it is not yet a result.
    baseline_peak_errors: tuple[int, ...] = ()
    #: The same errors for a counter given the library's authored column for
    #: this channel (D23). Neuromuscular timing was the last claim expected to
    #: survive the re-audit; this is the measurement that decided it.
    authored_peak_errors: tuple[int, ...] = ()

    @property
    def peak_within_a_day(self) -> float | None:
        if not self.peak_errors:
            return None
        return sum(1 for e in self.peak_errors if abs(e) <= 1) / len(self.peak_errors)

    @property
    def median_peak_error(self) -> float | None:
        return st.median(self.peak_errors) if self.peak_errors else None

    @property
    def median_crossing_error(self) -> float | None:
        return st.median(self.crossing_errors) if self.crossing_errors else None

    @property
    def baseline_peak_within_a_day(self) -> float | None:
        if not self.baseline_peak_errors:
            return None
        return sum(1 for e in self.baseline_peak_errors if abs(e) <= 1) / len(
            self.baseline_peak_errors
        )

    @property
    def authored_peak_within_a_day(self) -> float | None:
        if not self.authored_peak_errors:
            return None
        return sum(1 for e in self.authored_peak_errors if abs(e) <= 1) / len(
            self.authored_peak_errors
        )


@dataclass(frozen=True)
class StateReport:
    """Everything §19.1 asks for, in one object."""

    channels: tuple[ChannelScore, ...] = ()
    muscles: tuple[MuscleScore, ...] = ()
    cross_sectional: tuple[CrossSectionalScore, ...] = ()
    timing: tuple[TimingScore, ...] = ()
    rho_clipped_fraction: float = 0.0
    rho_longest_clipped_run: int = 0
    caveat: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def muscle_mean(self) -> float | None:
        scored = [s.pearson for s in self.muscles if s.pearson is not None]
        return st.fmean(scored) if scored else None

    @property
    def muscle_baseline_mean(self) -> float | None:
        scored = [s.baseline_pearson for s in self.muscles if s.baseline_pearson is not None]
        return st.fmean(scored) if scored else None

    @property
    def muscle_attributed_baseline_mean(self) -> float | None:
        """What the best map-sharing counter averaged across the muscles."""
        best = [
            s.best_attributed[1] for s in self.muscles if s.best_attributed is not None
        ]
        return st.fmean(best) if best else None

    @property
    def engine_cross_sectional(self) -> CrossSectionalScore | None:
        return next((c for c in self.cross_sectional if c.name == "engine"), None)

    @property
    def worst_muscle(self) -> MuscleScore | None:
        scored = [s for s in self.muscles if s.pearson is not None]
        return min(scored, key=lambda s: s.pearson) if scored else None


# --- timing ------------------------------------------------------------------

def _high_load_days(days: Sequence, quantile: float = 0.75) -> list[int]:
    """Indices of the heaviest sessions, by working-set count.

    Chosen from the *observable* log rather than from latent load, so which
    sessions count as heavy is not itself a judgement made with the answers in
    hand.
    """
    counts = [
        sum(1 for s in getattr(d, "sets", ()) if getattr(s, "set_type", None)
            in ("working", "backoff"))
        for d in days
    ]
    trained = [c for c in counts if c > 0]
    if len(trained) < 8:
        return []
    threshold = sorted(trained)[int(len(trained) * quantile)]
    return [i for i, c in enumerate(counts) if c >= threshold]


def _peak_and_crossing(series: Sequence[float], start: int) -> tuple[int, int | None] | None:
    window = list(series[start : start + TIMING_WINDOW_DAYS])
    if len(window) < 3:
        return None
    peak_index = window.index(max(window))
    peak_value = window[peak_index]
    if peak_value <= 0:
        return None
    crossing = None
    for offset in range(peak_index + 1, len(window)):
        if window[offset] < peak_value * CROSSING_FRACTION:
            crossing = offset
            break
    return peak_index, crossing


def _timing(
    channel: str,
    engine: Sequence[float],
    truth: Sequence[float],
    days: Sequence,
    baseline: Sequence[float] = (),
    authored: Sequence[float] = (),
) -> TimingScore:
    peaks: list[int] = []
    crossings: list[int] = []
    baseline_peaks: list[int] = []
    authored_peaks: list[int] = []
    sessions = 0
    for start in _high_load_days(days):
        if start + TIMING_WINDOW_DAYS > len(engine):
            continue
        left = _peak_and_crossing(engine, start)
        right = _peak_and_crossing(truth, start)
        if left is None or right is None:
            continue
        sessions += 1
        peaks.append(left[0] - right[0])
        if left[1] is not None and right[1] is not None:
            crossings.append(left[1] - right[1])
        if baseline and start + TIMING_WINDOW_DAYS <= len(baseline):
            counted = _peak_and_crossing(baseline, start)
            if counted is not None:
                baseline_peaks.append(counted[0] - right[0])
        if authored and start + TIMING_WINDOW_DAYS <= len(authored):
            counted = _peak_and_crossing(authored, start)
            if counted is not None:
                authored_peaks.append(counted[0] - right[0])
    return TimingScore(
        channel, sessions, tuple(peaks), tuple(crossings), tuple(baseline_peaks),
        tuple(authored_peaks),
    )


# --- the report ---------------------------------------------------------------

# --- cross-sectional: between muscles, within a day --------------------------

def _muscle_baseline_series(run, window_days) -> dict:
    """Each attributed counter's per-muscle series, trimmed to pair with truth."""
    from rhome_eval.run import LATENT_OFFSET_DAYS  # noqa: PLC0415

    out: dict = {}
    for baseline in MUSCLE_BASELINES:
        series = baseline.series(window_days, run.library)
        out[baseline.name] = {
            muscle: values[: len(values) - LATENT_OFFSET_DAYS] if LATENT_OFFSET_DAYS else values
            for muscle, values in series.items()
        }
    return out


def _cross_sectional(name: str, estimated: dict, truth: dict) -> CrossSectionalScore:
    """Correlate day-centred vectors across muscles.

    Both sides have their day mean removed, so what remains is purely the
    ordering between muscles. Reported two ways because they answer slightly
    different questions: pooled treats every muscle-day as one observation,
    the per-day mean weights every day equally regardless of how much contrast
    it happened to contain.
    """
    muscles = list(Muscle)
    length = min(len(estimated[m]) for m in muscles)
    length = min(length, min(len(truth[m]) for m in muscles))

    pooled_left: list[float] = []
    pooled_right: list[float] = []
    per_day: list[float] = []

    for index in range(length):
        left = [estimated[m][index] for m in muscles]
        right = [truth[m][index] for m in muscles]
        mean_left, mean_right = st.fmean(left), st.fmean(right)
        centred_left = [v - mean_left for v in left]
        centred_right = [v - mean_right for v in right]
        pooled_left.extend(centred_left)
        pooled_right.extend(centred_right)
        day_r = m.pearson(centred_left, centred_right)
        if day_r is not None:
            per_day.append(day_r)

    return CrossSectionalScore(
        name=name,
        pooled=m.pearson(pooled_left, pooled_right),
        per_day_mean=st.fmean(per_day) if per_day else None,
        days=length,
    )


def _authored_channel_counters(run, window_days) -> dict:
    """A decaying counter per channel, weighted by what the library declares.

    ``c^F`` totals for local fatigue, compoundness times squared relative
    intensity for neuromuscular strain, systemic cost for systemic. None of it
    is inferred: the Nuzzo relative-intensity curve is a published population
    relationship and turning logged repetitions and RIR into an intensity
    through it is a lookup, so D23's tie-break gives it to the competitor.
    """
    from rhome_core.intensity import relative_intensity  # noqa: PLC0415
    from rhome_eval.run import LATENT_OFFSET_DAYS  # noqa: PLC0415

    library = run.library

    def weights(performed, exercise) -> dict[str, float]:
        intensity, _ = relative_intensity(
            performed.reps,
            performed.rir if performed.rir is not None else 2.0,
            exercise.nuzzo_curve.value,
        )
        return {
            "local_fatigue": sum(exercise.fatigue_contributions.values()),
            "neuromuscular": exercise.compoundness * intensity ** 2,
            "systemic": exercise.systemic_cost,
        }

    per_day: dict[str, list[float]] = {c: [] for c in CHANNELS}
    for day in window_days:
        totals = {c: 0.0 for c in CHANNELS}
        for performed in getattr(day, "sets", ()):
            if getattr(performed, "set_type", None) not in ("working", "backoff"):
                continue
            exercise = library.exercises.get(getattr(performed, "exercise_id", None))
            if exercise is None:
                continue
            for channel, value in weights(performed, exercise).items():
                totals[channel] += value
        for channel in CHANNELS:
            per_day[channel].append(totals[channel])

    from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: PLC0415

    half_lives = {
        "local_fatigue": ENGINE_PARAMETERS.value("local_half_life_h"),
        "neuromuscular": ENGINE_PARAMETERS.value("neuromuscular_half_life_h"),
        "systemic": ENGINE_PARAMETERS.value("systemic_half_life_h"),
    }
    out = {}
    for channel in CHANNELS:
        series = decaying_count(per_day[channel], half_lives[channel])
        out[channel] = (
            series[: len(series) - LATENT_OFFSET_DAYS] if LATENT_OFFSET_DAYS else series
        )
    return out


def score_states(run: EvaluationRun, days: Sequence) -> StateReport:
    """Score one run's state reconstruction against latent truth."""
    if run.truth is None or run.alignment is None:
        raise ValueError("this run has no truth attached; call attach_truth first")

    window_days = [d for d in days if d.day_index in run.window.days]
    counter = decaying_count([
        sum(1 for s in d.sets if s.set_type in ("working", "backoff"))
        for d in window_days
    ])
    paired_counter = counter[: len(counter) - 1]

    channels = tuple(
        ChannelScore(
            channel=channel,
            pearson=m.pearson(run.aligned(channel), run.truth.channel(channel)),
            spearman=m.spearman(run.aligned(channel), run.truth.channel(channel)),
            rmse=m.rmse(run.aligned(channel), run.truth.channel(channel)),
            directional_accuracy=m.directional_accuracy(
                run.aligned(channel), run.truth.channel(channel)
            ),
            baseline_pearson=m.pearson(paired_counter, run.truth.channel(channel)),
            baseline_name="working sets, 30 h",
        )
        for channel in CHANNELS
    )

    attributed = _muscle_baseline_series(run, window_days)

    muscles = tuple(
        MuscleScore(
            muscle=muscle,
            pearson=m.pearson(run.estimated_muscle(muscle), run.truth.muscle(muscle)),
            spearman=m.spearman(run.estimated_muscle(muscle), run.truth.muscle(muscle)),
            directional_accuracy=m.directional_accuracy(
                run.estimated_muscle(muscle), run.truth.muscle(muscle)
            ),
            baseline_pearson=m.pearson(paired_counter, run.truth.muscle(muscle)),
            attributed_baselines={
                name: m.pearson(series[muscle], run.truth.muscle(muscle))
                for name, series in attributed.items()
            },
        )
        for muscle in Muscle
    )

    truth_by_muscle = {muscle: run.truth.muscle(muscle) for muscle in Muscle}
    cross_sectional = (
        _cross_sectional(
            "engine",
            {muscle: run.estimated_muscle(muscle) for muscle in Muscle},
            truth_by_muscle,
        ),
        *(
            _cross_sectional(name, series, truth_by_muscle)
            for name, series in attributed.items()
        ),
    )

    authored_channels = _authored_channel_counters(run, window_days)
    timing = tuple(
        _timing(
            channel, run.aligned(channel), run.truth.channel(channel),
            window_days, paired_counter, authored_channels.get(channel, ()),
        )
        for channel in CHANNELS
    )

    # Checkpoint 2 left the recovery multiplier's clipping as an open item.
    from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: PLC0415

    floor = ENGINE_PARAMETERS.value("rho_floor")
    ceiling = ENGINE_PARAMETERS.value("rho_ceiling")
    rhos = [r.recovery.rho for r in run.results]
    clipped = [abs(v - floor) < 1e-9 or abs(v - ceiling) < 1e-9 for v in rhos]
    longest = current = 0
    for is_clipped in clipped:
        current = current + 1 if is_clipped else 0
        longest = max(longest, current)

    return StateReport(
        channels=channels,
        muscles=muscles,
        cross_sectional=cross_sectional,
        timing=timing,
        rho_clipped_fraction=sum(clipped) / len(clipped),
        rho_longest_clipped_run=longest,
        caveat=run.caveat,
        notes=(
            "Timing metrics are unit-free and use no scale alignment.",
            "The 'counter' column is a single accumulator counting working "
            "sets, decaying at 30 h. It cannot attribute, so its per-muscle "
            "score is the same series compared against each -- which makes it "
            "the wrong competitor for a per-muscle claim, and it is kept only "
            "for continuity with L3.1.",
            "The attributed counters share the library's authored muscle map "
            "and nothing else: no repetitions, effort, novelty, wearables or "
            "recovery multiplier. D23 -- a trivial competitor gets every "
            "structure the engine is not claiming credit for.",
        ),
    )
