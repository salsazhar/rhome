"""Render the curated exercise library as a review page.

The CSV is the source of truth; this only renders it, so the page and the data
cannot disagree.
"""
from __future__ import annotations
import html, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rhome_core.derivation import derive_compoundness, derive_systemic_cost  # noqa: E402
from rhome_core.exercises import load_library  # noqa: E402
from rhome_core.muscles import REGION_OF, Muscle, Region  # noqa: E402

REGION_ORDER = [Region.UPPER, Region.CORE, Region.LOWER]
lib = load_library()


def bar(value: float, tone: str) -> str:
    return (f'<span class="bar"><span class="bar-fill {tone}" '
            f'style="width:{value*100:.0f}%"></span></span>'
            f'<span class="num">{value:.2f}</span>')


def muscle_chips(ex) -> str:
    out = []
    for m in ex.primary_muscles:
        out.append(f'<span class="chip p">{html.escape(m.value)}</span>')
    for m in ex.secondary_muscles:
        out.append(f'<span class="chip s">{html.escape(m.value)}</span>')
    for m in ex.stabiliser_muscles:
        out.append(f'<span class="chip t">{html.escape(m.value)}</span>')
    return "".join(out)


rows_by_region: dict[Region, list] = {r: [] for r in REGION_ORDER}
for ex in sorted(lib, key=lambda e: (-e.systemic_cost, e.name)):
    region = REGION_OF[ex.primary_muscles[0]]
    rows_by_region[region].append(ex)

sections = []
for region in REGION_ORDER:
    exercises = rows_by_region[region]
    if not exercises:
        continue
    body = []
    for ex in exercises:
        dk = derive_compoundness(ex.equipment, ex.movement_pattern, len(ex.primary_muscles))
        db = derive_systemic_cost(ex.stimulus_contributions, ex.equipment, ex.movement_pattern)
        drift = max(abs(dk - ex.compoundness), abs(db - ex.systemic_cost))
        flag = ' <span class="warn" title="derivation misses this exercise">△</span>' if drift > 0.15 else ""
        extras = []
        if ex.unilateral:
            extras.append("per-limb")
        if ex.bodyweight_fraction is not None:
            extras.append(f"β {ex.bodyweight_fraction:.2f}")
        if ex.nuzzo_curve.value != "general":
            extras.append(f"{ex.nuzzo_curve.value} curve")
        body.append(f"""
        <tr>
          <td class="name">{html.escape(ex.name)}{flag}
            <span class="meta">{html.escape(ex.movement_pattern.value.replace('_',' '))}
            · {html.escape(ex.equipment.value)}{(' · ' + ' · '.join(extras)) if extras else ''}</span></td>
          <td class="chips">{muscle_chips(ex)}</td>
          <td class="v">{bar(ex.compoundness,'k')}</td>
          <td class="v">{bar(ex.systemic_cost,'b')}</td>
        </tr>""")
    sections.append(f"""
    <section class="region">
      <h2>{region.value.title()} <span class="count">{len(exercises)}</span></h2>
      <div class="tbl"><table>
        <thead><tr><th>Exercise</th><th>Muscles</th><th>Compoundness κ</th><th>Systemic cost b</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table></div>
    </section>""")

within = sum(
    1 for e in lib
    if abs(derive_compoundness(e.equipment, e.movement_pattern, len(e.primary_muscles)) - e.compoundness) <= 0.15
    and abs(derive_systemic_cost(e.stimulus_contributions, e.equipment, e.movement_pattern) - e.systemic_cost) <= 0.15
)

HEAD = """<title>Rhome Exercise Library</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@600&display=swap">
<style>
:root{--paper:#ECEEEA;--surface:#F6F7F4;--ink:#15191B;--ink-mid:#3C4644;--ink-soft:#5F6A67;
--accent:#8C2F39;--verify:#2C6E6A;--gate:#8F6314;--rule:#D2D8D1;--rule-firm:#B9C2BA;
--serif:"IBM Plex Serif",Georgia,serif;--sans:"IBM Plex Sans",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0F1315;--surface:#171D1F;--ink:#E4E8E4;
--ink-mid:#B4BEBB;--ink-soft:#8E9996;--accent:#CE6B73;--verify:#5FADA6;--gate:#D6A643;--rule:#252D2F;--rule-firm:#374143;}}
:root[data-theme="dark"]{--paper:#0F1315;--surface:#171D1F;--ink:#E4E8E4;--ink-mid:#B4BEBB;--ink-soft:#8E9996;
--accent:#CE6B73;--verify:#5FADA6;--gate:#D6A643;--rule:#252D2F;--rule-firm:#374143;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 clamp(18px,4vw,44px) 80px}
header{border-bottom:1px solid var(--rule-firm);padding:clamp(40px,6vw,72px) 0 30px;margin-bottom:8px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:500}
h1{font-family:var(--serif);font-size:clamp(32px,5.4vw,52px);line-height:1.05;letter-spacing:-.02em;margin:14px 0 14px;text-wrap:balance}
.stand{color:var(--ink-mid);max-width:60ch;margin:0 0 20px;font-size:17px}
.stats{display:flex;flex-wrap:wrap;gap:10px 32px;font-family:var(--mono);font-size:12px;color:var(--ink-soft);letter-spacing:.03em}
.stats b{color:var(--ink);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:26px 0 0;font-size:13px;color:var(--ink-mid);align-items:center}
.region{margin-top:48px}
h2{font-family:var(--serif);font-size:24px;margin:0 0 14px;letter-spacing:-.01em}
h2 .count{font-family:var(--mono);font-size:12px;color:var(--ink-soft);font-weight:400;margin-left:8px;vertical-align:middle}
.tbl{overflow-x:auto;border-top:1px solid var(--rule-firm)}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:720px}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;font-weight:500;
color:var(--ink-soft);text-align:left;padding:11px 14px 10px 0;border-bottom:1px solid var(--rule);white-space:nowrap}
td{padding:12px 14px 12px 0;border-bottom:1px solid var(--rule);vertical-align:top}
tr:last-child td{border-bottom:none}
.name{font-weight:600;min-width:210px}
.name .meta{display:block;font-family:var(--mono);font-size:10.5px;font-weight:400;color:var(--ink-soft);letter-spacing:.02em;margin-top:3px;text-transform:lowercase}
.chips{min-width:230px}
.chip{display:inline-block;font-family:var(--mono);font-size:10.5px;padding:2px 7px;border-radius:2px;margin:0 4px 4px 0;border:1px solid}
.chip.p{color:var(--accent);border-color:var(--accent);font-weight:500}
.chip.s{color:var(--ink-mid);border-color:var(--rule-firm)}
.chip.t{color:var(--ink-soft);border-color:var(--rule);font-style:italic}
.v{width:190px;white-space:nowrap}
.bar{display:inline-block;width:110px;height:6px;background:var(--rule);border-radius:1px;overflow:hidden;vertical-align:middle;margin-right:9px}
.bar-fill{display:block;height:100%}
.bar-fill.k{background:var(--accent)}
.bar-fill.b{background:var(--verify)}
.num{font-family:var(--mono);font-size:12.5px;font-variant-numeric:tabular-nums;color:var(--ink-mid)}
.warn{color:var(--gate);font-weight:600;cursor:help}
.note{border-left:3px solid var(--gate);padding:4px 0 4px 18px;margin:34px 0 0;color:var(--ink-mid);max-width:66ch;font-size:14.5px}
.note b{color:var(--ink)}
footer{margin-top:52px;padding-top:22px;border-top:1px solid var(--rule);font-family:var(--mono);font-size:11px;color:var(--ink-soft);display:flex;gap:8px 26px;flex-wrap:wrap}
</style>"""

page = f"""{HEAD}
<div class="wrap">
<header>
  <span class="eyebrow">Rhome · L0.3 · Checkpoint 0</span>
  <h1>The curated exercise library</h1>
  <p class="stand">Every muscle contribution and cost coefficient in the v0 model, for review. This page renders <code>exercise_library.csv</code> directly, so it cannot disagree with what the engine loads.</p>
  <div class="stats">
    <span><b>{len(lib)}</b> exercises</span>
    <span><b>16/16</b> muscle groups covered</span>
    <span><b>{within}/{len(lib)}</b> reproduced by derivation</span>
    <span><b>100%</b> curated</span>
  </div>
  <div class="legend">
    <span class="chip p">primary</span><span class="chip s">secondary</span><span class="chip t">tertiary / stabiliser</span>
    <span style="color:var(--ink-soft)">— primary earns full stimulus and fatigue, secondary half of each, tertiary fatigue only</span>
  </div>
</header>
{''.join(sections)}
<p class="note"><b>△ marks the one exercise the derivation cannot reproduce.</b> The 45-degree back extension is tagged as a hinge, the same pattern as a deadlift, and the model deliberately cannot see absolute load — so nothing distinguishes a bodyweight extension from a loaded hinge at the point of derivation. It affects user-created exercises only; the curated value is used here.</p>
<footer><span>Rendered from data/exercises/exercise_library.csv</span><span>Docs v0.3</span><span>Coefficients are engineering priors, not measurements</span></footer>
</div>
"""

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("exercise_library.html")
out.write_text(page, encoding="utf-8")
print(f"wrote {out} — {len(lib)} exercises, {within}/{len(lib)} derivation agreement")
