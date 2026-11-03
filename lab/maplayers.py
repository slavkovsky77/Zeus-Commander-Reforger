"""Map layers from the run logs, for the lab app's Map tab (24 Oct - Martin: "do we have a map? an image overlay?";
plan page M6: https://claude.ai/artifact/EAVqib8JhtDtkVxGB3KKSV). Per map (arland, everon), from every run since
FROM_DAY whose log names that world:

  bases         the bases from the latest situation report (name, owner at the start, links)
  depot_spots   spots driven by the drive test's "depots" mode: the builder's access check ([ZCR][ACCESS] way=1/0/-1)
                and how many of the vans from each got to their goal
  depots_built  where AI Conflict's builders put vehicle depots in matches (CONSTRUCTION_PLACED), grouped within 25 m
  traps         where vehicles' moves failed ([ZCR][MOVEFAIL] UNREACHABLE / STUCK) or a drive test's crew got out,
                grouped within 15 m, matches and tests counted apart

Each run is read once (bytes, targeted patterns) and cached in .runtime/maplayers/<run>.json, keyed on its log's size
and mtime - the first build reads ~7 GB, later ones only new runs.

    python lab/maplayers.py arland          # build (or refresh) and print a summary
"""
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / ".runtime" / "runs"
CACHE = ROOT / ".runtime" / "maplayers"
FROM_DAY = "20261020"
# Runs whose van outcomes don't count (their access verdicts do): the 24 Oct Arland survey sent every van to one point in
# a forest (review note 391).
NO_OUTCOMES = ("drivetest-arland-depots-",)

WORLD = re.compile(rb"worlds/[^\s\"']*?([A-Za-z0-9_]+)\.ent")
ACCESS = re.compile(rb"\[ZCR\]\[ACCESS\] t=\d+ start=(\d+) x=(\d+) z=(\d+) (?:road|way)=(-?\d+)")
SPAWN = re.compile(rb"car=(\d+) event=SPAWN [^\n]*? x=(\d+) z=(\d+) convoy=\d+ start=(\d+)")
ARRIVE = re.compile(rb"car=(\d+) event=ARRIVE")
LOST = re.compile(rb"car=(\d+) event=LOST leg=\d+ why=(\w+) x=(\d+) z=(\d+)")
MOVEFAIL = re.compile(rb"\[ZCR\]\[MOVEFAIL\] t=(\d+) side=(\w+) vehicle=(\S+) error=(UNREACHABLE|STUCK) x=(\d+) z=(\d+)")
PLACED = re.compile(rb"CONSTRUCTION_PLACED\][^\n]*?faction=(\w+)[^\n]*?type=(\w+)[^\n]*?position=<(-?[\d.]+),[^,]+,(-?[\d.]+)>")
# Every building the builders placed (the base-building sub-lab, 25 Oct): its order's token, side, kind, place; built or not.
PLACED_T = re.compile(rb"CONSTRUCTION_PLACED\][^\n]*?token=(\S+)[^\n]*?faction=(\w+)[^\n]*?type=(\w+)[^\n]*?position=<(-?[\d.]+),[^,]+,(-?[\d.]+)>")
COMPLETED = re.compile(rb"CONSTRUCTION_COMPLETED\][^\n]*?token=(\S+)")
CACHE_V = 2


def slug(world: str) -> str:
    w = world.lower()
    if "arland" in w:
        return "arland"
    if "eden" in w or "everon" in w:
        return "everon"
    return w


def kind(run: Path) -> str:
    n = run.name
    if n.startswith(("drivetest-", "buildtest-")):
        return "test"
    if re.match(r"w\d+-|b-|depot-check", n):
        return "match"
    return "other"


def read_run(run: Path):
    """The run's map layer data, from the cache when its log hasn't changed."""
    logs = sorted(run.glob("logs/*/console.log"))
    if not logs:
        return None
    log = logs[-1]
    st = log.stat()
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{run.name}.json"
    if cached.exists():
        try:
            d = json.loads(cached.read_text(encoding="utf-8"))
            if d.get("size") == st.st_size and d.get("mtime") == int(st.st_mtime) and d.get("v") == CACHE_V:
                return d
        except (OSError, ValueError):
            pass
    data = log.read_bytes()
    w = WORLD.search(data[:2_000_000])
    d = {"run": run.name, "kind": kind(run), "size": st.st_size, "mtime": int(st.st_mtime), "v": CACHE_V,
         "map": slug(w.group(1).decode()) if w else "", "access": [], "spawns": {}, "arrived": [], "lost": [],
         "movefail": [], "placed": [], "buildings": [], "bases": []}
    if d["map"]:
        d["access"] = [[int(s), int(x), int(z), int(v)] for s, x, z, v in ACCESS.findall(data)]
        d["spawns"] = {c.decode(): [int(x), int(z), int(s)] for c, x, z, s in SPAWN.findall(data)}
        d["arrived"] = sorted({c.decode() for c in ARRIVE.findall(data)})
        d["lost"] = [[c.decode(), why.decode(), int(x), int(z)] for c, why, x, z in LOST.findall(data)]
        d["movefail"] = [[int(t), side.decode(), veh.decode(), err.decode(), int(x), int(z)] for t, side, veh, err, x, z in MOVEFAIL.findall(data)]
        d["placed"] = [[f.decode(), ty.decode(), round(float(x)), round(float(z))] for f, ty, x, z in PLACED.findall(data) if b"DEPOT" in ty]
        done = set(COMPLETED.findall(data))
        d["buildings"] = [[f.decode(), ty.decode(), round(float(x)), round(float(z)), int(tok in done)] for tok, f, ty, x, z in PLACED_T.findall(data)]
        snap = next(iter(run.glob("profile/zcr/snapshots.jsonl")), None)
        if snap:
            try:
                first = json.loads(snap.read_text(encoding="utf-8").splitlines()[0])
                d["bases"] = [{k: b.get(k) for k in ("id", "name", "owner", "x", "z", "links", "hq")} for b in first.get("bases", [])]
            except (OSError, ValueError, IndexError):
                pass
    cached.write_text(json.dumps(d), encoding="utf-8")
    return d


def group(points, radius):
    """Greedy grouping: each point joins the first group whose centre is within radius."""
    groups = []
    for p in points:
        for g in groups:
            if (g["x"] - p["x"]) ** 2 + (g["z"] - p["z"]) ** 2 <= radius * radius:
                g["items"].append(p)
                n = len(g["items"])
                g["x"] += (p["x"] - g["x"]) / n
                g["z"] += (p["z"] - g["z"]) / n
                break
        else:
            groups.append({"x": p["x"], "z": p["z"], "items": [p]})
    return groups


def run_time(run: Path) -> float:
    m = re.search(r"-(\d{8})-(\d{6})$", run.name)
    return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")) if m else 0


def allowed_kinds(kinds: str) -> tuple:
    return {"match": ("match",), "test": ("test",), "both": ("match", "test")}.get(kinds, ("match", "test", "other"))


def current_run(map_slug: str, kinds: str = "match"):
    """The run being played on this map now (its log written in the last 90 s), else the newest one of these kinds
    (28 Oct, Martin: "the map should also have an option to watch the current match only")."""
    allowed = allowed_kinds(kinds)
    runs = sorted((r for r in RUNS.iterdir() if r.is_dir() and kind(r) in allowed), key=run_time, reverse=True)[:40]
    newest = None
    for run in runs:
        logs = sorted(run.glob("logs/*/console.log"))
        if not logs:
            continue
        if not _live_world.get(run.name):
            with open(logs[-1], "rb") as f:
                w = WORLD.search(f.read(2_000_000))
            if w:
                _live_world[run.name] = slug(w.group(1).decode())
        if _live_world.get(run.name) != map_slug:
            continue
        if time.time() - logs[-1].stat().st_mtime < 90:
            return run, True
        newest = newest or run
    return newest, False


def layers(map_slug: str, since_h: float = 0, kinds: str = "match", current: bool = False) -> dict:
    """since_h: only runs started in the last since_h hours (0: every run since FROM_DAY) - 25 Oct, Martin: "let's reset
    the runs to today only"; kinds: "match" (watched and headless matches), "test" (sub-lab drive tests), "all" (also
    probes and the other sub-labs) - "since the 20th there were a lot of blind tests"; current: only the match being
    played now (or the latest one), see current_run."""
    allowed = allowed_kinds(kinds)
    started = time.time()
    floor = time.mktime(time.strptime(FROM_DAY, "%Y%m%d"))
    if since_h:
        floor = max(floor, time.time() - since_h * 3600)
    live_now = False
    if current:
        run, live_now = current_run(map_slug, kinds)
        runs = [run] if run else []
    else:
        runs = sorted((r for r in RUNS.iterdir() if r.is_dir() and run_time(r) >= floor), key=run_time)
    bases, spots, built, traps, buildings = [], {}, [], [], []
    scanned = 0
    for run in runs:
        d = read_run(run)
        if not d or d["map"] != map_slug or d["kind"] not in allowed:
            continue
        scanned += 1
        if d["bases"]:
            bases = d["bases"]                     # the latest report wins
        # Depot spots: the check's verdict, and each car's outcome by the spot it started from.
        for start, x, z, way in d["access"]:
            key = f"{x},{z}"
            s = spots.setdefault(key, {"x": x, "z": z, "way": way, "cars": 0, "out": 0, "runs": []})
            s["way"] = way
            if d["run"] not in s["runs"]:
                s["runs"].append(d["run"])
        arrived = set(d["arrived"])
        # Lost vans count only when they left their spawn spot: a crew that never drove off says nothing about the spot
        # (the 1-minute headless check runs, 24 Oct; the drivers that never sat in).
        lost = {c for c, why, x, z in d["lost"]
                if not (c in d["spawns"] and abs(d["spawns"][c][0] - x) < 6 and abs(d["spawns"][c][1] - z) < 6)}
        if not d["run"].startswith(NO_OUTCOMES):
            for car, (x, z, start) in d["spawns"].items():
                key = f"{x},{z}"
                if key in spots and (car in arrived or car in lost):   # finished vans only: still driving at the end don't count
                    spots[key]["cars"] += 1
                    spots[key]["out"] += car in arrived
        for f, ty, x, z in d["placed"]:
            built.append({"x": x, "z": z, "faction": f, "type": ty, "run": d["run"]})
        for f, ty, x, z, done in d.get("buildings") or []:
            buildings.append({"x": x, "z": z, "faction": f, "type": ty.lower(), "built": done, "run": d["run"]})
        for t, side, veh, err, x, z in d["movefail"]:
            traps.append({"x": x, "z": z, "what": err.lower(), "kind": d["kind"], "run": d["run"], "vehicle": veh})
        for car, why, x, z in d["lost"]:
            if why == "crew_out":
                sp = d["spawns"].get(car)
                if sp and abs(sp[0] - x) < 6 and abs(sp[1] - z) < 6:
                    continue                       # never left its spawn spot: not a place on the road
                traps.append({"x": x, "z": z, "what": "crew_out", "kind": d["kind"], "run": d["run"], "vehicle": ""})
    names = {b["id"]: b["name"] for b in bases}
    out_bases = [{"name": b["name"], "owner": b["owner"], "x": b["x"], "z": b["z"], "hq": bool(b.get("hq")),
                  "links": [names.get(i, str(i)) for i in (b.get("links") or [])]} for b in bases]
    out_built = []
    for g in group(built, 25):
        fac = {}
        for it in g["items"]:
            fac[it["faction"]] = fac.get(it["faction"], 0) + 1
        out_built.append({"x": round(g["x"]), "z": round(g["z"]), "count": len(g["items"]), "factions": fac,
                          "matches": len({it["run"] for it in g["items"]})})
    # Everything the builders placed (25 Oct, the base-building sub-lab): one mark per 12 m, its kinds, how often built.
    out_buildings = []
    for g in group(buildings, 12):
        kinds_n = {}
        for it in g["items"]:
            kinds_n[it["type"]] = kinds_n.get(it["type"], 0) + 1
        out_buildings.append({"x": round(g["x"]), "z": round(g["z"]), "count": len(g["items"]), "built": sum(i["built"] for i in g["items"]),
                              "kinds": kinds_n, "factions": sorted({i["faction"] for i in g["items"]}), "runs": len({i["run"] for i in g["items"]})})
    out_traps = []
    for g in group(traps, 15):
        items = g["items"]
        out_traps.append({"x": round(g["x"]), "z": round(g["z"]), "count": len(items),
                          "unreachable": sum(i["what"] == "unreachable" for i in items),
                          "stuck": sum(i["what"] == "stuck" for i in items),
                          "crew_out": sum(i["what"] == "crew_out" for i in items),
                          "in_matches": sum(i["kind"] == "match" for i in items),
                          "in_tests": sum(i["kind"] == "test" for i in items),
                          "runs": len({i["run"] for i in items}), "last_run": items[-1]["run"]})
    out_traps.sort(key=lambda t: -t["count"])
    # The planned supply routes (lab/roadgraph.py), when they've been built for this map.
    routes = []
    rf = ROOT / ".runtime" / "maps" / map_slug / "routes.json"
    if rf.exists():
        try:
            for r in json.loads(rf.read_text(encoding="utf-8")).get("routes", []):
                if r.get("ok"):
                    routes.append({"from": r["from"], "to": r["to"], "length_m": r["length_m"], "shortest_m": r.get("shortest_m"),
                                   "points": r["points"][::3] + [r["points"][-1]], "waypoints": len(r["waypoints"]),
                                   "stuck_places": len(r["stuck_places"])})
        except (OSError, ValueError):
            pass
    return {"map": map_slug, "runs": scanned, "since_h": since_h, "kinds": kinds,
            "current": {"run": runs[0].name, "live": live_now} if current and runs else None, "bases": out_bases,
            "depot_spots": [{k: v for k, v in s.items() if k != "runs"} | {"runs": len(s["runs"])} for s in spots.values()],
            "depots_built": out_built, "buildings": out_buildings, "traps": out_traps, "routes": routes, "built_s": round(time.time() - started, 1),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}


def main() -> int:
    m = sys.argv[1] if len(sys.argv) > 1 else "arland"
    d = layers(m)
    print(f"{m}: {d['runs']} runs, {len(d['bases'])} bases, {len(d['depot_spots'])} tested depot spots, "
          f"{len(d['depots_built'])} depot sites built, {len(d['traps'])} trap spots ({d['built_s']} s)")
    for t in d["traps"][:12]:
        print(f"  trap {t['x']},{t['z']}: {t['count']} (unreachable {t['unreachable']}, stuck {t['stuck']}, crew out {t['crew_out']};"
              f" matches {t['in_matches']}, tests {t['in_tests']}, runs {t['runs']})")
    for s in d["depot_spots"]:
        print(f"  depot spot {s['x']},{s['z']}: check {s['way']}, vans {s['out']}/{s['cars']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


LIVE = re.compile(r"\[ZCR\]\[LIVE\] t=(\d+) kind=(\w+) (.*)")
EFFORTS = re.compile(r"\[ZCR\]\[EFFORTS\] t=(\d+) side=(\w+) json=(.*)")
ROUTE_OF = re.compile(r"\[ZCR\]\[ROUTE\] t=\d+ car=(\d+) route=(\d+)")
PATH_OF = re.compile(r"car=(\d+) event=PATH n=\d+ pts=(\S+)")
_live_world = {}


def run_routes(run: Path) -> list:
    """The run's own planned routes (its seeded profile/zcr/routes.txt): [((fx, fz, tx, tz), [[x, z], ...]), ...] by number."""
    f = run / "profile" / "zcr" / "routes.txt"
    out = []
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts[:1] == ["route"] and len(parts) >= 7:
            out.append((tuple(int(float(v)) for v in parts[2:6]), []))
        elif len(parts) == 2 and out:
            out[-1][1].append([float(parts[0]), float(parts[1])])
    return out


PLAN_LINE = re.compile(r"\[ZCR\]\[ATTACKPLAN\] side=(\w+) slot=(\d+) objective=(-?\d+),(-?\d+) from=\S+ plans_for_objective=\d+ plan=(\w+) origin=(-?\d+),(-?\d+)")
_plan_scan = {}   # run name -> (log offset read so far, {(side, ox, oz, objx, objz, id): set of slots})


def plans_in_use(run: Path, log: Path, map_slug: str) -> list:
    """The attack plans this match's teams play (29 Oct evening, Martin: "now it seems simple waypoints according to the
    Commander Lab, I imagine having lines of attack"): each [ZCR][ATTACKPLAN] team line (AICF_ZcrAttackPlan.ForTeam, read
    from the whole log, incrementally) -> that plan's lanes and hold points from the run's own profile/zcr/attackplan.txt,
    its drive from .runtime/attack/<map>/plans.json."""
    offset, used = _plan_scan.get(run.name, (0, {}))
    size = log.stat().st_size
    if size < offset:
        offset, used = 0, {}
    with open(log, "rb") as f:
        f.seek(offset)
        raw = f.read()
    cut = raw.rfind(b"\n") + 1
    for m in PLAN_LINE.finditer(raw[:cut].decode("utf-8", "replace")):
        side, slot, objx, objz, pid, ox, oz = m.groups()
        used.setdefault((side, int(ox), int(oz), int(objx), int(objz), pid), set()).add(int(slot))
    _plan_scan[run.name] = (offset + cut, used)
    if not used:
        return []
    # The run's own plan file: plan line -> its lanes.
    lanes_of = {}
    pf = run / "profile" / "zcr" / "attackplan.txt"
    if pf.exists():
        cur, lane = None, None
        for line in pf.read_text(encoding="utf-8").splitlines():
            v = line.split()
            if not v or v[0] == "world":
                cur = lane = None
                continue
            if v[0] == "plan" and len(v) >= 8:
                cur = {"origin": [float(v[1]), float(v[2])], "objective": [float(v[3]), float(v[4])], "assembly": [float(v[5]), float(v[6])],
                       "id": v[7], "lanes": [], "holds": []}
                lanes_of[(round(float(v[1])), round(float(v[2])), round(float(v[3])), round(float(v[4])), v[7])] = cur
                lane = None
            elif v[0] == "lane" and cur is not None and len(v) >= 4:
                lane = []
                cur["lanes"].append(lane)
                cur["holds"].append([float(v[2]), float(v[3])])
            elif lane is not None and len(v) >= 2:
                lane.append([float(v[0]), float(v[1])])
    drives = {}
    pj = ROOT / ".runtime" / "attack" / map_slug / "plans.json"
    if pj.exists():
        try:
            for o in json.loads(pj.read_text(encoding="utf-8")).get("objectives", []):
                for h in o.get("hqs", []):
                    for p in h.get("plans", []):
                        drives[(round(h["x"]), round(h["z"]), round(o["objective"]["x"]), round(o["objective"]["z"]),
                                round(p["assembly"]["x"]), round(p["assembly"]["z"]))] = (
                            p["drive"]["points"][::3] + p["drive"]["points"][-1:], p.get("approach", ""), h.get("name", ""),
                            p["assembly"]["from_objective_m"])
        except (ValueError, KeyError):
            pass
    out = []
    for (side, ox, oz, objx, objz, pid), slots in used.items():
        plan = next((p for k, p in lanes_of.items() if abs(k[0] - ox) <= 1 and abs(k[1] - oz) <= 1 and abs(k[2] - objx) <= 1
                     and abs(k[3] - objz) <= 1 and k[4] == pid), None)
        if not plan:
            continue
        # By the assembly point, not the letter: the plan files are written from different planner runs (one-point / --all).
        ax, az = plan["assembly"]
        drive = min(((math.hypot(k[4] - ax, k[5] - az), dv) for k, dv in drives.items() if abs(k[0] - ox) <= 300 and abs(k[1] - oz) <= 300
                     and abs(k[2] - objx) <= 150 and abs(k[3] - objz) <= 150), default=(1e9, None), key=lambda t: t[0])
        drive = drive[1] if drive[0] < 80 else None
        out.append({**plan, "side": side, "teams": sorted(slots), "drive": drive[0] if drive else [],
                    "approach": drive[1] if drive else "", "from_name": drive[2] if drive else "", "assembly_m": drive[3] if drive else None})
    return out


LIVE_INTENT = re.compile(r"t=\d+ (\w+) gemini \([^)]*\): (.+)$")


def live_plans(run: Path) -> tuple:
    """Gemini's plan as it stands (3 Nov, Martin: "i still see the same plan in commander lab as always are we using
    fucking gemini or what?" - the map drew the stored plan the teams were given at the start, not the live one): the
    latest round of lab/liveplan.py (profile/zcr/liveplan.jsonl) -> one plan per route its teams play now, drawn like the
    stored plans; and the side's last plan in Gemini's words (profile/zcr/liveplan.log)."""
    zcr = run / "profile" / "zcr"
    f = zcr / "liveplan.jsonl"
    if not f.exists():
        return [], {}
    with open(f, "rb") as fh:
        fh.seek(max(0, f.stat().st_size - 400_000))
        rows = fh.read().decode("utf-8", "replace").splitlines()
    last = None
    for line in reversed(rows):
        try:
            last = json.loads(line)
            break
        except ValueError:
            continue
    if not last:
        return [], {}
    side, orders = last.get("side", ""), last.get("orders") or {}
    from_obj = {(round(d["x"]), round(d["z"])): d.get("from_obj_m") for d in last.get("drops") or []}
    groups = {}
    for tid, e in (last.get("entries") or {}).items():
        wps = e.get("waypoints") or []
        if len(wps) < 2:
            continue
        drop = e.get("drop")
        key = (e.get("route", "?"), round(drop[0]) if drop else None, round(drop[1]) if drop else None)
        g = groups.setdefault(key, {"id": key[0], "side": side, "teams": [], "lanes": [wps], "holds": [e.get("hold")],
                                    "assembly": drop or wps[0], "assembly_m": from_obj.get((key[1], key[2])), "drive": [],
                                    "approach": "", "from_name": "", "by": "rules", "why": [], "go": e.get("go", 1)})
        g["teams"].append(int(tid))
        o = orders.get(tid) or {}
        if o.get("source") == "model":
            g["by"] = "Gemini"
        if o.get("why") and o["why"] not in g["why"]:
            g["why"].append(o["why"])
    for g in groups.values():
        g["teams"].sort()
        g["why"] = "; ".join(g["why"])
    intents = {}
    lf = zcr / "liveplan.log"
    if lf.exists():
        with open(lf, "rb") as fh:
            fh.seek(max(0, lf.stat().st_size - 60_000))
            for line in fh.read().decode("utf-8", "replace").splitlines():
                m = LIVE_INTENT.search(line)
                if m:
                    intents[m.group(1)] = "Gemini: " + m.group(2)
    return list(groups.values()), intents


def live(map_slug: str) -> dict:
    """The running game on this map (its log written in the last 90 s): the last [ZCR][LIVE] round - teams, supply trucks,
    test vans - with each van's planned route and the game's current path (lab app /api/map/live)."""
    runs = sorted((r for r in RUNS.iterdir() if r.is_dir()), key=run_time, reverse=True)[:15]
    for run in runs:
        logs = sorted(run.glob("logs/*/console.log"))
        if not logs or time.time() - logs[-1].stat().st_mtime > 90:
            continue
        log = logs[-1]
        # The run's map, read once it is in the log (25 Oct: a run seen in its first seconds, before the world line,
        # was cached as no map and never shown live).
        if not _live_world.get(run.name):
            with open(log, "rb") as f:
                w = WORLD.search(f.read(2_000_000))
            if w:
                _live_world[run.name] = slug(w.group(1).decode())
        if _live_world.get(run.name) != map_slug:
            continue
        size = log.stat().st_size
        with open(log, "rb") as f:
            f.seek(max(0, size - 600_000))
            tail = f.read().decode("utf-8", "replace")
        rows = [(int(m.group(1)), m.group(2), m.group(3)) for m in LIVE.finditer(tail)]
        if not rows:
            continue   # just starting (or no live lines): an older game on this map may still be running
        last = max(r[0] for r in rows)
        units = {"team": [], "truck": [], "van": [], "builder": []}
        # Where each vehicle and team has been (the click-a-van view): "van:7", "truck:US:2", "team:USSR:A3" -> [[x, z], ...].
        trails = {}
        for tt, kind, rest in rows:
            u = dict(kv.split("=", 1) for kv in rest.split() if "=" in kv)
            key = f"{kind}:{u.get('id')}" if kind == "van" else f"{kind}:{u.get('side')}:{u.get('id')}"
            try:
                pt = [float(u["x"]), float(u["z"])]
            except (KeyError, ValueError):
                continue
            tr = trails.setdefault(key, [])
            if not tr or abs(tr[-1][0] - pt[0]) + abs(tr[-1][1] - pt[1]) > 4:
                tr.append(pt)
        for tt, kind, rest in rows:
            if tt < last - 4 or kind not in units:
                continue
            u = dict(kv.split("=", 1) for kv in rest.split() if "=" in kv)
            # A truck's road route still ahead (ZCR_LiveMap wps=x,z;x,z).
            if u.get("wps", "-") != "-":
                u["wps"] = [[float(v) for v in xy.split(",")] for xy in u["wps"].split(";") if "," in xy]
            else:
                u.pop("wps", None)
            for k in ("x", "z", "men", "cargo", "cap", "kmh", "ride", "route", "sx", "sz"):
                if k in u:
                    try:
                        u[k] = float(u[k])
                    except ValueError:
                        pass
            for k in ("to", "from", "base", "what"):
                if k in u:
                    u[k] = u[k].replace("_", " ")
            units[kind].append(u)
        # Vans: their planned route (lab/roadgraph.py routes.json, by the route the game picked) and the game's own path now.
        paths = {m.group(1): [[float(v) for v in xy.split(",")] for xy in m.group(2).split(";")] for m in PATH_OF.finditer(tail)}
        # The route number is the line in the run's own routes.txt (seeded at its start); its road points come from
        # routes.json by the same ends, else the run's waypoints themselves (routes.json rebuilt since).
        routes = {}
        rf = ROOT / ".runtime" / "maps" / map_slug / "routes.json"
        mine = run_routes(run)
        if units["van"] and (rf.exists() or mine):
            ok = [r for r in json.loads(rf.read_text(encoding="utf-8")).get("routes", []) if r.get("ok")] if rf.exists() else []
            by_ends = {(round(r["a"][0]), round(r["a"][1]), round(r["b"][0]), round(r["b"][1])): r for r in ok}
            for v in units["van"]:
                ri = int(v.get("route", -1))
                if ri < 0:
                    continue
                if mine:
                    if ri >= len(mine):
                        continue
                    ends, wps = mine[ri]
                    r = by_ends.get(ends)
                    routes[v["id"]] = r["points"][::2] + [r["points"][-1]] if r else wps
                elif ri < len(ok):
                    routes[v["id"]] = ok[ri]["points"][::2] + [ok[ri]["points"][-1]]
        # What each side attacks and defends now (28 Oct, Martin: "Commander Lab could show the main efforts, attacks, because
        # currently I don't know what is actually being attacked or defended"): its latest [ZCR][EFFORTS], every 30 s.
        efforts = {}
        for m in EFFORTS.finditer(tail):
            try:
                e = json.loads(m.group(3).strip())
            except ValueError:
                continue
            efforts[m.group(2)] = {"t": int(m.group(1)), "main": e.get("main") or "", "attack": e.get("attack") or [],
                                   "defend": e.get("defend") or [], "hold": e.get("hold") or [], "home": e.get("home") or 0}
        # Who holds each base now and each side's plan in words: the strategist's latest snapshots (about every 50 s).
        bases_now, intents = [], {}
        snap = run / "profile" / "zcr" / "snapshots.jsonl"
        if snap.exists():
            with open(snap, "rb") as f:
                f.seek(max(0, snap.stat().st_size - 300_000))
                snaps = f.read().decode("utf-8", "replace").splitlines()
            for line in snaps[-6:]:
                try:
                    s = json.loads(line)
                except ValueError:
                    continue
                intents[s.get("faction", "")] = s.get("intent") or ""
                bases_now = [{"name": b.get("name"), "owner": b.get("owner"), "x": b.get("x"), "z": b.get("z"), "hq": bool(b.get("hq"))}
                             for b in s.get("bases") or []]
        try:
            attack_plans = plans_in_use(run, log, map_slug)
        except OSError:
            attack_plans = []
        # A side Gemini commands: its live plan replaces the stored one it started with.
        try:
            gemini, gemini_intents = live_plans(run)
        except OSError:
            gemini, gemini_intents = [], {}
        if gemini:
            attack_plans = [p for p in attack_plans if p["side"] not in {g["side"] for g in gemini}] + gemini
        intents.update(gemini_intents)
        return {"run": run.name, "live": True, "t": last, "teams": units["team"], "trucks": units["truck"], "vans": units["van"], "builders": units["builder"],
                "paths": paths, "routes": routes, "trails": trails, "efforts": efforts, "bases_now": bases_now, "intents": intents,
                "attack_plans": attack_plans}
    return {"live": False}
