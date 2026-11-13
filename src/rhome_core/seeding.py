"""Deterministic random number generation (Guardrail 4).

Every random draw in Rhome comes from an explicitly passed generator derived
from a single root seed. Nothing uses NumPy's global random state.

The reason is reproducibility of a specific kind. ``DATA.md`` §20 requires the
generator to be deterministic under a fixed seed, so a dataset can be
regenerated exactly from its config. Global random state breaks that quietly:
adding one extra draw anywhere shifts every subsequent number in the program,
so an unrelated change silently produces a different dataset.

Named substreams solve this. Each component asks for its own generator by name,
and those streams are independent of one another. Adding a draw inside the
sleep model cannot perturb the numbers the programme generator sees.

    >>> root = RootSeed(20260822)
    >>> sleep_rng = root.stream("sim.sleep")
    >>> hrv_rng = root.stream("sim.hrv")

The same name against the same root seed always yields the same stream,
regardless of the order in which streams are requested.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

__all__ = ["RootSeed", "stream_seed"]


def stream_seed(root_seed: int, name: str) -> int:
    """Derive a stable 64-bit substream seed from a root seed and a name.

    Uses BLAKE2b rather than Python's ``hash``, which is randomised per process
    and would therefore make runs irreproducible across invocations.
    """
    if not name:
        raise ValueError("stream name must be a non-empty string")
    digest = hashlib.blake2b(
        name.encode("utf-8"), digest_size=8, key=str(int(root_seed)).encode("utf-8")
    ).digest()
    return int.from_bytes(digest, "big")


@dataclass(frozen=True)
class RootSeed:
    """The single seed a whole generation run derives from."""

    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.seed, (int, np.integer)) or isinstance(self.seed, bool):
            raise TypeError(f"root seed must be an integer, got {type(self.seed).__name__}")
        if self.seed < 0:
            raise ValueError("root seed must be non-negative")

    def stream(self, name: str) -> np.random.Generator:
        """Return the independent generator for the named substream."""
        return np.random.default_rng(stream_seed(self.seed, name))
