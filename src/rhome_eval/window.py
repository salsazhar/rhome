"""Evaluation windows, and the seal on the holdout (``DATA.md`` §15).

The holdout is opened once. That is not a convention to be remembered — it is
enforced here, because the value of a holdout is destroyed by the first
unrecorded look at it and nothing afterwards can tell you it happened.

Opening it requires an explicit argument *and* writes a record. A second
opening is permitted, because forbidding it outright would only encourage
working around the guard, but it is stamped as a second opening and every
result carries that mark. A number from a twice-opened holdout is a weaker
claim than the same number from a fresh one, and it should say so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

__all__ = ["Window", "HoldoutSeal", "holdout_seal", "SealError"]

REPO_ROOT = Path(__file__).resolve().parents[2]
SEAL_PATH = REPO_ROOT / "data" / "holdout_openings.json"

#: The development window is days 0–519; the holdout is 520–729.
DEVELOPMENT_DAYS = range(0, 520)
HOLDOUT_DAYS = range(520, 730)


class SealError(RuntimeError):
    """The holdout was requested without being deliberately opened."""


class Window(StrEnum):
    DEVELOPMENT = "development"
    HOLDOUT = "holdout"

    @property
    def days(self) -> range:
        return DEVELOPMENT_DAYS if self is Window.DEVELOPMENT else HOLDOUT_DAYS

    @property
    def is_sealed(self) -> bool:
        return self is Window.HOLDOUT


@dataclass(frozen=True)
class HoldoutSeal:
    """How many times the holdout has been opened, and when."""

    openings: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.openings)

    @property
    def is_first(self) -> bool:
        return self.count <= 1

    def note(self) -> str:
        if self.count == 0:
            return "holdout unopened"
        if self.count == 1:
            return f"holdout opened once, on {self.openings[0][:10]}"
        return (
            f"holdout opened {self.count} times, first on {self.openings[0][:10]}. "
            f"Results from a re-opened holdout are a weaker claim and must be "
            f"reported as such."
        )


def holdout_seal() -> HoldoutSeal:
    """Read the record without opening anything."""
    if not SEAL_PATH.exists():
        return HoldoutSeal()
    payload = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    return HoldoutSeal(
        openings=tuple(payload.get("openings", ())),
        reasons=tuple(payload.get("reasons", ())),
    )


def open_holdout(reason: str, *, record: bool = True) -> HoldoutSeal:
    """Open the holdout, recording that it happened.

    ``record=False`` exists only for tests, which must be able to exercise this
    path without writing to the project's real seal.
    """
    if not reason.strip():
        raise SealError("opening the holdout requires a stated reason")
    seal = holdout_seal()
    updated = HoldoutSeal(
        openings=seal.openings + (datetime.now(timezone.utc).isoformat(),),
        reasons=seal.reasons + (reason.strip(),),
    )
    if record:
        SEAL_PATH.write_text(
            json.dumps(
                {"openings": list(updated.openings), "reasons": list(updated.reasons)},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return updated
