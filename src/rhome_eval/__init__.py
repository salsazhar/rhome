"""Evaluation harness.

The only package permitted to import both ``rhome_sim`` and ``rhome_engine``,
and the only one permitted to read the simulator's hidden latent state. It
compares what the engine estimated against what was actually true.

That privilege is why evaluation is a separate package rather than living
inside the engine: the boundary is easier to police when it has a name.
"""

__all__ = ["ARCHITECTURE_ROLE"]

ARCHITECTURE_ROLE = "evaluation; may import rhome_sim, rhome_engine and rhome_core"
