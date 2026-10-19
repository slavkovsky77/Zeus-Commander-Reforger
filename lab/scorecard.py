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
  rides    at least one team boarded a vehicle
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
    lost = {s: 0 for s in SIDES}
    last_t = 0
    for line in open(log, encoding="utf-8", errors="replace"):
        if "[ZCR][" not in line and "BOARDING_PHASE_STARTED" not in line:
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
        elif "BOARDING_PHASE_STARTED" in line and side in SIDES:
            boarded[side].add(d.get("slot"))
        elif "[ZCR][LOSS]" in line:
            v = d.get("victim_side") or d.get("side")
            if v in SIDES:
                lost[v] += 1
    out = {"run": run.name, "minutes": round(last_t / 60, 1), "sides": {}}
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
            "field_overhead": round(sum(field_cover) / len(field_cover)) if field_cover else None,
            "lost": lost[s],
        }
    return out


CHECKS = [
    ("out", lambda m: m["out_min"] is not None and m["out_min"] <= 3, lambda m: f"{m['out_min']} min"),
    ("atbase", lambda m: m["atbase10"] is not None and m["atbase10"] <= 40, lambda m: f"{m['atbase10']}%"),
    ("team", lambda m: m["team10"] is not None and m["team10"] >= 2.5, lambda m: f"{m['team10']}"),
    ("drones", lambda m: m["drones_per4"] >= 1, lambda m: f"{m['drone_teams']} teams ({m['drones_per4']}/4min, {m['noteam']} refused)"),
    ("sky", lambda m: m["sky_pct"] is None or m["sky_pct"] >= 60, lambda m: "-" if m["sky_pct"] is None else f"{m['sky_pct']}%"),
    ("rides", lambda m: m["rides"] >= 1, lambda m: f"{m['rides']}"),
]


def report(card: dict) -> tuple:
    lines = [f"{card['run']}  ({card['minutes']} min)"]
    fails = 0
    for s in SIDES:
        m = card["sides"][s]
        parts = []
        for name, ok, show in CHECKS:
            good = ok(m)
            fails += not good
            parts.append(f"{name} {'ok ' if good else 'FAIL'} {show(m)}")
        lines.append(f"  {s:5} " + " | ".join(parts) + f" | field overhead {m['field_overhead']}% | lost {m['lost']}")
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
