"""Scale alignment between latent and estimated states (``DATA.md`` §19.1).

The engine's fatigue units are not the simulator's and were never meant to be.
The engine's local fatigue is a sum of impulses scaled by its own coefficients;
the simulator's is a two-component decay in units of its own choosing. Comparing
their RMSE directly would measure the arbitrary difference between two unit
systems, which is why the specification says "after agreed scale normalisation".

Two properties make the alignment honest rather than a way of flattering a
result:

**One scalar per channel, no offset.** A channel is a non-negative sum of
impulses and both sides are zero when nothing has been trained, so the mapping
that could exist is a scale. Allowing an offset would let a constant error be
absorbed into the alignment.

**Fitted on development, frozen, and applied unchanged to the holdout.**
Refitting on the holdout would tune a parameter on the data being used to test,
which is the whole failure the holdout exists to prevent. The fitted values are
content-addressed so a later run can prove it used the same ones.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping, Sequence

__all__ = ["ScaleAlignment", "fit_alignment", "AlignmentError"]


class AlignmentError(ValueError):
    """An alignment could not be fitted, or was misused."""


@dataclass(frozen=True)
class ScaleAlignment:
    """One multiplier per channel, mapping engine units onto latent units."""

    scales: Mapping[str, float] = field(default_factory=dict)
    fitted_on: str = "development"
    n_points: int = 0
    digest: str = ""

    def compute_digest(self) -> str:
        payload = json.dumps(
            {
                "scales": {k: round(v, 12) for k, v in sorted(self.scales.items())},
                "fitted_on": self.fitted_on,
                "n_points": self.n_points,
            },
            sort_keys=True,
        )
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()

    def verify(self) -> bool:
        return bool(self.digest) and self.digest == self.compute_digest()

    def apply(self, channel: str, values: Sequence[float]) -> list[float]:
        if channel not in self.scales:
            raise AlignmentError(
                f"no alignment fitted for channel {channel!r}; "
                f"have {sorted(self.scales)}"
            )
        scale = self.scales[channel]
        return [v * scale for v in values]


def fit_alignment(
    estimated: Mapping[str, Sequence[float]],
    truth: Mapping[str, Sequence[float]],
    *,
    fitted_on: str = "development",
) -> ScaleAlignment:
    """Least-squares scale through the origin, per channel.

    The scale minimising :math:`\\sum (s x_i - y_i)^2` is
    :math:`\\sum x_i y_i / \\sum x_i^2`. Fitting through the origin rather than
    with an intercept is the point: both series are zero when nothing has been
    trained, and an intercept would quietly absorb a constant bias that the
    evaluation is supposed to report.
    """
    scales: dict[str, float] = {}
    total_points = 0
    for channel, x in estimated.items():
        if channel not in truth:
            raise AlignmentError(f"no latent series for channel {channel!r}")
        y = truth[channel]
        if len(x) != len(y):
            raise AlignmentError(
                f"channel {channel!r}: {len(x)} estimates against {len(y)} truths"
            )
        denominator = sum(v * v for v in x)
        if denominator <= 0.0:
            raise AlignmentError(
                f"channel {channel!r} is identically zero; nothing to align"
            )
        scales[channel] = sum(a * b for a, b in zip(x, y)) / denominator
        total_points += len(x)

    alignment = ScaleAlignment(
        scales=dict(sorted(scales.items())), fitted_on=fitted_on, n_points=total_points
    )
    return ScaleAlignment(
        scales=alignment.scales,
        fitted_on=alignment.fitted_on,
        n_points=alignment.n_points,
        digest=alignment.compute_digest(),
    )
