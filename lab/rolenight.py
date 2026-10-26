"""The role-sized teams night (26 Oct - Martin: "fewer teams, 50 soldiers a side, assault teams bigger than the others";
"I'm going to sleep, you can test it during the night"). First the FPS in the game window (lab/fpstest.py, 30 game
minutes at 3x and 2x, nothing else running), then headless matches two at a time - the role-sized setup and today's
setup, the watched settings, phased v phased, 25 minutes - and a report.

    python lab/rolenight.py            # the whole night (skips what's done)
    python lab/rolenight.py --report   # .runtime/rolenight/REPORT.md
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / ".runtime" / "rolenight"
ROLE = "-aicfSquadsPerSide 10 -aicfAttackTeamSize 6 -aicfDefendTeamSize 3"
MATCHES = [("role", ROLE), ("base", ""), ("role", ROLE), ("role", ROLE), ("base", ""), ("role", ROLE)]
PORTS = [2148, 2150]


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "night.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def stats(run_dir: Path) -> dict:
    c = sorted(run_dir.glob("logs/*/console.log"))
    if not c:
        return {"error": "no log"}
    t = c[-1].read_text(encoding="utf-8", errors="replace")
    lives = [int(x) for x in re.findall(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team", t)]
    by = {}
    if lives:
        for side, role, men in re.findall(rf"\[ZCR\]\[LIVE\] t={max(lives)} kind=team side=(\w+) id=\d+ role=(\w+) men=(\d+)", t):
            by.setdefault(role, []).append(int(men))
    fps = [float(x) for x in re.findall(r"FPS: ([\d.]+), frame time", t)]
    return {"run": run_dir.name, "minutes": round(max(lives) / 60, 1) if lives else None,
            "captures": t.count("[ZCR][CAPTURE]"), "losses": t.count("[ZCR][LOSS]"),
            "unloads": t.count("LOGISTICS_UNLOAD_COMMITTED"), "assaults": len(re.findall(r"intent.*Assault on", t)),
            "gathers": len(re.findall(r"intent.*Gathering at", t)),
            "attack_teams": len(by.get("ATTACK", [])), "attack_men": sum(by.get("ATTACK", [])),
            "defend_teams": len(by.get("DEFEND", [])), "defend_men": sum(by.get("DEFEND", [])),
            "server_fps": round(sum(fps) / len(fps), 1) if fps else None,
            "crashed": bool(list(c[-1].parent.glob("*.mdmp")))}


def done() -> list:
    p = OUT / "results.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def report() -> Path:
    rows = done()
    lines = ["# Role-sized teams night", ""]
    fps = [json.loads(l) for l in (ROOT / ".runtime" / "fpstest" / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    lines += ["## FPS (game window, 30 game minutes)", "", "| setup | fps | after minute 6 (lowest) | captures | losses |", "|---|---|---|---|---|"]
    for r in fps:
        b = r.get("buckets", {})
        if len(b) < 9:
            continue
        late = [b[k]["fps"] for k in b if int(k.split("-")[0]) >= 6]
        lines.append(f"| {r['variant']} | {r['fps']} | {round(sum(late) / len(late), 1)} ({min(late)}) | {r.get('captures')} | {r.get('losses')} |")
    lines += ["", "## Headless matches (25 min, watched settings, phased v phased)", "",
              "| setup | captures | losses | deliveries | assaults | attack teams/men | defend teams/men | crashed |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['setup']} | {r.get('captures')} | {r.get('losses')} | {r.get('unloads')} | {r.get('assaults')} | "
                     f"{r.get('attack_teams')}/{r.get('attack_men')} | {r.get('defend_teams')}/{r.get('defend_men')} | {r.get('crashed')} |")
    for setup in ("role", "base"):
        g = [r for r in rows if r["setup"] == setup and "captures" in r]
        if g:
            avg = lambda k: round(sum(r.get(k) or 0 for r in g) / len(g), 1)
            lines.append(f"| **{setup} average ({len(g)})** | {avg('captures')} | {avg('losses')} | {avg('unloads')} | {avg('assaults')} | | | |")
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
    # 1. FPS in the window, alone.
    if not (OUT / "fps.done").exists():
        log("FPS: role3x, role2x (30 game minutes each, game window)")
        subprocess.run([sys.executable, "-u", str(HERE / "fpstest.py"), "--minutes", "30", "role3x", "role2x"], cwd=str(ROOT))
        (OUT / "fps.done").write_text("ok", encoding="utf-8")
        log("FPS done")
    # 2. Headless matches, two at a time.
    mods = (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").strip()
    extra = (ROOT / ".runtime" / "watch_extra.txt").read_text(encoding="utf-8").strip()
    todo = list(enumerate(MATCHES))[len(done()):]
    running = {}
    while todo or running:
        for port in PORTS:
            if port in running or not todo:
                continue
            i, (setup, add) = todo.pop(0)
            label = f"rolenight-{setup}-{i}-p{port}"
            argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", "arland", "--minutes", "25", "--label", label, "--port", str(port),
                    "--us", "phased", "--ussr", "phased", "--drones", "--mods", mods, "--extra", f"{extra} {add}".strip()]
            out = open(OUT / f"{label}.out", "w", encoding="utf-8")
            running[port] = (setup, label, subprocess.Popen(argv, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT,
                                                            creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS", 0)))
            log(f"start {label}")
        for port, (setup, label, proc) in list(running.items()):
            if proc.poll() is None:
                continue
            runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"), key=lambda r: r.stat().st_mtime)
            row = {"setup": setup, **(stats(runs[-1]) if runs else {"error": "no run folder"})}
            with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            log(f"done {label}: " + " ".join(f"{k}={v}" for k, v in row.items() if k != "run"))
            del running[port]
            report()
        time.sleep(20)
    log(f"night done - {report()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
