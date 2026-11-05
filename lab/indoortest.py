"""Integration test "indoors": FPV drones against soldiers in buildings (5 Nov, review note 560 - Martin: "i notice drones hitting
top of buildings", "if there is no chance to hit target drone operator in reality would not do that", "sometimes are under roofs
with no walls ... like gas stations", "open windows or whole ... could try to hit them like that?").

The FPV AI Drones mod's own test cases on a headless dedicated server (D:\\work\\fpv-ai-reforger\\tools\\run_mp.py, Game Master
Arland, upper CPU cores at low priority, its own port): a soldier stood in a building room with a way in (an open door, window,
hole), in one with none, under a canopy (a fuel station's roof, a shed open at the sides), or a squad in the open; one drone
launched 150 m out each time. The run dict counts what happened:

    python lab/sublab.py run indoors --scenario rooms --variant default --repeat 2
    python lab/indoortest.py rooms default --units 2          # one run by hand

Watched in the game window (Martin), the game free - rooms, a closed room and a canopy, the mod's chase camera behind the drone:
    python lab/indoortest.py rooms default --watch
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

FPV = Path(r"D:\work\fpv-ai-reforger")

SCENARIOS = {
    "rooms": ("indoor", "a soldier in a building room with a way in at his height - an open door, a window, a hole"),
    "closed": ("indoorclosed", "a soldier in a closed room - no way in"),
    "canopy": ("canopy", "a soldier under a roof with open sides - a fuel station, a shed open at the sides"),
    "open": ("infantry", "three soldiers in the open (as before - nothing should change)"),
}

VARIANTS = {
    "default": ("", "the mod as it is now: a soldier under a roof only through a way in, slowly along one straight line"),
    "off": ("noshelter=1", "as before 5 Nov: the dive whatever is over him (-fpvaiNoShelter)"),
}

PASS = re.compile(r"FPVAI_TEST\|([^|]+)\|(PASS|FAIL)\|(.*)")
RESULT = re.compile(r"FPVAI_TEST\|indoors_result\|INFO\|case=([^ ]+(?: [^ =]+)*) walls=(\d+) dead=(\d) detonated=(\d) offset=([-0-9.]+) entries=(\d+)")
INFANTRY = re.compile(r"FPVAI_TEST\|infantry squad 120m\|(PASS|FAIL)\|killed (\d+)/(\d+)")
COST = re.compile(r"FPVAI: shelter in the last (\d+) s: (\d+) roof looks \((\d+) under a roof\), (\d+) way-in scans, (\d+) lines")
IMPACTED = re.compile(r"detonated on .* at ([0-9.]+)m \(drone impacted first\)")


def run(scenario: str, variant: str, minutes: float, units: int, port: int) -> dict:
    case, _ = SCENARIOS[scenario]
    setting, _ = VARIANTS[variant]
    n = max(1, int(units))
    port = port or 2192
    argv = [sys.executable, "-u", str(FPV / "tools" / "run_mp.py"), "--port", str(port), "--others", "--low",
            "--cases", ",".join([case] * n), "--timeout-minutes", str(int(max(minutes, 4)))]
    if setting:
        argv += ["--set", setting]
    t0 = time.time()
    p = subprocess.run(argv, cwd=str(FPV), capture_output=True, text=True, errors="replace")
    out = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout + p.stderr)
    # The test server keeps only its last log: each run's drone lines kept here (.runtime/sublab/indoors/logs).
    logs = Path(__file__).resolve().parents[1] / ".runtime" / "sublab" / "indoors" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{time.strftime('%Y%m%d-%H%M%S')}-{scenario}-{variant}.log"
    log.write_text(out, encoding="utf-8")
    r = summarize(out.splitlines(), scenario, n, round(time.time() - t0))
    r["log"] = str(log)
    return r


def summarize(lines, scenario: str, n: int, seconds: int = 0) -> dict:
    passed = failed = kills = soldiers = detonated = wasted = entries = stuck = 0
    roof_hits = 0
    lines_per_min = 0
    script_errors = 0
    for l in lines:
        if "SCRIPT    (E)" in l and "Failed move" not in l:
            script_errors += 1
        m = PASS.search(l)
        if m and m.group(1) != "SUMMARY":
            if m.group(2) == "PASS":
                passed += 1
            else:
                failed += 1
            if "NEVER LEFT ITS LAUNCH SPOT" in m.group(3):
                stuck += 1
        m = RESULT.search(l)
        if m:
            soldiers += 1
            dead, det, ent = int(m.group(3)), int(m.group(4)), int(m.group(6))
            kills += dead
            detonated += det
            entries += ent
            if det and not dead:
                wasted += 1
        m = INFANTRY.search(l)
        if m:
            kills += int(m.group(2))
            soldiers += int(m.group(3))
        m = IMPACTED.search(l)
        if m and float(m.group(1)) > 2.5:
            roof_hits += 1
        m = COST.search(l)
        if m:
            lines_per_min = max(lines_per_min, round(int(m.group(5)) * 60 / max(int(m.group(1)), 1)))
    cases = passed + failed
    return {
        "cases": cases, "passed": passed, "pass_pct": round(100 * passed / cases) if cases else 0,
        "kills": kills, "soldiers": soldiers, "detonated": detonated,
        "wasted": wasted,                 # went off and killed nobody
        "roof_hits": roof_hits,           # went off on something more than 2.5 m short of him (a roof, a wall)
        "entries": entries,               # runs in through a way in
        "stuck": stuck,                   # stand-in launches that never left the ground
        "lines_per_min": lines_per_min,   # what the shelter checks cost: traces a minute (the busiest minute)
        "script_errors": script_errors, "crashed": cases == 0, "seconds": seconds, "scenario": scenario, "repeats": n,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("variant", choices=sorted(VARIANTS))
    ap.add_argument("--units", type=int, default=1, help="cases in the run (each a new spot)")
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--port", type=int, default=2192)
    ap.add_argument("--watch", action="store_true", help="in the game window for Martin (the mod's chase camera behind the drone): "
                    "rooms, a closed room and a canopy - the scenario and variant are ignored; only with the game free")
    a = ap.parse_args()
    if a.watch:
        cases = "indoor,indoorclosed,canopy,indoor,canopy"
        sys.exit(subprocess.run([sys.executable, str(FPV / "tools" / "run_tests.py"), "--window", "--cases", cases], cwd=str(FPV)).returncode)
    print(json.dumps(run(a.scenario, a.variant, a.minutes, a.units, a.port), indent=1))
