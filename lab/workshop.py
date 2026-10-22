"""Get Workshop mods to read how they solve one of our issues (the loop's 'has someone solved it already?' step).

    python lab/workshop.py get 6A8490E1621E7B3C D6B2CB76BADE18C3   # download (or find) the mods
    python lab/workshop.py unpack 6A8490E1621E7B3C                  # its scripts and configs into <dir>/_src/<id>

A mod already in paths.armour_dir (the owner's game mods folder) is used from there. Others are downloaded
by the dedicated server, which fetches the mods named in a server config: started from its own folder (or
it misses the base game), idle priority, a spare port, a scratch profile; stopped once every mod is there.
Run it between watched matches: an error dialog of any Reforger server used to end the watched match
(22 Oct, w5 of the 03:16 rerun; the loop now counts only its own processes' dialogs).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import pakread  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SERVER_ROOT = config.path("paths.steam") / "Arma Reforger Server"
DOWNLOADS = Path(config.get("paths.workshop_dir") or "D:/work/_mods_dl")
OWNER_MODS = Path(config.path("paths.armour_dir")) if config.get("paths.armour_dir") else None
PORT = 2199


def find(mod_id: str):
    for root in (DOWNLOADS, OWNER_MODS):
        if root and root.is_dir():
            for d in root.iterdir():
                if d.is_dir() and d.name.upper().endswith("_" + mod_id.upper()) and (d / "data.pak").is_file():
                    return d
    return None


def get(ids: list, timeout_s: int = 600) -> dict:
    found = {i: find(i) for i in ids}
    missing = [i for i, d in found.items() if d is None]
    if missing:
        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        work = ROOT / ".runtime" / "workshop"
        (work / "profile").mkdir(parents=True, exist_ok=True)
        cfg = work / "server.json"
        cfg.write_text(json.dumps({
            "bindAddress": "127.0.0.1", "bindPort": PORT, "publicAddress": "127.0.0.1", "publicPort": PORT,
            "game": {"name": "zcr workshop download", "password": "zcrdl", "scenarioId": "{ECC61978EDCC2B5A}Missions/23_Campaign.conf",
                     "maxPlayers": 1, "visible": False, "crossPlatform": False,
                     "gameProperties": {"battlEye": False},
                     "mods": [{"modId": i, "name": i} for i in missing]}}, indent=1), encoding="utf-8")
        argv = [str(SERVER_ROOT / "ArmaReforgerServer.exe"), "-config", str(cfg), "-addonDownloadDir", str(DOWNLOADS),
                "-addonsDir", f"{SERVER_ROOT / 'addons'},{DOWNLOADS}", "-profile", str(work / "profile"), "-maxFPS", "10", "-noThrow"]
        proc = subprocess.Popen(argv, cwd=str(SERVER_ROOT), creationflags=0x40,   # IDLE_PRIORITY_CLASS
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        try:
            while time.time() - t0 < timeout_s and proc.poll() is None:
                time.sleep(3)
                if all(find(i) for i in missing):
                    time.sleep(5)   # the last files of the last mod
                    break
        finally:
            if proc.poll() is None:
                proc.kill()
        found = {i: find(i) for i in ids}
    for i, d in found.items():
        print(f"{i} {d if d else 'NOT FOUND (wrong id, removed, or the download failed: see .runtime/workshop/profile/logs)'}")
    return found


def unpack(mod_id: str) -> Path:
    d = find(mod_id)
    if not d:
        sys.exit(f"{mod_id}: not downloaded - run get first")
    out = DOWNLOADS / "_src" / mod_id
    with open(d / "data.pak", "rb") as f:
        ch = pakread.chunks(f)
        off, size = ch["FILE"]
        f.seek(off)
        files = pakread.tree(f.read(size))
        n = 0
        for path, offset, stored, original, _flag in files:
            if path.endswith((".c", ".conf", ".et", ".ct", ".layout", ".gproj", ".txt", ".json", ".st")):
                dst = out / path
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(pakread.read_file(f, offset, stored, original))
                n += 1
    print(f"{mod_id}: {n} files of {len(files)} -> {out}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["get", "unpack"])
    ap.add_argument("ids", nargs="+")
    a = ap.parse_args()
    if a.what == "get":
        get(a.ids)
    else:
        get(a.ids)
        for i in a.ids:
            if find(i):
                unpack(i)


if __name__ == "__main__":
    main()
