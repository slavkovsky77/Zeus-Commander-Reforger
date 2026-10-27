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
    # 02:20 the fix (fork 72ce716: no ride spawn with over 1.0 m under the vehicle) against the old limit, same build.
    "slopefix": ("", "", True, "the battle with the slope limit 1.0 m (the fix)"),
    "slope4": ("-aicfMaxSpawnDeltaM 4", "", True, "the battle with the old slope limit 4 m (control)"),
    # 19:10 bisect of last night: the bad-matrix crash on the headless server 9 times since 04:32 last night, once before
    # ever; the fork's night changes were tested this morning (4 and 4 clean).
    "phased": ("", "", True, "phased against phased - no modern strategist"),
    "prenight": ("", "", True, "modern v phased on our game code from before last night (d83decf)"),
    # 19:15: the 2x2 - our game code x AI Conflict fork, each from before last night or today.
    "prefork": ("", "", True, "today's game code on AI Conflict from before last night (788479a)"),
    "oldall": ("", "", True, "both from before last night (d83decf + 788479a)"),
}
    # 20:45 the mass-boarding test (Martin: "so mass boarding test?"): every plan round both sides' main efforts flip
    # between their two farthest reachable bases (lab/flip.py), defenders committed - every team asks for a ride at once.
VARIANTS["massboard"] = ("", "", True, "mass boarding: main efforts flip every 45 s, today's fork")
VARIANTS["massboard_prefork"] = ("", "", True, "mass boarding on the AI Conflict fork from before last night")
STRATS = {"phased": ("phased", "phased"), "massboard": ("flip", "flip"), "massboard_prefork": ("flip", "flip")}
PLAN_SECONDS = {"massboard": 45, "massboard_prefork": 45}
ENVS = {"release": {"ZCR_RELEASE_EXE": "1"}, "prenight": {"ZCR_ADDON_ROOT": "D:/work/zcr-pre-night"},
        "prefork": {"ZCR_AICF_ROOT": "D:/work/aicf-pre-night"}, "massboard_prefork": {"ZCR_AICF_ROOT": "D:/work/aicf-pre-night"},
        "oldall": {"ZCR_ADDON_ROOT": "D:/work/zcr-pre-night", "ZCR_AICF_ROOT": "D:/work/aicf-pre-night"}}


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "crashlab.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# 00:00 the mass-boarding sub-lab (Martin: "not the full Arland battle, sub-lab scenario style - short tests doing the same
# thing over and over"): ZCR_BoardTest on the empty Arland test map - 8 vehicles spawned in one tick, every soldier
# boarding at once the way AI Conflict does it, dropped the way it drops a team, again. name: (-zcrBoardTest spec, words)
BOARD = {
    "mb_spawnboard": ("1700,1000;8;spawnboard;all", "fresh vehicles every cycle, boarded at once - the first ride wave"),
    "mb_board": ("1700,1000;8;board;all", "the same vehicles boarded and emptied at once, again and again"),
    "mb_calm": ("1700,1000;8;calm;all", "as board, the drop without release/interrupt"),
    "mb_apc": ("1700,1000;8;spawnboard;apc", "first-wave boarding, APCs only (LAV-25, BTR-70)"),
    "mb_cars": ("1700,1000;8;spawnboard;cars", "first-wave boarding, cars only (M998, UAZ-452, M1025, UAZ-469)"),
    "mb_apc_fight": ("1700,1000;8;spawnboard;apc_fight", "the setup the first crash came in: LAV-25 + US squads beside BTR-70 + Soviet squads, shooting each other while boarding"),
    # 00:35 one change at a time in the reviewed test (US, 8 LAV-25s, all board at once - 60 of 60 crashed 4-6 s after the order).
    "mb_apc_delay30": ("1700,1000;8;spawnboard;apc;30", "the reviewed test, the board order 30 s after the spawn instead of 3 s"),
    "mb_apc_oneby": ("1700,1000;8;spawnboard_oneby;apc", "the reviewed test, soldiers into each APC one by one (Martin's idea)"),
    # 00:47 Martin: "maybe it only happens on specific places?" - the reviewed test at the Arland airport apron.
    "mb_apc_airport": ("1000,2780;8;spawnboard;apc", "the reviewed test (US, 8 LAV-25s, all at once) at the airport apron instead of Moss Hill road"),
    # 01:00 the crash needs LAV-25s at Moss Hill road (72/72; airport 0/3, cars there 0/3): which of the 8 pad spots?
    "mb_pad0": ("1700,1000;1;spawnboard;apc", "one LAV-25 + one squad on pad 0 of the crashing Moss Hill layout"),
    "mb_pad1": ("1716,1000;1;spawnboard;apc", "one LAV-25 + one squad on pad 1 of the crashing Moss Hill layout"),
    "mb_pad2": ("1732,1000;1;spawnboard;apc", "one LAV-25 + one squad on pad 2 of the crashing Moss Hill layout"),
    "mb_pad3": ("1748,1000;1;spawnboard;apc", "one LAV-25 + one squad on pad 3 of the crashing Moss Hill layout"),
    "mb_pad4": ("1700,1018;1;spawnboard;apc", "one LAV-25 + one squad on pad 4 of the crashing Moss Hill layout"),
    "mb_pad5": ("1716,1018;1;spawnboard;apc", "one LAV-25 + one squad on pad 5 of the crashing Moss Hill layout"),
    "mb_pad6": ("1732,1018;1;spawnboard;apc", "one LAV-25 + one squad on pad 6 of the crashing Moss Hill layout"),
    "mb_pad7": ("1748,1018;1;spawnboard;apc", "one LAV-25 + one squad on pad 7 of the crashing Moss Hill layout"),
    # 03:30 which part of the APC, on the hillside where the reviewed test crashes 72/72 (one side, single squads):
    "mb_lav_plain": ("1700,1000;8;spawnboard;lav_plain", "the plain LAV-25 prefab instead of the Conflict variant"),
    "mb_btr": ("1700,1000;8;spawnboard;btr", "BTR-70 (Conflict) with Soviet squads"),
    "mb_btr_plain": ("1700,1000;8;spawnboard;btr_plain", "plain BTR-70 with Soviet squads"),
    "mb_apc_crew": ("1700,1000;8;spawnboard_crew;apc", "Conflict LAV-25, soldiers only into the driver and turret seats"),
    "mb_apc_cargo": ("1700,1000;8;spawnboard_cargo;apc", "Conflict LAV-25, soldiers only into the back"),
    # 03:45 the animation or the seat? the same reviewed test, the soldiers moved into / out of the seats without it:
    "mb_apc_tpin": ("1700,1000;8;spawnboard_tpin;apc", "in without the animation (teleport), out as usual"),
    "mb_apc_tpout": ("1700,1000;8;spawnboard_tpout;apc", "in as usual, out without the animation (teleport)"),
    "mb_apc_tp": ("1700,1000;8;spawnboard_tpin_tpout;apc", "in and out without the animation"),
    "mb_apc_kill": ("1700,1000;8;spawnboard_kill;apc", "US LAV-25s, everyone boarding at once, a soldier killed mid get-in up to 3 a cycle"),
}


def argv_for(scenario: str, variant: str, minutes: float, port: int, label: str) -> list:
    if variant in BOARD:
        mods = (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").strip()
        return [sys.executable, "-u", str(HERE / "reforger.py"), "--map", "arland-test", "--minutes", str(minutes), "--label", label,
                "--port", str(port), "--mods", mods, "--extra", f"-zcrBoardTest {BOARD[variant][0]}"]
    add, drop, drones, _ = VARIANTS[variant]
    mods = (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").strip()
    extra = (ROOT / ".runtime" / "watch_extra.txt").read_text(encoding="utf-8").strip()
    words = [w for w in extra.split() if w not in drop.split()] + add.split()
    argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", SCENARIOS[scenario][0], "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", STRATS.get(variant, ("modern", "phased"))[0], "--ussr", STRATS.get(variant, ("modern", "phased"))[1],
            "--mods", mods, "--extra", " ".join(words)]
    if variant in PLAN_SECONDS:
        argv += ["--plan-seconds", str(PLAN_SECONDS[variant])]
    if drones:
        argv.append("--drones")
    return argv


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    c = sorted(run_dir.glob("logs/*/console.log"))
    if not c:
        return {"scenario": scenario, "variant": variant, "error": "no log", "run": run_dir.name}
    t = c[-1].read_text(encoding="utf-8", errors="replace")
    lives = [int(x) for x in re.findall(r"\[ZCR\]\[LIVE\] t=(\d+)", t)] or [int(x) for x in re.findall(r"\[ZCR\]\[BOARDTEST[_A-Z]*\] t=(\d+)", t)]
    minutes = round(max(lives) / 60, 1) if lives else 0
    crash_log = c[-1].parent / "crash.log"
    ct = crash_log.read_text(encoding="utf-8", errors="replace") if crash_log.exists() else ""
    crashed = bool(list(c[-1].parent.glob("*.mdmp")))
    reason = ""
    if crashed:
        m = re.search(r"Reason: (.*)", ct)
        reason = m.group(1)[:70] if m else ""
    phys = re.findall(r"\[ZCR\]\[PHYS\] t=(\d+) what=(\w+) name=(\S+) kind=(\w+)", t)
    board_sum = re.findall(r"\[ZCR\]\[BOARDTEST_SUM\] t=(\d+) cycles=(\d+) issued=(\d+) seated=(\d+)", t)
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
    # 03:30 the boarding test's phase at the crash: the last event before it (BOARD = get-in ordered, ABOARD = all in,
    # DROP = get-out ordered, OUT = all out) and the seconds since - the crew-seat run crashed 9 s after DROP.
    phase, phase_s = "", None
    if crashed and crash_at:
        tc = datetime.strptime(crash_at.group(1), "%H:%M:%S.%f")
        ev = re.findall(r"^(\d\d:\d\d:\d\d\.\d+)\s+SCRIPT\s+: \[ZCR\]\[BOARDTEST\] t=\d+ cycle=\d+ event=(\w+)", t, re.M)
        ev = [(e, (tc - datetime.strptime(s, "%H:%M:%S.%f")).total_seconds()) for s, e in ev]
        ev = [x for x in ev if x[1] >= 0]
        if ev:
            phase, phase_s = ev[-1][0], round(ev[-1][1], 1)
    # the get-ins/get-outs started in the 20 s before the crash (ZCR_PhysWatch [ZCR][GETINOUT]): vehicle, tilt, seconds before
    moves = ""
    if crashed and crash_at:
        tc = datetime.strptime(crash_at.group(1), "%H:%M:%S.%f")
        mv = re.findall(r"^(\d\d:\d\d:\d\d\.\d+)\s+SCRIPT\s+: \[ZCR\]\[GETINOUT\] t=\d+ what=(\w+) man=\S+ vehicle=(\S+) "
                        r"seat=(\w+) pitch=(-?[\d.]+) roll=(-?[\d.]+)", t, re.M)
        mv = [(round((tc - datetime.strptime(s, "%H:%M:%S.%f")).total_seconds(), 1), w, v, st, pi, ro) for s, w, v, st, pi, ro in mv]
        mv = [m for m in mv if 0 <= m[0] <= 20]
        moves = "; ".join(f"{w} {v} {st} p{float(pi):.0f} r{float(ro):.0f} -{s}s" for s, w, v, st, pi, ro in mv[-4:])
    return {
        "scenario": scenario, "variant": variant, "run": run_dir.name, "minutes": minutes,
        "crash_phase": phase, "crash_phase_s": phase_s, "getinout_before": moves,
        "crashed": int(crashed), "crash_per_hour": round(60 * crashed / minutes, 2) if minutes else None,
        "reason": reason, "before_crash": before,
        "badmatrix_asserts": ct.count("BadMatrix33"), "oob_asserts": ct.count("out of world bounds"),
        "phys_wild": sum(1 for p in phys if p[1] == "wild"), "phys_spin": sum(1 for p in phys if p[1] == "spin"),
        "phys_nan": sum(1 for p in phys if p[1] == "nan"), "phys_falling": sum(1 for p in phys if p[1] == "falling"),
        "pushes": len(pushes), "turret_pushes": sum(1 for w in pushes if any(x in w for x in TURRETS)),
        "board_cycles": int(board_sum[-1][1]) if board_sum else None, "board_seated": int(board_sum[-1][3]) if board_sum else None,
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
    ap.add_argument("--gaming", action="store_true", help="Martin plays on this PC: one server, idle priority, pinned to the upper cores")
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
    bridges.ensure(("phased", "modern", "flip"))
    variants = a.variants.split(",")
    import cpu
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
            env.update(ENVS.get(variant, {}))
            proc = subprocess.Popen(argv_for("arland", variant, a.minutes, port, label), cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, env=env,
                                    creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS" if a.gaming else "BELOW_NORMAL_PRIORITY_CLASS", 0))
            running[port] = (variant, label, proc)
            log(f"start {label}")
            time.sleep(20)     # not all at the same second
        for port, (variant, label, proc) in list(running.items()):
            if proc.poll() is None:
                continue
            runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"), key=lambda r: r.stat().st_mtime)
            row = summarize(runs[-1], "arland", variant) if runs else {"scenario": "arland", "variant": variant, "error": "no run"}
            sublab.record("crash", row)
            log(f"done {label}: {row.get('minutes')} min crashed={row.get('crashed')} phase={row.get('crash_phase', '')}+{row.get('crash_phase_s')}s moves=[{row.get('getinout_before', '')}] {row.get('reason', '')} before=[{row.get('before_crash', '')}] "
                f"wild={row.get('phys_wild')} spin={row.get('phys_spin')} nan={row.get('phys_nan')} falling={row.get('phys_falling')} "
                f"turret_pushes={row.get('turret_pushes')}")
            del running[port]
        if a.gaming:
            cpu.pin_headless(True)   # every pass: a server started since is pinned too
        time.sleep(10)
    log("crash lab done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
