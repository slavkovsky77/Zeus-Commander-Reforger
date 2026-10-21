"""Where the goals stand: every goal of goals.toml judged on the latest matches, and the next one to work on.

    python lab/goals.py                  # each goal on its last 3 matches (watched ones by default)
    python lab/goals.py --last 5         # on the last 5
    python lab/goals.py --runs R1 R2     # on these matches
    python lab/goals.py --json           # also writes .runtime/goals.json (for the pages)

A goal's measure passes in a match when its value meets the target - for a side measure, both sides'
values. A goal is met when all its measures pass in enough of its matches (met_when, "2 of 3"). The next
goal is the first active one, in file order, that is not met. Exit code 1 when an active goal is not met
or a met goal broke (a regression).
"""
import argparse
import json
import operator
import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import measures  # noqa: E402
import scorecard  # noqa: E402

OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, ">": operator.gt, "<": operator.lt}
KIND = {"watched": r"w\d+-", "headless": r"(?!w\d+-)", "any": r""}


def load(path: Path = ROOT / "goals.toml") -> list:
    with open(path, "rb") as f:
        return tomllib.load(f).get("goal", [])


def check(value, target: str):
    """True / False, or None when there is no value."""
    m = re.match(r"\s*(>=|<=|==|>|<)\s*(-?[\d.]+)\s*$", target)
    if not m:
        raise ValueError(f"bad target {target!r}")
    if value is None:
        return None
    return OPS[m.group(1)](float(value), float(m.group(2)))


def runs_for(kind: str, last: int, needs: list) -> list:
    pattern = KIND.get(kind, kind)
    # Finished matches only (metrics.json is written at the end) - a running match's log is still growing.
    found = [r for r in scorecard.RUNS.iterdir() if r.is_dir() and re.match(pattern, r.name) and (r / "metrics.json").exists()
             and scorecard.console(r) and scorecard.console(r).stat().st_size > 2_000_000]
    found.sort(key=lambda r: r.stat().st_mtime)
    if "armour" in needs:
        found = [r for r in found if any((measures.measure(r).get("armour") or {}).get(s) for s in measures.SIDES)]
    # The newest first while measuring, at most 'last'.
    return found[-last:]


def judge(goal: dict, runs: list) -> dict:
    rows = []
    for run in runs:
        m = measures.measure(run)
        cells = []
        for spec in goal.get("measure", []):
            key, target = spec["key"], spec["target"]
            per = measures.MEASURES.get(key, ("match",))[0]
            value = m.get(key)
            never = key in measures.NO_VALUE_FAILS       # no value: it never happened - a fail, shown "never"
            if per == "side" and isinstance(value, dict):
                results = [False if (value.get(s) is None and never) else check(value.get(s), target) for s in measures.SIDES]
                ok = False if False in results else (None if None in results else True)
                shown = " ".join(f"{s} {value.get(s) if value.get(s) is not None else ('never' if never else '-')}" for s in measures.SIDES)
            else:
                ok = check(value, target)
                shown = "-" if value is None else str(value)
            cells.append({"key": key, "target": target, "value": value, "shown": shown, "ok": ok})
        rows.append({"run": run.name, "ok": all(c["ok"] for c in cells), "cells": cells})
    need, of = (int(x) for x in re.findall(r"\d+", goal.get("met_when", "2 of 3"))[:2])
    passed = sum(1 for r in rows if r["ok"])
    if len(rows) < of:
        met = None                     # not enough matches yet
    else:
        met = passed >= need
    return {"id": goal["id"], "title": goal.get("title", ""), "status": goal.get("status", "active"),
            "wish": goal.get("wish", ""), "notes": goal.get("notes", []), "met": met, "passed": passed,
            "of": len(rows), "need": need, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=3)
    ap.add_argument("--runs", nargs="*")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    results, nxt, broke = [], None, []
    for goal in load():
        if goal.get("status") == "paused":
            continue
        if a.runs:
            runs = [Path(r) if Path(r).is_dir() else scorecard.RUNS / r for r in a.runs]
        else:
            runs = runs_for(goal.get("matches", "watched"), a.last, goal.get("needs", []))
        res = judge(goal, runs)
        results.append(res)
        verdict = {True: "MET", False: "NOT MET", None: "TOO FEW MATCHES"}[res["met"]]
        print(f"{res['id']:13} [{res['status']}] {verdict} - {res['passed']} of {res['of']} matches pass "
              f"(needs {goal.get('met_when', '2 of 3')}) - {res['title']}")
        for row in res["rows"]:
            parts = [f"{c['key']} {c['shown']} ({c['target']}) {'ok' if c['ok'] else ('-' if c['ok'] is None else 'FAIL')}"
                     for c in row["cells"]]
            print(f"    {row['run'][:48]:48} {'pass' if row['ok'] else 'fail'}: " + " | ".join(parts))
        if res["status"] == "active" and res["met"] is not True and nxt is None:
            nxt = res
        if res["status"] == "met" and res["met"] is False:
            broke.append(res["id"])
    if broke:
        print(f"\nREGRESSION: met goal(s) broke: {', '.join(broke)} - fix these first")
    if nxt:
        print(f"\nNext: {nxt['id']} - {nxt['title']}")
    if a.json:
        out = ROOT / ".runtime" / "goals.json"
        out.write_text(json.dumps({"goals": results, "next": nxt and nxt["id"], "broke": broke}, indent=1), encoding="utf-8")
        print(f"wrote {out}")
    return 1 if (broke or nxt) else 0


if __name__ == "__main__":
    sys.exit(main())
