"""The transport integration test (31 Oct, Martin: "prepare transport sublab, this sublab will just do moving of manpower as
efficiently as possible (no enemy on the map)", "points is now to optimize manpower reinforcement supplies, catch problems
... i noticed soldier are not being transported properly", "we should measure how efficiently we are transporting soldiers
over the map"; review notes 471, 474).

A full Arland match where the US holds the whole map (-zcrAllBasesTo US: every base but the Soviet HQ) and nobody fights
(-aicfNoForces USSR: the Soviets field no teams; no FIA, no drones). Each of the 12 US teams of 4 is sent to one of its bases
and on arrival to the next (-zcrShuttleTest, ZCR_ShuttleTest.c) - the teams cross the map again and again the way AI Conflict
moves them (a ride or on foot), while AI Conflict's supply trucks serve the same bases.

    python lab/transporttest.py arland --variant rides --minutes 20
    python lab/transporttest.py arland --variant rides --watch          # in the game window
    python lab/sublab.py run transport --scenario arland --variant foot

Measures, per trip (assign -> within 120 m of the base): how many, how far, door-to-door km/h (a walking team makes ~4-5),
by ride or on foot; soldier-km moved and per game minute; the rides - asked, delivered, failed (at the HQ, and why), slow
get-outs; boarding, drive and wait-at-the-base times; how full the vehicles were; unjams and stuck vehicles; the supply
trucks' deliveries; script errors.
"""
import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lab"))
import assaulttest  # noqa: E402  (its BASE setup, mods and ride counter)

SCENARIOS = {
    # name: words
    "arland": "Arland: the US holds every base but the Soviet HQ; its 12 teams of 4 travel from base to base (0.4-3 km trips)",
}
_TEAMS = assaulttest._sized(4) + " -aicfSquadsPerSide 12 -aicfArmedRideEvery 0"
# The fork's walk-over and pads by a road are on by default from 31 Oct 22:40 (note 479): the variants run before then
# pin them off, so their numbers stay what they were.
_OLD = " -aicfWalkOverMeters 0 -aicfPadNearRoadMeters 0 -aicfRideSpacingMs 0"
# Ride spacing (1 Nov, note 481) is on by default from 00:10: the variants run before it pin it off.
_NOSPACE = " -aicfRideSpacingMs 0"
VARIANTS = {
    # name: (extra command line, words for the app)
    "rides": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 90000" + _OLD,
              "as the watched battles until 31 Oct: transport rides (Humvee / UAZ-469 jeep), at most 3 leaving a base at a time, 90 s to reach the vehicle"),
    "foot": (_TEAMS + " -aicfInfantryRideMeters 100000" + _OLD, "no rides: every team walks - the reference for what the rides are worth"),
    "rides6": (_TEAMS + " -aicfRidesPerBase 6" + _OLD, "as rides, up to 6 rides leaving a base at a time"),
    # 31 Oct, the first window run: rides 12.9 km/h door to door v 12.0 on foot - 82 s from the ride's spot planned to
    # leaving (54 s boarding), 7 of 28 rides failed (the team didn't reach its vehicle in time / boarding ran out).
    "ride1k": (_TEAMS + " -aicfRidesPerBase 3 -aicfInfantryRideMeters 1000" + _OLD,
               "rides only for trips over 1 km (300 m now) - short trips walk, no wait for a vehicle"),
    "stage50": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnStagingRadiusMeters 50" + _OLD,
                "a team counts as at its vehicle spot within 50 m, not 25 (the 'never reached the vehicle in time' failures)"),
    # The first A/B (note 475): 8-9 failed rides a run were SPAWN_SITE_APPROACH_TIMEOUT - the whole team has 90 s to reach
    # the vehicle spot, and after a trip it is strung out (the last man up to 550 m behind, the spot 100-250 m away).
    "approach180": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000" + _OLD,
                    "180 s (not 90) for the team to reach its vehicle spot - the default from 31 Oct 17:05 (failed rides 38% -> 13%)"),
    # The overhead (note 476): ~90 s from a ride's spot planned to leaving, ~60 s of it boarding - the team waits 43 m from
    # the vehicle's spot (so it is clear of the pad) and walks over when the vehicle is there.
    # Boarding (note 477): 60 s median - a soldier who stops making progress is re-ordered after 8 s, the driver pick
    # rotated after ~16 s.
    "stall4": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000 -aicfVehiclePassengerStallMs 4000" + _OLD,
               "as approach180, and a soldier who stops making progress while boarding is re-ordered after 4 s, not 8"),
    "near-pad": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000 -aicfVehicleSpawnStagingOffsetMeters 20" + _OLD,
                 "as approach180, and the team waits 20 m from the vehicle's spot, not 43"),
    "ride1k-approach180": (_TEAMS + " -aicfRidesPerBase 3 -aicfInfantryRideMeters 1000 -aicfVehicleSpawnApproachTimeoutMs 180000" + _OLD,
                           "rides only over 1 km, and 180 s to reach the vehicle spot"),
    # Stuck vehicles (note 479): 24 of the 44 stuck-vehicle lines were within 60 m of the pad the ride left from - the
    # empty-ground search takes the clear spot nearest the base's spawn point (Military Training Area: in its junkyard).
    "road-pad": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000 -aicfPadNearRoadMeters 12 -aicfWalkOverMeters 0" + _NOSPACE,
                 "as approach180, and the vehicle appears on clear ground within 12 m of a road when the base has one"),
    # Boarding (note 479): the team waits ~60 m from the vehicle; the passengers stood idle while the driver ran over and
    # got in (24 s), then ran the same 60 m (36 s). And the test had the seat fallback off (-aicfNoHiddenSeat from the
    # assault test's base) - the watched battles have had it on since 30 Oct (note 456).
    "walk-over": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000 -aicfWalkOverMeters 12 -aicfPadNearRoadMeters 0" + _NOSPACE,
                  "as approach180, and the passengers walk to the vehicle while the driver gets in"),
    "seat-on": ((_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000").replace(" -aicfNoHiddenSeat", "") + _OLD,
                "as approach180 with the seat fallback on, as in the watched battles since 30 Oct"),
    "fast-board": ((_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000 -aicfPadNearRoadMeters 12"
                    " -aicfWalkOverMeters 12").replace(" -aicfNoHiddenSeat", "") + _NOSPACE,
                   "road-pad + walk-over + the seat fallback on"),
    "now": ((_TEAMS + " -aicfRidesPerBase 3").replace(" -aicfNoHiddenSeat", "") + _NOSPACE,
            "the fork's defaults from 31 Oct 22:40 (180 s, walk-over, pads by a road) with the seat fallback on - as the watched battles"),
    # Where the time goes (note 480): our 3-rides-per-base cap (29 Oct, the HQ jams) delayed rides 78-160 s and was the first
    # refusal on most trips that walked the whole way - the team walks off while it waits and is soon past 250 m.
    "cap5": ((_TEAMS + " -aicfRidesPerBase 5").replace(" -aicfNoHiddenSeat", "") + _NOSPACE,
             "as now, and up to 5 rides leaving a base at a time (3 now)"),
    "cap0": ((_TEAMS + " -aicfRidesPerBase 0").replace(" -aicfNoHiddenSeat", "") + _NOSPACE,
             "as now, with no cap on rides leaving a base (as before 29 Oct, when 5-9 rides jammed the HQ's road)"),
    # The walk-in (note 480): rides drop their team 150 m short of the target (the attack stand-off) even at a quiet base of
    # their own - ~10% of a team's time is the walk-in after the drop.
    # cap0 v now with the defend fix (31 Oct 23:05-23:46, same HQ): 7.4 / 9.2 v 4.8 / 6.2 soldier-km a minute - drop100 builds on cap0.
    "drop100": ((_TEAMS + " -aicfRidesPerBase 0 -aicfVehicleDismountDistanceMeters 100").replace(" -aicfNoHiddenSeat", "") + _NOSPACE,
                "as cap0 (no cap on rides out of a base), and rides drop their team within 100 m of the target, not 150"),
    # Martin (1 Nov, note 481): "cap is retarted maybe some kind of timing so its not at once but fuck cap" - no cap, rides out of
    # a base start 8 game seconds apart (the fork's default).
    "spaced": (_TEAMS.replace(" -aicfNoHiddenSeat", ""),
               "no cap on rides out of a base, they start 8 s apart; walk-over, pads by a road, the seat fallback on"),
    # spaced (1 Nov 00:29, north HQ): 8.5 / 8.4 soldier-km a minute, as good as no cap - but at the start burst 18 rides queued
    # 40 s (median) for their turn and 3 teams walked too far meanwhile.
    "spaced4": (_TEAMS.replace(" -aicfNoHiddenSeat", "") + " -aicfRideSpacingMs 4000",
                "as spaced, rides out of a base 4 s apart, not 8"),
    # spaced4 (1 Nov 00:51): the queue halved (20 s v 40 s), the totals not better (7.8 / 7.8) - 8 s stays. In those runs the
    # cooldown after a failed ride (3 game minutes on foot, 26 Oct: request-fail loops) was the first refusal on 4 whole-way walks.
    "cool90": (_TEAMS.replace(" -aicfNoHiddenSeat", "") + " -aicfRideCooldownMs 90000",
               "as spaced, and a team whose ride failed walks 90 s before it may ask again, not 3 min"),
}
# 1 Nov 22:30 (note 484, Martin: "really the only should walk long distances when car broke down"): the fork looks again for
# a vehicle spot after 10 s (not 60), allows 12 vehicles a side (not 10), and has no ride spacing by default. The variants
# above pin what they ran.
for _name, (_extra, _words) in list(VARIANTS.items()):
    _pin = " -aicfSiteRelookMs 0 -aicfMaxVehiclesPerFaction 10"
    if _name in ("spaced", "cool90"):
        _pin += " -aicfRideSpacingMs 8000"
    VARIANTS[_name] = (_extra + _pin, _words)
# cap0 overnight (4 runs): 17 of 96 trips of 1 km+ on foot (29 of 160 km) - no vehicle spot in time 5, the cooldown after a
# failed ride 3, the drop-off timing out 3, a soldier not boarding in time 2, the 10-s wait after a ride 2, the 10-vehicle limit 1.
VARIANTS["nowalk"] = (_TEAMS.replace(" -aicfNoHiddenSeat", ""),
                      "as cap0 (no cap, no spacing, the seat fallback on), and a team whose vehicle spot was taken looks again after "
                      "10 s, not 60; 12 vehicles a side, not 10")
# nowalk, watched (1 Nov 22:15, note 485): no long walk from a taken vehicle spot or the vehicle limit any more; 5 of the 7 long
# trips on foot came after a drop-off that ran out of time (one soldier slow to get out) - the ride counted as failed and the
# team walked 3 minutes, past 250 m. From 22:45 the fork has no cooldown after a slow drop-off; the variants above pin it on.
for _name, (_extra, _words) in list(VARIANTS.items()):
    VARIANTS[_name] = (_extra + " -aicfDropoffCooldown 1", _words)
VARIANTS["nowalk2"] = (_TEAMS.replace(" -aicfNoHiddenSeat", ""),
                       "as nowalk, and a slow drop-off (one soldier slow to get out) doesn't bar the team from its next ride")
# 2 Nov night (note 502): the same build with AI Conflict's old threat limit for its recoveries (0.01) - an A/B for the 0.35
# limit, the only difference. From 2 Nov 00:42 nowalk2 also carries the fork's departure queue, failed-get-in seat, 20-s
# retry at a base, the leg reset and ZCR's boarding hold (the fork's and ZCR's defaults).
VARIANTS["thr01"] = (_TEAMS.replace(" -aicfNoHiddenSeat", "") + " -aicfRecoveryMaxThreat 0.01",
                     "as nowalk2 (2 Nov fixes), with AI Conflict's old limit for its recoveries: only under a threat of 0.01")
TEST = " -zcrShuttleTest -zcrAllBasesTo US -aicfNoForces USSR -aicfNoVictory"
# Seats a ride vehicle has (the game's prefabs).
SEATS = {"M998_covered_long": 4, "UAZ469": 5, "M923A1_transport": 15, "Ural4320_transport": 15, "UAZ452_transport": 8}


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False, speed: float = 1) -> dict:
    extra, _ = VARIANTS[variant]
    import sublab
    title = sublab.title("transport", scenario, variant)
    label = f"transport-{scenario}-{variant}-p{port}" if not watch else f"transporttest-{scenario}-{variant}-watch"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--commander-mode", "US", "--mods", assaulttest.MODS, "--plan-seconds", "60",
            "--extra", f"{extra}{TEST} -zcrTestTitle {title}"]
    if watch:
        argv += ["--solo", "--watch"]
        argv[argv.index("--extra") + 1] += f" -zcrSpeed {speed:g}"
        argv[argv.index("--minutes") + 1] = str(round(minutes / speed, 2))
    subprocess.run(argv, cwd=str(ROOT), stdout=None if watch else subprocess.DEVNULL, stderr=None if watch else subprocess.DEVNULL,
                   creationflags=0 if watch else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


def _once(lines: list, tag: str, side: str = "US") -> list:
    """The lines with a tag for a side, each once (AI Conflict's lines often come twice): keyed by t_ms and slot."""
    out, seen = [], set()
    for l in lines:
        if tag not in l or f"faction={side} " not in l:
            continue
        k = ((re.search(r"t_ms=(\d+)", l) or [0, 0])[1], (re.search(r" slot=(\w+)", l) or [0, 0])[1])
        if k not in seen:
            seen.add(k)
            out.append(l)
    return out


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    out = {"scenario": scenario, "variant": variant, "run": run_dir.name, "run_path": str(run_dir)}
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        out["error"] = "no log"
        return out
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    # The trips (ZCR_ShuttleTest).
    trips = []
    for l in dict.fromkeys(l.split("SCRIPT", 1)[-1] for l in lines if "[ZCR][SHUTTLE]" in l and "event=arrive" in l):
        m = re.search(r" t=(\d+) .* slot=(\d+) event=arrive trip=(\d+) base=(\S+) dist=(\d+) trip_s=(\d+) rode=(\d) men=(\d+)", l)
        if m:
            trips.append({"t": int(m.group(1)), "slot": int(m.group(2)), "dist": int(m.group(5)), "s": int(m.group(6)),
                          "rode": m.group(7) == "1", "men": int(m.group(8))})
    assigned = len(set(l.split("SCRIPT", 1)[-1] for l in lines if "[ZCR][SHUTTLE]" in l and "event=assign" in l))
    rounds = {}
    for l in lines:
        m = re.search(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=US id=(\d+) role=(\w+) men=(\d+) ride=\d x=(-?\d+) z=(-?\d+)", l)
        if m:
            rounds.setdefault(int(m.group(1)), []).append((m.group(3), int(m.group(4)), float(m.group(5)), float(m.group(6))))
    last_t = max(rounds) if rounds else 0
    out["minutes"] = round(last_t / 60, 1)
    out["trips_assigned"] = assigned
    out["trips_done"] = len(trips)
    med = lambda v: round(statistics.median(v), 1) if v else -1
    kmh = [t["dist"] / t["s"] * 3.6 for t in trips if t["s"] > 0]
    out["door_kmh"] = med(kmh)
    out["door_kmh_ride"] = med([t["dist"] / t["s"] * 3.6 for t in trips if t["s"] > 0 and t["rode"]])
    out["door_kmh_foot"] = med([t["dist"] / t["s"] * 3.6 for t in trips if t["s"] > 0 and not t["rode"]])
    out["trip_km"] = med([t["dist"] / 1000 for t in trips])
    out["rode_pct"] = round(100 * sum(1 for t in trips if t["rode"]) / len(trips)) if trips else 0
    out["long_rode_pct"] = (round(100 * sum(1 for t in trips if t["rode"] and t["dist"] >= 1000) / max(1, sum(1 for t in trips if t["dist"] >= 1000)))
                            if trips else 0)
    out["soldier_km"] = round(sum(t["men"] * t["dist"] for t in trips) / 1000, 1)
    out["soldier_km_per_min"] = round(out["soldier_km"] / out["minutes"], 2) if out["minutes"] else 0
    # The rides (AI Conflict's trip states), with the assault test's counter.
    by_t = {t: [(r, n, x, z) for r, n, x, z in v] for t, v in rounds.items()}
    out.update(assaulttest.rides(lines, "US", by_t))
    state, since, board, drive, wait, why, planned = {}, {}, [], [], [], {}, {}
    for l in _once(lines, "VEHICLE_STATE_CHANGED"):
        t = re.search(r"t_ms=(\d+)", l)
        s = re.search(r" slot=(\w+)", l)
        st = re.search(r"new_state=(\w+)|state=(\w+)", l)
        if not (t and s and st):
            continue
        slot, now, new = s.group(1), int(t.group(1)) / 1000, st.group(1) or st.group(2)
        old = state.get(slot)
        if new == "SITE_PLANNED":
            planned[slot] = now
        if new == "TRANSIT" and old == "BOARDING":
            board.append(now - since[slot])
        if new == "TRANSIT" and slot in planned:
            wait.append(now - planned.pop(slot))
        if new == "DISMOUNT" and old == "TRANSIT":
            drive.append(now - since[slot])
        if new == "FALLBACK" and old != "DISMOUNT":
            r = re.search(r"reason=(\w+)", l)
            why[r.group(1) if r else "?"] = why.get(r.group(1) if r else "?", 0) + 1
        state[slot], since[slot] = new, now
    out["board_s"] = round(statistics.median(board)) if board else -1
    out["drive_s"] = round(statistics.median(drive)) if drive else -1
    out["base_wait_s"] = round(statistics.median(wait)) if wait else -1
    out["fail_reasons"] = ", ".join(f"{k} {v}" for k, v in sorted(why.items(), key=lambda kv: -kv[1]))
    cars, full = {}, []
    men_of = {}
    for l in _once(lines, "VEHICLE_SPAWNED]"):
        m = re.search(r"prefab=\{[0-9A-F]+\}Prefabs/Vehicles/\w+/\w+/(\w+)\.et", l)
        s = re.search(r" numeric_slot=(\d+)", l)
        if m:
            cars[m.group(1)] = cars.get(m.group(1), 0) + 1
            if s:
                men_of[int(s.group(1))] = m.group(1)
    out["vehicles"] = ", ".join(f"{k} {v}" for k, v in sorted(cars.items()))
    seats = [min(1.0, t["men"] / SEATS[men_of[t["slot"]]]) for t in trips if t["rode"] and men_of.get(t["slot"]) in SEATS]
    out["seat_use_pct"] = round(100 * statistics.mean(seats)) if seats else -1
    out["unjams"] = len({l.split("SCRIPT", 1)[-1] for l in lines if "[ZCR][UNJAM]" in l and "side=US " in l and "action=" in l})
    stuck = {l.split("SCRIPT", 1)[-1] for l in lines if "[ZCR][MOVEFAIL]" in l and "side=US " in l}
    out["stuck"] = len(stuck)
    # Stuck within 60 m of a pad a US ride was spawned on - the ride couldn't get out to the road (note 479).
    pads = {(float(m.group(1)), float(m.group(2))) for l in lines if "VEHICLE_SPAWN_PAD_PROBE" in l and "faction=US" in l and "result=CLEAR" in l
            for m in [re.search(r"origin=<([-\d.]+),[-\d.]+,([-\d.]+)>", l)] if m}
    at = [(int(m.group(1)), int(m.group(2))) for l in stuck for m in [re.search(r" x=(\d+) z=(\d+)", l)] if m]
    out["stuck_at_pad"] = sum(1 for x, z in at if any((x - a) ** 2 + (z - b) ** 2 < 3600 for a, b in pads))
    # The supply trucks: deliveries unloaded and how much.
    unloads = [l for l in _once(lines, "LOGISTICS_UNLOAD_COMMITTED") if "purpose=DELIVERY" in l]
    out["supply_runs"] = len(unloads)
    out["supplies"] = sum(int((re.search(r" amount=(\d+)", l) or [0, 0])[1]) for l in unloads)
    out["enemy_teams"] = len(_once(lines, "GROUP_ENTITY_SPAWNED", "USSR"))
    out["lost"] = sum(1 for l in lines if "[ZCR][LOSS]" in l and " side=US " in l and "kind=man" in l)
    out["script_errors"] = len([l for l in lines if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l])
    out["crashed"] = bool(list(log.parent.glob("*.mdmp")))
    out.update(timeline(lines))
    return out


FAR_M = 400      # a team this far from its target base is on a trip, not at its target
BASE_M = 250     # a team this close to a base is at a base (walking to its vehicle, waiting for one), not walking a trip
SLICE_S = 300


def timeline(lines: list) -> dict:
    """What Martin sees, over time (2 Nov, note 496: 'it degrated with time, a lot of walking units or stuck vehicles'
    while rode_pct said 98% - it counts only trips that arrived). From every [ZCR][LIVE] team sample: team-minutes on
    foot more than FAR_M from the target base and BASE_M from every base (walk_far_min; walk_far_pct of all team time),
    on foot and standing anywhere far from the target, bases too (idle_far_min); aboard a vehicle that doesn't move
    (still_aboard_min); each also as a share of all team time (_pct); AI Conflict's stuck
    vehicles and failed rides; per 5 game minutes in 'by5'. The target base's spot = where teams stood when they
    arrived there."""
    samples = {}
    for l in lines:
        m = re.search(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=US id=(\d+) \S+ men=(\d+) ride=(\d) x=(-?\d+) z=(-?\d+) to=(\S+)", l)
        if m:
            samples[(int(m.group(1)), int(m.group(2)))] = (int(m.group(4)), float(m.group(5)), float(m.group(6)), m.group(7), int(m.group(3)))
    arrive = []
    for l in lines:
        m = re.search(r"\[ZCR\]\[SHUTTLE\] t=(\d+) side=US slot=(\d+) event=arrive trip=\d+ base=(\S+)", l)
        if m:
            arrive.append((int(m.group(1)), int(m.group(2)), m.group(3)))
    by_team = {}
    for (t, i), v in sorted(samples.items()):
        by_team.setdefault(i, []).append((t,) + v)
    spots = {}
    for t, i, base in arrive:
        near = min(by_team.get(i, []), key=lambda s: abs(s[0] - t), default=None)
        if near and abs(near[0] - t) <= 20:
            spots.setdefault(base, []).append((near[2], near[3]))
    spot = {b: (statistics.median(x for x, _ in v), statistics.median(z for _, z in v)) for b, v in spots.items()}
    # The HQ: where the teams stood at the first sample.
    first = [ss[0] for ss in by_team.values() if ss]
    if first:
        spot.setdefault("HQ", (statistics.median(s[2] for s in first), statistics.median(s[3] for s in first)))
    end = max((t for t, _ in samples), default=0)
    nslices = end // SLICE_S + 1
    walk = [0.0] * nslices
    idle = [0.0] * nslices
    still = [0.0] * nslices
    for i, ss in by_team.items():
        for a, b in zip(ss, ss[1:]):
            t, ride, x, z, to, men = a
            dt = min(b[0] - t, 30)
            if men <= 0 or to not in spot:
                continue
            if math.hypot(x - spot[to][0], z - spot[to][1]) <= FAR_M:
                continue
            moved = math.hypot(b[2] - x, b[3] - z) >= 3 * max(1, dt / 10)
            if ride:
                if not moved:
                    still[t // SLICE_S] += dt / 60          # aboard a vehicle that doesn't move (boarding, queue, stuck)
                continue
            if not moved:
                idle[t // SLICE_S] += dt / 60               # on foot, standing - at a base too (D1 'chilling at a house')
            if any(math.hypot(x - bx, z - bz) <= BASE_M for bx, bz in spot.values()):
                continue                                     # at a base: walking to the vehicle, waiting for one
            walk[t // SLICE_S] += dt / 60
    stuck = [0] * nslices
    failed = [0] * nslices
    t0 = None
    for l in lines:
        m = re.search(r"\[ZCR\]\[LIVE\] t=(\d+) ", l)
        tm = re.search(r"^(\d\d):(\d\d):(\d\d)", l)
        if m and tm and t0 is None:
            t0 = int(tm.group(1)) * 3600 + int(tm.group(2)) * 60 + int(tm.group(3)) - int(m.group(1))
    def game_t(l):
        tm = re.search(r"^(\d\d):(\d\d):(\d\d)", l)
        return (int(tm.group(1)) * 3600 + int(tm.group(2)) * 60 + int(tm.group(3)) - t0) if tm and t0 is not None else -1
    for l in _once(lines, "VEHICLE_STUCK_DETECTED"):
        t = game_t(l)
        if 0 <= t < nslices * SLICE_S:
            stuck[t // SLICE_S] += 1
    for l in lines:
        if "[ZCR][RIDE] faction=US " in l and "failed=" in l:
            t = game_t(l)
            if 0 <= t < nslices * SLICE_S:
                failed[t // SLICE_S] += 1
    # A failed ride at a base followed by the same team's next boarding within 2 minutes (2 Nov, note 500 - Martin: "team d1
    # recovered somehow"; the 20-s wait after a failed ride at a base, notes 489-491).
    retries, retried = 0, 0
    boards = {}
    for l in _once(lines, "BOARDING_COMPLETE]"):
        sm = re.search(r" numeric_slot=(\d+)", l)
        if sm:
            boards.setdefault(int(sm.group(1)), []).append(game_t(l))
    for l in lines:
        m = re.search(r"\[ZCR\]\[RIDE\] faction=US slot=(\d+) failed=\S+ walks_ms=\d+ at_base=1", l)
        if m:
            retries += 1
            t = game_t(l)
            if any(0 < b - t <= 120 for b in boards.get(int(m.group(1)), [])):
                retried += 1
    by5 = " | ".join(f"{k * 5}-{k * 5 + 5}: walk {walk[k]:.0f} idle {idle[k]:.0f} still {still[k]:.0f} stuck {stuck[k]} failed {failed[k]}"
                     for k in range(nslices))
    mins = max(1.0, end / 60)
    teams = max(1, len(by_team))
    return {"walk_far_min": round(sum(walk), 1), "walk_far_pct": round(100 * sum(walk) / (teams * mins)),
            "idle_far_min": round(sum(idle), 1), "idle_far_pct": round(100 * sum(idle) / (teams * mins)),
            "still_aboard_min": round(sum(still), 1), "still_aboard_pct": round(100 * sum(still) / (teams * mins)),
            "stuck_detected": sum(stuck), "rides_failed_t": sum(failed), "base_fail_retried": f"{retried}/{retries}", "by5": by5}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="rides", choices=list(VARIANTS))
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--port", type=int, default=2162)
    ap.add_argument("--watch", action="store_true", help="in the game window (solo) - only when nobody else uses the game")
    ap.add_argument("--speed", type=float, default=1, help="with --watch: the game's time multiplier")
    ap.add_argument("--summarize", default="", help="summarize an existing run folder instead of running")
    a = ap.parse_args()
    r = summarize(Path(a.summarize), a.scenario, a.variant) if a.summarize else run(a.scenario, a.variant, a.minutes, 0, a.port, a.watch, a.speed)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
