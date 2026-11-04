"""The alpha's load test: one headless server (port 2198) with only the release items and their dependencies, the alpha
scenario, no launch parameters of ours on the command line (the scenario's own m_sAICFLaunchParams must do it) and no
Python helper beside it (no strategist bridge, no live planner) - what a player gets.

    python tools/release/loadtest.py --minutes 4                 # from the release worktrees' source projects
    python tools/release/loadtest.py --minutes 25 --packed D:/work/release/packed   # from the packed addons
    python tools/release/loadtest.py --summary <run folder>      # read a finished run again

Pass: the scripts compile, [AICF][LAUNCH] lists the scenario's parameters, the in-game point general plans both sides
(PLAN source=point-ingame), and no script error of ours (AI Conflict's own logged ERROR lines - Failed move,
MEANINGFUL_TASK, CORE_ERROR_BRIDGE - are its routine reports, not script errors). The server is ours alone: started here,
stopped here by its own process id, pinned off the watched game's cores like the lab's headless servers.
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
R1 = HERE.parent.parent                                   # D:/work/release/reforger-commander
R2 = R1.parent / "reforger-ai-conflict"                   # D:/work/release/reforger-ai-conflict
RUNS = R1.parent / "runs"
DEPS = R1.parent / "deps"                                 # junctions to the dependencies only (source runs)
DEPS_PACKED = R1.parent / "deps-packed"                   # ... the three Workshop mods (packed runs)
SERVER = Path("E:/SteamLibrary/steamapps/common/Arma Reforger Server")
EXE = SERVER / "ArmaReforgerServerDiag.exe"
PORT = 2198
SCENARIO = "{E035D09029D235F6}Missions/ZCR_Alpha_Beauregard.conf"
OURS = "CF39E4A7CCBBF845,ACAA98B674F022BB,CA2CA4E14BB55417,CF67CCE40B62DA50"     # fork Core, fork Arland, ZCR, the alpha
WORKSHOP = "5EDAAE0D3CC60D6B,68FCF11534562F2E,3257E44260058CE5,65AD60E204191D37"  # DCO, Competent AI driving, FPV AI Drones, RCD
DEP_DIRS = {   # dependency folder name -> where it is on this PC
    "DCO_AIReforger_5EDAAE0D3CC60D6B": "D:/work/_mods_dl/addons/DCO_AIReforger_5EDAAE0D3CC60D6B",
    "CompetentAIdriving_68FCF11534562F2E": "D:/work/_mods_dl/addons/CompetentAIdriving_68FCF11534562F2E",
    "RealisticCombatDrones_65AD60E204191D37": "E:/ArmaReforgerMods/addons/RealisticCombatDrones_65AD60E204191D37",
}
FPV_SOURCE = "D:/work/reforger-local-mods/FPV_AI_Drones"   # the FPV AI Drones build the battles run (source project)


def deps(packed: Path | None) -> Path:
    """The dependency folder: a junction per dependency (rmdir removes a junction, never its target). Packed runs get
    their own folder with the three Workshop mods only (FPV AI Drones comes packed with the release items)."""
    folder = DEPS_PACKED if packed else DEPS
    folder.mkdir(parents=True, exist_ok=True)
    want = dict(DEP_DIRS)
    if not packed:
        want["FPV_AI_Drones"] = FPV_SOURCE
    for name, target in want.items():
        link = folder / name
        if not link.exists():
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(Path(target))], capture_output=True, check=True)
    return folder


def command(profile: Path, packed: Path | None, header: bool, dep_dir: Path) -> list:
    roots = ([str(packed)] if packed else [str(R2), str(R1)]) + [str(dep_dir), str(SERVER / "addons")]
    cmd = [str(EXE)]
    if not packed:
        cmd += ["-gproj", str(R1 / "ZCR_Alpha" / "addon.gproj")]
    cmd += ["-server", SCENARIO]
    if header:
        cmd += ["-MissionHeader", "Missions/ZCR_Alpha_Beauregard.conf"]
    cmd += ["-addr", f"127.0.0.1:{PORT}", "-addonsDir", ",".join(roots), "-addons", OURS + "," + WORKSHOP,
            "-profile", str(profile), "-backendFreshSession", "-noThrow", "-maxFPS", "60", "-logStats", "10000"]
    return cmd


def busy_port() -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name='ArmaReforgerServerDiag.exe'\" | Select-Object -ExpandProperty CommandLine"],
                         capture_output=True, text=True).stdout
    return "\n".join(l for l in out.splitlines() if f":{PORT}" in l)


OUR_FILES = re.compile(r"(ZeusCommanderReforger|ZCR_Alpha|AIConflict(Core|Arland)?|FPVAI)/[^\s:]*\.c")
SCRIPT_ERRORS = re.compile(r"Virtual Machine Exception|NULL pointer|Can't compile|Compile error|Script compilation failed|"
                           r"Unknown (type|class)|Undefined|Function .* not found|Reason:", re.I)


def summary(run: Path) -> dict:
    logs = sorted(run.glob("logs/*/console.log"))
    if not logs:
        return {"run": run.name, "error": "no console log"}
    text = logs[-1].read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    err_lines = []
    for extra in ("script.log", "error.log"):
        f = logs[-1].parent / extra
        if f.exists():
            err_lines += f.read_text(encoding="utf-8", errors="replace").splitlines()
    # A failed AI move is reported as a "Virtual Machine Exception" with "Reason: Failed move ..." - the game's behaviour
    # tree giving up a path (noise, as AI Conflict's own ERROR reports); every other exception counts.
    noise = set()
    for src in (lines, err_lines):
        for i, l in enumerate(src):
            if "Virtual Machine Exception" in l and any("Reason: Failed move" in x for x in src[i + 1:i + 4]):
                noise.add(l)
                noise.update(x for x in src[i + 1:i + 4] if "Reason:" in x)
    ours = [l for l in lines + err_lines if ("(E)" in l or "ERROR" in l or "Reason:" in l) and (SCRIPT_ERRORS.search(l) or OUR_FILES.search(l))
            and "[AICF]" not in l and l not in noise]
    ours = list(dict.fromkeys(ours))   # console.log and script.log repeat the same lines
    lost = {"US": 0, "USSR": 0}
    for m in re.finditer(r"\[ZCR\]\[LOSS\] t=\d+ victim=\S+ side=(\w+) kind=man", text):
        if m.group(1) in lost:
            lost[m.group(1)] += 1
    plans = re.findall(r"\[ZCR\]\[PLAN\] faction=(\w+) revision=(\d+) source=(\S+) .*?intent=(.*)", text)
    last_plan = {}
    for side, rev, src, intent in plans:
        last_plan[side] = {"revision": int(rev), "source": src, "intent": intent.strip()}
    efforts = {}
    for m in re.finditer(r"\[ZCR\]\[EFFORTS\] t=(\d+) side=(\w+) json=(.*)", text):
        try:
            e = json.loads(m.group(3))
        except ValueError:
            continue
        efforts[m.group(2)] = {"t": int(m.group(1)), "main": e.get("main"),
                               "attack": [(a.get("base"), a.get("teams"), f"{a.get('there')}/{a.get('men')}") for a in e.get("attack") or []]}
    ts = re.findall(r"\[ZCR\]\[\w+\] t=(\d+)", text)
    fps = [float(x) for x in re.findall(r"DEFAULT\s+: FPS: ([\d.]+)", text)]
    return {
        "run": run.name,
        "game_s": int(ts[-1]) if ts else 0,
        "compiled": "Compiling Game scripts" in text and not re.search(r"Can't compile|Script compilation failed", text),
        "launch": [l.split("[AICF][LAUNCH] ", 1)[1][:600] for l in lines if "[AICF][LAUNCH]" in l],
        "roster_ready": "[AICF][STAGE1][INFO][ROSTER_READY]" in text,
        "plans": last_plan,
        "plan_sources": sorted({p[2] for p in plans}),
        "captures": re.findall(r"\[ZCR\]\[CAPTURE\] t=(\d+) base=(.+?) from=(\w*) to=(\w*)", text),
        "score": (re.findall(r"\[ZCR\]\[SCORE\] t=\d+ (US=\d+ USSR=\d+)", text) or [""])[-1],
        "lost": lost,
        "drone_launches": len(re.findall(r"\[ZCR\]\[DRONES\] t=\d+ side=\w+ .*?kind=", text)),
        "efforts": efforts,
        "fps_median": sorted(fps)[len(fps) // 2] if fps else None,
        "failed_moves": len([l for l in noise if "Virtual Machine Exception" in l]),
        "script_errors_ours": ours[:30],
        "script_errors_ours_count": len(ours),
        "bridge_lines": len(re.findall(r"\[ZCR\]\[BRIDGE_SEND\]", text)),
        "attackplan_warning": "no $profile:zcr/attackplan.txt" in text,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=4)
    ap.add_argument("--packed", default="")
    ap.add_argument("--label", default="alpha")
    ap.add_argument("--header", action="store_true", help="also pass -MissionHeader (as the lab does)")
    ap.add_argument("--summary", default="")
    a = ap.parse_args()
    if a.summary:
        print(json.dumps(summary(Path(a.summary)), indent=1))
        return 0
    if busy_port():
        print(f"port {PORT} is in use by another server - not started")
        return 1
    packed = Path(a.packed) if a.packed else None
    dep_dir = deps(packed)
    profile = RUNS / f"{a.label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    profile.mkdir(parents=True)
    cmd = command(profile, packed, a.header, dep_dir)
    (profile / "run.json").write_text(json.dumps({"command": cmd, "minutes": a.minutes, "packed": str(packed or "")}, indent=1), encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(EXE.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    print(f"server pid {proc.pid}, profile {profile}", flush=True)
    sys.path.insert(0, str(R1 / "lab"))
    try:
        import cpu
        cpu.pin_if_watched(proc.pid)   # off the watched game's cores (lab note 279)
    except Exception as e:
        print(f"(not pinned: {e})")
    end = time.time() + a.minutes * 60 + 90   # + the start (scripts, world, roster)
    try:
        while time.time() < end and proc.poll() is None:
            time.sleep(10)
    finally:
        if proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)   # our own server only
    s = summary(profile)
    s["exit"] = proc.returncode
    (profile / "summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    print(json.dumps(s, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
