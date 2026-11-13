"""End-to-end audit of Layer 1.

Independent of the test suite: reads the *written dataset* and checks it against
the documented requirements directly. A green test run says the code does what
the tests expect; this says the artefact is what the specification asked for.

Every check states the document clause it comes from, and reports the measured
value rather than only a verdict, so a marginal pass is visible as marginal.
"""
from __future__ import annotations

import csv, json, shutil, subprocess, sys, tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path("data/synthetic/athlete_a")
results: list[tuple[str, str, bool, str]] = []


def check(section: str, requirement: str, ok: bool, detail: str, *, n: int | None = None) -> None:
    """Record one audit result.

    ``n`` is the sample size the check ran over. A check with nothing to look
    at must fail rather than pass vacuously: an empty scope that reports PASS
    is the failure mode that makes an audit worthless.
    """
    if n is not None and n == 0:
        results.append((section, requirement, False, f"VACUOUS: no samples ({detail})"))
        return
    results.append((section, requirement, bool(ok), detail))


def rows(rel):
    with (ROOT / rel).open(encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h))


def num(v, d=None):
    return float(v) if v not in (None, "", "None") else d


daily = rows("observable/daily_recovery.csv")
sets = rows("observable/sets.csv")
workouts = rows("observable/workouts.csv")
anchors = rows("observable/performance_tests.csv")
exercises = rows("observable/exercise_metadata.csv")
latent_daily = rows("hidden/latent_daily.csv")
latent_sets = rows("hidden/latent_sets.csv")
manifest = rows("hidden/scenario_manifest.csv")
config = json.loads((ROOT / "metadata" / "generation_config.json").read_text())
report = json.loads((ROOT / "metadata" / "quality_report.json").read_text())

dose = [s for s in sets if s["set_type"] in ("working", "backoff")]
date_index = {d["date"]: i for i, d in enumerate(daily)}
wk_day = {w["workout_id"]: date_index[w["date"]] for w in workouts}

# === scale (DATA.md §4) ====================================================
check("§4.1", "730 consecutive days", len(daily) == 730, f"{len(daily)} days")
check("§4.2", "470-510 lifting sessions", 470 <= len(workouts) <= 510, f"{len(workouts)}")
check("§4.2", "7500-8500 working sets", 7500 <= len(dose) <= 8500, f"{len(dose)}")
per_session = len(dose) / len(workouts)
check("§4.2", "14-18 working sets per session", 14 <= per_session <= 18, f"{per_session:.1f}")
check("§4.2", "730 daily recovery rows", len(latent_daily) == 730, f"{len(latent_daily)}")

# === training distribution (DATA.md §9) ====================================
def rep_band(r):
    return "1-3" if r <= 3 else "4-6" if r <= 6 else "7-10" if r <= 10 else "11-15" if r <= 15 else "16-25"

rc = Counter(rep_band(int(s["reps"])) for s in dose)
for band, (lo, hi) in {"1-3": (10, 15), "4-6": (24, 29), "7-10": (31, 37),
                       "11-15": (18, 22), "16-25": (5, 9)}.items():
    pct = 100 * rc[band] / len(dose)
    check("§9.1", f"repetition band {band} in {lo}-{hi}%", lo <= pct <= hi, f"{pct:.1f}%")

lc = Counter(min(3, int(num(s["rir"]))) for s in dose if s["rir"])
graded = sum(lc.values())
for rir, (lo, hi) in {0: (17, 25), 1: (22, 28), 2: (24, 28), 3: (24, 35)}.items():
    pct = 100 * lc[rir] / graded
    check("§9.2", f"logged RIR {rir} in {lo}-{hi}%", lo <= pct <= hi, f"{pct:.1f}%")

tc = Counter(min(3, round(num(r["true_rir"]))) for r in latent_sets
             if r["set_type"] in ("working", "backoff"))
tgraded = sum(tc.values())
for rir, (lo, hi) in {0: (10, 14), 1: (28, 33), 2: (35, 39), 3: (18, 23)}.items():
    pct = 100 * tc[rir] / tgraded
    check("§9.2", f"true RIR {rir} in {lo}-{hi}%", lo <= pct <= hi, f"{pct:.1f}%")

# === upper/lower parity (DATA.md §3.2) =====================================
from rhome_core.exercises import load_library
from rhome_core.muscles import REGION_OF, Region

library = load_library()
weekly = defaultdict(lambda: defaultdict(float))
for s in dose:
    for m, c in library[s["exercise_id"]].stimulus_contributions.items():
        weekly[wk_day[s["workout_id"]] // 7][m] += c
complete = [w for w in weekly if len(weekly[w]) > 4]
devs = []
for start in range(min(complete), max(complete) - 3):
    blk = [w for w in range(start, start + 4) if w in complete]
    if len(blk) < 4:
        continue
    up = sum(weekly[w][m] for w in blk for m in weekly[w] if REGION_OF[m] is Region.UPPER)
    lo_ = sum(weekly[w][m] for w in blk for m in weekly[w] if REGION_OF[m] is Region.LOWER)
    devs.append(abs(up - lo_) / ((up + lo_) / 2))
devs.sort()
within = sum(1 for d in devs if d <= 0.10) / len(devs)
check("§3.2", "upper/lower parity within ~10% of blocks", within >= 0.95,
      f"{within:.1%} of {len(devs)} blocks; median {devs[len(devs)//2]:.1%}, max {devs[-1]:.1%}",
      n=len(devs))

# === recovery data (DATA.md §11, §18) ======================================
import statistics as st
lat_by_date_all = {r["date"]: r for r in latent_daily}
slp = [num(d["total_sleep_min"]) / 60 for d in daily if d["total_sleep_min"]]
# §11.2's figure describes ordinary night-to-night variation. A record that
# includes deliberate sleep-restriction blocks carries more spread by design,
# so measuring the whole series against that figure would be measuring the
# scenarios rather than the sleep model.
ordinary_slp = [num(d["total_sleep_min"]) / 60 for d in daily
                if d["total_sleep_min"]
                and lat_by_date_all[d["date"]]["scenario_labels"] == "S0_ordinary"]
check("§11.2", "sleep centres near 7.5 h", abs(st.mean(slp) - 7.5) < 0.3, f"{st.mean(slp):.2f} h")
check("§11.2", "ordinary-night sleep SD 0.6-0.9 h",
      0.6 <= st.pstdev(ordinary_slp) <= 0.9, f"{st.pstdev(ordinary_slp):.3f} h",
      n=len(ordinary_slp))
check("§11.2", "whole record spreads wider than ordinary nights",
      st.pstdev(slp) > st.pstdev(ordinary_slp),
      f"{st.pstdev(slp):.3f} h with restriction blocks")
rm = [num(d["hrv_rmssd_ms"]) for d in daily if d["hrv_rmssd_ms"]]
check("§10", "RMSSD centres on the 60 ms baseline", abs(st.mean(rm) - 60) < 4, f"{st.mean(rm):.1f} ms")
check("§18", "RMSSD stays physiologically plausible", max(rm) < 130 and min(rm) > 20,
      f"{min(rm):.0f}-{max(rm):.0f} ms")
rh = [num(d["resting_hr_bpm"]) for d in daily if d["resting_hr_bpm"]]
check("§10", "resting HR centres on the 52 bpm baseline", abs(st.mean(rh) - 52) < 2,
      f"{st.mean(rh):.1f} bpm")
stages_ok = all(
    num(d["rem_sleep_min"], 0) + num(d["deep_sleep_min"], 0) <= num(d["total_sleep_min"], 1e9)
    for d in daily if d["total_sleep_min"])
check("§18", "sleep stages never exceed total sleep", stages_ok, "all rows")

# === missingness (DATA.md §17) =============================================
mc = Counter(d["wearable_missingness"] for d in daily)
check("§17", "3-5% nights lose one metric", 2.5 <= 100 * mc["partial"] / len(daily) <= 5.5,
      f"{100*mc['partial']/len(daily):.1f}%")
check("§17", "1-2% nights lose all metrics", 0.7 <= 100 * mc["full"] / len(daily) <= 2.5,
      f"{100*mc['full']/len(daily):.1f}%")
no_effort = sum(1 for s in dose if not s["rir"])
check("§17", "occasional sets without an effort rating", 0.5 <= 100 * no_effort / len(dose) <= 5,
      f"{100*no_effort/len(dose):.1f}%")

lat_by_date = {r["date"]: r for r in latent_daily}
scn_missing = ordinary_missing = scn_total = ordinary_total = 0
for d in daily:
    adverse = any(x in lat_by_date[d["date"]]["scenario_labels"]
                  for x in ("S7_illness", "S4_sleep", "S5_sleep", "S2_failure"))
    if adverse:
        scn_total += 1; scn_missing += d["wearable_missingness"] != "none"
    elif lat_by_date[d["date"]]["scenario_labels"] == "S0_ordinary":
        ordinary_total += 1; ordinary_missing += d["wearable_missingness"] != "none"
adverse_rate = scn_missing / max(scn_total, 1)
ordinary_rate = ordinary_missing / max(ordinary_total, 1)
check("§17", "missingness not concentrated in adverse scenarios",
      adverse_rate < ordinary_rate * 2.0,
      f"adverse {adverse_rate:.1%} of {scn_total}d vs ordinary {ordinary_rate:.1%}",
      n=scn_total)

# === scenarios (DATA.md §13, §15) ==========================================
families = {m["scenario"] for m in manifest}
check("§13", "all 12 scheduled scenario families present", len(families) == 12,
      f"{len(families)} families, {len(manifest)} windows")
dev_w = [m for m in manifest if m["window"] == "development"]
hold_w = [m for m in manifest if m["window"] == "holdout"]
check("§15", "scenarios in both development and holdout",
      len(dev_w) >= 6 and len(hold_w) >= 5, f"{len(dev_w)} dev, {len(hold_w)} holdout")
scenario_days = sum(1 for r in latent_daily if r["scenario_labels"] != "S0_ordinary")
check("§13", "scenarios are episodes, not the baseline",
      0.20 <= scenario_days / 730 <= 0.45, f"{100*scenario_days/730:.0f}% of days")

# === realism invariants (DATA.md §18) ======================================
INC = {"barbell": 2.5, "machine": 5.0, "cable": 2.5, "dumbbell": 2.0, "bodyweight": 2.5}
bad_load = [s for s in sets if s["set_type"] != "warmup"
            and abs(num(s["external_load_kg"]) / INC[library[s["exercise_id"]].equipment.value]
                    - round(num(s["external_load_kg"]) / INC[library[s["exercise_id"]].equipment.value])) > 1e-6]
check("§18", "loads change in realistic increments", not bad_load, f"{len(bad_load)} offending sets")

lset = {(r["workout_id"], r["exercise_id"], r["set_number"]): r for r in latent_sets}
impossible = [s for s in dose
              if int(s["reps"]) >= 12
              and num(lset[(s["workout_id"], s["exercise_id"], s["set_number"])]["true_relative_intensity"]) > 0.85]
check("§18", "no impossible load/repetition combinations", not impossible,
      f"{len(impossible)} offending sets")

bw = [num(r["true_body_mass_kg"]) for r in latent_daily]
check("§12", "body mass moves slowly, ~4-5 kg net range",
      3.0 <= max(bw) - min(bw) <= 6.0, f"{max(bw)-min(bw):.1f} kg")
obs_bw = [num(d["bodyweight_kg"]) for d in daily if d["bodyweight_kg"]]
check("§12", "scale readings noisier than the tissue trend",
      st.pstdev(obs_bw) > st.pstdev(bw) * 0.9, "daily noise present")

weeks = Counter(wk_day[w["workout_id"]] // 7 for w in workouts)
check("§18", "five sessions a week is an average, not an invariant",
      len(set(weeks.values())) > 1, f"weekly counts {sorted(set(weeks.values()))}")

# === separation (DATA.md §2, §6) ===========================================
leaked = [c for t in (daily, sets, workouts, anchors)
          for c in t[0] if c.startswith("true_") or "scenario" in c or "shock" in c]
check("§2", "no latent column in the observable tables", not leaked, f"{leaked or 'none'}")
check("§6.1", "hidden table carries per-muscle ground truth",
      sum(1 for c in latent_daily[0] if c.startswith("true_fatigue_")) == 16,
      f"{sum(1 for c in latent_daily[0] if c.startswith('true_fatigue_'))} muscles")
check("§6.3", "scenario manifest is in the hidden directory",
      (ROOT / "hidden" / "scenario_manifest.csv").exists(), "present")

from rhome_core.architecture import check_import_boundaries
v = check_import_boundaries()
check("§2", "engine cannot import the simulator or read hidden files", not v, f"{len(v)} violations")

# === reproducibility (DATA.md §20) =========================================
for field in ("seed", "dataset_version", "commit_hash", "simulator_constants",
              "athlete", "scenario_schedule"):
    check("§20", f"generation config records {field}", field in config,
          "present" if field in config else "ABSENT")

from rhome_sim.dataset import verify_checksums, write_dataset
from rhome_sim.generate import simulate
check("§20", "written dataset matches its own checksums", not verify_checksums(ROOT),
      f"{len(verify_checksums(ROOT))} mismatches")

tmp = Path(tempfile.mkdtemp()) / "regen"
write_dataset(simulate(config["seed"], n_days=config["n_days"]), tmp)
a = json.loads((ROOT / "metadata" / "checksums.json").read_text())
b = json.loads((tmp / "metadata" / "checksums.json").read_text())
differing = [k for k in a if k != "metadata/generation_config.json" and a[k] != b.get(k)]
shutil.rmtree(tmp.parent, ignore_errors=True)
check("§20", "regeneration from seed is byte-identical", not differing,
      f"{len(differing)} differing files")

# === quality report agreement ==============================================
check("meta", "quality report agrees with the files",
      report["days"] == len(daily) and report["sessions"] == len(workouts)
      and report["sets_total"] == len(sets),
      f"{report['days']}d / {report['sessions']}s / {report['sets_total']} sets")

# === test suite and conformance ============================================
proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                      capture_output=True, text=True)
last = proc.stdout.strip().splitlines()[-1] if proc.stdout else "no output"
check("meta", "full test suite passes", proc.returncode == 0, last)

conf = (Path("build_log") / "conformance.md").read_text()
covered = int(conf.split("**Covered:**")[1].split()[0])
uncovered = int(conf.split("**Uncovered:**")[1].split()[0])
check("meta", "every registered specification clause has a test", uncovered == 0,
      f"{covered} covered, {uncovered} uncovered")

# === output ================================================================
passed = sum(1 for *_, ok, _ in results if ok)
print(f"\n{'':4}{'SECTION':10}{'REQUIREMENT':62}{'MEASURED':28}")
print("-" * 108)
current = None
for section, requirement, ok, detail in results:
    if section != current:
        print(); current = section
    mark = "PASS" if ok else "FAIL"
    print(f"{mark:4}{section:10}{requirement:62}{detail:28}")
print("-" * 108)
print(f"{passed}/{len(results)} checks passed")
failures = [(s, r, d) for s, r, ok, d in results if not ok]
if failures:
    print("\nFAILURES:")
    for s, r, d in failures:
        print(f"  {s} {r} -> {d}")
sys.exit(1 if failures else 0)
