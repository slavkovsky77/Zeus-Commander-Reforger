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
VARIANTS = {
    # name: (extra command line, words for the app)
    "rides": (_TEAMS + " -aicfRidesPerBase 3",
              "as the watched battles: transport rides (Humvee / UAZ-469 jeep), at most 3 rides leaving a base at a time"),
    "foot": (_TEAMS + " -aicfInfantryRideMeters 100000", "no rides: every team walks - the reference for what the rides are worth"),
    "rides6": (_TEAMS + " -aicfRidesPerBase 6", "as rides, up to 6 rides leaving a base at a time"),
    # 31 Oct, the first window run: rides 12.9 km/h door to door v 12.0 on foot - 82 s from the ride's spot planned to
    # leaving (54 s boarding), 7 of 28 rides failed (the team didn't reach its vehicle in time / boarding ran out).
    "ride1k": (_TEAMS + " -aicfRidesPerBase 3 -aicfInfantryRideMeters 1000",
               "rides only for trips over 1 km (300 m now) - short trips walk, no wait for a vehicle"),
    "stage50": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnStagingRadiusMeters 50",
                "a team counts as at its vehicle spot within 50 m, not 25 (the 'never reached the vehicle in time' failures)"),
    # The first A/B (note 475): 8-9 failed rides a run were SPAWN_SITE_APPROACH_TIMEOUT - the whole team has 90 s to reach
    # the vehicle spot, and after a trip it is strung out (the last man up to 550 m behind, the spot 100-250 m away).
    "approach180": (_TEAMS + " -aicfRidesPerBase 3 -aicfVehicleSpawnApproachTimeoutMs 180000",
                    "180 s (not 90) for the team to reach its vehicle spot"),
    "ride1k-approach180": (_TEAMS + " -aicfRidesPerBase 3 -aicfInfantryRideMeters 1000 -aicfVehicleSpawnApproachTimeoutMs 180000",
                           "rides only over 1 km, and 180 s to reach the vehicle spot"),
}
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
    out["stuck"] = len({l.split("SCRIPT", 1)[-1] for l in lines if "[ZCR][MOVEFAIL]" in l and "side=US " in l})
    # The supply trucks: deliveries unloaded and how much.
    unloads = [l for l in _once(lines, "LOGISTICS_UNLOAD_COMMITTED") if "purpose=DELIVERY" in l]
    out["supply_runs"] = len(unloads)
    out["supplies"] = sum(int((re.search(r" amount=(\d+)", l) or [0, 0])[1]) for l in unloads)
    out["enemy_teams"] = len(_once(lines, "GROUP_ENTITY_SPAWNED", "USSR"))
    out["lost"] = sum(1 for l in lines if "[ZCR][LOSS]" in l and " side=US " in l and "kind=man" in l)
    out["script_errors"] = len([l for l in lines if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l])
    out["crashed"] = bool(list(log.parent.glob("*.mdmp")))
    return out


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
