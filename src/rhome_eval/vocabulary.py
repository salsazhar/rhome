"""The frozen exercise mapping (``BUILD_PLAN.md`` L3.10).

L3.12 is a one-shot run against the athlete's real history, and it must make no
decisions. Every judgement it would otherwise have to make — which library
exercise a logged name refers to — is taken here, in advance, reviewed by the
athlete and frozen.

The reason for the ordering is the reason for the whole holdout discipline. A
mapping chosen at L3.12 would be chosen with the athlete's results already
visible, and "Machine Chest Press" resolved one way rather than another after
seeing which way fits better is tuning, however innocent the intent. Freezing it
beforehand makes that impossible rather than discouraged.

Two properties make the freeze real rather than declared:

**An unreviewed mapping is refused.** The proposal tool writes
``reviewed: false``, and nothing will run on a file still carrying it. The
matcher scores spelling and cannot see anatomy — it once offered
``seated_machine_back_extension`` for "Seated Machine Leg Extension", quadriceps
read as spinal erectors — so its output is a draft by definition.

**The reviewed file is content-addressed.** A digest is recorded when the
mapping is frozen, so a later run can prove it used the same one. Without it
"frozen" means only that somebody intended not to change it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ExerciseMapping",
    "MappingError",
    "load_mapping",
    "mapping_path",
    "mapping_digest",
]

REPO_ROOT = Path(__file__).resolve().parents[2]


class MappingError(RuntimeError):
    """The mapping is missing, unreviewed, incomplete or has been altered."""


def mapping_path() -> Path:
    return REPO_ROOT / "data" / "real_exercise_mapping.json"


def mapping_digest(path: Path | None = None) -> str:
    """Content address of the mapping as it stands on disk."""
    return hashlib.sha256((path or mapping_path()).read_bytes()).hexdigest()


@dataclass(frozen=True)
class ExerciseMapping:
    """Logged exercise names resolved to library ids, reviewed and frozen."""

    #: Logged name -> library exercise id. A name whose coefficients are to be
    #: derived maps to ``None`` and is present here rather than absent, because
    #: absence and "no library match" must not look the same to a caller.
    resolved: dict[str, str | None]
    digest: str
    library: str

    def __len__(self) -> int:
        return len(self.resolved)

    def __contains__(self, logged_name: object) -> bool:
        return logged_name in self.resolved

    @property
    def derived_names(self) -> tuple[str, ...]:
        """Names with no library match, whose coefficients come from tags."""
        return tuple(sorted(k for k, v in self.resolved.items() if v is None))

    def library_id(self, logged_name: str) -> str | None:
        """Resolve one logged name.

        Raises rather than returning ``None`` for a name the mapping has never
        seen. ``None`` already means "matched to nothing on purpose", and
        conflating the two would let an unmapped name pass silently into a run
        that cannot be repeated.
        """
        try:
            return self.resolved[logged_name]
        except KeyError:
            raise MappingError(
                f"no mapping for logged exercise name {logged_name!r}. The "
                f"vocabulary was frozen at L3.10 from the sealed log; a name "
                f"absent from it means the log has changed since, and the "
                f"mapping must be re-reviewed rather than guessed at now."
            ) from None


def load_mapping(path: Path | None = None) -> ExerciseMapping:
    """Load the frozen mapping, refusing anything not ready to be trusted."""
    path = path or mapping_path()
    if not path.exists():
        raise MappingError(
            f"no exercise mapping at {path}. Run "
            f"tools/propose_exercise_mapping.py --write, review every row, then "
            f"set reviewed to true."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("reviewed"):
        raise MappingError(
            f"{path.name} is not reviewed. The matcher scores spelling and "
            f"cannot see anatomy, so its proposals are a draft: it offered "
            f"seated_machine_back_extension for 'Seated Machine Leg Extension'. "
            f"Review every row, then set reviewed to true."
        )

    rows = payload.get("mappings", ())
    if not rows:
        raise MappingError(f"{path.name} contains no mappings")

    unresolved = [
        row["logged_name"]
        for row in rows
        if row.get("verdict") != "derive" and not row.get("exercise_id")
    ]
    if unresolved:
        raise MappingError(
            f"{len(unresolved)} names are neither mapped nor marked for "
            f"derivation: {unresolved[:5]}. Every logged name must resolve to a "
            f"library id or be deliberately marked derive — silently dropping "
            f"one would delete training load from the athlete's history."
        )

    return ExerciseMapping(
        resolved={
            row["logged_name"]: (
                None if row.get("verdict") == "derive" else row["exercise_id"]
            )
            for row in rows
        },
        digest=mapping_digest(path),
        library=payload.get("library", "unknown"),
    )
