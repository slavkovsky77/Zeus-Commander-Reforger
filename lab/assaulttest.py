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
    "city": "BOTH",   # one base, Farm (29 Oct, Martin: "make it in a way there can be fight somewhere, so maybe farm")
}

# The one-point scenarios' point: Signal Hill 1628 m from one HQ, 1688 m from the other; Farm 1115 m from the
# north-western (harbour) HQ and 2090 m from the southern one - the harbour side holds it first, the other storms it.
# Both sides may attack the point whatever their radio network reaches (fork 1a910e8, ZCR_OnePoint). Tried once each
# on 29 Oct: Arleville (every base dealt, out of one side's radio reach) and Beauregard (every base left neutral).
POINTS = {"point": "Signal_Hill", "city": "Farm"}
POINT = POINTS["point"]

SCENARIO_WORDS = {
    "ussr": "The Soviets attack the US base nearest their HQ with everything from the first minute; the US holds it",
    "us": "The US attacks the Soviet base nearest its HQ with everything from the first minute; the Soviets hold it",
    "point": "One neutral point in the middle (Signal Hill, 1.6-1.7 km from both HQs) and the two main bases - both sides go for the point with everything; no other base is on any list",
    "city": "One base, Farm (1.1 km from the harbour HQ, 2.1 km from the southern one) - the other bases dealt to the sides but off every list; both sides storm Farm",
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
    "squads12": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort",
                 "12 teams of 4 a side instead of 20 of 2 (the same ~48 soldiers, half the vehicles), binds"),
    "squads12-seat": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort").replace(" -aicfNoHiddenSeat", ""),
                      "12 teams of 4, binds, and AI Conflict seats a passenger whose get-in never starts (its fallback, off since 22 Oct)"),
    "squads12-foot": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfInfantryRideMeters 100000",
                      "12 teams of 4, binds, no rides: every team walks (the reference for what the rides are worth)"),
    "stage50": (BASE + " -zcrBindMainEffort -aicfVehicleSpawnStagingRadiusMeters 50",
                "binds, and a team counts as at its vehicle spot within 50 m, not 25 (spots at the harbour's waterline)"),
    "squads12-queue": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 2").replace(" -aicfNoHiddenSeat", ""),
                       "12 teams of 4, binds, seat fallback on, and at most 2 rides leaving a base at a time - the next team walks"),
    "storm-mounted": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3").replace(" -aicfNoHiddenSeat", ""),
                      "the storm rides in (Martin, 29 Oct: 'storms should be done by vehicles'): 12 teams of 4, binds, seat fallback "
                      "on, rides for every march over 300 m, at most 3 leaving a base at a time (the jam inside the HQ, note 444)"),
    # 29 Oct night (Martin, note 449: "attacks should be planned in some smarter way, we have to read the maps"): the attack
    # plan read from the map (lab/attackplan.py -> .runtime/attack/seed_<point>_<pick>/zcr/attackplan.txt, see SEEDS).
    "storm-plan": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold").replace(" -aicfNoHiddenSeat", ""),
                   "as storm-mounted, and the attack plan read from the map that the model picked: the rides to its assembly point "
                   "hidden from the objective, the teams in along its cover-to-cover lanes"),
    "storm-plan-hold": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan").replace(" -aicfNoHiddenSeat", ""),
                        "as storm-plan, and the hold line: teams wait ~150 m out until 3 are there (or 90 s), then all go in together"),
    "storm-plan-light": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold -aicfApcEvery 0").replace(" -aicfNoHiddenSeat", ""),
                         "as storm-plan, rides in light vehicles only (no APC rides: the BTR-70s jammed the harbour HQ, 29 Oct night)"),
    "storm-plan-light-hold": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfApcEvery 0").replace(" -aicfNoHiddenSeat", ""),
                              "the plan, light rides and the hold line together"),
    "storm-plan-light-hold-noarm": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfApcEvery 0 -zcrNoArmour").replace(" -aicfNoHiddenSeat", ""),
                                    "the plan, light rides, the hold line - and no armour units (29 Oct night: bought at the HQ they stood on its exit road while the rides left)"),
    "storm-plan-light-hold-algo": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfApcEvery 0").replace(" -aicfNoHiddenSeat", ""),
                                   "as storm-plan-light-hold, with the plan the algorithm scored best instead of the model's pick"),
    "storm-plan-trans-hold": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                              "the plan and the hold line, transport rides only (29 Oct night: armed and armoured rides delivered 1 of 39, trucks and vans 31 of 52)"),
    "storm-trans": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                    "the control for the plan runs: today's way with transport rides only and the armour off the HQ exit - no plan"),
    "storm-plan-trans-hold-algo": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                                   "as storm-plan-trans-hold, with the plan the algorithm scored best instead of the model's pick"),
    "storm-plan-trans": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                         "the plan without the hold line, transport rides only - the lanes and the assembly point alone"),
    "storm-plan-close": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                         "the plan with its assembly point 200-400 m out (300-650 before; the covered dismount drops 180-300 m out) and no hold line, transport rides"),
    "storm-plan-algo": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold").replace(" -aicfNoHiddenSeat", ""),
                        "as storm-plan, with the plan the algorithm itself scored best"),
    # 29 Oct evening (Martin's go, note 451): the seat fallback stays off, as in the watched matches - both of the night's
    # crashes came after forced seats.
    "storm-safe": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -aicfArmedRideEvery 0",
                   "no plan, transport rides, the seat fallback off (the watched matches' setting) - the control"),
    # The normal matches' setup (2-man teams, every base dealt) with the plans for every base (lab/attackplan.py --all):
    "now-trans": (BASE + " -aicfArmedRideEvery 0", "as the watched matches since 29 Oct evening: transport rides only - the control"),
    "now-plan": (BASE + " -aicfArmedRideEvery 0 -zcrAttackPlan -zcrNoAttackHold",
                 "as now-trans, with attack plans from the map for every base from every base (the origin nearest where a team started)"),
    # 30 Oct 03:15 the van fix (fork: the UAZ-452 counts its 2 front seats - its back is broken for the AI, the van sub-lab):
    "storm-safe-van8": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -aicfArmedRideEvery 0 -aicfVanSeats 8",
                        "storm-safe with the old van (8 seats: Soviet teams of 4 ride the UAZ-452 and its broken back) - the van fix's control"),
    "storm-plan-measured": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0",
                            "per HQ the approach that did best in the measured runs, or no plan where none beat it (lab/attackscore.py); transport rides, the seat fallback off"),
    # 31 Oct night (the transport test, note 480): the 3-rides-per-base cap cost the most there - no cap moved +8% (north HQ)
    # to +50% (south HQ) more soldiers, no jam at the HQ. Does the Farm battle jam at the HQ without it (the 29 Oct reason)?
    "storm-plan-measured-cap0": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 0 -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0",
                                 "as storm-plan-measured, with no cap on rides leaving a base"),
}
SEEDS = {"storm-plan": "model", "storm-plan-hold": "model", "storm-plan-light": "model", "storm-plan-light-hold": "model", "storm-plan-light-hold-noarm": "model", "storm-plan-light-hold-algo": "algorithm", "storm-plan-trans-hold": "model", "storm-plan-trans": "model", "storm-plan-close": "close_model", "storm-plan-trans-hold-algo": "algorithm", "storm-plan-algo": "algorithm", "storm-plan-measured": "measured", "storm-plan-measured-cap0": "measured", "now-plan": "@arland_all"}   # variant -> which plan pick (lab/attackplan.py --export)
RIDE_FAIL = ("BOARDING_PHASE_DEADLINE_EXCEEDED", "BOARDING_PROGRESS_GRACE_DEADLINE_EXCEEDED", "DRIVER_RECOVERY_EXHAUSTED",
             "VEHICLE_STUCK_PERSISTENT", "MOB_EGRESS_SOFT_NUDGE", "MOB_EGRESS_HIDDEN_RECOVERY", "VEHICLE_FALLBACK_LONE_SURVIVOR")
NEAR_M = 300


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False, speed: float = 1,
        cam_spot: str = "") -> dict:
    attacker = SCENARIOS[scenario]
    extra, _ = VARIANTS[variant]
    if cam_spot:
        extra += f" -zcrCamSpot {cam_spot}"
    us, ussr = ("assault", "hold") if attacker == "US" else ("hold", "assault")
    if attacker == "BOTH":
        us = ussr = "point"
        extra += f" -zcrOnePoint {POINTS[scenario]}"
    sys.path.insert(0, str(ROOT / "lab"))
    import bridges
    import sublab
    bridges.ensure(("point",) if attacker == "BOTH" else ("assault", "hold"))
    title = sublab.title("assault", scenario, variant)
    label = f"assault-{scenario}-{variant}-p{port}" if not watch else f"assaulttest-{scenario}-{variant}-watch"   # lab/watch_test.py finds the game by it
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", us, "--ussr", ussr, "--drones", "--mods", MODS, "--plan-seconds", "60",
            "--extra", f"{extra} -zcrTestTitle {title}"]
    if variant in SEEDS:
        seed = ROOT / ".runtime" / "attack" / f"seed_{POINTS.get(scenario, scenario).lower()}_{SEEDS[variant]}"
        if SEEDS[variant].startswith("@"):   # a whole map's plans (lab/attackplan.py --all)
            seed = ROOT / ".runtime" / "attack" / f"seed_{SEEDS[variant][1:]}"
        if not (seed / "zcr" / "attackplan.txt").exists():
            raise SystemExit(f"no plan file {seed / 'zcr' / 'attackplan.txt'} - run lab/attackplan.py --export first")
        argv += ["--seed-profile", str(seed)]
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


def rides(lines: list, side: str, rounds: dict) -> dict:
    """AI Conflict's rides for one side, from its trip state changes (29 Oct, note 444): asked (a vehicle spot planned),
    delivered (the team dismounted), failed (fell back to walking), failed at the HQ (the team's last place within 150 m
    of where the side's teams stood in the first round), and the most rides boarding or driving at the same moment."""
    first = rounds[min(rounds)] if rounds else []
    hq = (sorted(x for _, _, x, _ in first)[len(first) // 2], sorted(z for _, _, _, z in first)[len(first) // 2]) if first else None
    where = {}      # numeric slot -> [(t, x, z)]
    for l in lines:
        if "[ZCR][LIVE]" in l and f"kind=team side={side} " in l:
            m = re.search(r" t=(\d+) kind=team side=\w+ id=(\d+) .* x=(-?\d+) z=(-?\d+)", l)
            if m:
                where.setdefault(int(m.group(2)), []).append((int(m.group(1)), float(m.group(3)), float(m.group(4))))
    state, out, peak = {}, {"rides_asked": 0, "rides_delivered": 0, "rides_failed": 0, "rides_failed_at_hq": 0, "rides_slow_out": 0}, 0
    for l in lines:
        if "[VEHICLE_STATE_CHANGED]" not in l or f"faction={side} " not in l:
            continue
        st, pv = re.search(r" state=(\w+)", l), re.search(r"previous_state=(\w+)", l)
        slot, t = re.search(r"numeric_slot=(\d+)", l), re.search(r"t_ms=(\d+)", l)
        if not st or not slot or not t:
            continue
        st, slot, t = st.group(1), int(slot.group(1)), int(t.group(1)) // 1000
        if st == "SITE_PLANNED" and pv and pv.group(1) == "WAITING_FOR_SITE":
            out["rides_asked"] += 1
        elif st == "DISMOUNT":
            out["rides_delivered"] += 1
        elif st == "FALLBACK" and state.get(slot) == "DISMOUNT":
            # Delivered, then a slow get-out (DISEMBARK_TIMEOUT ~20 s after the drop, 30 Oct 23:35): not a failed ride.
            out["rides_slow_out"] += 1
        elif st == "FALLBACK":
            out["rides_failed"] += 1
            seen = [p for p in where.get(slot, []) if p[0] <= t]
            if hq and seen and math.hypot(seen[-1][1] - hq[0], seen[-1][2] - hq[1]) <= 150:
                out["rides_failed_at_hq"] += 1
        state[slot] = st
        peak = max(peak, sum(1 for v in state.values() if v in ("SPAWN_COMMIT", "BOARDING", "TRANSIT")))
    out["rides_peak"] = peak
    return out


def summarize(run_dir: Path, scenario: str, variant: str, objective: tuple | None = None, attacker: str = "") -> dict:
    """objective: (base id, name) for a run without the assault generals (e.g. a watched match, to compare). The point
    scenario: both sides' numbers (us_..., ussr_...), who took the point and when."""
    attacker = attacker or SCENARIOS[scenario]
    if attacker == "BOTH":
        out = {"scenario": scenario, "variant": variant, "run": run_dir.name, "run_path": str(run_dir)}
        sides = {s: summarize(run_dir, scenario, variant, objective, s) for s in ("US", "USSR")}
        out["objective"] = sides["USSR"].get("objective", "?")
        for k in ("at_obj_3", "at_obj_5", "at_obj_5_pct", "at_obj_8", "at_obj_12", "at_obj_15", "first_arrival_s", "to_obj_pct", "lone_survivors", "ride_fails",
                  "captured", "capture_s", "hq_m", "teams_in", "third_in_s", "first_to_third_s", "plan_dismounts", "holds", "hold_go_s", "rides_asked", "rides_delivered", "rides_failed", "rides_failed_at_hq", "rides_slow_out", "rides_peak"):
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
    # Do the attack teams arrive together (29 Oct night, the attack plan's hold line)? When each first got within 150 m of
    # the objective; the third one's time, and the gap from the first to the third.
    arrived = {}
    for l in lines:
        if not obj or "[ZCR][LIVE]" not in l or f"kind=team side={attacker} " not in l or "role=ATTACK" not in l:
            continue
        m = re.search(r" t=(\d+) kind=team side=\w+ id=(\d+) role=\w+ men=(\d+) ride=\d x=(-?\d+) z=(-?\d+)", l)
        if m and int(m.group(3)) > 0 and int(m.group(2)) not in arrived and math.hypot(float(m.group(4)) - obj["x"], float(m.group(5)) - obj["z"]) <= 150:
            arrived[int(m.group(2))] = int(m.group(1))
    times = sorted(arrived.values())
    out["teams_in"] = len(times)
    out["third_in_s"] = times[2] if len(times) >= 3 else -1
    out["first_to_third_s"] = times[2] - times[0] if len(times) >= 3 else -1
    # The attack plan in the game: rides dropped at its assembly point, the hold line's go.
    out["plan_dismounts"] = sum(1 for l in lines if "[ZCR][DISMOUNT]" in l and f"faction={attacker} " in l and " assembly" in l)
    go = next((l for l in lines if "[ZCR][HOLD]" in l and f"side={attacker} " in l and "event=go" in l), None)
    out["hold_go_s"] = int(re.search(r" t=(\d+)", go).group(1)) if go else -1
    out["holds"] = sum(1 for l in lines if "[ZCR][HOLD]" in l and f"side={attacker} " in l and "event=hold" in l)

    def at(minute):
        if not rounds or not obj:
            return 0, 0
        t = min(rounds, key=lambda k: abs(k - minute * 60))
        if abs(t - minute * 60) > 30:
            return 0, 0
        near = sum(men for _, men, x, z in rounds[t] if math.hypot(x - obj["x"], z - obj["z"]) <= NEAR_M)
        attack = sum(men for role, men, _, _ in rounds[t] if role == "ATTACK")
        return near, attack

    # How far the side's HQ is from the objective (Arland's HQs swap between matches): where its teams stood in the first round.
    if rounds and obj:
        first_round = rounds[min(rounds)]
        hx = sorted(x for _, _, x, _ in first_round)[len(first_round) // 2]
        hz = sorted(z for _, _, _, z in first_round)[len(first_round) // 2]
        out["hq_m"] = round(math.hypot(hx - obj["x"], hz - obj["z"]))
    for mnt in (3, 5, 8, 12, 15):
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
    out.update(rides(lines, attacker, rounds))
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
    ap.add_argument("--cam-spot", default="", help="with --watch: x,z,from_s,to_s - the camera follows the ride nearest that spot "
                    "between those game seconds (-zcrCamSpot, 31 Oct: the airfield edge west of Farm)")
    a = ap.parse_args()
    if a.summarize:
        r = summarize(Path(a.summarize), a.scenario, a.variant)
    else:
        r = run(a.scenario, a.variant, a.minutes, 0, a.port, a.watch, a.speed, a.cam_spot)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
