"""The Progress tab's graphs, as data the app draws with ECharts: the engine page's graphs (lab/progress.py)
plus each goal's measures over the watched matches.

Two kinds of graph from lab/progress.py's per-match rows:
  family  one measure, a line per kind of match (headless, watched, two armies...) - mean per build
  multi   several measures over all matches together - mean per build
and one from the goals: every watched match's value of a goal's measure, with its target.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import goals as goals_mod  # noqa: E402
import measures  # noqa: E402
import progress  # noqa: E402

# (id, kind, title, why, measures [(label, key)], unit, ymax, target (value, label) or None, better)
CHARTS = [
    ("checks", "multi", "What the screen shows: checks passed", "lab/scorecard.py on every match, both sides: first team out by 3 min, at most 40% at the main base at 10 min, teams of 2.5+, a drone team every 4 min, drones up 60% of the time, safe near drones, drone victims not standing, riding 25%.",
     [("checks passed", "sc_pass")], "%", 100, (100, "all"), "higher"),
    ("reckless", "multi", "Reckless soldiers", "Of the soldiers in high danger (enemy within 150 m, under fire, a friend just lost, a drone within 150 m), % still standing; of the soldiers drones killed, % standing and % prone.",
     [("standing in danger", "sc_danger"), ("drone victims standing", "sc_dd_standing"), ("drone victims prone", "sc_dd_prone")], "%", 100, None, "lower"),
    ("panic", "multi", "Safe near a drone", "Of the soldiers within 150 m of an enemy drone: under a roof or trees, running for cover or lying prone.",
     [("safe near drones", "sc_panic")], "%", 100, (60, "60%"), "higher"),
    ("atbase", "family", "At the main base at minute 10", "Of each side's soldiers, % within 200 m of the main base at 10 minutes (Martin: \"chilling at the base\").",
     [("at the main base", "sc_atbase")], "%", 100, (40, "40%"), "lower"),
    ("out", "family", "First team out of the base", "Minutes until a soldier is over 200 m from his main base. AI Conflict's teams of one man waited 10-20 minutes before r16.",
     [("first out", "sc_out")], " min", None, (3, "3 min"), "lower"),
    ("sky", "family", "Drones up", "% of the 30-s samples with a side's drones in the air (from r16).",
     [("drones up", "sc_sky")], "%", 100, (60, "60%"), "higher"),
    ("drones", "family", "Drone teams per 4 minutes", "Drone teams launched per side per 4 minutes after the first two (Martin: \"heavy drone dependent\").",
     [("teams / 4 min", "sc_drones")], "", None, (1, "1"), "higher"),
    ("riding", "family", "Soldiers riding", "% of the 30-s samples with a side's soldiers in a moving vehicle (from r18).",
     [("riding", "sc_riding")], "%", 100, (25, "25%"), "higher"),
    ("trucks", "multi", "Supply trucks", "AI Conflict's supply runs per match, both sides: jobs taken and loads unloaded at a base.",
     [("jobs", "sc_jobs"), ("unloads", "sc_unloads")], "", None, None, "higher"),
    ("forts", "multi", "Defences built", "Fortifications both sides' engineers finished per match (from r20).",
     [("fortifications", "sc_forts")], "", None, None, "higher"),
    ("armour", "multi", "Armour in combat", "Tanks and IFVs per match, both sides (from r26): bought, got into the assault on their front, enemy killed by their guns - and their own soldiers killed by them (22 Oct: 50 own, 8 enemy). Martin: 'if the AI can shoot from the tank, make it work and watch the progress'.",
     [("bought", "sc_armour"), ("into the assault", "sc_armour_assault"), ("enemy killed by armour", "sc_armour_kills"), ("own killed by armour", "sc_armour_friendly")], "", None, None, "higher"),
    ("shot", "multi", "Fire at drones", "Drones a side's soldiers shot down with small arms, per side per match (from r20).",
     [("shot down", "sc_shot")], "", None, None, "higher"),
    ("vehlost", "multi", "Vehicles lost", "Vehicles destroyed per match, both sides. On 20 Oct 191 of 342 blew up on mine rows across the main bases' exit roads (removed from r21).",
     [("vehicles lost", "sc_veh_lost")], "", None, None, "lower"),
    ("lost", "multi", "Losses", "Soldiers lost per side per match.", [("lost per side", "sc_lost")], "", None, None, "lower"),
    ("spacing", "family", "Spread out", "Median metres from a soldier in the field to his nearest friend (\"one drone kills them all\").",
     [("metres to the nearest friend", "spacing")], " m", None, (10, "10 m"), "higher"),
    ("team", "family", "Team size", "Soldiers on foot per group, on average (fireteams of 5 from r13).", [("team size", "team")], "", None, (5, "5"), "lower"),
    ("stacked", "family", "Stacking", "Soldiers on foot in the field bunched up with 6 or more friends within 25 m (from r6).",
     [("stacked", "stacked")], "%", None, (10, "limit 10%"), "lower"),
    ("cover", "family", "Fighting from cover", "Of the soldiers who know an enemy within 300 m, how many have something solid within 3 m toward it, or a roof (from r6).",
     [("from cover", "cover")], "%", 60, (40, "target 40%"), "higher"),
    ("dronevictims", "family", "Drone victims caught in the open", "Of the soldiers drones killed, how many had nothing overhead - no roof, no tree crown (from r7).",
     [("in the open", "drone_victims_open")], "%", 100, None, "lower"),
    ("causes", "multi", "What causes the losses", "Share of soldiers lost, all matches of each build. The front-line reports' band for drones: 70-96%.",
     [("FPV drones", "cause_drone"), ("direct fire", "cause_direct"), ("unknown", "cause_unknown")], "%", 100, None, None),
    ("exchange", "family", "Loss ratio", "Soldiers of the other army lost per soldier the side with our strategist lost - drone kills included.",
     [("loss ratio", "loss_ratio")], "", None, (1, "even"), "higher"),
    ("margin", "family", "Bases won", "Bases held at the end, the side with our strategist minus the other.", [("margin", "margin")], "", None, None, "higher"),
    ("walk", "family", "How far the infantry walks", "Median distance an attacking squad covers on foot to its objective (Arma 3's measure; from r11).",
     [("walked", "walk")], " m", None, (300, "300 m"), "lower"),
    ("fight", "family", "Fighting distance", "Median distance between killer and victim of the kills by enemy soldiers.", [("distance", "fight_m")], " m", None, None, None),
    ("traffic", "family", "Vehicles drive well: jams and long stops", "Per match, both sides: jams (a driven vehicle still 45 game s with another vehicle within 10 m) and long stops (a vehicle still 2 game minutes or more). Martin: 'cars blocking each other is the biggest issue'. Goal: jams 2 or fewer, long stops 3 or fewer.",
     [("jams", "jams"), ("long stops (2 min+)", "stuck_long")], "", None, (3, "3"), "lower"),
    ("stuck", "family", "Vehicles stuck and failed drives", "Per match: stuck spells (a vehicle still 45 game s with somewhere to go), drives the game gave up (stuck or unreachable - the crew then gets out and walks) and armour standing still in its approach or assault.",
     [("stuck spells", "stuck_vehicles"), ("failed drives", "move_fails"), ("armour still", "armour_still")], "", None, None, "lower"),
    ("drive", "family", "Driving speed", "Median speed of the AI-driven vehicles while moving (km/h). The game's drivers run 8-25 km/h; lower means queues and crawling.",
     [("moving speed", "drive_kmh")], " km/h", None, (18, "18 km/h"), "higher"),
    ("fps", "family", "Game frame rate", "Median frames per second during each match: in a watched match the game window itself (it hosts the match), headless the server. Normal about 40; three of my stress servers alongside cut it to 15-20 (21 Oct 20:10).",
     [("fps", "fps")], " fps", None, (30, "30 fps"), "higher"),
]

ROW_KEYS = sorted({k for c in CHARTS for _, k in c[4]})


def progress_data() -> dict:
    rows = progress.rows_all()
    slim = [{"run": r["run"], "started": r["started"], "build": r["build"], "family": r["family"], "kind": r["kind"],
             **{k: r.get(k) for k in ROW_KEYS if r.get(k) is not None}} for r in rows]
    builds = [{"n": b, "name": name, "from": live} for b, name, live, *_ in progress.BUILDS]
    charts = [{"id": c[0], "kind": c[1], "title": c[2], "why": c[3], "measures": [{"label": l, "key": k} for l, k in c[4]],
               "unit": c[5], "ymax": c[6], "target": c[7], "better": c[8]} for c in CHARTS]
    return {"builds": builds, "families": [{"id": f, "name": n} for f, n in progress.FAMILIES], "rows": slim, "charts": charts}


def goal_history(n: int = 40) -> list:
    """Each goal measure over the last n finished watched matches: one point per match (per side for side measures)."""
    runs = goals_mod.runs_for("watched", n, [])
    out = []
    for goal in goals_mod.load():
        if goal.get("status") == "paused":
            continue
        for spec in goal.get("measure", []):
            key = spec["key"]
            per = measures.MEASURES.get(key, ("match",))[0]
            pts = []
            for r in runs:
                if goal.get("needs") and "armour" in goal["needs"] and not any((measures.measure(r).get("armour") or {}).get(s) for s in measures.SIDES):
                    continue
                v = measures.measure(r).get(key)
                m = re.search(r"-(\d{8})-(\d{6})$", r.name)
                at = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]} {m.group(2)[:2]}:{m.group(2)[2:4]}" if m else r.name
                pts.append({"at": at, "run": r.name, "value": v})
            out.append({"goal": goal["id"], "title": goal.get("title", ""), "key": key, "per": per, "target": spec["target"],
                        "label": measures.MEASURES.get(key, ("", key))[1], "points": pts})
    return out
