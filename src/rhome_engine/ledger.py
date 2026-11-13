"""The contribution ledger (``MODEL.tex`` §Exact contribution decomposition).

Every fatigue state in this model is a sum of exponentially decaying impulses,
which means exact attribution is available in closed form. The trace is a
decomposition, not a rationalisation written after the number was produced.

The ledger's whole job is to stay honest about that. It never integrates
:math:`\\rho` for itself and never applies a half-life of its own: it reads the
survival clock the state engine advances, so a contributor's surviving value is
computed with the identical arithmetic that produced the state. A ledger that
recomputed decay independently would agree at first and drift later, and the
drift would appear as a plausible explanation of a number it no longer matched.

Two things are easy to get wrong here and are handled explicitly.

**Background activity is a contributor.** Steps enter as a constant input rate
across the waking window rather than as an impulse, so a ledger that recorded
only sets would find its shares summing to less than one on any day the athlete
walked. Each segment's integrated increment is recorded at the segment's end,
which is exact from that instant onward.

**Old impulses are folded, not dropped.** Pruning a contributor that has
decayed to nothing would break the sum-to-one property that makes the trace
checkable. Instead its surviving mass moves into a single residual entry that
decays like any other, so the decomposition stays complete.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from rhome_core.muscles import Muscle

__all__ = ["Impulse", "Contribution", "ContributionLedger", "Channel"]

LN2 = math.log(2.0)

#: Impulses older than this many half-lives are folded into the residual
#: entry. At twenty half-lives a contributor retains under one part in a
#: million, which is far below the precision of anything displayed.
FOLD_AFTER_HALF_LIVES = 20.0


class Channel:
    """The decomposable state channels."""

    LOCAL_FATIGUE = "local_fatigue"
    NEUROMUSCULAR = "neuromuscular"
    SYSTEMIC = "systemic"
    ADAPTATION = "adaptation"

    #: Channels whose decay is modulated by the recovery context. Adaptation is
    #: not: a good night's sleep does not accelerate a training adaptation.
    RHO_MODULATED = frozenset({LOCAL_FATIGUE, NEUROMUSCULAR, SYSTEMIC})


@dataclass
class Impulse:
    """One deposit into one channel, as recorded at the moment it happened."""

    source: str
    label: str
    channel: str
    subject: str
    magnitude: float
    at_h: float
    clock_at_origin: float
    #: True for the folded residual, which has no single origin.
    is_residual: bool = False


@dataclass(frozen=True)
class Contribution:
    """One contributor's standing in a state at one instant."""

    source: str
    label: str
    impulse: float
    surviving: float
    share: float
    age_h: float

    @property
    def is_residual(self) -> bool:
        return self.source == "residual"


class ContributionLedger:
    """Records impulses and prices their survival against the state's clock."""

    def __init__(self, half_lives: dict[str, float], adaptation_tau_h: float) -> None:
        self._half_lives = dict(half_lives)
        self._adaptation_tau_h = adaptation_tau_h
        self._entries: dict[tuple[str, str], list[Impulse]] = {}

    # --- recording ---------------------------------------------------------

    def record(
        self,
        channel: str,
        subject: str,
        magnitude: float,
        at_h: float,
        clock: float,
        source: str,
        label: str,
    ) -> None:
        if magnitude <= 0.0:
            return
        key = (channel, subject)
        self._entries.setdefault(key, []).append(
            Impulse(source, label, channel, subject, magnitude, at_h, clock)
        )

    def record_set(
        self, dose, at_h: float, clock: float, source: str, label: str, adaptation_gain: float
    ) -> None:
        """Record every channel one set touches."""
        for muscle, value in dose.local_fatigue.items():
            self.record(
                Channel.LOCAL_FATIGUE, muscle.value, value, at_h, clock, source, label
            )
        for muscle, value in dose.stimulus.items():
            self.record(
                Channel.ADAPTATION, muscle.value, adaptation_gain * value,
                at_h, clock, source, label,
            )
        self.record(Channel.NEUROMUSCULAR, "", dose.neuromuscular, at_h, clock, source, label)
        self.record(Channel.SYSTEMIC, "", dose.systemic, at_h, clock, source, label)

    # --- pricing -----------------------------------------------------------

    def _survival(self, entry: Impulse, t_h: float, clock: float) -> float:
        if entry.channel == Channel.ADAPTATION:
            return math.exp(-(t_h - entry.at_h) / self._adaptation_tau_h)
        elapsed = clock - entry.clock_at_origin
        return math.exp(-LN2 / self._half_lives[entry.channel] * elapsed)

    def contributions(
        self, channel: str, subject: str, total: float, t_h: float, clock: float
    ) -> tuple[Contribution, ...]:
        """Rank the contributors to one state, highest share first.

        ``total`` is the state's own value. Shares are taken against it rather
        than against the sum of surviving contributions, so a decomposition
        that has lost track of something reports shares that do not sum to one
        — which is exactly the signal the integrity test looks for.
        """
        entries = self._entries.get((channel, subject), ())
        if not entries or total <= 0.0:
            return ()

        priced = [
            Contribution(
                source=e.source,
                label=e.label,
                impulse=e.magnitude,
                surviving=(surviving := e.magnitude * self._survival(e, t_h, clock)),
                share=surviving / total,
                age_h=t_h - e.at_h,
            )
            for e in entries
        ]
        return tuple(sorted(priced, key=lambda c: -c.surviving))

    # --- housekeeping ------------------------------------------------------

    def fold_old(self, t_h: float, clock: float) -> None:
        """Move spent impulses into the residual entry.

        Folding rather than discarding is what keeps shares summing to one. The
        residual carries no single source, so it is labelled as what it is —
        older training whose individual sets no longer matter separately.
        """
        for (channel, subject), entries in self._entries.items():
            if channel == Channel.ADAPTATION:
                cutoff = self._adaptation_tau_h * FOLD_AFTER_HALF_LIVES / LN2
                spent = [e for e in entries if not e.is_residual and t_h - e.at_h > cutoff]
            else:
                cutoff = self._half_lives[channel] * FOLD_AFTER_HALF_LIVES
                spent = [
                    e for e in entries
                    if not e.is_residual and clock - e.clock_at_origin > cutoff
                ]
            if not spent:
                continue

            carried = sum(e.magnitude * self._survival(e, t_h, clock) for e in spent)
            kept = [e for e in entries if e not in spent]
            residual = next((e for e in kept if e.is_residual), None)
            if residual is None:
                kept.append(
                    Impulse(
                        "residual", "older training", channel, subject,
                        carried, t_h, clock, is_residual=True,
                    )
                )
            else:
                # Re-express the existing residual at the current clock so the
                # two masses are commensurable before they are added.
                residual.magnitude = (
                    residual.magnitude * self._survival(residual, t_h, clock) + carried
                )
                residual.at_h = t_h
                residual.clock_at_origin = clock
            self._entries[(channel, subject)] = kept

    def size(self) -> int:
        return sum(len(v) for v in self._entries.values())
