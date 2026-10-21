"""Armour stress test: make the armour crash happen on purpose, then switch things off until it stops.

Martin (21 Oct): "fix armor crashes ... maybe try to simulate it somehow and then we could fix it". The watched
matches crashed 13 times in 33 game hours with armour, once in 51 without. A headless server (1x - the speed-up
works only in the watched game) runs Arland with drones and -zcrArmourStress: up to 6 tanks/IFVs a side, free,
bought again 30 s after a loss - many times the armour of a normal match. Each variant adds switches:

    control     the stress alone
    keeptype    -zcrArmourKeepType  (the vehicles keep their own type, not made APCs)
    vanilla     -zcrArmourVanilla   (the game's LAV-25 / BTR-70, not the mods' vehicles)
    hold        -zcrArmourHold      (bought and crewed, never ordered anywhere)
    nodrones    no FPV drones
    keepwrecks  -zcrKeepWrecks      (wrecks are not removed)

Runs matches of --minutes each until --hours have passed, one line per match into .runtime/stress.jsonl
(variant, minutes, crashed, crash kind, game time). The lab app's Crashes tab shows them.

    python lab/stress.py --variant control --hours 1.5 --port 2146
    python lab/stress.py --summary
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lab"))
import crashes  # noqa: E402

OUT = ROOT / ".runtime" / "stress.jsonl"
VARIANTS = {
    "control": ("-zcrArmourStress", True),
    "keeptype": ("-zcrArmourStress -zcrArmourKeepType", True),
    "vanilla": ("-zcrArmourStress -zcrArmourVanilla", True),
    "hold": ("-zcrArmourStress -zcrArmourHold", True),
    "nodrones": ("-zcrArmourStress", False),
    "keepwrecks": ("-zcrArmourStress -zcrKeepWrecks", True),
}


def one(variant: str, minutes: float, port: int) -> dict:
    extra, drones = VARIANTS[variant]
    label = f"stress-{variant}"
    started = time.time()
    cmd = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland", "--minutes", str(minutes),
           "--label", label, "--port", str(port), "--us", "phased", "--ussr", "phased", "--armour",
           f"--extra=-zcrNoFIA {extra}"] + (["--drones"] if drones else [])
    with open(ROOT / ".runtime" / f"{label}-{port}.out", "w", encoding="utf-8") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    runs = [r for r in (ROOT / ".runtime" / "runs").glob(f"{label}-*") if r.stat().st_mtime >= started - 5]
    row = {"variant": variant, "port": port, "started": time.strftime("%Y-%m-%d %H:%M", time.localtime(started)),
           "planned_min": minutes}
    if not runs:
        row["error"] = "no run folder"
        return row
    run = max(runs, key=lambda r: r.stat().st_mtime)
    info = crashes.read_run(run) or {}
    row.update({"run": run.name, "minutes": round(info.get("minutes", 0), 1), "crashed": bool(info.get("crashed")),
                "kind": info.get("kind", ""), "game_t": info.get("game_t")})
    return row


def summary() -> None:
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()] if OUT.exists() else []
    by = {}
    for r in rows:
        s = by.setdefault(r["variant"], [0, 0, 0.0])
        s[0] += 1
        s[1] += 1 if r.get("crashed") else 0
        s[2] += r.get("minutes", 0) or 0
    for v, (n, c, m) in by.items():
        rate = c / (m / 60) if m else 0
        print(f"{v:10s} {n:3d} matches {c:2d} crashed  {m / 60:5.1f} h  {rate:.2f} crashes per hour")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variant", choices=sorted(VARIANTS), default="control")
    ap.add_argument("--hours", type=float, default=1.5)
    ap.add_argument("--minutes", type=float, default=40, help="each match (a crash ends it early)")
    ap.add_argument("--port", type=int, default=2146)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        summary()
        return 0
    end = time.time() + a.hours * 3600
    while time.time() < end - 5 * 60:
        minutes = min(a.minutes, max(5, (end - time.time()) / 60 - 2))
        row = one(a.variant, minutes, a.port)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
