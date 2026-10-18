"""Run one Reforger match for the lab: a headless server with AI Conflict, our addon and AI
commanders on both sides, straight from the source folders (no packing), modelled on AI Conflict's
own launcher (tools/Start-AICFRuntime.ps1).

    python lab/reforger.py --map everon --minutes 30 --label base1             # AI Conflict + our hooks
    python lab/reforger.py --map everon --minutes 30 --label llm1 --bridge     # with the bridge
    python lab/reforger.py --map everon --dry-run                              # print the command only

Each run gets a fresh profile in .runtime/runs/<label>-<stamp>; the server's console.log there is
measured by metrics.py when the match ends, and $profile:zcr/snapshots.jsonl keeps the situation
reports for replay.py. The match on screen (for watching and recording) joins with --client.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import metrics  # noqa: E402

STEAM = Path(r"E:\SteamLibrary\steamapps\common")
SERVER_ROOT = STEAM / "Arma Reforger Server"
GAME_ROOT = STEAM / "Arma Reforger"
AICF = Path(r"D:\work\reforger-ai-conflict")
OUR_ADDON = "CA2CA4E14BB55417"
CORE = "9178E5822AFE48EA,B52C5F6AEDBF423E"
MAPS = {
    # map: (AI Conflict project, extra addon ids, scenario, mission header)
    "arland": ("AIConflictArland", "", "{BC2437E4861B4FD2}Missions/AICF_Conflict_Arland.conf", "Missions/AICF_Conflict_Arland.conf"),
    "everon": ("AIConflictEveron", "A4B2E62595F645A4", "{4C5D73A5614F41D9}Missions/AICF_Conflict_Everon.conf", "Missions/AICF_Conflict_Everon.conf"),
}
READY = "[AICF][STAGE1][INFO][ROSTER_READY]"


def command(a, profile: Path) -> list:
    project, extra, scenario, header = MAPS[a.map]
    addons = ",".join(x for x in (CORE, extra, OUR_ADDON) if x)
    exe = (SERVER_ROOT / "ArmaReforgerServerDiag.exe") if not a.client else (GAME_ROOT / "ArmaReforgerSteamDiag.exe")
    roots = [str(AICF), str(ROOT), str((SERVER_ROOT if not a.client else GAME_ROOT) / "addons")]
    cmd = [str(exe), "-gproj", str(AICF / project / "addon.gproj")]
    cmd += ["-server", scenario, "-MissionHeader", header, "-worldSystemsConfig", "Configs/Systems/ConflictSystems.conf"] \
        if not a.client else ["-client", f"127.0.0.1:{a.port}"]
    cmd += ["-addonsDir", ",".join(roots), "-addons", addons, "-profile", str(profile), "-backendFreshSession"]
    if not a.client:
        cmd += ["-aicfAICommanderMode", "BOTH", "-maxFPS", "60", "-logStats", "10000",
                "-zcrPlanSeconds", str(a.plan_seconds)]
        if a.bridge:
            cmd += ["-zcrBridge", a.bridge_url]
    return cmd


def console_log(profile: Path):
    logs = sorted(profile.glob("logs/*/console.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="everon", choices=sorted(MAPS))
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--label", default="run")
    ap.add_argument("--port", type=int, default=2001)
    ap.add_argument("--plan-seconds", type=int, default=90)
    ap.add_argument("--bridge", action="store_true", help="send situation reports to the bridge (start lab/bridge.py first)")
    ap.add_argument("--bridge-url", default="http://127.0.0.1:8765")
    ap.add_argument("--client", action="store_true", help="the game on screen, joining the local server")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    profile = ROOT / ".runtime" / "runs" / f"{a.label}-{'client-' if a.client else ''}{stamp}"
    cmd = command(a, profile)
    if a.dry_run:
        print(json.dumps(cmd, indent=1))
        return 0
    exe = Path(cmd[0])
    if not exe.is_file():
        print(f"missing {exe} - install it first (Steam: Library > Tools > Arma Reforger Server)")
        return 1
    profile.mkdir(parents=True)
    proc = subprocess.Popen(cmd, cwd=str(exe.parent))
    print(f"{'client' if a.client else 'server'} started (pid {proc.pid}), profile {profile}", flush=True)
    if a.client:
        return 0
    t0, ready_at = time.time(), None
    try:
        while proc.poll() is None:
            time.sleep(5)
            log = console_log(profile)
            if ready_at is None and log and READY in log.read_text(encoding="utf-8", errors="replace"):
                ready_at = time.time()
                print(f"both sides' squads are deployed after {round(ready_at - t0)} s; the match runs {a.minutes} min", flush=True)
            if ready_at is None and time.time() - t0 > 600:
                print("no ROSTER_READY in 10 minutes - stopping")
                break
            if ready_at and time.time() - ready_at > a.minutes * 60:
                break
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(30)
            except subprocess.TimeoutExpired:
                proc.kill()
    log = console_log(profile)
    if not log:
        print("no console.log written")
        return 1
    m = metrics.measure(log.read_text(encoding="utf-8", errors="replace").splitlines())
    (profile / "metrics.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(json.dumps(m, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
