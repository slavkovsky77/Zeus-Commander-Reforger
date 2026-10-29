"""Attack plans read from the map (29 Oct night - Martin, review note 449: "attacks should be planned in some smarter way,
we have to read the maps; planning the driving route first, then some coordination of teams where they would actually
attack, maybe some timing; a set of waypoints that would go on under attack; with the map you can read where they have
cover"; "where it could hide if something happens - drone maybe?"; "I imagine having lines of attack").

The geometry is computed here, exactly; a model may only choose between the plans (lab/attackpick.py). For one objective:

  ground     -zcrAttackScan (ZCR_AttackScan.c): a 10 m grid within 1 km - height, how many of 9 defender eye points on
             the objective see a crouching soldier there, a roof or canopy overhead; the map dump's trees per 25 m cell
  lanes      one search outward from the objective over that grid: walking a cell costs more the more the objective
             sees it, far from any roof or canopy, on a steep slope - so every cell knows its cheapest cover-to-cover way in
  assembly   road points 300-650 m out that the objective can't see (nor anything within 20 m): where the teams get out
  drive      the road graph (lab/roadgraph.py) from the HQ to the assembly point; road stretches the objective sees are dear
  plan       per approach sector (8 of 45 degrees) the best assembly point; the 3 best sectors per HQ are the candidates.
             Each: 3 lanes (a team each, pushed apart), a hold line ~150 m out where the teams wait for each other, a
             support position with a view of the objective, a hiding spot (roof or canopy) for every lane waypoint, and
             pull-off spots under cover along the last kilometre of the drive

    python lab/attackplan.py farm            # .runtime/attack/farm_scan.jsonl -> farm_plans.json + farm_<hq>.png
"""
import argparse
import heapq
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import roadgraph  # noqa: E402

OUT = ROOT / ".runtime" / "attack"
MAPS = ROOT / ".runtime" / "maps"
ASSEMBLY_MIN, ASSEMBLY_MAX = 300, 650
GOAL_M = 50            # a lane ends this close to the objective's centre
HOLD_M = 150           # the hold line: this far out on each lane
LANE_GAP_M = 35        # lanes kept this far apart
WAYPOINT_M = 60        # a lane waypoint every ~this far
SEEN_COST = 6.0        # walking a cell all 9 eyes see costs 7x a hidden one
NO_ROOF_COST = 0.6     # ... and more when no roof or canopy is within ROOF_REACH_M
ROOF_REACH_M = 40
DRIVE_SEEN_COST = 5.0  # a road stretch the objective sees, per metre
WALK_MPS, DRIVE_MPS = 1.5, 8.0


class Ground:
    def __init__(self, scan: Path, slug: str):
        lines = scan.read_text(encoding="utf-8").splitlines()
        head = json.loads(lines[0])
        self.ox, self.oy, self.oz = head["objective"]
        self.step = head["step"]
        self.cells = {}
        for l in lines[1:]:
            c = json.loads(l)
            self.cells[self.key(c["x"], c["z"])] = (c["x"], c["z"], c["y"], c["seen"], c["roof"])
        trees = json.loads((MAPS / slug / "map_trees.json").read_text(encoding="utf-8"))
        self.tree_cell = trees["cell"]
        self.trees = {k: v for k, v in trees["trees"].items()}
        self.roof_m = self.roof_distance()

    def key(self, x, z):
        return (round(x / self.step), round(z / self.step))

    def at(self, x, z):
        return self.cells.get(self.key(x, z))

    def tree_count(self, x, z):
        return self.trees.get(f"{int(x // self.tree_cell)},{int(z // self.tree_cell)}", 0)

    def covered(self, k):
        x, z, _, _, roof = self.cells[k]
        return roof or self.tree_count(x, z) >= 6

    def roof_distance(self):
        """Metres from every cell to the nearest roof or canopy (multi-source search over the grid)."""
        dist = {k: 0.0 for k in self.cells if self.covered(k)}
        heap = [(0.0, k) for k in dist]
        heapq.heapify(heap)
        while heap:
            d, k = heapq.heappop(heap)
            if d > dist.get(k, 1e18):
                continue
            for n, w in self.neighbours(k):
                nd = d + w
                if nd < dist.get(n, 1e18):
                    dist[n] = nd
                    heapq.heappush(heap, (nd, n))
        return dist

    def neighbours(self, k):
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx or dz:
                    n = (k[0] + dx, k[1] + dz)
                    if n in self.cells:
                        yield n, self.step * (1.414 if dx and dz else 1.0)

    def walk_cost(self, a, b, metres, avoid=None):
        _, _, ya, _, _ = self.cells[a]
        _, _, yb, seen, _ = self.cells[b]
        cost = metres * (1 + SEEN_COST * seen / 9)
        if self.roof_m.get(b, 1e9) > ROOF_REACH_M:
            cost += metres * NO_ROOF_COST
        slope = abs(yb - ya) / metres
        if slope > 0.3:
            cost += metres * 4 * (slope - 0.3)
        if avoid and b in avoid:
            cost += metres * 3
        return cost

    def lanes_from_objective(self, avoid=None):
        """The cheapest way in from every cell: cost and next cell toward the objective (one search outward)."""
        goal = [k for k, c in self.cells.items() if math.hypot(c[0] - self.ox, c[1] - self.oz) <= GOAL_M]
        dist = {k: 0.0 for k in goal}
        nxt = {}
        heap = [(0.0, k) for k in goal]
        heapq.heapify(heap)
        while heap:
            d, k = heapq.heappop(heap)
            if d > dist.get(k, 1e18):
                continue
            for n, w in self.neighbours(k):
                nd = d + self.walk_cost(n, k, w, avoid)
                if nd < dist.get(n, 1e18):
                    dist[n] = nd
                    nxt[n] = k
                    heapq.heappush(heap, (nd, n))
        return dist, nxt

    def hidden_spot(self, x, z, r=20):
        k = self.key(x, z)
        n = int(math.ceil(r / self.step))
        for dx in range(-n, n + 1):
            for dz in range(-n, n + 1):
                c = self.cells.get((k[0] + dx, k[1] + dz))
                if c and c[3] > 0:
                    return False
        return k in self.cells

    def nearest_cover(self, x, z, r=60):
        k = self.key(x, z)
        n = int(math.ceil(r / self.step))
        best, bd = None, r + 1
        for dx in range(-n, n + 1):
            for dz in range(-n, n + 1):
                kk = (k[0] + dx, k[1] + dz)
                if kk in self.cells and self.covered(kk):
                    c = self.cells[kk]
                    d = math.hypot(c[0] - x, c[1] - z)
                    if d < bd:
                        best, bd = (c[0], c[1], "roof" if c[4] else "trees"), d
        return (best, round(bd)) if best else (None, None)


def trace(start, nxt, g: Ground):
    path, k = [start], start
    while k in nxt:
        k = nxt[k]
        path.append(k)
    return [(g.cells[k][0], g.cells[k][1]) for k in path]


def thin(points, every=WAYPOINT_M):
    out, run = [points[0]], 0.0
    for p, q in zip(points, points[1:]):
        run += math.hypot(q[0] - p[0], q[1] - p[1])
        if run >= every:
            out.append(q)
            run = 0.0
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def lane_stats(points, g: Ground):
    cells = [g.at(x, z) for x, z in points]
    cells = [c for c in cells if c]
    n = max(1, len(cells))
    length = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(points, points[1:]))
    seen = sum(1 for c in cells if c[3] > 0)
    roofed = sum(1 for (x, z) in points if g.roof_m.get(g.key(x, z), 1e9) <= ROOF_REACH_M)
    return {"length_m": round(length), "seen_pct": round(100 * seen / n), "cover_within_40m_pct": round(100 * roofed / max(1, len(points)))}


def drive_search(graph: roadgraph.Graph, g: Ground, src):
    """Road-graph search from the HQ's road point; stretches the objective sees cost more."""
    seen_at = {}
    for i in range(len(graph.x)):
        c = g.at(graph.x[i], graph.z[i])
        if c and c[3] > 0:
            seen_at[i] = c[3] / 9
    dist, prev = {src: 0.0}, {}
    heap = [(0.0, src)]
    while heap:
        c, u = heapq.heappop(heap)
        if c > dist.get(u, 1e18):
            continue
        for v, d, f in graph.adj.get(u, ()):
            nc = c + d * f + graph.penalty[v] + d * DRIVE_SEEN_COST * seen_at.get(v, 0.0)
            if nc < dist.get(v, 1e18):
                dist[v] = nc
                prev[v] = u
                heapq.heappush(heap, (nc, v))
    return dist, prev


def road_path(graph, prev, dst):
    nodes = [dst]
    while nodes[-1] in prev:
        nodes.append(prev[nodes[-1]])
    nodes.reverse()
    return nodes


def support_position(g: Ground, angle, assembly):
    """A spot that sees the objective (and so is seen by it - in cover), 150-500 m out on the attack's side, high ground."""
    best, bs = None, -1e9
    for k, (x, z, y, seen, roof) in g.cells.items():
        r = math.hypot(x - g.ox, z - g.oz)
        if seen < 3 or not (150 <= r <= 500):
            continue
        a = math.degrees(math.atan2(x - g.ox, z - g.oz))
        da = abs((a - angle + 180) % 360 - 180)
        if da > 60:
            continue
        cover = 1 if (roof or g.tree_count(x, z) >= 3) else 0
        s = (y - g.oy) * 0.5 + cover * 20 - da * 0.2 - math.hypot(x - assembly[0], z - assembly[1]) / 40
        if s > bs:
            best, bs = {"x": x, "z": z, "height_over_objective_m": round(y - g.oy, 1), "sees": seen, "cover": bool(cover)}, s
    return best


SIDE_MAX_DEG = 90      # an approach at most this far round from the side the attack comes from - no driving round the objective
SIDE_FREE_DEG = 30     # ... and every degree beyond this costs SIDE_COST seconds
SIDE_COST = 1.0


def plan_for_hq(g: Ground, graph, hq, lanes):
    dist, nxt = lanes
    sa, _ = graph.nearest(hq["x"], hq["z"])
    ddist, dprev = drive_search(graph, g, sa)
    # 29 Oct evening: the side the attack comes from. Every plan from the far (south) HQ to Farm did worse than no plan,
    # the two driving round to its east side (3 km) among them; across Arland's bases the cover-weighted walk alone made
    # the algorithm take the same side of an objective from every base, even across it.
    from_deg = math.degrees(math.atan2(hq["x"] - g.ox, hq["z"] - g.oz))
    candidates = []
    for i in range(len(graph.x)):
        x, z = graph.x[i], graph.z[i]
        r = math.hypot(x - g.ox, z - g.oz)
        if not (ASSEMBLY_MIN <= r <= ASSEMBLY_MAX) or i not in ddist or graph.w[i] < 3:
            continue
        k = g.key(x, z)
        if k not in dist or not g.hidden_spot(x, z):
            continue
        angle = math.degrees(math.atan2(x - g.ox, z - g.oz))
        off = abs((angle - from_deg + 180) % 360 - 180)
        if off > SIDE_MAX_DEG:
            continue
        drive_m = ddist[i]
        walk = dist[k]
        total = drive_m / DRIVE_MPS + walk / WALK_MPS + SIDE_COST * max(0.0, off - SIDE_FREE_DEG)
        candidates.append((total, i, k, angle, drive_m, walk))
    best = {}
    for c in candidates:
        sector = compass(c[3])
        if sector not in best or c[0] < best[sector][0]:
            best[sector] = c
    plans = []
    for n, (total, i, k, angle, drive_m, walk) in enumerate(sorted(best.values())[:3]):
        ax, az = graph.x[i], graph.z[i]
        nodes = road_path(graph, dprev, i)
        route_pts = [(round(graph.x[j], 1), round(graph.z[j], 1)) for j in nodes]
        route_len = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(route_pts, route_pts[1:]))
        # Three lanes: the main one from the assembly point, two from 40 m either side, pushed apart from the ones before.
        side = (math.cos(math.radians(angle)), -math.sin(math.radians(angle)))
        starts = [(ax, az), (ax + side[0] * 40, az + side[1] * 40), (ax - side[0] * 40, az - side[1] * 40)]
        lane_list, avoid = [], set()
        for li, (sx, sz) in enumerate(starts):
            ld, ln = lanes if li == 0 else g.lanes_from_objective(avoid)
            sk = g.key(sx, sz)
            if sk not in ld:
                sk = k
            pts = trace(sk, ln, g)
            for (x, z) in pts:
                kk = g.key(x, z)
                rr = int(math.ceil(LANE_GAP_M / g.step))
                for dx in range(-rr, rr + 1):
                    for dz in range(-rr, rr + 1):
                        avoid.add((kk[0] + dx, kk[1] + dz))
            wps = thin(pts)
            hold = min(wps, key=lambda p: abs(math.hypot(p[0] - g.ox, p[1] - g.oz) - HOLD_M))
            hides = []
            for (x, z) in wps:
                spot, d = g.nearest_cover(x, z)
                hides.append({"at": [x, z], "hide": [spot[0], spot[1]] if spot else None, "kind": spot[2] if spot else None, "m": d})
            lane_list.append({"team": li + 1, "waypoints": [[x, z] for x, z in wps], "hold": [hold[0], hold[1]],
                              "hiding": hides, **lane_stats(pts, g)})
        # Pull-offs: cover beside the last kilometre of the drive.
        pulloffs, last = [], None
        for (x, z) in route_pts:
            if math.hypot(x - ax, z - az) > 1000 or math.hypot(x - g.ox, z - g.oz) < ASSEMBLY_MIN:
                continue
            spot, d = g.nearest_cover(x, z, 30)
            if spot and (last is None or math.hypot(spot[0] - last[0], spot[1] - last[1]) > 250):
                pulloffs.append({"x": spot[0], "z": spot[1], "kind": spot[2]})
                last = spot
        seen_road = sum(1 for (x, z) in route_pts if (g.at(x, z) or (0, 0, 0, 0, 0))[3] > 0)
        plans.append({
            "id": "ABC"[n], "approach_deg": round((angle + 360) % 360), "approach": compass(angle),
            "assembly": {"x": round(ax, 1), "z": round(az, 1), "from_objective_m": round(math.hypot(ax - g.ox, az - g.oz))},
            "drive": {"length_m": round(route_len), "points": route_pts, "road_points_seen_by_objective": seen_road},
            "lanes": lane_list, "support": support_position(g, angle, (ax, az)), "pulloffs": pulloffs[:4],
            "minutes": {"drive": round(route_len / DRIVE_MPS / 60, 1), "walk": round(lane_list[0]["length_m"] / WALK_MPS / 60, 1)},
            "score": round(total), "timing": [
                "all teams drive to the assembly point and get out",
                "wait there for every team (at most 3 minutes), drones on the objective",
                "the support team takes the support position and opens fire",
                "the assault teams go together along their lanes",
                f"each team holds at the hold line (~{HOLD_M} m out) until the others are there, then all go in"]})
    return plans


def compass(angle):
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return names[int(((angle + 360) % 360 + 22.5) // 45) % 8]


EXPLORE = 6.0   # --export explore: an approach run n times gets EXPLORE / sqrt(n + 1) on top of its estimate


def measured_pick(objective, hq: dict, explore: bool = False) -> tuple:
    """(plan id or 'none', why) from lab/attackscore.py's scores: the approach with the best estimate from this HQ - the
    measured mean shrunk toward AI Conflict's own approach (no plan); an approach never run counts as no plan. 'none' when
    no plan does better than AI Conflict's own (29 Oct night: from the south HQ every plan did worse). explore: the
    upper bound instead, so an untried approach gets its runs."""
    import attackscore
    rows = attackscore.rows_for(attackscore.load(), objective, (hq["x"], hq["z"]))
    options = [(None, "none")] + [((p["assembly"]["x"], p["assembly"]["z"]), p["id"]) for p in hq["plans"]]
    best, why = None, []
    for asm, pid in options:
        est, runs, _ = attackscore.estimate(rows, asm, objective)
        value = est + (EXPLORE / math.sqrt(runs + 1) if explore else 0)
        why.append(f"{pid} {est} ({runs} runs)")
        if best is None or value > best[0] + 1e-9:
            best = (value, pid)
    return best[1], ", ".join(why)


def export(name: str, which: str) -> Path:
    """The chosen plan per HQ for the game (-zcrAttackPlan reads $profile:zcr/attackplan.txt, AICF_ZcrAttackPlan.c): which =
    'algorithm' (its best score), 'model' (lab/attackpick.py's picks; the algorithm's where the model gave none), 'measured'
    (the best measured approach, lab/attackscore.py) or 'explore' (measured, untried approaches favoured). A pick of 'none'
    writes no plan for that HQ: its teams take AI Conflict's own approach."""
    plans = json.loads((OUT / f"{name}_plans.json").read_text(encoding="utf-8"))
    picks = {}
    if which == "model":
        for h in json.loads((OUT / f"{name}_picks.json").read_text(encoding="utf-8"))["hqs"]:
            picks[tuple(h["hq"])] = (h["model"] or {}).get("pick")
    lines = []
    for hq in plans["hqs"]:
        if which in ("measured", "explore"):
            pick, why = measured_pick((plans["objective"]["x"], plans["objective"]["z"]), hq, which == "explore")
            print(f"HQ {hq['x']:.0f},{hq['z']:.0f}: measured estimates {why}")
        else:
            pick = picks.get((hq["x"], hq["z"])) or hq["algorithm_pick"]
        if str(pick).lower() == "none":
            print(f"HQ {hq['x']:.0f},{hq['z']:.0f}: no plan - AI Conflict's own approach ({which})")
            continue
        pl = next((p for p in hq["plans"] if p["id"] == pick), hq["plans"][0])
        lines += plan_lines(hq, plans["objective"], pl)
        print(f"HQ {hq['x']:.0f},{hq['z']:.0f}: plan {pl['id']} from the {pl['approach']} ({which})")
    seed = OUT / f"seed_{name}_{which}"
    (seed / "zcr").mkdir(parents=True, exist_ok=True)
    (seed / "zcr" / "attackplan.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {seed / 'zcr' / 'attackplan.txt'}")
    return seed


def plan_lines(origin: dict, objective: dict, pl: dict) -> list:
    """One plan in the game's format (AICF_ZcrAttackPlan.c)."""
    a_ = pl["assembly"]
    lines = [f"plan {origin['x']:.1f} {origin['z']:.1f} {objective['x']:.1f} {objective['z']:.1f} {a_['x']} {a_['z']} {pl['id']}"]
    for ln in pl["lanes"]:
        lines.append(f"lane {len(ln['waypoints'])} {ln['hold'][0]} {ln['hold'][1]}")
        lines += [f"{x} {z}" for x, z in ln["waypoints"]]
    return lines


FROM_MIN_M, FROM_MAX_M = 700, 4000   # --all: plans for attacks from bases this far from the objective


def plan_all(slug: str, scan_dir: Path, which: str) -> Path:
    """--all: the normal matches' plan file (29 Oct evening, Martin's go, review note 451). Every base of the map scanned
    (-zcrAttackScan all writes $profile:zcr/attackscan/<x>_<z>.jsonl) is an objective, planned from every other base
    FROM_MIN_M-FROM_MAX_M away - a side's attacks start from wherever its teams are, mostly its bases; the game takes the
    plan from the origin nearest where a team started (AICF_ZcrAttackPlan.ForTeam). Per objective and origin: which =
    'measured' - the best measured approach where the lab has runs from there (lab/attackscore.py), else the algorithm's;
    'algorithm' - always the algorithm's. Writes .runtime/attack/<map>/plans.json and seed_<map>_all/zcr/attackplan.txt."""
    import shutil
    import time
    import attackscore
    scores = attackscore.load()
    dest = OUT / slug
    dest.mkdir(parents=True, exist_ok=True)
    heads = []
    for s in sorted(scan_dir.glob("*.jsonl")):
        h = json.loads(s.read_text(encoding="utf-8").splitlines()[0])
        shutil.copy(s, dest / f"scan_{s.name}")
        heads.append((dest / f"scan_{s.name}", h))
    roads = [json.loads(l) for l in (MAPS / slug / "map_roads.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    graph = roadgraph.Graph(roads, [])
    bases = [{"x": h["objective"][0], "z": h["objective"][2], "name": h.get("name", "")} for _, h in heads]
    out = {"map": slug, "objectives": []}
    lines = [f"world {slug}"]   # the game keeps a map's section only on that map (AICF_ZcrAttackPlan.Load)
    for scan, h in heads:
        t0 = time.time()
        g = Ground(scan, slug)
        lanes = g.lanes_from_objective()
        objective = {"x": g.ox, "z": g.oz, "y": g.oy, "name": h.get("name", "")}
        entry = {"objective": objective, "cells": len(g.cells), "seen_cells": sum(1 for c in g.cells.values() if c[3] > 0), "hqs": []}
        for b in bases:
            d = math.hypot(b["x"] - g.ox, b["z"] - g.oz)
            if not (FROM_MIN_M <= d <= FROM_MAX_M):
                continue
            plans = plan_for_hq(g, graph, b, lanes)
            if not plans:
                continue
            hq = {"x": b["x"], "z": b["z"], "name": b["name"], "from_objective_m": round(d), "plans": plans, "algorithm_pick": plans[0]["id"]}
            pick, why = hq["algorithm_pick"], "the algorithm's best score"
            if which == "measured" and attackscore.rows_for(scores, (g.ox, g.oz), (b["x"], b["z"])):
                pick, why = measured_pick((g.ox, g.oz), hq)
                why = "measured: " + why
            hq["pick"], hq["why"] = pick, why
            entry["hqs"].append(hq)
            if str(pick).lower() != "none":
                pl = next((p for p in plans if p["id"] == pick), plans[0])
                lines += plan_lines(b, objective, pl)
            else:   # no plan from here - so the game doesn't take a neighbouring base's plan instead
                lines.append(f"plan {b['x']:.1f} {b['z']:.1f} {objective['x']:.1f} {objective['z']:.1f} 0 0 none")
            chosen = "no plan" if str(pick).lower() == "none" else f"plan {pick} from the {next(p for p in plans if p['id'] == pick)['approach']}"
            print(f"  {objective['name']:24} from {b['name'] or '?':24} {round(d):5} m: {chosen} ({why})")
        out["objectives"].append(entry)
        print(f"{objective['name']}: {len(entry['hqs'])} origins, {time.time() - t0:.1f} s")
    (dest / "plans.json").write_text(json.dumps(out), encoding="utf-8")
    seed = OUT / f"seed_{slug}_all"
    (seed / "zcr").mkdir(parents=True, exist_ok=True)
    (seed / "zcr" / "attackplan.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {dest / 'plans.json'} and {seed / 'zcr' / 'attackplan.txt'} ({sum(1 for l in lines if l.startswith('plan '))} plans)")
    return seed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="the objective's short name: .runtime/attack/<name>_scan.jsonl (with --all: anything, e.g. all)")
    ap.add_argument("--map", default="arland")
    ap.add_argument("--all", default="", help="a folder of -zcrAttackScan all scans (or 'latest': the newest run's): plans for every "
                                              "base from every other base, the normal matches' plan file")
    ap.add_argument("--pick", default="measured", choices=["measured", "algorithm"], help="with --all: which plan per pair")
    ap.add_argument("--snapshot", default="", help="a snapshots.jsonl for the HQ positions (default: the newest run's)")
    ap.add_argument("--export", default="", choices=["", "model", "algorithm", "measured", "explore"],
                    help="write the game's plan file from the saved plans")
    ap.add_argument("--assembly", default="", help="min,max metres of the assembly point from the objective (default 300,650)")
    a = ap.parse_args()
    if a.assembly:
        global ASSEMBLY_MIN, ASSEMBLY_MAX
        ASSEMBLY_MIN, ASSEMBLY_MAX = (float(v) for v in a.assembly.split(","))
    if a.export:
        export(a.name, a.export)
        return 0
    if a.all:
        scan_dir = Path(a.all) if a.all != "latest" else max((ROOT / ".runtime" / "runs").glob("*/profile/zcr/attackscan"),
                                                            key=lambda p: p.stat().st_mtime)
        plan_all(a.map, scan_dir, a.pick)
        return 0
    g = Ground(OUT / f"{a.name}_scan.jsonl", a.map)
    roads = [json.loads(l) for l in (MAPS / a.map / "map_roads.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    graph = roadgraph.Graph(roads, [])
    snap = Path(a.snapshot) if a.snapshot else max((ROOT / ".runtime" / "runs").glob("*/profile/zcr/snapshots.jsonl"), key=lambda p: p.stat().st_mtime)
    bases = json.loads(snap.read_text(encoding="utf-8").splitlines()[0])["bases"]
    hqs = [b for b in bases if b.get("hq")]
    lanes = g.lanes_from_objective()
    out = {"objective": {"x": g.ox, "z": g.oz, "y": g.oy, "name": a.name}, "cells": len(g.cells),
           "seen_cells": sum(1 for c in g.cells.values() if c[3] > 0), "hqs": []}
    for hq in hqs:
        plans = plan_for_hq(g, graph, hq, lanes)
        out["hqs"].append({"x": hq["x"], "z": hq["z"], "from_objective_m": round(math.hypot(hq["x"] - g.ox, hq["z"] - g.oz)),
                           "plans": plans, "algorithm_pick": plans[0]["id"] if plans else None})
        for p in plans:
            print(f"HQ {hq['x']:.0f},{hq['z']:.0f}: plan {p['id']} from the {p['approach']} - assembly {p['assembly']['from_objective_m']} m out, "
                  f"drive {p['drive']['length_m']} m ({p['drive']['road_points_seen_by_objective']} road points seen), lane "
                  f"{p['lanes'][0]['length_m']} m, seen {p['lanes'][0]['seen_pct']}%, cover in reach {p['lanes'][0]['cover_within_40m_pct']}%, "
                  f"support {'yes' if p['support'] else 'none'}, score {p['score']}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.name}_plans.json").write_text(json.dumps(out), encoding="utf-8")
    print(f"written {OUT / (a.name + '_plans.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
