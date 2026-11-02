"""Fortification plans for AI Conflict's builders, chosen by the model from the map (2 Nov 2026 - Martin: "fortifications
should be planned via the LLM general - I think it will be probably much smarter in choosing the place and direction of
fortifications").

The split of the attack plans (lab/attackplan.py + attackpick.py, notes 394/396/449): the code computes the valid choices
from the map exactly, the model only chooses among them - the spots and the facing of each - with reasons; its answer is
checked, and today's placement stays the fallback in the game.

  candidates  a 10 m grid inside the base's building radius (from where the game placed small compositions in earlier runs,
              lab 'harvest'): off the roads, no building/wall/fence/rock within 7 m, not under trees or a roof, flat, 30 m+
              from the base point (its core stays free); a spot where the game already placed a small composition is 'proven'
  threats     per base, the directions of the other bases within 2.5 km (AI Conflict builds fortifications only at such a
              base), grouped into sectors up to 70 degrees wide; a sector's threat point is its nearest base
  measures    a viewshed from each spot (eye 1.5 m, target 1 m above the ground; terrain from the base's 10 m scan of
              lab/attackplan.py, buildings from the map dump, trees as a thinning screen): field of fire = share of the
              ground 20-300 m out in a 60 degree arc that is in view; approach lanes in view (the attack plans' lanes into
              this base from the threat's bases); cover behind = metres to a roof, wood or building in the rear half
  model       one call per base and threat sector (cached): the map image with the numbered candidates and their numbers ->
              5 spots + 3 spares in order, a facing each, reasons (.runtime/fortplan/arland/picks.json)
  algo        the code's own pick for comparison: best score, spread out, facing the threat
  export      .runtime/fortplan/arland/seed_<llm|algo>/zcr/fortplan.txt, read by -zcrFortPlan (AICF_ZcrFortPlan.c in the fork)

    python lab/fortplan.py harvest                       # where the game placed small compositions (all Arland runs)
    python lab/fortplan.py plan [--base Farm] [--no-model] [--redo] [--proven-only]
    python lab/fortplan.py export llm                    # or algo
    python lab/fortplan.py measure <run_dir>             # the fortifications of one run, measured
    python lab/fortplan.py compare                       # on the map: today's placements v the model's v the code's
"""
import argparse
import base64
import io
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

SLUG = "arland"
MAPS = ROOT / ".runtime" / "maps"
SCANS = ROOT / ".runtime" / "attack" / SLUG
OUT = ROOT / ".runtime" / "fortplan" / SLUG
FRONT_M = 2500          # AI Conflict builds fortifications at a base with an enemy base this close (AtFront)
SECTOR_DEG = 70         # threat directions grouped into sectors this wide
GRID_M = 10
CORE_M = 30             # candidates at least this far from the base point
ROAD_CLEAR_M = 6        # ... this far from a road's edge
OBJECT_CLEAR_M = 7      # ... no object 0.4 m+ tall this close
SLOPE_M = 2.0           # ... the ground within 10 m rises/falls at most this much
TREES_MAX = 4           # ... at most this many trees in its 25 m tree cell
EYE_M, TARGET_M = 1.5, 1.0
RAY_STEP_DEG, RAY_STEP_M, RAY_M = 5, 5, 320
ARC_DEG = 30            # a fortification's arc of fire: +- this
FOF_MIN_M, FOF_MAX_M = 20, 300
TREE_SCREEN = 0.025     # per tree in a 25 m cell, the share of the view one 5 m step through it blocks
SPOTS, SPARES = 5, 3    # AICF_ConstructionPlanner.FortificationsPerBase() = 5
MODEL_CANDIDATES = 24
SPREAD_M = 22


# ----------------------------------------------------------------------------------------------------------- map data
def bases() -> list:
    out = []
    for f in sorted(SCANS.glob("scan_*.jsonl")):
        h = json.loads(f.open(encoding="utf-8").readline())
        x, y, z = h["objective"]
        out.append({"name": h.get("name", "?"), "x": x, "z": z, "y": y, "scan": f})
    names = [b["name"] for b in out]
    for b in out:   # two "Main Operating Base"s: north and south
        if names.count(b["name"]) > 1:
            b["name"] += " (north)" if b["z"] > 2000 else " (south)"
        b["key"] = re.sub(r"[^a-z0-9]+", "_", b["name"].lower()).strip("_")
    return out


def bearing(ax, az, bx, bz) -> float:
    return math.degrees(math.atan2(bx - ax, bz - az)) % 360


def angle_between(a, b) -> float:
    return abs((a - b + 180) % 360 - 180)


def compass(angle) -> str:
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return names[int(((angle % 360) + 22.5) // 45) % 8]


def _roads():
    return [json.loads(l) for l in (MAPS / SLUG / "map_roads.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def road_gap(x, z, roads, near=60) -> float:
    """Metres from (x, z) to the nearest road's edge (negative: on it) - as lab/buildtest.py."""
    best = 1e9
    for r in roads:
        p, half = r["p"], r.get("w", 4) / 2
        for (ax, az), (bx, bz) in zip(p, p[1:]):
            if near and (min(ax, bx) - near > x or max(ax, bx) + near < x or min(az, bz) - near > z or max(az, bz) + near < z):
                continue
            dx, dz = bx - ax, bz - az
            L = dx * dx + dz * dz
            t = 0 if L == 0 else max(0, min(1, ((x - ax) * dx + (z - az) * dz) / L))
            best = min(best, math.hypot(x - (ax + t * dx), z - (az + t * dz)) - half)
    if best > 1e8 and near:
        return road_gap(x, z, roads, 0)
    return best


class Terrain:
    """One base's ground: heights / roofs from its 10 m scan, trees per 25 m cell, objects on a 2 m grid."""

    OBJ_CELL = 2.0

    def __init__(self, base: dict, objects=None, trees=None):
        self.base = base
        lines = base["scan"].read_text(encoding="utf-8").splitlines()
        head = json.loads(lines[0])
        self.step = head["step"]
        cells = [json.loads(l) for l in lines[1:]]
        xs = [c["x"] for c in cells]
        zs = [c["z"] for c in cells]
        self.x0, self.z0 = min(xs), min(zs)
        nx, nz = int(round((max(xs) - self.x0) / self.step)) + 1, int(round((max(zs) - self.z0) / self.step)) + 1
        self.h = np.full((nx, nz), np.nan)
        self.seen = np.zeros((nx, nz), dtype=np.int8)
        self.roof = np.zeros((nx, nz), dtype=np.int8)
        for c in cells:
            i, j = int(round((c["x"] - self.x0) / self.step)), int(round((c["z"] - self.z0) / self.step))
            self.h[i, j] = c["y"]
            self.seen[i, j] = c["seen"]
            self.roof[i, j] = c["roof"]
        # cells the scan has no height for: the sea (the scan skips water) - sea level, and no candidate there
        self.known = ~np.isnan(self.h)
        self.h = np.where(self.known, self.h, 0.0)
        trees = trees or json.loads((MAPS / SLUG / "map_trees.json").read_text(encoding="utf-8"))
        self.tree_cell = trees["cell"]
        self.trees = trees["trees"]
        # objects within 560 m of the base on a 2 m grid: the tallest per cell
        R = 560
        self.ox0, self.oz0 = base["x"] - R, base["z"] - R
        n = int(2 * R / self.OBJ_CELL) + 1
        self.obj = np.zeros((n, n), dtype=np.float32)
        for o in objects if objects is not None else load_objects():
            if abs(o["x"] - base["x"]) > R + 30 or abs(o["z"] - base["z"]) > R + 30:
                continue
            h = o.get("h", 0)
            if h < 0.4 or o["c"] in ("PowerlineEntity", "LakeGeneratorEntity", "GameEnvironmentProbeEntity", "SCR_CampaignSpawnPointGroup"):
                continue
            sx, sz = max(o.get("sx", 1), 0.5), max(o.get("sz", 1), 0.5)
            if sx * sz > 4000:   # odd huge bounds (terrain pieces, lakes)
                continue
            a = math.radians(o.get("yaw", 0))
            ca, sa = math.cos(a), math.sin(a)
            for lx in np.arange(-sx / 2, sx / 2 + 0.01, 1.0):
                for lz in np.arange(-sz / 2, sz / 2 + 0.01, 1.0):
                    wx = o["x"] + lx * ca + lz * sa
                    wz = o["z"] - lx * sa + lz * ca
                    i, j = int((wx - self.ox0) / self.OBJ_CELL), int((wz - self.oz0) / self.OBJ_CELL)
                    if 0 <= i < n and 0 <= j < n and h > self.obj[i, j]:
                        self.obj[i, j] = h

    def height(self, x, z) -> float:
        fx, fz = (x - self.x0) / self.step, (z - self.z0) / self.step
        i, j = int(math.floor(fx)), int(math.floor(fz))
        nx, nz = self.h.shape
        i, j = max(0, min(nx - 2, i)), max(0, min(nz - 2, j))
        tx, tz = min(1, max(0, fx - i)), min(1, max(0, fz - j))
        h = self.h
        return (h[i, j] * (1 - tx) * (1 - tz) + h[i + 1, j] * tx * (1 - tz) + h[i, j + 1] * (1 - tx) * tz + h[i + 1, j + 1] * tx * tz)

    def cell(self, x, z):
        i, j = int(round((x - self.x0) / self.step)), int(round((z - self.z0) / self.step))
        nx, nz = self.h.shape
        return (i, j) if 0 <= i < nx and 0 <= j < nz else None

    def tree_count(self, x, z) -> int:
        return self.trees.get(f"{int(x // self.tree_cell)},{int(z // self.tree_cell)}", 0)

    def object_h(self, x, z) -> float:
        i, j = int((x - self.ox0) / self.OBJ_CELL), int((z - self.oz0) / self.OBJ_CELL)
        n = self.obj.shape[0]
        return float(self.obj[i, j]) if 0 <= i < n and 0 <= j < n else 0.0

    def object_near(self, x, z, r) -> float:
        """The tallest object within r metres."""
        i0, j0 = int((x - r - self.ox0) / self.OBJ_CELL), int((z - r - self.oz0) / self.OBJ_CELL)
        i1, j1 = int((x + r - self.ox0) / self.OBJ_CELL) + 1, int((z + r - self.oz0) / self.OBJ_CELL) + 1
        n = self.obj.shape[0]
        sub = self.obj[max(0, i0):min(n, i1), max(0, j0):min(n, j1)]
        if sub.size == 0:
            return 0.0
        ii, jj = np.meshgrid(np.arange(max(0, i0), min(n, i1)), np.arange(max(0, j0), min(n, j1)), indexing="ij")
        cx, cz = self.ox0 + (ii + 0.5) * self.OBJ_CELL, self.oz0 + (jj + 0.5) * self.OBJ_CELL
        mask = (cx - x) ** 2 + (cz - z) ** 2 <= r * r
        return float(sub[mask].max()) if mask.any() else 0.0

    def slope(self, x, z) -> float:
        hs = [self.height(x + dx, z + dz) for dx in (-10, 0, 10) for dz in (-10, 0, 10)]
        return max(hs) - min(hs)

    COVER_CELL = 5
    _cover = None

    def covered(self, x, z) -> bool:
        """A roof or canopy overhead (the scan), a wood (6+ trees in the 25 m cell) or a building 2.5 m+ (5 m cells)."""
        if self._cover is None:
            n = self.obj.shape[0]
            k = int(self.COVER_CELL / self.OBJ_CELL)   # 2 m cells per 5 m cell (2; the last half-cell ignored)
            m = n // k
            tall = self.obj[:m * k, :m * k].reshape(m, k, m, k).max(axis=(1, 3)) >= 2.5
            cov = np.zeros((m, m), dtype=bool)
            for i in range(m):
                for j in range(m):
                    cx, cz = self.ox0 + (i + 0.5) * k * self.OBJ_CELL, self.oz0 + (j + 0.5) * k * self.OBJ_CELL
                    c = self.cell(cx, cz)
                    cov[i, j] = tall[i, j] or bool(c and self.roof[c]) or self.tree_count(cx, cz) >= 6
            self._cover, self._cover_k = cov, k * self.OBJ_CELL
        i, j = int((x - self.ox0) / self._cover_k), int((z - self.oz0) / self._cover_k)
        m = self._cover.shape[0]
        return bool(self._cover[i, j]) if 0 <= i < m and 0 <= j < m else False

    def viewshed(self, x, z) -> np.ndarray:
        """vis[ray, step]: the ground at distance (step+1)*RAY_STEP_M along bearing ray*RAY_STEP_DEG is in view from (x, z)."""
        rays, steps = 360 // RAY_STEP_DEG, RAY_M // RAY_STEP_M
        vis = np.zeros((rays, steps), dtype=bool)
        eye = self.height(x, z) + EYE_M
        for r in range(rays):
            a = math.radians(r * RAY_STEP_DEG)
            sa, ca = math.sin(a), math.cos(a)
            best = -1e9
            screen = 1.0
            for s in range(steps):
                d = (s + 1) * RAY_STEP_M
                px, pz = x + sa * d, z + ca * d
                g = self.height(px, pz)
                if screen >= 0.5 and (g + TARGET_M - eye) / d >= best:
                    vis[r, s] = True
                top = g + (self.object_h(px, pz) if d > 6 else 0)   # its own walls don't block it
                best = max(best, (top - eye) / d)
                if d > 6:
                    screen *= 1 - min(0.9, TREE_SCREEN * self.tree_count(px, pz))
                c = self.cell(px, pz)
                if c and self.roof[c] and d > 12:   # under a roof or a canopy: a screen too
                    screen *= 0.7
        return vis


_OBJECTS = None


def load_objects():
    global _OBJECTS
    if _OBJECTS is None:
        _OBJECTS = [json.loads(l) for l in (MAPS / SLUG / "map_objects.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return _OBJECTS


def fof(vis: np.ndarray, facing: float, arc=ARC_DEG, dmin=FOF_MIN_M, dmax=FOF_MAX_M) -> float:
    """Field of fire: the share of the ground dmin-dmax m out within +-arc of facing that is in view (area-weighted)."""
    rays, steps = vis.shape
    num = den = 0.0
    for r in range(rays):
        if angle_between(r * RAY_STEP_DEG, facing) > arc:
            continue
        for s in range(steps):
            d = (s + 1) * RAY_STEP_M
            if dmin <= d <= dmax:
                num += d * bool(vis[r, s])
                den += d
    return float(num / den) if den else 0.0


def in_view(vis: np.ndarray, x, z, px, pz) -> bool:
    d = math.hypot(px - x, pz - z)
    s = int(round(d / RAY_STEP_M)) - 1
    if s < 0:
        return True
    if s >= vis.shape[1]:
        return False
    r = int(round(bearing(x, z, px, pz) / RAY_STEP_DEG)) % vis.shape[0]
    return bool(vis[r, s])


def lane_view(vis, x, z, facing, lanes, arc=45, reach=FOF_MAX_M + 50):
    """Of the approach lanes' points within reach, the share in view inside the arc; None when no lane comes within reach."""
    pts = [(px, pz) for lane in lanes for px, pz in lane if FOF_MIN_M <= math.hypot(px - x, pz - z) <= reach]
    if not pts:
        return None
    ok = sum(1 for px, pz in pts if angle_between(bearing(x, z, px, pz), facing) <= arc and in_view(vis, x, z, px, pz))
    return ok / len(pts)


def cover_behind(t: Terrain, x, z, facing, reach=100) -> float:
    """Metres to the nearest roof, wood or building in the rear half (away from the facing), capped at reach."""
    best = reach
    back = (facing + 180) % 360
    for dx in range(-reach, reach + 1, 5):
        for dz in range(-reach, reach + 1, 5):
            d = math.hypot(dx, dz)
            if d < 8 or d >= best or angle_between(bearing(0, 0, dx, dz), back) > 90:
                continue
            if t.covered(x + dx, z + dz):
                best = d
    return best


# ----------------------------------------------------------------------------------------------------------- harvest
PLACED = re.compile(r"\[CONSTRUCTION_PLACED\] .*?type=(\w+) .*?prefab=(\S+) .*?position=<([-\d.]+),([-\d.]+),([-\d.]+)> yaw=([-\d.]+)")


def harvest() -> dict:
    """Where the game placed small (SlotFlatSmall) compositions in every Arland run: proven sites, and each base's reach."""
    bs = bases()
    sites = {b["key"]: [] for b in bs}
    runs = 0
    for log in (ROOT / ".runtime" / "runs").glob("*/logs/*/console.log"):
        try:
            with log.open(encoding="utf-8", errors="replace") as f:
                head = f.read(4000)
                if "Arland" not in head:
                    continue
                text = head + f.read()
        except OSError:
            continue
        found = False
        for m in PLACED.finditer(text):
            kind, prefab = m.group(1), m.group(2)
            if "SlotFlatSmall" not in prefab:
                continue
            x, z = float(m.group(3)), float(m.group(5))
            b = min(bs, key=lambda b: math.hypot(b["x"] - x, b["z"] - z))
            d = math.hypot(b["x"] - x, b["z"] - z)
            if d > 260:
                continue
            sites[b["key"]].append([round(x, 1), round(z, 1), kind.lower(), round(d), round(float(m.group(6)))])
            found = True
        runs += found
    out = {"runs": runs, "bases": {}}
    for b in bs:
        s = sites[b["key"]]
        uniq, placements = {}, {}
        for x, z, k, d, yaw in s:
            uniq.setdefault((round(x / 3), round(z / 3)), [x, z, k, d])
            placements.setdefault((round(x / 3), round(z / 3), k, yaw % 360), [x, z, k, d, yaw % 360])
        ds = sorted(v[3] for v in uniq.values())
        reach = ds[int(len(ds) * 0.97)] if len(ds) >= 10 else 120
        # sites: one per spot (candidates, reach); placements: each kind and yaw placed there (today's placement, 'compare')
        out["bases"][b["key"]] = {"name": b["name"], "x": b["x"], "z": b["z"], "placed": len(s), "sites": list(uniq.values()),
                                  "placements": list(placements.values()), "reach_m": reach}
        print(f"{b['name']:30} {len(s):5} placed, {len(uniq):4} distinct sites, reach {reach} m")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sites.json").write_text(json.dumps(out), encoding="utf-8")
    print(f"{runs} Arland runs -> {OUT / 'sites.json'}")
    return out


# ----------------------------------------------------------------------------------------------------------- threats
def threat_sectors(b: dict, bs: list) -> list:
    """The other bases within FRONT_M grouped by bearing into sectors up to SECTOR_DEG wide: [{from, to, threat: nearest}]."""
    nb = sorted(((bearing(b["x"], b["z"], o["x"], o["z"]), math.hypot(o["x"] - b["x"], o["z"] - b["z"]), o) for o in bs
                 if o is not b and math.hypot(o["x"] - b["x"], o["z"] - b["z"]) < FRONT_M), key=lambda t: t[0])
    if not nb:
        return []
    # start the sweep after the widest gap so no sector straddles it
    gaps = [((nb[(i + 1) % len(nb)][0] - nb[i][0]) % 360, i) for i in range(len(nb))]
    start = (max(gaps)[1] + 1) % len(nb)
    order = nb[start:] + nb[:start]
    sectors, cur = [], [order[0]]
    for t in order[1:]:
        if (t[0] - cur[0][0]) % 360 <= SECTOR_DEG:
            cur.append(t)
        else:
            sectors.append(cur)
            cur = [t]
    sectors.append(cur)
    out = []
    for s in sectors:
        near = min(s, key=lambda t: t[1])
        out.append({"from": round(s[0][0]), "to": round(s[-1][0]), "bearing": round(near[0]), "threat": near[2]["name"],
                    "tx": near[2]["x"], "tz": near[2]["z"], "threat_m": round(near[1]), "bases": [t[2]["name"] for t in s]})
    return out


def approach_lanes(b: dict, sector: dict) -> list:
    """The attack plans' lanes into this base from the sector's bases (lab/attackplan.py --all): the picked plan's 3 lanes,
    from the assembly point in - [[(x, z), ...], ...]."""
    f = SCANS / "plans.json"
    if not f.exists():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for o in d["objectives"]:
        if math.hypot(o["objective"]["x"] - b["x"], o["objective"]["z"] - b["z"]) > 50:
            continue
        for hq in o["hqs"]:
            br = bearing(b["x"], b["z"], hq["x"], hq["z"])
            width = (sector["to"] - sector["from"]) % 360
            if (br - sector["from"]) % 360 > width + 1 or math.hypot(hq["x"] - b["x"], hq["z"] - b["z"]) > FRONT_M:
                continue
            pick = hq.get("pick") or hq.get("algorithm_pick")
            pl = next((p for p in hq["plans"] if p["id"] == pick), hq["plans"][0])
            for lane in pl["lanes"]:
                pts = [tuple(p) for p in lane["waypoints"]]
                dense = []
                for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                    n = max(1, int(math.hypot(bx - ax, bz - az) // 20))
                    dense += [(ax + (bx - ax) * k / n, az + (bz - az) * k / n) for k in range(n)]
                dense.append(pts[-1])
                out.append(dense)
    return out


# ----------------------------------------------------------------------------------------------------------- candidates
def candidates(b: dict, t: Terrain, site_info: dict, roads, proven_only: bool = False) -> list:
    """proven_only: only where the game placed a small composition before - for a cramped base whose map-filtered spots fail
    the game's own checks (2 Nov, the Farm: 0 of its planned spots in two runs - AI Conflict's road clearance and base access
    corridors, single trees and fences the map dump lacks, worker paths through the fenced paddocks)."""
    reach = site_info.get("reach_m", 120)
    proven = site_info.get("sites", [])
    limit = reach - 6
    out = []
    n = -1 if proven_only else int(limit // GRID_M)   # -1: no grid
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, z = b["x"] + i * GRID_M, b["z"] + j * GRID_M
            d = math.hypot(x - b["x"], z - b["z"])
            if d < CORE_M or d > limit:
                continue
            c = t.cell(x, z)
            if not c or not t.known[c] or t.h[c] < 1 or t.roof[c]:
                continue
            if t.tree_count(x, z) > TREES_MAX or t.slope(x, z) > SLOPE_M:
                continue
            gap = road_gap(x, z, roads)
            if gap < ROAD_CLEAR_M:
                continue
            if t.object_near(x, z, OBJECT_CLEAR_M) >= 0.4:
                continue
            near_proven = min((math.hypot(p[0] - x, p[1] - z) for p in proven), default=1e9)
            out.append({"x": round(x, 1), "z": round(z, 1), "from_centre_m": round(d), "road_m": round(gap),
                        "proven": near_proven <= 6})
    # the proven sites themselves (where the grid missed them)
    for px, pz, kind, d, *_ in proven:
        if d < CORE_M or d > limit or any(math.hypot(c["x"] - px, c["z"] - pz) < 8 for c in out):
            continue
        gap = road_gap(px, pz, roads)
        if gap < ROAD_CLEAR_M - 2 and not proven_only:
            continue
        out.append({"x": px, "z": pz, "from_centre_m": round(d), "road_m": round(gap), "proven": True})
    return out


def score_candidates(b, t: Terrain, cands: list, sector: dict, lanes: list):
    tb = sector["bearing"]
    for c in cands:
        if "vis" not in c:
            c["vis"] = t.viewshed(c["x"], c["z"])
        vis = c["vis"]
        tbear = bearing(c["x"], c["z"], sector["tx"], sector["tz"])
        c["threat_bearing"] = round(tbear)
        c["fof_threat"] = round(fof(vis, tbear), 3)
        best = max(range(0, 360, 10), key=lambda a: fof(vis, a))
        c["open_dir"], c["fof_open"] = best, round(fof(vis, best), 3)
        lv = lane_view(vis, c["x"], c["z"], tbear, lanes)
        c["lanes_seen"] = None if lv is None else round(lv, 2)
        c["cover_behind_m"] = round(cover_behind(t, c["x"], c["z"], tbear))
        fwd = ((c["x"] - b["x"]) * math.sin(math.radians(tb)) + (c["z"] - b["z"]) * math.cos(math.radians(tb)))
        c["toward_threat_m"] = round(fwd)
        c["score"] = round(2 * c["fof_threat"] + 0.8 * (c["lanes_seen"] or 0) + (0.3 if c["cover_behind_m"] <= 40 else 0)
                           + 0.4 * max(-1, min(1, fwd / 100)) + (0.3 if c["proven"] else 0), 3)


def spread(cands: list, k: int, gap=SPREAD_M) -> list:
    out = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if all(math.hypot(c["x"] - o["x"], c["z"] - o["z"]) >= gap for o in out):
            out.append(c)
        if len(out) >= k:
            break
    return out


# ----------------------------------------------------------------------------------------------------------- image
def draw(b: dict, t: Terrain, cands: list, sector: dict, lanes: list, reach: float, picks=None) -> Image.Image:
    import mapimage
    full, mpp, world = mapimage.base_map(SLUG, "topo", 4)
    half = reach + 330
    x0, x1, z0, z1 = b["x"] - half, b["x"] + half, b["z"] - half, b["z"] + half
    crop = full.crop((int(x0 / mpp), int((world - z1) / mpp), int(x1 / mpp), int((world - z0) / mpp))).convert("RGBA")
    S = 1400 / crop.size[0]
    crop = crop.resize((1400, int(crop.size[1] * S)), Image.LANCZOS)
    px = lambda x, z: ((x - x0) / mpp * S, (z1 - z) / mpp * S)
    over = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    f_small, f_mid, f_big = mapimage.font(17), mapimage.font(20, True), mapimage.font(26, True)
    # ground the base sees (its 9 eye points, the scan) - light red: what is not shaded is dead ground to the base
    hs = t.step / 2 / mpp * S
    nx, nz = t.seen.shape
    for i in range(nx):
        for j in range(nz):
            if t.seen[i, j] > 0:
                x, z = t.x0 + i * t.step, t.z0 + j * t.step
                if x0 <= x <= x1 and z0 <= z <= z1:
                    cx, cy = px(x, z)
                    d.rectangle([cx - hs, cy - hs, cx + hs, cy + hs], fill=(220, 30, 30, 18 + 9 * int(t.seen[i, j])))
    # the building radius
    cx, cy = px(b["x"], b["z"])
    r = reach / mpp * S
    for a in range(0, 360, 6):
        a0, a1 = math.radians(a), math.radians(a + 3)
        d.line([(cx + r * math.sin(a0), cy - r * math.cos(a0)), (cx + r * math.sin(a1), cy - r * math.cos(a1))], fill=(20, 20, 20, 220), width=3)
    # approach lanes
    for lane in lanes:
        pts = [px(x, z) for x, z in lane if x0 <= x <= x1 and z0 <= z <= z1]
        if len(pts) >= 2:
            d.line(pts, fill=(200, 0, 0, 230), width=5)
            (ax, ay), (bx2, by2) = pts[-2], pts[-1]
            ang = math.atan2(by2 - ay, bx2 - ax)
            d.polygon([(bx2, by2), (bx2 - 18 * math.cos(ang - 0.4), by2 - 18 * math.sin(ang - 0.4)),
                       (bx2 - 18 * math.cos(ang + 0.4), by2 - 18 * math.sin(ang + 0.4))], fill=(200, 0, 0, 230))
    # the threat arrow, at the image edge toward the threat
    a = math.radians(sector["bearing"])
    ex, ey = cx + (half - 60) / mpp * S * math.sin(a), cy - (half - 60) / mpp * S * math.cos(a)
    sx, sy = cx + (reach + 30) / mpp * S * math.sin(a), cy - (reach + 30) / mpp * S * math.cos(a)
    d.line([(ex, ey), (sx, sy)], fill=(160, 0, 0, 255), width=9)
    d.polygon([(sx, sy), (sx + 26 * math.sin(a - 0.5), sy - 26 * math.cos(a - 0.5)), (sx + 26 * math.sin(a + 0.5), sy - 26 * math.cos(a + 0.5))], fill=(160, 0, 0, 255))
    label = f"ENEMY: {sector['threat']} {sector['threat_m'] / 1000:.1f} km ({sector['bearing']} deg)"
    lx, ly = min(max(ex - 150, 5), crop.size[0] - 420), min(max(ey - 34, 5), crop.size[1] - 34)
    d.rectangle([lx - 4, ly - 2, lx + 10 * len(label) + 20, ly + 30], fill=(255, 255, 255, 220))
    d.text((lx, ly), label, fill=(160, 0, 0, 255), font=f_mid)
    # the base point
    d.rectangle([cx - 9, cy - 9, cx + 9, cy + 9], fill=(0, 0, 0, 255))
    d.text((cx + 12, cy - 12), b["name"], fill=(0, 0, 0, 255), font=f_mid)
    # candidates
    chosen = {p["n"]: p for p in (picks or [])}
    for n, c in enumerate(cands, 1):
        x, y = px(c["x"], c["z"])
        f = c["fof_threat"]
        col = (30, 160, 60) if f >= 0.3 else (230, 180, 20) if f >= 0.15 else (150, 150, 150)
        rad = 15
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=col + (235,), outline=(0, 0, 0, 255), width=4 if c["proven"] else 2)
        txt = str(n)
        d.text((x - 6 * len(txt), y - 11), txt, fill=(0, 0, 0, 255), font=f_mid)
        if n in chosen:
            fa = math.radians(chosen[n]["facing"])
            for da in (-ARC_DEG, ARC_DEG):
                aa = fa + math.radians(da)
                d.line([(x, y), (x + 90 * math.sin(aa), y - 90 * math.cos(aa))], fill=(0, 70, 200, 230), width=3)
            d.line([(x, y), (x + 110 * math.sin(fa), y - 110 * math.cos(fa))], fill=(0, 70, 200, 255), width=5)
    # legend + scale
    leg = ["numbered circles: spots the builders can use (green: 30%+ of the ground toward the enemy in view,",
           "  yellow: 15-30%, grey: less; thick ring: the game built here before)",
           "black dashed circle: the base's building limit; black square: the base",
           "red shading: ground the base itself sees (unshaded = dead ground to it)",
           "red lines: likely enemy approach lanes into the base; big red arrow: the enemy",
           "map: 1 px = %.1f m; north is up" % (mpp / S)]
    d.rectangle([5, crop.size[1] - 24 * len(leg) - 14, 760, crop.size[1] - 5], fill=(255, 255, 255, 225))
    for k, l in enumerate(leg):
        d.text((12, crop.size[1] - 24 * (len(leg) - k) - 8), l, fill=(0, 0, 0, 255), font=f_small)
    bar = 100 / mpp * S
    d.rectangle([crop.size[0] - bar - 30, 20, crop.size[0] - 30, 30], fill=(0, 0, 0, 255))
    d.text((crop.size[0] - bar - 30, 34), "100 m", fill=(0, 0, 0, 255), font=f_small)
    return Image.alpha_composite(crop, over).convert("RGB")


# ----------------------------------------------------------------------------------------------------------- the model
SYSTEM = ("You are the engineer officer of one side in an Arma Reforger match (a military game). Your builders will put up "
          "5 small fortifications at the base on the map - mostly roofed bunkers and guard towers, one machine-gun nest, one "
          "sandbag position - each with a firing arc about 60 degrees wide to its front. An algorithm has found the spots "
          "the builders can build on (numbered on the map, with their numbers below); you choose 5 of them, most important "
          "first, plus 3 spares in case one turns out blocked, and the compass direction each faces (0 north, 90 east). "
          "Judge as a soldier would: the fortifications must cover the ways the enemy will come from (the red arrow and "
          "the red approach lanes, roads into the base, dead ground the base itself cannot see), each with a wide view "
          "over open ground in front, ideally with cover (trees, buildings) behind; together they should cover the threat "
          "side with overlapping arcs and not all stand in one spot; do not face them into a wood or a hill right in front. "
          'Answer with JSON only: {"spots": [{"n": 4, "facing": 120, "why": "..."}, ... 8 entries, the first 5 the ones '
          'to build], "summary": "the idea of the defence in two sentences"}.')


def describe(b, cands, sector, lanes) -> str:
    rows = []
    for n, c in enumerate(cands, 1):
        lane = "no approach lane within 350 m" if c["lanes_seen"] is None else f"sees {round(100 * c['lanes_seen'])}% of the approach lanes' ground within 350 m"
        rows.append(f"{n}: {c['from_centre_m']} m from the base point to the {compass(bearing(b['x'], b['z'], c['x'], c['z']))}, "
                    f"{c['toward_threat_m']:+} m toward the enemy; facing the enemy ({c['threat_bearing']} deg) it sees "
                    f"{round(100 * c['fof_threat'])}% of the ground 20-300 m out in its arc; its widest view faces {c['open_dir']} deg "
                    f"({round(100 * c['fof_open'])}%); {lane}; cover behind {'within ' + str(c['cover_behind_m']) + ' m' if c['cover_behind_m'] < 100 else 'none within 100 m'}; "
                    f"{c['road_m']} m from a road{'; the game has built here before' if c['proven'] else ''}.")
    others = ", ".join(x for x in sector["bases"] if x != sector["threat"])
    return (f"The base: {b['name']}. The enemy is expected from the {compass(sector['bearing'])} ({sector['from']}-{sector['to']} deg): "
            f"the nearest enemy base that way is {sector['threat']}, {sector['threat_m']} m away"
            + (f" (also that way: {others})" if others else "") + ". "
            + (f"The red lines are the {len(lanes)} likely approach lanes of an attack from there (they keep to cover and dead ground)."
               if lanes else "No approach lanes are known.") + "\n\nThe spots:\n" + "\n".join(rows))


def ask_model(llm, image: Image.Image, text: str) -> dict:
    import providers
    img = image.copy()
    img.thumbnail((1400, 1400))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    t0 = time.time()
    r = providers._post("https://openrouter.ai/api/v1/chat/completions",
                        {"model": llm.model, "temperature": 0.3, "max_tokens": 4000, "response_format": {"type": "json_object"},
                         "messages": [{"role": "system", "content": SYSTEM},
                                      {"role": "user", "content": [{"type": "text", "text": text},
                                                                   {"type": "image_url", "image_url": {"url": url}}]}]},
                        {"authorization": f"Bearer {llm.key}", "x-title": "Zeus Commander Reforger"}, 150)
    if "error" in r:
        raise RuntimeError(f"openrouter: {r['error']}")
    out = providers.extract_json(r["choices"][0]["message"].get("content") or "")
    out["seconds"] = round(time.time() - t0, 1)
    out["usage"] = r.get("usage")
    return out


def validate(answer: dict, cands: list, sector: dict) -> tuple:
    """The model's spots checked: a listed number, once; a facing within 90 deg of the threat (else turned to 90 deg off it).
    Returns (spots [{n, facing, why}], notes)."""
    out, notes, seen = [], [], set()
    for s in answer.get("spots") or []:
        try:
            n, facing = int(s.get("n")), float(s.get("facing"))
        except (TypeError, ValueError):
            notes.append(f"unreadable {s}")
            continue
        if not 1 <= n <= len(cands) or n in seen:
            notes.append(f"spot {n} not a listed one or twice")
            continue
        seen.add(n)
        c = cands[n - 1]
        tb = bearing(c["x"], c["z"], sector["tx"], sector["tz"])
        if angle_between(facing, tb) > 90:
            sign = 1 if (facing - tb) % 360 < 180 else -1
            notes.append(f"spot {n}: facing {facing:.0f} more than 90 deg off the enemy ({tb:.0f}) - turned to {(tb + 90 * sign) % 360:.0f}")
            facing = (tb + 90 * sign) % 360
        out.append({"n": n, "facing": round(facing % 360), "why": str(s.get("why", ""))[:300]})
        if len(out) >= SPOTS + SPARES:
            break
    return out, notes


def algo_pick(cands: list) -> list:
    """The code's own pick: the best scores spread SPREAD_M+ apart, each facing the threat."""
    picked = spread(cands, SPOTS + SPARES, 25)
    return [{"n": cands.index(c) + 1, "x": c["x"], "z": c["z"], "facing": c["threat_bearing"], "why": f"score {c['score']}"} for c in picked]


def plan(only: str = "", use_model: bool = True, redo: bool = False, proven_only: bool = False) -> dict:
    bs = bases()
    sites = json.loads((OUT / "sites.json").read_text(encoding="utf-8"))["bases"] if (OUT / "sites.json").exists() else {}
    roads = _roads()
    objects = load_objects()
    trees = json.loads((MAPS / SLUG / "map_trees.json").read_text(encoding="utf-8"))
    pf = OUT / "plans.json"
    plans = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {"map": SLUG, "bases": {}}
    llm = None
    if use_model:
        import providers
        llm = providers.OpenRouter(json.loads((HERE / "bridge.local.json").read_text(encoding="utf-8")))
        plans["model"] = llm.model
    calls = 0
    for b in bs:
        if only and only.lower() not in b["name"].lower():
            continue
        t0 = time.time()
        t = Terrain(b, objects, trees)
        info = sites.get(b["key"], {})
        entry = plans["bases"].setdefault(b["key"], {"name": b["name"], "x": b["x"], "z": b["z"], "sectors": []})
        if proven_only:   # kept for the base's later re-plans
            entry["proven_only"] = True
        cands = candidates(b, t, info, roads, entry.get("proven_only", False))
        entry["reach_m"] = info.get("reach_m", 120)
        entry["candidates_all"] = len(cands)
        old = {(s["from"], s["to"]): s for s in entry.get("sectors", [])}
        sectors = []
        for sec in threat_sectors(b, bs):
            lanes = approach_lanes(b, sec)
            score_candidates(b, t, cands, sec, lanes)
            shown = spread(cands, MODEL_CANDIDATES)
            sid = f"{b['key']}_{sec['bearing']}"
            img = draw(b, t, shown, sec, lanes, entry["reach_m"])
            img.save(OUT / f"{sid}.png")
            text = describe(b, shown, sec, lanes)
            prev = old.get((sec["from"], sec["to"]))
            rec = {**sec, "id": sid, "lanes": len(lanes), "candidates": [{k: v for k, v in c.items() if k != "vis"} for c in shown],
                   "algo": algo_pick(shown), "asked": text}
            def valid(p_):   # a cached pick still among this run's candidates (anywhere, not only the shown ones)
                at = prev["candidates"][p_["n"] - 1]
                return any(math.hypot(c["x"] - at["x"], c["z"] - at["z"]) < 1 for c in cands)
            if not shown:   # no spot to choose from (Signal Hill: the game never built there - no building radius)
                rec["llm"], rec["notes"] = [], ["no candidates"]
            elif prev and prev.get("model") and not prev["model"].get("error") and not redo and prev.get("llm") and                     all(valid(p_) for p_ in prev["llm"][:SPOTS]):
                # the cached answer stands while its 5 spots are still valid candidates (the numbers it saw stay with it)
                rec.update({k: prev[k] for k in ("model", "llm", "notes", "candidates", "asked") if k in prev})
                rec["cached"] = True
            elif llm:
                try:
                    ans = ask_model(llm, img, text)
                    calls += 1
                    rec["model"] = ans
                    rec["llm"], rec["notes"] = validate(ans, shown, sec)
                except Exception as e:   # the algorithm's / today's placement stands
                    rec["model"] = {"error": f"{type(e).__name__}: {e}"}
                    rec["llm"], rec["notes"] = [], []
            for p_ in rec.get("llm", []):
                c = rec["candidates"][p_["n"] - 1]
                p_["x"], p_["z"] = c["x"], c["z"]
            if rec.get("llm") and not rec.get("cached"):
                draw(b, t, shown, sec, lanes, entry["reach_m"], rec["llm"][:SPOTS]).save(OUT / f"{sid}_llm.png")
            sectors.append(rec)
            m = rec.get("model") or {}
            print(f"  {b['name']:28} enemy from {sec['bearing']:3} ({sec['from']}-{sec['to']}, {sec['threat']}): {len(shown)} shown, "
                  f"model {[s['n'] for s in rec.get('llm', [])]} {('- ' + m.get('error')) if m.get('error') else ''}", flush=True)
        entry["sectors"] = sectors
        print(f"{b['name']}: {len(cands)} candidates, {len(sectors)} sectors, {time.time() - t0:.0f} s", flush=True)
        pf.write_text(json.dumps(plans, indent=1), encoding="utf-8")
    print(f"model calls: {calls}; {pf}")
    return plans


def export(which: str) -> Path:
    """The plans in the game's format (AICF_ZcrFortPlan.c): which = llm (the model's spots; a sector without them: none) or
    algo (the code's best scores, facing the threat)."""
    plans = json.loads((OUT / "plans.json").read_text(encoding="utf-8"))
    lines = [f"world {SLUG}"]
    n = 0
    for key, e in plans["bases"].items():
        for s in e["sectors"]:
            spots = s.get("llm") if which == "llm" else s.get("algo")
            if not spots:
                continue
            lines.append(f"base {e['x']:.1f} {e['z']:.1f} {s['tx']:.1f} {s['tz']:.1f} {s['from']} {s['to']} {which} {s['id']}")
            for p in spots:
                lines.append(f"spot {p['x']} {p['z']} {p['facing']}")
            n += 1
    seed = OUT / f"seed_{which}"
    (seed / "zcr").mkdir(parents=True, exist_ok=True)
    (seed / "zcr" / "fortplan.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {seed / 'zcr' / 'fortplan.txt'} ({n} base plans)")
    return seed


# ----------------------------------------------------------------------------------------------------------- measure
FORT = re.compile(r"\[ZCR\]\[FORTPLAN\] event=placed (.*)")
KV = re.compile(r"(\w+)=(\S+)")


def measure_text(text: str, done_tokens=None) -> list:
    """Every fortification a run placed ([ZCR][FORTPLAN] event=placed), measured on the map: facing error to the threat base,
    field of fire in its facing and toward the threat, approach lanes in view, cover behind, road gap, from the base point."""
    bs = bases()
    roads = _roads()
    objects = trees = None
    terrains = {}
    out = []
    for m in FORT.finditer(text):
        f = dict(KV.findall(m.group(1)))
        x, z, facing = float(f["x"]), float(f["z"]), float(f["dir"])
        b = min(bs, key=lambda b: math.hypot(b["x"] - x, b["z"] - z))
        if b["key"] not in terrains:
            if objects is None:
                objects = load_objects()
                trees = json.loads((MAPS / SLUG / "map_trees.json").read_text(encoding="utf-8"))
            terrains[b["key"]] = Terrain(b, objects, trees)
        t = terrains[b["key"]]
        vis = t.viewshed(x, z)
        tx, tz = (float(v) for v in f.get("threat", "0,0").split(","))
        row = {"token": f.get("token"), "side": f.get("side"), "base": b["name"], "kind": f.get("kind"), "source": f.get("source"),
               "x": x, "z": z, "dir": facing, "spot": int(f.get("spot", -1)),
               "built": None if done_tokens is None else f.get("token") in done_tokens,
               "road_m": round(road_gap(x, z, roads)), "from_centre_m": round(math.hypot(x - b["x"], z - b["z"])),
               "fof_facing": round(fof(vis, facing), 3), "cover_behind_m": round(cover_behind(t, x, z, facing))}
        if tx or tz:
            tb = bearing(x, z, tx, tz)
            sec = {"from": round(bearing(b["x"], b["z"], tx, tz)) - 1, "to": round(bearing(b["x"], b["z"], tx, tz)) + 1}
            lanes = approach_lanes(b, sec)
            lv = lane_view(vis, x, z, facing, lanes)
            row.update({"face_err": round(angle_between(facing, tb)), "fof_threat": round(fof(vis, tb), 3),
                        "lanes_seen": None if lv is None else round(lv, 2)})
        out.append(row)
    return out


def summary(rows: list) -> dict:
    def med(v):
        v = sorted(x for x in v if x is not None)
        return v[len(v) // 2] if v else None
    def mean(v):
        v = [x for x in v if x is not None]
        return round(sum(v) / len(v), 2) if v else None
    built = [r["built"] for r in rows if r["built"] is not None]
    return {"forts": len(rows), "forts_plan": sum(1 for r in rows if r["source"] != "rules"),
            "face_err_med": med([r.get("face_err") for r in rows]), "face_err_mean": mean([r.get("face_err") for r in rows]),
            "facing_ok": sum(1 for r in rows if r.get("face_err") is not None and r["face_err"] <= ARC_DEG),
            "fof_facing": mean([r["fof_facing"] for r in rows]), "fof_threat": mean([r.get("fof_threat") for r in rows]),
            "lanes_seen": mean([r.get("lanes_seen") for r in rows]),
            "cover40": sum(1 for r in rows if r["cover_behind_m"] <= 40), "fort_road_m": med([r["road_m"] for r in rows]),
            "fort_centre_m": med([r["from_centre_m"] for r in rows]),
            "fort_built_pct": round(100 * sum(built) / len(built)) if built else None}


def compare() -> dict:
    """On the map, per base and threat sector: today's fortifications (every one the game placed at that base in the lab's
    Arland runs, at its yaw) against the model's 5 spots and the code's 5 (algo), with their facings - the same measures as
    'measure'. Written to compare.json; prints the overall means."""
    plans = json.loads((OUT / "plans.json").read_text(encoding="utf-8"))
    sites = json.loads((OUT / "sites.json").read_text(encoding="utf-8"))["bases"]
    bs = {b["key"]: b for b in bases()}
    roads = _roads()
    objects = load_objects()
    trees = json.loads((MAPS / SLUG / "map_trees.json").read_text(encoding="utf-8"))
    rows = []
    for key, e in plans["bases"].items():
        secs = [s for s in e["sectors"] if s.get("llm")]
        if not secs:
            continue
        b = bs[key]
        t = Terrain(b, objects, trees)
        vcache = {}
        today = [(p[0], p[1], p[4]) for p in sites.get(key, {}).get("placements", []) if p[2] == "fortification"]
        for s in secs:
            lanes = approach_lanes(b, s)
            pick = lambda which: [(p["x"], p["z"], p["facing"]) for p in s[which][:SPOTS]]
            for src, spots in (("rules", today), ("llm", pick("llm")), ("algo", pick("algo"))):
                for x, z, facing in spots:
                    if (x, z) not in vcache:
                        vcache[(x, z)] = t.viewshed(x, z)
                    vis = vcache[(x, z)]
                    tb = bearing(x, z, s["tx"], s["tz"])
                    lv = lane_view(vis, x, z, facing, lanes)
                    rows.append({"base": b["name"], "sector": s["id"], "source": src, "x": x, "z": z, "dir": facing,
                                 "face_err": round(angle_between(facing, tb)), "fof_facing": round(fof(vis, facing), 3),
                                 "fof_threat": round(fof(vis, tb), 3), "lanes_seen": None if lv is None else round(lv, 2),
                                 "cover_behind_m": round(cover_behind(t, x, z, facing)), "road_m": round(road_gap(x, z, roads)),
                                 "from_centre_m": round(math.hypot(x - b["x"], z - b["z"])), "built": None})
        print(f"{b['name']}: {len(secs)} sectors, {len(today)} of today's fortification placements", flush=True)
    out = {"rows": rows, "overall": {}}
    for src in ("rules", "algo", "llm"):
        r = [x for x in rows if x["source"] == src]
        o = summary(r)
        o["facing_ok_pct"] = round(100 * o["facing_ok"] / max(1, len(r)))
        o["cover40_pct"] = round(100 * o["cover40"] / max(1, len(r)))
        out["overall"][src] = o
        print(src, o)
    (OUT / "compare.json").write_text(json.dumps(out), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("harvest")
    p = sub.add_parser("plan")
    p.add_argument("--base", default="")
    p.add_argument("--no-model", action="store_true")
    p.add_argument("--redo", action="store_true", help="ask the model again even where a cached answer fits")
    p.add_argument("--proven-only", action="store_true", help="candidates only where the game built before (kept for the base)")
    e = sub.add_parser("export")
    e.add_argument("which", choices=["llm", "algo"])
    m = sub.add_parser("measure")
    m.add_argument("run")
    sub.add_parser("compare")
    a = ap.parse_args()
    if a.cmd == "harvest":
        harvest()
    elif a.cmd == "plan":
        plan(a.base, not a.no_model, a.redo, a.proven_only)
    elif a.cmd == "export":
        export(a.which)
    elif a.cmd == "compare":
        compare()
    elif a.cmd == "measure":
        log = next(iter(sorted(Path(a.run).glob("logs/*/console.log"))))
        rows = measure_text(log.read_text(encoding="utf-8", errors="replace"))
        for r in rows:
            print(r)
        print(summary(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
