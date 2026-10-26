"""The crash sub-lab (26 Oct - Martin, note 421: "let's make a sub-lab reproducing the crash and try to fix it"). The night's
crashes: the engine asserts on a bad entity matrix (enf_entity.cpp 1656-1672 - orientation, position, bounding box) and then
reads bad memory; 5 of 14 headless 45-min matches, clustered (4 of 5 starts between 06:40 and 07:26, then 8 clean in a row).
The scenario is the battle itself (nothing smaller reproduced it so far): headless Arland, modern v phased, the watched
settings, ZCR_PhysWatch logging any entity going wild, spinning, NaN or falling under the ground ([ZCR][PHYS]). Each variant
switches one suspect off; the measure is crashes per game hour, and what the watcher saw in the seconds before each crash.

    python lab/crashlab.py --parallel 4 --runs 24           # spread over the variants, 4 servers at once
    python lab/sublab.py report crash                       # the table (also in the lab app's Sub-labs tab)
"""
import argparse
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
sys.path.insert(0, str(HERE))
OUT = ROOT / ".runtime" / "crashlab"
PORTS = [2148, 2150, 2152, 2154, 2156, 2158]
TURRETS = ("LAV25", "BTR70", "UAZ469_PKM", "M1025_armed", "BRDM", "M2A2", "BMP")

SCENARIOS = {
    "arland": ("arland", "the Arland battle, modern v phased, the watched settings"),
}
# name: (add, drop, drones, description)
VARIANTS = {
    "default": ("", "", True, "the watched setup as it is (armed vehicles pushed out of jams)"),
    "noturretpush": ("", "-zcrMoveTurrets", True, "no pushes of armed vehicles"),
    "nomoves": ("-zcrNoUnjam", "", True, "no vehicle moved by our code at all"),
    "nodrones": ("", "", False, "no FPV drones"),
    "noarmed": ("-aicfArmedRideEvery 0 -aicfApcEvery 0", "", True, "no armed rides or APC rides (fewer turret vehicles)"),
    "physfix": ("-zcrPhysFix", "", True, "items falling under the ground deleted before the world's floor"),
    # 18:30: crashes come 0.05-0.8 s after the engine's "Stuck trying to get into vehicle. Reseting.." 4-5x more often than by
    # chance (5 of 58 within 1 s, ~1 expected) - and the night's free pads multiplied boardings.
    "norides": ("-aicfInfantryRideMeters 5000", "", True, "no infantry rides on Arland (5 km: the fork's maximum)"),
    # 19:05: no event explains most crashes (62 in 1097 runs: a dozen vehicle/boarding events each ~2x), the 21 Oct code
    # crashed too when re-run on 22 Oct - and every crash of the kind starts with the diagnostic build's asserts.
    "release": ("", "", True, "the release server build instead of the diagnostic one"),
}


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "crashlab.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def argv_for(scenario: str, variant: str, minutes: float, port: int, label: str) -> list:
    add, drop, drones, _ = VARIANTS[variant]
    mods = (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").strip()
    extra = (ROOT / ".runtime" / "watch_extra.txt").read_text(encoding="utf-8").strip()
    words = [w for w in extra.split() if w not in drop.split()] + add.split()
    argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", SCENARIOS[scenario][0], "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "modern", "--ussr", "phased", "--mods", mods, "--extra", " ".join(words)]
    if drones:
        argv.append("--drones")
    return argv


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    c = sorted(run_dir.glob("logs/*/console.log"))
    if not c:
        return {"scenario": scenario, "variant": variant, "error": "no log", "run": run_dir.name}
    t = c[-1].read_text(encoding="utf-8", errors="replace")
    lives = [int(x) for x in re.findall(r"\[ZCR\]\[LIVE\] t=(\d+)", t)]
    minutes = round(max(lives) / 60, 1) if lives else 0
    crash_log = c[-1].parent / "crash.log"
    ct = crash_log.read_text(encoding="utf-8", errors="replace") if crash_log.exists() else ""
    crashed = bool(list(c[-1].parent.glob("*.mdmp")))
    reason = ""
    if crashed:
        m = re.search(r"Reason: (.*)", ct)
        reason = m.group(1)[:70] if m else ""
    phys = re.findall(r"\[ZCR\]\[PHYS\] t=(\d+) what=(\w+) name=(\S+) kind=(\w+)", t)
    before = ""
    if crashed and phys and lives:
        end = max(lives)
        near = [p for p in phys if int(p[0]) >= end - 15]
        before = "; ".join(f"{w} {n} ({k}) t={tt}" for tt, w, n, k in near[-4:])
    pushes = re.findall(r"op=push what=(\S+)", t)
    stuck = re.findall(r"^(\d\d:\d\d:\d\d\.\d+)\s+AI\s+\(W\): Stuck trying to get into vehicle", t, re.M)
    stuck_gap = None
    crash_at = re.search(r"^(\d\d:\d\d:\d\d\.\d+)\s+ENGINE\s+\(F\): Crashed", t, re.M)
    if crash_at and stuck:
        tc = datetime.strptime(crash_at.group(1), "%H:%M:%S.%f")
        gaps = [(tc - datetime.strptime(s, "%H:%M:%S.%f")).total_seconds() for s in stuck]
        gaps = [g for g in gaps if g >= 0]
        stuck_gap = round(min(gaps), 2) if gaps else None
    return {
        "scenario": scenario, "variant": variant, "run": run_dir.name, "minutes": minutes,
        "crashed": int(crashed), "crash_per_hour": round(60 * crashed / minutes, 2) if minutes else None,
        "reason": reason, "before_crash": before,
        "badmatrix_asserts": ct.count("BadMatrix33"), "oob_asserts": ct.count("out of world bounds"),
        "phys_wild": sum(1 for p in phys if p[1] == "wild"), "phys_spin": sum(1 for p in phys if p[1] == "spin"),
        "phys_nan": sum(1 for p in phys if p[1] == "nan"), "phys_falling": sum(1 for p in phys if p[1] == "falling"),
        "pushes": len(pushes), "turret_pushes": sum(1 for w in pushes if any(x in w for x in TURRETS)),
        "stuck_getin": len(stuck), "stuck_before_crash_s": stuck_gap,
        "script_errors": sum(1 for b in re.findall(r"Virtual Machine Exception(.{0,400})", t, re.S)
                             if "Failed move" not in b and ".bt" not in b),
    }


def run(scenario: str, variant: str, minutes: float, units: int, port: int) -> dict:
    """One run, for lab/sublab.py run crash."""
    label = f"crashlab-{variant}-p{port}"
    subprocess.run(argv_for(scenario, variant, minutes, port, label), cwd=str(ROOT))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"), key=lambda r: r.stat().st_mtime)
    return summarize(runs[-1], scenario, variant) if runs else {"scenario": scenario, "variant": variant, "error": "no run"}


def port_busy(port: int) -> bool:
    out = subprocess.run(["netstat", "-ano", "-p", "UDP"], capture_output=True, text=True).stdout
    return f"127.0.0.1:{port} " in out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--ports", default="", help="its own ports, e.g. 2160,2162 (another crashlab running: no race for a port)")
    ap.add_argument("--runs", type=int, default=24, help="runs in all, spread over the variants in turn")
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--recount", action="store_true", help="summarize every recorded run again from its log")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.recount:
        import sublab
        path = sublab.results_path("crash")
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        out = []
        for r in rows:
            run_dir = ROOT / ".runtime" / "runs" / r.get("run", "")
            out.append({**r, **summarize(run_dir, r["scenario"], r["variant"])} if r.get("run") and run_dir.exists() else r)
        path.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
        print(f"recounted {len(out)} runs")
        return 0
    import bridges
    import sublab
    bridges.ensure(("phased", "modern"))
    variants = a.variants.split(",")
    todo = [variants[i % len(variants)] for i in range(a.runs)]
    ports = [int(x) for x in a.ports.split(",")] if a.ports else PORTS[:a.parallel]
    running = {}
    n = 0
    while todo or running:
        for port in ports:
            if port in running or not todo or port_busy(port):
                continue
            variant = todo.pop(0)
            n += 1
            label = f"crashlab-{variant}-{n}-p{port}"
            out = open(OUT / f"{label}.out", "w", encoding="utf-8")
            env = dict(os.environ)
            if variant == "release":
                env["ZCR_RELEASE_EXE"] = "1"
            proc = subprocess.Popen(argv_for("arland", variant, a.minutes, port, label), cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, env=env,
                                    creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
            running[port] = (variant, label, proc)
            log(f"start {label}")
            time.sleep(20)     # not all at the same second
        for port, (variant, label, proc) in list(running.items()):
            if proc.poll() is None:
                continue
            runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"), key=lambda r: r.stat().st_mtime)
            row = summarize(runs[-1], "arland", variant) if runs else {"scenario": "arland", "variant": variant, "error": "no run"}
            sublab.record("crash", row)
            log(f"done {label}: {row.get('minutes')} min crashed={row.get('crashed')} {row.get('reason', '')} before=[{row.get('before_crash', '')}] "
                f"wild={row.get('phys_wild')} spin={row.get('phys_spin')} nan={row.get('phys_nan')} falling={row.get('phys_falling')} "
                f"turret_pushes={row.get('turret_pushes')}")
            del running[port]
        time.sleep(10)
    log("crash lab done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
