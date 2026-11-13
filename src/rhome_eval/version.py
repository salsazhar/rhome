"""Model versions and their freeze dates (``D22``).

D22 made validation prospective: the recurring exam is every session logged
*after* a model version was frozen, because those cannot have been fitted to.
That regime needs one thing the project did not have — a way to say which
version a logged session post-dates. Until this module existed, "frozen on"
was prose in ``DECISIONS.md`` and nothing could be proved from it.

**The freeze date is derived, never declared.** A hand-maintained version
string is a version string that eventually lies, which is why the library pin
and the frozen projections are both content-addressed. The same argument
applies with more force here, because the thing at stake is whether a score
was earned on unseen data. So ``frozen_at`` is read from the last commit that
touched anything determining engine behaviour, and the digest is computed from
the code and parameters actually present.

**What counts as a new model.** Two groups, kept separate because they answer
different questions:

``engine``
    ``src/rhome_engine/``, ``src/rhome_core/`` and the exercise library. These
    decide what the engine predicts given its inputs. A change here is a new
    model version and resets the freeze date.

``inputs``
    The real-data mapping, conventions, gym tags and body mass. These decide
    what the engine *sees* on the historical log. They are recorded so an
    evaluation can prove which were in force, but they do not make a new
    model — and the prospective logger writes library ids directly, so the
    name mapping does not apply to prospective data at all.

Source files are digested whole rather than by parsing. A comment edit will
therefore change the digest without changing a prediction. That is the safe
direction to be wrong in: a spurious "different version" costs a re-freeze, a
spurious "same version" costs a false claim about unseen data.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

__all__ = [
    "ModelVersion",
    "VersionError",
    "VERSIONS_PATH",
    "capture",
    "record",
    "load_versions",
    "latest",
    "drift",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_PATH = REPO_ROOT / "data" / "model_versions.json"

#: Everything that decides what the engine predicts from a given input.
#: A change to any of these is a new model version.
ENGINE_PATHS: tuple[str, ...] = (
    "src/rhome_engine",
    "src/rhome_core",
    "data/exercises/exercise_library_v1_2.csv",
)

#: Files inside the engine paths that provably cannot change a prediction, and
#: so must not churn the version. ``conformance.py`` is the specification-to-test
#: coverage registry: nothing in ``rhome_engine`` or ``rhome_core`` imports it,
#: only ``tests/conftest.py`` and the layer audit do. Registering a clause is
#: not a model change, and treating it as one would make every stage that adds
#: coverage forfeit its freeze date.
EXCLUDED_SOURCES: tuple[str, ...] = (
    "src/rhome_core/conformance.py",
)

#: Everything that decides what the engine *sees* on the historical log.
#: Recorded, but not part of the model's identity. Some are gitignored athlete
#: data, which is why these are content-digested rather than git-pinned.
INPUT_PATHS: tuple[str, ...] = (
    "data/real_exercise_mapping.json",
    "data/real_conventions.json",
    "data/real_gym_tags.json",
    "data/real_body_mass.json",
)

_CHUNK = 1 << 20


class VersionError(RuntimeError):
    """A version could not be captured, recorded or verified."""


@dataclass(frozen=True)
class ModelVersion:
    """One frozen model, and proof of what it was.

    ``frozen_at`` is the moment the model last changed, not the moment this
    record was written. Sessions logged after it are the prospective exam.
    """

    label: str
    frozen_at: str
    commit: str
    parameters_digest: str
    source_digest: str
    library: Mapping[str, object]
    inputs: Mapping[str, str]
    known_defects: tuple[str, ...] = ()
    note: str = ""
    recorded_at: str = ""
    digest: str = ""

    def compute_digest(self) -> str:
        payload = json.dumps(
            {
                "frozen_at": self.frozen_at,
                "commit": self.commit,
                "parameters": self.parameters_digest,
                "source": self.source_digest,
                "library": dict(sorted(self.library.items())),
            },
            sort_keys=True,
        )
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()

    def verify(self) -> bool:
        return bool(self.digest) and self.digest == self.compute_digest()

    def covers(self, when: str) -> bool:
        """Does a session logged at ``when`` post-date this freeze?

        The prospective exam is exactly the sessions for which this is true.
        """
        return _instant(when) > _instant(self.frozen_at)

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "frozen_at": self.frozen_at,
            "commit": self.commit,
            "parameters_digest": self.parameters_digest,
            "source_digest": self.source_digest,
            "library": dict(self.library),
            "inputs": dict(self.inputs),
            "known_defects": list(self.known_defects),
            "note": self.note,
            "recorded_at": self.recorded_at,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, object]) -> "ModelVersion":
        return cls(
            label=str(row["label"]),
            frozen_at=str(row["frozen_at"]),
            commit=str(row["commit"]),
            parameters_digest=str(row["parameters_digest"]),
            source_digest=str(row["source_digest"]),
            library=dict(row.get("library") or {}),  # type: ignore[arg-type]
            inputs=dict(row.get("inputs") or {}),  # type: ignore[arg-type]
            known_defects=tuple(row.get("known_defects") or ()),  # type: ignore[arg-type]
            note=str(row.get("note", "")),
            recorded_at=str(row.get("recorded_at", "")),
            digest=str(row.get("digest", "")),
        )


# --- the pieces a version is made of ---------------------------------------

def _instant(text: str) -> datetime:
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _git(*args: str) -> str:
    try:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise VersionError(f"git {' '.join(args)} failed") from exc
    return done.stdout.strip()


def parameters_digest() -> str:
    """Every registered parameter, by name and value.

    Both registries, because the exercise-to-muscle coefficients live in
    ``rhome_core`` and decide predictions as surely as the half-lives do.
    """
    from rhome_core.parameters import CORE_PARAMETERS  # noqa: PLC0415
    from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: PLC0415

    rows = sorted(
        (f"{registry.namespace}.{p.name}", repr(p.value))
        for registry in (CORE_PARAMETERS, ENGINE_PARAMETERS)
        for p in registry
    )
    payload = json.dumps(rows, sort_keys=True)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_files(paths: Sequence[str]) -> list[Path]:
    excluded = {REPO_ROOT / entry for entry in EXCLUDED_SOURCES}
    found: list[Path] = []
    for entry in paths:
        target = REPO_ROOT / entry
        if target.is_dir():
            found.extend(sorted(p for p in target.rglob("*.py") if p.is_file()))
        elif target.is_file():
            found.append(target)
    return [p for p in found if p not in excluded]


def source_digest() -> str:
    """The engine's code and library, digested whole."""
    files = _tree_files(ENGINE_PATHS)
    if not files:
        raise VersionError("no engine sources found to digest")
    rows = [
        [str(p.relative_to(REPO_ROOT)), _file_digest(p)] for p in files
    ]
    payload = json.dumps(rows, sort_keys=True)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def last_engine_change() -> tuple[str, str]:
    """When the engine last changed, and at which commit.

    Derived rather than declared: this is the freeze date, and a freeze date a
    human types is one that stays at its first value while the code moves past
    it. Uncommitted changes to engine paths make the answer a lie, so they are
    refused rather than ignored.
    """
    spec = [*ENGINE_PATHS, *(f":(exclude){entry}" for entry in EXCLUDED_SOURCES)]
    dirty = _git("status", "--porcelain", "--", *spec)
    if dirty:
        raise VersionError(
            "engine paths have uncommitted changes, so the freeze date would "
            f"be wrong; commit or revert first:\n{dirty}"
        )
    commit = _git("log", "-1", "--format=%H", "--", *spec)
    when = _git("log", "-1", "--format=%cI", "--", *spec)
    if not commit or not when:
        raise VersionError("no commit found touching the engine paths")
    return when, commit


def input_digests() -> dict[str, str]:
    """Content digests of the real-data ingest inputs that are present."""
    return {
        entry: _file_digest(REPO_ROOT / entry)
        for entry in INPUT_PATHS
        if (REPO_ROOT / entry).is_file()
    }


def capture(label: str, *, note: str = "", known_defects: Sequence[str] = ()) -> ModelVersion:
    """Build a version record from the repository as it stands."""
    from rhome_core.exercises import library_path, library_pin  # noqa: PLC0415

    frozen_at, commit = last_engine_change()
    pin = library_pin(library_path().parent / "exercise_library_v1_2.csv")
    version = ModelVersion(
        label=label,
        frozen_at=frozen_at,
        commit=commit,
        parameters_digest=parameters_digest(),
        source_digest=source_digest(),
        library=pin.as_dict(),
        inputs=input_digests(),
        known_defects=tuple(known_defects),
        note=note,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    return replace(version, digest=version.compute_digest())


# --- the append-only record -------------------------------------------------

def load_versions() -> list[ModelVersion]:
    if not VERSIONS_PATH.exists():
        return []
    payload = json.loads(VERSIONS_PATH.read_text(encoding="utf-8"))
    return [ModelVersion.from_dict(row) for row in payload.get("versions", [])]


def latest() -> ModelVersion | None:
    versions = load_versions()
    return versions[-1] if versions else None


def record(version: ModelVersion) -> ModelVersion:
    """Append a version. Never rewrites one: a freeze happens once."""
    existing = load_versions()
    for prior in existing:
        if prior.label == version.label:
            raise VersionError(
                f"version {version.label!r} is already recorded, frozen at "
                f"{prior.frozen_at}. A freeze happens once; choose a new label."
            )
        if prior.digest == version.digest:
            raise VersionError(
                f"this model is already recorded as {prior.label!r} "
                f"({prior.digest}); nothing has changed since it was frozen."
            )
    rows = [v.as_dict() for v in existing] + [version.as_dict()]
    VERSIONS_PATH.write_text(
        json.dumps({"versions": rows}, indent=1) + "\n", encoding="utf-8"
    )
    return version


def drift(version: ModelVersion) -> dict[str, str]:
    """Which parts of a recorded version no longer match the working tree."""
    moved: dict[str, str] = {}
    if version.parameters_digest != parameters_digest():
        moved["parameters"] = "a registered parameter's value has changed"
    if version.source_digest != source_digest():
        moved["source"] = "engine or core source has changed"
    current = input_digests()
    for name, digest in version.inputs.items():
        if current.get(name) != digest:
            moved[name] = "ingest input has changed or is missing"
    if not version.verify():
        moved["digest"] = "the record's own digest does not match its contents"
    return moved
