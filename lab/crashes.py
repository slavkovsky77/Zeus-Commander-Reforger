"""Crashes of the watched matches: what kind, and what happened just before.

Martin (21 Oct): "a lot of crashes ... it's kind of random, couldn't you improve logging?". The game crashes inside
its own entity update (or hangs 300 s and closes itself); the console log runs right up to that moment. For each
crashed match this prints the kind of crash (the game's reason and first code address), the game time, and the
last 30 s of what our scripts did to the world ([ZCR][ENT], from 21 Oct 19:30), the commander tick's steps
([ZCR][STEP]/[SLOW]), armour events, wrecks removed, drones, and AI Conflict's vehicle deletions.

Then, for each kind of event, how many crashes had one in the 10 s before - against how often a 10-s window of a
match that did not crash has one (the "lift": far above 1 points at a trigger, about 1 is background).

    python lab/crashes.py              # watched matches of the last 2 days
    python lab/crashes.py --days 7 --all
    python lab/crashes.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / ".runtime" / "runs"
CACHE = ROOT / ".runtime" / "crashes_cache"
STRESS = ROOT / ".runtime" / "stress.jsonl"
STAMP = re.compile(r"^\s*(\d\d):(\d\d):(\d\d)\.(\d+)")
GAME_T = re.compile(r"\[ZCR\]\[[A-Z]+\] t=(\d+)")

# Events worth lining up with a crash: name -> test on a console line.
EVENTS = {
    "our spawn": lambda l: "[ZCR][ENT]" in l and " op=spawn " in l,
    "our delete": lambda l: "[ZCR][ENT]" in l and " op=delete " in l,
    "our destroy": lambda l: "[ZCR][ENT]" in l and " op=destroy " in l,
    "our relocate": lambda l: ("[ZCR][ENT]" in l and " op=move " in l) or "event=RELOCATED" in l,
    "our crew/kick/board": lambda l: "[ZCR][ENT]" in l and (" op=crew " in l or " op=kick " in l or " op=board " in l),
    "wreck removed": lambda l: "[ZCR][WRECK]" in l and "removed=" in l,
    "armour event": lambda l: "[ZCR][ARMOUR]" in l and "event=STATUS" not in l and "event=ORDER" not in l,
    "drone hit": lambda l: "FPVAI:" in l and " detonated " in l,
    "drone station removed": lambda l: "FPVAI:" in l and "station removed" in l,
    "drone shot down": lambda l: "shot down an enemy drone" in l or ("[ZCR][ANTIDRONE]" in l and "down" in l),
    "vehicle deleted (AICF)": lambda l: "VEHICLE_DELETE_REQU" in l,
    "building placed (AICF)": lambda l: "[CONSTRUCTION_PLACED]" in l,
    "vehicle destroyed": lambda l: "[ZCR][LOSS]" in l and "kind=vehicle" in l,
}
SHOW = ("[ZCR][ENT]", "[ZCR][SLOW]", "[ZCR][STEP]", "[ZCR][WRECK]", "VEHICLE_DELETE_REQU", "station removed",
        " detonated ", "event=RELOCATED", "event=RECREW", "event=REMOUNT", "event=LOST", "[CONSTRUCTION_PLACED]")


def seconds(line: str) -> float | None:
    m = STAMP.match(line)
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000 if m else None


def kind_of(crash_log: Path, console_tail: str) -> str:
    text = crash_log.read_text(encoding="utf-8", errors="replace") if crash_log.exists() else ""
    if "Application hangs" in console_tail:
        return "hang (closed itself after 300 s)"
    blocks = text.split("------------------------------------")
    last = blocks[-1] if blocks else ""
    reasons = re.findall(r"^Reason: (.*)$", text, re.M)
    final = reasons[-1] if reasons else ""
    frames = re.findall(r"0x7ff[0-9a-f]{9}", last)
    bad_matrix = any("BadMatrix" in r or "BadVec" in r for r in reasons[-4:])
    if "Access violation" in final:
        tag = "entity update" if "0x7ff7168a6984" in frames else (frames[1] if len(frames) > 1 else "?")
        return ("bad position, then " if bad_matrix else "") + f"access violation ({tag})"
    return final[:60] or "unknown"


def read_run(run: Path) -> dict | None:
    """One run's crash facts; a finished run's (log untouched for 3 minutes) are kept in .runtime/crashes_cache."""
    logs = sorted(run.glob("logs/*/console.log"))
    if not logs:
        return None
    console = logs[-1]
    st = console.stat()
    key = CACHE / f"{run.name}.json"
    if key.exists():
        try:
            cached = json.loads(key.read_text(encoding="utf-8"))
            if cached.get("size") == st.st_size:
                return cached.get("row")
        except (OSError, ValueError):
            pass
    row = scan_run(run, console)
    if time.time() - st.st_mtime > 180:
        CACHE.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps({"size": st.st_size, "row": row}), encoding="utf-8")
    return row


def scan_run(run: Path, console: Path) -> dict | None:
    crashed = bool(list(console.parent.glob("*.mdmp")))
    lines = console.read_text(encoding="utf-8", errors="replace").splitlines()
    stamped = [(seconds(l), l) for l in lines]
    stamped = [(t, l) for t, l in stamped if t is not None]
    if len(stamped) < 100:
        return None
    first, last = stamped[0][0], stamped[-1][0]
    if last < first:
        last += 86400
    events = {k: [] for k in EVENTS}
    game_t = None
    speed, armour, drones = 1.0, False, False
    for t, l in stamped:
        if "[ZCR][SPEED]" in l and "switch=1" in l:
            m = re.search(r"multiplier=([\d.]+)", l)
            speed = float(m.group(1)) if m else speed
        if not armour and "[ZCR][ARMOUR]" in l and "event=BOUGHT" in l:
            armour = True
        if not drones and "FPVAI:" in l:
            drones = True
        if t < first:
            t += 86400
        g = GAME_T.search(l)
        if g:
            game_t = int(g[1])
        for k, test in EVENTS.items():
            if test(l):
                events[k].append(t)
    out = {"run": run.name, "crashed": crashed, "first": first, "last": last, "minutes": (last - first) / 60,
           "game_t": game_t, "events": events, "speed": speed, "armour": armour, "drones": drones,
           "watched": bool(re.match(r"w\d+-", run.name)), "day": time.strftime("%Y-%m-%d", time.localtime(console.stat().st_mtime))}
    if crashed:
        tail = "\n".join(l for _, l in stamped[-40:])
        out["kind"] = kind_of(console.parent / "crash.log", tail)
        out["before"] = [l.strip()[:190] for t, l in stamped if last - 30 <= (t if t >= first else t + 86400) <= last
                         and any(s in l for s in SHOW)]
    return out


def lift(rows: list[dict], window: float = 10) -> list[tuple]:
    crashed = [r for r in rows if r["crashed"]]
    clean = [r for r in rows if not r["crashed"] and r["minutes"] > 5]
    table = []
    for k in EVENTS:
        hit = sum(1 for r in crashed if any(r["last"] - window <= t <= r["last"] for t in r["events"][k]))
        # Base rate: the share of a clean match's 10-s windows (every 10 s) that hold one.
        win = have = 0
        for r in clean:
            ts = sorted(r["events"][k])
            t = r["first"] + window
            j = 0
            while t <= r["last"]:
                while j < len(ts) and ts[j] < t - window:
                    j += 1
                win += 1
                have += 1 if j < len(ts) and ts[j] <= t else 0
                t += window
        base = have / win if win else 0
        rate = hit / len(crashed) if crashed else 0
        table.append((k, hit, len(crashed), base, rate / base if base else (float("inf") if hit else 0)))
    return table


def split(rows: list[dict]) -> list[dict]:
    """Crashes per game hour by speed-up, armour and drones (runs of 3+ minutes)."""
    by = {}
    for r in rows:
        if r["minutes"] < 3:
            continue
        k = (r.get("speed", 1), r.get("armour", False), r.get("drones", False))
        s = by.setdefault(k, {"speed": k[0], "armour": k[1], "drones": k[2], "runs": 0, "crashes": 0, "game_h": 0.0})
        s["runs"] += 1
        s["crashes"] += 1 if r["crashed"] else 0
        s["game_h"] += r["minutes"] / 60 * k[0]
    out = sorted(by.values(), key=lambda s: (s["armour"], s["drones"], s["speed"]))
    for s in out:
        s["game_h"] = round(s["game_h"], 1)
        s["per_game_h"] = round(s["crashes"] / s["game_h"], 3) if s["game_h"] else 0
    return out


def stress_rows() -> list[dict]:
    if not STRESS.exists():
        return []
    return [json.loads(l) for l in STRESS.read_text(encoding="utf-8").splitlines() if l.strip()]


def stress_summary(rows: list[dict]) -> list[dict]:
    by = {}
    for r in rows:
        s = by.setdefault(r["variant"], {"variant": r["variant"], "matches": 0, "crashes": 0, "hours": 0.0, "first_crash_min": []})
        s["matches"] += 1
        s["hours"] += (r.get("minutes") or 0) / 60
        if r.get("crashed"):
            s["crashes"] += 1
            s["first_crash_min"].append(r.get("minutes"))
    for s in by.values():
        s["hours"] = round(s["hours"], 2)
        s["per_h"] = round(s["crashes"] / s["hours"], 2) if s["hours"] else 0
    return list(by.values())


def report(days: float = 4) -> dict:
    """Everything the lab app's Crashes tab shows."""
    since = time.time() - days * 86400
    runs = [r for r in RUNS.iterdir() if r.is_dir() and r.stat().st_mtime >= since]
    rows = [x for x in (read_run(r) for r in sorted(runs, key=lambda p: p.stat().st_mtime)) if x]
    watched = [r for r in rows if r["watched"]]
    stress = [r for r in rows if r["run"].startswith("stress-")]
    fmt = lambda t: time.strftime("%H:%M", time.gmtime(t % 86400))
    shown = [r for r in rows if r["crashed"] and (r["watched"] or r["run"].startswith("stress-"))]
    crashes = [{"run": r["run"], "day": r["day"], "at": fmt(r["last"]), "minutes": round(r["minutes"], 1), "game_t": r["game_t"],
                "kind": r.get("kind", ""), "armour": r["armour"], "speed": r["speed"], "before": r.get("before", [])[-12:]}
               for r in shown]
    kinds = {}
    for c in crashes:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    srows = stress_rows()
    return {"days": days, "watched": len(watched), "crashes": crashes[::-1], "kinds": kinds,
            "split": split(rows), "lift": [{"event": k, "hit": h, "of": n, "base": round(b, 3), "lift": (None if l == float("inf") else round(l, 2))}
                                           for k, h, n, b, l in lift(watched)],
            "stress": stress_summary(srows), "stress_runs": srows[-30:][::-1], "stress_running": len(stress) > 0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=2, help="runs started in the last N days")
    ap.add_argument("--all", action="store_true", help="headless runs too, not only the watched matches (w*)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    since = time.time() - a.days * 86400
    runs = [r for r in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime)
            if r.is_dir() and r.stat().st_mtime >= since and (a.all or re.match(r"w\d+-", r.name))]
    rows = [x for x in (read_run(r) for r in runs) if x]
    crashed = [r for r in rows if r["crashed"]]
    table = lift(rows)
    if a.json:
        for r in rows:
            r.pop("events", None)
        print(json.dumps({"matches": len(rows), "crashes": crashed, "lift": table}, indent=1, default=str))
        return 0
    fmt = lambda t: time.strftime("%H:%M:%S", time.gmtime(t % 86400))
    print(f"{len(crashed)} crashes in {len(rows)} matches\n")
    for r in crashed:
        print(f"== {r['run']}  crashed {fmt(r['last'])} after {r['minutes']:.1f} min, game t={r['game_t']}  [{r['kind']}]")
        for l in r["before"][-14:]:
            print("   ", l)
        print()
    print("kinds:")
    for k in sorted({r["kind"] for r in crashed}):
        print(f"  {sum(1 for r in crashed if r['kind'] == k)}  {k}")
    print("\nevent in the 10 s before a crash  (crashes with one | share of clean 10-s windows with one | lift)")
    for k, hit, n, base, lf in sorted(table, key=lambda x: -x[4] if x[4] != float("inf") else -1e9):
        print(f"  {k:24s} {hit:2d}/{n:<2d} | {base:5.0%} | {'-' if not hit else ('new' if lf == float('inf') else f'{lf:.1f}x')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
