"""Riders lost aboard their vehicles, and what they leave behind (5 Nov 00:55 - Martin, watching the town battle: "dont we
have many us soldiers stuck unconscious in the cars? like it seem vehicles have tags soldiers seem dead or something").

What it reads from a match's log (script.log, else console.log):
  hits    - a vehicle whose riders died together: [ZCR][LOSS] kind=man foot=0 (aboard at the last 5-s sample) within 6 s and
            8 m of each other; the FPV drone that did it ("FPVAI: droneN detonated on Vehicle ... at <x y z>" within 20 m and
            8 s before), the vehicle's speed while the drone circled it (the drone's last "phase=orbit ... target_kmh="), the
            seconds from the drone's acquiring it to the hit ("phase=hit t="), and how long the riding team had stood within
            30 m before (its [ZCR][LIVE] team line, ride=1, within 15 m of the hit just before it)
  left    - of those vehicles, the ones not destroyed afterwards (no [ZCR][LOSS] kind=vehicle within 25 m later): they stay
            on the road with the bodies in their seats - the watch camera's vehicle tag counts every occupied seat, the dead
            too ("US M998 covered long (4)"), and ZCR_Wrecks only removes destroyed vehicles
  zombie  - AI Conflict trips left in TRANSIT with no one alive (SLOT_ACTIVITY alive=0 vehicle_state=TRANSIT, the trip's own
            faction): until when, and whether that slot's next team (a later group generation) ever got a ride - a trip of
            its own, or at least a VEHICLE_REQUEST_INELIGIBLE line (its ride was considered)
  waits   - riding teams (ride=1, every man v) that stood within 30 m for 120 s or more: where, how long, how it ended
  u       - unconscious soldiers (mp=x,z,u; builds from 5 Nov 00:57 on carry it)

First read (5 Nov, 28 town battles, all with -zcrRideStayMounted): 373 of the US's 970 losses and 334 of the Soviets' 1060
died aboard; 187 vehicles lost 2+ riders at once, 178 of them to an FPV drone, 96 of the 129 with a known speed standing
(<=3 km/h) while it circled; 107 were left intact with 363 bodies in their seats; 57 US trips (7 Soviet) stayed in TRANSIT
with no one alive - a burning UAZ ends its trip at once (VEHICLE_ON_FIRE), an M998 doesn't burn - and none of the 21 slots
refilled after such a trip got a ride again.

  python lab/ridedeaths.py                 the town battles (*beauregard-town-*), one line each and the totals
  python lab/ridedeaths.py RUN [RUN ...]   these runs (folder names under .runtime/runs, or paths)
  python lab/ridedeaths.py --detail RUN    every hit, zombie trip and long wait of the run
"""
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

RUNS = Path(__file__).resolve().parents[1] / ".runtime" / "runs"
GROUP_S, GROUP_M = 6, 8          # deaths of one vehicle's riders: this close in time and space
HIT_S, HIT_M = 8, 20             # an FPV detonation this close before the deaths caused them
WRECK_M = 25                     # a vehicle destroyed this close later: the same vehicle
STAND_M = 30                     # a riding team within this of a spot is standing
WAIT_S = 120                     # a stand this long aboard is a 'wait'

T = re.compile(r" t=(\d+) ")
KV = re.compile(r"(\w+)=(\S+)")
TAKEN = re.compile(r"FPVAI: (drone\d+) \(.*taken over at .* faction=(\w+)")
DET = re.compile(r"FPVAI: (drone\d+) detonated on (\w+)<.*?at <(-?[\d.]+) (-?[\d.]+) (-?[\d.]+)> @\"\{\w+\}(\S+?)\"")
ORBIT = re.compile(r"FPVAI: run drone=(drone\d+) phase=orbit .*target_kmh=(\d+)")
HIT = re.compile(r"FPVAI: run drone=(drone\d+) phase=hit t=([\d.]+)")
TEAM = re.compile(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=(\w+) id=(\d+) role=\S+ men=(\d+) ride=(\d) x=(-?\d+) z=(-?\d+)")
TRIP = re.compile(r"operation_id=trip-(US|USSR)-(\d+)-(\d+)-(\d+)")


def log_of(run: str):
    p = Path(run)
    if not p.exists():
        p = RUNS / run
    for name in ("script.log", "console.log"):
        f = next(iter(sorted((p / "logs").glob("*/" + name))), None)
        if f:
            return f
    return None


def parse(lines):
    t = 0
    side_of, orbit_kmh, hit_s = {}, {}, {}
    deaths, dets, wrecks = [], [], []
    teams = defaultdict(list)            # (side, id) -> [(t, ride, x, z, men, all_v, wp)]
    unconscious = set()
    zombie = {}                          # (faction, numeric slot, generation, trip) -> [first_t, last_t, slot key]
    rode = defaultdict(set)              # (faction, numeric slot) -> group generations that had a trip
    considered = defaultdict(set)        # (faction, slot key) -> group generations whose ride was considered
    spawned = defaultdict(set)           # (faction, numeric slot) -> generations spawned
    for line in lines:
        m = T.search(line)
        if m:
            t = int(m.group(1))
        if "FPVAI: " in line:
            m = TAKEN.search(line)
            if m:
                side_of[m.group(1)] = m.group(2)
                continue
            m = ORBIT.search(line)
            if m:
                orbit_kmh[m.group(1)] = int(m.group(2))
                continue
            m = HIT.search(line)
            if m:
                hit_s[m.group(1)] = float(m.group(2))
                continue
            m = DET.search(line)
            if m:
                dets.append({"t": t, "drone": m.group(1), "on": m.group(2), "x": float(m.group(3)), "z": float(m.group(5)),
                             "what": m.group(6).rsplit("/", 1)[-1].replace(".et", ""), "side": side_of.get(m.group(1), "?")})
            continue
        if "[ZCR][LOSS]" in line:
            d = dict(KV.findall(line))
            try:
                x, z, lt = float(d["x"]), float(d["z"]), int(d["t"])
            except (KeyError, ValueError):
                continue
            if d.get("kind") == "vehicle":
                wrecks.append({"t": lt, "x": x, "z": z, "what": d.get("victim")})
            elif d.get("kind") == "man" and d.get("foot") == "0":
                deaths.append({"t": lt, "x": x, "z": z, "side": d.get("side"), "relation": d.get("relation")})
            continue
        if "kind=team" in line and "[ZCR][LIVE]" in line:
            m = TEAM.search(line)
            if not m:
                continue
            d = dict(KV.findall(line))
            mp = d.get("mp", "-")
            states = [s.split(",")[-1] for s in mp.split(";") if s.count(",") == 2]
            for s in mp.split(";"):
                p = s.split(",")
                if len(p) == 3 and p[2] == "u":
                    unconscious.add((m.group(2), m.group(3), round(int(p[0]) / 5), round(int(p[1]) / 5)))
            wp = None
            if d.get("wp", "-") != "-" and "," in d["wp"]:
                try:
                    wp = tuple(float(v) for v in d["wp"].split(",")[:2])
                except ValueError:
                    wp = None
            teams[(m.group(2), int(m.group(3)))].append((int(m.group(1)), int(m.group(5)), int(m.group(6)), int(m.group(7)),
                                                         int(m.group(4)), bool(states) and all(s == "v" for s in states), wp))
            continue
        if "[AICF]" in line:
            if "SLOT_ACTIVITY" in line:
                d = dict(KV.findall(line))
                m = TRIP.search(line)
                if (m and d.get("alive") == "0" and d.get("vehicle_state") == "TRANSIT" and m.group(1) == d.get("faction")):
                    k = (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
                    z = zombie.setdefault(k, [t, t, d.get("slot")])
                    z[1] = t
                continue
            m = TRIP.search(line)
            if m:
                rode[(m.group(1), int(m.group(2)))].add(int(m.group(3)))
            if "VEHICLE_REQUEST_INELIGIBLE" in line:
                d = dict(KV.findall(line))
                try:
                    considered[(d.get("faction"), d.get("slot"))].add(int(d.get("group_generation", "0")))
                except ValueError:
                    pass
            elif "SPAWN_BOUND" in line:
                d = dict(KV.findall(line))
                try:
                    spawned[(d.get("faction"), int(d["slot"]))].add(int(d["generation"]))
                except (KeyError, ValueError):
                    pass
    return {"deaths": deaths, "dets": dets, "wrecks": wrecks, "teams": teams, "orbit": orbit_kmh, "hit": hit_s,
            "unconscious": unconscious, "zombie": zombie, "rode": rode, "considered": considered, "spawned": spawned, "end": t}


def hits(p):
    groups = []
    for d in sorted(p["deaths"], key=lambda r: r["t"]):
        for g in groups:
            if g["side"] == d["side"] and abs(g["t"] - d["t"]) <= GROUP_S and math.hypot(g["x"] - d["x"], g["z"] - d["z"]) <= GROUP_M:
                g["n"] += 1
                break
        else:
            groups.append({"t": d["t"], "x": d["x"], "z": d["z"], "side": d["side"], "n": 1})
    for g in groups:
        det = next((x for x in reversed(p["dets"]) if 0 <= g["t"] - x["t"] <= HIT_S
                    and math.hypot(x["x"] - g["x"], x["z"] - g["z"]) <= HIT_M), None)
        g["drone"] = det
        g["kmh"] = p["orbit"].get(det["drone"]) if det else None
        g["acquired_s"] = p["hit"].get(det["drone"]) if det else None
        g["destroyed"] = next((w for w in p["wrecks"] if 0 <= w["t"] - g["t"] <= 3600
                               and math.hypot(w["x"] - g["x"], w["z"] - g["z"]) <= WRECK_M), None)
        g["stood_s"], g["to_wp_m"], g["team"] = None, None, None
        # The riding team: ride=1 within 15 m just before; in a column several are - the one that lost the men (fewer
        # after, or no line at all) is it.
        best = None
        for key, tr in p["teams"].items():
            if key[0] != g["side"]:
                continue
            before = [k for k, r in enumerate(tr) if g["t"] - 12 <= r[0] <= g["t"] and r[1] == 1
                      and math.hypot(r[2] - g["x"], r[3] - g["z"]) <= 15]
            if not before:
                continue
            i = before[-1]
            after = [r for r in tr[i + 1:] if r[0] <= g["t"] + 15]
            lost = not after or after[-1][4] <= tr[i][4] - (g["n"] - 1)
            if best is None or (lost and not best[2]):
                best = (key, i, lost)
        if best:
            key, i, _ = best
            tr = p["teams"][key]
            last = tr[i]
            j = i
            while j > 0 and tr[j - 1][1] == 1 and math.hypot(tr[j - 1][2] - last[2], tr[j - 1][3] - last[3]) <= STAND_M:
                j -= 1
            g["team"] = key[1]
            g["stood_s"] = last[0] - tr[j][0]
            if last[6]:
                g["to_wp_m"] = round(math.hypot(last[6][0] - last[2], last[6][1] - last[3]))
    return groups


def waits(p, hs=()):
    out = []
    for key, tr in p["teams"].items():
        i = 0
        while i < len(tr):
            if tr[i][1] != 1 or not tr[i][5]:
                i += 1
                continue
            j = i
            while j + 1 < len(tr) and tr[j + 1][1] == 1 and math.hypot(tr[j + 1][2] - tr[i][2], tr[j + 1][3] - tr[i][3]) <= STAND_M:
                j += 1
            if tr[j][0] - tr[i][0] >= WAIT_S:
                nxt = tr[j + 1] if j + 1 < len(tr) else None
                killed = next((h for h in hs if h["side"] == key[0] and h["n"] >= 2 and tr[j][0] - 5 <= h["t"] <= tr[j][0] + 15
                               and math.hypot(h["x"] - tr[j][2], h["z"] - tr[j][3]) <= STAND_M), None)
                if killed:
                    end = f"killed aboard ({killed['n']} men)"
                elif nxt is None:
                    end = "match end" if p["end"] - tr[j][0] < 30 else "team gone (lost)"
                elif nxt[4] < tr[j][4]:
                    end = "men lost"
                elif nxt[1] == 0:
                    end = "got out"
                else:
                    end = "drove on"
                out.append({"side": key[0], "team": key[1], "from": tr[i][0], "s": tr[j][0] - tr[i][0], "x": tr[i][2], "z": tr[i][3],
                            "men": tr[i][4], "end": end})
            i = j + 1
    return sorted(out, key=lambda w: w["from"])


def zombies(p):
    out = []
    for (fac, num, gen, trip), (t0, t1, key) in sorted(p["zombie"].items(), key=lambda kv: kv[1][0]):
        later_rides = sorted(g for g in p["rode"].get((fac, num), set()) if g > gen)
        later_teams = sorted(g for g in p["spawned"].get((fac, num), set()) if g > gen)
        later_considered = sorted(g for g in p["considered"].get((fac, key), set()) if g > gen)
        out.append({"faction": fac, "slot": key, "gen": gen, "trip": trip, "from": t0, "to": t1, "end": p["end"],
                    "next_teams": later_teams, "next_rides": later_rides, "next_considered": later_considered})
    return out


def summary(name, p, detail=False):
    hs = hits(p)
    ws, zs = waits(p, hs), zombies(p)
    sides = sorted({h["side"] for h in hs} | {w["side"] for w in ws} | {z["faction"] for z in zs})
    row = {}
    for s in sides:
        sh = [h for h in hs if h["side"] == s and h["n"] >= 2]
        fpv = [h for h in sh if h["drone"]]
        standing = [h for h in fpv if h["kmh"] is not None and h["kmh"] <= 3]
        left = [h for h in sh if not h["destroyed"]]
        sz = [z for z in zs if z["faction"] == s]
        stuck = [z for z in sz if z["next_teams"] and not z["next_rides"] and not z["next_considered"]]
        row[s] = {"aboard_dead": sum(h["n"] for h in hs if h["side"] == s), "vehicles": len(sh), "fpv": len(fpv),
                  "standing": len(standing), "kmh_known": sum(1 for h in fpv if h["kmh"] is not None), "left": len(left),
                  "bodies_left": sum(h["n"] for h in left), "zombie": len(sz), "next_team_no_ride": len(stuck),
                  "waits": sum(1 for w in ws if w["side"] == s), "waits_killed": sum(1 for w in ws if w["side"] == s and w["end"].startswith("killed")),
                  "wait_max": max([w["s"] for w in ws if w["side"] == s], default=0)}
    u = len(p["unconscious"])
    parts = []
    for s, r in row.items():
        parts.append(f"{s}: {r['aboard_dead']} riders died aboard, {r['vehicles']} vehicles hit ({r['fpv']} by FPV, "
                     f"{r['standing']}/{r['kmh_known']} standing <=3 km/h), {r['left']} left with {r['bodies_left']} bodies; "
                     f"{r['zombie']} trips stuck in TRANSIT, {r['next_team_no_ride']} slots' next team never rode; "
                     f"{r['waits']} waits aboard 120 s+ (max {r['wait_max']} s, {r['waits_killed']} ended killed aboard)")
    print(f"{name}  (game t={p['end']} s, unconscious seen: {u})")
    for s in parts:
        print("   " + s)
    if detail:
        print("   hits (side, t, men, where, drone, its side, kmh while it circled, s from acquiring, team stood s, to its wp m, destroyed later):")
        for h in hs:
            if h["n"] < 2:
                continue
            d = h["drone"]
            print(f"     {h['side']} t={h['t']} men={h['n']} at={h['x']:.0f},{h['z']:.0f} drone={d and d['drone']}/{d and d['what']} "
                  f"of={d and d['side']} kmh={h['kmh']} acquired_s={h['acquired_s']} team={h['team']} stood_s={h['stood_s']} "
                  f"to_wp_m={h['to_wp_m']} destroyed={h['destroyed'] and (h['destroyed']['what'], h['destroyed']['t'])}")
        print("   trips left in TRANSIT with no one alive (slot, trip, game s shown on the slot, later teams, later rides, later considered):")
        for z in zs:
            print(f"     {z['faction']} {z['slot']} gen={z['gen']} trip={z['trip']} t={z['from']}-{z['to']} (match end {z['end']}) "
                  f"next_teams={z['next_teams']} next_rides={z['next_rides']} considered={z['next_considered']}")
        print("   waits aboard 120 s+:")
        for w in ws:
            print(f"     {w['side']} team {w['team']} t={w['from']} for {w['s']} s at {w['x']},{w['z']} men={w['men']} -> {w['end']}")
    return row, u


def main(argv) -> int:
    detail = "--detail" in argv
    names = [a for a in argv if not a.startswith("--")]
    if not names:
        names = sorted(p.name for p in RUNS.glob("*beauregard-town-*") if p.is_dir())
    total = defaultdict(lambda: defaultdict(int))
    runs = 0
    for name in names:
        log = log_of(name)
        if not log:
            print(name, "no log")
            continue
        p = parse(log.read_text(encoding="utf-8", errors="replace").splitlines())
        if p["end"] < 300:
            print(f"{name}  (game t={p['end']} s - too short, skipped)")
            continue
        runs += 1
        row, u = summary(Path(name).name, p, detail)
        for s, r in row.items():
            for k, v in r.items():
                if k == "wait_max":
                    total[s][k] = max(total[s][k], v)
                else:
                    total[s][k] += v
        total["all"]["unconscious"] += u
    if runs > 1:
        print(f"\nTOTAL over {runs} matches:")
        for s, r in total.items():
            print(f"   {s}: " + ", ".join(f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
