"""Crash probe (26 Oct night): is the night's final build stable enough to watch? 4 of its first 5 runs crashed (bad matrix;
two at 35-40 game seconds while teams boarded rides at the main base), against 2 of 8 earlier in the night. Headless
Arland, modern v phased, 15 game minutes, two at a time, alternating the watched setup's turret pushes on and off
(4 crashes in the night came within 2 s of pushing a turret vehicle).

    python lab/crashprobe.py            # the probe (skips what's done)
    python lab/crashprobe.py --report   # .runtime/crashprobe/REPORT.md
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
OUT = ROOT / ".runtime" / "crashprobe"
MINUTES = 15
RUNS = ["turrets", "noturrets"] * 4
PORTS = [2148, 2150]


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "probe.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def stats(run_dir: Path) -> dict:
    c = sorted(run_dir.glob("logs/*/console.log"))
    if not c:
        return {"error": "no log"}
    t = c[-1].read_text(encoding="utf-8", errors="replace")
    lives = [int(x) for x in re.findall(r"\[ZCR\]\[LIVE\] t=(\d+)", t)]
    crash = c[-1].parent / "crash.log"
    reason = ""
    if crash.exists():
        m = re.search(r"Reason: (.*)", crash.read_text(encoding="utf-8", errors="replace"))
        reason = m.group(1)[:80] if m else ""
    crashed = bool(list(c[-1].parent.glob("*.mdmp")))
    return {"run": run_dir.name, "minutes": round(max(lives) / 60, 1) if lives else None, "crashed": crashed,
            "reason": reason if crashed else "", "pushes": t.count("op=push"),
            "turret_pushes": len(re.findall(r"op=push what=(?:LAV25|BTR70|UAZ469_PKM|M1025_armed|BRDM)", t))}


def done() -> list:
    p = OUT / "results.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def report() -> Path:
    rows = done()
    lines = ["# Crash probe", "", f"Headless Arland, modern v phased, {MINUTES} game minutes, the night's final build.", "",
             "| variant | minutes | crashed | reason | pushes | turret pushes |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['variant']} | {r.get('minutes')} | {r.get('crashed')} | {r.get('reason')} | {r.get('pushes')} | {r.get('turret_pushes')} |")
    for v in ("turrets", "noturrets"):
        g = [r for r in rows if r["variant"] == v]
        if g:
            lines.append(f"| **{v}** | {round(sum(r.get('minutes') or 0 for r in g), 1)} min in all | {sum(1 for r in g if r.get('crashed'))} of {len(g)} | | | |")
    p = OUT / "REPORT.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def port_busy(port: int) -> bool:
    out = subprocess.run(["netstat", "-ano", "-p", "UDP"], capture_output=True, text=True).stdout
    return f"127.0.0.1:{port} " in out


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
    todo = list(enumerate(RUNS))[len(done()):]
    running = {}
    while todo or running:
        for port in PORTS:
            if port in running or not todo or port_busy(port):
                continue
            i, variant = todo.pop(0)
            label = f"crashprobe-{variant}-{i}-p{port}"
            run_extra = extra if variant == "turrets" else " ".join(x for x in extra.split() if x != "-zcrMoveTurrets")
            argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", "arland", "--minutes", str(MINUTES), "--label", label,
                    "--port", str(port), "--us", "modern", "--ussr", "phased", "--drones", "--mods", mods, "--extra", run_extra]
            out = open(OUT / f"{label}.out", "w", encoding="utf-8")
            running[port] = (variant, label, subprocess.Popen(argv, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT,
                                                              creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS", 0)))
            log(f"start {label}")
        for port, (variant, label, proc) in list(running.items()):
            if proc.poll() is None:
                continue
            runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"), key=lambda r: r.stat().st_mtime)
            row = {"variant": variant, **(stats(runs[-1]) if runs else {"error": "no run folder"})}
            with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            log(f"done {label}: {row.get('minutes')} min crashed={row.get('crashed')} {row.get('reason', '')} turret_pushes={row.get('turret_pushes')}")
            del running[port]
            report()
        time.sleep(15)
    log(f"probe done - {report()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
