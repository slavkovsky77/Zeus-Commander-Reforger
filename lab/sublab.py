"""Sub-labs: one small experiment per issue (23 Oct 2026, Martin: "a sub-scenario with a sub-lab for this specific
experiment, where we try to solve solely that - independent and faster iteration"). A sub-lab is a question, a runner
that plays the smallest scenario reproducing the issue, named scenarios and variants, a score and a pass rule. Every
run adds one row; the report and the lab app's Sub-labs tab compare the variants per scenario.

    python lab/sublab.py list
    python lab/sublab.py new <name> --question "..." --runner lab/<x>test.py --scenarios a,b --variants raw,default --score "legs - 4*lost"
    python lab/sublab.py run <name> [--scenario s] [--variant v] [--repeat 1] [--minutes M] [--port 2148]
    python lab/sublab.py report <name>

Definition: lab/sublabs/<name>.toml (in the repo). Results: .runtime/sublab/<name>/results.jsonl and REPORT.md.
The runner is a module with run(scenario, variant, minutes, units, port) -> dict (one flat summary of the run; the
score expression is evaluated on it, None counts as 0). lab/drivetest.py is the first one.
"""
import argparse
import importlib.util
import json
import statistics
import sys
import tomllib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFS = HERE / "sublabs"
OUT = ROOT / ".runtime" / "sublab"


def names() -> list:
    return sorted(p.stem for p in DEFS.glob("*.toml")) if DEFS.is_dir() else []


def load(name: str) -> dict:
    p = DEFS / f"{name}.toml"
    if not p.is_file():
        sys.exit(f"no sub-lab '{name}' (lab/sublabs/{name}.toml); known: {', '.join(names()) or '-'}")
    d = tomllib.loads(p.read_text(encoding="utf-8"))
    d.setdefault("name", name)
    d.setdefault("keys", [])
    d.setdefault("higher_is_better", True)
    d.setdefault("minutes", 10)
    d.setdefault("units", 6)
    return d


def runner(d: dict):
    path = ROOT / d["runner"]
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


def score(d: dict, row: dict) -> float:
    env = {k: (0 if v is None or isinstance(v, (dict, list)) else v) for k, v in row.items()}
    env = {k: (int(v) if isinstance(v, bool) else v) for k, v in env.items()}
    try:
        return float(eval(d["score"], {"__builtins__": {}}, env))   # our own expression from the repo's toml
    except Exception as e:
        print(f"[sublab] score '{d['score']}' failed: {e}", flush=True)
        return 0.0


def results_path(name: str) -> Path:
    return OUT / name / "results.jsonl"


def record(name: str, row: dict) -> dict:
    """Append one run (also used by other runners, e.g. lab/drivenight.py). Adds at / scenario / score."""
    d = load(name)
    row = dict(row)
    row.setdefault("scenario", row.get("track"))
    row.setdefault("at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    row["score"] = score(d, row)
    p = results_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def rows(name: str) -> list:
    p = results_path(name)
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def run(name: str, scenario: str, variant: str, repeat: int, minutes: float, port: int) -> list:
    d = load(name)
    mod = runner(d)
    scenarios = [scenario] if scenario else d["scenarios"]
    variants = [variant] if variant else d["variants"]
    out = []
    for s in scenarios:
        for v in variants:
            for i in range(repeat):
                print(f"[sublab] {name}: {s} / {v} #{i + 1} ({minutes or d['minutes']} min)", flush=True)
                r = mod.run(s, v, minutes or d["minutes"], d["units"], port)
                r["rep"] = i
                row = record(name, r)
                out.append(row)
                print("  " + " ".join(f"{k}={row.get(k)}" for k in ["score"] + d["keys"]), flush=True)
    return out


def matrix(name: str) -> dict:
    d = load(name)
    rs = rows(name)
    cells = {}
    for r in rs:
        if r.get("watched"):
            continue   # runs watched in the window (often sped up) aren't comparable: the charts show them, the table doesn't
        cells.setdefault(r.get("scenario"), {}).setdefault(r.get("variant"), []).append(r)
    table = []
    for s in d["scenarios"] + sorted(set(cells) - set(d["scenarios"])):
        if s is None:
            continue
        row = {"scenario": s, "cells": {}}
        for v, group in (cells.get(s) or {}).items():
            cell = {"n": len(group), "score": round(statistics.mean(x.get("score") or 0 for x in group), 1)}
            for k in d["keys"]:
                vals = [x.get(k) for x in group if isinstance(x.get(k), (int, float)) and not isinstance(x.get(k), bool)]
                cell[k] = round(statistics.mean(vals), 1) if vals else None
            row["cells"][v] = cell
        if row["cells"]:
            table.append(row)
    return {"name": name, "question": d.get("question", ""), "issue": d.get("issue", ""), "pass_rule": d.get("pass_rule", ""), "score_text": d["score"],
            "scenarios": d["scenarios"], "variants": d["variants"], "baseline": d.get("baseline"), "candidate": d.get("candidate"),
            "keys": d["keys"], "higher_is_better": d["higher_is_better"], "runs": len(rs), "last_at": rs[-1]["at"] if rs else None,
            "table": table, "recent": [{k: r.get(k) for k in ["at", "scenario", "variant", "score"] + d["keys"] + ["run"]} for r in rs[-12:]][::-1],
            # every run, oldest first, for the app's charts (the last 400)
            "all": [{k: r.get(k) for k in ["at", "scenario", "variant", "score", "watched"] + d["keys"]} for r in rs[-400:]]}


def report(name: str) -> Path:
    m = matrix(name)
    lines = [f"# Sub-lab {name}", "", m["question"], "", f"Pass: {m['pass_rule']}", "",
             f"Runs: {m['runs']}" + (f", last {m['last_at']}" if m["last_at"] else ""), "",
             "| scenario | " + " | ".join(m["variants"]) + " |", "|---|" + "---|" * len(m["variants"])]
    for row in m["table"]:
        cells = []
        for v in m["variants"]:
            c = row["cells"].get(v)
            cells.append(f"**{c['score']}** (n={c['n']}; " + ", ".join(f"{k} {c.get(k)}" for k in m["keys"][:4]) + ")" if c else "")
        lines.append(f"| {row['scenario']} | " + " | ".join(cells) + " |")
    lines += ["", f"Score: `{load(name)['score']}` ({'higher' if m['higher_is_better'] else 'lower'} is better). "
              f"Baseline `{m['baseline']}`, candidate `{m['candidate']}`."]
    p = OUT / name / "REPORT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def app_data() -> list:
    """Every sub-lab for the lab app's Sub-labs tab."""
    out = []
    for n in names():
        try:
            out.append(matrix(n))
        except Exception as e:
            out.append({"name": n, "question": f"(broken definition: {e})", "table": [], "recent": [], "variants": [], "keys": [], "runs": 0})
    return out


def new(name: str, a) -> Path:
    DEFS.mkdir(parents=True, exist_ok=True)
    p = DEFS / f"{name}.toml"
    if p.exists():
        sys.exit(f"{p} exists")
    def arr(s):
        return "[" + ", ".join(f'"{x.strip()}"' for x in s.split(",") if x.strip()) + "]"
    p.write_text(f'''# Sub-lab "{name}" - created {datetime.now():%Y-%m-%d %H:%M} by lab/sublab.py new
name = "{name}"
question = "{a.question}"
issue = "{a.issue}"
pass_rule = "{a.pass_rule}"
runner = "{a.runner}"
minutes = {a.minutes}
units = {a.units}
scenarios = {arr(a.scenarios)}
variants = {arr(a.variants)}
baseline = "{a.baseline}"
candidate = "{a.candidate}"
score = "{a.score}"
higher_is_better = true
keys = {arr(a.keys)}
''', encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--question", required=True)
    n.add_argument("--issue", default="")
    n.add_argument("--pass-rule", default="")
    n.add_argument("--runner", required=True)
    n.add_argument("--scenarios", required=True)
    n.add_argument("--variants", required=True)
    n.add_argument("--baseline", default="raw")
    n.add_argument("--candidate", default="default")
    n.add_argument("--score", required=True)
    n.add_argument("--keys", default="")
    n.add_argument("--minutes", type=float, default=10)
    n.add_argument("--units", type=int, default=6)
    r = sub.add_parser("run")
    r.add_argument("name")
    r.add_argument("--scenario", default="")
    r.add_argument("--variant", default="")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--minutes", type=float, default=0)
    r.add_argument("--port", type=int, default=2148)
    rp = sub.add_parser("report")
    rp.add_argument("name")
    a = ap.parse_args()
    if a.cmd == "list":
        for n in names():
            m = matrix(n)
            print(f"{n:14} runs={m['runs']:4}  {m['question'][:90]}")
    elif a.cmd == "new":
        print("written", new(a.name, a))
    elif a.cmd == "run":
        run(a.name, a.scenario, a.variant, a.repeat, a.minutes, a.port)
        print("report:", report(a.name))
    elif a.cmd == "report":
        p = report(a.name)
        print(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
