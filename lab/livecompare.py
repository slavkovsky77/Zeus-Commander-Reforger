"""The live planner head to head (2 Nov night, review note 515 - Martin: "only one side can use it, the other one will not,
and we will compare"): every Farm battle of the given variants, per side - which arm it played (gemini / code: live plans
by lab/liveplan.py; rules: farm-now's way) and from which HQ (harbour: 1.1 km from Farm, south: 2.1 km; drawn per match,
and the nearer HQ wins Farm more often - so the arms are compared per HQ).

Per side and battle:
  expose_pct    [ZCR][EXPOSE] ai_seen: of its squad soldiers moving on foot (sampled every 10 s), the share an enemy
                soldier's own perception saw in the last 3 s - the whole battle, and before Farm was first taken (approach);
                expose_trace_pct the same by eye-to-eye sight lines to the 4 nearest enemies (seen=; fewer - see ZCR_Sampler)
  route_legs_pct  of its attack waypoints toward Farm, the share that came with an approach leg (a lane or live route)
  lost, killed  soldiers lost ([ZCR][LOSS]) and enemy soldiers lost
  took, took_s  whether / when it took Farm first ([ZCR][CAPTURE])
  held_s        game seconds it held Farm; owner_end who held it at the end
  at_obj_N      its soldiers within 300 m of Farm at minute N (lab/assaulttest.py)

    python lab/livecompare.py                      # farm-gemini, farm-live and farm-now runs since 2 Nov 21:00
    python lab/livecompare.py --variants farm-gemini --since 20261102-2100
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import assaulttest  # noqa: E402


def side_rows(run: Path, variant: str) -> list:
    s = assaulttest.summarize(run, "city", variant)
    if s.get("error") or not s.get("minutes"):
        return []
    log = next(iter(sorted(run.glob("logs/*/console.log"))), None)
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log else []
    live_side, picker, calls, fallbacks, problems = None, None, 0, 0, 0
    lp = run / "profile" / "zcr" / "liveplan.jsonl"
    if lp.exists():
        for l in lp.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(l)
            except ValueError:
                continue
            if e.get("event") == "side":
                live_side, picker = e["side"], e["picker"] + ("+drones" if e.get("drones") else "")
            elif e.get("source") == "gemini":
                calls += 1
                problems += len(e.get("problems") or [])
            elif e.get("source") == "code-fallback":
                calls += 1
                fallbacks += 1
    # Farm's owners over time.
    caps = []
    for l in lines:
        m = re.search(r"\[ZCR\]\[CAPTURE\] t=(\d+) base=Farm from=(\w*) to=(\w+)", l)
        if m:
            caps.append((int(m.group(1)), m.group(3)))
    end_t = int(round(s["minutes"] * 60))
    held = {"US": 0, "USSR": 0}
    owner, since = "FIA", 0
    for t, to in caps + [(end_t, None)]:
        if owner in held:
            held[owner] += max(0, t - since)
        owner, since = (to, t) if to else (owner, t)
    first_take = caps[0][0] if caps else None
    # moving, seen by an enemy's perception (ai_seen); before the first capture: moving, ai_seen; sight-line traces (seen=)
    expose = {"US": [0, 0, 0, 0, 0], "USSR": [0, 0, 0, 0, 0]}
    for l in lines:
        m = re.search(r"\[ZCR\]\[EXPOSE\] t=(\d+) side=(\w+) moving=(\d+) seen=(\d+) pct=\d+ ai_seen=(\d+)", l)
        if m and m.group(2) in expose:
            t, mv, tr, sn = int(m.group(1)), int(m.group(3)), int(m.group(4)), int(m.group(5))
            ex = expose[m.group(2)]
            ex[0] += mv
            ex[1] += sn
            ex[4] += tr
            if first_take is None or t <= first_take:
                ex[2] += mv
                ex[3] += sn
    # Attack legs on a route: AI Conflict's attack waypoints toward Farm that came with an approach leg (the plan's lane or
    # route) - the rest went straight at Farm (after rides, stuck-route recoveries, ...).
    appr, legs = set(), {"US": [0, 0], "USSR": [0, 0]}
    for l in lines:
        m = re.search(r"INFANTRY_APPROACH_ASSIGNED\] .*t_ms=(\d+) faction=(\w+) numeric_slot=(\d+)", l)
        if m:
            appr.add((m.group(1), m.group(2), m.group(3)))
    for l in lines:
        m = re.search(r"ORDER_WAYPOINT_CREATED\] .*t_ms=(\d+) faction=(\w+) slot=\w+ stable_slot=\w+ numeric_slot=(\d+) .*"
                      r"waypoint_kind=ATTACK_OPERATIONAL_MOVE .*role=ATTACK", l)
        if m and m.group(2) in legs:
            legs[m.group(2)][0] += 1
            legs[m.group(2)][1] += (m.group(1), m.group(2), m.group(3)) in appr
    rows = []
    for side in ("US", "USSR"):
        k = side.lower()
        other = "USSR" if side == "US" else "US"
        hq_m = s.get(f"{k}_hq_m")
        arm = (picker if side == live_side else "rules") if live_side else ("rules" if variant == "farm-now" else "?")
        ex = expose[side]
        rows.append({"run": run.name, "variant": variant, "side": side, "arm": arm, "hq": "harbour" if hq_m and hq_m < 1500 else "south",
                     "hq_m": hq_m, "took": s.get(f"{k}_captured"), "took_s": s.get(f"{k}_capture_s"), "held_s": held[side],
                     "owner_end": owner, "lost": s.get(f"{k}_lost"), "killed": s.get(f"{other.lower()}_lost"),
                     "expose_pct": round(100 * ex[1] / ex[0], 1) if ex[0] else None, "expose_moving": ex[0],
                     "expose_trace_pct": round(100 * ex[4] / ex[0], 1) if ex[0] else None,
                     "expose_approach_pct": round(100 * ex[3] / ex[2], 1) if ex[2] else None,
                     "at_obj_5": s.get(f"{k}_at_obj_5"), "at_obj_8": s.get(f"{k}_at_obj_8"), "at_obj_12": s.get(f"{k}_at_obj_12"),
                     "at_obj_15": s.get(f"{k}_at_obj_15"), "first_arrival_s": s.get(f"{k}_first_arrival_s"),
                     "rides_delivered": s.get(f"{k}_rides_delivered"), "rides_failed": s.get(f"{k}_rides_failed"),
                     "minutes": s["minutes"], "script_errors": s.get("script_errors"),
                     "attack_legs": legs[side][0], "route_legs_pct": round(100 * legs[side][1] / legs[side][0]) if legs[side][0] else None,
                     "model_calls": calls if side == live_side else 0, "model_fallbacks": fallbacks if side == live_side else 0,
                     "model_problems": problems if side == live_side else 0})
    return rows


def mean(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def table(rows: list) -> list:
    out = []
    for arm in ("gemini", "gemini+drones", "gemini-all", "code", "rules"):
        for hq in ("harbour", "south", "both"):
            r = [x for x in rows if (x["arm"] == arm or (arm == "gemini-all" and x["arm"].startswith("gemini")))
                 and (x["hq"] == hq or hq == "both")]
            if not r:
                continue
            out.append({"arm": arm, "hq": hq, "n": len(r), "took": sum(1 for x in r if x["took"]),
                        "took_s": mean([x["took_s"] for x in r if x["took"]]), "held_s": mean([x["held_s"] for x in r]),
                        "held_end": sum(1 for x in r if x["owner_end"] == x["side"]), "lost": mean([x["lost"] for x in r]),
                        "killed": mean([x["killed"] for x in r]), "expose_pct": mean([x["expose_pct"] for x in r]),
                        "expose_approach_pct": mean([x["expose_approach_pct"] for x in r]),
                        "at_obj_8": mean([x["at_obj_8"] for x in r]), "at_obj_12": mean([x["at_obj_12"] for x in r]),
                        "route_legs_pct": mean([x["route_legs_pct"] for x in r]),
                        "first_arrival_s": mean([x["first_arrival_s"] for x in r if x["first_arrival_s"] and x["first_arrival_s"] > 0])})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variants", default="farm-gemini,farm-gemini-routes,farm-live")
    ap.add_argument("--since", default="20261102-2100", help="run folders stamped at or after this (YYYYMMDD-HHMM)")
    ap.add_argument("--min-minutes", type=float, default=15)
    a = ap.parse_args()
    rows = []
    for v in a.variants.split(","):
        for run in sorted((ROOT / ".runtime" / "runs").glob(f"assault-city-{v}-p*")):
            m = re.search(r"-(\d{8}-\d{6})$", run.name)
            if not m or m.group(1)[:13] < a.since:
                continue
            for r in side_rows(run, v):
                if r["minutes"] >= a.min_minutes:
                    rows.append(r)
    for r in rows:
        print(f"{r['run'][-24:]} {r['side']:4} {r['arm']:6} {r['hq']:7} took={r['took']} at {r['took_s']:>5} held={r['held_s']:>4}s "
              f"end={r['owner_end']:4} lost={r['lost']:>2} killed={r['killed']:>2} expose={r['expose_pct']}% "
              f"(approach {r['expose_approach_pct']}%) at8={r['at_obj_8']} at12={r['at_obj_12']} route_legs={r['route_legs_pct']}% "
              f"calls={r['model_calls']}")
    print()
    t = table(rows)
    for x in t:
        print(f"{x['arm']:6} {x['hq']:7} n={x['n']} took {x['took']}/{x['n']} (mean {x['took_s']} s) held {x['held_s']} s, at the end "
              f"{x['held_end']}/{x['n']}; lost {x['lost']} killed {x['killed']}; seen while moving {x['expose_pct']}% "
              f"(approach {x['expose_approach_pct']}%); at Farm min 8 {x['at_obj_8']}, min 12 {x['at_obj_12']}; "
              f"attack legs on a route {x['route_legs_pct']}%")
    out = ROOT / ".runtime" / "liveplan" / "compare.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows, "table": t}, indent=1), encoding="utf-8")
    print("written", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
