"""The real-data cold run, and the seal on it (``BUILD_PLAN.md`` L3.12).

There is one athlete, one export, and one chance to run against it. `D9` sealed
it before the engine existed for a reason that bears repeating: data seen during
development is data tuned against, whether or not anyone intends it.

This module owns two things.

**The opening record.** The synthetic holdout has had one since L3.1 and the
real data has not, which is the wrong way round — the synthetic holdout can be
regenerated from a different seed and this cannot. Opening is recorded with a
stated reason, exactly as ``rhome_eval.window`` does, and every result carries
the count.

**What "consumed" actually means.** A second opening does not by itself destroy
the holdout; a *model change made after seeing results* does. So the record
distinguishes the two, and a run is marked ``dry`` when it reads the data
without scoring it. A dry pass exists to catch a parsing bug before the scoring
pass, and fixing ingestion after seeing row counts conditions nothing about the
model. Fixing the model after seeing residuals is the act that spends the
resource, and it is the one the record is designed to make visible.

That distinction is stated here rather than left to judgement, because the
temptation it guards against arrives precisely when the numbers are
disappointing.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "RealSeal",
    "SealError",
    "real_seal",
    "open_real_data",
    "ColdRunInputs",
    "assemble",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
SEAL_PATH = REPO_ROOT / "data" / "real_openings.json"

ARCHIVE = REPO_ROOT / "data" / "real" / "spotr" / "spotr_training_archive.sqlite"
OURA = REPO_ROOT / "data" / "real" / "oura" / "oura_2024-12-17_2026-08-23_trends.csv"


class SealError(RuntimeError):
    """The athlete's history was requested without being deliberately opened."""


@dataclass(frozen=True)
class RealSeal:
    """How many times the athlete's own history has been opened, and why."""

    openings: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.openings)

    @property
    def scoring_openings(self) -> int:
        """Openings that read results. These are the ones that cost something."""
        return sum(1 for k in self.kinds if k != "dry")

    def note(self) -> str:
        if self.count == 0:
            return "the athlete's history is unopened"
        scoring = self.scoring_openings
        head = (
            f"opened {self.count} time{'s' if self.count != 1 else ''} "
            f"({scoring} scoring, {self.count - scoring} dry), "
            f"first on {self.openings[0][:10]}"
        )
        if scoring <= 1:
            return head
        return (
            head
            + ". More than one scoring opening: any model change made between "
            + "them consumed the holdout, and results must be reported as a "
            + "weaker claim."
        )


def real_seal() -> RealSeal:
    """Read the record without opening anything."""
    if not SEAL_PATH.exists():
        return RealSeal()
    payload = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    return RealSeal(
        openings=tuple(payload.get("openings", ())),
        reasons=tuple(payload.get("reasons", ())),
        kinds=tuple(payload.get("kinds", ())),
    )


def open_real_data(reason: str, *, kind: str = "scoring", record: bool = True) -> RealSeal:
    """Open the athlete's history, recording that it happened.

    ``kind`` is ``dry`` for a pass that reads without scoring and ``scoring``
    otherwise. ``record=False`` exists only for tests, which must exercise this
    path without writing to the project's real seal.
    """
    if not reason.strip():
        raise SealError("opening the athlete's history requires a stated reason")
    if kind not in ("dry", "scoring"):
        raise SealError(f"kind must be 'dry' or 'scoring', got {kind!r}")

    seal = real_seal()
    updated = RealSeal(
        openings=seal.openings + (datetime.now(timezone.utc).isoformat(),),
        reasons=seal.reasons + (reason.strip(),),
        kinds=seal.kinds + (kind,),
    )
    if record:
        SEAL_PATH.write_text(
            json.dumps(
                {
                    "openings": list(updated.openings),
                    "reasons": list(updated.reasons),
                    "kinds": list(updated.kinds),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return updated


# --- assembling the run -------------------------------------------------------

@dataclass
class ColdRunInputs:
    """Everything the engine needs, and the provenance of all of it."""

    days: list
    report: object
    seal: RealSeal
    mapping_digest: str
    equipment_context_digest: str
    library_pin: object

    @property
    def provenance(self) -> str:
        return (
            f"library {self.library_pin.version} ({self.library_pin.digest[:12]}), "
            f"mapping {self.mapping_digest[:12]}, contexts "
            f"{self.equipment_context_digest[:12] or 'none'}, {self.seal.note()}"
        )


def assemble(reason: str, *, kind: str = "scoring", record: bool = True) -> ColdRunInputs:
    """Open the history and build the engine's input, refusing anything unready.

    Every precondition is checked before the seal is opened, so a run that is
    going to fail on a missing mapping fails without spending an opening.
    """
    from rhome_core.exercises import library_path, load_library  # noqa: PLC0415

    from rhome_eval.spotr import GYM_TAGS, build_days, load_equipment_contexts  # noqa: PLC0415
    from rhome_eval.vocabulary import load_mapping  # noqa: PLC0415

    if not ARCHIVE.exists():
        raise SealError(f"no Spotr archive at {ARCHIVE}")
    if not OURA.exists():
        raise SealError(f"no Oura export at {OURA}")

    # Refuses an unreviewed or incomplete mapping. Checked first: a run that
    # cannot proceed should not consume an opening to discover it.
    mapping = load_mapping()
    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    if library.pin is None:
        raise SealError("the library carries no pin; a run must record its library")

    seal = open_real_data(reason, kind=kind, record=record)
    contexts = load_equipment_contexts()
    days, report = build_days(
        ARCHIVE, OURA, mapping, library, equipment_contexts=contexts
    )
    return ColdRunInputs(
        days=days,
        report=report,
        seal=seal,
        mapping_digest=mapping.digest,
        equipment_context_digest=(
            hashlib.sha256(GYM_TAGS.read_bytes()).hexdigest()
            if GYM_TAGS.exists() else ""
        ),
        library_pin=library.pin,
    )
