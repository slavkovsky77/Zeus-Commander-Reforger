"""Attack approaches scored from measured runs (29 Oct evening - Martin's go on the morning page's "choose approaches from
results as well as from the map", review note 451; the night's 34 Farm runs showed that a good approach pays off but that
neither the algorithm nor Gemini reliably finds it, note 450).

For every one-point assault run (lab/assaulttest.py, scenarios point and city) and each side: the HQ it attacked from (the
run's snapshot), the approach it had (the run's own attackplan.txt - the plan line of that HQ; none = AI Conflict's own
approach), its ride setup, and what Martin sees: soldiers at the objective by minute 8 and 12, the objective taken within
15 minutes, the third team in. Per objective, HQ, setup and approach:

    .runtime/attack/scores.json  {"objective": {"Farm": {"x", "z"}}, "rows": [{"objective", "hq": [x, z], "rides",
                                  "approach", "assembly": [x, z] | null, "runs", "at8", "at12", "took", "third", "score"}]}

score per run = soldiers there at minute 12 + 10 if it took the objective; the row's score is the mean. estimate() shrinks a
row toward the HQ's no-plan mean (PRIOR_RUNS pseudo-runs), so one lucky run doesn't decide. Used by lab/attackplan.py
--export measured (per HQ the approach with the best estimate, or none when AI Conflict's own approach is best) and by
lab/attackpick.py (the model is shown the measured results next to the map).

    python lab/attackscore.py               # every run -> scores.json and the table
    python lab/attackscore.py --rides all   # the table for every ride setup, not just the transport rides
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = ROOT / ".runtime" / "attack"
RUNS = ROOT / ".runtime" / "runs"
CACHE = OUT / "run_summaries.json"
COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
SAME_ASSEMBLY_M = 80     # two plans whose assembly points are this close, in the same compass sector, are the same approach
PRIOR_RUNS = 2           # estimate(): the HQ's no-plan mean counts as this many runs
NONE = "none"            # the approach of a run without a plan: AI Conflict's own


def compass(dx: float, dz: float) -> str:
    a = math.degrees(math.atan2(dx, dz))
    return COMPASS[int(((a + 360) % 360 + 22.5) // 45) % 8]


def approach_name(obj, assembly) -> str:
    if not assembly:
        return NONE
    return f"{compass(assembly[0] - obj[0], assembly[1] - obj[1])} {round(math.dist(assembly, obj))} m"


def same_approach(obj, a, b) -> bool:
    return (math.dist(a, b) < SAME_ASSEMBLY_M and
            compass(a[0] - obj[0], a[1] - obj[1]) == compass(b[0] - obj[0], b[1] - obj[1]))


def setup(run: dict) -> tuple:
    """(rides, variant) from the run's own run.json: transport = trucks and vans only (-aicfArmedRideEvery 0)."""
    extra = run.get("args", {}).get("extra", "")
    label = run.get("args", {}).get("label", "")
    if "foot" in label:
        rides = "foot"
    elif "-aicfArmedRideEvery 0" in extra:
        rides = "transport"
    else:
        rides = "mixed"
    return rides, label


def summaries(refresh: bool = False) -> dict:
    """Every one-point run's summary (assaulttest.summarize), cached by run folder and its log's size."""
    import assaulttest
    cache = {} if refresh or not CACHE.exists() else json.loads(CACHE.read_text(encoding="utf-8"))
    out = {}
    for r in sorted(RUNS.glob("assault*-*")):
        scenario = r.name.split("-")[1]
        if scenario not in ("point", "city") or not (r / "run.json").exists():
            continue
        logs = list((r / "logs").glob("*/console.log"))
        stamp = sum(p.stat().st_size for p in logs)
        if r.name in cache and cache[r.name].get("_stamp") == stamp:
            out[r.name] = cache[r.name]
            continue
        variant = r.name.split(f"-{scenario}-", 1)[1]
        variant = variant.replace("-watch", "").split("-p2", 1)[0].rsplit("-2026", 1)[0]
        if variant not in assaulttest.VARIANTS:
            variant = "now"
        try:
            d = assaulttest.summarize(r, scenario, variant)
        except Exception as e:     # a run that never got going
            d = {"error": f"{type(e).__name__}: {e}"}
        d["_stamp"] = stamp
        out[r.name] = d
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out), encoding="utf-8")
    return out


def side_runs(refresh: bool = False):
    """One record per run and side: objective, HQ, rides, approach, the outcome."""
    for name, d in summaries(refresh).items():
        if d.get("error") or d.get("crashed") or (d.get("minutes") or 0) < 12:
            continue
        r = RUNS / name
        snap = r / "profile" / "zcr" / "snapshots.jsonl"
        if not snap.exists():
            continue
        first = json.loads(snap.read_text(encoding="utf-8").splitlines()[0])
        objective = d.get("objective")
        base = next((b for b in first["bases"] if b.get("name") == objective), None)
        if not base:
            continue
        obj = (base["x"], base["z"])
        plans = {}
        pf = r / "profile" / "zcr" / "attackplan.txt"
        run = json.loads((r / "run.json").read_text(encoding="utf-8"))
        if pf.exists() and "-zcrAttackPlan" in run.get("args", {}).get("extra", ""):
            for line in pf.read_text(encoding="utf-8").splitlines():
                v = line.split()
                if v and v[0] == "plan":
                    plans[(round(float(v[1])), round(float(v[2])))] = (float(v[5]), float(v[6]))
        rides, label = setup(run)
        for side in ("us", "ussr"):
            hq = next((b for b in first["bases"] if b.get("hq") and b.get("owner") == side.upper()), None)
            if not hq:
                continue
            assembly = plans.get((hq["x"], hq["z"]))
            took = bool(d.get(f"{side}_captured")) and 0 <= (d.get(f"{side}_capture_s") or -1) <= 900
            at12 = d.get(f"{side}_at_obj_12") or 0
            yield {"run": name, "objective": objective, "obj": obj, "hq": (hq["x"], hq["z"]), "rides": rides, "assembly": assembly,
                   "at8": d.get(f"{side}_at_obj_8") or 0, "at12": at12, "took": took,
                   "third": 0 <= (d.get(f"{side}_third_in_s") or -1) <= 900, "score": at12 + (10 if took else 0)}


def table(refresh: bool = False) -> dict:
    groups = defaultdict(list)
    objectives = {}
    for s in side_runs(refresh):
        objectives[s["objective"]] = {"x": s["obj"][0], "z": s["obj"][1]}
        # The same approach: an assembly point within SAME_ASSEMBLY_M of one already seen from this HQ.
        key_asm = None
        if s["assembly"]:
            for (o, hq, rides, asm) in groups:
                if o == s["objective"] and hq == s["hq"] and rides == s["rides"] and asm and same_approach(s["obj"], asm, s["assembly"]):
                    key_asm = asm
                    break
            key_asm = key_asm or s["assembly"]
        groups[(s["objective"], s["hq"], s["rides"], key_asm)].append(s)
    rows = []
    for (o, hq, rides, asm), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3] or (0, 0))):
        n = len(rs)
        mean = lambda k: round(sum(float(r[k]) for r in rs) / n, 1)
        rows.append({"objective": o, "hq": list(hq), "rides": rides, "approach": approach_name(rs[0]["obj"], asm),
                     "assembly": list(asm) if asm else None, "runs": n, "at8": mean("at8"), "at12": mean("at12"),
                     "took": sum(1 for r in rs if r["took"]), "third": sum(1 for r in rs if r["third"]), "score": mean("score")})
    return {"objective": objectives, "rows": rows}


def load() -> dict:
    p = OUT / "scores.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"objective": {}, "rows": []}


def rows_for(scores: dict, objective, hq, rides: str = "transport") -> list:
    """An HQ's rows for one objective - its name, or its (x, z) (a plans file's own name may differ, e.g. farmclose)."""
    def same(name):
        if isinstance(objective, str):
            return name.lower() == objective.lower()
        o = scores["objective"].get(name)
        return bool(o) and math.dist((o["x"], o["z"]), objective) < 100
    return [r for r in scores["rows"] if same(r["objective"]) and rides in ("all", r["rides"]) and math.dist(r["hq"], hq) < 300]


def estimate(rows: list, assembly, obj=None) -> tuple:
    """(estimated score, runs, row) for the approach with this assembly point (None = no plan) from an HQ's rows: its measured
    mean shrunk toward the HQ's no-plan mean by PRIOR_RUNS pseudo-runs; unmeasured = the no-plan mean (nothing known)."""
    base = next((r for r in rows if r["assembly"] is None), None)
    prior = base["score"] if base else (sum(r["score"] * r["runs"] for r in rows) / max(1, sum(r["runs"] for r in rows)) if rows else 0)
    if assembly is None:
        row = base
    else:
        row = next((r for r in rows if r["assembly"] and (same_approach(obj, r["assembly"], assembly) if obj
                                                          else math.dist(r["assembly"], assembly) < SAME_ASSEMBLY_M)), None)
    if not row:
        return round(prior, 1), 0, None
    k = 0 if row is base else PRIOR_RUNS
    return round((row["score"] * row["runs"] + prior * k) / (row["runs"] + k), 1), row["runs"], row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rides", default="transport", help="the ride setup shown: transport, mixed, foot or all")
    ap.add_argument("--refresh", action="store_true", help="summarize every run again (ignore the cache)")
    a = ap.parse_args()
    t = table(a.refresh)
    (OUT / "scores.json").write_text(json.dumps(t, indent=1), encoding="utf-8")
    for o in sorted(t["objective"]):
        hqs = sorted({tuple(r["hq"]) for r in t["rows"] if r["objective"] == o})
        for hq in hqs:
            rows = rows_for(t, o, hq, a.rides)
            if not rows:
                continue
            print(f"{o} from the HQ at {hq[0]:.0f},{hq[1]:.0f} ({round(math.dist(hq, (t['objective'][o]['x'], t['objective'][o]['z'])))} m):")
            for r in sorted(rows, key=lambda r: -r["score"]):
                est, _, _ = estimate(rows, r["assembly"])
                print(f"  {r['rides']:9} {r['approach']:22} runs {r['runs']:2}  at8 {r['at8']:5}  at12 {r['at12']:5}  took {r['took']}/{r['runs']}"
                      f"  3 teams {r['third']}/{r['runs']}  score {r['score']:5}  estimate {est}")
    print(f"written {OUT / 'scores.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
