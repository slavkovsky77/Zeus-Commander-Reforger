"""Why attack teams stand still with waypoints ahead (5 Nov - Martin, watching the battle for Beauregard: "I still have feeling they
dont move a lot", "but yeah I see they are defending"). Read-only: battles' console logs and live-plan files; nothing is changed.

Per attack team (role=ATTACK) on foot and per game minute, from the live team line ([ZCR][LIVE] kind=team, every 5 game s):
  moved      metres the team's leader moved in the minute; under STILL_M (15) = standing
  band       the leader's distance from the objective at the minute's start (Beauregard's base origin, 3297,2860)
  a waypoint the team has a current waypoint (wp=); its kind/storm level/radius from wpk= (the first of the queue)
Each standing minute gets ONE cause, the first that fits:
  ORDERED - somebody told the team to stand there
    wait        the general's entry for the team says go=0 ('wait' or 'support', profile/zcr/liveplan.jsonl entries)
    cover_stop  the waypoint is a live route's cover stop (defend at storm level > 0, 20 m: 'c' 15 s, 'e' 25 s; the fork's
                AICF_OrderPlanner.CreateWaypoint zcrPauseS)
    muster      AI Conflict's infantry recruitment: the team waits at a barracks for its new men (posture INFANTRY_RECRUITMENT)
    parked      a defend waypoint of AI Conflict's holds (level 0, 50 m, not the town's anchor) where the team stood when its
                stuck rule parked it: TEMPORARY_ROUTE_REPLAN_HOLD (the reliability audit's failed repair) or FIELD_HOLD (after
                its stuck checks) - AICF_MatchController, AICF_OrderPlanner.HoldPositionForTemporaryRouteReplan /
                HoldPositionForPersistentStuck; an hour's hold, its replan excludes the target beyond -aicfZcrNoHoldNearM
    town_in     the defend waypoint at the town's building anchor (AICF_BuildingAnchor - [AICF][DEFEND_ANCHOR]; the side holds
                the town, posture AREA_SECURITY, or a DEFEND_ACTION recovery leg), the leader within 150 m of the town
    town_way    the same waypoint, the leader farther out (on his way to it)
    defend      any other defend or timed hold waypoint
  NOT ORDERED - a 'go', a move waypoint ahead, still standing
    arrived     the leader within the waypoint's radius + 10 m: the leg is not complete - AI Conflict's attack legs need ALL
                the living men there (EAIWaypointCompletionType.All) - or the next leg not given yet
    fight       half or more of the minute's soldier-samples in fight behaviours (DCO_Gunner, Attack, Suppress, Observe...,
                DCO_Relocate, CQB ...)
    drone       a drone shelter run ([ZCR][SHELTER_RUN]) ended at the team in the minute
    other       the rest
Per cause: known enemies of the side within 300 m ([ZCR][KNOWN]), a loss within 150 m in the minute ([ZCR][LOSS]), stuck
detections of the team (GROUP_STUCK_DETECTED, matched by the wall clock), spread (farthest man from the leader), stances, how
long the waypoint had been current, and the behaviours (acts=).

    python lab/standstill.py RUN_DIR [RUN_DIR ...]          # a table per battle and the totals
    python lab/standstill.py RUN_DIR --json out.json        # every team-minute as JSON too
"""
import argparse
import bisect
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

OBJ = (3297.0, 2860.0)   # Beauregard's base origin (AI Conflict's objective)
STILL_M = 15
BANDS = [(0, 150, "<150"), (150, 300, "150-300"), (300, 600, "300-600"), (600, 1500, "600-1500"), (1500, 99999, ">1500")]
FIGHT = {"DCO_Gunner", "Attack", "Suppress", "SuppressGroupCluster", "ObserveThreatSystem", "MoveAndInvestigate", "ThrowGrenadeTo",
         "DCO_Relocate", "DCO_CQBMoveSlot", "DCO_CQBHold", "DCO_CQBEnter", "DCO_CQBSupport", "ObserveUnknownFire", "Retreat",
         "MoveFromUnsafeArea", "FindFirePosition"}
CAUSES = ["wait", "cover_stop", "muster", "parked", "town_in", "town_way", "defend", "arrived", "fight", "drone", "other"]
ORDERED = {"wait", "cover_stop", "muster", "parked", "town_in", "town_way", "defend"}
RE_WALL = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d+)")
RE_T = re.compile(r"\[ZCR\]\[\w+\] t=(\d+)")
RE_TEAM = re.compile(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=(\w+) id=(\d+) role=(\w+) men=(\d+) ride=(\d+) x=(-?\d+) z=(-?\d+) to=(\S+)"
                     r" posture=(\S+) wp=(\S+) wps=(\S+) wplevel=(-?\d+) wpk=(\S+) mp=(\S+) acts=(\S+)")
RE_KNOWN = re.compile(r"\[ZCR\]\[KNOWN\] t=(\d+) side=(\w+) n=(\d+) at=(\S*)")
RE_LOSS = re.compile(r"\[ZCR\]\[LOSS\] t=(\d+) .*?side=(\w+) kind=man .*? x=(-?\d+) z=(-?\d+)")
RE_SHELTER = re.compile(r"\[ZCR\]\[SHELTER_RUN\] t=(\d+) side=(\w+) .*? x=(-?\d+) z=(-?\d+)")
RE_SEIZE = re.compile(r"\[ZCR\]\[SEIZE\] t=(\d+) .*owner=(\w+)")
RE_GSD = re.compile(r"\[GROUP_STUCK_DETECTED\].*? faction=(\w+) slot=(\d+) role=ATTACK")
RE_ANCHOR = re.compile(r"\[DEFEND_ANCHOR\].*? anchor=(-?\d+) (-?\d+)")
RE_REPLAN = re.compile(r"\[FALSE_COMPLETION_ROUTE_REPLAN\].*? faction=(\w+) .*?numeric_slot=(\d+) .*?replanned=(\d)")


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def band_of(d):
    for lo, hi, name in BANDS:
        if lo <= d < hi:
            return name
    return ">1500"


def wall_s(line):
    m = RE_WALL.match(line)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def parse_team(m):
    t, side, tid, role, men, ride, x, z, to, posture, wp, wps, wplevel, wpk, mp, acts = m.groups()
    members = []
    for e in mp.split(";"):
        p = e.split(",")
        if len(p) == 3:
            members.append((float(p[0]), float(p[1]), p[2]))
    kinds = []
    for e in wpk.split(";"):
        p = e.split("/")
        if len(p) == 3:
            kinds.append((p[0], int(p[1]), int(p[2])))
    a = {}
    for e in acts.split(","):
        if ":" in e:
            k, v = e.rsplit(":", 1)
            a[k] = a.get(k, 0) + int(v)
    w = tuple(float(v) for v in wp.split(",")) if wp != "-" else None
    return {"t": int(t), "side": side, "id": int(tid), "role": role, "men": int(men), "ride": int(ride), "x": float(x), "z": float(z),
            "posture": posture, "wp": w, "wplevel": int(wplevel), "kinds": kinds, "members": members, "acts": a}


def new_session():
    return {"teams": defaultdict(list), "known": defaultdict(list), "losses": [], "shelter": [], "owner": [], "stuck": [], "anchors": [],
            "clock": [], "replans": []}


def load_log(path: Path):
    """The log's battle: a mission restarted in the same log (the game time back to ~0, the 17:45 battle at 18:54) starts a
    new session; the one with the most team lines is kept."""
    sessions = [new_session()]
    d = sessions[0]
    last_wall = None
    last_t = -1
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            zcr = "[ZCR][" in line
            if not zcr and "GROUP_STUCK_DETECTED" not in line and "DEFEND_ANCHOR" not in line and "FALSE_COMPLETION_ROUTE_REPLAN" not in line:
                continue
            w = wall_s(line)
            if w is not None:
                if last_wall is not None and w < last_wall - 3600:   # past midnight
                    w += 86400
                last_wall = w
            if zcr:
                mt = RE_T.search(line)
                if mt:
                    t = int(mt.group(1))
                    if t < last_t - 300:
                        sessions.append(new_session())
                        d = sessions[-1]
                    last_t = t
                    if w is not None and (not d["clock"] or d["clock"][-1][0] != w):
                        d["clock"].append((w, t))
            if "kind=team" in line:
                m = RE_TEAM.search(line)
                if m:
                    r = parse_team(m)
                    d["teams"][(r["side"], r["id"])].append(r)
                continue
            m = RE_KNOWN.search(line)
            if m:
                pts = []
                for e in m.group(4).split(";"):
                    p = e.split(",")
                    if len(p) == 2:
                        pts.append((float(p[0]), float(p[1])))
                d["known"][m.group(2)].append((int(m.group(1)), pts))
                continue
            m = RE_LOSS.search(line)
            if m:
                d["losses"].append((int(m.group(1)), m.group(2), float(m.group(3)), float(m.group(4))))
                continue
            m = RE_SHELTER.search(line)
            if m:
                d["shelter"].append((int(m.group(1)), m.group(2), float(m.group(3)), float(m.group(4))))
                continue
            m = RE_SEIZE.search(line)
            if m:
                if not d["owner"] or d["owner"][-1][1] != m.group(2):
                    d["owner"].append((int(m.group(1)), m.group(2)))
                continue
            m = RE_GSD.search(line)
            if m and w is not None:
                d["stuck"].append((w, m.group(1), int(m.group(2))))
                continue
            m = RE_ANCHOR.search(line)
            if m:
                d["anchors"].append((float(m.group(1)), float(m.group(2))))
                continue
            m = RE_REPLAN.search(line)
            if m and w is not None:
                d["replans"].append((w, m.group(1), int(m.group(2)), int(m.group(3))))
    d = max(sessions, key=lambda x: sum(len(v) for v in x["teams"].values()))
    # AI Conflict's lines carry the wall clock only (its t_ms is not the game time): to game seconds by the ZCR lines around
    walls = [c[0] for c in d["clock"]]
    stuck = []
    for w, side, slot in d["stuck"]:
        i = bisect.bisect_left(walls, w)
        if 0 <= i < len(walls):
            stuck.append((d["clock"][i][1], side, slot))
    d["stuck"] = stuck
    replans = []
    for w, side, slot, ok in d["replans"]:
        i = bisect.bisect_left(walls, w)
        if 0 <= i < len(walls):
            replans.append((d["clock"][i][1], side, slot, ok))
    d["replans"] = replans
    return d


def load_plan(path: Path):
    """side -> sorted [(t, entries, orders, status)] from liveplan.jsonl."""
    plan = defaultdict(list)
    if not path.exists():
        return plan
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if "t" not in r or "side" not in r:
                continue
            plan[r["side"]].append((r["t"], r.get("entries", {}), r.get("orders", {}), r.get("teams", {})))
    for s in plan:
        plan[s].sort(key=lambda x: x[0])
    return plan


def latest(seq, t):
    lo, hi, best = 0, len(seq) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if seq[mid][0] <= t:
            best = seq[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def minutes(run: Path):
    logs = sorted(run.glob("logs/logs_*/console.log"))
    if not logs:
        return [], None
    d = load_log(logs[-1])
    plan = load_plan(run / "profile" / "zcr" / "liveplan.jsonl")
    town_anchor = next((a for a in d["anchors"] if dist(a, OBJ) < 150), None)
    out = []
    for (side, tid), rows in d["teams"].items():
        rows = [r for r in rows if r["role"] == "ATTACK"]
        if len(rows) < 2:
            continue
        since = {}
        wp_from, prev_wp = rows[0]["t"], rows[0]["wp"]
        for r in rows:
            if r["wp"] != prev_wp:
                wp_from, prev_wp = r["t"], r["wp"]
            since[r["t"]] = r["t"] - wp_from
        i = 0
        while i < len(rows):
            r0 = rows[i]
            j = i
            while j < len(rows) and rows[j]["t"] < r0["t"] + 60:
                j += 1
            if j >= len(rows) or rows[j]["t"] - r0["t"] > 70:
                i = j if j > i else i + 1
                continue
            r1, win, i = rows[j], rows[i:j], j
            if r0["ride"] or r1["ride"] or any(m[2] == "v" for m in r0["members"] + r1["members"]):
                continue
            if r1["men"] > r0["men"]:      # a new team in the slot
                continue
            lead0, lead1 = (r0["x"], r0["z"]), (r1["x"], r1["z"])
            moved = dist(lead0, lead1)
            if moved > 400:
                continue
            d_obj = dist(lead0, OBJ)
            k0 = r0["kinds"][0] if r0["kinds"] else ("-", 0, 0)
            rec = {"run": run.name, "side": side, "id": tid, "t": r0["t"], "band": band_of(d_obj), "d_obj": round(d_obj),
                   "moved": round(moved, 1), "men": r0["men"], "posture": r0["posture"], "wp": r0["wp"], "kind": k0[0], "klevel": k0[1],
                   "kradius": k0[2], "nwps": len(r0["kinds"])}
            rec["wp_m"] = round(dist(lead0, r0["wp"])) if r0["wp"] else None
            rec["anchor"] = bool(town_anchor and r0["wp"] and dist(r0["wp"], town_anchor) < 6)
            rec["wp_age"] = since.get(r0["t"], 0)
            rec["spread"] = round(max((dist(lead0, (m[0], m[1])) for m in r0["members"]), default=0))
            st, acts = Counter(), Counter()
            for w in win:
                for m in w["members"]:
                    st[m[2]] += 1
                for k, v in w["acts"].items():
                    acts[k] += v
            rec["stance"], rec["acts"] = dict(st), dict(acts)
            rec["men_moved"] = (sum(1 for a, b in zip(r0["members"], r1["members"]) if dist(a, b) >= STILL_M)
                                if len(r0["members"]) == len(r1["members"]) else None)
            row = latest(plan.get(side, []), r0["t"])
            entry = order = status = None
            if row and r0["t"] - row[0] <= 120:
                entry = row[1].get(str(tid))
                o = row[2].get(str(tid))
                order = o.get("order") if o else None
                status = row[3].get(str(tid))
            rec["go"] = entry.get("go") if entry else None
            rec["order"], rec["status"] = order, status
            k = latest(d["known"].get(side, []), r0["t"])
            rec["known_m"] = round(min(dist(lead0, p) for p in k[1])) if k and r0["t"] - k[0] <= 90 and k[1] else None
            pts = [(m[0], m[1]) for m in r0["members"]] or [lead0]
            rec["losses"] = sum(1 for (lt, ls, lx, lz) in d["losses"]
                                if ls == side and r0["t"] <= lt < r0["t"] + 60 and min(dist((lx, lz), p) for p in pts) < 150)
            rec["shelter"] = sum(1 for (st_, ss, sx, sz) in d["shelter"]
                                 if ss == side and r0["t"] <= st_ < r0["t"] + 75 and min(dist((sx, sz), p) for p in pts) < 60)
            ow = latest(d["owner"], r0["t"])
            rec["owner"] = ow[1] if ow else "-"
            rec["stuck"] = sum(1 for (st_, s_, sl) in d["stuck"] if s_ == side and sl == tid and r0["t"] <= st_ < r0["t"] + 60)
            rec["cause"] = cause(rec)
            out.append(rec)
    # AI Conflict's replan after a temporary hold (ResumeAfterFalseCompletionHold): by the team's distance from the town
    # (its target is excluded beyond -aicfZcrNoHoldNearM, 450 m) and posture
    replans = Counter()
    for t, side, slot, ok in d["replans"]:
        rows = [r for r in d["teams"].get((side, slot), []) if r["t"] <= t and r["role"] == "ATTACK"]
        if rows and t - rows[-1]["t"] <= 120:
            r = rows[-1]
            far = ">450" if dist((r["x"], r["z"]), OBJ) > 450 else "<=450"
            replans[(far, "holder" if r["posture"] == "AREA_SECURITY" else "attacker", ok)] += 1
    return out, town_anchor, replans


def cause(r):
    acts = r["acts"]
    total = sum(acts.values()) or 1
    if r["go"] == 0:
        return "wait"
    if r["kind"] == "defend" and r["klevel"] > 0 and r["kradius"] <= 20:
        return "cover_stop"
    if r["posture"] == "INFANTRY_RECRUITMENT":
        return "muster"
    if r["kind"] == "defend" and r["klevel"] == 0 and r["kradius"] == 50 and not r["anchor"]:
        return "parked"
    if r["anchor"]:
        return "town_in" if r["d_obj"] < 150 else "town_way"
    if r["kind"] in ("defend", "hold"):
        return "defend"
    if r["wp_m"] is not None and r["wp_m"] <= r["kradius"] + 10:
        return "arrived"
    if sum(v for k_, v in acts.items() if k_ in FIGHT) >= 0.5 * total:
        return "fight"
    if r["shelter"] > 0:
        return "drone"
    return "other"


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else 0


def table(recs, label, groups=(("300-600 m", ("300-600",)), ("inside 300 m", ("150-300", "<150")))):
    print(f"\n=== {label}: {len(recs)} team-minutes of attack teams on foot with a waypoint")
    for lo, hi, name in BANDS[::-1]:
        b = [r for r in recs if r["band"] == name]
        if b:
            still = [r for r in b if r["moved"] < STILL_M]
            mv = [r["moved"] / 60 for r in b if r["moved"] >= STILL_M]
            print(f"  {name:>9}: {len(b):5} min, standing {len(still):5} ({pct(len(still), len(b)):3.0f}%), moving at a median "
                  f"{med(mv):.2f} m/s")
    for gname, bands in groups:
        b = [r for r in recs if r["band"] in bands]
        still = [r for r in b if r["moved"] < STILL_M]
        if not still:
            continue
        holder = sum(1 for r in still if r["posture"] == "AREA_SECURITY")
        print(f"\n  -- {gname}: {len(still)} standing team-minutes of {len(b)}; ordered "
              f"{pct(sum(1 for r in still if r['cause'] in ORDERED), len(still)):.0f}%, of the side holding the town "
              f"(posture AREA_SECURITY) {pct(holder, len(still)):.0f}%")
        c = Counter(r["cause"] for r in still)
        for k in CAUSES:
            n = c.get(k, 0)
            if not n:
                continue
            sub = [r for r in still if r["cause"] == k]
            acts, st = Counter(), Counter()
            for r in sub:
                acts.update(r["acts"])
                st.update(r["stance"])
            at, stt = sum(acts.values()) or 1, sum(st.values()) or 1
            kn = sum(1 for r in sub if r["known_m"] is not None and r["known_m"] < 300)
            print(f"    {'ORDERED' if k in ORDERED else 'GO':7} {k:10} {n:5} ({pct(n, len(still)):3.0f}%)  holder {pct(sum(1 for r in sub if r['posture'] == 'AREA_SECURITY'), n):3.0f}%"
                  f"  known<300m {pct(kn, n):3.0f}%  loss {pct(sum(1 for r in sub if r['losses']), n):3.0f}%"
                  f"  stuck-check {pct(sum(1 for r in sub if r['stuck']), n):3.0f}%  spread>60m {pct(sum(1 for r in sub if r['spread'] > 60), n):3.0f}%"
                  f"  same wp {med([r['wp_age'] for r in sub])} s  prone {pct(st.get('p', 0), stt):.0f}% crouch {pct(st.get('c', 0), stt):.0f}%")
            print(f"            {', '.join(f'{a} {pct(v, at):.0f}%' for a, v in acts.most_common(6))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--json")
    a = ap.parse_args()
    allrecs = []
    for rd in a.runs:
        run = Path(rd)
        recs, anchor, replans = minutes(run)
        recs = [r for r in recs if r["wp"] is not None]
        where = f"{anchor}, {dist(anchor, OBJ):.0f} m from the town's centre" if anchor else "none logged"
        table(recs, f"{run.name} (the town's defend anchor {where})")
        for far in (">450", "<=450"):
            for who in ("holder", "attacker"):
                n, ok = replans.get((far, who, 0), 0) + replans.get((far, who, 1), 0), replans.get((far, who, 1), 0)
                if n:
                    print(f"  replans after a temporary hold, {far} m out, {who}: {ok} of {n} gave the team a new order")
        allrecs += recs
    if len(a.runs) > 1:
        table(allrecs, "all battles")
    if a.json:
        Path(a.json).write_text(json.dumps(allrecs), encoding="utf-8")


if __name__ == "__main__":
    main()
