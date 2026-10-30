"""The van sub-lab (29 Oct night, Martin: "can you do integration sublab test for van bug?"; "it can be just van bug that
doesn't happen in other vehicles, can you verify?"; "i remember something like that from multiplayer with people that I
couldn't get off and was stuck"; review notes 455, 456).

The question: do soldiers fail to get into - or out of - the UAZ-452 van more than other vehicles? Two watched Farm runs
with the seat fallback off: 1 of 23 Soviet rides from the harbour HQ delivered; the boarding timeouts show 3 of 4 aboard
and the 4th standing at the van's door, his get-in running 77 s without the game's animation ever finishing.

The scenario: ZCR_BoardTest (-zcrBoardTest, the crash sub-lab's boarding test) on the empty Arland test map, the airport
apron (flat - no tilt; cars there never crashed): 8 vehicles of ONE type on pads 16 m apart, a team beside each; every
soldier ordered into a seat the way AI Conflict does it (the seat reserved, the game's SCR_AIGetInVehicle - no forced
seat), then out the way AI Conflict drops a team, again and again ("board" mode: the same vehicles). No mods: the game's
own vehicles and soldiers. Per run, over all cycles:

    ordered      soldiers given a seat (only the seats a vehicle has - a rifle squad overfills a jeep)
    aboard_pct   of those, in their seat within 45 s
    in_fail      ordered but not in at the end of the 45 s
    stuck_in     still inside 30 s after the get-out order (Martin's "couldn't get off")
    engine_stuck the game's own "Stuck trying to get into vehicle" warnings

    python lab/vantest.py apron --variant van_ussr --minutes 6
    python lab/sublab.py run vans --scenario apron --variant van_ussr --repeat 2
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent

SCENARIOS = {
    "apron": ("1000,2780", "the Arland airport apron - flat, open ground"),
}
VARIANTS = {
    "van_ussr": ("van_ussr", "UAZ-452 van, Soviet rifle squads (the harbour HQ's rides)"),
    "van_us": ("van_us", "UAZ-452 van, US rifle squads - the van or the soldiers?"),
    "m998_us": ("m998_us", "M998 Humvee (covered), US rifle squads (the south HQ's rides)"),
    "m998_ussr": ("m998_ussr", "M998 Humvee, Soviet rifle squads"),
    "m923_us": ("m923_us", "M923 truck, US rifle squads"),
    "van2_ussr": ("van2_ussr", "UAZ-452 van, Soviet two-man teams (as in the watched matches)"),
    "m998_2_us": ("m998_2_us", "M998 Humvee, US two-man teams (as in the watched matches)"),
    "ural_ussr": ("ural_ussr", "Ural-4320 truck, Soviet rifle squads - the Soviet side's ride if the van is the bug"),
    "uaz469_ussr": ("uaz469_ussr", "UAZ-469 jeep (no gun), Soviet rifle squads"),
}
EVENT = re.compile(r"\[ZCR\]\[BOARDTEST\] t=(\d+) cycle=(\d+) event=(\w+) soldiers=(\d+) n=(\d+)")


def run(scenario: str, variant: str, minutes: float, units: int, port: int) -> dict:
    spot = SCENARIOS[scenario][0]
    kinds = VARIANTS[variant][0]
    label = f"vantest-{scenario}-{variant}-p{port}"
    argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", "arland-test", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--mods", "", "--extra", f"-zcrBoardTest {spot};8;board;{kinds}"]
    subprocess.run(argv, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


def summarize(run_dir: Path, scenario: str = "", variant: str = "") -> dict:
    out = {"scenario": scenario, "variant": variant, "run": run_dir.name}
    logs = sorted(run_dir.glob("logs/*/console.log"))
    if not logs:
        out["error"] = "no log"
        return out
    text = logs[-1].read_text(encoding="utf-8", errors="replace")
    cycles = {}
    for t, cycle, ev, soldiers, n in EVENT.findall(text):
        c = cycles.setdefault(int(cycle), {})
        c[ev] = int(n)
        c["soldiers"] = int(soldiers)
    # ABOARD counts everyone in a seat - with those still inside from the cycle before (its OUT n, never ordered again):
    # the ones who got in this cycle are ABOARD minus those.
    inside = 0
    for k in sorted(cycles):
        c = cycles[k]
        c["new"] = max(0, c.get("ABOARD", 0) - inside)
        inside = c.get("OUT", 0)
    done = [c for c in cycles.values() if "BOARD" in c and "ABOARD" in c]
    ordered = sum(c["BOARD"] for c in done)
    aboard = sum(min(c["new"], c["BOARD"]) for c in done)
    outs = [c for c in done if "OUT" in c]
    out.update({
        "cycles": len(done),
        "ordered": ordered,
        "aboard": aboard,
        "aboard_pct": round(100 * aboard / ordered, 1) if ordered else None,
        "in_fail": ordered - aboard,
        "cycles_short": sum(1 for c in done if c["ABOARD"] < c["BOARD"]),
        "stuck_in": sum(c["OUT"] for c in outs),
        "out_cycles": len(outs),
        "engine_stuck": len(re.findall(r"Stuck trying to get into vehicle", text)),
        "script_errors": len(re.findall(r"SCRIPT\s+\(E\)", text)),
        "crashed": bool(list(logs[-1].parent.glob("*.mdmp"))),
        "minutes": round(max([int(x) for x in re.findall(r"\[ZCR\]\[BOARDTEST[_A-Z]*\] t=(\d+)", text)] or [0]) / 60, 1),
    })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="van_ussr", choices=list(VARIANTS))
    ap.add_argument("--minutes", type=float, default=6)
    ap.add_argument("--port", type=int, default=2178)
    ap.add_argument("--summarize", default="", help="summarize an existing run folder instead of running")
    a = ap.parse_args()
    r = summarize(Path(a.summarize), a.scenario, a.variant) if a.summarize else run(a.scenario, a.variant, a.minutes, 0, a.port)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
