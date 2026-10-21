"""The measures goals are judged by: numbers per match, read from a match's server log.

    python lab/measures.py RUN_DIR            # every measure of one match
    python lab/measures.py --list             # the measures and what each one counts

A measure is per side (a value for US and for USSR) or per match (one value). Every per-side value of
lab/scorecard.py is a measure too (out_min, atbase10, drones_per4, sky_pct, panic_pct, riding_pct,
truck_jobs, truck_unloads, forts, armour_assault, armour_kills, ...). To add one: parse it in extra()
below, describe it in MEASURES, and a goal in goals.toml can use it by its key.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scorecard  # noqa: E402

SIDES = scorecard.SIDES
KV = re.compile(r"(\w+)=(\S*)")

# key: (per, what it counts). Scorecard keys are added at the end of the file.
MEASURES = {
    "minutes": ("match", "game minutes the match ran - the watch loop's own record for watched matches, else the last commander log line"),
    "ended_early": ("match", "1 when a watched match ended early with a crash dump (a crash or a freeze); stopped by hand: 0"),
    "drones_lost_water": ("match", "drones the drone mod lost over the sea (its 'lost ... WST_OCEAN' line)"),
    "drones_lost": ("match", "drones the drone mod lost without a detonation, anywhere"),
    "dry_routes": ("match", "drone teams sent round the sea by a dry via point ([ZCR][DRONES] dry_route=1)"),
    "truck_first_min": ("side", "game minute of the side's first supply truck job (none: no value)"),
    "truck_loads": ("side", "supply truck loads at a source"),
    "truck_drivers_killed": ("side", "supply truck jobs ended by the driver's death"),
    "depots": ("side", "supply depots the side built (light and heavy)"),
    "front_supply_pct": ("side", "the side's front bases (not its HQ), average supplies in % of their maximum at the end"),
    "scorecard_fails": ("match", "lab/scorecard.py hard checks failed, both sides (what the watcher sees)"),
    "fps": ("match", "the game's average FPS over the match (the engine's 'FPS:' line every 10 s, -logStats)"),
    "fps_low": ("match", "the game's FPS at the slowest tenth of the match (10th percentile of those lines)"),
    # 21 Oct night (Martin's complaints of the day, lab app 'Goals'):
    "jams": ("match", "vehicles jammed - a driven vehicle still 45 game s with another vehicle within 10 m ([ZCR][JAM]), both sides"),
    "stuck_vehicles": ("match", "driven vehicles still 45 game s with no vehicle near ([ZCR][STUCKVEH]), both sides"),
    "runovers": ("match", "soldiers killed with no killer next to a moving vehicle of their side (runover= on [ZCR][LOSS])"),
    "giveways": ("match", "armour that backed off for a vehicle blocking it head-on ([ZCR][ARMOUR] event=GIVEWAY)"),
    "armour_still": ("match", "armour stuck on its way two minutes ([ZCR][ARMOUR] event=STILL), both sides"),
    "drive_kmh": ("match", "median speed of AI-driven vehicles while moving (over 3 km/h; [ZCR][DRIVE] moving_kmh, older logs median_kmh), both sides"),
    "site_search_s": ("match", "median game seconds from a building order to its site placed (both sides; AI Conflict's real ms x the speed-up)"),
    "search_gave_up_pct": ("match", "% of building site searches that found no site (SEARCH_BUDGET_EXHAUSTED) of those that ended"),
}
# Measures with no value when the thing never happened (no truck all match): that fails a target, it isn't "no data".
NO_VALUE_FAILS = {"truck_first_min"}
SCORECARD_KEYS = ["out_min", "atbase10", "team10", "drone_teams", "drones_per4", "sky_pct", "rides", "riding_pct",
                  "panic_pct", "danger_standing", "shot_down", "truck_jobs", "truck_unloads", "forts", "armed_teams",
                  "drone_dead_standing", "drone_dead_prone", "lost", "armour", "armour_assault", "armour_kills",
                  "armour_lost", "field_overhead"]
for _k in SCORECARD_KEYS:
    MEASURES.setdefault(_k, ("side", "lab/scorecard.py, see its header"))

_cache = {}


def extra(run: Path) -> dict:
    log = scorecard.console(run)
    out = {"drones_lost_water": 0, "drones_lost": 0, "dry_routes": 0,
           "truck_first_min": {s: None for s in SIDES}, "truck_loads": {s: 0 for s in SIDES},
           "truck_drivers_killed": {s: 0 for s in SIDES}, "depots": {s: 0 for s in SIDES},
           "front_supply_pct": {s: None for s in SIDES}, "fps": None, "fps_low": None,
           "jams": 0, "stuck_vehicles": 0, "drive_kmh": None, "runovers": 0, "giveways": 0, "armour_still": 0, "site_search_s": None, "search_gave_up_pct": None}
    if not log:
        return out
    game_t = 0
    supply = {}
    fps = []
    speed = 1.0
    decided, placed_s, gave_up = {}, [], 0
    kmh = []
    for line in open(log, encoding="utf-8", errors="replace"):
        if "[ZCR][DRIVE]" in line and "median_kmh=" in line:
            # The moving vehicles' median (from 21 Oct night); older logs: the median of all driven vehicles.
            km = re.search(r"moving_kmh=(\d+)", line) or re.search(r"median_kmh=(\d+)", line)
            if km:
                kmh.append(int(km.group(1)))
            continue
        if "[ZCR][JAM]" in line:
            out["jams"] += 1
            continue
        if "[ZCR][STUCKVEH]" in line:
            out["stuck_vehicles"] += 1
            continue
        if "[ZCR][LOSS]" in line and " runover=" in line:
            out["runovers"] += 1
        if "[ZCR][ARMOUR]" in line:
            if "event=GIVEWAY" in line:
                out["giveways"] += 1
            elif "event=STILL" in line:
                out["armour_still"] += 1
        if "[ZCR][SPEED]" in line and "switch=1" in line:
            sp = re.search(r"multiplier=([\d.]+)", line)
            if sp:
                speed = float(sp.group(1))
        if "[CONSTRUCTION_" in line:
            cm = re.search(r"\[(CONSTRUCTION_[A-Z_]+)\].*?t_ms=(\d+) token=(\S+)", line)
            if cm:
                ev, tms, tok = cm.group(1), int(cm.group(2)), cm.group(3)
                if ev == "CONSTRUCTION_DECISION":
                    decided[tok] = tms
                elif ev == "CONSTRUCTION_PLACED" and tok in decided:
                    placed_s.append((tms - decided.pop(tok)) / 1000 * speed)
                elif ev == "CONSTRUCTION_CANCELLED" and "SEARCH_BUDGET_EXHAUSTED" in line and tok in decided:
                    decided.pop(tok)
                    gave_up += 1
        if "DEFAULT" in line and ": FPS: " in line:
            f = re.search(r": FPS: ([\d.]+)", line)
            if f:
                fps.append(float(f.group(1)))
            continue
        g = re.search(r"\[ZCR\]\[\w+\] t=(\d+)", line)
        if g:
            game_t = int(g.group(1))
        if "FPVAI: drone" in line and " lost (" in line:
            out["drones_lost"] += 1
            if "WST_OCEAN" in line:
                out["drones_lost_water"] += 1
            continue
        if "dry_route=1" in line:
            out["dry_routes"] += 1
            continue
        if "LOGISTICS_" in line or "CONSTRUCTION_COMPLETED" in line or "[ZCR][SUPPLY]" in line:
            d = dict(KV.findall(line))
            side = d.get("faction") or d.get("side")
            if side not in SIDES:
                continue
            if "LOGISTICS_JOB_RESERVED" in line and out["truck_first_min"][side] is None:
                out["truck_first_min"][side] = round(game_t / 60, 1)
            elif "LOGISTICS_LOAD_COMMITTED" in line:
                out["truck_loads"][side] += 1
            elif "LOGISTICS_CONTROL_LOST" in line and d.get("driver_alive") == "0":
                out["truck_drivers_killed"][side] += 1
            elif "CONSTRUCTION_COMPLETED" in line and d.get("type", "").endswith("DEPOT"):
                out["depots"][side] += 1
            elif "[ZCR][SUPPLY]" in line and d.get("main") == "0" and d.get("pct"):
                supply[(side, d.get("base"))] = float(d["pct"])
    for s in SIDES:
        vals = [v for (side, _), v in supply.items() if side == s]
        out["front_supply_pct"][s] = round(sum(vals) / len(vals)) if vals else None
    if kmh:
        out["drive_kmh"] = sorted(kmh)[len(kmh) // 2]
    if placed_s:
        out["site_search_s"] = round(sorted(placed_s)[len(placed_s) // 2])
    if placed_s or gave_up:
        out["search_gave_up_pct"] = round(100 * gave_up / (len(placed_s) + gave_up))
    if fps:
        out["fps"] = round(sum(fps) / len(fps), 1)
        out["fps_low"] = sorted(fps)[len(fps) // 10]
    return out


def measure(run: Path) -> dict:
    """Every measure of a match: {key: value} for a match measure, {key: {side: value}} for a side one."""
    key = str(run)
    if key in _cache:
        return _cache[key]
    # Finished matches are measured once: .runtime/measures/<run>.json, redone when the log or this file changes.
    log = scorecard.console(run)
    stamp = f"{log.stat().st_size}-{int(log.stat().st_mtime)}-{int(Path(__file__).stat().st_mtime)}" if log else ""
    disk = scorecard.RUNS.parent / "measures" / f"{run.name}.json"
    if log and disk.exists():
        saved = json.loads(disk.read_text(encoding="utf-8"))
        if saved.get("_stamp") == stamp:
            _cache[key] = saved["values"]
            return saved["values"]
    card = scorecard.measure(run)
    out = {}
    if card:
        out["minutes"] = card["minutes"]
        for k in SCORECARD_KEYS:
            out[k] = {s: card["sides"][s].get(k) for s in SIDES}
        _, fails = scorecard.report(card)
        out["scorecard_fails"] = fails
    out.update(extra(run))
    # A watched match: the watch loop's own record of how long it ran and why it ended.
    watched = scorecard.RUNS.parent / "watch_matches.jsonl"
    if watched.exists():
        for line in open(watched, encoding="utf-8", errors="replace"):
            if run.name in line:
                rec = json.loads(line)
                if Path(rec.get("server_profile", "")).name == run.name:
                    out["minutes"] = rec.get("minutes", out.get("minutes"))
                    # A crash or freeze leaves a dump; a match stopped by hand (the owner, the loop) doesn't count.
                    dumps = list(run.glob("logs/*/*.mdmp"))
                    out["ended_early"] = 1 if rec.get("ended") and dumps else 0
    _cache[key] = out
    if log:
        disk.parent.mkdir(parents=True, exist_ok=True)
        disk.write_text(json.dumps({"_stamp": stamp, "values": out}), encoding="utf-8")
    return out


def main() -> int:
    if "--list" in sys.argv:
        for k, (per, what) in MEASURES.items():
            print(f"{k:22} per {per:5}  {what}")
        return 0
    for a in sys.argv[1:]:
        run = Path(a) if Path(a).is_dir() else scorecard.RUNS / a
        print(run.name)
        print(json.dumps(measure(run), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
