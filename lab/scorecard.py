"""What Martin sees on screen, as hard checks per match - the check that should have caught the
19 Oct regression (teams of one man waiting at base, no drones in the sky, nobody in a vehicle).
Averages over the whole match hid it, and the headless batch looked fine while the watched matches
had collapsed; so: the watched matches first, time slices, and pass/fail against fixed limits.

    python lab/scorecard.py                 # the latest watched match and the latest batch match
    python lab/scorecard.py RUN_DIR ...     # these matches
    python lab/scorecard.py --today         # every match of today, one line each

Checks per side (US, USSR):
  out      first team leaves the main base (a soldier over 200 m from it) by minute 3
  atbase   at minute 10, at most 40% of the side's soldiers within 200 m of the main base
  team     at minute 10, teams of 2.5 or more on average (soldiers per team out there)
  drones   a drone team launched at least every 4 minutes on average (after the first 2 minutes)
  sky      drones in the air in at least 60% of the 30-s samples after minute 3 (r16+)
  rides    soldiers riding in a moving vehicle in at least 25% of the 30-s samples (r18+; before,
           teams that started boarding - which said "fine" while Martin saw no car on screen)
  panic    near an enemy drone (250 m) at least 60% under cover, running for it or prone, on average
           (Martin: "infantry has to be very careful when there is a drone")
  down     of the soldiers drones killed, at most 50% standing (none was prone before r19)
  open     soldiers in the field with something overhead or beside them - shown, not checked yet
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / ".runtime" / "runs"
KV = re.compile(r"(\w+)=(\S*)")
SIDES = ("US", "USSR")


def console(run: Path):
    logs = sorted(run.glob("logs/*/console.log"))
    return logs[0] if logs else None


def kv(line: str) -> dict:
    return dict(KV.findall(line))


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def measure(run: Path) -> dict:
    log = console(run)
    if not log:
        return {}
    crowd = {s: [] for s in SIDES}
    air = {s: [] for s in SIDES}
    launches = {s: [] for s in SIDES}
    noteam = {s: 0 for s in SIDES}
    boarded = {s: set() for s in SIDES}
    riding = {s: [] for s in SIDES}
    threat = {s: [] for s in SIDES}
    danger_high = {s: [] for s in SIDES}        # % of the high-danger soldiers standing, per sample
    shot_down = {s: 0 for s in SIDES}
    jobs = {s: 0 for s in SIDES}
    unloads = {s: 0 for s in SIDES}
    forts = {s: 0 for s in SIDES}
    armed = {s: set() for s in SIDES}
    wrecks = 0
    veh_lost = 0
    # Armour (ZCR_Armour): units bought, units that got to the assault, enemy killed by armour, armour lost.
    armour = {k: {s: 0 for s in SIDES} for k in ("bought", "lost", "kills", "friendly")}
    armour_assault = {s: set() for s in SIDES}
    drone_dead = {s: [] for s in SIDES}
    # The drone teams (ZCR_DroneOperator, 24 Oct): flights, goggles on at take-off, the pilot still through a flight
    # (take-off and landing position within 3 m), sorties out, launches from the bag, loads at the truck.
    op = {k: {s: 0 for s in SIDES} for k in ("flights", "goggles", "still", "out", "launch", "loaded")}
    took_off = {}
    lost = {s: 0 for s in SIDES}
    last_t = 0
    for line in open(log, encoding="utf-8", errors="replace"):
        if "[ZCR][" not in line and "BOARDING_PHASE_STARTED" not in line and "LOGISTICS_" not in line                 and "CONSTRUCTION_COMPLETED" not in line and "ARMED_LIGHT" not in line:
            continue
        d = kv(line)
        t = num(d.get("t"))
        if t is not None:
            last_t = max(last_t, t)
        side = d.get("side") or d.get("faction")
        if "[ZCR][CROWD]" in line and side in SIDES:
            crowd[side].append(d)
        elif "[ZCR][DRONEAIR]" in line and side in SIDES:
            air[side].append((t, int(num(d.get("air"), 0))))
        elif "[ZCR][DRONES]" in line and side in SIDES:
            if "kind=" in line and "team=" in line:
                launches[side].append(t)
            elif "no team" in line:
                noteam[side] += 1
        elif "[ZCR][DRONETHREAT]" in line and side in SIDES and " near=" in line:
            safe = num(d.get("covered"), 0) + num(d.get("reacting"), 0) + num(d.get("prone"), 0)
            threat[side].append(min(100, safe))
        elif "[ZCR][DANGER]" in line and side in SIDES:
            if num(d.get("high_standing"), -1) >= 0:
                danger_high[side].append(num(d.get("high_standing")))
        elif "[ZCR][ANTIDRONE]" in line and side in SIDES and "shot_down=1" in line:
            shot_down[side] += 1
        elif "[ZCR][OPERATOR]" in line and side in SIDES:
            ev = d.get("event")
            if ev == "flying":
                op["flights"][side] += 1
                took_off[side] = (num(d.get("x"), 0), num(d.get("z"), 0))
            elif ev == "landed" and side in took_off:
                x0, z0 = took_off.pop(side)
                if ((num(d.get("x"), 0) - x0) ** 2 + (num(d.get("z"), 0) - z0) ** 2) ** 0.5 <= 3:
                    op["still"][side] += 1
            elif ev == "goggles" and d.get("ok") == "1":
                op["goggles"][side] += 1
        elif "[ZCR][SORTIE]" in line and side in SIDES:
            ev = d.get("event")
            if ev in ("out", "launch", "loaded"):
                op[ev][side] += 1
        elif "[ZCR][ARMOUR]" in line and side in SIDES:
            ev = d.get("event")
            if ev == "BOUGHT":
                armour["bought"][side] += 1
            elif ev == "LOST":
                armour["lost"][side] += 1
            elif ev == "ORDER" and d.get("phase") == "ASSAULT":
                armour_assault[side].add((d.get("unit"), armour["bought"][side]))
        elif "[ZCR][WRECK]" in line:
            wrecks += 1
        elif "LOGISTICS_JOB_RESERVED" in line and side in SIDES:
            jobs[side] += 1
        elif "LOGISTICS_UNLOAD_COMMITTED" in line and side in SIDES:
            unloads[side] += 1
        elif "CONSTRUCTION_COMPLETED" in line and "type=FORTIFICATION" in line and side in SIDES:
            forts[side] += 1
        elif "ARMED_LIGHT" in line and side in SIDES and d.get("slot"):
            armed[side].add(d.get("slot"))
        elif "[ZCR][RIDING]" in line and side in SIDES:
            riding[side].append(int(num(d.get("riding"), 0)))
        elif "BOARDING_PHASE_STARTED" in line and side in SIDES:
            boarded[side].add(d.get("slot"))
        elif "[ZCR][LOSS]" in line:
            if d.get("kind") == "vehicle":
                veh_lost += 1
            k = d.get("killer_side")
            if "armour=" in line and k in SIDES and k != (d.get("victim_side") or d.get("side")):
                armour["kills"][k] += 1
            # Own soldiers killed by our armour (22 Oct: 12 that day, against 8 enemy) - not its crew dying with
            # their own vehicle (credited to a crewmate, 1-5 m away: 38 of the 50 'friendly' deaths that day).
            elif "armour=" in line and k in SIDES and k == (d.get("victim_side") or d.get("side")) and                     not ("Crew" in (d.get("victim") or "") and num(d.get("distance"), 99) <= 5):
                armour["friendly"][k] += 1
            v = d.get("victim_side") or d.get("side")
            if v in SIDES:
                lost[v] += 1
                if d.get("kind") == "man" and d.get("killer_kind") in ("none", "") and d.get("stance"):
                    drone_dead[v].append(d.get("stance"))
    out = {"run": run.name, "minutes": round(last_t / 60, 1), "sides": {}, "wrecks": wrecks, "veh_lost": veh_lost}
    for s in SIDES:
        rows = crowd[s]
        first_out = next((num(r["t"]) / 60 for r in rows if num(r.get("field"), 0) > 0), None)
        at10 = min(rows, key=lambda r: abs(num(r["t"]) - 600)) if rows else None
        men10 = num(at10.get("men"), 0) if at10 else 0
        atbase10 = round(100 * (men10 - num(at10.get("field"), 0)) / men10) if men10 else None
        team10 = num(at10.get("team")) if at10 else None
        span = max(1.0, (last_t - 120) / 60)
        per4 = round(len([t for t in launches[s] if t and t >= 120]) * 4 / span, 1)
        sky = [a for t, a in air[s] if t and t >= 180]
        sky_pct = round(100 * sum(1 for a in sky if a > 0) / len(sky)) if sky else None
        field_cover = [num(r.get("field_above")) for r in rows if num(r.get("field_above"), -1) >= 0]
        out["sides"][s] = {
            "out_min": None if first_out is None else round(first_out, 1),
            "atbase10": atbase10,
            "team10": team10,
            "drone_teams": len(launches[s]),
            "drones_per4": per4,
            "noteam": noteam[s],
            "sky_pct": sky_pct,
            "rides": len(boarded[s]),
            "riding_pct": round(100 * sum(1 for r in riding[s] if r > 0) / len(riding[s])) if riding[s] else None,
            "riding_avg": round(sum(riding[s]) / len(riding[s]), 1) if riding[s] else None,
            "field_overhead": round(sum(field_cover) / len(field_cover)) if field_cover else None,
            "panic_pct": round(sum(threat[s]) / len(threat[s])) if threat[s] else None,
            "danger_standing": round(sum(danger_high[s]) / len(danger_high[s])) if danger_high[s] else None,
            "shot_down": shot_down[s],
            "truck_jobs": jobs[s],
            "truck_unloads": unloads[s],
            "forts": forts[s],
            "armed_teams": len(armed[s]),
            "drone_dead_n": len(drone_dead[s]),
            "drone_dead_standing": round(100 * drone_dead[s].count("STAND") / len(drone_dead[s])) if drone_dead[s] else None,
            "drone_dead_prone": round(100 * drone_dead[s].count("PRONE") / len(drone_dead[s])) if drone_dead[s] else None,
            "lost": lost[s],
            "armour": armour["bought"][s],
            "armour_assault": len(armour_assault[s]),
            "armour_kills": armour["kills"][s],
            "armour_friendly": armour["friendly"][s],
            "armour_lost": armour["lost"][s],
            "op_flights": op["flights"][s],
            "op_goggles_pct": round(100 * op["goggles"][s] / op["flights"][s]) if op["flights"][s] else None,
            "op_still_pct": round(100 * op["still"][s] / op["flights"][s]) if op["flights"][s] else None,
            "op_sorties": op["out"][s],
            "op_launches": op["launch"][s],
            "op_loads": op["loaded"][s],
        }
    return out


CHECKS = [
    ("out", lambda m: m["out_min"] is not None and m["out_min"] <= 3, lambda m: f"{m['out_min']} min"),
    ("atbase", lambda m: m["atbase10"] is not None and m["atbase10"] <= 40, lambda m: f"{m['atbase10']}%"),
    ("team", lambda m: m["team10"] is not None and m["team10"] >= 2.5, lambda m: f"{m['team10']}"),
    ("drones", lambda m: m["drones_per4"] >= 1, lambda m: f"{m['drone_teams']} teams ({m['drones_per4']}/4min, {m['noteam']} refused)"),
    ("sky", lambda m: m["sky_pct"] is None or m["sky_pct"] >= 60, lambda m: "-" if m["sky_pct"] is None else f"{m['sky_pct']}%"),
    ("panic", lambda m: m.get("panic_pct") is None or m["panic_pct"] >= 60,
     lambda m: "-" if m.get("panic_pct") is None else f"{m['panic_pct']}% safe near drones"),
    # judged from 3 drone victims of a side on (24 Oct: one standing victim failed a whole match)
    ("down", lambda m: m.get("drone_dead_standing") is None or m.get("drone_dead_n", 3) < 3 or m["drone_dead_standing"] <= 50,
     lambda m: "-" if m.get("drone_dead_standing") is None else f"drone victims {m['drone_dead_standing']}% standing, {m['drone_dead_prone']}% prone"),
    # The drone teams (24 Oct, kept in KEEP.md): goggles on and the pilot still at 80% of flights, judged from 3 flights.
    ("operators", lambda m: m.get("op_flights", 0) < 3 or (m["op_goggles_pct"] >= 80 and m["op_still_pct"] >= 80),
     lambda m: "-" if not m.get("op_flights") else (f"{m['op_flights']} flights, goggles {m['op_goggles_pct']}%, still {m['op_still_pct']}%, "
                                                    f"{m['op_sorties']} sorties, {m['op_launches']} launches, {m['op_loads']} loads")),
    ("rides", lambda m: m["riding_pct"] >= 25 if m["riding_pct"] is not None else m["rides"] >= 1,
     lambda m: (f"riding in {m['riding_pct']}% of samples, {m['riding_avg']} on average" if m["riding_pct"] is not None
                else f"{m['rides']} teams boarded (old measure)")),
]


def report(card: dict) -> tuple:
    lines = [f"{card['run']}  ({card['minutes']} min, vehicles lost {card.get('veh_lost')}, wrecks removed {card.get('wrecks')})"]
    fails = 0
    for s in SIDES:
        m = card["sides"][s]
        parts = []
        for name, ok, show in CHECKS:
            good = ok(m)
            fails += not good
            parts.append(f"{name} {'ok ' if good else 'FAIL'} {show(m)}")
        lines.append(f"  {s:5} " + " | ".join(parts) + f" | field overhead {m['field_overhead']}% | lost {m['lost']}")
        lines.append(f"        in danger standing {m.get('danger_standing')}% | drones shot down {m.get('shot_down')} | truck jobs {m.get('truck_jobs')}, "
                     f"unloads {m.get('truck_unloads')} | bunkers {m.get('forts')} | armed rides {m.get('armed_teams')} teams"
                     f" | armour {m.get('armour')} bought, {m.get('armour_assault')} into the assault, {m.get('armour_kills')} kills, {m.get('armour_lost')} lost")
    return "\n".join(lines), fails


def latest(prefix_re: str) -> list:
    runs = [r for r in RUNS.iterdir() if r.is_dir() and re.match(prefix_re, r.name) and console(r)]
    runs.sort(key=lambda r: r.stat().st_mtime)
    done = [r for r in runs if console(r).stat().st_size > 2_000_000]
    return done[-1:]


def main() -> int:
    args = sys.argv[1:]
    if args == ["--today"]:
        day = datetime.now().strftime("%Y%m%d")
        runs = sorted((r for r in RUNS.iterdir() if r.is_dir() and f"-{day}-" in r.name and re.match(r"(w\d+|b)-", r.name)
                       and console(r) and console(r).stat().st_size > 2_000_000), key=lambda r: r.name[-6:])
    elif args:
        runs = [Path(a) if Path(a).is_dir() else RUNS / a for a in args]
    else:
        runs = latest(r"w\d+-") + latest(r"b-")
    total = 0
    for run in runs:
        card = measure(run)
        if not card:
            continue
        text, fails = report(card)
        total += fails
        print(text)
        with open(RUNS.parent / "scorecards.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(card) + "\n")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
