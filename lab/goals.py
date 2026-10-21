"""Where the goals stand: every goal of goals.toml judged on the latest matches, and the next one to work on.

    python lab/goals.py                  # each goal on its last 3 matches (watched ones by default)
    python lab/goals.py --last 5         # on the last 5
    python lab/goals.py --runs R1 R2     # on these matches
    python lab/goals.py --json           # also writes .runtime/goals.json (for the pages)
    python lab/goals.py --html OUT.html  # the goals page: verdicts, values, the last 12 matches as a strip

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
    ap.add_argument("--html", help="write the goals page here")
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
    if a.html:
        history = {}
        for goal in load():
            if goal.get("status") != "paused" and not a.runs:
                history[goal["id"]] = judge(goal, runs_for(goal.get("matches", "watched"), 12, goal.get("needs", [])))
        Path(a.html).write_text(page(results, history, nxt, broke), encoding="utf-8")
        print(f"wrote {a.html}")
    return 1 if (broke or nxt) else 0


def when(run: str) -> str:
    m = re.search(r"-(\d{8})-(\d{2})(\d{2})\d{2}$", run)
    return f"{m.group(1)[6:8]}.{m.group(1)[4:6]} {m.group(2)}:{m.group(3)}" if m else run[:12]


def page(results: list, history: dict, nxt, broke: list) -> str:
    """The goals page: each goal's verdict on its last matches, the values, and the last 12 matches as a strip."""
    import html as h
    from datetime import datetime
    chip = {True: ("ok", "met"), False: ("no", "not met"), None: ("wait", "too few matches")}
    parts = []
    for res in results:
        cls, text = chip[res["met"]]
        if res["status"] == "met" and res["met"] is False:
            cls, text = "no", "broke (was met)"
        rows = "".join(
            f"<tr><td>{h.escape(c['key'])} <span class=t>{h.escape(c['target'])}</span></td>"
            + "".join(f"<td class=num><span class='d {('ok' if r['cells'][i]['ok'] else ('no' if r['cells'][i]['ok'] is False else 'na'))}'></span>"
                      f"{h.escape(r['cells'][i]['shown'])}</td>" for r in res["rows"]) + "</tr>"
            for i, c in enumerate(res["rows"][0]["cells"] if res["rows"] else []))
        head = "".join(f"<th>{h.escape(when(r['run']))}</th>" for r in res["rows"])
        hist = history.get(res["id"])
        strip = ""
        if hist and hist["rows"]:
            strip = "<div class=strip>" + "".join(
                f"<span class='s {'ok' if r['ok'] else 'no'}' title='{h.escape(r['run'])}'></span>" for r in hist["rows"]) + \
                f"<span class=sl>last {len(hist['rows'])} matches, oldest first: {sum(1 for r in hist['rows'] if r['ok'])} passed</span></div>"
        notes = ", ".join(str(n) for n in res["notes"])
        parts.append(f"""<section class=goal><div class=gh><h2>{h.escape(res['title'])}</h2><span class='chip {cls}'>{text}: {res['passed']} of {res['of']}</span></div>
<p class=wish>"{h.escape(res['wish'])}" <span class=t>goal {h.escape(res['id'])} - notes {notes}</span></p>
<div class=tbl><table><thead><tr><th>Measure (target)</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>{strip}</section>""")
    top = ""
    if broke:
        top += f"<p class='banner no'>Broke: {', '.join(broke)} - a goal that was met fails again; it comes first.</p>"
    if nxt:
        top += f"<p class=banner>Next: <b>{h.escape(nxt['title'])}</b> ({h.escape(nxt['id'])})</p>"
    stamp = datetime.now().strftime("%d %b %H:%M")
    return f"""<title>Commander Goals</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* One column of goal cards; per goal a table of the last matches and a strip of the last 12. */
:root {{ --bg:#f2f4f1; --panel:#fff; --ink:#18211e; --muted:#56625d; --line:#d5dbd6; --accent:#2c5a86;
  --good:#23743f; --good-soft:#e1f1e6; --bad:#a3322a; --bad-soft:#f7e3e1; --warn:#8a5a00; --warn-soft:#f6ecd6; --na:#b9c2bd;
  --f-display:"Barlow Condensed","Arial Narrow",sans-serif; --f-body:"Source Sans 3","Segoe UI",system-ui,sans-serif; --f-mono:"JetBrains Mono",Consolas,monospace; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#121816; --panel:#1a2220; --ink:#e3e9e5; --muted:#9aa7a1; --line:#2c3833; --accent:#7fb0de;
  --good:#6fcf8f; --good-soft:#17301f; --bad:#f08a80; --bad-soft:#3a1d1a; --warn:#e7b85a; --warn-soft:#33290f; --na:#4a5651; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --bg:#121816; --panel:#1a2220; --ink:#e3e9e5; --muted:#9aa7a1; --line:#2c3833; --accent:#7fb0de;
  --good:#6fcf8f; --good-soft:#17301f; --bad:#f08a80; --bad-soft:#3a1d1a; --warn:#e7b85a; --warn-soft:#33290f; --na:#4a5651; color-scheme:dark; }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.5 var(--f-body); }}
.wrap {{ max-width:860px; margin:0 auto; padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); padding-block:24px 56px; display:grid; gap:22px; }}
h1,h2 {{ font-family:var(--f-display); font-weight:700; margin:0; text-wrap:balance; }}
h1 {{ font-size:40px; line-height:1; }} h2 {{ font-size:23px; line-height:1.1; }}
p {{ margin:0; }} .sub {{ color:var(--muted); max-width:70ch; }}
.banner {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--accent); padding:10px 12px; border-radius:6px; }}
.banner.no {{ border-left-color:var(--bad); }}
.goal {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px; display:grid; gap:10px; min-width:0; }}
.gh {{ display:flex; flex-wrap:wrap; gap:8px 12px; align-items:baseline; justify-content:space-between; }}
.wish {{ color:var(--muted); font-size:14px; }} .t {{ font:12px var(--f-mono); color:var(--muted); white-space:nowrap; }}
.chip {{ font:600 12px/1 var(--f-mono); padding:6px 9px; border-radius:999px; white-space:nowrap; }}
.chip.ok {{ color:var(--good); background:var(--good-soft); }} .chip.no {{ color:var(--bad); background:var(--bad-soft); }} .chip.wait {{ color:var(--warn); background:var(--warn-soft); }}
.tbl {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }}
th {{ font:600 11px var(--f-mono); color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }}
td.num {{ font-family:var(--f-mono); font-size:12.5px; font-variant-numeric:tabular-nums; }}
.d {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; background:var(--na); }}
.d.ok {{ background:var(--good); }} .d.no {{ background:var(--bad); }}
.strip {{ display:flex; flex-wrap:wrap; align-items:center; gap:3px; }}
.s {{ width:14px; height:14px; border-radius:3px; background:var(--na); }} .s.ok {{ background:var(--good); }} .s.no {{ background:var(--bad); }}
.sl {{ font:12px var(--f-mono); color:var(--muted); margin-left:8px; }}
</style>
<div class=wrap>
<header style="display:grid;gap:6px"><h1>Commander Goals</h1>
<p class=sub>Each goal judged on its last finished watched matches (lab/goals.py, {stamp}). Side values are US / USSR; a side measure passes when both sides pass. Green dot: passes, red: fails, grey: no value.</p></header>
{top}
{''.join(parts)}
</div>"""


if __name__ == "__main__":
    sys.exit(main())
