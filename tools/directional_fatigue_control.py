"""The paired directional test, run on SYNTHETIC data as a control (L3.15).

The real-data run of `directional_fatigue_test.py` returned chance. Before that
could mean anything, the design had to be exercised where the answer is known:
the engine reconstructs the simulator's latent local fatigue at +0.941
cross-sectionally, so a valid instrument should detect it here.

It does not. The test scores 49.0% on n=4228 against a ceiling of 54.6% — a
ceiling that at this n sits about 6 SE from chance and would be plainly
visible. **The design fails to detect a model known to be nearly correct**, so
the real-data null is void as evidence about the fatigue model.

What survives is the signal-to-noise comparison the two runs make possible, and
that is the finding: observed performance noise is 4.9x larger on the real
athlete, predicted contrast 1.6x smaller, so the fatigue signal is 7.8x weaker
relative to noise in reality than in the simulator.

D19: this is the check that stopped a null being read as a refutation. Twice.

Original docstring:
The same paired directional test, run on SYNTHETIC data.

If the design works there, the design is sound and the real log is the
problem. If it scores chance there too, the design is underpowered everywhere
and the real-data null says nothing at all.
"""
import sys, math, statistics as st
from collections import defaultdict
from pathlib import Path
ROOT = Path("/Users/salmanazhar/Desktop/rhome")
sys.path.insert(0, str(ROOT/"src")); sys.path.insert(0, str(ROOT/"tests"))
from rhome_core.exercises import load_library
from rhome_engine.session import RhomeEngine
from test_session_driver import _days

days = _days()[:519]
lib = load_library()
results = RhomeEngine(lib).run(days)

history = defaultdict(list)
pairs = []
MIN_PRIOR = 3
for r in results:
    if not r.observations: continue
    first, pos = {}, {}
    for o in r.observations:
        if o.exercise_id in first: continue
        pos[o.exercise_id] = len(first); first[o.exercise_id] = o
    entries = []
    for ident, o in first.items():
        base = o.base_exercise_id or o.exercise_id
        ex = lib.exercises.get(base)
        proj = r.projections.get(ident)
        if ex is None or proj is None: continue
        prior = history[ident]
        if len(prior) < MIN_PRIOR or o.observed <= 0: continue
        ref = st.median(prior)
        if ref <= 0: continue
        entries.append((frozenset(ex.primary_muscles), proj.suppression,
                        math.log(o.observed) - math.log(ref)))
    for i in range(len(entries)):
        for j in range(i+1, len(entries)):
            a, b = entries[i], entries[j]
            if a[0] & b[0]: continue
            pairs.append((a[1]-b[1], a[2]-b[2]))
    for ident, o in first.items():
        if o.observed > 0: history[ident].append(o.observed)

hits = sum(1 for g, t in pairs if t != 0 and (g > 0) == (t < 0))
n = len(pairs)
sp = st.pstdev([g for g, _ in pairs]); so = st.pstdev([t for _, t in pairs])
print(f"SYNTHETIC, identical design:  {hits}/{n} = {hits/n:.1%}")
print(f"  sd predicted gap {sp:.4f}   sd observed gap {so:.4f}   ratio {sp/so:.4f}")
ceil = 0.5 + math.atan(sp/so)/math.pi
print(f"  ceiling for a perfect model of this size: {ceil:.1%}")
se = math.sqrt(0.25/n)
print(f"  n={n}, SE={se:.4f}, engine is {(hits/n-0.5)/se:+.2f} SE from chance")
print(f"\nREAL, same design:            71/143 = 49.7%")
print(f"  sd predicted 0.0060  sd observed 0.3243  ratio 0.0184  ceiling 50.6%")
