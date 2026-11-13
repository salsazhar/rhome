"""Propose a mapping from the athlete's exercise names to library ids (L3.10).

The vocabulary extracted at L3.10 has to reach library ids before L3.12 can run.
This tool proposes; **the athlete decides**. That division is not politeness, it
is the whole design, and BUILD_PLAN says why: automated name matching fails on
exactly the cases that matter. "Machine Chest Press" could be any of a dozen
library rows differing in systemic cost, axial load and stabiliser tags, and a
fuzzy matcher will choose one of them with total confidence and no way for a
reader to see that it guessed.

So the tool claims confidence only where the tokens agree *exactly* and no rival
is close. Everything else is marked `review` and carries its score, its
runner-up and the gap between them. A tool that reported only its winner would
be hiding precisely the information a reviewer needs — and an earlier version of
this one did exactly that, confidently mapping "Seated Machine Leg Extension" to
``seated_machine_back_extension``.

**Nothing is dropped.** A name with no acceptable candidate is marked `derive`,
not discarded. The derivation path from L0.3 gives an unmatched exercise
coefficients from its muscle tags and equipment, and the confidence system from
L2.6 already docks dose quality for a derived coefficient — so an unmatched
exercise costs accuracy and says so, where a discarded one would silently delete
training load from the athlete's history.

    python3 tools/propose_exercise_mapping.py            # report
    python3 tools/propose_exercise_mapping.py --write    # write the review file
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rhome_core.exercises import load_library, library_path  # noqa: E402

VOCABULARY = ROOT / "data" / "real_vocabulary.json"
PROPOSAL = ROOT / "data" / "real_exercise_mapping.json"
LIBRARY = library_path().parent / "exercise_library_v1_2.csv"

#: Abbreviations and house spellings the athlete's logger uses. Expanded rather
#: than matched fuzzily, because "KB" and "kettlebell" share no characters and
#: no similarity measure will connect them.
SYNONYMS = {
    "kb": "kettlebell", "db": "dumbbell", "bb": "barbell",
    "ohp": "overhead press", "rdl": "romanian deadlift",
    "tricep": "triceps", "bicep": "biceps",
    "pushdown": "pressdown", "pulldown": "pulldown",
    "sit": "situp", "ups": "up", "raises": "raise",
    "chest supported": "chest_supported",
}

#: Words that carry no discriminating information between library rows.
NOISE = {"the", "a", "with", "and", "of", "on", "at"}

#: Below this, no candidate is proposed and the name is marked for derivation.
FLOOR = 0.55

#: A winner this close to its runner-up is not a winner.
AMBIGUOUS_GAP = 0.06

#: Only an exact token match is auto-accepted. Everything else goes to review.
#:
#: A first version accepted anything with a clear winner above the floor, and
#: put 53 of 68 names in the confident bucket. Two of them were wrong, and one
#: was wrong in a way that would have been expensive: "Seated Machine Leg
#: Extension" matched ``seated_machine_back_extension`` at 0.66 — quadriceps
#: read as spinal erectors. It sat between ``Incline Cable Fly`` -> ``cable_fly``
#: at 0.67 and ``Machine Chest Press`` -> ``single_arm_chest_press_machine`` at
#: 0.64, both defensible.
#:
#: That is the point: no threshold separates the wrong 0.66 from the right 0.69,
#: because the score measures spelling and the error is anatomical. So the tool
#: claims confidence only where the tokens agree exactly, and refers the rest to
#: the person who knows which machine they used.
EXACT = 1.0


def normalise(text: str) -> list[str]:
    """Lowercase, expand synonyms, drop punctuation, return sorted tokens."""
    text = text.lower()
    text = re.sub(r"[()\-/,'’\"]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens: list[str] = []
    for token in text.split():
        token = SYNONYMS.get(token, token)
        if token and token not in NOISE:
            tokens.extend(token.split())
    return sorted(set(tokens))


def score(left: list[str], right: list[str]) -> float:
    """Token overlap, tie-broken by character similarity.

    Token overlap alone rates "Seated Machine Leg Curl" and "Seated Machine Leg
    Extension" identically against a three-token query. The character term
    separates them without letting spelling dominate meaning.
    """
    if not left or not right:
        return 0.0
    shared = len(set(left) & set(right))
    overlap = shared / max(len(set(left) | set(right)), 1)
    characters = SequenceMatcher(None, " ".join(left), " ".join(right)).ratio()
    return 0.75 * overlap + 0.25 * characters


def propose(names: list[str], library) -> list[dict]:
    catalogue = [(e.exercise_id, normalise(e.name), e) for e in library]
    out: list[dict] = []

    for name in names:
        query = normalise(name)
        ranked = sorted(
            ((score(query, tokens), eid, exercise) for eid, tokens, exercise in catalogue),
            key=lambda row: -row[0],
        )
        best, runner_up = ranked[0], ranked[1]
        gap = best[0] - runner_up[0]

        if best[0] < FLOOR:
            verdict = "derive"
        elif best[0] >= EXACT and gap >= AMBIGUOUS_GAP:
            verdict = "exact"
        else:
            verdict = "review"

        out.append({
            "logged_name": name,
            "verdict": verdict,
            "exercise_id": best[1] if verdict != "derive" else None,
            "score": round(best[0], 4),
            "gap_to_runner_up": round(gap, 4),
            "alternatives": [
                {"exercise_id": eid, "name": exercise.name, "score": round(value, 4)}
                for value, eid, exercise in ranked[:4]
            ],
            "reviewed": False,
        })
    return out


def main(write: bool) -> int:
    if not VOCABULARY.exists():
        raise SystemExit(
            f"{VOCABULARY.relative_to(ROOT)} not found; run "
            f"tools/extract_exercise_vocabulary.py --write first"
        )
    names = json.loads(VOCABULARY.read_text(encoding="utf-8"))["names"]
    library = load_library(LIBRARY)
    rows = propose(names, library)

    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("exact", "review", "derive")}
    print(f"\n{len(names)} logged names against {len(library)} library exercises")
    print(f"  exact  {counts['exact']:3d}   tokens agree exactly and no rival is close")
    print(f"  review {counts['review']:3d}   a candidate exists; the matcher cannot vouch for it")
    print(f"  derive {counts['derive']:3d}   no acceptable candidate, coefficients derived\n")

    for verdict, heading in (
        ("review", "NEEDS THE ATHLETE — the matcher scores spelling, not anatomy"),
        ("derive", "NO MATCH — coefficients will be derived from muscle tags"),
        ("exact", "EXACT"),
    ):
        selected = [r for r in rows if r["verdict"] == verdict]
        if not selected:
            continue
        print(f"--- {heading}: {len(selected)}")
        for row in selected:
            head = f"    {row['logged_name'][:42]:42s}"
            if verdict == "derive":
                near = row["alternatives"][0]
                print(f"{head} (nearest {near['exercise_id']} at {near['score']:.2f})")
            elif verdict == "review":
                others = ", ".join(a["exercise_id"] for a in row["alternatives"][1:3])
                print(f"{head} {row['exercise_id']:38s} {row['score']:.2f}   or: {others}")
            else:
                print(f"{head} {row['exercise_id']}")
        print()

    if not write:
        print("Report only. Pass --write to produce the review file.")
        return 0

    payload = {
        "stage": "L3.10",
        "library": "v1.2",
        "vocabulary_source": str(VOCABULARY.relative_to(ROOT)),
        "reviewed": False,
        "review_note": (
            "Set reviewed to true only after checking every row. Rows marked "
            "review or derive need a decision. Rows marked exact matched token "
            "for token with no close rival and can be skimmed, but the matcher "
            "scores spelling and cannot see anatomy, so a wrong exact match is "
            "possible where two exercises share a name."
        ),
        "mappings": rows,
    }
    PROPOSAL.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PROPOSAL.relative_to(ROOT)} — unreviewed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--write" in sys.argv))
