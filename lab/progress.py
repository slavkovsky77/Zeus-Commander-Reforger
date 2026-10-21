"""How the Reforger commander progresses: measurements per build, read back from every match's server
log and situation reports - like the Arma 3 lab's progress.py.

    python lab/progress.py                 # table per build, writes .runtime/progress.json
    python lab/progress.py --html out.html # the engine page's charts (inline SVG)

A build is a milestone of the doctrine (BUILDS below), assigned to a match by its start time. Each
match is measured from the doctrine side's view - the side whose strategist is ours; the other side
runs on AI Conflict alone. Matches with AI Conflict on both sides are the control.

Per match:
  margin      bases held at the end, doctrine side minus the other
  caps        bases the doctrine side took; first_cap: minutes to its first
  assault     minutes from the doctrine side's assault order on a base to taking it
  storm       minutes from the storm order to taking it
  close6      metres from the objective of the nearest squad sent there, 6 min into the first assault
  exchange    soldiers the doctrine side killed per soldier it lost
  intensity   soldiers lost per 20 game minutes, everyone
  stuck       AI Conflict's stuck reports for the doctrine side's squads per 20 game minutes
  drones      FPV teams, strikes and kills per match (watched matches load the drone mods)
  causes      share of all losses: drone, direct fire (a killer), unknown (no killer)
  walk        Arma 3's "how far the infantry walks": median straight-line distance an attacking
              squad covers on foot to its objective - from where it got out of a vehicle, or from
              where it was when it got the order - of the squads that got within 150 m (from r11)
  rode        Arma 3's "riding to the attack": % of those squads that rode a vehicle (from r11)
  fight_m     engine: median distance of the direct-fire kills, everyone
  fps         engine: the server's median frames per second (logged every minute), and aichar its
              median soldiers simulated
  trips       truck trips AI Conflict started for the doctrine side (motorize, r6)
"""
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = ROOT / ".runtime" / "runs"
sys.path.insert(0, str(HERE))
import metrics  # noqa: E402

# (number, name, live from, what changed) - the changelog page lists the same builds.
BUILDS = [
    (1, "first loop", "2026-10-19 02:40", "Gemini or our rules pick the targets; AI Conflict does the rest"),
    (2, "attack doctrine", "2026-10-19 03:45", "Arma 3's attack doctrine: gather at the nearest base, then assault; an assault that stops gaining is called off"),
    (3, "commit", "2026-10-19 04:52", "two defender squads join the assault; the attacking force counted from AI Conflict's own orders"),
    (4, "storm", "2026-10-19 05:53", "after 4 min of assault the squads go in at a player order's priority"),
    (5, "fixes", "2026-10-19 07:55", "doctrine memory per match (two matches shared it); far objectives no longer 'bled out'"),
    (6, "motorize", "2026-10-19 10:30", "attack squads ride trucks (probes); storm priority as a setting"),
    (7, "soldier measures", "2026-10-19 12:29", "Arma 3's soldier measurements (cover, sitting ducks, stacking); careful storm by default; watch buttons"),
    (8, "drone doctrine", "2026-10-19 13:00", "drone warfare doctrine: prep fire and pressure, both sides fly drones, headless too; force and storm from what the side has seen"),
    (9, "cover layer", "2026-10-19 14:31", "soldier layer: cover in a firefight for our strategist's side (Arma 3's coverFight); drones hunt seen enemy soldiers"),
    (10, "cover with the game", "2026-10-19 15:05", "the soldier layer works with the game's own cover: holds it 20 s (the game: 5 s), asks its cover search, leaves soldiers in it alone"),
    (11, "walk and ride", "2026-10-19 15:25", "Arma 3's walk and ride measures (squads report whether they ride), engine measures; recordings of the game window only"),
    (12, "covered dismount", "2026-10-19 15:40", "light vehicles first; our side's vehicles stop 200-400 m short where the objective can't see them; solo 2x watched matches"),
    (13, "fireteams, side panels, bounding", "2026-10-19 16:58", "AI Conflict changed: 20 fireteams of 5 per side in a wedge; Arma 3's side panels; bounding on; drone shot to the hit; covered dismount on long rides"),
    (14, "two armies, drone sites", "2026-10-19 17:56", "watched matches: two armies only (no FIA); drones only from drone sites (truck + operators); stuck drones retargeted"),
    (15, "drone reaction", "2026-10-19 20:40", "soldiers (both sides) run to overhead cover or get down when an enemy drone is within 150 m; scatter after a hit; watched at 3x"),
    (16, "teams out at once, drones search", "2026-10-19 21:28", "fireteams start with 3 of 5 and leave with 3 (they waited 10-20 min as one man); drones search when nothing is known and spot for their side"),
    (17, "rides, covered steps", "2026-10-19 21:51", "infantry teams ride light vehicles on marches over 500 m (not one ride before), jog, end each march step in cover; AI Conflict's side flies drones every 2 min"),
    (18, "cover, panic, scan", "2026-10-19 22:05", "idle soldiers to cover anywhere, drone panic from 250 m, drones sweep instead of hovering, rides from 300 m, 16 vehicles per side"),
    (19, "doctrine v doctrine, held prone, standoff", "2026-10-19 23:35", "both sides our doctrine; speed set by the game itself; prone held by the game's stance setting; soldiers hold 60 m from a seen enemy; supply trucks run again; free look, orbit, REPORT, IDs in captions"),
    (20, "danger awareness, anti-drone fire, defend in buildings", "2026-10-20 02:20", "no standing in danger, prone every second near drones, small-arms fire at drones, defenders at the base's buildings, kill zones, wrecks cleared, spectators block no rescue, armed rides, wedge not column"),
    (21, "supply trucks carry the income", "2026-10-20 11:14", "AI Conflict's trucks: bases ask below 35% and are filled to 50%, a source keeps 200; lab income only at the main bases, so the trucks have something to carry"),
    (22, "trucks deliver, much more building", "2026-10-20 14:05", "depots and fortifications pay their cost only, 5 fortifications a base in six types, work crews of idle soldiers, truck roads 100 m beyond a base, the side's first depot first"),
    (23, "supply depots, trucks every match, drones off the sea", "2026-10-20 16:30", "the two bases nearest the middle are supply depots, 3 trucks a depot, fortifications third in the building round, trucks from 60%, drone sweeps never over the sea, abandoned vehicles off the roads"),
    (24, "supplies, trucks and building on screen; gates off the roads; Yunakivka", "2026-10-21 02:00", "base labels with stock and need, supply truck tags, fortification and building-site markers, truck and building shots; 27 road gates removed, a side's first depot forced; AI Conflict runs on Yunakivka"),
    (25, "APC rides; truck drivers left alone; road blocks stay", "2026-10-21 03:56", "every 2nd armed ride an APC (LAV-25 / BTR-70); soldier layers leave truck drivers and builders alone; road blocks kept, minefields removed; Yunakivka storage caches"),
    (26, "armour units (game APCs)", "2026-10-21 04:28", "each side buys a crewed tank/IFV pair at its HQ and sends it to the front; without the armour mods the LAV-25 / BTR-70"),
]
FAMILIES = [("arland-headless", "Arland headless"), ("arland-watched", "Arland watched"), ("everon-watched", "Everon watched"),
            ("arland-headless-2a", "Arland headless, two armies"), ("arland-watched-2a", "Arland watched, two armies"),
            ("everon-watched-2a", "Everon watched, two armies"),
            ("arland-headless-2a-dd", "Arland headless, doctrine v doctrine"), ("arland-watched-2a-dd", "Arland watched, doctrine v doctrine")]
KEYS = ["sc_pass", "sc_out", "sc_atbase", "sc_drones", "sc_sky", "sc_riding", "sc_danger", "sc_panic", "sc_dd_standing", "sc_dd_prone", "sc_shot", "sc_lost", "sc_armed", "sc_jobs", "sc_unloads", "sc_forts", "sc_wrecks", "sc_veh_lost", "sc_armour", "sc_armour_assault", "sc_armour_kills", "pace", "deaths_prone", "drone_near_covered", "drone_near_running", "drone_near_prone", "drone_victims_open", "drone_victims_standing", "field_open", "loss_ratio", "team", "spacing", "walk", "rode", "fight_m", "fps", "aichar", "cover", "incover", "ducks", "stacked", "drone_kills_ours", "lost_to_drones", "margin", "caps", "first_cap", "assault", "storm", "close6", "exchange", "intensity", "stuck",
        "drone_teams", "drone_strikes", "drone_kills", "cause_drone", "cause_direct", "cause_unknown", "trips"]
STAMP = re.compile(r"-(\d{8})-(\d{6})$")


def soldier_metrics(lines: list, side: str) -> dict:
    """Arma 3's soldier measurements (ZCR_Sampler, from r6): fighting from cover, sitting ducks,
    stacking - for one side's soldiers."""
    out = {}
    eng = cov = 0
    eng_g = inc = 0
    teams, spacings = [], []
    stacked = []
    deaths = ducks = 0
    for l in lines:
        if "[ZCR][EXPOSURE]" in l and f"side={side} " in l:
            f = metrics.fields(l, "[ZCR][EXPOSURE]")
            n = int(f.get("engaged", 0))
            eng += n
            cov += n * int(f.get("covered", 0))
            if "incover" in f:
                eng_g += n
                inc += n * int(f["incover"])
        elif "[ZCR][CROWD]" in l and f"side={side} " in l:
            f = metrics.fields(l, "[ZCR][CROWD]")
            # In the field (over 200 m from the main base, where recruits gather) when logged.
            if "team" in f and float(f["team"]) > 0:
                teams.append(float(f["team"]))
            if "spacing" in f and f["spacing"] != "-1":
                spacings.append(int(f["spacing"]))
            if "field_stacked" in f:
                if f["field_stacked"] != "-1":
                    stacked.append(int(f["field_stacked"]))
            else:
                stacked.append(int(f.get("stacked", 0)))
        elif "[ZCR][LOSS]" in l and " stance=" in l:
            f = metrics.fields(l, "[ZCR][LOSS]")
            if f.get("side") != side or f.get("kind") != "man" or f.get("foot") != "1":
                continue
            deaths += 1
            # A sitting duck: not covered toward his killer, not under a roof, not moving.
            if f.get("covered") != "1" and f.get("roof") != "1" and f.get("moving") != "1":
                ducks += 1
    if eng:
        out["cover"] = round(cov / eng, 1)
    if eng_g:
        out["incover"] = round(inc / eng_g, 1)
    if teams:
        out["team"] = round(statistics.mean(teams), 1)
    if spacings:
        out["spacing"] = round(statistics.median(spacings), 1)
    if stacked:
        out["stacked"] = round(statistics.mean(stacked), 1)
    if deaths:
        out["ducks"] = round(100 * ducks / deaths, 1)
        out["deaths_sampled"] = deaths
    return out


def approach_metrics(snaps: list, side: str) -> dict:
    """Arma 3's walk and rode (ac-lab v73) from the strategist's reports: per attack assignment (a
    squad with the ATTACK role sent to a base not its side's), the distance on foot to the objective
    from where it got out of a vehicle or got the order, for the assignments that got within 150 m."""
    cur, done = {}, []
    for r in snaps:
        if r.get("faction") != side:
            continue
        bases = {b["id"]: b for b in r.get("bases", [])}
        for s in r.get("squads", []):
            if "x" not in s:
                continue
            b = bases.get(s.get("target", -1))
            if b is None or b.get("owner") == side or s.get("role") != "ATTACK":
                cur.pop(s["slot"], None)
                continue
            a = cur.get(s["slot"])
            if a is None or a["target"] != b["id"]:
                a = cur[s["slot"]] = {"target": b["id"], "start": (s["x"], s["z"]), "rode": False, "done": False}
            if s.get("ride"):
                a["rode"], a["start"] = True, None          # riding: the walk starts where he gets out
            elif a["start"] is None:
                a["start"] = (s["x"], s["z"])
            cx, cz = b.get("cx", b["x"]), b.get("cz", b["z"])
            if not a["done"] and a["start"] and math.hypot(s["x"] - cx, s["z"] - cz) <= 150:
                a["done"] = True
                done.append((a["rode"], math.hypot(a["start"][0] - cx, a["start"][1] - cz)))
    if not done:
        return {}
    return {"walk": round(statistics.median(d for _, d in done)), "rode": round(100 * sum(r for r, _ in done) / len(done), 1),
            "arrivals": len(done)}


def drone_exposure(lines: list, detonations: list) -> dict:
    """How soldiers (both sides) behave when drones come (Martin: "with danger from drones they should
    run like hell to cover - measure it, in detail"): of the soldiers within 150 m of an enemy drone,
    % under a roof or canopy, % running to cover, % prone ([ZCR][DRONETHREAT], from r15); of the
    soldiers drones killed (no killer, within 5 s of a detonation), % caught in the open (nothing
    overhead) and % standing up; of the soldiers in the field, % with nothing overhead ([ZCR][CROWD])."""
    out = {}
    near = cov = run = pr = 0
    for l in lines:
        if "[ZCR][DRONETHREAT]" in l and " near=" in l:
            f = metrics.fields(l, "[ZCR][DRONETHREAT]")
            n = int(f.get("near", 0))
            near += n
            cov += n * int(f.get("covered", 0))
            run += n * int(f.get("reacting", 0))
            pr += n * int(f.get("prone", 0))
    if near:
        out["drone_near_covered"] = round(cov / near, 1)
        out["drone_near_running"] = round(run / near, 1)
        out["drone_near_prone"] = round(pr / near, 1)
    victims = open_ = standing = 0
    for l in lines:
        if "[ZCR][LOSS]" not in l or " above=" not in l:
            continue
        f = metrics.fields(l, "[ZCR][LOSS]")
        if f.get("kind") != "man" or f.get("killer_kind", "none") != "none":
            continue
        c = metrics.clock(l)
        if c is None or not any(0 <= c - d <= 5 for d in detonations):
            continue
        victims += 1
        if f.get("above") == "none":
            open_ += 1
        if f.get("stance") == "STAND":
            standing += 1
    if victims:
        out["drone_victims_open"] = round(100 * open_ / victims, 1)
        out["drone_victims_standing"] = round(100 * standing / victims, 1)
    fields_, above = [], []
    for l in lines:
        if "[ZCR][CROWD]" in l and "field_above=" in l:
            f = metrics.fields(l, "[ZCR][CROWD]")
            if f.get("field_above", "-1") != "-1" and int(f.get("field", 0)) > 0:
                fields_.append(int(f["field"]))
                above.append(int(f["field_above"]))
    if fields_:
        out["field_open"] = round(100 - sum(a * n for a, n in zip(above, fields_)) / sum(fields_), 1)
    return out


def engine_metrics(lines: list) -> dict:
    """How the engine behaves: fighting distance, server frame rate, soldiers simulated."""
    out = {}
    dist = []
    fps, chars = [], []
    for l in lines:
        if "[ZCR][LOSS]" in l:
            f = metrics.fields(l, "[ZCR][LOSS]")
            try:
                d = float(f.get("distance", "-1"))
            except ValueError:
                continue
            # Enemy fire only (20 Oct): friendly kills (crashes, run over, 347 at a median 3 m) and
            # suicides (0 m) made the "point-blank gunfights" of the night's page - enemy kills: 30 m.
            if f.get("killer_kind", "none") == "man" and f.get("relation", "").startswith("KILLED_BY_ENEMY") and d > 0:
                dist.append(d)
        elif "FPS: " in l and "frame time" in l:
            m = re.search(r"FPS: ([\d.]+).*?AIChar: (\d+)", l)
            if m:
                fps.append(float(m.group(1)))
                chars.append(int(m.group(2)))
    if dist:
        out["fight_m"] = round(statistics.median(dist))
    if len(fps) > 2:
        out["fps"] = round(statistics.median(fps[2:]), 1)      # past the start-up
        out["aichar"] = round(statistics.median(chars[2:]))
    return out


def build_of(started: datetime) -> int:
    n = 1
    for num, _, live, _ in BUILDS:
        if started >= datetime.strptime(live, "%Y-%m-%d %H:%M"):
            n = num
    return n


def server_runs():
    for run in sorted(RUNS.iterdir()):
        name = run.name
        if "-client-" in name or not STAMP.search(name):
            continue
        if not (name.startswith("b-") or name.startswith("probe-") or re.match(r"w\d+-", name)):
            continue
        logs = sorted(run.glob("logs/*/console.log"))
        if logs:
            yield run, logs[-1]


def strategist_sides(lines: list) -> dict:
    """{side: strategist} from the server's command line and its plan lines."""
    cli = next((l for l in lines if "CLI Params:" in l), "")
    args = cli.split("CLI Params:", 1)[-1].split()
    get = lambda k: args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else None
    default = get("-zcrBridge")
    sides = {}
    for side, key in (("US", "-zcrBridgeUS"), ("USSR", "-zcrBridgeUSSR")):
        url = get(key) or default
        if url and url != "none":
            src = Counter(metrics.fields(l, "[ZCR][PLAN]").get("source") for l in lines
                          if "[ZCR][PLAN]" in l and f"faction={side} " in l)
            src.pop("doctrine-fallback", None)
            sides[side] = src.most_common(1)[0][0] if src else "?"
    return sides


def measure_run(run: Path, log: Path):
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    m = metrics.measure(lines)
    score = m.get("score") or {}
    if not score or m["minutes"] < 10:
        return None
    started = datetime.strptime("".join(STAMP.search(run.name).groups()), "%Y%m%d%H%M%S")
    sides = strategist_sides(lines)
    # Both sides ours (doctrine v doctrine, from 19 Oct 22:26): their own line ("-dd"), measured as the
    # US seat - not a head-to-head against AI Conflict, so its margin isn't one.
    both = len(sides) == 2
    side = "US" if both else next(iter(sides), "USSR")     # control: measured as the USSR seat
    other = "US" if side == "USSR" else "USSR"
    mapname = "everon" if "everon" in run.name else "arland"
    kind = "watched" if re.match(r"w\d+-", run.name) else "probe" if run.name.startswith("probe-") else "headless"
    # The two-army test scenario (-zcrNoFIA, from r14): its own lines - no FIA, a different game.
    two_armies = any("CLI Params:" in l and "-zcrNoFIA" in l for l in lines[:400])
    row = {"run": run.name, "started": started.strftime("%Y-%m-%d %H:%M"), "build": build_of(started),
           "map": mapname, "kind": kind, "family": (f"{mapname}-{kind}" + ("-2a" if two_armies else "") + ("-dd" if both else "")) if sides else "control",
           "side": side, "strategist": sides.get(side, "none"), "minutes": m["minutes"]}
    row["margin"] = score.get(side, 0) - score.get(other, 0)
    cli = next((l for l in lines if "CLI Params:" in l), "").split()
    row["storm_priority"] = int(float(cli[cli.index("-zcrStormPriority") + 1])) if "-zcrStormPriority" in cli else 1000
    row["motorize"] = any("[ZCR][PLAN]" in l and f"faction={side} " in l and "motorize=1" in l for l in lines)

    # Captures, assault and storm orders, by base name.
    caps, assault_at, storm_at = {}, {}, {}
    for l in lines:
        t = None
        if "[ZCR][CAPTURE]" in l:
            f = re.search(r"t=(\d+) base=(.*?) from=(\S*) to=(\S*)", l)
            if f and f.group(4) == side:
                caps.setdefault(f.group(2), int(f.group(1)))
        elif "[ZCR][PLAN]" in l and f"faction={side} " in l and "intent=" in l:
            f = re.search(r"intent=(?:Assault on|Storming) (.*?) with ", l)
            t = metrics.fields(l, "[ZCR][PLAN]")
            if f:
                tt = re.search(r"t=(\d+)", l)
                clock_t = metrics.clock(l)
                assault_at.setdefault(f.group(1), clock_t)
        elif "[ZCR][STORM]" in l and f"faction={side} " in l and "base=" in l:
            f = re.search(r"t=(\d+) faction=\S+ base=(.*?) squads=", l)
            if f:
                storm_at.setdefault(f.group(2), int(f.group(1)))
    # Plan lines carry no match time: convert the order's clock to match seconds by the first loss/score line.
    offset = None
    for l in lines:
        if "[ZCR][SCORE]" in l:
            c = metrics.clock(l)
            t = int(metrics.fields(l, "[ZCR][SCORE]").get("t", 0))
            if c is not None:
                offset = c - t
                break
    row["caps"] = len(caps)
    row["first_cap"] = round(min(caps.values()) / 60, 1) if caps else None
    waits = [(t - (assault_at[b] - offset)) / 60 for b, t in caps.items() if b in assault_at and offset is not None]
    row["assault"] = round(statistics.mean(waits), 1) if waits else None
    storms = [(t - storm_at[b]) / 60 for b, t in caps.items() if b in storm_at]
    row["storm"] = round(statistics.mean(storms), 1) if storms else None

    # Losses: exchange, intensity, causes.
    lost = Counter()
    kills = 0
    causes = Counter()
    det = [c for c in (metrics.clock(l) for l in lines if "FPVAI: drone" in l and " detonated" in l) if c is not None]
    for l in lines:
        if "[ZCR][LOSS]" not in l:
            continue
        f = metrics.fields(l, "[ZCR][LOSS]")
        lost[f.get("side", "?")] += 1
        if f.get("killer_side") == side:
            kills += 1
        c = metrics.clock(l)
        if f.get("killer_kind", "none") == "none":
            causes["drone" if c is not None and any(0 <= c - d <= 5 for d in det) else "unknown"] += 1
        else:
            causes["direct"] += 1
    total = sum(lost.values())
    row["exchange"] = round(kills / max(lost[side], 1), 2)
    # Loss ratio: the other army's soldiers lost per own soldier lost - drones' kills too (they have no
    # killer in the game's death event), FIA left out. The two-army scenario's main score.
    row["loss_ratio"] = round(lost[other] / max(lost[side], 1), 2) if lost[other] or lost[side] else None
    row["intensity"] = round(total / m["minutes"] * 20, 1)
    for k in ("drone", "direct", "unknown"):
        row[f"cause_{k}"] = round(100 * causes[k] / total, 1) if total else None
    stuck = sum(1 for l in lines if "GROUP_STUCK_DETECTED" in l and f"faction={side} " in l)
    row["stuck"] = round(stuck / m["minutes"] * 20, 1)
    has_drones = any("[ZCR][DRONES]" in l for l in lines)
    row["drone_teams"] = m["drone_teams"].get(side, 0) if has_drones else None
    row["drone_strikes"] = m["drone_strikes"] if has_drones else None
    row["drone_kills"] = sum(m["drone_kills"].values()) if has_drones else None
    # Both sides fly drones from r8: what our drones killed, and what we lost to theirs.
    row["drone_kills_ours"] = sum(n for s_, n in m["drone_kills"].items() if s_ != side) if has_drones else None
    row["lost_to_drones"] = m["drone_kills"].get(side, 0) if has_drones else None
    row["trips"] = sum(1 for l in lines if "][VEHICLE_REQUESTED]" in l and f"faction={side} " in l)
    row.update(soldier_metrics(lines, side))
    row.update(engine_metrics(lines))
    row.update(drone_exposure(lines, det))
    # AI Conflict start-up failure seen once (19 Oct 13:27): a side's barracks never built, so it
    # never recruits - such a match says nothing about the strategist.
    row["recruits"] = sum(1 for l in lines if "INFANTRY_RECRUIT_JOINED" in l and f"faction={side} " in l)
    row["recruits_other"] = sum(1 for l in lines if "INFANTRY_RECRUIT_JOINED" in l and f"faction={other} " in l)
    # Two armies (-zcrNoFIA) start with soldiers on the map and recruit only 9-30 a match: under 3 is the failure.
    if m["minutes"] >= 20 and (row["recruits"] < 3 or row["recruits_other"] < 3):
        return None

    # Approach: the nearest squad sent to the first objective, 6 min after the assault order.
    row["close6"] = None
    snaps_path = run / "profile" / "zcr" / "snapshots.jsonl"
    first = min(assault_at.items(), key=lambda kv: kv[1]) if assault_at else None
    if first and offset is not None and snaps_path.exists():
        name, at = first[0], first[1] - offset
        best = None
        for line in snaps_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("faction") != side or r.get("t", 0) < at + 360:
                continue
            b = next((x for x in r.get("bases", []) if x.get("name") == name), None)
            if b is None:
                break
            cx, cz = b.get("cx", b["x"]), b.get("cz", b["z"])
            d = [math.hypot(s["x"] - cx, s["z"] - cz) for s in r.get("squads", []) if "x" in s and s.get("target") == b["id"]]
            best = round(min(d)) if d else None
            break
        row["close6"] = best
    if row["build"] >= 11 and snaps_path.exists():
        snaps = []
        for line in snaps_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                snaps.append(json.loads(line))
            except ValueError:
                pass
        row.update(approach_metrics(snaps, side))
    row.update(screen_metrics(run, lines))
    return row


def screen_metrics(run: Path, lines: list) -> dict:
    """What the screen shows (lab/scorecard.py, 19 Oct): the checks passed and their numbers, both sides
    averaged (doctrine against doctrine); pace on the move; how many of the dead were lying prone."""
    out = {}
    try:
        import scorecard
        card = scorecard.measure(run)
        sides = [card["sides"][s] for s in ("US", "USSR") if s in card.get("sides", {})]
        checks = [ok(m) for m in sides for _, ok, _ in scorecard.CHECKS]
        if checks:
            out["sc_pass"] = round(100 * sum(checks) / len(checks))

        def avg(key):
            vals = [m[key] for m in sides if m.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
        def total(key):
            vals = [m[key] for m in sides if m.get(key) is not None]
            return sum(vals) if vals else None
        out.update({"sc_out": avg("out_min"), "sc_atbase": avg("atbase10"), "sc_drones": avg("drones_per4"),
                    "sc_sky": avg("sky_pct"), "sc_riding": avg("riding_pct"),
                    "sc_danger": avg("danger_standing"), "sc_panic": avg("panic_pct"),
                    "sc_dd_standing": avg("drone_dead_standing"), "sc_dd_prone": avg("drone_dead_prone"),
                    "sc_shot": avg("shot_down"), "sc_lost": avg("lost"), "sc_armed": avg("armed_teams"),
                    "sc_jobs": total("truck_jobs"), "sc_unloads": total("truck_unloads"), "sc_forts": total("forts"),
                    "sc_wrecks": card.get("wrecks"), "sc_veh_lost": card.get("veh_lost"),
                    "sc_armour": total("armour"), "sc_armour_assault": total("armour_assault"), "sc_armour_kills": total("armour_kills")})
    except Exception as e:   # the page must not stop on one match
        print(f"scorecard {run.name}: {e}", file=sys.stderr)
    paces = [int(m.group(1)) for m in (re.search(r" pace=(\d+)", l) for l in lines if "[ZCR][CROWD]" in l) if m]
    if paces:
        out["pace"] = round(sum(paces) / len(paces) / 10, 1)
    stances = [m.group(1) for m in (re.search(r"kind=man .*stance=([A-Z]+)", l) for l in lines if "[ZCR][LOSS]" in l) if m]
    if stances:
        out["deaths_prone"] = round(100 * stances.count("PRONE") / len(stances))
    return out


def rows_all() -> list:
    out = []
    for run, log in server_runs():
        try:
            r = measure_run(run, log)
        except Exception as e:   # one broken log must not stop the page
            print(f"skip {run.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if r:
            out.append(r)
    return out


def aggregate(rows: list) -> dict:
    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        for fam in (r["family"], "all" if r["kind"] != "probe" and r["family"] != "control" else "other"):
            for k in KEYS:
                if r.get(k) is not None:
                    agg[fam][r["build"]][k].append(r[k])
            agg[fam][r["build"]]["n"].append(1)
    return {fam: {b: {k: (len(x) if k == "n" else round(statistics.mean(x), 1)) for k, x in ks.items()}
                  for b, ks in sorted(bs.items())} for fam, bs in agg.items()}


def control_baseline(rows: list, key: str):
    vals = [r[key] for r in rows if r["family"] == "control" and r.get(key) is not None]
    return round(statistics.mean(vals), 1) if vals else None


def html(agg: dict, rows: list) -> str:
    from charts import line_chart
    builds = [b for b, *_ in BUILDS]
    notes = {b: name for b, name, *_ in BUILDS}
    charts = []

    def ser(key, fams=FAMILIES):
        return [(name, {b: ks.get(key) for b, ks in agg.get(f, {}).items()}) for f, name in fams]

    def add(title, why, series, **kw):
        used = sorted({b for _, d in series for b, v in d.items() if v is not None})
        if not used:
            return
        charts.append(f'<figure class="pfig"><figcaption><b>{title}</b> {why}</figcaption>'
                      + line_chart(title, used, series, notes={b: notes[b] for b in used}, prefix="r", **kw) + "</figure>")

    add("What the screen shows: checks passed", "lab/scorecard.py on every match, both sides: first team out by 3 min, at most 40% at the main base at 10 min, teams of 2.5+, a drone team every 4 min, drones up 60% of the time, soldiers riding 25% of the time. From 19 Oct 21:40, when Martin found the regression the other measures hid.",
        ser("sc_pass"), unit="%", ymax=100, target=(100, "all"), better="higher")
    add("First team out of the base", "Minutes until a soldier of either side is over 200 m from his main base (both sides averaged). AI Conflict's teams of one man waited 10-20 minutes before r16.",
        ser("sc_out"), unit=" min", target=(3, "3 min"), better="lower")
    add("At the main base at minute 10", "Of each side's soldiers, % within 200 m of the main base at 10 minutes (Martin: \"chilling at the base doing push-ups\").",
        ser("sc_atbase"), unit="%", ymax=100, target=(40, "40%"), better="lower")
    add("Drone teams per 4 minutes", "Drone teams launched per side per 4 minutes after the first two (Martin: \"heavy drone dependent\"); 0-0.5 from 18:40 until r16.",
        ser("sc_drones"), target=(1, "1"), better="higher")
    add("Drones up", "% of the 30-s samples with a side's drones in the air (from r16).", ser("sc_sky"), unit="%", ymax=100, target=(60, "60%"), better="higher")
    add("Soldiers riding", "% of the 30-s samples with a side's soldiers in a moving vehicle (from r18; no ride at all before r17).", ser("sc_riding"), unit="%", ymax=100, target=(25, "25%"), better="higher")
    add("Pace on the move", "Median speed of soldiers on foot moving over 3 km/h - a walk is ~1.7 m/s, a jog ~3.5 (Martin: \"they just walk to the points\").", ser("pace"), unit=" m/s", better="higher")
    add("Dead lying prone", "Of the soldiers lost on foot, % lying prone when killed - 0% in the 23:22 match: the drone reaction's \"get down\" was undone at once (fixed r19).", ser("deaths_prone"), unit="%", ymax=100, better="higher")
    add("Fighting from cover", "Of the soldiers (with our strategist) who know an enemy within 300 m, how many have something solid within 3 m toward the nearest one, or a roof. Same measure as Arma 3, ground counts as cover. From r6.",
        ser("cover"), unit="%", ymax=60, target=(40, "target 40%"), better="higher")
    add("In the game's own cover", "Of the same soldiers, how many are at one of the game's own cover points (in cover, exposed to shoot or hidden) - what its attack logic counts as cover. From r10.",
        ser("incover"), unit="%", ymax=60, better="higher")
    add("Under cover when a drone comes", "Of the soldiers (both sides) within 150 m of an enemy drone in the air, how many are under a roof or tree canopy. Measured every 10 s from r15, when soldiers started reacting to drones.",
        ser("drone_near_covered"), unit="%", ymax=100, better="higher")
    add("Running for cover from a drone", "Of the same soldiers, how many are running to overhead cover at that moment (and how many lie prone: see the table). From r15.",
        ser("drone_near_running"), unit="%", ymax=100, better="higher")
    add("Drone victims caught in the open", "Of the soldiers drones killed (no killer, within 5 s of a detonation), how many had nothing overhead - no roof, no tree crown. From r7's death records.",
        ser("drone_victims_open"), unit="%", ymax=100, better="lower")
    add("In the open in the field", "Of the soldiers on foot in the field (over 200 m from their main base), how many have nothing overhead - what a drone sees. From r7.",
        ser("field_open"), unit="%", ymax=100, better="lower")
    add("Sitting ducks", "Of the soldiers lost on foot, how many were standing or lying still in the open: not covered toward the killer, no roof, not moving. From r6.",
        ser("ducks"), unit="%", ymax=100, target=(50, "limit 50%"), better="lower")
    add("Team size", "Soldiers on foot per group, on average (Martin: groups of 2-5 like Arma 3's fireteams; AI Conflict's squads were 10, fireteams of 5 from r13).",
        ser("team"), target=(5, "5"), better="lower")
    add("Spacing", "Median metres from a soldier in the field to his nearest friend - a squad walking single file down a road sits at 3-5 m. From r13.",
        ser("spacing"), unit=" m", target=(10, "10 m"), better="higher")
    add("Stacking", "Soldiers on foot in the field (over 200 m from their main base, where AI Conflict gathers its recruits) bunched up with 6 or more friends within 25 m. From r6.",
        ser("stacked"), unit="%", target=(10, "limit 10%"), better="lower")
    base_margin_ussr = control_baseline(rows, "margin")
    add("Bases won", "Bases held at the end, the side with our strategist minus the side on AI Conflict alone. On Arland the US seat starts stronger: in the controls (AI Conflict on both sides) the USSR ends "
        f"{base_margin_ussr:+} on average." if base_margin_ussr is not None else "Bases held at the end, our side minus AI Conflict's.",
        ser("margin"), ymax=3, better="higher")
    add("Bases taken", "Bases the side with our strategist took in a match (30 min, watched 28).", ser("caps"), ymax=4, better="higher")
    add("Time to the first capture", "Minutes until the side with our strategist took its first base.", ser("first_cap"), unit=" min", ymax=30, better="lower")
    add("From the assault order to the capture", "Minutes from the doctrine's assault order on a base to taking it - the Arma 3 doctrine's measure of an assault that gains ground.",
        ser("assault"), unit=" min", ymax=25, better="lower")
    add("From the storm to the capture", "Minutes from the storm order to taking the base (from r4).", ser("storm"), unit=" min", ymax=15, better="lower")
    add("How close after 6 minutes", "Metres from the objective of the nearest squad sent there, 6 minutes into the first assault. AI Conflict stages squads 400-500 m out.",
        ser("close6"), unit=" m", target=(250, "250 m"), better="lower")
    add("How far the infantry walks", "Median distance an attacking squad covers on foot to its objective - from where it got out of a vehicle, or from where it was when it got the order (squads that got within 150 m). Arma 3's measure; Martin: in reality they dismount 100-300 m out. From r11.",
        ser("walk"), unit=" m", target=(300, "300 m"), better="lower")
    add("Riding to the attack", "Of the attacking squads that reached their objective, how many rode a vehicle part of the way. Arma 3's measure. From r11.",
        ser("rode"), unit="%", ymax=100, better="higher")
    add("Fighting distance", "Engine: median distance between killer and victim of the kills by enemy soldiers (from 20 Oct: friendly kills - crashes, run over - and suicides left out; they made a false 3 m). Shows at what range Reforger's AI actually fights.",
        ser("fight_m"), unit=" m")
    add("Server frame rate", "Engine: the server's median frames per second during the match (logged every minute). The AI thinks and moves less smoothly when it drops; 3-4 servers and the watched game share one PC.",
        ser("fps"), unit=" fps", target=(30, "30 fps"), better="higher")
    add("Loss ratio", "Soldiers of the other army lost per soldier the side with our strategist lost - drone kills included (they have no killer in the game's death event), FIA left out. The two-army scenario's main score.",
        ser("loss_ratio"), target=(1, "even"), better="higher")
    add("Exchange", "Soldiers the side with our strategist killed (FIA and enemy) per soldier it lost.", ser("exchange"), target=(1, "even trade"), better="higher")
    add("Does the fight happen", "Soldiers lost per 20 game minutes, everyone.", ser("intensity"))
    add("Stuck squads", "AI Conflict's stuck reports for the squads of the side with our strategist, per 20 game minutes.", ser("stuck"), better="lower")
    mix = [("FPV drones", {b: ks.get("cause_drone") for b, ks in agg.get("all", {}).items()}),
           ("Direct fire", {b: ks.get("cause_direct") for b, ks in agg.get("all", {}).items()}),
           ("Unknown", {b: ks.get("cause_unknown") for b, ks in agg.get("all", {}).items()})]
    add("What causes the losses", "Share of soldiers lost, all matches of each build. A death with no killer within 5 s of an FPV detonation counts as the drone's. The green band is what front-line reports give for drones (the drone warfare doctrine's aim, review note 118).",
        mix, unit="%", ymax=100, band=(70, 96, "front: drones 70-96%"))
    add("Drone exchange", "Soldiers killed by our strategist's drones, and soldiers it lost to the enemy's drones, per match (both sides fly drones from r8).",
        [("Killed by our drones", {b: ks.get("drone_kills_ours") for b, ks in agg.get("all", {}).items()}),
         ("Lost to theirs", {b: ks.get("lost_to_drones") for b, ks in agg.get("all", {}).items()})])
    add("Drones in use", "FPV teams launched, strikes and kills per match - watched matches only until r7; from r8 headless too, and both sides fly drones.",
        [("Teams", {b: ks.get("drone_teams") for b, ks in agg.get("all", {}).items()}),
         ("Strikes", {b: ks.get("drone_strikes") for b, ks in agg.get("all", {}).items()}),
         ("Kills", {b: ks.get("drone_kills") for b, ks in agg.get("all", {}).items()})], ymax=25)
    n = len([r for r in rows if r["family"] != "control" and r["kind"] != "probe"])
    nc = len([r for r in rows if r["family"] == "control"])
    np_ = len([r for r in rows if r["kind"] == "probe"])
    return (f'<p class="pnote">Measured, not estimated: {n} matches against AI Conflict, {nc} controls and {np_} probes (in the table below, not the lines), read back from the logs by '
            f'<code>python lab/progress.py</code>. Each point is the mean of that build\'s matches - most builds have 1-4, so single points jump. '
            f'Lines are per map and kind: headless (measured) and watched (recorded, with drones). Hover a point for its value.</p>'
            '<div class="pgrid">' + "".join(charts) + "</div>")


def headline(agg: dict, first: int = 14) -> str:
    """The problems Martin raised, one chart each: every match of a build (both sides ours, both sides
    averaged), from r14 (two armies, drone sites) - the top of the engine page."""
    from charts import line_chart
    notes = {b: name for b, name, *_ in BUILDS}
    allb = {b: ks for b, ks in agg.get("all", {}).items() if b >= first}
    charts = []

    def add(title, why, series, **kw):
        used = sorted({b for _, d in series for b, v in d.items() if v is not None})
        if not used:
            return
        charts.append(f'<figure class="pfig"><figcaption><b>{title}</b> {why}</figcaption>'
                      + line_chart(title, used, series, prefix="r", **kw) + "</figure>")

    def s(name, key):
        return (name, {b: ks.get(key) for b, ks in allb.items()})
    add("Checks passed", "What the screen shows (lab/scorecard.py): team out by 3 min, few at the base at 10 min, teams of 2.5+, drones every 4 min and up 60% of the time, panic near drones, drone victims not standing, riding 25%.",
        [s("checks passed", "sc_pass")], unit="%", ymax=100, target=(100, "all"), better="higher")
    add("Reckless soldiers", "Of the soldiers in high danger (enemy within 150 m, under fire, a friend just lost, a drone within 150 m), % still standing - measured from r20; and of the soldiers drones killed, % standing and % prone.",
        [s("standing in danger", "sc_danger"), s("drone victims standing", "sc_dd_standing"), s("drone victims prone", "sc_dd_prone")], unit="%", ymax=100, better="lower")
    add("Safe near a drone", "Of the soldiers within 150 m of an enemy drone: under a roof or trees, running for cover or lying prone.",
        [s("safe near drones", "sc_panic")], unit="%", ymax=100, target=(60, "60%"), better="higher")
    add("Spread out", "Median metres from a soldier in the field to his nearest friend (\"one drone kills them all\"); target 10 m.",
        [s("metres to the nearest friend", "spacing")], unit=" m", target=(10, "10 m"), better="higher")
    add("Chilling at the base", "% of each side's soldiers within 200 m of their main base at minute 10.",
        [s("at the main base", "sc_atbase")], unit="%", ymax=100, target=(40, "40%"), better="lower")
    add("Drones in the air", "% of the 30-s samples with a side's drones up, and drone teams launched per 4 minutes.",
        [s("drones up %", "sc_sky")], unit="%", ymax=100, target=(60, "60%"), better="higher")
    add("Using vehicles", "% of the 30-s samples with a side's soldiers riding a moving vehicle; teams riding an armed vehicle per side.",
        [s("riding %", "sc_riding")], unit="%", ymax=100, target=(25, "25%"), better="higher")
    add("Vehicles lost", "Vehicles destroyed per match, both sides. On 20 Oct 191 of 342 blew up on the world's mine rows across the main bases' exit roads (removed from r21).",
        [s("vehicles lost", "sc_veh_lost")], better="lower")
    add("Armour in combat", "Tanks and IFVs (ZCR_Armour, from r26) per match, both sides: bought, got into the assault on their front, and enemy killed by them.",
        [s("armour bought", "sc_armour"), s("into the assault", "sc_armour_assault"), s("killed by armour", "sc_armour_kills")], better="higher")
    add("Fire at drones", "Drones a side's soldiers shot down with small arms, per side per match (from r20).",
        [s("shot down", "sc_shot")], better="higher")
    add("Supply trucks", "AI Conflict's supply runs per match, both sides: jobs taken and loads unloaded at a base.",
        [s("jobs", "sc_jobs"), s("unloads", "sc_unloads")], better="higher")
    add("Defences built", "Bunkers both sides' engineers finished per match (from r20).",
        [s("bunkers", "sc_forts")], better="higher")
    add("Losses", "Soldiers lost per side per match.", [s("lost per side", "sc_lost")], better="lower")
    n = {b: ks.get("n") for b, ks in allb.items()}
    counts = ", ".join(f"r{b} {c}" for b, c in n.items() if c)
    key = " · ".join(f"<b>r{b}</b> {notes[b]}" for b in sorted(allb))
    return (f'<p class="pnote">One point per build: the mean of its matches (both sides ours, headless and watched; probes left out). Matches: {counts}. Hover a point for its value.</p>'
            '<div class="pgrid">' + "".join(charts) + f'</div><p class="pnote">Builds: {key}. What each one changed: the changelog.</p>')


def main() -> int:
    rows = rows_all()
    agg = aggregate(rows)
    if "--html" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--html") + 1])
        out.write_text(html(agg, rows), encoding="utf-8")
        print(f"charts -> {out}")
    (ROOT / ".runtime" / "progress.json").write_text(json.dumps(
        {"generated": datetime.now().isoformat(timespec="minutes"), "matches": rows, "by_build": agg}, indent=1), encoding="utf-8")
    print(f"{len(rows)} matches -> .runtime/progress.json")
    for r in rows:
        print(f"r{r['build']} {r['run'][:44]:44} {r['side']:4} {r['strategist']:10} margin {r['margin']:+d} caps {r['caps']} "
              f"first {r['first_cap']} assault {r['assault']} storm {r['storm']} close6 {r['close6']} exch {r['exchange']} "
              f"int {r['intensity']} stuck {r['stuck']} trips {r['trips']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
