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

import config  # noqa: E402  - this machine's paths: lab/lab.toml + lab/lab.local.toml

STEAM = config.path("paths.steam")
SERVER_ROOT = STEAM / "Arma Reforger Server"
GAME_ROOT = STEAM / "Arma Reforger"
AICF = config.path("paths.ai_conflict")
OUR_ADDON = "CA2CA4E14BB55417"
# The FPV AI Drones for Reforger mod and Realistic Combat Drones, which it needs (paths.mod_dirs).
DRONE_DIRS = config.paths("paths.mod_dirs")
DRONE_ADDONS = "3257E44260058CE5,65AD60E204191D37"
CORE = "9178E5822AFE48EA,B52C5F6AEDBF423E"
# Armour (Martin, 21 Oct: "more types of vehicles - APC, tanks... maybe use some mods"): one family of
# Workshop mods on the same two bases (SpaceCore, WCS_Armaments) - M2A2 Bradley, BMP-1, M1A1 Abrams,
# T-72. ZCR_Armour buys them for each side when they're loaded (else the game's LAV-25 / BTR-70).
ARMOUR_ADDONS = "5E389BB9F58B79A6,629B2BA37EFFD577,63120AE07E6C0966,5E524E4FEECCA92B,5D1880C4AD410C14,5E0AB16BEB16D6A4"
ARMOUR_DIR = str(config.path("paths.armour_dir")) if config.get("paths.armour_dir") else ""   # the Workshop mods folder
# The strategist bridges (lab/bridge.py), shared by every match on this PC.
BRIDGES = {"llm": 8765, "doctrine": 8766, "phased": 8767, "llm-phased": 8768}
MAPS = {
    # map: (AI Conflict project, extra addon ids, scenario, mission header)
    "arland": ("AIConflictArland", "", "{BC2437E4861B4FD2}Missions/AICF_Conflict_Arland.conf", "Missions/AICF_Conflict_Arland.conf"),
    "everon": ("AIConflictEveron", "A4B2E62595F645A4", "{4C5D73A5614F41D9}Missions/AICF_Conflict_Everon.conf", "Missions/AICF_Conflict_Everon.conf"),
    # Yunakivka (Martin, 20 Oct: "commonly used in multiplayer, a lot of trenches"): SpearHead's "SH UHC
    # Yunakivka" is Conflict (GameMode_Campaign, ConflictBase prefabs, US/USSR/FIA, remnant supply depots) -
    # AI Conflict's bootstrap (in AIConflictArland) runs on it. The map mod and its dependencies.
    "yunakivka": ("AIConflictArland", "6A2C1C65791CE941,68D6FA70573ED4FE,6A46B8CB8111095A,66D60C6AD1621BF0,69770D09755CE1DC,646518DA09B1E283,673AD67900BE5E70",
                  "{869411EFF47B7AF5}Missions/SH UHC Yunakivka.conf", "Missions/SH UHC Yunakivka.conf"),
}
READY = "[AICF][STAGE1][INFO][ROSTER_READY]"


def command(a, profile: Path) -> list:
    project, extra, scenario, header = MAPS[a.map]
    armour = getattr(a, "armour", False)
    addons = ",".join(x for x in (CORE, extra, OUR_ADDON, DRONE_ADDONS if a.drones else "", ARMOUR_ADDONS if armour else "") if x)
    # Solo: the game itself hosts the match (singleplayer, like Arma 3's watched games) - only there
    # the diagnostic build's Diag Menu > Cheats > "DTime multiplier" speeds the whole game up.
    solo = getattr(a, "solo", False)
    game = a.client or solo
    exe = (SERVER_ROOT / "ArmaReforgerServerDiag.exe") if not game else (GAME_ROOT / "ArmaReforgerSteamDiag.exe")
    mod_dirs = DRONE_DIRS if a.drones or a.map == "yunakivka" else ([ARMOUR_DIR] if armour else [])
    roots = [str(AICF), str(ROOT)] + mod_dirs + [str((SERVER_ROOT if not game else GAME_ROOT) / "addons")]
    cmd = [str(exe), "-gproj", str(AICF / project / "addon.gproj")]
    cmd += ["-server", scenario, "-MissionHeader", header, "-worldSystemsConfig", "Configs/Systems/ConflictSystems.conf",
            "-addr", f"127.0.0.1:{a.port}"] if not a.client else ["-client", f"127.0.0.1:{a.port}"]
    # -noThrow: the debug builds' assertions (e.g. a smoking animation's thread check in vanilla)
    # don't stop the game with a dialog; they are still logged.
    cmd += ["-addonsDir", ",".join(roots), "-addons", addons, "-profile", str(profile), "-backendFreshSession", "-noThrow"]
    if not a.client:
        # -aicfConstructionAttempts 512 (AI Conflict's maximum, default 256): Arland's harbour main base
        # is cramped (water, access corridors) and its side's barracks search ran out of budget - that
        # side never recruited (19 Oct 13:27 US, 15:36 USSR).
        cmd += ["-aicfAICommanderMode", "BOTH", "-maxFPS", "60", "-logStats", "10000", "-aicfConstructionAttempts", "512",
                "-zcrPlanSeconds", str(a.plan_seconds), "-zcrLabWeather"]
        if a.bridge:
            cmd += ["-zcrBridge", a.bridge_url]
        # A strategist per side (head-to-head): none = AI Conflict alone, doctrine, llm.
        for side in ("us", "ussr"):
            name = getattr(a, side, "") or ""
            if name:
                url = f"http://127.0.0.1:{BRIDGES[name]}" if name in BRIDGES else "none"
                cmd += [f"-zcrBridge{side.upper()}", url]
        if a.drones:
            cmd += ["-zcrDrones"]        # strategist sides send FPV teams to their objectives
        cmd += (getattr(a, "extra", "") or "").split()   # lab settings, e.g. -zcrStormPriority 100
        if a.watch:
            cmd += ["-zcrWatchServer"]   # players get the whole map (they only watch)
        if solo and a.watch:
            cmd += ["-zcrWatch"]
    elif a.watch:
        cmd += ["-zcrWatch"]             # the director camera instead of the game's menus
    return cmd


def window_settings(profile: Path) -> None:
    """The game on screen opens in the game's own MAXIMIZED mode - a normal window with borders at the
    screen's resolution (Martin: windowed, full resolution). Resizing the window from outside left
    the picture at the default 1280x720 in a corner; the game sizes it right only from its settings."""
    docs = Path.home() / "Documents" / "My Games" / "ArmaReforger" / "profile" / ".save"
    users = sorted(docs.glob("app1874880_user*")) if docs.exists() else []
    name = users[0].name if users else "app1874880_user0"
    import ctypes
    w, h = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
    d = profile / ".save" / name / "settings"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["EngineUserSettings {", " VideoUserSettings VideoUserSettings {", '  MaxFps "60"', "  WindowMode MAXIMIZED",
             f"  ScreenWidth {w}", f"  ScreenHeight {h}", "  ResolutionScale 1", "  WindowPosX 0", "  WindowPosY 0", " }", "}", ""]
    (d / "ReforgerEngineSettings.conf").write_text(chr(10).join(lines), encoding="utf-8")


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
    ap.add_argument("--solo", action="store_true", help="the game on screen hosting the match itself (singleplayer; the Diag Menu's time multiplier works here)")
    ap.add_argument("--drones", action="store_true", help="load FPV AI Drones + Realistic Combat Drones")
    ap.add_argument("--armour", action="store_true", help="load the armour mods (Bradley, BMP-1, Abrams, T-72) for ZCR_Armour")
    ap.add_argument("--watch", action="store_true", help="server: watchers see the whole map; client: director camera")
    ap.add_argument("--us", default="", help="US strategist: none, doctrine, llm, phased, llm-phased")
    ap.add_argument("--ussr", default="", help="USSR strategist")
    ap.add_argument("--extra", default="", help="more server parameters, e.g. '-zcrStormPriority 100'")
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
    if a.client or getattr(a, "solo", False):
        window_settings(profile / "profile")
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
