"""Tonight's extra slot for the collision forecast (v2, this separate copy): the head-on and Everon exit tracks, our v1
rules and v2, three 10-minute runs each, one at a time on port 2152, rows into the main repo's driving sub-lab."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drivetest  # noqa: E402  (this copy's runner and scripts)
sys.path.insert(0, r"D:\work\reforger-commander\lab")
import importlib.util
spec = importlib.util.spec_from_file_location("main_sublab", r"D:\work\reforger-commander\lab\sublab.py")
main_sublab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_sublab)

for rep in range(3):
    for track in ("headon", "everonexit"):
        for variant in ("risk", "default"):
            r = drivetest.run(track, variant, 10, 8 if track == "headon" else 6, 2152)
            r["rep"] = rep
            r["copy"] = "risk-v2"
            if variant == "default":
                r["variant"] = "default"
            row = main_sublab.record("driving", r)
            print(track, variant, rep, {k: row.get(k) for k in ("legs", "lost", "car_hits", "jams", "risk_caps", "score")}, flush=True)
