"""Road graph and supply routes for one map (24 Oct night - Martin: "supply lines should be planned up front... trucks
follow precomputed routes", review note 394; plan page M4 https://claude.ai/artifact/EAVqib8JhtDtkVxGB3KKSV).

Input: the map dump (python lab/reforger.py ... --extra "-zcrMapDump -aicfOff" -> .runtime/maps/<map>/map_roads.jsonl)
and the Map tab's layers (lab/maplayers.py: bases, where vehicles got stuck). The game's road network has no links
between roads, so the graph is ours: each road's points in order, and each road's two ends joined to the nearest point
of another road within JOIN_M (the junction pieces). A stretch costs its length times a factor for its road (main
roads cheaper, farm tracks dearer) plus a penalty where vehicles got stuck in past runs.

Output, in .runtime/maps/<map>/:
  routes.json   every route: from, to, length, the road points, the waypoints a truck gets (every ~STEP_M and at each
                junction), the stuck places it passes
  routes.txt    the same waypoints for the game: "route <n> <from_x> <from_z> <to_x> <to_z> <count>" then "x z" lines

    python lab/roadgraph.py arland          # graph check + the supply test's routes + base-to-base routes
"""
import heapq
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / ".runtime" / "maps"
sys.path.insert(0, str(Path(__file__).resolve().parent))
JOIN_M = 12
STEP_M = 300
# A junction gets a waypoint only where the route turns there by more than TURN_DEG (24 Oct night: a waypoint every ~100 m
# and at every road change made the vans brake at each - median trip 261 s against the game planner's 173 s).
TURN_DEG = 30
TRAP_M = 20
TRAP_COST_M = 400


def factor(width: float) -> float:
    if width >= 6:
        return 0.85            # main road
    if width >= 4:
        return 1.0
    if width >= 2.5:
        return 1.35            # farm and forest tracks
    return 1.0                 # the 1 m junction pieces between roads


class Graph:
    def __init__(self, roads, traps=()):
        self.x, self.z, self.w, self.road = [], [], [], []
        self.adj = {}
        ends = []
        for ri, r in enumerate(roads):
            ids = []
            for px, pz in r["p"]:
                ids.append(len(self.x))
                self.x.append(px)
                self.z.append(pz)
                self.w.append(r["w"])
                self.road.append(ri)
            for a, b in zip(ids, ids[1:]):
                self.link(a, b, factor(r["w"]))
            if ids:
                ends += [ids[0], ids[-1]]
        # A spatial grid for nearest-point lookups.
        self.cell = 25
        self.grid = {}
        for i in range(len(self.x)):
            self.grid.setdefault(self.key(self.x[i], self.z[i]), []).append(i)
        self.junctions = 0
        for e in ends:
            best, bd = None, JOIN_M
            for j in self.near(self.x[e], self.z[e], JOIN_M):
                if self.road[j] == self.road[e]:
                    continue
                d = math.hypot(self.x[j] - self.x[e], self.z[j] - self.z[e])
                if d < bd:
                    best, bd = j, d
            if best is not None:
                self.link(e, best, 1.0)
                self.junctions += 1
        # Stuck places: passing one costs as much as a detour of up to TRAP_COST_M (more for places where vehicles got
        # stuck more often), spread over the road points within TRAP_M of it - so a route pays it about once, however
        # many of its points lie in the zone (24 Oct: charged per point, the US main base's trucks went round the island).
        self.penalty = [0.0] * len(self.x)
        self.trap_at = [None] * len(self.x)
        for ti, t in enumerate(traps):
            zone = [j for j in self.near(t["x"], t["z"], TRAP_M) if math.hypot(self.x[j] - t["x"], self.z[j] - t["z"]) <= TRAP_M]
            if not zone:
                continue
            pen = min(TRAP_COST_M, 60 * math.log2(1 + t["count"])) / len(zone)
            for j in zone:
                if pen > self.penalty[j]:
                    self.penalty[j] = pen
                    self.trap_at[j] = ti

    def key(self, x, z):
        return (int(x // self.cell), int(z // self.cell))

    def near(self, x, z, r):
        k = int(math.ceil(r / self.cell))
        cx, cz = self.key(x, z)
        for gx in range(cx - k, cx + k + 1):
            for gz in range(cz - k, cz + k + 1):
                yield from self.grid.get((gx, gz), ())

    def link(self, a, b, f):
        d = math.hypot(self.x[a] - self.x[b], self.z[a] - self.z[b])
        self.adj.setdefault(a, []).append((b, d, f))
        self.adj.setdefault(b, []).append((a, d, f))

    def nearest(self, x, z, min_width=3.0, max_m=300):
        best, bd = None, max_m
        for j in self.near(x, z, max_m):
            if self.w[j] < min_width:
                continue
            d = math.hypot(self.x[j] - x, self.z[j] - z)
            if d < bd:
                best, bd = j, d
        return best, bd

    def components(self):
        seen, sizes = set(), []
        for s in range(len(self.x)):
            if s in seen:
                continue
            stack, n = [s], 0
            seen.add(s)
            while stack:
                u = stack.pop()
                n += 1
                for v, _, _ in self.adj.get(u, ()):
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            sizes.append(n)
        return sorted(sizes, reverse=True)

    def path(self, src, dst, plain=False):
        dist, prev = {src: 0.0}, {}
        heap = [(0.0, src)]
        while heap:
            c, u = heapq.heappop(heap)
            if u == dst:
                break
            if c > dist.get(u, 1e18):
                continue
            for v, d, f in self.adj.get(u, ()):
                nc = c + (d if plain else d * f + self.penalty[v])
                if nc < dist.get(v, 1e18):
                    dist[v] = nc
                    prev[v] = u
                    heapq.heappush(heap, (nc, v))
        if dst not in dist:
            return None, None
        nodes = [dst]
        while nodes[-1] != src:
            nodes.append(prev[nodes[-1]])
        return nodes[::-1], dist[dst]


def heading(g: Graph, a, b):
    return math.degrees(math.atan2(g.x[b] - g.x[a], g.z[b] - g.z[a]))


def turn(g: Graph, nodes, i, reach=3):
    """How much the route turns at nodes[i]: the heading over a few points before against a few points after."""
    a, b = nodes[max(0, i - reach)], nodes[min(len(nodes) - 1, i + reach)]
    if a == nodes[i] or b == nodes[i]:
        return 0.0
    d = abs(heading(g, nodes[i], b) - heading(g, a, nodes[i])) % 360
    return min(d, 360 - d)


def waypoints(g: Graph, nodes, step=STEP_M):
    """Points a truck gets: every ~step metres along the route, and at a junction where the route turns (changes road
    and bends by TURN_DEG or more) - there the game's planner could take the other branch."""
    out, run = [], 0.0
    for i, n in enumerate(nodes):
        if i == 0:
            continue
        p = nodes[i - 1]
        run += math.hypot(g.x[n] - g.x[p], g.z[n] - g.z[p])
        switch = i + 1 < len(nodes) and g.road[nodes[i + 1]] != g.road[n] and turn(g, nodes, i) >= TURN_DEG
        if run >= step or switch or i == len(nodes) - 1:
            out.append([round(g.x[n], 1), round(g.z[n], 1)])
            run = 0.0
    # Drop waypoints closer than 60 m to the one before (junction pieces make clusters).
    kept = []
    for w in out:
        if kept and math.hypot(w[0] - kept[-1][0], w[1] - kept[-1][1]) < 60 and w is not out[-1]:
            continue
        kept.append(w)
    return kept


def route(g: Graph, a, b, name_a="", name_b="", traps=()):
    sa, da = g.nearest(*a)
    sb, db = g.nearest(*b)
    if sa is None or sb is None:
        return {"from": name_a, "to": name_b, "ok": False, "why": "no road within 300 m"}
    nodes, cost = g.path(sa, sb)
    if not nodes:
        return {"from": name_a, "to": name_b, "ok": False, "why": "roads not connected"}
    length = sum(math.hypot(g.x[n] - g.x[p], g.z[n] - g.z[p]) for p, n in zip(nodes, nodes[1:]))
    _, shortest = g.path(sa, sb, plain=True)
    passed = sorted({g.trap_at[n] for n in nodes if g.trap_at[n] is not None})
    return {"from": name_a, "to": name_b, "ok": True, "a": list(a), "b": list(b), "length_m": round(length),
            "straight_m": round(math.hypot(b[0] - a[0], b[1] - a[1])), "shortest_m": round(shortest or 0), "start_road_m": round(da), "end_road_m": round(db),
            "cost": round(cost), "points": [[round(g.x[n], 1), round(g.z[n], 1)] for n in nodes],
            "waypoints": waypoints(g, nodes),
            "stuck_places": [{"x": traps[t]["x"], "z": traps[t]["z"], "count": traps[t]["count"]} for t in passed]}


def build(slug: str) -> dict:
    import maplayers
    import drivetest
    roads = [json.loads(l) for l in (MAPS / slug / "map_roads.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    layers = maplayers.layers(slug)
    traps = [t for t in layers["traps"] if t["count"] >= 3]
    g = Graph(roads, traps)
    comps = g.components()
    routes = []
    # The supply test's vans: each depot spot to its base (lab/drivetest.py arland-supply).
    track = drivetest.TRACKS.get(f"{slug}-supply")
    if track:
        for pair in track[1].split("|"):
            s, t = pair.split(">")
            a = tuple(float(v) for v in s.split(","))
            b = tuple(float(v) for v in t.split(","))
            routes.append(route(g, a, b, f"depot {s}", f"base {t}", traps))
    # Base to base along the radio links.
    bases = layers["bases"]
    done = set()
    for b in bases:
        for ln in b["links"]:
            o = next((x for x in bases if x["name"] == ln), None)
            key = tuple(sorted((b["name"] + str(b["x"]), ln + str(o["x"] if o else ""))))
            if not o or key in done:
                continue
            done.add(key)
            routes.append(route(g, (b["x"], b["z"]), (o["x"], o["z"]), b["name"], o["name"], traps))
    out = {"map": slug, "nodes": len(g.x), "edges": sum(len(v) for v in g.adj.values()) // 2, "junctions": g.junctions,
           "components": comps[:8], "routes": routes}
    (MAPS / slug / "routes.json").write_text(json.dumps(out), encoding="utf-8")
    lines = []
    for i, r in enumerate(x for x in routes if x["ok"]):
        lines.append(f"route {i} {r['a'][0]:.0f} {r['a'][1]:.0f} {r['b'][0]:.0f} {r['b'][1]:.0f} {len(r['waypoints'])}")
        lines += [f"{w[0]} {w[1]}" for w in r["waypoints"]]
    (MAPS / slug / "routes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "arland"
    out = build(slug)
    print(f"{slug}: {out['nodes']} road points, {out['edges']} links, {out['junctions']} junctions, "
          f"components (largest first) {out['components']}")
    for r in out["routes"]:
        if not r["ok"]:
            print(f"  {r['from']} -> {r['to']}: NO ROUTE ({r['why']})")
            continue
        print(f"  {r['from']} -> {r['to']}: {r['length_m']} m by road (shortest road {r['shortest_m']}, straight {r['straight_m']}), start {r['start_road_m']} m off, "
              f"{len(r['waypoints'])} waypoints, passes {len(r['stuck_places'])} stuck places")
    return 0


if __name__ == "__main__":
    sys.exit(main())
