"""Pack the alpha's addons headless with Workbench's own command line (-wbModule=ResourceManager -packAddon; see
Arma Reforger Tools/Workbench/docs/EnfusionScriptAPI/html/Page_CLI.html): each into D:/work/release/packed/<ID>_<GUID>,
the folder layout a server or the game reads Workshop addons from. Packing compiles the scripts first ("Addon cannot be
packed due to failed script compilation!").

    python tools/release/pack.py              # all five, in dependency order
    python tools/release/pack.py ZCR_Alpha    # one

Workbench opens minimised and not in front (the game window may be on screen). This is the packed build check only:
publishing is Martin's step in Workbench (the first publish of an item can't be done from the command line - its
-publishAddon is for updates).
"""
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R1 = HERE.parent.parent
R2 = R1.parent / "reforger-ai-conflict"
OUT = R1.parent / "packed"
CACHE = R1.parent / "pack-cache"
LOGS = R1.parent / "pack-logs"
WB = Path("E:/SteamLibrary/steamapps/common/Arma Reforger Tools/Workbench/ArmaReforgerWorkbenchSteamDiag.exe")
GAME_ADDONS = Path("E:/SteamLibrary/steamapps/common/Arma Reforger/addons")
DEPS = R1.parent / "deps"
ADDONS = [   # (project folder, its dependencies as -addons)
    (R2 / "AIConflictCore", ""),
    (R2 / "AIConflictArland", "CF39E4A7CCBBF845"),
    (R1 / "ZeusCommanderReforger", "CF39E4A7CCBBF845,ACAA98B674F022BB"),
    (DEPS / "FPV_AI_Drones", "65AD60E204191D37"),   # the junction tools/release/loadtest.py makes (one path per addon)
    (R1 / "ZCR_Alpha", "CF39E4A7CCBBF845,ACAA98B674F022BB,CA2CA4E14BB55417,5EDAAE0D3CC60D6B,68FCF11534562F2E,3257E44260058CE5,65AD60E204191D37"),
]


def gproj(folder: Path) -> tuple:
    t = (folder / "addon.gproj").read_text(encoding="utf-8")
    return re.search(r'ID "([^"]+)"', t).group(1), re.search(r'GUID "([0-9A-F]+)"', t).group(1)


def pack(folder: Path, deps: str) -> dict:
    pid, guid = gproj(folder)
    out = OUT / f"{pid}_{guid}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    logs = LOGS / f"{pid}-{time.strftime('%Y%m%d-%H%M%S')}"
    logs.mkdir(parents=True)
    roots = [str(R2), str(R1), str(DEPS), str(GAME_ADDONS)]
    # No -wbsilent: in silent mode Workbench quits before its Resource Manager (where -packAddon runs) opens.
    cmd = [str(WB), "-noThrow", "-gproj", str(folder / "addon.gproj"), "-addonsDir", ",".join(roots)]
    if deps:
        cmd += ["-addons", deps]
    cmd += ["-logsDir", str(logs), "-wbModule=ResourceManager", "-packAddon", "-packAddonDir", str(out),
            "-packAddonCacheDir", str(CACHE / pid)]
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7   # SW_SHOWMINNOACTIVE: minimised, never in front
    t0 = time.time()
    p = subprocess.Popen(cmd, startupinfo=si, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        rc = p.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)   # our own Workbench only
        rc = "timeout"
    files = sorted(x.relative_to(out).as_posix() for x in out.rglob("*") if x.is_file())
    log = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in sorted(logs.rglob("*.log")))
    errors = [l for l in log.splitlines() if re.search(r"\(E\)|cannot be packed|failed", l, re.I)][:20]
    return {"addon": f"{pid}_{guid}", "exit": rc, "seconds": round(time.time() - t0), "files": files,
            "size_mb": round(sum(x.stat().st_size for x in out.rglob("*") if x.is_file()) / 1e6, 2), "errors": errors,
            "logs": str(logs)}


def main() -> int:
    only = set(sys.argv[1:])
    ok = True
    for folder, deps in ADDONS:
        if only and folder.name not in only:
            continue
        r = pack(folder, deps)
        print(r, flush=True)
        ok = ok and r["exit"] == 0 and bool(r["files"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
