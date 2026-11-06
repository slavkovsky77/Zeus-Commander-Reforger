"""The release night of 6 Nov (Martin, 02:50: "prepare mods for release", "watch for crashes, test shit", "a night of all the
integration tests because of the update", "test battle on everon or arland with not fixed battle point"). Two lanes of
headless jobs, one after another in each, from when the PC's dedicated server is on the new game build. Every server start
goes through the PC's game lock (lab/gamelock.py), so the Faces session gets its slots between jobs.

    python lab/night6.py            # wait for the server update, then both lanes
    python lab/night6.py --plan     # the jobs, run nothing
Stop between jobs: create .runtime/night/stop. Log: .runtime/night/night6.log; each job's output in .runtime/night/night6/.
"""
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FPV = Path(r"D:\work\fpv-ai-reforger")
REL = Path(r"D:\work\release\reforger-commander")
OUT = ROOT / ".runtime" / "night" / "night6"
LOG = ROOT / ".runtime" / "night" / "night6.log"
STOP = ROOT / ".runtime" / "night" / "stop"
MANIFEST = Path(r"E:\SteamLibrary\steamapps\appmanifest_1874900.acf")
PY = sys.executable


def sub(name, scenario, variant, port):
    return (f"{name}-{scenario}-{variant}", ROOT, [PY, "-u", "lab/sublab.py", "run", name, "--scenario", scenario, "--variant", variant, "--port", str(port)])


A, B = 2148, 2150
LANES = {
    "A": [
        ("fpv-suite", FPV, [PY, "-u", "tools/run_mp.py", "--port", "2196", "--others", "--low", "--timeout-minutes", "50", "--cases",
                            "uaz,btr,infantry,route,miss,moving,indoor,indoorclosed,canopy,housedoor,garage,swarm,longhold"]),
        ("alpha-packed", REL, [PY, "-u", "tools/release/loadtest.py", "--minutes", "25", "--packed", "D:/work/release/packed", "--label", "alpha-packed-193322"]),
        *[sub("guns", s, "default", A) for s in ("apc-duel", "apc-vs-squad", "tank-duel", "ifv-vs-squad")],
        *[sub("driving", s, "default", A) for s in ("headon", "convoy", "traffic", "bridge", "farm-conflict")],
        *[sub("vans", "apron", v, A) for v in ("van_ussr", "uaz469_ussr")],
        sub("transport", "arland", "nowalk2", A),
        *[sub("infantry", s, "dco", A) for s in ("storm-foot", "storm-village", "farm-drones-both")],
    ],
    "B": [
        ("map-arland-doctrine", ROOT, [PY, "-u", "lab/maptest.py", "--map", "arland", "--variant", "doctrine", "--minutes", "60", "--port", str(B)]),
        ("map-arland-aicf", ROOT, [PY, "-u", "lab/maptest.py", "--map", "arland", "--variant", "aicf", "--minutes", "60", "--port", str(B)]),
        ("map-everon-doctrine", ROOT, [PY, "-u", "lab/maptest.py", "--map", "everon", "--variant", "doctrine", "--minutes", "60", "--port", str(B)]),
        sub("crash", "arland", "default", B),
        *[sub("assault", s, "team4-bind", B) for s in ("ussr", "us")],
        *[sub("building", s, "default", B) for s in ("near2", "farm")],
    ],
}


def say(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def server_updated() -> bool:
    t = MANIFEST.read_text(encoding="utf-8", errors="replace")
    b = re.search(r'"buildid"\s+"(\d+)"', t)
    target = re.search(r'"TargetBuildID"\s+"(\d+)"', t)
    flags = re.search(r'"StateFlags"\s+"(\d+)"', t)
    return bool(b and flags and flags.group(1) == "4" and (not target or target.group(1) in ("0", b.group(1))))


def lane(name):
    for job, cwd, argv in LANES[name]:
        if STOP.exists():
            say(f"lane {name}: stop file - ending")
            return
        say(f"lane {name}: {job} starts")
        t0 = time.time()
        with open(OUT / f"{job}.out", "w", encoding="utf-8") as f:
            try:
                rc = subprocess.run(argv, cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, timeout=4 * 3600).returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
        say(f"lane {name}: {job} done in {round((time.time() - t0) / 60)} min, exit {rc}")


def main() -> int:
    if "--plan" in sys.argv:
        for n, jobs in LANES.items():
            for job, cwd, argv in jobs:
                print(n, job, cwd, " ".join(argv[1:]))
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    say("night6: waiting for the dedicated server's update (appmanifest 1874900)")
    t0 = time.time()
    while not server_updated():
        if STOP.exists():
            return 0
        if time.time() - t0 > 4 * 3600:
            say("night6: no server update in 4 hours - giving up")
            return 1
        time.sleep(60)
    say("night6: the server is on the new build - both lanes start")
    time.sleep(30)
    threads = [threading.Thread(target=lane, args=(n,)) for n in LANES]
    for t in threads:
        t.start()
        time.sleep(90)   # the second server starts after the first is up
    for t in threads:
        t.join()
    say("night6: all done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
