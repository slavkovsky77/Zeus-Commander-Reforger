"""The assault sub-lab (28 Oct, Martin: "why teams were not set off, can we analyse ... maybe some sublabs for the tests?";
review note 433). A full Arland match with the watched matches' setup, but one side attacks one base with everything from the
first minute (lab/assault.py's 'assault' general) and the other holds it ('hold') - do the ordered attack teams get there?
The runner of the sub-lab "assault" (lab/sublabs/assault.toml):

    python lab/assaulttest.py ussr --variant now --minutes 10
    python lab/sublab.py run assault --scenario ussr --variant team4 --repeat 2

Measures (the attacker): soldiers within 300 m of the objective at game minute 3, 5 and 8 and as a share of its attack
teams' soldiers then; the first arrival; where its attack orders really sent the teams (AI Conflict's own order lines - our
live line shows only each team's assigned target, which misled us on 28 Oct); lone survivors sent home; failed rides;
the capture; losses on both sides.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The watched matches' setup on 28 Oct (.runtime/watch_extra.txt, watch_mods.txt; armour mods off), frozen so a later
# change to the watched setup doesn't move the sub-lab's baseline.
BASE = ("-zcrNoFIA -zcrArmourVanilla -zcrMoveTurrets -aicfNoHiddenSeat -zcrNoCoverLayer -zcrDangerDronesOnly "
        "-aicfMaxAgentsPerFaction 50 -aicfCapCountsAll -aicfInfantryDeploySize 2 -aicfMusterSize 2 "
        "-aicfMaxBuildersPerFaction 6 -aicfVehicleMinimumRequestAgents 2 -zcrProjSweep")
MODS = "3B9F2C4D5E6A7B81,68FCF11534562F2E,5EDAAE0D3CC60D6B"
SCENARIOS = {
    # name: the attacking side - the other holds. Arland's HQs swap between matches; both generals pick the enemy base
    # nearest the attacker's HQ (on 28 Oct: Military Training Area when the USSR attacks, Farm when the US does).
    "ussr": "USSR",   # the Soviets attack (28 Oct: nobody reached Military Training Area in two 5-minute assaults)
    "us": "US",       # the US attacks
    "point": "BOTH",  # one neutral point (Signal Hill), both sides go for it; nothing else on any list (-zcrOnePoint)
}

POINT = "Signal_Hill"   # the one-point scenario's point: 1628 m from the Soviet HQ, 1688 m from the US one

SCENARIO_WORDS = {
    "ussr": "The Soviets attack the US base nearest their HQ with everything from the first minute; the US holds it",
    "us": "The US attacks the Soviet base nearest its HQ with everything from the first minute; the Soviets hold it",
    "point": "One neutral point in the middle (Signal Hill, 1.6-1.7 km from both HQs) and the two main bases - both sides go for the point with everything; no other base is on any list",
}


def _sized(n: int) -> str:
    return BASE.replace("-aicfInfantryDeploySize 2 -aicfMusterSize 2", f"-aicfInfantryDeploySize {n} -aicfMusterSize {n}")


VARIANTS = {
    # name: (extra command line, words for the app)
    "now": (BASE, "as the watched matches: 2-man teams, rides, AI Conflict picks each team's target"),
    "team3": (_sized(3), "teams set out with 3 men (AI Conflict's default), not 2"),
    "team4": (_sized(4), "teams set out with 4 men"),
    "bind": (BASE + " -zcrBindMainEffort", "attack teams go only for the main effort, avoided bases are avoided (-zcrBindMainEffort)"),
    "foot": (BASE + " -aicfInfantryRideMeters 100000", "no rides: every team walks"),
    "team4-bind": (_sized(4) + " -zcrBindMainEffort", "4-man teams that go only for the main effort"),
    "stage50": (BASE + " -zcrBindMainEffort -aicfVehicleSpawnStagingRadiusMeters 50",
                "binds, and a team counts as at its vehicle spot within 50 m, not 25 (spots at the harbour's waterline)"),
}
RIDE_FAIL = ("BOARDING_PHASE_DEADLINE_EXCEEDED", "BOARDING_PROGRESS_GRACE_DEADLINE_EXCEEDED", "DRIVER_RECOVERY_EXHAUSTED",
             "VEHICLE_STUCK_PERSISTENT", "MOB_EGRESS_SOFT_NUDGE", "MOB_EGRESS_HIDDEN_RECOVERY", "VEHICLE_FALLBACK_LONE_SURVIVOR")
NEAR_M = 300


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False, speed: float = 1) -> dict:
    attacker = SCENARIOS[scenario]
    extra, _ = VARIANTS[variant]
    us, ussr = ("assault", "hold") if attacker == "US" else ("hold", "assault")
    if attacker == "BOTH":
        us = ussr = "point"
        extra += f" -zcrOnePoint {POINT}"
    sys.path.insert(0, str(ROOT / "lab"))
    import bridges
    import sublab
    bridges.ensure(("point",) if attacker == "BOTH" else ("assault", "hold"))
    title = sublab.title("assault", scenario, variant)
    label = f"assault-{scenario}-{variant}-p{port}" if not watch else f"assaulttest-{scenario}-{variant}-watch"   # lab/watch_test.py finds the game by it
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", us, "--ussr", ussr, "--drones", "--mods", MODS, "--plan-seconds", "60",
            "--extra", f"{extra} -zcrTestTitle {title}"]
    if watch:
        # The game window, at 1x by default (Martin watches at 1x - 28 Oct: 'it jumps because of speed'); always passed, the
        # game keeps its multiplier between runs. The test still lasts 'minutes' game minutes.
        argv += ["--solo", "--watch"]
        argv[argv.index("--extra") + 1] += f" -zcrSpeed {speed:g}"
        argv[argv.index("--minutes") + 1] = str(round(minutes / speed, 2))
    subprocess.run(argv, cwd=str(ROOT), stdout=None if watch else subprocess.DEVNULL, stderr=None if watch else subprocess.DEVNULL,
                   creationflags=0 if watch else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


def summarize(run_dir: Path, scenario: str, variant: str, objective: tuple | None = None, attacker: str = "") -> dict:
    """objective: (base id, name) for a run without the assault generals (e.g. a watched match, to compare). The point
    scenario: both sides' numbers (us_..., ussr_...), who took the point and when."""
    attacker = attacker or SCENARIOS[scenario]
    if attacker == "BOTH":
        out = {"scenario": scenario, "variant": variant, "run": run_dir.name, "run_path": str(run_dir)}
        sides = {s: summarize(run_dir, scenario, variant, objective, s) for s in ("US", "USSR")}
        out["objective"] = sides["USSR"].get("objective", "?")
        for k in ("at_obj_3", "at_obj_5", "at_obj_5_pct", "at_obj_8", "first_arrival_s", "to_obj_pct", "lone_survivors", "ride_fails",
                  "captured", "capture_s"):
            for s in ("US", "USSR"):
                out[f"{s.lower()}_{k}"] = sides[s].get(k)
        out["at_obj_5"] = (sides["US"].get("at_obj_5") or 0) + (sides["USSR"].get("at_obj_5") or 0)
        out["ride_fails"] = (sides["US"].get("ride_fails") or 0) + (sides["USSR"].get("ride_fails") or 0)
        out["us_lost"], out["ussr_lost"] = sides["USSR"].get("def_lost"), sides["USSR"].get("att_lost")
        for k in ("minutes", "script_errors", "crashed"):
            out[k] = sides["USSR"].get(k)
        return out
    defender = "US" if attacker == "USSR" else "USSR"
    out = {"scenario": scenario, "variant": variant, "run": run_dir.name, "run_path": str(run_dir)}
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        out["error"] = "no log"
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # The objective: the attacker's plan names it; its place from the strategist's snapshot (base ids = graph nodes).
    obj_id, obj_name = objective if objective else (None, "")
    for l in lines if not objective else []:
        if "[ZCR][PLAN]" in l and f"faction={attacker} " in l:
            m = re.search(r"Assault test: everything at (.+?) \(base (\d+)\)", l)
            if m:
                obj_name, obj_id = m.group(1), int(m.group(2))
                break
    obj = None
    snap = run_dir / "profile" / "zcr" / "snapshots.jsonl"
    if snap.exists() and obj_id is not None:
        for s in snap.read_text(encoding="utf-8", errors="replace").splitlines()[:4]:
            try:
                obj = next((b for b in json.loads(s).get("bases", []) if b.get("id") == obj_id), None) or obj
            except ValueError:
                continue
    callsign = None
    for l in lines:
        m = re.search(r"\[GRAPH_NODE\] node=(\d+) .*callsign=(\d+)", l)
        if m and obj_id is not None and int(m.group(1)) == obj_id:
            callsign = m.group(2)
    out["objective"] = obj_name or "?"
    # Where the attacker's soldiers are: [ZCR][LIVE] team lines, one round every few seconds.
    rounds = {}
    for l in lines:
        if "[ZCR][LIVE]" not in l or f"kind=team side={attacker} " not in l:
            continue
        m = re.search(r" t=(\d+) kind=team side=\w+ id=(\d+) role=(\w+) men=(\d+) ride=\d x=(-?\d+) z=(-?\d+)", l)
        if m:
            rounds.setdefault(int(m.group(1)), []).append((m.group(3), int(m.group(4)), float(m.group(5)), float(m.group(6))))
    first = None
    if obj:
        for t in sorted(rounds):
            if any(math.hypot(x - obj["x"], z - obj["z"]) <= NEAR_M for _, _, x, z in rounds[t]):
                first = t
                break

    def at(minute):
        if not rounds or not obj:
            return 0, 0
        t = min(rounds, key=lambda k: abs(k - minute * 60))
        if abs(t - minute * 60) > 30:
            return 0, 0
        near = sum(men for _, men, x, z in rounds[t] if math.hypot(x - obj["x"], z - obj["z"]) <= NEAR_M)
        attack = sum(men for role, men, _, _ in rounds[t] if role == "ATTACK")
        return near, attack

    for mnt in (3, 5, 8):
        near, attack = at(mnt)
        out[f"at_obj_{mnt}"] = near
        out[f"at_obj_{mnt}_pct"] = round(100 * near / attack) if attack else 0
    out["first_arrival_s"] = first if first is not None else -1
    # AI Conflict's attack orders for the attacker (the re-issued copies left out).
    orders = [re.search(r"slot=(\d+) .*role=ATTACK posture=(\w+) (?:old_target=\d+ new_)?target=(\d+) reason=(\w+)", l)
              for l in lines if ("ORDER_ASSIGNED" in l or "TARGET_REASSIGNED" in l) and f"faction={attacker} " in l and "role=ATTACK" in l]
    orders = [m for m in orders if m and m.group(4) != "ORDER_RECOVERY"]
    real = [m for m in orders if m.group(2) != "LONE_SURVIVOR_RETREAT"]
    out["orders"] = len(real)
    out["to_obj_pct"] = round(100 * sum(1 for m in real if m.group(3) == callsign) / len(real)) if real and callsign else 0
    out["lone_survivors"] = sum(1 for m in orders if m.group(2) == "LONE_SURVIVOR_RETREAT")
    # Failed rides: orders AI Conflict re-issued because a ride didn't work out (any of the attacker's teams).
    out["ride_fails"] = sum(1 for l in lines if ("ORDER_ASSIGNED" in l or "TARGET_REASSIGNED" in l) and f"faction={attacker} " in l
                            and re.search(r"reason=(" + "|".join(RIDE_FAIL) + r") ", l))
    cap = [l for l in lines if "[ZCR][CAPTURE]" in l and obj_name and f"base={obj_name} " in l and re.search(r"to=" + attacker + r"(\s|$)", l)]
    out["captured"] = int(bool(cap))
    m = re.search(r" t=(\d+)", cap[0]) if cap else None
    out["capture_s"] = int(m.group(1)) if m else -1
    losses = {s: sum(1 for l in lines if "[ZCR][LOSS]" in l and f" side={s} " in l and "kind=man" in l) for s in (attacker, defender)}
    out["att_lost"], out["def_lost"] = losses[attacker], losses[defender]
    last_t = max(rounds) if rounds else 0
    out["minutes"] = round(last_t / 60, 1)
    out["script_errors"] = len([l for l in lines if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l])
    out["crashed"] = bool(list(log.parent.glob("*.mdmp")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="now", choices=list(VARIANTS))
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--port", type=int, default=2160)
    ap.add_argument("--watch", action="store_true", help="in the game window (solo) - only when nobody else uses the game")
    ap.add_argument("--speed", type=float, default=1, help="with --watch: the game's time multiplier (default 1x)")
    ap.add_argument("--summarize", default="", help="summarize an existing run folder instead of running")
    a = ap.parse_args()
    if a.summarize:
        r = summarize(Path(a.summarize), a.scenario, a.variant)
    else:
        r = run(a.scenario, a.variant, a.minutes, 0, a.port, a.watch, a.speed)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
