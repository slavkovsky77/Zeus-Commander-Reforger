"""The lab monitor's data: what the loop is doing now, the goals, the iteration log, the latest matches,
commits and review notes - written as two JSON documents that Claude pushes to the monitor page's
database (the Commander Lab monitor artifact, [pages] monitor in lab/lab.local.toml).

    python lab/monitor.py now --step investigate --goal trucks --doing "following one truck job"
    python lab/monitor.py log --goal trucks --finding "..." --change "..." --commit 5ce12a1 \
        --before "first truck at min 15-27" --after "first truck at min 14" --verdict better
    python lab/monitor.py build          # writes .runtime/monitor/state.json and log.json

Then push them (the record skill): ArtifactData list collection "lab" for the versions, and one batch
of two sets - lab/state from .runtime/monitor/state.json, lab/log from .runtime/monitor/log.json -
each with its if_version (omit it the first time).

now   what the loop is doing (step: measure, investigate, fix, verify, record, waiting, idle)
log   one finished iteration: the goal, what was wrong, what changed, before -> after, the verdict
build everything else is read from the lab's own files: goals.toml judged on the matches
      (lab/goals.py), the watch loop's log, running servers, both repos' commits, the review notes.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402
import goals as goals_mod  # noqa: E402
import measures  # noqa: E402
import scorecard  # noqa: E402

OUT = ROOT / ".runtime" / "monitor"
NOW = OUT / "now.json"
LOG = ROOT / ".runtime" / "loop_log.jsonl"
MATCH_KEYS = ["truck_first_min", "truck_unloads", "front_supply_pct", "depots", "forts", "drones_lost_water",
              "armour_assault", "armour_kills", "scorecard_fails", "lost"]


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def watched_now() -> dict:
    """The watch loop's current match from its log: running (no video or early end after it) or the last one."""
    log = ROOT / ".runtime" / "watch_day.out"
    if not log.exists():
        return {}
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
    last, after = None, []
    for l in lines:
        m = re.match(r"(\d\d:\d\d:\d\d) match (\d+): (\w+), (.+?), (\d+) min, build (\S+?),", l)
        if m:
            last, after = m, []
        elif last:
            after.append(l)
    if not last:
        return {}
    ended = next((a for a in after if " video " in a or "ended early" in a), None)
    speed = next((re.search(r"measured ([\d.]+)x", a).group(1) for a in after if "measured" in a), "1")
    out = {"match": int(last.group(2)), "map": last.group(3), "sides": last.group(4), "length_min": int(last.group(5)),
           "build": last.group(6), "started": last.group(1), "speed": float(speed), "running": ended is None}
    if ended is None:
        start = datetime.combine(datetime.now().date(), datetime.strptime(last.group(1), "%H:%M:%S").time())
        out["game_min"] = max(0, round((datetime.now() - start).total_seconds() * float(speed) / 60 - 2))
    early = next((a for a in after if "ended early" in a), None)
    if early:
        out["ended_early"] = early.split("ended early: ", 1)[-1]
    return out


def servers() -> list:
    """Lab servers and games running now (their run folder names)."""
    try:
        ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                             "Get-CimInstance Win32_Process -Filter \"Name like 'ArmaReforger%'\" | ForEach-Object { $_.CommandLine }"],
                            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    return sorted({m.group(1) for m in re.finditer(r"runs[\\/]([\w.-]+)", ps)})


def commits() -> list:
    out = []
    for name, repo in (("commander", ROOT), ("ai-conflict", config.path("paths.ai_conflict"))):
        try:
            text = subprocess.run(["git", "-C", str(repo), "log", "-8", "--format=%h|%ad|%s", "--date=format:%d.%m %H:%M"],
                                  capture_output=True, text=True, timeout=20).stdout
        except Exception:
            continue
        for l in text.splitlines():
            h, d, s = l.split("|", 2)
            out.append({"repo": name, "hash": h, "at": d, "text": s[:160]})
    return sorted(out, key=lambda c: datetime.strptime(c["at"], "%d.%m %H:%M"), reverse=True)[:12]


def notes(n: int = 8) -> list:
    path = config.path("paths.notes")
    if not path.exists():
        return []
    rows = []
    for l in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\| (\d+) \| (.+?) \| (.+?) \|\s*$", l)
        if m:
            rows.append({"no": int(m.group(1)), "text": m.group(2)[:220], "status": m.group(3)[:300]})
    return rows[-n:][::-1]


def goal_rows() -> list:
    out = []
    for i, goal in enumerate(goals_mod.load()):
        if goal.get("status") == "paused":
            continue
        of = int(re.findall(r"\d+", goal.get("met_when", "2 of 3"))[1])
        res = goals_mod.judge(goal, goals_mod.runs_for(goal.get("matches", "watched"), max(3, of), goal.get("needs", [])))
        hist = goals_mod.judge(goal, goals_mod.runs_for(goal.get("matches", "watched"), 12, goal.get("needs", [])))
        out.append({
            "id": res["id"], "order": i, "title": res["title"], "status": res["status"], "wish": res["wish"],
            "notes": res["notes"], "met": res["met"], "passed": res["passed"], "of": res["of"], "need": res["need"],
            "matches": [{"run": r["run"], "when": goals_mod.when(r["run"]), "ok": r["ok"],
                         "cells": [{"key": c["key"], "target": c["target"], "shown": c["shown"], "ok": c["ok"]} for c in r["cells"]]}
                        for r in res["rows"][-3:]],
            "history": [{"when": goals_mod.when(r["run"]), "ok": r["ok"]} for r in hist["rows"]],
        })
    return out


def match_rows(n: int = 10) -> list:
    runs = goals_mod.runs_for("watched", n, [])
    out = []
    for r in reversed(runs):
        m = measures.measure(r)
        out.append({"run": r.name, "when": goals_mod.when(r.name), "minutes": m.get("minutes"),
                    "ended_early": m.get("ended_early", 0), **{k: m.get(k) for k in MATCH_KEYS}})
    return out


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    now = json.loads(NOW.read_text(encoding="utf-8")) if NOW.exists() else {}
    gl = goal_rows()
    broke = [g["id"] for g in gl if g["status"] == "met" and g["met"] is False]
    nxt = next((g["id"] for g in gl if g["status"] == "active" and g["met"] is not True), None)
    pages = {k: v for k, v in (config.get("pages", {}) or {}).items() if v}
    state = {"updated": stamp(), "now": now, "watched": watched_now(), "servers": servers(), "goals": gl,
             "broke": broke, "next": nxt, "matches": match_rows(), "commits": commits(), "notes": notes(), "pages": pages}
    (OUT / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    items = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()] if LOG.exists() else []
    (OUT / "log.json").write_text(json.dumps({"updated": stamp(), "items": items[-60:][::-1]}, indent=1), encoding="utf-8")
    print(f"wrote {OUT / 'state.json'} ({len(gl)} goals, {len(state['matches'])} matches) and log.json ({len(items)} iterations)")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("now")
    n.add_argument("--step", required=True)
    n.add_argument("--goal", default="")
    n.add_argument("--doing", default="")
    n.add_argument("--next", default="")
    lg = sub.add_parser("log")
    for f in ("goal", "finding", "change", "commit", "before", "after", "verdict", "title"):
        lg.add_argument(f"--{f}", default="")
    sub.add_parser("build")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd == "now":
        NOW.write_text(json.dumps({"at": stamp(), "step": a.step, "goal": a.goal, "doing": a.doing, "next": a.next}), encoding="utf-8")
    elif a.cmd == "log":
        entry = {"at": stamp(), **{k: getattr(a, k) for k in ("goal", "title", "finding", "change", "commit", "before", "after", "verdict")}}
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
