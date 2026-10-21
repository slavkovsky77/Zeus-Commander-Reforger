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
    logs = sorted(run.glob("logs/*/console.log"))
    if not logs:
        return None
    console = logs[-1]
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
    for t, l in stamped:
        if t < first:
            t += 86400
        g = GAME_T.search(l)
        if g:
            game_t = int(g[1])
        for k, test in EVENTS.items():
            if test(l):
                events[k].append(t)
    out = {"run": run.name, "crashed": crashed, "first": first, "last": last, "minutes": (last - first) / 60,
           "game_t": game_t, "events": events}
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
