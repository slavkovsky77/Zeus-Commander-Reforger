"""The night's blast slot (23 Oct, review note 311): a wreck on the lane - the head-on track with a hit every 150 s and
convoys whose lead is hit at the lane every second convoy - for the game's driver alone, our v1 rules and v2 (the
collision forecast). Starts when the v2 slot (risknight.py) has finished, then one 10-minute run at a time on port 2152;
rows into the main repo's driving sub-lab. Extra tracks named on the command line run after these (e.g. traffic)."""
import importlib
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drivetest  # noqa: E402  (this copy's runner and scripts)

spec = importlib.util.spec_from_file_location("main_sublab", r"D:\work\reforger-commander\lab\sublab.py")
main_sublab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_sublab)


def busy(word: str) -> bool:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object -ExpandProperty CommandLine"],
                         capture_output=True, text=True).stdout
    return word in out


while busy("risknight.py"):
    time.sleep(60)
print(time.strftime("%H:%M:%S"), "v2 slot finished, blast slot starts", flush=True)

tracks = ["headonblast", "convoyblast"] + sys.argv[1:]
for rep in range(2):
    for track in tracks:
        importlib.reload(drivetest)   # tracks added during the night
        if track not in drivetest.TRACKS:
            print(track, "unknown, skipped", flush=True)
            continue
        for variant in ("raw", "default", "risk"):
            r = drivetest.run(track, variant, 10, 8 if track == "headonblast" else 6, 2152)
            r["rep"] = rep
            r["copy"] = "blast"
            row = main_sublab.record("driving", r)
            print(time.strftime("%H:%M:%S"), track, variant, rep, {k: row.get(k) for k in ("legs", "lost", "car_hits", "jams", "blasts", "blocked", "pass_s", "score")}, flush=True)
print(time.strftime("%H:%M:%S"), "blast slot done", flush=True)
