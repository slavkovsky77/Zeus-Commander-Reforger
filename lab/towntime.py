"""The battle for Beauregard minute by minute (5 Nov night - Martin, watching: "why no side captures point yet?", "it takes some
time that ai basically fails to attack storm and get units to front", "like it degrades with time? too many drone team? too
many vehicles I dont know?", "maybe some soldiers are unconscious?", "i saw them stuck in one house").

Per town battle (lab/assaulttest.py beauregard: town-brains, town-vs-rules, town-forts, town-nodoor) and per game minute:
  att300/att150/att60   attack-team soldiers (role=ATTACK) within 300 / 150 / 60 m of Beauregard (3297,2860), US+USSR,
                        from each soldier's position on the live team line ([ZCR][LIVE] kind=team mp=)
  prone / unc / veh     of all attack soldiers: lying prone (p), unconscious (u, battles from 5 Nov 00:57), in a vehicle (v)
  react                 men reacting to drones ([ZCR][DRONETHREAT] reacting=, both sides)
  fps / ai / aich       the server's FPS line: FPS (the minute's lowest), AI agents (AI:), character agents (AIChar:)
  veh                   vehicles (Veh:)
  air / launch          drones in the air ([ZCR][DRONEAIR] air=), drone teams launched so far ([ZCR][DRONES] team= kind=)
  aboard                riders aboard ([ZCR][RIDING] aboard=)
  stuck                 vehicles stuck or jammed ([ZCR][DRIVE] stuck= + jammed=) and still-vehicle pushes ([ZCR][UNJAM])
  lost                  soldiers lost so far ([ZCR][LOSS] kind=man)
  AI Conflict's order repair (per minute; the coordinator's lead from team A0 at the end of 20261105-003457):
  wpf                   WAYPOINT_MOVE_FAILED (ORDER_RESTORE_REQUESTED reason=WAYPOINT_MOVE_FAILED)
  rec / recd            ORDER_RECOVERY_ISSUED / of them a DEFEND_ACTION waypoint (ORDER_WAYPOINT_CREATED reason=ORDER_RECOVERY)
  fcr                   FALSE_COMPLETION_ROUTE_REPLAN
  gsd                   GROUP_STUCK_DETECTED
  imf                   INFANTRY_MOVE_FAILED reason=STUCK (a group's move failed as stuck within seconds)
  far / mid             attack soldiers more than 1500 m from the point (at or near their HQ) / 300-1500 m
  frz / frzN            attack soldiers on foot in a team that moved less than 25 m in the last 3 minutes, more than 150 m from
                        the point / of them within 150-500 m (stopped short of the town)
  nowp                  attack soldiers in a team with no waypoint at all (wp=-)
  fhm                   soldiers of the slots (any role) whose last SLOT_ACTIVITY says PERSISTENT_STUCK_FIELD_HOLD
  mgd / sup             soldiers in AI Conflict's squads (FORCE_HEARTBEAT managed_agents) / all others (AIChar - mgd: builders,
                        truck and armour crews, drone operators) - with -aicfCapCountsAll the others count against the side cap
  rblk                  REINFORCEMENT_BLOCKED reason=FACTION_LIMIT (a dead squad not respawned: the side is at its cap)
  pact                  attack men whose current behaviour is a PerformAction or a door behaviour (opening a navlink door; acts=,
                        battles from 5 Nov 00:57)
  dtprn                 men lying prone by the drone reaction ([ZCR][DRONETHREAT] prone=, both sides)
  fh / trh              attack slots whose last SLOT_ACTIVITY says PERSISTENT_STUCK_FIELD_HOLD / TEMPORARY_ROUTE_REPLAN_HOLD

    python lab/towntime.py                      # every town battle since 4 Nov 02:00: a table per battle, then the summary
    python lab/towntime.py --summary            # only the summary (5-minute bins, early-fall v stalled, correlations)
    python lab/towntime.py RUN_DIR [RUN_DIR..]  # these battles
    python lab/towntime.py --json out.json      # every battle's minutes as JSON too
"""
import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / ".runtime" / "runs"
OBJ = (3297.0, 2860.0)   # Beauregard
SIDES = ("US", "USSR")
SINCE = "20261104-0200"
EARLY_S = 16 * 60        # "fell early": the town taken by game minute 16 (as in 5 of the first 6 battles of 4 Nov)

RE_WALL = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d+)")
RE_T = re.compile(r"\[ZCR\]\[\w+\] t=(\d+)")
RE_TEAM = re.compile(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=(\w+) id=(\d+) role=(\w+) men=(\d+) ride=(\d+) x=(-?\d+) z=(-?\d+) to=(\S+) posture=(\S+)")
RE_FPS = re.compile(r"FPS: ([\d.]+),.*? AI: (\d+), AIChar: (\d+), Veh: (\d+) \((\d+)\)")


def wall_s(line: str):
    m = RE_WALL.match(line)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 10 ** len(m.group(4)) if m else None


def kv(line: str, key: str, cast=int, default=None):
    m = re.search(r"(?:^|\s)" + key + r"=(-?[\w.]+)", line)
    if not m:
        return default
    try:
        return cast(m.group(1))
    except ValueError:
        return default


def meta(run: Path) -> dict:
    d = {"run": run.name, "variant": next((v for v in ("town-brains", "town-vs-rules", "town-forts", "town-nodoor")
                                            if f"-{v}-" in run.name), "?"), "watched": "-watch-" in run.name}
    try:
        r = json.loads((run / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        r = {}
    extra = (r.get("args") or {}).get("extra", "")
    d.update(commit=(r.get("commit") or "")[:7], dirty=r.get("dirty"), started=r.get("started", ""),
             nodoor="-zcrNoDoorReaction" in extra, relentless="-zcrStormRelentless" in extra,
             stations="-fpvaiKeepStations" in extra)
    m = re.search(r"-zcrSpeed ([\d.]+)", extra)
    d["speed"] = float(m.group(1)) if m else 1.0
    return d


def parse(run: Path) -> dict:
    """One battle: its meta and a dict minute -> measures."""
    log = next(iter(sorted(run.glob("logs/*/console.log"))), None)
    out = meta(run)
    if not log:
        out["error"] = "no console.log"
        return out
    mins = defaultdict(lambda: defaultdict(float))
    teams = {}          # current snapshot: (side, id) -> parsed team, for the snapshot at snap_t
    track = defaultdict(list)   # (side, id) -> [(t, x, z)] team centres, for the 'frozen' measure
    centre = defaultdict(dict)  # (side, id) -> {minute: (distance to the point, on foot)}, for the closing speed
    snap_t = None
    slot_state = {}     # (faction, numeric slot) -> (role, allowed_idle_reason, alive)
    last_wall = last_t = None
    day = 0
    prev_wall = None
    door_error = False
    first_cap = None
    cap_by = ""
    launched = 0
    lost = {"US": 0, "USSR": 0}
    acts_near = defaultdict(lambda: defaultdict(int))   # minute -> behaviour -> attack men within 300 m
    acts_all = defaultdict(lambda: defaultdict(int))    # minute -> behaviour -> attack men anywhere (summed over the minute's last snapshot)
    speed = out["speed"]
    anchor = None
    last_minute = -1

    def close_snapshot():
        if snap_t is None or not teams:
            return
        m = snap_t // 60
        row = mins[m]
        for k in [k for k in row if k.startswith("_s_")]:
            row[k] = 0
        a = defaultdict(float)
        acts = defaultdict(int)
        acts_all[m] = defaultdict(int)
        for (side, _), tm in teams.items():
            if tm["role"] != "ATTACK":
                continue
            a["att_men"] += tm["men"]
            cx = sum(x for x, _, _ in tm["mp"]) / len(tm["mp"])
            cz = sum(z for _, z, _ in tm["mp"]) / len(tm["mp"])
            hist = track[(side, _)]
            hist.append((snap_t, cx, cz))
            while hist and hist[0][0] < snap_t - 400:
                hist.pop(0)
            old = [h for h in hist if h[0] <= snap_t - 180]
            cd = math.hypot(cx - OBJ[0], cz - OBJ[1])
            centre[(side, _)][m] = (cd, not any(st == "v" for _, _, st in tm["mp"]))
            if old and not any(st == "v" for _, _, st in tm["mp"]) and cd > 150:
                if math.hypot(cx - old[-1][1], cz - old[-1][2]) < 25:
                    a["frz"] += tm["men"]
                    if cd <= 500:
                        a["frzN"] += tm["men"]
            if tm.get("nowp"):
                a["nowp"] += tm["men"]
            for (x, z, st) in tm["mp"]:
                dist = math.hypot(x - OBJ[0], z - OBJ[1])
                a["prone"] += st == "p"
                a["unc"] += st == "u"
                a["veh"] += st == "v"
                if dist > 1500:
                    a["far"] += 1
                elif dist > 300:
                    a["mid"] += 1
                if dist <= 300:
                    a["att300"] += 1
                    a[f"att300_{side}"] += 1
                    a["prone300"] += st == "p"
                    a["unc300"] += st == "u"
                if dist <= 150:
                    a["att150"] += 1
                    a[f"att150_{side}"] += 1
                if dist <= 60:
                    a["att60"] += 1
                    a[f"att60_{side}"] += 1
            for k, n in tm["acts"].items():
                if "PerformAction" in k or "Door" in k:
                    a["pact"] += n
                acts_all[m][k] += n
            if tm["acts"] and any(math.hypot(x - OBJ[0], z - OBJ[1]) <= 300 for x, z, _ in tm["mp"]):
                for k, n in tm["acts"].items():
                    acts[k] += n
        for k in ("att_men", "att300", "att150", "att60", "prone", "unc", "veh", "prone300", "unc300", "pact", "far", "mid", "frz", "frzN", "nowp",
                  "att300_US", "att300_USSR", "att150_US", "att150_USSR", "att60_US", "att60_USSR"):
            row[k] = a.get(k, 0)
        acts_near[m] = acts

    with open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            w = wall_s(line)
            if w is not None:
                if prev_wall is not None and w + day * 86400 < prev_wall - 43200:
                    day += 1
                w += day * 86400
                prev_wall = w
            if "OpenNavlinkDoor" in line and "Unknown class" in line:
                door_error = True
            mt = RE_T.search(line)
            if mt:
                t = int(mt.group(1))
                if w is not None:
                    last_wall, last_t = w, t
                    # the game's speed from the [ZCR] clock itself (watched battles run at 2-3x, whatever -zcrSpeed said)
                    if anchor is None:
                        anchor = (w, t)
                    elif w - anchor[0] >= 20:
                        speed = min(5.0, max(0.2, (t - anchor[1]) / (w - anchor[0])))
                        anchor = (w, t)
            elif last_t is not None and w is not None:
                t = int(last_t + max(0.0, w - last_wall) * speed)
            else:
                continue
            m = t // 60
            last_minute = max(last_minute, m)
            row = mins[m]
            if "[ZCR][LIVE]" in line and "kind=team" in line:
                mm = RE_TEAM.search(line)
                if not mm:
                    continue
                tt = int(mm.group(1))
                if tt != snap_t:
                    close_snapshot()
                    teams = {}
                    snap_t = tt
                side, tid, role, men = mm.group(2), mm.group(3), mm.group(4), int(mm.group(5))
                mp = []
                pm = re.search(r" mp=(\S*)", line)
                if pm and pm.group(1) not in ("", "-"):
                    for p in pm.group(1).split(";"):
                        bits = p.split(",")
                        if len(bits) >= 3:
                            try:
                                mp.append((float(bits[0]), float(bits[1]), bits[2]))
                            except ValueError:
                                pass
                if not mp:
                    mp = [(float(mm.group(7)), float(mm.group(8)), "?")] * men
                acts = {}
                am = re.search(r" acts=(\S+)", line)
                if am and am.group(1) != "-":
                    for p in am.group(1).split(","):
                        if ":" in p:
                            k, n = p.rsplit(":", 1)
                            acts[k] = int(n) if n.isdigit() else 0
                teams[(side, tid)] = {"role": role, "men": men, "mp": mp, "acts": acts, "nowp": " wp=- " in line}
            elif "FPS:" in line and "AIChar" in line:
                mf = RE_FPS.search(line)
                if mf:
                    fps = float(mf.group(1))
                    row["fps"] = min(row["fps"], fps) if row.get("fps") else fps
                    row["fps_sum"] += fps
                    row["fps_n"] += 1
                    row["ai"] = int(mf.group(2))
                    row["aich"] = int(mf.group(3))
                    row["vehs"] = int(mf.group(4))
            elif "[ZCR][DRONETHREAT]" in line and " side=" in line and "reacting=" in line:
                s = kv(line, "side", str)
                row[f"react_{s}"] = kv(line, "reacting", int, 0)
                row[f"dtprone_{s}"] = kv(line, "prone", int, 0)
            elif "[ZCR][DRONEAIR]" in line:
                s = kv(line, "side", str)
                row[f"air_{s}"] = max(row.get(f"air_{s}", 0), kv(line, "air", int, 0))
            elif "[ZCR][DRONES]" in line and " team=" in line and " kind=" in line:
                launched += 1
                row["launches"] += 1
            elif "[ZCR][RIDING]" in line:
                s = kv(line, "side", str)
                row[f"aboard_{s}"] = kv(line, "aboard", int, 0)
            elif "[ZCR][DRIVE]" in line and " side=" in line:
                s = kv(line, "side", str)
                row[f"stuck_{s}"] = kv(line, "stuck", int, 0) + kv(line, "jammed", int, 0)
            elif "[ZCR][UNJAM]" in line:
                row["unjam"] += 1
            elif "[ZCR][LOSS]" in line and "kind=man" in line:
                s = kv(line, "side", str)
                if s in lost:
                    lost[s] += 1
            elif "[ZCR][SEIZE]" in line and "base=Beauregard" in line and "event=taken" in line:
                if first_cap is None:
                    first_cap, cap_by = t, kv(line, "by", str, "")
                row["taken"] += 1
            elif "[ZCR][CAPTURE]" in line and "base=Beauregard" in line:
                if first_cap is None:
                    first_cap, cap_by = t, kv(line, "to", str, "")
            elif "[ZCR][POP]" in line:
                for s in SIDES:
                    row[f"foot_{s}"] = kv(line, f"{s.lower()}_foot", int, 0)
            elif "[ZCR][CENSUS]" in line and "orphan_waypoints=" in line:
                row["orphan_wp"] = kv(line, "orphan_waypoints", int, 0)
            elif "[AICF]" in line:
                if "[ORDER_RESTORE_REQUESTED]" in line and "reason=WAYPOINT_MOVE_FAILED" in line:
                    row["wpf"] += 1
                elif "[ORDER_RECOVERY_ISSUED]" in line:
                    row["rec"] += 1
                elif "[ORDER_WAYPOINT_CREATED]" in line and "reason=ORDER_RECOVERY" in line and "waypoint_kind=DEFEND_ACTION" in line:
                    row["recd"] += 1
                elif "[FALSE_COMPLETION_ROUTE_REPLAN]" in line:
                    row["fcr"] += 1
                elif "[FORCE_HEARTBEAT]" in line:
                    row["mgd"] = kv(line, "managed_agents", int, 0)
                elif "[REINFORCEMENT_BLOCKED]" in line:
                    row["rblk"] += 1
                elif "[GROUP_STUCK_DETECTED]" in line:
                    row["gsd"] += 1
                elif "[INFANTRY_MOVE_FAILED]" in line and "reason=STUCK" in line:
                    row["imf"] += 1
                elif "[GROUP_STUCK_FIELD_HOLD]" in line:
                    row["fhe"] += 1
                elif "[SLOT_ACTIVITY]" in line:
                    slot_state[(kv(line, "faction", str), kv(line, "numeric_slot", str))] = (kv(line, "role", str), kv(line, "allowed_idle_reason", str), kv(line, "alive", int, 0))
                    row["fh"] = sum(1 for r, why, _ in slot_state.values() if r == "ATTACK" and why == "PERSISTENT_STUCK_FIELD_HOLD")
                    row["fhm"] = sum(n for _, why, n in slot_state.values() if why == "PERSISTENT_STUCK_FIELD_HOLD")
                    row["trh"] = sum(1 for r, why, _ in slot_state.values() if r == "ATTACK" and why == "TEMPORARY_ROUTE_REPLAN_HOLD")
            row["launched"] = launched
            row["lost"] = lost["US"] + lost["USSR"]
    close_snapshot()
    out["door_class_error"] = door_error
    out["door"] = not door_error and not out["nodoor"]
    out["first_cap_s"] = first_cap
    out["cap_by"] = cap_by
    out["last_min"] = last_minute
    res = {}
    for m in sorted(mins):
        r = mins[m]
        if r.get("fps_n"):
            r["fps_mean"] = r["fps_sum"] / r["fps_n"]
        r["react"] = r.get("react_US", 0) + r.get("react_USSR", 0)
        r["dtprn"] = r.get("dtprone_US", 0) + r.get("dtprone_USSR", 0)
        r["air"] = r.get("air_US", 0) + r.get("air_USSR", 0)
        r["aboard"] = r.get("aboard_US", 0) + r.get("aboard_USSR", 0)
        r["stuck"] = r.get("stuck_US", 0) + r.get("stuck_USSR", 0)
        res[m] = {k: v for k, v in r.items() if not k.startswith("fps_s") and k != "fps_n"}
    # carry the last value forward for state measures sampled less often than every minute
    for k in ("ai", "aich", "vehs", "fh", "fhm", "trh", "orphan_wp", "mgd"):
        last = None
        for m in sorted(res):
            if k in res[m]:
                last = res[m][k]
            elif last is not None:
                res[m][k] = last
    for m in res:
        if res[m].get("aich") is not None and res[m].get("mgd") is not None:
            res[m]["sup"] = res[m]["aich"] - res[m]["mgd"]
    out["minutes"] = res
    out["acts_near"] = {m: dict(v) for m, v in acts_near.items() if v}
    out["acts_all"] = {m: dict(v) for m, v in acts_all.items() if v}
    # Closing speed: metres a team on foot got closer to the point in a game minute, by where it was (minutes 0-30).
    closing = {}
    for lo, hi in CLOSING_BANDS:
        steps = [d - nxt[0] for mins_ in centre.values() for mm, (d, foot) in mins_.items()
                 if mm < 30 and foot and lo <= d < hi and (nxt := mins_.get(mm + 1)) and nxt[1]]
        closing[f"{lo}-{hi}"] = (round(sum(steps) / len(steps), 1), len(steps)) if steps else (None, 0)
    out["closing"] = closing
    return out


COLS = [("att300", "a300"), ("att150", "a150"), ("att60", "a60"), ("att_men", "attm"), ("mid", "mid"), ("far", "far"),
        ("frz", "frz"), ("frzN", "frzN"), ("nowp", "nowp"), ("prone", "prn"), ("unc", "unc"),
        ("veh", "inveh"), ("react", "react"), ("dtprn", "dtprn"), ("fps", "fps"), ("ai", "AI"), ("aich", "AIch"), ("vehs", "veh"), ("air", "air"),
        ("launched", "lnch"), ("aboard", "abrd"), ("stuck", "stk"), ("unjam", "unjam"), ("lost", "lost"),
        ("mgd", "mgd"), ("sup", "sup"), ("rblk", "rblk"), ("wpf", "wpf"), ("rec", "rec"), ("recd", "recD"), ("fcr", "fcr"), ("gsd", "gsd"), ("imf", "imf"), ("fh", "fh"), ("fhm", "fhm"), ("trh", "trh"), ("pact", "pact")]


def fmt(v):
    if v is None or v == "":
        return "."
    if isinstance(v, float):
        return f"{v:.0f}" if abs(v - round(v)) < 1e-9 or abs(v) >= 10 else f"{v:.1f}"
    return str(v)


def table(b: dict) -> str:
    cap = f"taken at {b['first_cap_s'] / 60:.1f} min by {b['cap_by']}" if b.get("first_cap_s") is not None else "not taken"
    head = (f"== {b['run']}  [{b['variant']}{' watched' if b['watched'] else ''}] commit {b.get('commit')} door="
            f"{'on' if b['door'] else 'OFF'}{' (switch)' if b.get('nodoor') else ''}{' relentless' if b.get('relentless') else ''}"
            f"  {b['last_min'] + 1} min, {cap}")
    lines = [head, "min " + " ".join(f"{c:>5}" for _, c in COLS) + "  a300 US/USSR"]
    for m, r in sorted(b["minutes"].items()):
        lines.append(f"{m:>3} " + " ".join(f"{fmt(r.get(k)):>5}" for k, _ in COLS)
                     + f"  {fmt(r.get('att300_US', 0))}/{fmt(r.get('att300_USSR', 0))}")
    acts = b.get("acts_near") or {}
    if acts:
        lines.append("attack men within 300 m by current behaviour (acts=), every 5th minute:")
        for m in sorted(acts):
            if m % 5 == 4:
                lines.append(f"  min {m}: " + ", ".join(f"{k} {n}" for k, n in sorted(acts[m].items(), key=lambda x: -x[1])[:8]))
    return "\n".join(lines)


def pearson(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else None


def summary(battles: list) -> str:
    out = []
    full = [b for b in battles if b.get("minutes") and b["last_min"] >= 14 and b["variant"] != "town-forts"]
    keys = [k for k, _ in COLS]
    bins = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 45), (45, 60)]

    def binmean(group, k, lo, hi):
        vals = [b["minutes"][m].get(k) for b in group for m in b["minutes"] if lo <= m < hi and b["minutes"][m].get(k) is not None]
        return sum(vals) / len(vals) if vals else None

    for name, group in (("all battles (not town-forts, 15+ min)", full),
                        ("fell early (taken by min 16)", [b for b in full if b.get("first_cap_s") is not None and b["first_cap_s"] <= EARLY_S]),
                        ("stalled (not taken by min 16)", [b for b in full if b.get("first_cap_s") is None or b["first_cap_s"] > EARLY_S])):
        out.append(f"-- {name}: {len(group)} battles - mean per minute in each 5-minute bin")
        out.append("game min  " + " ".join(f"{c:>5}" for _, c in COLS))
        for lo, hi in bins:
            if not any(lo <= m < hi for b in group for m in b["minutes"]):
                continue
            out.append(f"{lo:>3}-{hi:<3}   " + " ".join(f"{fmt(binmean(group, k, lo, hi)):>5}" for k in keys))
        out.append("")
    # Which measure goes with attack soldiers near the point, minute by minute (minutes 8-30, all battles together)?
    pts = [(b, m) for b in full for m in b["minutes"] if 8 <= m < 30]
    out.append("-- correlation with a150 (attack men within 150 m), battle-minutes 8-30 of all battles; and with the game minute")
    for k, c in COLS:
        if k == "att150":
            continue
        xs = [(b["minutes"][m].get(k), b["minutes"][m].get("att150", 0), m) for b, m in pts if b["minutes"][m].get(k) is not None]
        r1 = pearson([x for x, _, _ in xs], [y for _, y, _ in xs])
        r2 = pearson([x for x, _, _ in xs], [mm for _, _, mm in xs])
        out.append(f"  {c:>6}: with a150 {fmt(round(r1, 2)) if r1 is not None else '.':>5}   with minute {fmt(round(r2, 2)) if r2 is not None else '.':>5}")
    out.append("")
    out.append("-- per battle: first capture, door, a150 mean at min 8-12 / 13-20 / 21-30, AI agents at min 5 / 15 / 25, fps low, wpf+rec+fcr+gsd+imf per 10 min")
    for b in battles:
        if not b.get("minutes"):
            continue
        ms = b["minutes"]

        def mean(k, lo, hi):
            v = [ms[m].get(k, 0) for m in ms if lo <= m <= hi]
            return sum(v) / len(v) if v else None

        def at(k, m):
            return ms.get(m, {}).get(k)

        rep = sum(ms[m].get(k, 0) for m in ms for k in ("wpf", "rec", "fcr", "gsd", "imf"))
        cap = f"{b['first_cap_s'] / 60:5.1f}" if b.get("first_cap_s") is not None else "  -  "
        out.append(f"  {b['run'][-38:]:<38} {b['variant']:<13} cap {cap} door {'on ' if b['door'] else 'OFF'} "
                   f"a150 {fmt(mean('att150', 8, 12)):>3}/{fmt(mean('att150', 13, 20)):>3}/{fmt(mean('att150', 21, 30)):>3}  "
                   f"AI {fmt(at('ai', 5)):>3}/{fmt(at('ai', 15)):>3}/{fmt(at('ai', 25)):>3}  "
                   f"fps {fmt(min((ms[m]['fps'] for m in ms if ms[m].get('fps')), default=None)):>3}  "
                   f"repair/10min {fmt(rep * 10 / max(1, b['last_min'] + 1)):>4}  {b['last_min'] + 1} min")
    return "\n".join(out)


CLOSING_BANDS = ((60, 150), (150, 300), (300, 700))
DIGEST = [("a300", "att300"), ("a150", "att150"), ("a60", "att60"), ("attack men", "att_men"), ("frozen 150-500", "frzN"),
          ("squad men", "mgd"), ("other men", "sup"), ("prone", "prone"), ("unconscious", "unc"), ("fps low", "fps"),
          ("AI agents", "ai"), ("drones up", "air"), ("aboard", "aboard"), ("lost", "lost")]
DIGEST_MIN = (5, 8, 10, 12, 15, 20, 25, 30)


def digest(b: dict) -> str:
    """One battle in a few lines: each measure at game minutes 5, 8, 10, 12, 15, 20, 25, 30."""
    cap = f"taken {b['first_cap_s'] / 60:.1f} min by {b['cap_by']}" if b.get("first_cap_s") is not None else "not taken"
    clo = ", ".join(f"{k} m {v[0]}" for k, v in (b.get("closing") or {}).items() if v[0] is not None)
    lines = [f"{b['run']} [{b['variant']}{', watched' if b['watched'] else ''}] door {'on' if b['door'] else 'OFF'}, {cap}; "
             f"teams on foot got closer by (m per game minute): {clo}",
             f"  {'game minute':<15}" + "".join(f"{m:>5}" for m in DIGEST_MIN)]
    for name, k in DIGEST:
        lines.append(f"  {name:<15}" + "".join(f"{fmt(b['minutes'].get(m, {}).get(k)):>5}" for m in DIGEST_MIN))
    return "\n".join(lines)


def ab(battles: list) -> str:
    """Door on v off (town-brains v town-nodoor), paired by build: one row per battle, then each arm's means."""
    keys = [("a300 8-15", "att300", 8, 15), ("a150 8-30", "att150", 8, 30), ("a60 8-30", "att60", 8, 30),
            ("frozen 10-30", "frzN", 10, 30), ("prone 8-30", "prone", 8, 30), ("unc 8-30", "unc", 8, 30),
            ("door acts", "pact", 0, 30), ("imf/min", "imf", 0, 30), ("lost 30", "lost", 29, 30)]
    out = [f"{'battle':46} {'build':8} door  taken  " + " ".join(f"{k[0]:>12}" for k in keys) + "   closing 150-300 / 300-700"]
    arms = defaultdict(list)
    for b in battles:
        if b["variant"] not in ("town-brains", "town-nodoor") or b.get("watched"):
            continue
        ms = b["minutes"]
        vals = []
        for _, k, lo, hi in keys:
            v = [ms[m].get(k, 0) for m in ms if lo <= m <= hi]
            vals.append(sum(v) / len(v) if v else None)
        cap = b["first_cap_s"] / 60 if b.get("first_cap_s") is not None else None
        clo = b.get("closing") or {}
        row = {"cap": cap, "vals": vals, "c1": (clo.get("150-300") or (None,))[0], "c2": (clo.get("300-700") or (None,))[0]}
        arms[(b.get("commit"), b["door"])].append(row)
        out.append(f"{b['run'][-46:]:46} {b.get('commit', ''):8} {'on ' if b['door'] else 'OFF'}  {fmt(round(cap, 1)) if cap else '  -':>5}  "
                   + " ".join(f"{fmt(round(v, 1)) if v is not None else '.':>12}" for v in vals) + f"   {fmt(row['c1'])} / {fmt(row['c2'])}")
    out.append("")
    for (commit, door), rows in sorted(arms.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        n = len(rows)
        taken = sum(1 for r in rows if r["cap"] is not None)
        early = sum(1 for r in rows if r["cap"] is not None and r["cap"] * 60 <= EARLY_S)
        means = [sum(r["vals"][i] or 0 for r in rows) / n for i in range(len(keys))]
        c1 = [r["c1"] for r in rows if r["c1"] is not None]
        c2 = [r["c2"] for r in rows if r["c2"] is not None]
        out.append(f"build {commit} door {'on ' if door else 'OFF'}: {n} battles, taken {taken} (by min 16: {early}) | "
                   + ", ".join(f"{k[0]} {fmt(round(v, 1))}" for k, v in zip(keys, means))
                   + f" | closing {fmt(round(sum(c1) / len(c1), 1)) if c1 else '.'} / {fmt(round(sum(c2) / len(c2), 1)) if c2 else '.'}")
    return "\n".join(out)


def town_runs(since: str = SINCE) -> list:
    runs = []
    for run in RUNS.glob("*beauregard-town-*"):
        m = re.search(r"-(\d{8}-\d{6})$", run.name)
        if m and m.group(1)[:13] >= since:
            runs.append((m.group(1), run))
    return [r for _, r in sorted(runs)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", help="run folders (default: every town battle since --since)")
    ap.add_argument("--since", default=SINCE)
    ap.add_argument("--summary", action="store_true", help="only the summary")
    ap.add_argument("--ab", action="store_true", help="the door A/B: town-brains v town-nodoor headless battles, paired by build")
    ap.add_argument("--digest", action="store_true", help="each battle as a few lines (measures at minutes 5-30), then the summary")
    ap.add_argument("--json", default="", help="write every battle's minutes to this file")
    ap.add_argument("--min-minutes", type=int, default=5, help="leave out battles shorter than this")
    a = ap.parse_args()
    runs = [Path(r) for r in a.runs] if a.runs else town_runs(a.since)
    battles = []
    for run in runs:
        b = parse(run)
        if b.get("error") or b.get("last_min", -1) + 1 < a.min_minutes:
            continue
        battles.append(b)
        if a.ab:
            continue
        if a.digest:
            print(digest(b))
            print()
        elif not a.summary:
            print(table(b))
            print()
    if a.ab:
        print(ab(battles))
        return 0
    print(summary(battles))
    if a.json:
        Path(a.json).write_text(json.dumps(battles, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
