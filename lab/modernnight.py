"""The modern doctrine night (26 Oct - Martin, note 420: "more hit and run, modern-style assaults with quick dismounts
near positions, storms with heavy drone support"; note 419: "more drone-doctrine oriented, I miss storms, longer
matches would be nice"). Headless Arland matches two at a time, 45 game minutes, the watched settings, the modern
strategist (lab/modern.py) against phased (lab/phased.py) with the sides swapped every match, then modern against
itself; a report per side.

    python lab/modernnight.py            # the whole night (skips what's done)
    python lab/modernnight.py --report   # .runtime/modernnight/REPORT.md
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
OUT = ROOT / ".runtime" / "modernnight"
MINUTES = 45
MATCHES = [("modern-us", "modern", "phased"), ("modern-ussr", "phased", "modern")] * 3 + [("modern-both", "modern", "modern")] * 2
PORTS = [2148, 2150]
SIDES = ("US", "USSR")


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "night.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def side_stats(t: str, side: str) -> dict:
    other = "USSR" if side == "US" else "US"
    plans = re.findall(rf"\[ZCR\]\[PLAN\] faction={side} .*intent=(.*)", t)
    score = re.findall(r"\[ZCR\]\[SCORE\] t=\d+ US=(\d+) USSR=(\d+)", t)
    return {
        "captures": len(re.findall(rf"\[ZCR\]\[CAPTURE\] t=\d+ base=.* to={side}\b", t)),
        "lost_bases": len(re.findall(rf"\[ZCR\]\[CAPTURE\] t=\d+ base=.* from={side} ", t)),
        "bases_end": int(score[-1][SIDES.index(side)]) if score else None,
        "losses": len(re.findall(rf"\[ZCR\]\[LOSS\] .* side={side} kind=man", t)),
        "kills": len(re.findall(rf"\[ZCR\]\[LOSS\] .* side={other} kind=man killer_side={side} ", t)),
        "storms": len(re.findall(rf"\[ZCR\]\[STORM\] t=\d+ faction={side} ", t)),
        "strikes": len({p.split(":")[0] for p in plans if p.startswith("Strike ")}),
        "pullbacks": sum(1 for p in plans if "pulling back" in p),
        "gathers": sum(1 for p in plans if p.startswith("Gathering at")),
        "launches": len(re.findall(rf"\[ZCR\]\[DRONES\] t=\d+ side={side} team=\d+ kind=", t)),
        "surge_launches": len(re.findall(rf"\[ZCR\]\[DRONES\] t=\d+ side={side} team=\d+ kind=.* why=surge", t)),
        "dismounts": len(re.findall(rf"\[ZCR\]\[DISMOUNT\] t=\d+ faction={side} ", t)),
        "seat_refusals": len(re.findall(rf"WAITING_FOR_SITE_EXIT\].* faction={side} .*reason=INSUFFICIENT_COMPARTMENTS", t)),
        "abandoned": len(re.findall(rf"\[VEHICLE_ABANDONED\].* faction={side} ", t)),
        "built": len(re.findall(rf"\[CONSTRUCTION_COMPLETED\].* faction={side} ", t)),
    }


def stats(run_dir: Path) -> dict:
    c = sorted(run_dir.glob("logs/*/console.log"))
    if not c:
        return {"error": "no log"}
    t = c[-1].read_text(encoding="utf-8", errors="replace")
    lives = [int(x) for x in re.findall(r"\[ZCR\]\[LIVE\] t=(\d+)", t)]
    return {"run": run_dir.name, "minutes": round(max(lives) / 60, 1) if lives else None,
            "detonations": len(re.findall(r"FPVAI: drone\d+ detonated", t)),
            "drowned": len(re.findall(r"FPVAI: drone\d+ lost .*WST_OCEAN", t)),
            "lost_search": len(re.findall(r"FPVAI: drone\d+ lost \(SEARCH\)", t)),
            "footprint_cleared": t.count("CONSTRUCTION_FOOTPRINT_CLEARED"),
            "completion_waits": t.count("CONSTRUCTION_COMPLETION_WAIT"),
            # VM exceptions but the behaviour trees' "Failed move" (the engine's, harmless)
            "script_errors": sum(1 for r in re.findall(r"Virtual Machine Exception\s*Reason: ([^\n]*)", t) if not r.startswith("Failed move")),
            "nan_guards": t.count("NaN guard"),
            "crashed": bool(list(c[-1].parent.glob("*.mdmp"))),
            **{side: side_stats(t, side) for side in SIDES}}


def done() -> list:
    p = OUT / "results.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


KEYS = ["captures", "lost_bases", "bases_end", "losses", "kills", "storms", "strikes", "pullbacks", "gathers", "launches",
        "dismounts", "seat_refusals", "abandoned", "built"]


def report() -> Path:
    rows = done()
    lines = ["# Modern doctrine night", "", f"Headless Arland, {MINUTES} game minutes, the watched settings.", "",
             "| match | side | doctrine | " + " | ".join(KEYS) + " |", "|---" * (len(KEYS) + 3) + "|"]
    per = {"modern": [], "phased": []}
    for r in rows:
        for side in SIDES:
            s = r.get(side) or {}
            doc = r["us"] if side == "US" else r["ussr"]
            per.setdefault(doc, []).append(s)
            lines.append(f"| {r['setup']} {r.get('minutes')}m | {side} | {doc} | " + " | ".join(str(s.get(k)) for k in KEYS) + " |")
    lines += ["", "## Per doctrine (average per side and match)", "", "| doctrine | n | " + " | ".join(KEYS) + " |",
              "|---" * (len(KEYS) + 2) + "|"]
    for doc, g in per.items():
        if g:
            avg = lambda k: round(sum(s.get(k) or 0 for s in g) / len(g), 1)
            lines.append(f"| {doc} | {len(g)} | " + " | ".join(str(avg(k)) for k in KEYS) + " |")
    lines += ["", "## Drones and health (per match)", "", "| match | detonations | drowned | lost searching | footprint cleared | completion waits | script errors | NaN guards | crashed |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['setup']} | {r.get('detonations')} | {r.get('drowned')} | {r.get('lost_search')} | {r.get('footprint_cleared')} | "
                     f"{r.get('completion_waits')} | {r.get('script_errors')} | {r.get('nan_guards')} | {r.get('crashed')} |")
    p = OUT / "REPORT.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.report:
        print(report().read_text(encoding="utf-8"))
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    import bridges
    bridges.ensure(("phased", "modern"))
    mods = (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").strip()
    extra = (ROOT / ".runtime" / "watch_extra.txt").read_text(encoding="utf-8").strip()
    todo = list(enumerate(MATCHES))[len(done()):]
    running = {}
    while todo or running:
        for port in PORTS:
            if port in running or not todo:
                continue
            i, (setup, us, ussr) = todo.pop(0)
            label = f"modernnight-{setup}-{i}-p{port}"
            argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", "arland", "--minutes", str(MINUTES), "--label", label,
                    "--port", str(port), "--us", us, "--ussr", ussr, "--drones", "--mods", mods, "--extra", extra]
            out = open(OUT / f"{label}.out", "w", encoding="utf-8")
            running[port] = (setup, us, ussr, label, subprocess.Popen(argv, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT,
                                                                       creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS", 0)))
            log(f"start {label} (US {us}, USSR {ussr})")
        for port, (setup, us, ussr, label, proc) in list(running.items()):
            if proc.poll() is None:
                continue
            runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"), key=lambda r: r.stat().st_mtime)
            row = {"setup": setup, "us": us, "ussr": ussr, **(stats(runs[-1]) if runs else {"error": "no run folder"})}
            with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            brief = " ".join(f"{side}:{row.get(side, {}).get('captures')}cap/{row.get(side, {}).get('storms')}storm/{row.get(side, {}).get('launches')}fpv"
                             for side in SIDES)
            log(f"done {label}: {row.get('minutes')} min {brief} crashed={row.get('crashed')} errors={row.get('script_errors')}")
            del running[port]
            report()
        time.sleep(20)
    log(f"night done - {report()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
