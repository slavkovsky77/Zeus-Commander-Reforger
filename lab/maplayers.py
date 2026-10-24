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


def slug(world: str) -> str:
    w = world.lower()
    if "arland" in w:
        return "arland"
    if "eden" in w or "everon" in w:
        return "everon"
    return w


def kind(run: Path) -> str:
    n = run.name
    if n.startswith("drivetest-"):
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
            if d.get("size") == st.st_size and d.get("mtime") == int(st.st_mtime):
                return d
        except (OSError, ValueError):
            pass
    data = log.read_bytes()
    w = WORLD.search(data[:2_000_000])
    d = {"run": run.name, "kind": kind(run), "size": st.st_size, "mtime": int(st.st_mtime),
         "map": slug(w.group(1).decode()) if w else "", "access": [], "spawns": {}, "arrived": [], "lost": [],
         "movefail": [], "placed": [], "bases": []}
    if d["map"]:
        d["access"] = [[int(s), int(x), int(z), int(v)] for s, x, z, v in ACCESS.findall(data)]
        d["spawns"] = {c.decode(): [int(x), int(z), int(s)] for c, x, z, s in SPAWN.findall(data)}
        d["arrived"] = sorted({c.decode() for c in ARRIVE.findall(data)})
        d["lost"] = [[c.decode(), why.decode(), int(x), int(z)] for c, why, x, z in LOST.findall(data)]
        d["movefail"] = [[int(t), side.decode(), veh.decode(), err.decode(), int(x), int(z)] for t, side, veh, err, x, z in MOVEFAIL.findall(data)]
        d["placed"] = [[f.decode(), ty.decode(), round(float(x)), round(float(z))] for f, ty, x, z in PLACED.findall(data) if b"DEPOT" in ty]
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


def layers(map_slug: str, since_h: float = 0, kinds: str = "match") -> dict:
    """since_h: only runs started in the last since_h hours (0: every run since FROM_DAY) - 25 Oct, Martin: "let's reset
    the runs to today only"; kinds: "match" (watched and headless matches), "test" (sub-lab drive tests), "all" (also
    probes and the other sub-labs) - "since the 20th there were a lot of blind tests"."""
    allowed = {"match": ("match",), "test": ("test",), "both": ("match", "test")}.get(kinds, ("match", "test", "other"))
    started = time.time()
    floor = time.mktime(time.strptime(FROM_DAY, "%Y%m%d"))
    if since_h:
        floor = max(floor, time.time() - since_h * 3600)
    runs = sorted((r for r in RUNS.iterdir() if r.is_dir() and run_time(r) >= floor), key=run_time)
    bases, spots, built, traps = [], {}, [], []
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
    return {"map": map_slug, "runs": scanned, "since_h": since_h, "kinds": kinds, "bases": out_bases,
            "depot_spots": [{k: v for k, v in s.items() if k != "runs"} | {"runs": len(s["runs"])} for s in spots.values()],
            "depots_built": out_built, "traps": out_traps, "routes": routes, "built_s": round(time.time() - started, 1),
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


def live(map_slug: str) -> dict:
    """The running game on this map (its log written in the last 90 s): the last [ZCR][LIVE] round - teams, supply trucks,
    test vans - with each van's planned route and the game's current path (lab app /api/map/live)."""
    runs = sorted((r for r in RUNS.iterdir() if r.is_dir()), key=run_time, reverse=True)[:15]
    for run in runs:
        logs = sorted(run.glob("logs/*/console.log"))
        if not logs or time.time() - logs[-1].stat().st_mtime > 90:
            continue
        log = logs[-1]
        if run.name not in _live_world:
            with open(log, "rb") as f:
                w = WORLD.search(f.read(2_000_000))
            _live_world[run.name] = slug(w.group(1).decode()) if w else ""
        if _live_world[run.name] != map_slug:
            continue
        size = log.stat().st_size
        with open(log, "rb") as f:
            f.seek(max(0, size - 600_000))
            tail = f.read().decode("utf-8", "replace")
        rows = [(int(m.group(1)), m.group(2), m.group(3)) for m in LIVE.finditer(tail)]
        if not rows:
            return {"run": run.name, "live": False}
        last = max(r[0] for r in rows)
        units = {"team": [], "truck": [], "van": []}
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
            for k in ("x", "z", "men", "cargo", "cap", "kmh", "ride", "route"):
                if k in u:
                    try:
                        u[k] = float(u[k])
                    except ValueError:
                        pass
            for k in ("to", "from"):
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
        return {"run": run.name, "live": True, "t": last, "teams": units["team"], "trucks": units["truck"], "vans": units["van"],
                "paths": paths, "routes": routes, "trails": trails}
    return {"live": False}
