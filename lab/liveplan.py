"""Live attack plans for one side of the Farm battle, rewritten while it runs (2 Nov night, review note 515 - Martin: "why
gemini is not used for planning attacks?", "attack routes are not properly used - infantry is not choosing the best
possible route going through real cover", "attack routes should be planned based on the context (positions of soldiers,
cover)", "points where soldiers are dropped should be planned by LLM", "enemies should definitely not be ignored", "only
one side can use it, the other one will not, and we will compare").

The split agreed from the research (models draw poor routes on grids; code proposes, the model chooses; a slow model
must not drive): every ROUND_S game seconds the code redraws, for the side it plans for, from what THAT side knows -

  threat      the enemies its soldiers saw in the last minute ([ZCR][KNOWN], 10 m): from each, sight lines over the
              10 m ground scan (.runtime/attack/farm_scan.jsonl), blocked by buildings and by ~30 m of wood
              (.runtime/maps/arland/map_trees.json); nearer counts more. When the enemy holds Farm, the ground its 9
              eye points see is added (the scan's 'seen')
  cover       a roof or canopy, or dense trees (6+ per 25 m); every cell's distance to the nearest
  drop points D1..  road points 300-800 m from Farm on the side's half, hidden from the known enemies and from Farm's
              eyes, scored by the drive from the HQ (roads in the enemies' sight dear) and the covered walk in
  routes      per start (a drop point, or a group of the side's teams on foot) the cheapest way in over the threat and
              cover costs (C) and the best one forced through a gate left (L) or right (R) of it; each with its hold point
              (~180 m out, the best covered spot) and its numbers
  support P1, P2  spots 150-450 m out that see Farm, in cover, not seen by the known enemies

and the picker gives every attack team of the side: a drop point (teams not out of their vehicle yet - frozen once it
rides), a route (L/C/R from its start), and go / wait (to the hold point, then wait up to 3 min) / support (to P1/P2,
fire from there up to 8 min, then in). Pickers: 'code' (the cheapest, teams spread over the best two) or 'gemini' (the
model of lab/bridge.local.json, every GEMINI_S game seconds or on an event - Farm changing hands, losses - with the map
image and a short text; its answer checked team by team, anything invalid falls back to the code's pick). Between the
model's calls the code keeps redrawing the routes it chose with the latest threat. The game (-zcrLivePlan,
AICF_ZcrAttackPlan.LoadLive) reads $profile:zcr/liveplan.txt when its version changes: rides to the drop point (ZCR_Dismount),
the teams' legs along the routes (AICF_InfantryApproachRoute.LiveCandidate). Every round is logged to
$profile:zcr/liveplan.jsonl (the model's reasons too) and every model call's image to $profile:zcr/liveplan/.

    python lab/liveplan.py --label assault-city-farm-gemini-p2178 --side harbour --picker gemini   # beside the battle
    python lab/liveplan.py --replay .runtime/runs/<run> --t 420 --side USSR --picker code --known-from-live   # offline
"""
import argparse
import base64
import io
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import roadgraph  # noqa: E402

ATTACK = ROOT / ".runtime" / "attack"
MAPS = ROOT / ".runtime" / "maps"
OBJECTIVE = "Farm"      # the battle's objective: --objective (4 Nov: Beauregard, the battle of the city)

ROUND_S = 30            # the code redraws every this many game seconds
GEMINI_S = 150          # the model every this many game seconds ...
GEMINI_MIN_S = 110      # ... or on an event, but never sooner than this after the last call
GOAL_M = 50             # a route ends this close to the objective's centre
VIEW_M = 500            # a known enemy's sight counts this far
EYE_M, TARGET_M = 1.7, 1.4
BUILDING_M = 6          # a roof without trees around: a building this high
WOOD_BLOCK_M = 30       # this much dense wood on a sight line hides
THREAT_COST = 3.0       # walking a cell one close known enemy sees costs 4x a hidden one
# Danger zones (note 541): where the side lost men or vehicles lately - each loss counts 1 (a man) or 3 (a vehicle),
# fading to 0 over DANGER_S; grouped within DANGER_GROUP_M; a route or drive near one (DANGER_R_M) costs more.
DANGER_S = 600
DANGER_GROUP_M = 80
DANGER_R_M = 70
DANGER_COST = 2.0       # per unit of faded weight, on top of the cell cost
# A risk, not a wall (5 Nov - Martin, watching: "general keeps them away but should it really be like that? maybe it should be
# just danger risk, sometimes they probably have to go through killzone anyway"): the weight per cell is capped at DANGER_CAP
# (20 losses at the town's edge had made it 40x dearer - every way in a wall), and none counts within DANGER_FREE_M of the
# objective - the fight is there, the teams must go in.
DANGER_CAP = 1.5
DANGER_FREE_M = 150
THREAT_CAP = 3.0
NO_COVER_COST = 0.6     # ... more with no roof, canopy or dense trees within COVER_REACH_M (drones)
COVER_REACH_M = 40
STATIC_COST = 2.0       # the cells Farm's eye points see, when the enemy holds it ...
STATIC_COST_OPEN = 0.5  # ... and when it's neutral (it will be watched soon)
DROP_MIN, DROP_MAX = 300, 800
DROP_N = 4
SIDE_MAX_DEG, SIDE_FREE_DEG = 90, 30
DRIVE_THREAT_COST = 4.0
NEAR_OBJ_DRIVE_M = 280  # roads this close to the objective are dear to drive (the enemy holds it or will)
WALK_MPS, DRIVE_MPS = 1.5, 8.0
HOLD_M = 180
WAYPOINT_M = 50
WAIT_S, SUPPORT_S = 180, 480
# Waits that never end (4 Nov night - in the town battles Gemini renewed a team's 'wait' for 8-12 minutes: US T0 stood 4+
# minutes 75 m short of its waypoint): a team kept waiting WAIT_MAX_S in a row goes on, for RELEASED_S before a wait holds
# it again; the prompt says so.
WAIT_MAX_S, RELEASED_S = 240, 300
RAID_S = 150            # a raid team fights at the enemy drone site up to this long, then goes on to the objective
SITE_SEEN_M = 100       # an enemy drone site is located once one of the side's known enemies stood this close to it
STANCES = ("assault", "fortify", "counter_drone")
# What a team does at each point of its route (note 540 - Martin: "those waypoints dont have type like move, defense, hold,
# clear building, enter building ... cover?"): stop briefly in cover at a tree line, go into the buildings, or move on.
POINT_ACTION = {"edge of trees": "c", "edge of buildings": "e", "in buildings": "e"}
GROUP_M = 80            # teams on foot this close share their routes
AT_OBJ_M = 150          # a team this close to the objective fights there - no live entry
HQ_M = 350              # a team this close to its HQ, not riding, waits for a ride (gets a drop point)

DIRS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]


def _sl(n, d):
    """Slices of the cells whose neighbour at offset d exists (a) and of those neighbours (b)."""
    if d > 0:
        return slice(0, n - d), slice(d, n)
    if d < 0:
        return slice(-d, n), slice(0, n + d)
    return slice(0, n), slice(0, n)


class Grid:
    """The 10 m ground scan around the objective as arrays [i (x), j (z)]."""

    def __init__(self, scan: Path, slug: str = "arland"):
        lines = scan.read_text(encoding="utf-8").splitlines()
        head = json.loads(lines[0])
        self.ox, self.oy, self.oz = head["objective"]
        self.step = float(head["step"])
        cells = [json.loads(l) for l in lines[1:]]
        xs = np.array([c["x"] for c in cells], float)
        zs = np.array([c["z"] for c in cells], float)
        self.x0, self.z0 = xs.min(), zs.min()
        self.nx = int(round((xs.max() - self.x0) / self.step)) + 1
        self.nz = int(round((zs.max() - self.z0) / self.step)) + 1
        shape = (self.nx, self.nz)
        self.H = np.zeros(shape, np.float32)
        self.seen = np.zeros(shape, np.float32)
        self.roof = np.zeros(shape, bool)
        self.valid = np.zeros(shape, bool)
        ii = np.round((xs - self.x0) / self.step).astype(int)
        jj = np.round((zs - self.z0) / self.step).astype(int)
        self.H[ii, jj] = [c["y"] for c in cells]
        self.seen[ii, jj] = [c["seen"] for c in cells]
        self.roof[ii, jj] = [bool(c["roof"]) for c in cells]
        self.valid[ii, jj] = True
        self.X = (self.x0 + np.arange(self.nx) * self.step)[:, None] * np.ones((1, self.nz))
        self.Z = (self.z0 + np.arange(self.nz) * self.step)[None, :] * np.ones((self.nx, 1))
        trees = json.loads((MAPS / slug / "map_trees.json").read_text(encoding="utf-8"))
        tc, tt = trees["cell"], trees["trees"]
        self.trees = np.zeros(shape, np.float32)
        kx = (self.X // tc).astype(int)
        kz = (self.Z // tc).astype(int)
        for i in range(self.nx):
            for j in range(self.nz):
                if self.valid[i, j]:
                    self.trees[i, j] = tt.get(f"{kx[i, j]},{kz[i, j]}", 0)
        self.building = self.roof & (self.trees < 2)
        self.wood = np.clip(self.trees / 8.0, 0, 1) + 0.5 * (self.roof & ~self.building)
        self.wood = np.clip(self.wood, 0, 1)
        self.covered = self.valid & (self.roof | (self.trees >= 6))
        self.robj = np.hypot(self.X - self.ox, self.Z - self.oz)
        # The distance to the nearest cover (a field from the covered cells over plain metres).
        unit = np.where(self.valid, 1.0, np.inf)
        self.cover_m = field(Costs(self, unit, slope=False), self.covered)

    def cell(self, x, z):
        i = int(round((x - self.x0) / self.step))
        j = int(round((z - self.z0) / self.step))
        if 0 <= i < self.nx and 0 <= j < self.nz:
            return i, j
        return None

    def xz(self, c):
        return float(self.X[c]), float(self.Z[c])

    def ok(self, c):
        return c is not None and self.valid[c]

    def nearest_valid(self, x, z, r=60, avoid_building=False):
        c = self.cell(x, z)
        if c and self.valid[c] and not (avoid_building and self.building[c]):
            return c
        n = int(math.ceil(r / self.step))
        best, bd = None, 1e9
        ci, cj = int(round((x - self.x0) / self.step)), int(round((z - self.z0) / self.step))
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i, j = ci + di, cj + dj
                if 0 <= i < self.nx and 0 <= j < self.nz and self.valid[i, j] and not (avoid_building and self.building[i, j]):
                    d = di * di + dj * dj
                    if d < bd:
                        best, bd = (i, j), d
        return best


class Costs:
    """Edge weights per direction: metres x the mean of the two cells' costs, plus steep ground."""

    def __init__(self, g: Grid, cell_cost, slope=True):
        self.g, self.c = g, cell_cost
        self.W = []
        for di, dj, f in DIRS:
            ai, bi = _sl(g.nx, di)
            aj, bj = _sl(g.nz, dj)
            m = f * g.step
            w = m * (cell_cost[ai, aj] + cell_cost[bi, bj]) / 2
            if slope:
                s = np.abs(g.H[bi, bj] - g.H[ai, aj]) / m
                w = w + m * 4 * np.maximum(0, s - 0.3)
            self.W.append((ai, aj, bi, bj, w))

    def w(self, a, b):
        g = self.g
        m = g.step * (1.4142 if (a[0] != b[0] and a[1] != b[1]) else 1.0)
        w = m * (self.c[a] + self.c[b]) / 2
        s = abs(float(g.H[b]) - float(g.H[a])) / m
        return w + m * 4 * max(0.0, s - 0.3)


def field(costs: Costs, sources, max_iter=2000):
    """The cheapest cost from every cell to the sources (a mask): Bellman-Ford over the grid, all cells at once."""
    D = np.full(sources.shape, np.inf)
    D[sources] = 0.0
    for it in range(max_iter):
        if it % 12 == 0:
            before = D.copy()
        for ai, aj, bi, bj, w in costs.W:
            v = D[ai, aj]
            np.minimum(v, D[bi, bj] + w, out=v)
        if it % 12 == 11 and np.array_equal(before, D):
            break
    return D


def descend(D, costs: Costs, start, limit=2000):
    """The cells from start down the field D to its source."""
    g = costs.g
    path, c = [start], start
    for _ in range(limit):
        if D[c] <= 0 or not np.isfinite(D[c]):
            break
        best, bv = None, np.inf
        for di, dj, _ in DIRS:
            n = (c[0] + di, c[1] + dj)
            if 0 <= n[0] < g.nx and 0 <= n[1] < g.nz and D[n] < D[c]:
                v = D[n] + costs.w(c, n)
                if v < bv:
                    best, bv = n, v
        if best is None:
            break
        path.append(best)
        c = best
    return path


def observers_from(known, enemy_count_cap=3):
    """Known enemy positions clustered within 30 m: (x, z, weight)."""
    pts = list(known)
    out = []
    used = [False] * len(pts)
    for i, (x, z) in enumerate(pts):
        if used[i]:
            continue
        members = [(x, z)]
        used[i] = True
        for j in range(i + 1, len(pts)):
            if not used[j] and math.hypot(pts[j][0] - x, pts[j][1] - z) <= 30:
                used[j] = True
                members.append(pts[j])
        n = len(members)
        cx = sum(p[0] for p in members) / n
        cz = sum(p[1] for p in members) / n
        out.append((cx, cz, 1 + 0.5 * (min(n, enemy_count_cap) - 1)))
    return out


def threat_map(g: Grid, observers, K=48):
    """Per cell: the known enemies that see it (sight over terrain, buildings, wood), weighted by nearness."""
    T = np.zeros((g.nx, g.nz), np.float32)
    vi, vj = np.nonzero(g.valid)
    tx, tz = g.X[vi, vj], g.Z[vi, vj]
    th = g.H[vi, vj] + TARGET_M
    t = (np.arange(K) + 0.5) / K
    for ox, oz, w in observers:
        oc = g.nearest_valid(ox, oz, 40)
        if oc is None:
            continue
        ho = float(g.H[oc]) + EYE_M
        d = np.hypot(tx - ox, tz - oz)
        sel = (d > 5) & (d <= VIEW_M)
        if not sel.any():
            continue
        dx, dz, dd, hh = tx[sel] - ox, tz[sel] - oz, d[sel], th[sel]
        sx = ox + dx[:, None] * t[None, :]
        sz = oz + dz[:, None] * t[None, :]
        si = np.clip(np.round((sx - g.x0) / g.step).astype(int), 0, g.nx - 1)
        sj = np.clip(np.round((sz - g.z0) / g.step).astype(int), 0, g.nz - 1)
        hs = g.H[si, sj]
        ray = ho + (hh - ho)[:, None] * t[None, :]
        along = dd[:, None] * t[None, :]
        inner = (along > 8) & (dd[:, None] - along > 8)
        solid = (((hs + BUILDING_M * g.building[si, sj]) > ray) & inner).any(1)
        low = (ray - hs) < 14
        wood = (g.wood[si, sj] * (inner & low)).sum(1) * (dd / K)
        vis = (~solid) & (wood < WOOD_BLOCK_M)
        fall = np.where(dd <= 150, 1.0, 1.0 - 0.65 * (dd - 150) / (VIEW_M - 150))
        T[vi[sel], vj[sel]] += (w * vis * fall).astype(np.float32)
    return np.minimum(T, THREAT_CAP)


class Situation:
    """One side's picture at one moment: what the log says, as the side may know it."""

    def __init__(self):
        self.t = 0
        self.side = ""
        self.enemy = ""
        self.hq = {}            # side -> (x, z)
        self.owner = "FIA"
        self.teams = []         # dicts: id, role, men, ride, x, z, to
        self.known = []         # (x, z) the side knows
        self.lost = {"US": 0, "USSR": 0}
        self.own_losses = []    # (t, kind, x, z) of the side's own losses in the last DANGER_S
        self.sites = []         # (x, z, name) of the enemy drone sites the side has located
        self.armour = []        # the side's fighting vehicles: dicts unit, prefab, phase, x, z, health
        self.known_n = 0
        self.droneplan = {}     # the side's drone plan's last decision ([ZCR][DRONEPLAN])
        self.nodes = {}         # base name -> graph node id; "enemy_hq" -> the enemy main base's


class LogReader:
    """Follows a console.log: the last [ZCR][LIVE] round per side, [ZCR][KNOWN], captures, losses."""

    LIVE = re.compile(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=(\w+) id=(\d+) role=(\w+) men=(\d+) ride=(\d) x=(-?\d+) z=(-?\d+) to=(.*?) posture=")
    KNOWN = re.compile(r"\[ZCR\]\[KNOWN\] t=(\d+) side=(\w+) n=(\d+) at=(\S*)")
    CAPTURE = re.compile(r"\[ZCR\]\[CAPTURE\] t=(\d+) base=(.+?) from=(\w*) to=(\w+)")
    SETUP = re.compile(r"\[ZCR\]\[SETUP\] t=(\d+) no_fia base=(\S+) to=(\w+)")
    LOSS = re.compile(r"\[ZCR\]\[LOSS\] t=(\d+) .* side=(\w+) kind=man")
    DRONEPLAN = re.compile(r"\[ZCR\]\[DRONEPLAN\] t=(\d+) side=(\w+) teams=(\d+) tempo=(\d+) have=(\d+) .*?why=(.*)$")

    def __init__(self, path: Path):
        self.path = path
        self.pos = 0
        self.t = 0
        self.rounds = {"US": {}, "USSR": {}}    # side -> t -> {id: team}
        self.last_round = {"US": 0, "USSR": 0}
        self.known = {"US": [], "USSR": []}
        self.known_t = {"US": -1, "USSR": -1}
        self.owner = "FIA"
        self.owner_t = 0
        self.lost = {"US": 0, "USSR": 0}
        self.losses = []        # (t, side, kind "man"|"vehicle", x, z) - every loss (danger zones, note 541)
        self.sites = []         # [side, x, z, name] - every drone site set up ([ZCR][DRONESITE] set_up)
        self.field_built = {"US": [], "USSR": []}   # (x, z) of each field fortification built ([ZCR][FORTPLAN] source=field)
        self.located = {"US": set(), "USSR": set()}   # side -> indexes of ENEMY drone sites it has located (note 542)
        self.armour = {"US": {}, "USSR": {}}  # side -> unit -> its last [ZCR][ARMOUR] STATUS (note 544)
        self.first_round = {}
        self.droneplan = {}     # side -> the drone plan's last decision (teams wanted, tempo, teams it has, why)
        self.buf = ""

    def poll(self, until_t=None):
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            data = f.read()
        if not data:
            return
        text = self.buf + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self.buf = lines.pop()
        consumed = len(data)
        for k, line in enumerate(lines):
            if until_t is not None:
                m = re.search(r"\[ZCR\]\[\w+\] t=(\d+)", line)
                if m and int(m.group(1)) > until_t:
                    self.buf = ""
                    consumed = 0
                    break
            self.feed(line)
        self.pos += consumed

    def feed(self, line):
        if "[ZCR]" not in line:
            return
        m = self.LIVE.search(line)
        if m:
            t, side = int(m.group(1)), m.group(2)
            if side not in self.rounds:
                return
            self.t = max(self.t, t)
            team = {"id": int(m.group(3)), "role": m.group(4), "men": int(m.group(5)), "ride": int(m.group(6)),
                    "x": float(m.group(7)), "z": float(m.group(8)), "to": m.group(9).strip()}
            self.rounds[side].setdefault(t, {})[team["id"]] = team
            if t > self.last_round[side]:
                old = [k for k in self.rounds[side] if k < t - 30]
                for k in old:
                    if side not in self.first_round:
                        self.first_round[side] = list(self.rounds[side][k].values())
                    del self.rounds[side][k]
                self.last_round[side] = t
            return
        if "[ZCR][ARMOUR]" in line and (" event=STATUS " in line or " event=LOST " in line):
            d = dict(kv.split("=", 1) for kv in line.split("[ZCR][ARMOUR]", 1)[1].split() if "=" in kv)
            side, unit = d.get("side"), d.get("unit")
            if side in self.armour and unit:
                if d.get("event") == "LOST":
                    self.armour[side].pop(unit, None)
                else:
                    try:
                        self.armour[side][unit] = {"unit": int(unit), "prefab": d.get("prefab", "?"), "phase": d.get("phase", "?"),
                                                   "x": float(d["x"]), "z": float(d["z"]), "health": int(float(d.get("health", 100))),
                                                   "aboard": d.get("aboard", "?"), "t": int(d.get("t", 0))}
                    except (KeyError, ValueError):
                        pass
            return
        if "[ZCR][FORTPLAN]" in line and " event=placed " in line and "source=field" in line:
            d = dict(kv.split("=", 1) for kv in line.split("[ZCR][FORTPLAN]", 1)[1].split() if "=" in kv)
            try:
                if d.get("side") in self.field_built:
                    self.field_built[d["side"]].append((float(d["x"]), float(d["z"])))
            except ValueError:
                pass
            return
        if "[ZCR][DRONESITE]" in line and " set_up " in line:
            d = dict(kv.split("=", 1) for kv in line.split("[ZCR][DRONESITE]", 1)[1].split() if "=" in kv)
            try:
                self.sites.append([d["side"], float(d["x"]), float(d["z"]), line.split(" at=", 1)[1].split(" main=")[0]])
            except (KeyError, ValueError, IndexError):
                pass
            return
        m = self.KNOWN.search(line)
        if m:
            side = m.group(2)
            pts = []
            for p in m.group(4).split(";"):
                if "," in p:
                    a, b = p.split(",")
                    pts.append((float(a), float(b)))
            self.known[side] = pts
            # An enemy drone site is located once an enemy the side saw stood near it (its operators, its truck).
            for k, (ss, sx, sz, _) in enumerate(self.sites):
                if ss != side and side in self.located and k not in self.located[side] and \
                        any(math.hypot(x - sx, z - sz) <= SITE_SEEN_M for x, z in pts):
                    self.located[side].add(k)
            self.known_t[side] = int(m.group(1))
            self.t = max(self.t, int(m.group(1)))
            return
        m = self.CAPTURE.search(line)
        if m and m.group(2) == OBJECTIVE:
            self.owner = m.group(4)
            self.owner_t = int(m.group(1))
            return
        # The objective dealt to a side at the start (-zcrBaseTo, 4 Nov evening: the field fortification test gave Beauregard
        # to the US and its general planned as the attacker - captures were all the reader knew).
        m = self.SETUP.search(line)
        if m and m.group(2) == OBJECTIVE and m.group(3) in ("US", "USSR"):
            self.owner = m.group(3)
            self.owner_t = int(m.group(1))
            return
        m = self.LOSS.search(line)
        if m and m.group(2) in self.lost:
            self.lost[m.group(2)] += 1
        if "[ZCR][LOSS]" in line:
            # A man: his side. A vehicle: its side is gone once it burns - the game credits a drone's hit to an occupant
            # who died with it (killer_dead=1), so his side is the vehicle's.
            d = dict(kv.split("=", 1) for kv in line.split("[ZCR][LOSS]", 1)[1].split() if "=" in kv)
            kind, side = d.get("kind"), d.get("side", "")
            if kind == "vehicle" and side not in self.lost and d.get("killer_dead") == "1":
                side = d.get("killer_side", "")
            try:
                if kind in ("man", "vehicle") and side in self.lost:
                    self.losses.append((int(d["t"]), side, kind, float(d["x"]), float(d["z"])))
            except (KeyError, ValueError):
                pass
            return
        m = self.DRONEPLAN.search(line)
        if m:
            why = m.group(6).strip()
            # The drone rule's own count from the situation (ZCR_Drones.Decide: 2, +1 each for attack, contact, threat,
            # finding, -1 for a team lost; 2-6) - shown to the model, which otherwise saw its own order back as the rule's.
            rule = 2 + sum(1 for k in ("attack", "contact=", "threat=", "finding=") if re.search(r"(^| )" + k, why))
            rule -= 1 if re.search(r"(^| )lost", why) else 0
            self.droneplan[m.group(2)] = {"t": int(m.group(1)), "teams": int(m.group(3)), "tempo": int(m.group(4)),
                                          "have": int(m.group(5)), "why": why, "rule": max(2, min(6, rule))}

    def teams(self, side):
        """The newest complete round of a side's teams (the round before the newest, which may still be filling)."""
        r = self.rounds.get(side, {})
        if not r:
            return []
        ts = sorted(r)
        t = ts[-2] if len(ts) >= 2 else ts[-1]
        return list(r[t].values())


def hq_positions(run_dir: Path, reader: LogReader) -> dict:
    """Each side's HQ: from the commander's snapshots (bases with hq=1), else the median of its teams' first round."""
    snap = run_dir / "profile" / "zcr" / "snapshots.jsonl"
    out = {}
    if snap.exists():
        for line in snap.read_text(encoding="utf-8", errors="replace").splitlines()[:2]:
            try:
                for b in json.loads(line).get("bases", []):
                    if b.get("hq") and b.get("owner") in ("US", "USSR"):
                        out[b["owner"]] = (b["x"], b["z"])
            except ValueError:
                continue
    for side in ("US", "USSR"):
        if side not in out:
            first = reader.first_round.get(side) or reader.teams(side)
            if first:
                out[side] = (sorted(t["x"] for t in first)[len(first) // 2], sorted(t["z"] for t in first)[len(first) // 2])
    return out


class Planner:
    def __init__(self, slug="arland", scan=None):
        self.scan_path = scan or ATTACK / "farm_scan.jsonl"
        self.g = Grid(self.scan_path, slug)
        roads = [json.loads(l) for l in (MAPS / slug / "map_roads.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        self.roads = roads
        self._fort_terrain = None
        self.graph = roadgraph.Graph(roads, [])
        g = self.g
        self.goal = g.valid & (g.robj <= GOAL_M)
        self.node_cell = {}
        for i in range(len(self.graph.x)):
            c = g.cell(self.graph.x[i], self.graph.z[i])
            if c is not None and g.valid[c]:
                self.node_cell[i] = c

    # -- the picture --------------------------------------------------------------------------------------------------
    def costs(self, threat, owner, side):
        g = self.g
        static = STATIC_COST if owner not in (side, "FIA", "") else (0.0 if owner == side else STATIC_COST_OPEN)
        c = 1 + THREAT_COST * threat + static * g.seen / 9 + NO_COVER_COST * (g.cover_m > COVER_REACH_M)
        return np.where(g.valid, c, np.inf)

    def danger(self, s: Situation):
        """The side's danger field from its own recent losses: per cell, the faded weight of the losses within DANGER_R_M."""
        g = self.g
        D = np.zeros(g.X.shape, np.float32)
        for lt, kind, x, z in s.own_losses:
            w = (3.0 if kind == "vehicle" else 1.0) * max(0.0, 1.0 - (s.t - lt) / DANGER_S)
            if w <= 0:
                continue
            r2 = (g.X - x) ** 2 + (g.Z - z) ** 2
            D += np.where(r2 <= DANGER_R_M ** 2, w, 0.0).astype(np.float32)
        D = np.minimum(D, DANGER_CAP)
        D[g.robj <= DANGER_FREE_M] = 0
        return D

    @staticmethod
    def zones(s: Situation, ox, oz):
        """The side's danger zones: its recent losses grouped within DANGER_GROUP_M (Z1, Z2, ... heaviest first)."""
        groups = []
        for lt, kind, x, z in sorted(s.own_losses, key=lambda l: -l[0]):
            for gr_ in groups:
                if math.hypot(gr_["x"] - x, gr_["z"] - z) <= DANGER_GROUP_M:
                    n = gr_["men"] + gr_["vehicles"]
                    gr_["x"] += (x - gr_["x"]) / (n + 1)
                    gr_["z"] += (z - gr_["z"]) / (n + 1)
                    gr_["vehicles" if kind == "vehicle" else "men"] += 1
                    gr_["weight"] += (3.0 if kind == "vehicle" else 1.0) * max(0.0, 1.0 - (s.t - lt) / DANGER_S)
                    break
            else:
                groups.append({"x": x, "z": z, "men": int(kind == "man"), "vehicles": int(kind == "vehicle"), "newest_s": s.t - lt,
                               "weight": (3.0 if kind == "vehicle" else 1.0) * max(0.0, 1.0 - (s.t - lt) / DANGER_S)})
        zones = [gr_ for gr_ in groups if gr_["weight"] >= 1.5]
        zones.sort(key=lambda gr_: -gr_["weight"])
        for k, zn in enumerate(zones):
            zn["id"] = f"Z{k + 1}"
            zn["x"], zn["z"], zn["weight"] = round(zn["x"]), round(zn["z"]), round(zn["weight"], 1)
            zn["from_obj_m"] = round(math.hypot(zn["x"] - ox, zn["z"] - oz))
            zn["dir"] = compass(math.degrees(math.atan2(zn["x"] - ox, zn["z"] - oz)))
        return zones

    def threat(self, s: Situation):
        T = threat_map(self.g, observers_from(s.known))
        if s.owner not in (s.side, "FIA", ""):
            T = np.minimum(THREAT_CAP, T + 1.5 * self.g.seen / 9)
        return T

    def drive(self, hq, threat):
        """The road graph from the HQ: cost per node (roads the known enemies see, and near the objective, dear)."""
        import heapq
        gr, g = self.graph, self.g
        src, _ = gr.nearest(hq[0], hq[1], 3.0, 400)
        if src is None:
            return {}, {}
        extra = {}
        for i, c in self.node_cell.items():
            e = DRIVE_THREAT_COST * float(threat[c])
            if g.robj[c] < NEAR_OBJ_DRIVE_M:
                e += 5.0
            if e:
                extra[i] = e
        dist, prev = {src: 0.0}, {}
        heap = [(0.0, src)]
        while heap:
            cst, u = heapq.heappop(heap)
            if cst > dist.get(u, 1e18):
                continue
            for v, d, f in gr.adj.get(u, ()):
                nc = cst + d * f + gr.penalty[v] + d * extra.get(v, 0.0)
                if nc < dist.get(v, 1e18):
                    dist[v] = nc
                    prev[v] = u
                    heapq.heappush(heap, (nc, v))
        return dist, prev

    def drops(self, s: Situation, threat, D_obj):
        g, gr = self.g, self.graph
        hq = s.hq.get(s.side)
        if not hq:
            return []
        dist, prev = self.drive(hq, threat)
        from_deg = math.degrees(math.atan2(hq[0] - g.ox, hq[1] - g.oz))
        enemy_holds = s.owner not in (s.side, "FIA", "")
        cands = []
        for strict in (True, False):
            for i, c in self.node_cell.items():
                r = float(g.robj[c])
                if not (DROP_MIN <= r <= DROP_MAX) or i not in dist or gr.w[i] < 3 or not np.isfinite(D_obj[c]):
                    continue
                angle = math.degrees(math.atan2(gr.x[i] - g.ox, gr.z[i] - g.oz))
                off = abs((angle - from_deg + 180) % 360 - 180)
                if off > SIDE_MAX_DEG:
                    continue
                i0, i1, j0, j1 = max(0, c[0] - 2), c[0] + 3, max(0, c[1] - 2), c[1] + 3
                if threat[i0:i1, j0:j1].max() > 0.05:
                    continue
                if strict and g.seen[i0:i1, j0:j1].max() > 0:
                    continue
                if not strict and g.seen[c] > (0 if enemy_holds else 2):
                    continue
                score = dist[i] / DRIVE_MPS + D_obj[c] / WALK_MPS + max(0.0, off - SIDE_FREE_DEG)
                cands.append((score, i, c, angle, off))
            if len({int(((a + 360) % 360) // 30) for _, _, _, a, _ in cands}) >= 3:
                break
        best = {}
        for cnd in cands:
            sec = int(((cnd[3] + 360) % 360) // 30)
            if sec not in best or cnd[0] < best[sec][0]:
                best[sec] = cnd
        chosen = []
        for cnd in sorted(best.values()):
            if all(abs((cnd[3] - o[3] + 180) % 360 - 180) >= 25 for o in chosen):
                chosen.append(cnd)
            if len(chosen) >= DROP_N:
                break
        out = []
        for n, (score, i, c, angle, off) in enumerate(chosen):
            nodes = [i]
            while nodes[-1] in prev:
                nodes.append(prev[nodes[-1]])
            length = sum(math.hypot(gr.x[a] - gr.x[b], gr.z[a] - gr.z[b]) for a, b in zip(nodes, nodes[1:]))
            seen_nodes = sum(1 for k in nodes if k in self.node_cell and threat[self.node_cell[k]] > 0.2)
            out.append({"id": f"D{n + 1}", "x": round(gr.x[i], 1), "z": round(gr.z[i], 1), "cell": c,
                        "from_obj_m": round(float(g.robj[c])), "dir": compass(angle), "drive_m": round(length),
                        "drive_seen_pts": seen_nodes, "score": round(score)})
        return out

    def support(self, s: Situation, threat):
        g = self.g
        hq = s.hq.get(s.side)
        if not hq:
            return []
        from_deg = math.degrees(math.atan2(hq[0] - g.ox, hq[1] - g.oz))
        ang = np.degrees(np.arctan2(g.X - g.ox, g.Z - g.oz))
        off = np.abs((ang - from_deg + 180) % 360 - 180)
        ok = g.valid & (g.seen >= 4) & (g.robj >= 150) & (g.robj <= 450) & (off <= 100) & (threat < 0.3) & ~g.building
        score = (g.H - g.oy) * 0.5 + 20 * (g.cover_m <= 10) - 30 * threat - off * 0.1 - g.robj / 40
        score = np.where(ok, score, -np.inf)
        out = []
        flat = np.argsort(score, axis=None)[::-1]
        for k in flat[:4000]:
            c = np.unravel_index(k, score.shape)
            if not np.isfinite(score[c]):
                break
            x, z = g.xz(c)
            if all(math.hypot(x - p["x"], z - p["z"]) >= 150 for p in out):
                out.append({"id": f"P{len(out) + 1}", "x": x, "z": z, "cell": c, "from_obj_m": round(float(g.robj[c])),
                            "sees": int(g.seen[c]), "height_over_obj_m": round(float(g.H[c] - g.oy), 1),
                            "cover": bool(g.cover_m[c] <= 10)})
            if len(out) >= 2:
                break
        return out

    # Field fortifications (4 Nov, note 538 - Martin: "llm general could actually build defense lines (bunkers and shit)
    # where it needs like who told that some position outside of the base could not set up?"): places outside any base
    # where the side's builders can put a bunker or guard tower (AICF_ZcrFortPlan builds the ones the general picks - 'fort'
    # lines). Open flat ground (no roof, under 2 trees, slope <= FORT_SLOPE), cover in reach. The side holding the objective:
    # a ring FORT_HOLD_M out toward the enemy's side, facing outward; the other side: places FORT_ATTACK_M out on its own
    # side that see the objective, facing it - a base of fire. Not in the side's danger zones nor (attacking) the enemy's view.
    FORT_SLOPE = 0.15
    FORT_HOLD_M = (110, 240)     # 4 Nov night: from 50 m - spots inside the town's base failed its access corridors
    FORT_ATTACK_M = (150, 400)
    FORT_SPACING_M = 50
    FORT_CANDIDATES = 5
    FORT_ROAD_M = 12     # from a road's edge (the game's ROAD_OR_ACCESS_CORRIDOR: 10 of the first test's 21 tries)
    FORT_OBJECT_M = 7    # no wall, fence or rock 0.4 m+ this close (PHYSICAL_OBSTRUCTION: 8 of 21) - lab/fortplan.py's checks

    def fort_terrain(self):
        """lab/fortplan.py's ground around the objective (its objects on a 2 m grid), loaded once."""
        if self._fort_terrain is None:
            import fortplan
            self._fort_terrain = fortplan.Terrain({"scan": Path(self.scan_path), "x": self.g.ox, "z": self.g.oz})
        return self._fort_terrain

    def field_forts(self, s: Situation, threat, danger):
        g = self.g
        hq = s.hq.get(s.side)
        enemy_hq = s.hq.get(s.enemy)
        holding = s.owner == s.side
        if not hasattr(g, "slope_cell"):
            gx, gz = np.gradient(g.H, g.step)
            g.slope_cell = np.hypot(gx, gz)
        ang = np.degrees(np.arctan2(g.X - g.ox, g.Z - g.oz))
        if holding and enemy_hq:
            to_deg = math.degrees(math.atan2(enemy_hq[0] - g.ox, enemy_hq[1] - g.oz))
            lo, hi = self.FORT_HOLD_M
            width = 80
        elif hq:
            to_deg = math.degrees(math.atan2(hq[0] - g.ox, hq[1] - g.oz))
            lo, hi = self.FORT_ATTACK_M
            width = 80
        else:
            return []
        off = np.abs((ang - to_deg + 180) % 360 - 180)
        ok = (g.valid & ~g.roof & (g.trees < 2) & (g.slope_cell <= self.FORT_SLOPE) & (g.robj >= lo) & (g.robj <= hi)
              & (off <= width) & (danger < 0.5) & (g.cover_m <= 40))
        if not holding:
            ok &= threat < 0.5     # 4 Nov night: a town hides the point - no cell 150-400 m out sees Beauregard; sight only scores
        mid = (lo + hi) / 2
        score = -off * 0.15 - np.abs(g.robj - mid) / 15 + 8 * (g.cover_m <= 15) - 20 * danger
        if not holding:
            score += g.seen * 1.5 - 20 * threat
        score = np.where(ok, score, -np.inf)
        out = []
        for k in np.argsort(score, axis=None)[::-1][:6000]:
            c = np.unravel_index(k, score.shape)
            if not np.isfinite(score[c]):
                break
            x, z = g.xz(c)
            if any(math.hypot(x - f["x"], z - f["z"]) < self.FORT_SPACING_M for f in out):
                continue
            import fortplan
            if fortplan.road_gap(x, z, self.roads) < self.FORT_ROAD_M or self.fort_terrain().object_near(x, z, self.FORT_OBJECT_M) >= 0.4:
                continue
            if holding:
                facing = math.degrees(math.atan2(x - g.ox, z - g.oz)) % 360        # outward, the way the enemy comes
            else:
                facing = math.degrees(math.atan2(g.ox - x, g.oz - z)) % 360        # at the objective
            out.append({"id": f"F{len(out) + 1}", "x": round(x, 1), "z": round(z, 1), "facing": round(facing),
                        "from_obj_m": round(float(g.robj[c])), "dir": compass(math.degrees(math.atan2(x - g.ox, z - g.oz))),
                        "cover_m": round(float(g.cover_m[c])), "sees": int(g.seen[c]), "role": "hold" if holding else "fire base"})
            if len(out) >= self.FORT_CANDIDATES:
                break
        return out

    # -- routes -------------------------------------------------------------------------------------------------------
    def routes_from(self, key, start_xz, costs, D_obj, threat):
        """C: the cheapest way in; L / R: the best ones through a gate left / right of it."""
        g = self.g
        sc = g.nearest_valid(start_xz[0], start_xz[1], 80)
        if sc is None or not np.isfinite(D_obj[sc]):
            return {}
        src = np.zeros(D_obj.shape, bool)
        src[sc] = True
        D_s = field(costs, src)
        total = D_s + D_obj
        out = {"C": descend(D_obj, costs, sc)}
        sx, sz = g.xz(sc)
        r_s = math.hypot(sx - g.ox, sz - g.oz)
        theta = math.degrees(math.atan2(sx - g.ox, sz - g.oz))
        if r_s > 220:
            rg = min(320.0, max(120.0, 0.55 * r_s))
            ang = np.degrees(np.arctan2(g.X - g.ox, g.Z - g.oz))
            rel = (ang - theta + 180) % 360 - 180
            ring = g.valid & (np.abs(g.robj - rg) <= 25)
            for name, lo, hi in (("L", 20, 75), ("R", -75, -20)):
                gate = ring & (rel >= lo) & (rel <= hi) & (total < 2.5 * D_obj[sc] + 1)
                if not gate.any():
                    continue
                cstar = np.unravel_index(np.argmin(np.where(gate, total, np.inf)), total.shape)
                first = descend(D_s, costs, cstar)[::-1]
                out[name] = first + descend(D_obj, costs, cstar)[1:]
        routes = {}
        for side, cells in out.items():
            if len(cells) < 3:
                continue
            routes[side] = self.route_info(f"{key}-{side}", cells, costs, threat, D_s)
        # Drop near-copies (a side route that runs with C).
        for side in ("L", "R"):
            if side in routes and "C" in routes and overlap(routes[side]["pts"], routes["C"]["pts"]) > 0.7:
                del routes[side]
        return routes

    def route_info(self, rid, cells, costs, threat, D_s=None):
        g = self.g
        pts = [g.xz(c) for c in cells]
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        n = len(cells)
        thr = [float(threat[c]) for c in cells]
        seen_pct = round(100 * sum(1 for v in thr if v > 0.2) / n)
        cover_pct = round(100 * sum(1 for c in cells if g.cover_m[c] <= COVER_REACH_M) / n)
        obj_pct = round(100 * sum(1 for c in cells if g.seen[c] > 0) / n)
        cost = sum(costs.w(a, b) for a, b in zip(cells, cells[1:]))
        wps, chain, open_max, wp_kinds = cover_bounds(g, cells)   # was thin_cells (a point every 50 m) - now cover to cover
        hold = hold_point(g, cells, threat)
        return {"id": rid, "cells": cells, "pts": pts, "length_m": round(length), "minutes": round(length / WALK_MPS / 60, 1),
                "known_enemy_view_pct": seen_pct, "max_threat": round(max(thr), 2), "cover_in_reach_pct": cover_pct,
                "farm_view_pct": obj_pct, "cost": round(cost), "waypoints": wps, "hold": hold,
                "chain": chain_text(chain), "open_max_m": open_max, "wp_kinds": wp_kinds}

    def route_via(self, rid, start_xz, via_cell, costs, D_obj, threat):
        """From a start through a point (a support position) into the objective."""
        g = self.g
        sc = g.nearest_valid(start_xz[0], start_xz[1], 80)
        if sc is None:
            return None
        src = np.zeros(D_obj.shape, bool)
        src[sc] = True
        D_s = field(costs, src)
        if not np.isfinite(D_s[via_cell]):
            return None
        cells = descend(D_s, costs, via_cell)[::-1] + descend(D_obj, costs, via_cell)[1:]
        info = self.route_info(rid, cells, costs, threat)
        info["hold"] = list(g.xz(via_cell))
        return info


def overlap(a, b, r=30):
    """The share of a's points within r of a point of b."""
    if not a:
        return 0.0
    bb = np.array(b)
    near = sum(1 for p in a if np.min(np.hypot(bb[:, 0] - p[0], bb[:, 1] - p[1])) <= r)
    return near / len(a)


def thin_cells(g: Grid, cells):
    """Waypoints every ~WAYPOINT_M along the route, off buildings (the navmesh is round them)."""
    pts = [g.xz(c) for c in cells]
    out, run = [pts[0]], 0.0
    for p, q in zip(pts, pts[1:]):
        run += math.hypot(q[0] - p[0], q[1] - p[1])
        if run >= WAYPOINT_M:
            out.append(q)
            run = 0.0
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    fixed = []
    for x, z in out:
        c = g.cell(x, z)
        if c is not None and g.building[c]:
            c2 = g.nearest_valid(x, z, 25, avoid_building=True)
            if c2 is not None:
                x, z = g.xz(c2)
        fixed.append((round(x, 1), round(z, 1)))
    return fixed


COVER_NEAR_M = 8        # a route cell this close to a roof, canopy or dense trees counts as in cover
BOUND_IN_COVER_M = 120  # inside a long cover stretch, a point every this many metres
BOUND_OPEN_M = 100      # across a long open stretch (over 150 m), a point every this many metres


def cover_bounds(g: Grid, cells):
    """The route as bounds from cover to cover (3 Nov night, note 535 - Martin: "the fastest way to actually win would be
    to gradually occupy building and then push from closes building to closest tree line and thoe the points", "llm
    general should actually plan axis of attack based on covers", "movement from cover to cover should be fast"): the
    route's stretches in cover (a building, a tree line or wood) and in the open; a waypoint at the far edge of each cover
    stretch (the jump-off point to the next), every BOUND_IN_COVER_M inside a long one and every BOUND_OPEN_M across a
    long open one, and the end. -> (waypoints, chain [{"kind", "from_obj_m", "len_m"}], longest open stretch in m)"""
    pts = [g.xz(c) for c in cells]
    n = len(cells)
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    near = [float(g.cover_m[c]) <= COVER_NEAR_M for c in cells]

    def building_near(k):
        i0, j0 = cells[k]
        return any(0 <= i0 + di < g.nx and 0 <= j0 + dj < g.nz and g.building[i0 + di, j0 + dj] for di in (-1, 0, 1) for dj in (-1, 0, 1))

    def index_at(d, lo, hi):
        for k in range(lo, hi + 1):
            if cum[k] >= d:
                return k
        return hi

    idx, chain, longest = [], [], 0.0
    kind_at = {}   # waypoint index -> what it is (the map shows it: 4 Nov, "type of waypoint and status")
    i = 0
    while i < n:
        j = i
        while j + 1 < n and near[j + 1] == near[i]:
            j += 1
        span = cum[j] - cum[i]
        if near[i]:
            what = "buildings" if any(building_near(q) for q in range(i, j + 1)) else "trees"
            k = i
            while cum[j] - cum[k] > BOUND_IN_COVER_M + 20:
                k = index_at(cum[k] + BOUND_IN_COVER_M, k + 1, j)
                idx.append(k)
                kind_at[k] = "in " + what
            idx.append(j)
            kind_at[j] = "edge of " + what
            chain.append({"kind": what, "from_obj_m": round(float(g.robj[cells[j]])), "len_m": round(span)})
        else:
            gap = cum[min(j + 1, n - 1)] - cum[max(i - 1, 0)]
            longest = max(longest, gap)
            if gap > 150:
                k = i
                while cum[j] - cum[k] > BOUND_OPEN_M + 20:
                    k = index_at(cum[k] + BOUND_OPEN_M, k + 1, j)
                    idx.append(k)
                    kind_at[k] = "open"
            chain.append({"kind": "open", "from_obj_m": round(float(g.robj[cells[j]])), "len_m": round(gap)})
        i = j + 1
    idx.append(n - 1)
    kind_at[n - 1] = "Farm"
    out, last = [], None
    for k in sorted(set(idx)):
        if k == 0 or (last is not None and cum[k] - cum[last] < 30 and k != n - 1):
            continue
        out.append(k)
        last = k
    wps, kinds = [], []
    for k in out:
        kinds.append(kind_at.get(k, "route"))
        x, z = pts[k]
        if g.building[cells[k]]:
            c2 = g.nearest_valid(x, z, 25, avoid_building=True)
            if c2 is not None:
                x, z = g.xz(c2)
        wps.append((round(x, 1), round(z, 1)))
    if not wps:
        wps, kinds = [(round(pts[-1][0], 1), round(pts[-1][1], 1))], ["Farm"]
    return wps, chain, round(longest), kinds


def chain_text(chain):
    """'trees 540 m out -> open 120 m -> buildings 300 m out -> Farm' (short open bits under 40 m left out)."""
    parts = []
    for b in chain:
        if b["kind"] == "open":
            if b["len_m"] >= 40:
                parts.append(f"open {b['len_m']} m")
        else:
            parts.append(f"{b['kind']} {b['from_obj_m']} m out")
    return " -> ".join(parts + ["Farm"])


def hold_point(g: Grid, cells, threat):
    """Where a waiting team waits: on the route 130-260 m from the objective, the spot with the least threat, covered."""
    best, bs = None, 1e9
    for c in cells:
        r = float(g.robj[c])
        if 130 <= r <= 260 and not g.building[c]:
            s = 10 * float(threat[c]) + 2 * float(g.seen[c]) / 9 + (0 if g.cover_m[c] <= 15 else 1.5) + abs(r - HOLD_M) / 100
            if s < bs:
                best, bs = c, s
    if best is None:
        best = min(cells, key=lambda c: abs(float(g.robj[c]) - HOLD_M)) if float(g.robj[cells[0]]) > 200 else cells[0]
    return list(g.xz(best))


def compass(angle):
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return names[int(((angle + 360) % 360 + 22.5) // 45) % 8]


# -- orders ----------------------------------------------------------------------------------------------------------
class Commander:
    """One side's live plan: the picture every round, the picker's orders per team, the file for the game."""

    def __init__(self, planner: Planner, side: str, picker: str, out_dir: Path, llm=None, log=print, drones=False):
        self.p = planner
        self.side = side
        self.picker = picker
        # 2 Nov night (Martin: "maybe even the LLM commander should decide when to use drones"): with drones, the model also
        # decides the side's drone operator teams (1-6) and where they fly (farm / enemy_hq / none) - the game hands it to
        # the drone plan's hook (ZCR_Strategist.ApplyLiveDrones); without, the drone rule decides.
        self.drones_on = drones and picker == "gemini"
        self.drones = None      # {"teams": n, "target": "farm"|"enemy_hq"|"none", "why": ""}
        self.out_dir = out_dir
        self.llm = llm
        self.log = log
        # team id -> {"drop_xz": (x, z)|None, "route": "L"|"C"|"R", "order": go|wait|support, "support_xz": (x, z)|None, "why", "source"}:
        # places, not ids - the drop points and support positions are numbered anew every round.
        self.orders = {}
        self.frozen_drop = {}   # team id -> (x, z): the drop point its ride was given
        self.frozen_hold = {}   # team id -> (order, (x, z)): the hold point of its wait or support while that order stands
        self.version = int(time.time()) % 100000 * 10
        self.lines = []         # this side's lines of the plan file (team/drones), for a shared file
        self.strategy = None    # {"stance", "why"} - the model's battle strategy (note 542)
        self.armour_orders = {}  # unit -> {"order", "xz", "why"} - the model's orders for its fighting vehicles (note 544)
        self.forts = []         # [{"x", "z", "facing", "t", "why"}] - the field fortifications the model wants built (note 538)
        self.wait_since = {}    # team id -> game second its present run of 'wait' orders began
        self.released = {}      # team id -> game second it was sent on after waiting WAIT_MAX_S
        self.sink = None        # --side both: writes both sides' lines into one liveplan.txt
        self.last_model_t = -1e9
        self.last_model_owner = None
        self.last_model_lost = 0
        self.model_calls = 0
        self.last = None        # the last round's picture (for the image)

    # The picture: threat, drop points, starts and their routes, support positions.
    def picture(self, s: Situation):
        p, g = self.p, self.p.g
        t0 = time.time()
        threat = p.threat(s)
        danger = p.danger(s)
        cost = p.costs(threat, s.owner, s.side) + DANGER_COST * danger
        costs = Costs(g, cost)
        D_obj = field(costs, p.goal)
        drops = p.drops(s, np.minimum(THREAT_CAP, threat + 0.5 * danger), D_obj)
        zones = p.zones(s, g.ox, g.oz)
        for d in drops:
            d["zones"] = [zn["id"] for zn in zones if math.hypot(zn["x"] - d["x"], zn["z"] - d["z"]) <= DANGER_R_M + 30]
        sup = p.support(s, threat)
        forts = p.field_forts(s, threat, danger)
        teams = [tm for tm in s.teams if tm["men"] > 0 and tm["role"] == "ATTACK" and tm["to"] == OBJECTIVE]
        hq = s.hq.get(s.side)
        status = {}
        for tm in teams:
            d_obj = math.hypot(tm["x"] - g.ox, tm["z"] - g.oz)
            if d_obj <= AT_OBJ_M:
                status[tm["id"]] = "at_farm"
            elif tm["ride"]:
                status[tm["id"]] = "riding"
            elif hq and math.hypot(tm["x"] - hq[0], tm["z"] - hq[1]) <= HQ_M:
                status[tm["id"]] = "at_hq"
            else:
                status[tm["id"]] = "on_foot"
        # Starts: each drop point; the teams on foot in groups within GROUP_M.
        starts = {}
        for d in drops:
            starts[d["id"]] = {"xz": (d["x"], d["z"]), "teams": []}
        groups = []
        for tm in teams:
            if status[tm["id"]] != "on_foot":
                continue
            for gr_ in groups:
                if math.hypot(tm["x"] - gr_["xz"][0], tm["z"] - gr_["xz"][1]) <= GROUP_M:
                    gr_["teams"].append(tm["id"])
                    break
            else:
                groups.append({"xz": (tm["x"], tm["z"]), "teams": [tm["id"]]})
        for n, gr_ in enumerate(groups):
            starts[f"G{n + 1}"] = gr_
        # Riding teams whose drop point is not among today's: their own start.
        for tm in teams:
            if status[tm["id"]] == "riding" and tm["id"] in self.frozen_drop:
                fx, fz = self.frozen_drop[tm["id"]]
                if not any(math.hypot(fx - d["x"], fz - d["z"]) < 30 for d in drops):
                    starts[f"V{tm['id']}"] = {"xz": (fx, fz), "teams": [tm["id"]]}
        routes = {}
        for key, st in starts.items():
            for side_, info in p.routes_from(key, st["xz"], costs, D_obj, threat).items():
                routes[info["id"]] = info
        for info in routes.values():
            info["zones"] = [zn["id"] for zn in zones if any(math.hypot(zn["x"] - x, zn["z"] - z) <= DANGER_R_M for x, z in info["pts"])]
        sites = []
        for sx, sz, sname in s.sites:
            cell = g.nearest_valid(sx, sz, 40, avoid_building=True)
            if cell is None:
                continue
            ang = math.degrees(math.atan2(sx - g.ox, sz - g.oz))
            sites.append({"id": f"H{len(sites) + 1}", "x": round(sx), "z": round(sz), "cell": cell, "name": sname,
                          "from_obj_m": round(math.hypot(sx - g.ox, sz - g.oz)), "dir": compass(ang)})
        known = observers_from(s.known)
        pic = {"t": s.t, "nodes": s.nodes, "threat": threat, "costs": costs, "D_obj": D_obj, "drops": drops, "support": sup, "teams": teams,
               "zones": zones, "sites": sites, "armour": list(s.armour), "forts": forts,
               "status": status, "starts": starts, "routes": routes, "known": known, "owner": s.owner, "lost": dict(s.lost),
               "hq": hq, "seconds": round(time.time() - t0, 1)}
        self.last = pic
        return pic

    @staticmethod
    def match_drop(pic, xz, within=150):
        """Today's drop point nearest a place (within 'within' m), else None."""
        if not xz or not pic["drops"]:
            return None
        d = min(pic["drops"], key=lambda d: math.hypot(d["x"] - xz[0], d["z"] - xz[1]))
        return d if math.hypot(d["x"] - xz[0], d["z"] - xz[1]) <= within else None

    @staticmethod
    def match_support(pic, xz, within=100):
        if not xz or not pic["support"]:
            return None
        p_ = min(pic["support"], key=lambda p_: math.hypot(p_["x"] - xz[0], p_["z"] - xz[1]))
        return p_ if math.hypot(p_["x"] - xz[0], p_["z"] - xz[1]) <= within else None

    def start_of(self, pic, tm):
        """The start key whose routes a team picks from: its drop point (not out yet), else its group."""
        st = pic["status"][tm["id"]]
        if st in ("at_hq", "riding"):
            o = self.orders.get(tm["id"], {})
            if st == "riding" and tm["id"] in self.frozen_drop:
                d = self.match_drop(pic, self.frozen_drop[tm["id"]], 30)
                return d["id"] if d else f"V{tm['id']}"
            d = self.match_drop(pic, o.get("drop_xz")) or (pic["drops"][0] if pic["drops"] else None)
            return d["id"] if d else None
        for key, s_ in pic["starts"].items():
            if key.startswith("G") and tm["id"] in s_["teams"]:
                return key
        return None

    def code_orders(self, pic, only=None):
        """The code's pick: the best drop points and routes, teams spread over the best two; go."""
        drops = pic["drops"]
        by_start = {}
        for rid, r in pic["routes"].items():
            by_start.setdefault(rid.rsplit("-", 1)[0], []).append(r)
        for v in by_start.values():
            v.sort(key=lambda r: r["cost"])
        n_hq = 0
        out = {}
        for k, tm in enumerate(sorted(pic["teams"], key=lambda t: t["id"])):
            if only is not None and tm["id"] not in only:
                continue
            st = pic["status"][tm["id"]]
            if st == "at_farm":
                continue
            o = {"order": "go", "support_xz": None, "why": "code: cheapest", "source": "code", "drop_xz": None}
            start = None
            # Sticky: a team keeps its drop point (while one of today's is near it) and its route side (while its start
            # has that route) - the code redraws the geometry, it doesn't reshuffle the teams every round.
            prev = self.orders.get(tm["id"])
            if prev and prev.get("source") == "code":
                pstart = self.start_of(pic, tm)
                if (st != "at_hq" or self.match_drop(pic, prev.get("drop_xz"))) and f"{pstart}-{prev.get('route')}" in pic["routes"]:
                    if st == "at_hq":
                        n_hq += 1
                    out[tm["id"]] = prev
                    continue
            if st == "at_hq" and drops:
                use = drops[1] if (len(drops) > 1 and n_hq % 2 == 1 and drops[1]["score"] <= 1.25 * drops[0]["score"]) else drops[0]
                n_hq += 1
                o["drop_xz"] = (use["x"], use["z"])
                start = use["id"]
            else:
                o["drop_xz"] = self.orders.get(tm["id"], {}).get("drop_xz")
                start = self.start_of(pic, tm)
            rs = by_start.get(start, [])
            if rs:
                pick = rs[1] if (len(rs) > 1 and k % 2 == 1 and rs[1]["cost"] <= 1.2 * rs[0]["cost"]) else rs[0]
                o["route"] = pick["id"].rsplit("-", 1)[1]
            else:
                o["route"] = "C"
            out[tm["id"]] = o
        return out

    # -- the model --------------------------------------------------------------------------------------------------
    def want_model(self, s: Situation):
        if self.picker != "gemini" or self.llm is None:
            return False
        since = s.t - self.last_model_t
        if since >= GEMINI_S:
            return True
        if since < GEMINI_MIN_S:
            return False
        if s.owner != self.last_model_owner:
            return True
        return s.lost.get(s.side, 0) - self.last_model_lost >= 4

    def model_orders(self, pic, s: Situation, image: Path):
        text = self.prompt_text(pic, s)
        t0 = time.time()
        ans = ask_model(self.llm, image, text)
        secs = round(time.time() - t0, 1)
        return ans, text, secs

    def prompt_text(self, pic, s: Situation):
        g = self.p.g
        lines = [f"Game time {s.t // 60}:{s.t % 60:02d}. You command the {s.side} side. Farm is held by: "
                 f"{'you' if s.owner == s.side else ('the enemy' if s.owner not in ('FIA', '') else 'nobody (neutral)')}.",
                 f"Your losses so far: {s.lost.get(s.side, 0)} soldiers; enemy losses: {s.lost.get(s.enemy, 0)}.",
                 f"Enemies your soldiers saw in the last minute: {sum(1 for _ in s.known)} "
                 f"(in {len(pic['known'])} groups, red X on the map) - the enemy may also be where you have not looked.",
                 f"Your HQ: {'%.0f m' % math.hypot(pic['hq'][0] - g.ox, pic['hq'][1] - g.oz) if pic['hq'] else '?'} from Farm.", "",
                 "Your attack teams (id, men, where):"]
        for tm in sorted(pic["teams"], key=lambda t: t["id"]):
            st = pic["status"][tm["id"]]
            d = math.hypot(tm["x"] - g.ox, tm["z"] - g.oz)
            where = {"at_farm": "fighting at Farm", "riding": "in a vehicle", "at_hq": "at the HQ, about to ride",
                     "on_foot": "on foot"}[st]
            start = self.start_of(pic, tm)
            o = self.orders.get(tm["id"])
            prev = ""
            if o:
                sp = self.match_support(pic, o.get("support_xz")) if o.get("order") == "support" else None
                prev = f"; current order: route {start}-{o.get('route')}, {o.get('order')}" + (f" at {sp['id']}" if sp else "")
                if o.get("order") == "wait" and tm["id"] in self.wait_since:
                    waited = s.t - self.wait_since[tm["id"]]
                    if s.t - self.released.get(tm["id"], -1e9) < RELEASED_S:
                        prev += f" (it waited {waited // 60} min, so it is going on now whatever you say)"
                    elif waited >= 60:
                        prev += f" (waiting {waited // 60} min so far; at {WAIT_MAX_S // 60} min it goes on)"
            lines.append(f"  T{tm['id']}: {tm['men']} men, {where}, {round(d)} m from Farm" + (f", routes from {start}" if start and st != "at_farm" else "") + prev)
        zones = pic.get("zones") or []
        if zones:
            lines += ["", f"Danger zones - where your side lost soldiers or vehicles in the last {DANGER_S // 60} minutes (drones, mines, "
                      "fire; the enemy is likely still watching them). A risk to weigh, not a wall: the routes listed go round them when "
                      "that costs little, and through them when it's the way in - then fast and in cover:"]
            for zn in zones:
                lines.append(f"  {zn['id']}: {zn['from_obj_m']} m {zn['dir']} of Farm - {zn['men']} soldiers and {zn['vehicles']} vehicles lost, "
                             f"the last {zn['newest_s'] // 60} min {zn['newest_s'] % 60:02d} s ago")
        if pic.get("sites"):
            lines += ["", "Enemy drone sites you have located (their FPV operators - each launches a drone about every 30 s):"]
            for sp_ in pic["sites"]:
                lines.append(f"  {sp_['id']}: {sp_['from_obj_m']} m {sp_['dir']} of Farm ({sp_['name']})")
        lines += ["", "Drop points (where a vehicle lets a team out; all hidden from the enemies you know and from Farm):"]
        for d in pic["drops"]:
            lines.append(f"  {d['id']}: {d['from_obj_m']} m {d['dir']} of Farm, drive {d['drive_m']} m from the HQ, "
                         f"{d['drive_seen_pts']} road points of the drive in known enemies' view"
                         + (f", IN DANGER ZONE {', '.join(d['zones'])}" if d.get("zones") else ""))
        lines += ["", "Routes into Farm (L/C/R from each start), each as its chain of cover - the buildings and tree lines a team "
                  "bounds between, the open stretches it must cross - then its numbers:"]
        for rid, r in sorted(pic["routes"].items()):
            lines.append(f"  {rid}: {r.get('chain', '?')}; {r['length_m']} m ({r['minutes']} min on foot), longest open stretch "
                         f"{r.get('open_max_m', '?')} m, in known enemies' view {r['known_enemy_view_pct']}%, in Farm's view "
                         f"{r['farm_view_pct']}%, cover within 40 m {r['cover_in_reach_pct']}%, cost {r['cost']}"
                         + (f", THROUGH DANGER ZONE {', '.join(r['zones'])}" if r.get("zones") else ""))
        if pic["support"]:
            lines += ["", "Support positions (see Farm, in reach of cover):"]
            for sp in pic["support"]:
                lines.append(f"  {sp['id']}: {sp['from_obj_m']} m from Farm, {sp['height_over_obj_m']} m above it, sees it from "
                             f"{sp['sees']}/9 eye points, {'in cover' if sp['cover'] else 'open'}")
        drones = ""
        if self.drones_on:
            dp = s.droneplan or {}
            why = re.sub(r"\(.*?\)|commander", "", str(dp.get("why", ""))).strip() or "quiet"
            cur = (f"you have {dp.get('have')} drone operator teams; from the situation ({why}) the drone rule would keep "
                   f"{dp.get('rule')}" if dp else "no drone plan logged yet")
            mine = f" Your last order: {self.drones['teams']} teams at {self.drones['target']}." if self.drones else ""
            lines += ["", f"FPV drones: {cur}.{mine} Each operator team flies one FPV drone at a time, a launch about every "
                      "30 s in a fight (2-man teams at drone trucks behind the front, apart from your attack teams); drones "
                      "strike enemies near their target and spot enemies for you (the red X's). Decide how many operator teams "
                      "(1-6) and their target: farm (enemies at and around Farm - mind your own teams going in there), "
                      "enemy_hq (the enemy's main base and what leaves it) or none (they only defend your teams and scout)."]
            drones = ', "drones": {"teams": 1-6, "target": "farm"|"enemy_hq"|"none", "why": "few words"}'
        lines += ["", "How to win (modern infantry against drones): plan an axis of attack through cover - take the buildings "
                  "nearest Farm first, from there the closest tree line, then Farm itself; teams move fast from cover to cover "
                  "and never stop in the open (a team lying in a field is what an FPV kills) - they stop ~15 s in cover at each tree "
                  "line's edge and go into the buildings on their way; choose routes with short open "
                  "stretches; put several teams on one or two axes rather than one team everywhere; 'wait' only to gather "
                  "teams in cover for a joint push; weigh the danger zones - where you just lost men or vehicles the next team may "
                  "die the same way, so take another drop point or route when one is about as good, but don't give up the attack "
                  "for them: sometimes the way in runs through a killzone, then go through it fast, in cover, with several teams."]
        if pic.get("armour"):
            kinds = {"LAV25": "LAV-25 APC (25 mm autocannon and MG)", "BTR70": "BTR-70 APC (14.5 mm HMG and MG)",
                     "M2A2": "M2A2 Bradley IFV", "BMP": "BMP IFV", "M1A1": "M1A1 tank", "T72": "T-72 tank"}
            doing = {"APPROACH": "moving up", "ASSAULT": "attacking at Farm", "OVERWATCH": "on overwatch", "HOLD": "holding",
                     "RECREW": "back for a new crew", "REMOUNT": "crew boarding", "GIVEWAY": "giving way"}
            lines += ["", "Your fighting vehicles (crewed, they fight from the vehicle; strong against infantry in the open and light "
                      "vehicles at 200-800 m, weak against drones and AT rockets up close - an APC driven into Farm gets lost, one "
                      "watching from cover 200-400 m out keeps the enemy's heads down while your infantry goes in):"]
            for a_ in pic["armour"]:
                kind = next((v for k, v in kinds.items() if k in a_["prefab"]), a_["prefab"])
                lines.append(f"  A{a_['unit']}: {kind}, {round(math.hypot(a_['x'] - g.ox, a_['z'] - g.oz))} m "
                             f"{compass(math.degrees(math.atan2(a_['x'] - g.ox, a_['z'] - g.oz)))} of Farm, health {a_['health']}%, "
                             f"now {doing.get(a_['phase'], a_['phase'].lower() or 'waiting for orders')}")
        lines += ["", "Your strategy - think about the battle, not only the next move, and choose one: 'assault' (take Farm), "
                  "'fortify' (you hold Farm and your men there die in the open: your builders put bunkers and guard towers "
                  "there first), 'counter_drone' (enemy drones are killing your men: twice as many of your soldiers fire at "
                  "drones, out to 180 m, and every one of your FPVs goes for the enemy drone sites you have located). Besides, any team may 'raid' a located enemy drone site (H1..: route there, fight the "
                  "operators up to 2.5 min, then on to Farm) - if drones kill your attackers, killing their operators is "
                  "often the way in."]
        if pic.get("forts"):
            lines += ["", "Field positions where your builders can put a bunker or guard tower outside any base - they walk out from "
                      "your nearest base (up to 1.2 km, so a far one takes 10-15 minutes) and build it; it is cover your men can fight from (drones and fire "
                      "kill men in the open). Pick up to 3, or none:"]
            for f in pic["forts"]:
                lines.append(f"  {f['id']}: {f['from_obj_m']} m {f['dir']} of Farm, facing {compass(f['facing'])}, a {f['role']} position"
                             f", cover {f['cover_m']} m away" + (f", sees Farm from {f['sees']}/9 eye points" if f['role'] != "hold" else ""))
            built = getattr(s, "field_built", [])
            if built:
                lines.append(f"  Built so far: {len(built)} - " + ", ".join(
                    f"{round(math.hypot(x - g.ox, z - g.oz))} m {compass(math.degrees(math.atan2(x - g.ox, z - g.oz)))} of Farm"
                    for x, z in built[-6:]) + " (your men can fight from them).")
            if self.forts:
                lines.append("  Already ordered: " + ", ".join(f"{round(math.hypot(f['x'] - g.ox, f['z'] - g.oz))} m "
                                                             f"{compass(math.degrees(math.atan2(f['x'] - g.ox, f['z'] - g.oz)))} of Farm"
                                                             for f in self.forts) + " (they stay ordered unless you pick others).")
        raid = ', "site": "H1" or null' if pic.get("sites") else ""
        armour = (', "armour": [{"unit": <A number>, "order": "overwatch"|"assault"|"hold", "support": "P1" or null (for '
                  'overwatch: the support position it fires from), "why": "few words"}]') if pic.get("armour") and pic.get("support") else ""
        lines += ["", 'Answer JSON only: {"reason": "one line: your plan", "strategy": {"stance": "assault"|"fortify"|"counter_drone", '
                  '"why": "few words"}, "teams": [{"team": <id>, "drop": "D1" or null, '
                  '"route": "<start>-L|C|R", "order": "go"|"wait"|"support"' + ('|"raid"' if raid else '') + ', "support": "P1" or null'
                  + raid + ', "why": "few words"}]'
                  + drones + armour + (', "forts": ["F1", ...] (up to 3 field positions to fortify, [] for none)' if pic.get("forts") else "")
                  + "} - one entry per team above that is not fighting at Farm. drop: only for teams at the HQ (a team "
                  "in a vehicle keeps its drop point). route: one of the routes listed from the team's start (for a team at the "
                  "HQ, from the drop point you give it)."]
        return "\n".join(lines)

    def validate(self, ans, pic):
        """The model's orders team by team; anything invalid -> the code's pick for that team. (orders, problems)"""
        code = self.code_orders(pic)
        out, problems = {}, []
        given = {}
        for e in (ans or {}).get("teams", []) if isinstance(ans, dict) else []:
            try:
                tid = int(str(e.get("team", "")).lstrip("Tt"))
            except ValueError:
                problems.append(f"bad team {e.get('team')!r}")
                continue
            given[tid] = e
        drop_by = {d["id"]: d for d in pic["drops"]}
        sup_by = {p_["id"]: p_ for p_ in pic["support"]}
        for tm in pic["teams"]:
            tid = tm["id"]
            st = pic["status"][tid]
            if st == "at_farm":
                continue
            e = given.get(tid)
            if e is None:
                prev = self.orders.get(tid)
                out[tid] = dict(prev) if prev else code.get(tid, {"order": "go", "route": "C"})
                out[tid]["source"] = "kept" if prev else "code"
                continue
            o = {"order": str(e.get("order", "go")).lower(), "support_xz": None, "why": str(e.get("why", ""))[:120], "source": "model"}
            if o["order"] not in ("go", "wait", "support", "raid"):
                problems.append(f"T{tid}: order {o['order']!r}")
                o["order"] = "go"
            if st == "at_hq":
                drop = drop_by.get(str(e.get("drop")))
                if drop is None:
                    problems.append(f"T{tid}: drop {e.get('drop')!r}")
                    drop = self.match_drop(pic, code.get(tid, {}).get("drop_xz")) or (pic["drops"][0] if pic["drops"] else None)
                o["drop_xz"] = (drop["x"], drop["z"]) if drop else None
                start = drop["id"] if drop else None
            else:
                o["drop_xz"] = self.orders.get(tid, {}).get("drop_xz")
                start = self.start_of(pic, tm)
            route = str(e.get("route") or "")
            side_ = route.rsplit("-", 1)[-1].upper() if route else ""
            if f"{start}-{side_}" not in pic["routes"]:
                problems.append(f"T{tid}: route {route!r} not from {start}")
                side_ = code.get(tid, {}).get("route", "C")
                o["source"] = "model+code_route"
            o["route"] = side_
            if o["order"] == "raid":
                site = {sp_["id"]: sp_ for sp_ in pic.get("sites") or []}.get(str(e.get("site")))
                if site is None:
                    problems.append(f"T{tid}: raid site {e.get('site')!r}")
                    o["order"] = "go"
                else:
                    o["site_xz"] = (site["x"], site["z"])
            if o["order"] == "support":
                sp = sup_by.get(str(e.get("support")))
                if sp is None:
                    problems.append(f"T{tid}: support {e.get('support')!r}")
                    o["order"] = "go"
                else:
                    o["support_xz"] = (sp["x"], sp["z"])
            out[tid] = o
        if isinstance(ans, dict) and isinstance(ans.get("armour"), list):
            units = {a_["unit"]: a_ for a_ in pic.get("armour") or []}
            for e in ans["armour"]:
                try:
                    unit = int(str(e.get("unit", "")).lstrip("Aa"))
                except (ValueError, AttributeError):
                    problems.append(f"armour unit {e!r}")
                    continue
                order = str(e.get("order", "")).lower()
                if unit not in units or order not in ("overwatch", "assault", "hold"):
                    problems.append(f"armour A{unit}: {order!r}")
                    continue
                xz = (self.p.g.ox, self.p.g.oz)
                if order == "overwatch":
                    sp = sup_by.get(str(e.get("support")))
                    if sp is None:
                        problems.append(f"armour A{unit}: support {e.get('support')!r}")
                        continue
                    xz = (sp["x"], sp["z"])
                self.armour_orders[unit] = {"order": order, "xz": xz, "why": str(e.get("why", ""))[:120]}
        if isinstance(ans, dict) and isinstance(ans.get("forts"), list) and pic.get("forts") is not None:
            by_id = {f["id"]: f for f in pic.get("forts") or []}
            chosen = []
            for fid in ans["forts"][:3]:
                f = by_id.get(str(fid).strip().upper())
                if not f:
                    problems.append(f"fort {fid!r}")
                    continue
                # The same place as one ordered before (within 30 m): its spot as given then, so the game keeps its tries.
                same = next((o for o in self.forts if math.hypot(o["x"] - f["x"], o["z"] - f["z"]) <= 30), None)
                chosen.append(same or {"x": f["x"], "z": f["z"], "facing": f["facing"], "t": pic["t"]})
            if chosen or ans["forts"] == []:
                self.forts = chosen
        if isinstance(ans, dict) and isinstance(ans.get("strategy"), dict):
            stance = str(ans["strategy"].get("stance", "")).lower()
            if stance in STANCES:
                self.strategy = {"stance": stance, "why": str(ans["strategy"].get("why", ""))[:120]}
            else:
                problems.append(f"strategy {stance!r}")
        if self.drones_on and isinstance(ans, dict):
            d = ans.get("drones")
            try:
                teams = int((d or {}).get("teams"))
                target = str((d or {}).get("target", "farm")).lower()
                if not 1 <= teams <= 6:
                    raise ValueError(f"teams {teams}")
                if target not in ("farm", "enemy_hq", "none"):
                    problems.append(f"drones target {target!r}")
                    target = "farm"
                self.drones = {"teams": teams, "target": target, "why": str((d or {}).get("why", ""))[:120]}
            except (TypeError, ValueError, AttributeError) as e:
                problems.append(f"drones {d!r}: {e}")
        return out, problems

    # -- the file -----------------------------------------------------------------------------------------------------
    def entries(self, pic):
        """Per team: (drop xz or None, route info, go, hold xz, hold_s)."""
        g = self.p.g
        out = {}
        for tm in pic["teams"]:
            tid = tm["id"]
            st = pic["status"][tid]
            if st == "at_farm" or tid not in self.orders:
                continue
            o = self.orders[tid]
            drop_xz = None
            if st == "riding" and tid in self.frozen_drop:
                drop_xz = self.frozen_drop[tid]
            elif st in ("at_hq", "riding"):
                d = self.match_drop(pic, o.get("drop_xz")) or (pic["drops"][0] if pic["drops"] else None)
                if d:
                    drop_xz = (d["x"], d["z"])
                    if st == "riding":
                        self.frozen_drop[tid] = drop_xz
            if st == "on_foot":
                self.frozen_drop.pop(tid, None)
            start = self.start_of(pic, tm)
            if start is None:
                continue
            route = pic["routes"].get(f"{start}-{o.get('route', 'C')}") or pic["routes"].get(f"{start}-C")
            if route is None:
                continue
            go, hold, hold_s = 1, route["hold"], 0
            if o.get("order") == "wait":
                since = self.wait_since.setdefault(tid, pic["t"])
                last = self.released.get(tid, -1e9)
                if pic["t"] - last < RELEASED_S:
                    pass
                elif pic["t"] - since >= WAIT_MAX_S:
                    self.released[tid] = pic["t"]
                    self.log(f"t={pic['t']} {self.side} T{tid} waited {pic['t'] - since} s - goes on")
                else:
                    go, hold_s = 0, WAIT_S
            else:
                self.wait_since.pop(tid, None)
            if o.get("order") == "raid" and o.get("site_xz"):
                cell = g.nearest_valid(o["site_xz"][0], o["site_xz"][1], 40, avoid_building=True)
                if cell is not None:
                    from_xz = drop_xz if (st in ("at_hq", "riding") and drop_xz) else (tm["x"], tm["z"])
                    via = self.p.route_via(f"{start}-H", from_xz, cell, pic["costs"], pic["D_obj"], pic["threat"])
                    if via:
                        route, go, hold, hold_s = via, 0, via["hold"], RAID_S
            elif o.get("order") == "support" and o.get("support_xz"):
                sp = self.match_support(pic, o["support_xz"])
                cell = sp["cell"] if sp else g.nearest_valid(o["support_xz"][0], o["support_xz"][1], 30, avoid_building=True)
                if cell is not None:
                    from_xz = drop_xz if (st in ("at_hq", "riding") and drop_xz) else (tm["x"], tm["z"])
                    via = self.p.route_via(f"{start}-{sp['id'] if sp else 'P'}", from_xz, cell, pic["costs"], pic["D_obj"], pic["threat"])
                    if via:
                        route, go, hold, hold_s = via, 0, via["hold"], SUPPORT_S
            # The hold point stays put while the team's wait (or support) stands (3 Nov, note 515): its route is redrawn
            # from where it stands every 30 s, and the hold point moved with it - the team never got there, 0 holds in 8
            # battles. A new spot only when the order changes or the new one is 250 m+ away.
            if go:
                self.frozen_hold.pop(tid, None)
            else:
                prev = self.frozen_hold.get(tid)
                if prev and prev[0] == o.get("order") and math.hypot(prev[1][0] - hold[0], prev[1][1] - hold[1]) < 250:
                    hold = prev[1]
                else:
                    self.frozen_hold[tid] = (o.get("order"), tuple(hold))
            out[tid] = {"drop": drop_xz, "route": route, "go": go, "hold": list(hold), "hold_s": hold_s}
        return out

    def write(self, pic, entries, profile_zcr: Path):
        g = self.p.g
        lines = []
        if self.strategy:
            lines.append(f"strategy {self.side} {self.strategy['stance']}")
        for f in self.forts:
            lines.append(f"fort {self.side} {f['x']:.1f} {f['z']:.1f} {f['facing']:.0f}")
        alive = {a_["unit"] for a_ in pic.get("armour") or []}
        for unit, o in sorted(self.armour_orders.items()):
            if unit in alive:
                lines.append(f"armour {self.side} {unit} {o['order']} {o['xz'][0]:.1f} {o['xz'][1]:.1f}")
        if self.drones_on and self.drones:
            nodes = pic.get("nodes") or {}
            node = {"farm": nodes.get(OBJECTIVE, -1), "enemy_hq": nodes.get("enemy_hq", -1)}.get(self.drones["target"], -1)
            lines.append(f"drones {self.side} {self.drones['teams']} {node}")
        for tid, e in sorted(entries.items()):
            wps = e["route"]["waypoints"]
            dx, dz = e["drop"] if e["drop"] else (0, 0)
            lines.append(f"team {self.side} {tid} {g.ox:.1f} {g.oz:.1f} {dx:.1f} {dz:.1f} {e['go']} {e['hold'][0]:.1f} {e['hold'][1]:.1f} "
                         f"{e['hold_s']} {e['route']['id']} {len(wps)}")
            # Each point's action (note 540): a short stop in cover at a tree line's edge (c), the men into the buildings (e),
            # else on (m) - AICF_ZcrPlanLane.m_aActions.
            kinds = e["route"].get("wp_kinds") or []
            acts = [POINT_ACTION.get(kinds[k] if k < len(kinds) else "", "m") for k in range(len(wps))]
            lines += [f"{x:.1f} {z:.1f} {a_}" for (x, z), a_ in zip(wps, acts)]
        self.lines = lines
        if self.sink:   # both sides planned (3 Nov, --side both): one file with both generals' orders
            self.sink(profile_zcr)
            return
        self.version += 1
        write_live(profile_zcr, [f"version {self.version}"] + lines + ["end"], self.log)

    # -- one round ------------------------------------------------------------------------------------------------------
    def round(self, s: Situation, profile_zcr: Path, write=True):
        pic = self.picture(s)
        entry = {"t": s.t, "side": s.side, "owner": s.owner, "lost": s.lost, "known": len(s.known), "known_groups": len(pic["known"]),
                 "teams": {tm["id"]: pic["status"][tm["id"]] for tm in pic["teams"]}, "drops": [{k: v for k, v in d.items() if k != "cell"} for d in pic["drops"]],
                 "routes": {rid: {k: v for k, v in r.items() if k not in ("cells", "pts")} for rid, r in pic["routes"].items()},
                 "support": [{k: v for k, v in p_.items() if k != "cell"} for p_ in pic["support"]], "picture_s": pic["seconds"],
                 "zones": pic.get("zones") or []}
        # New teams and the code arm: the code's pick; the model when due.
        fresh = {tm["id"] for tm in pic["teams"] if tm["id"] not in self.orders and pic["status"][tm["id"]] != "at_farm"}
        if self.picker == "code":
            self.orders.update(self.code_orders(pic))
            entry["source"] = "code"
        else:
            if fresh:
                self.orders.update(self.code_orders(pic, only=fresh))
            if self.want_model(s) and any(pic["status"][tm["id"]] != "at_farm" for tm in pic["teams"]):
                image = profile_zcr / "liveplan" / f"t{s.t:05d}.jpg"
                image.parent.mkdir(parents=True, exist_ok=True)
                draw(self.p, pic, s).save(image, quality=85)
                self.last_model_t, self.last_model_owner, self.last_model_lost = s.t, s.owner, s.lost.get(s.side, 0)
                self.model_calls += 1
                try:
                    ans, text, secs = self.model_orders(pic, s, image)
                    orders, problems = self.validate(ans, pic)
                    self.orders.update(orders)
                    entry.update(source="gemini", reason=ans.get("reason"), answer=ans, problems=problems, model_s=secs, prompt=text,
                                 image=str(image.name))
                    stance = f" [strategy: {self.strategy['stance']}]" if self.strategy else ""
                    self.log(f"t={s.t} {s.side} gemini ({secs} s, {len(problems)} problems): {ans.get('reason')}{stance}")
                except Exception as e:   # the model failed: the code's pick for every team
                    self.orders.update(self.code_orders(pic))
                    entry.update(source="code-fallback", error=f"{type(e).__name__}: {e}")
                    self.log(f"t={s.t} {s.side} model failed ({type(e).__name__}: {e}) - the code's pick")
            else:
                entry["source"] = "kept"
        entries = self.entries(pic)
        if self.drones_on:
            entry["drones"] = self.drones
            entry["droneplan"] = s.droneplan
        entry["strategy"] = self.strategy
        entry["armour"] = {"units": pic.get("armour") or [], "orders": {str(k): v for k, v in self.armour_orders.items()}}
        entry["sites"] = [{k: v for k, v in sp_.items() if k != "cell"} for sp_ in pic.get("sites") or []]
        entry["orders"] = {tid: {k: v for k, v in o.items()} for tid, o in self.orders.items() if tid in entries}
        entry["field_spots"] = pic.get("forts") or []
        entry["forts"] = [dict(f) for f in self.forts]
        entry["entries"] = {tid: {"route": e["route"]["id"], "go": e["go"], "drop": e["drop"], "hold": e["hold"], "hold_s": e["hold_s"],
                                  "waypoints": e["route"]["waypoints"], "wp_kinds": e["route"].get("wp_kinds"),
                                  "chain": e["route"].get("chain")} for tid, e in entries.items()}
        if write:
            self.write(pic, entries, profile_zcr)
            entry["version"] = self.version
        with open(profile_zcr / "liveplan.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry


# -- the image -------------------------------------------------------------------------------------------------------
_BASE = {}


def draw(p: Planner, pic, s: Situation, half=1050, px_out=1200):
    import mapimage
    g = p.g
    key = (g.ox, g.oz, half)
    if key not in _BASE:
        base, mpp, world = mapimage.base_map("arland", "topo", 4)
        x0, x1, z0, z1 = g.ox - half, g.ox + half, g.oz - half, g.oz + half
        crop = base.crop((int(x0 / mpp), int((world - z1) / mpp), int(x1 / mpp), int((world - z0) / mpp))).convert("RGBA")
        _BASE[key] = (crop, mpp, x0, z1)
    crop, mpp, x0, z1 = _BASE[key]
    W = crop.size[0]
    sc = px_out / W
    img = crop.resize((px_out, int(crop.size[1] * sc)))
    px = lambda x, z: ((x - x0) / mpp * sc, (z1 - z) / mpp * sc)
    # Threat (red) and cover (green) at grid resolution, then scaled onto the map.
    rgba = np.zeros((g.nz, g.nx, 4), np.uint8)
    thr = pic["threat"].T[::-1]
    cov = g.covered.T[::-1]
    rgba[cov] = (40, 150, 60, 70)
    m = thr > 0.05
    a = np.clip(60 + 60 * thr, 0, 210).astype(np.uint8)
    rgba[m, 0], rgba[m, 1], rgba[m, 2], rgba[m, 3] = 220, 30, 30, a[m]
    ov = Image.fromarray(rgba, "RGBA")
    gx0, gz1 = g.x0 - g.step / 2, g.z0 + (g.nz - 0.5) * g.step
    left, top = px(gx0, gz1)
    ov = ov.resize((max(1, int(g.nx * g.step / mpp * sc)), max(1, int(g.nz * g.step / mpp * sc))), Image.NEAREST)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.paste(ov, (int(left), int(top)))
    img = Image.alpha_composite(img, layer)
    d = ImageDraw.Draw(img)
    f_s, f_m, f_b = mapimage.font(13), mapimage.font(15, True), mapimage.font(20, True)
    for zn in pic.get("zones") or []:
        zx, zy = px(zn["x"], zn["z"])
        rr = DANGER_R_M / mpp * sc
        d.ellipse([zx - rr, zy - rr, zx + rr, zy + rr], outline=(200, 0, 0), width=4)
        d.text((zx + rr + 3, zy - 9), f"{zn['id']} danger: {zn['men']} men, {zn['vehicles']} veh lost", fill=(160, 0, 0), font=f_m)
    palette = [(25, 110, 220), (230, 120, 20), (140, 60, 190), (0, 150, 150), (200, 30, 120), (120, 90, 30), (60, 60, 60)]
    starts = sorted({rid.rsplit("-", 1)[0] for rid in pic["routes"]})
    for k, st in enumerate(starts):
        col = palette[k % len(palette)]
        for rid, r in pic["routes"].items():
            if rid.rsplit("-", 1)[0] != st:
                continue
            pts = [px(x, z) for x, z in r["waypoints"]]
            if len(pts) >= 2:
                d.line(pts, fill=col + (230,), width=3)
                lx, ly = pts[min(len(pts) - 1, max(1, len(pts) // 3))]
                d.text((lx + 3, ly - 8), rid, fill=col + (255,), font=f_s, stroke_width=2, stroke_fill=(255, 255, 255, 255))
            hx, hy = px(*r["hold"])
            d.line([(hx - 5, hy), (hx + 5, hy)], fill=(20, 20, 20, 255), width=3)
    for dp in pic["drops"]:
        x, y = px(dp["x"], dp["z"])
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(255, 255, 255, 230), outline=(20, 20, 20, 255), width=2)
        d.text((x + 10, y - 10), dp["id"], fill=(20, 20, 20, 255), font=f_m, stroke_width=2, stroke_fill=(255, 255, 255, 255))
    for sp in pic["support"]:
        x, y = px(sp["x"], sp["z"])
        d.polygon([(x, y - 9), (x - 8, y + 6), (x + 8, y + 6)], fill=(20, 120, 40, 255), outline=(255, 255, 255, 255))
        d.text((x + 9, y - 8), sp["id"], fill=(20, 120, 40, 255), font=f_m, stroke_width=2, stroke_fill=(255, 255, 255, 255))
    for ox, oz, w in pic["known"]:
        x, y = px(ox, oz)
        r = 5 + 2 * w
        d.line([(x - r, y - r), (x + r, y + r)], fill=(180, 0, 0, 255), width=3)
        d.line([(x - r, y + r), (x + r, y - r)], fill=(180, 0, 0, 255), width=3)
    for tm in pic["teams"]:
        x, y = px(tm["x"], tm["z"])
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(30, 80, 220, 255), outline=(255, 255, 255, 255), width=2)
        d.text((x + 8, y + 2), f"T{tm['id']}", fill=(30, 60, 200, 255), font=f_s, stroke_width=2, stroke_fill=(255, 255, 255, 255))
    ox_, oy_ = px(g.ox, g.oz)
    star = [(ox_ + 16 * math.cos(math.pi / 2 + i * math.pi / 5) * (1 if i % 2 == 0 else 0.45),
             oy_ - 16 * math.sin(math.pi / 2 + i * math.pi / 5) * (1 if i % 2 == 0 else 0.45)) for i in range(10)]
    d.polygon(star, fill=(200, 20, 20, 255), outline=(255, 255, 255, 255))
    d.text((ox_ + 18, oy_ - 12), "FARM", fill=(150, 0, 0, 255), font=f_b, stroke_width=2, stroke_fill=(255, 255, 255, 255))
    if pic["hq"]:
        hx, hy = px(*pic["hq"])
        hx, hy = min(max(hx, 12), img.size[0] - 12), min(max(hy, 12), img.size[1] - 12)
        d.rectangle([hx - 9, hy - 9, hx + 9, hy + 9], fill=(20, 20, 20, 255))
        d.text((hx + 12, hy - 10), "YOUR HQ", fill=(20, 20, 20, 255), font=f_m, stroke_width=2, stroke_fill=(255, 255, 255, 255))
    legend = ("red: ground the enemies you know see (darker = more, nearer)   green: roof, canopy or dense trees   red X: known enemies   "
              "blue: your teams   circles D: drop points   lines: routes (bar = hold point)   triangles P: support positions")
    d.rectangle([0, 0, img.size[0], 22], fill=(255, 255, 255, 220))
    d.text((6, 4), legend, fill=(30, 30, 30, 255), font=f_s)
    d.text((6, img.size[1] - 18), f"t={s.t}s  side={s.side}  map: Enfumap (enfumap.com)", fill=(0, 0, 0, 200), font=f_s)
    return img.convert("RGB")


SYSTEM = ("You are the battle commander of one side in an Arma Reforger match (a military game). Your infantry teams attack "
          "one objective, Farm; the enemy attacks it too. Code has read the map and computed your options exactly: drop points "
          "where vehicles let teams out (hidden from the enemies you know), and from each start 2-3 routes into Farm - C the "
          "cheapest through cover and away from known enemies' sight, L and R flanking ones. You decide, per team: the drop "
          "point (teams at the HQ only), the route, and the order: 'go' (along the route into Farm), 'wait' (along the route to "
          "its hold point ~180 m out, wait there up to 3 minutes - to gather teams for a joint assault, or while the way is "
          "watched) or 'support' (go to a support position P1/P2 with a view of Farm and fire from there up to 8 minutes, then "
          "in). Think like a platoon commander: approach unseen through cover, avoid ground the enemy watches, do not feed "
          "teams in one by one into a defended objective, flank, use support fire, keep the momentum when the enemy is weak. "
          "The enemies shown are only those your soldiers saw in the last minute. Answer with JSON only.")


def named(text: str) -> str:
    """The prompt's 'Farm' as the battle's objective (--objective)."""
    return text if OBJECTIVE == "Farm" else text.replace("Farm", OBJECTIVE.replace("_", " "))


# The cost (5 Nov - Martin: "shit we spent 11 euros ?!?! on gemini calls?", "some optimization would be nice"): 1,423 calls that
# day, $12.52 - 0.88 cents a call: 4,832 tokens in (0.36 c - the 1200 px map about half of it) and 1,403 out (0.52 c), 913 of them
# the model's hidden thinking (0.34 c). The map goes at IMAGE_PX (one image tile) and the thinking at REASONING (OpenRouter's
# reasoning effort; LIVEPLAN_REASONING=default leaves the model's own, LIVEPLAN_IMAGE_PX=1200 the old size). Each call's tokens and
# cost stay in liveplan.jsonl (answer._usage).
IMAGE_PX = int(os.environ.get("LIVEPLAN_IMAGE_PX", "768"))
REASONING = os.environ.get("LIVEPLAN_REASONING", "low")


def ask_model(llm, image: Path, text: str) -> dict:
    import providers
    img = Image.open(image).convert("RGB")
    if max(img.size) > IMAGE_PX:
        img.thumbnail((IMAGE_PX, IMAGE_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    body = {"model": llm.model, "temperature": 0.3, "max_tokens": 4000, "response_format": {"type": "json_object"},
            "usage": {"include": True},
            "messages": [{"role": "system", "content": named(SYSTEM)},
                         {"role": "user", "content": [{"type": "text", "text": named(text)},
                                                      {"type": "image_url", "image_url": {"url": url}}]}]}
    if REASONING and REASONING != "default":
        body["reasoning"] = {"effort": REASONING}
    r = providers._post("https://openrouter.ai/api/v1/chat/completions", body,
                        {"authorization": f"Bearer {llm.key}", "x-title": "Zeus Commander Reforger"}, 60)
    if "error" in r:
        raise RuntimeError(f"openrouter: {r['error']}")
    content = r["choices"][0]["message"].get("content") or ""
    out = providers.extract_json(content)
    out["_usage"] = r.get("usage")
    return out


def make_llm():
    import providers
    cfg = json.loads((HERE / "bridge.local.json").read_text(encoding="utf-8"))
    return providers.OpenRouter(cfg)


def write_live(profile_zcr: Path, lines, log=print):
    """$profile:zcr/liveplan.txt, replaced whole (the game reads it when its version line changes)."""
    profile_zcr.mkdir(parents=True, exist_ok=True)
    tmp = profile_zcr / "liveplan.tmp"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for _ in range(20):
        try:
            os.replace(tmp, profile_zcr / "liveplan.txt")
            return
        except PermissionError:
            time.sleep(0.1)
    log("could not replace liveplan.txt (the game held it)")


def situation(reader: LogReader, side: str, hqs: dict, known_from_live=False) -> Situation:
    s = Situation()
    s.t = reader.t
    s.side = side
    s.enemy = "USSR" if side == "US" else "US"
    s.hq = hqs
    s.owner = reader.owner
    s.teams = reader.teams(side)
    s.known = list(reader.known.get(side, []))
    if known_from_live and not s.known:
        # Offline tests on runs from before [ZCR][KNOWN]: the enemy teams within 400 m of one of ours (not what it knew).
        mine = s.teams
        for e in reader.teams(s.enemy):
            if e["men"] > 0 and any(math.hypot(e["x"] - m["x"], e["z"] - m["z"]) <= 400 for m in mine):
                s.known += [(e["x"], e["z"])] * min(e["men"], 3)
    s.lost = dict(reader.lost)
    s.own_losses = [(lt, k, x, z) for lt, sd, k, x, z in reader.losses if sd == side and reader.t - lt <= DANGER_S]
    s.sites = [(reader.sites[k][1], reader.sites[k][2], reader.sites[k][3]) for k in sorted(reader.located.get(side, ()))]
    s.armour = sorted(reader.armour.get(side, {}).values(), key=lambda a_: a_["unit"])
    s.field_built = list(reader.field_built.get(side, []))
    s.droneplan = dict(reader.droneplan.get(side, {}))
    s.nodes = base_nodes(reader, side)
    return s


_NODES = {}


def base_nodes(reader: LogReader, side: str) -> dict:
    """Graph node ids of the bases (the commander's snapshot): {"Farm": 2, "enemy_hq": 1, ...}."""
    run_dir = reader.path.parent.parent.parent
    key = (str(run_dir), side)
    if key not in _NODES:
        out = {}
        snap = run_dir / "profile" / "zcr" / "snapshots.jsonl"
        if snap.exists():
            for line in snap.read_text(encoding="utf-8", errors="replace").splitlines()[:1]:
                try:
                    for b_ in json.loads(line).get("bases", []):
                        out[b_["name"]] = b_["id"]
                        if b_.get("hq") and b_.get("owner") in ("US", "USSR") and b_["owner"] != side:
                            out["enemy_hq"] = b_["id"]
                except ValueError:
                    pass
        if OBJECTIVE not in out:
            return out
        _NODES[key] = out
    return _NODES[key]


def resolve_side(spec: str, hqs: dict, planner: Planner) -> str:
    """US / USSR as given; 'harbour' / 'south': the side whose HQ is nearer / farther from Farm (HQs are drawn per match)."""
    if spec in ("US", "USSR"):
        return spec
    g = planner.g
    d = {s: math.hypot(x - g.ox, z - g.oz) for s, (x, z) in hqs.items()}
    if len(d) < 2:
        return ""
    near = min(d, key=d.get)
    far = max(d, key=d.get)
    return near if spec == "harbour" else far


def find_run(label: str, after: float, timeout=600) -> Path:
    t0 = time.time()
    while time.time() - t0 < timeout:
        runs = [r for r in (ROOT / ".runtime" / "runs").glob(f"{label}-*") if r.stat().st_mtime >= after - 5]
        if runs:
            return max(runs, key=lambda r: r.stat().st_mtime)
        time.sleep(2)
    raise SystemExit(f"no run folder {label}-* appeared")


def live(a):
    global OBJECTIVE
    OBJECTIVE = a.objective
    planner = Planner(scan=Path(a.scan) if a.scan else None)
    llm = make_llm() if a.picker == "gemini" else None
    run_dir = Path(a.run) if a.run else find_run(a.label, a.after or time.time())
    zcr = run_dir / "profile" / "zcr"
    zcr.mkdir(parents=True, exist_ok=True)
    logf = open(zcr / "liveplan.log", "a", encoding="utf-8")

    def log(msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    log(f"liveplan for {run_dir.name}: side {a.side}, picker {a.picker}" + (f" ({llm.model})" if llm else ""))
    console = None
    t0 = time.time()
    while console is None:
        logs = sorted(run_dir.glob("logs/*/console.log"))
        if logs:
            console = logs[-1]
        elif time.time() - t0 > 4 * 3600:   # AoE mode (2 Nov): lab/reforger.py may wait its turn for a long time
            log("no console.log - stopping")
            return 1
        else:
            time.sleep(3)
    reader = LogReader(console)
    # 3 Nov night (Martin: "test more like those two sides battle over the farm but general actually uses brain, not
    # hardcoded shit"): --side both - a general for each side, both sides' orders in the one liveplan.txt the game reads.
    cmds = {}           # side -> Commander
    last_round_t = {}   # side -> the game second of its last round
    version = [int(time.time()) % 100000 * 10]

    def sink(zdir):
        version[0] += 1
        lines = [f"version {version[0]}"]
        for c in cmds.values():
            lines += c.lines
        write_live(zdir, lines + ["end"], log)
        for c in cmds.values():
            c.version = version[0]

    last_size, last_growth = -1, time.time()
    while True:
        reader.poll()
        size = console.stat().st_size
        if size != last_size:
            last_size, last_growth = size, time.time()
        elif time.time() - last_growth > 120:
            log("the game's log stopped growing - done")
            break
        if not cmds and reader.t >= 30:
            hqs = hq_positions(run_dir, reader)
            both = a.side == "both"
            # 4 Nov night (Martin: "over night you can test both gemini vs gemini but also gemini vs rule based"): with
            # --rules-side, that side's general picks by the code's rules (the same routes, drops, danger zones), the other
            # by Gemini.
            rules_side = resolve_side(a.rules_side, hqs, planner) if a.rules_side else ""
            for spec in (["US", "USSR"] if both else [a.side]):
                side = resolve_side(spec, hqs, planner)
                if not side or side not in hqs:
                    continue
                picker = "code" if side == rules_side else a.picker
                cmd = Commander(planner, side, picker, zcr, llm, log, a.drones)
                if both:
                    cmd.sink = sink
                cmds[side] = cmd
                g = planner.g
                log(f"plans for {side} by {picker} (HQ {hqs.get(side)}, {math.hypot(hqs[side][0] - g.ox, hqs[side][1] - g.oz):.0f} m from the objective); "
                    + ("both sides planned live" if both else "the other side plays the rules"))
                with open(zcr / "liveplan.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps({"event": "side", "side": side, "spec": a.side, "picker": picker, "hqs": hqs,
                                        "drones": bool(a.drones and a.picker == "gemini"),
                                        "hq_m": round(math.hypot(hqs[side][0] - g.ox, hqs[side][1] - g.oz)),
                                        "model": llm.model if llm else None}) + "\n")
        for side, cmd in cmds.items():
            if reader.t - last_round_t.get(side, -1e9) < ROUND_S or not reader.teams(side):
                continue
            last_round_t[side] = reader.t
            s = situation(reader, side, cmd_hqs(run_dir, reader))
            try:
                e = cmd.round(s, zcr)
                log(f"t={s.t} {side} round: {len(e['entries'])} teams planned, {len(e['routes'])} routes, {len(e['drops'])} drops, "
                    f"{e['known']} known, owner {s.owner}, {e['source']}, picture {e['picture_s']} s")
            except Exception as ex:
                import traceback
                log(f"t={s.t} {side} round failed: {type(ex).__name__}: {ex}\n{traceback.format_exc()}")
        time.sleep(3)
    return 0


_HQS = {}


def cmd_hqs(run_dir, reader):
    if run_dir not in _HQS or len(_HQS[run_dir]) < 2:
        _HQS[run_dir] = hq_positions(run_dir, reader)
    return _HQS[run_dir]


def replay(a):
    """Offline: the picture at game second --t of an old run, the image, the code's (and optionally the model's) pick."""
    global OBJECTIVE
    OBJECTIVE = a.objective
    planner = Planner(scan=Path(a.scan) if a.scan else None)
    run_dir = Path(a.replay)
    console = sorted(run_dir.glob("logs/*/console.log"))[-1]
    reader = LogReader(console)
    reader.poll(until_t=a.t)
    hqs = hq_positions(run_dir, reader)
    side = resolve_side(a.side, hqs, planner)
    out = Path(a.out) if a.out else ROOT / ".runtime" / "liveplan_test"
    out.mkdir(parents=True, exist_ok=True)
    s = situation(reader, side, hqs, a.known_from_live)
    cmd = Commander(planner, side, a.picker, out, make_llm() if a.picker == "gemini" else None, drones=a.drones)
    cmd.last_model_t = -1e9
    t0 = time.time()
    e = cmd.round(s, out)
    print(f"t={s.t} side={side} owner={s.owner} known={len(s.known)} teams={len(s.teams)} in {time.time() - t0:.1f} s "
          f"(picture {e['picture_s']} s); source {e['source']}")
    for d in e["drops"]:
        print("  drop", d)
    for rid, r in sorted(e["routes"].items()):
        print(f"  route {rid}: {r['length_m']} m, view {r['known_enemy_view_pct']}%, farm view {r['farm_view_pct']}%, cover {r['cover_in_reach_pct']}%, cost {r['cost']}")
    for tid, o in sorted(e["entries"].items()):
        print(f"  T{tid} ({e['teams'][tid]}): {o['route']} go={o['go']} drop={o['drop']} hold={o['hold']} ({len(o['waypoints'])} waypoints)")
    for f in (cmd.last or {}).get("forts") or []:
        print("  field spot", f)
    for f in cmd.forts:
        print("  fort ordered", f)
    if e.get("reason"):
        print("  model:", e["reason"], e.get("problems"))
    draw(planner, cmd.last, s).save(out / f"replay_t{s.t}.jpg", quality=85)
    print("written", out / "liveplan.txt", out / f"replay_t{s.t}.jpg")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="", help="the battle's run label (lab/assaulttest.py); the newest run folder with it")
    ap.add_argument("--after", type=float, default=0, help="with --label: a run folder made after this (epoch seconds)")
    ap.add_argument("--run", default="", help="the run folder (instead of --label)")
    ap.add_argument("--side", default="harbour", help="US, USSR, harbour (the side whose HQ is nearer Farm), south, or both (a general for each side)")
    ap.add_argument("--picker", default="code", choices=["code", "gemini"])
    ap.add_argument("--rules-side", default="", help="with --side both: this side (US, USSR, harbour, south) picks by the rules, the other by --picker")
    ap.add_argument("--objective", default="Farm", help="the base fought over (its name as in the log, underscores for spaces)")
    ap.add_argument("--scan", default="", help="its 10 m ground scan (-zcrAttackScan; default .runtime/attack/farm_scan.jsonl)")
    ap.add_argument("--drones", action="store_true", help="with --picker gemini: the model also decides the drone teams and target")
    ap.add_argument("--replay", default="", help="offline: an old run folder")
    ap.add_argument("--t", type=int, default=420, help="with --replay: the game second")
    ap.add_argument("--out", default="", help="with --replay: where to write (default .runtime/liveplan_test)")
    ap.add_argument("--known-from-live", action="store_true", help="with --replay on runs before [ZCR][KNOWN]: enemy teams near ours")
    a = ap.parse_args()
    if a.replay:
        return replay(a)
    return live(a)


if __name__ == "__main__":
    sys.exit(main())
