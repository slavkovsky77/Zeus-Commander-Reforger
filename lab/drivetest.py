"""The driving test track: a few crewed vehicles driven A -> B -> A on one stretch with a known trap, headless, for a
few minutes - a fix tried in minutes on the same stretch instead of waiting for a match to send rides through it
(22 Oct, Martin: "do a simple scenario that reproduces the issue ... to optimise it faster").

    python lab/drivetest.py mosshill                      # the game's driver with our unjam (the default build)
    python lab/drivetest.py mosshill --variant raw        # no unjam at all: the game's driver alone
    python lab/drivetest.py mosshill --variant price      # + the road price addon (roads 10x cheaper than fields)
    python lab/drivetest.py mosshill northfarm --minutes 10 --cars 6

Each run prints one line: legs driven, median and longest leg, legs still open at the end, jams, stuck spells,
failed drives, pushes and the share of moving samples off the road. Runs on its own port, idle priority (the watched
loop keeps the game window); AI Conflict's own war goes on around the track (no switch turns it off), so each track
drives the side that holds its ground.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name: (map, A, B, kind) - A and B snap to the nearest road in the game.
TRACKS = {
    # name: (map, A, B, kind, via or "", both) - A, B and the via point snap to the nearest road in the game.
    # Moss Hill: a farm lane squeezed between a supply cache and a static car wreck with brick piles (2292,1277);
    # 155 stuck/unreachable reports there on 22 Oct, rides of both sides queueing behind. USSR ground.
    "mosshill": ("arland-test", "1700,1000", "2800,1600", "uaz", "2292,1277", False),
    # The same stretch with the Conflict bases in place (Moss Hill's supply cache by the lane) - the trap catches here.
    "mosshill-conflict": ("arland-conflict-test", "1700,1000", "2800,1600", "uaz", "2292,1277", False),
    # Head-on: the Moss Hill route with every second car starting at B - they meet on the narrow lane all the time
    # (two head-on crashes in two runs on 22 Oct, both drivers dead).
    "headon": ("arland-test", "1700,1000", "2800,1600", "uaz", "2292,1277", True),
    # Convoys A -> B through the same lane, one after the other (Martin, 23 Oct night: "convoy test would be great too").
    "convoy": ("arland-test", "1700,1000", "2800,1600", "uaz", "2292,1277", "convoy"),
    # The road blocked: every second convoy's lead car is hit at the lane, a wreck stays a minute (Martin: "they would meet
    # and one of them would explode, so we see how the other direction reacts to the blocked road"; "convoy and the front one").
    "convoyblast": ("arland-test", "1700,1000", "2800,1600", "uaz", "2292,1277", "convoy;blast"),
    "headonblast": ("arland-test", "1700,1000", "2800,1600", "uaz", "2292,1277", "both;blast"),
    # Traffic (Martin, 23 Oct night: "supply runs ... transporting soldiers and supplies by many cars, a traffic simulation"):
    # UAZ vans, Ural troop trucks (8 soldiers in the back) and Ural supply trucks between four stops - Moss Hill's two
    # ends, the north farm and the north-west - each to a random next stop, 10 s loading there. A holds the stops, kind the mix.
    # Armour (Martin, 23 Oct: "this sub-lab should test some tanks and APCs", review note 322): BTR-70s on the head-on
    # lane and in convoys with the lead hit; the Workshop T-72 head-on and BMP-1 convoys (loaded with --armour).
    "apc-headon": ("arland-test", "1700,1000", "2800,1600", "btr70", "2292,1277", True),
    "apc-convoyblast": ("arland-test", "1700,1000", "2800,1600", "btr70", "2292,1277", "convoy;blast"),
    "tank-headon": ("arland-test", "1700,1000", "2800,1600", "t72", "2292,1277", True),
    "ifv-convoyblast": ("arland-test", "1700,1000", "2800,1600", "bmp1", "2292,1277", "convoy;blast"),
    "traffic": ("arland-test", "1700,1000;2800,1600;2450,2950;1200,3250", "", "uaz,ural,uralsupply", "", "traffic"),
    # Supply runs (Martin, 23 Oct: "1. the truck comes to the supply point to pick up supplies -> to the point that should be
    # supplied and unloads them; 2. the same with manpower"): trucks start empty at the destination (stop 2), load at the
    # supply point (stop 1) and unload at the destination; manpower: a squad waits by the pickup, boards, gets out there.
    # Both routes pass the junction bend at (2515, 1580-1690) where the watched trucks hit each other.
    "supply": ("arland-test", "1700,1000;2800,1600", "", "uralsupply", "", "shuttle"),
    # The Soviet supply vans at the Farm (24 Oct 19:46, report 27 - Martin: "this is a pretty big issue, let's simulate it
    # in the sub-lab and fix it, without fighting"): two UAZ-452 vans leave together from the Farm's depot spots (2141,2938 and
    # 2112,2943, AI Conflict's spawn slots) for the source base 1.1 km east; in the match they met at the farm wall's corner
    # and dodged each other for 100+ s (the game's move-from-incoming-vehicle on both) while our spacing rule stopped them.
    "farm": ("arland-test", "2141,2938|2112,2943", "3253,2862", "uaz", "", "pair"),
    "farm-conflict": ("arland-conflict-test", "2141,2938|2112,2943", "3253,2862", "uaz", "", "pair"),
    "manpower": ("arland-test", "1700,1000;2800,1600", "", "uralpickup", "", "shuttle"),
    # Trucks through the same lane, both ways (supply trucks; Competent AI driving widens their turn radius).
    "trucks": ("arland-test", "1700,1000", "2800,1600", "ural", "2292,1277", True),
    # North farm fields: rides cut across fenced fields (2040,2980 / 2150,2880 / 2250,2970) on their way to the
    # US main base and can't find a way out (UNREACHABLE). US ground.
    "northfarm": ("arland-test", "2450,2950", "1200,3250", "m998", "", False),
    # Everon: the US main base's exit road (5350,9960, 16 m off the road by farm fences).
    "everonexit": ("everon-test", "5700,9650", "4700,9900", "m998", "", False),
}

VARIANTS = {
    # name: (extra server parameters, extra mods)
    "raw": ("-zcrNoUnjam -zcrNoEarlyUnjam -zcrNoOncoming -zcrNoTraffic -zcrCrewsLeave", ""),
    "moveturrets": ("-zcrMoveTurrets", ""),                                    # ours, and stuck armour gets pushed back too (off since 22 Oct: crashes)  # the game's driver alone
    "default": ("", ""),                                                      # ours: push back-offs, early unjam, oncoming slow-down, spacing
    "nospacing": ("-zcrNoSpacing", ""),                                       # ours without the spacing rule
    "risk": ("-zcrRisk -zcrNoOncoming -zcrNoSpacing", ""),
    "risk2": ("-zcrRisk -zcrNoOncoming -zcrNoSpacing", ""),                   # v2.1: the same flags, this copy's forecast window 130 m                    # ours with the collision forecast instead of oncoming + spacing
    "nooncoming": ("-zcrNoOncoming", ""),
    "nocrossing": ("-zcrNoCrossing -zcrNoJunction", ""),                      # ours without the crossing and junction rules (before 23 Oct evening)
    "nojunction": ("-zcrCrossing -zcrNoJunction", ""),                        # ours with the crossing rule but not the junction slow-down
    "crossing": ("-zcrCrossing", ""),                                         # ours plus the crossing rule (off by default since 23 Oct 19:40)
    "late": ("-zcrNoEarlyUnjam", ""),                                         # back-offs only after 45 s
    "price": ("", "3B9F2C4D5E6A7B81"),                                        # + roads 10x cheaper than fields
    "competent": ("", "68FCF11534562F2E"),                                    # + Competent AI driving (turn radius, trucks/APCs)
    "crx": ("", "5F268647F8A1A1F4"),                                          # + CRX Enfusion A.I. (column driving, vehicle combat)
    "jmvai": ("-zcrNoUnjam -zcrNoEarlyUnjam -zcrNoOncoming -zcrNoTraffic", "6A8490E1621E7B3C,7A3C51E0D2B94F61"),   # JMVehicleAI, tuned, alone
    "best": ("", "3B9F2C4D5E6A7B81,68FCF11534562F2E"),                         # ours + road price + Competent AI driving
    # The Farm's wall corner (24 Oct): the same with the trees within 8 m of the corner's gap deleted - is it the tree?
    "notree": ("-zcrProbeAt 2196,2929,8 -zcrClearTrees -zcrRoadsAt 2180,2920,180", "3B9F2C4D5E6A7B81,68FCF11534562F2E"),
    "probe": ("-zcrProbeAt 2196,2929,8 -zcrRoadsAt 2180,2920,180", "3B9F2C4D5E6A7B81,68FCF11534562F2E"),
}


ARMOUR_KINDS = {"t72", "m1a1", "bmp1", "bradley"}   # Workshop vehicles: lab/reforger.py --armour loads them


def _title(name: str, scenario: str, variant: str) -> str:
    sys.path.insert(0, str(ROOT / "lab"))
    import sublab
    return sublab.title(name, scenario, variant)


def run(track: str, variant: str, minutes: float, cars: int, port: int, watch: bool = False, speed: float = 3) -> dict:
    map_name, a, b, kind, via, both = TRACKS[track]
    extra, mods = VARIANTS[variant]
    mode = ("both" if both else "") if isinstance(both, bool) else both
    spec = f"{a};{b};{cars};{kind};{via or '-'}" + (f";{mode}" if mode else "")
    test = f"-zcrDriveTest {spec}"
    if mode in ("traffic", "shuttle"):
        test = f"-zcrTrafficSim {a} -zcrTrafficCars {cars} -zcrTrafficKinds {kind}" + (" -zcrTrafficShuttle" if mode == "shuttle" else "")
    # The port in the name: two runs of the same track and setup start in the same second on the night's two ports, and
    # run folders are named label + second (23 Oct: every second run of a pair came back empty).
    label = f"drivetest-{track}-{variant}-p{port}" if not watch else f"drivetest-{track}-{variant}-watch"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", map_name, "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "none", "--ussr", "none", "--extra", f"-aicfOff -zcrLabWeather -zcrNoFIA -zcrArmourVanilla -zcrNoArmour -zcrTestTitle {_title('driving', track, variant)} {test} {extra}".strip()]
    if mods:
        argv += ["--mods", mods]
    if kind in ARMOUR_KINDS:
        argv += ["--armour"]   # the Workshop tanks and IFVs
    if watch:
        # The game window at 3x by default (Martin, 24 Oct: "make default speed 3x"): the game's own time multiplier
        # (-zcrSpeed, as the watched matches); the test still lasts 'minutes' game minutes.
        argv += ["--watch", "--solo"]
        if speed > 1:
            argv[argv.index("--extra") + 1] += f" -zcrSpeed {speed:g}"
            argv[argv.index("--minutes") + 1] = str(round(minutes / speed, 2))   # in the game window (lab/watch_test.py records it)
    subprocess.run(argv, cwd=str(ROOT), stdout=None if watch else subprocess.DEVNULL, stderr=None if watch else subprocess.DEVNULL,
                   creationflags=0 if watch else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"track": track, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], track, variant)


def summarize(run_dir: Path, track: str, variant: str) -> dict:
    """One flat summary of a finished track run (also for backfilling old runs into the sub-lab)."""
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    out = {"track": track, "variant": variant}
    if not log:
        out["error"] = "no log"
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    legs = [int(x) for x in re.findall(r"\[ZCR\]\[DRIVETEST\] .*event=ARRIVE .*leg_s=(\d+)", text)]
    legs += [int(x) for x in re.findall(r"\[ZCR\]\[TRAFFICSIM\] .*event=DELIVER .* s=(\d+)", text)]   # traffic: a delivery is a trip
    km = re.findall(r"\[ZCR\]\[TRAFFICSIM_SUM\] .* km=([\d.]+)", text)
    legs.sort()
    last = re.findall(r"\[ZCR\]\[DRIVETEST_SUM\] .*open_legs=(\d+) oldest_open_s=(\d+)", text)
    moving = sum(int(x) for x in re.findall(r"\[ZCR\]\[OFFROAD\] .*moving=(\d+)", text))
    off = sum(int(x) for x in re.findall(r"\[ZCR\]\[OFFROAD\] .*offroad=(\d+)", text))
    out.update({
        "spawned": text.count("event=SPAWN"), "lost": text.count("event=LOST"),
        "legs": len(legs), "median_leg_s": legs[len(legs) // 2] if legs else None, "max_leg_s": legs[-1] if legs else None,
        "oldest_open_s": int(last[-1][1]) if last else None,
        "jams": text.count("[ZCR][JAM]"), "stuck": text.count("[ZCR][STUCKVEH]"), "move_fails": text.count("[ZCR][MOVEFAIL]"),
        "unreachable": len(re.findall(r"\[ZCR\]\[MOVEFAIL\] .*error=UNREACHABLE", text)), "pushes": text.count("[ZCR][PUSH]"),
        "gates": text.count("[ZCR][GATE]"),
        "car_hits": len([l for l in text.splitlines() if "[ZCR][COLLISION]" in l and " other=object " not in l]),
        # The Farm pair (24 Oct): seconds the drivers spent dodging each other, pairs done, both arrived, the second car's time.
        "evade_s": sum(int(m) for m in re.findall(r"event=ARRIVE .* evade_s=(\d+)", text)),
        "evade_max_s": max([int(m) for m in re.findall(r"event=ARRIVE .* evade_s=(\d+)", text)] or [0]),
        "pairs": len(re.findall(r"event=CONVOY ", text)),
        # The fixes (24 Oct): dodging broken (one gives way), detours from a dead end, gates and barriers opened ahead.
        "dodge_broken": len(re.findall(r"\[ZCR\]\[DODGE\] t=\d+ side=", text)),
        "detours": len(re.findall(r"\[ZCR\]\[DETOUR\] .* via_m=", text)),
        "detour_no_road": len(re.findall(r"\[ZCR\]\[DETOUR\] .* why=no_road", text)),
        "gates_opened": len(re.findall(r"\[ZCR\]\[GATEAHEAD\] .* gate=", text)),
        "unreachable": len(re.findall(r"\[ZCR\]\[MOVEFAIL\] .* error=UNREACHABLE", text)),
        "crew_out": len(re.findall(r"event=LOST .* why=crew_out", text)),
        "road_first": len(re.findall(r"\[ZCR\]\[ROADFIRST\]", text)),
        "pairs_through": len(re.findall(r"event=CONVOY .* cars=2 arrived=2 ", text)),
        "pair_last_s": (sorted(int(m) for m in re.findall(r"event=CONVOY .* last_s=(\d+)", text) if int(m) >= 0) or [None])[-1],
        "oncoming": len(re.findall(r"\[ZCR\]\[ONCOMING\] .* other=", text)),
        "stops": len(re.findall(r"\[ZCR\]\[SPACING\] .*band=stop", text)),
        "risk_caps": text.count("[ZCR][RISK]"),
        "crossings": len(re.findall(r"\[ZCR\]\[CROSSING\] .* other=", text)),
        "junction_slows": len(re.findall(r"\[ZCR\]\[JUNCTION\] .* other=", text)),
        "crossing_timeouts": len(re.findall(r"\[ZCR\]\[CROSSING\] .*why=timeout", text)),
        "men_delivered": int((re.findall(r"\[ZCR\]\[TRAFFICSIM_SUM\] .*men_delivered=(\d+)", text) or [0])[-1]),
        "supplies_delivered": int((re.findall(r"\[ZCR\]\[TRAFFICSIM_SUPPLY\] .*supplies_delivered=(\d+)", text) or [0])[-1]),
        "km": float(km[-1]) if km else None, "deliveries": text.count("event=DELIVER"),
        "blasts": text.count("event=BLAST "), "blocked": text.count("event=BLOCKED"), "wreck_gone": text.count("event=WRECK_GONE"),
        "pass_s": sorted(int(x) for x in re.findall(r"event=PASSWRECK s=(\d+)", text)),
        "convoys": [dict(re.findall(r"(\w+)=(-?\w+)", l.split("event=CONVOY", 1)[1])) for l in text.splitlines() if "event=CONVOY" in l],
        "offroad_pct": round(100 * off / moving) if moving else None,
        "script_errors": len([l for l in text.splitlines() if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l]),
        "crashed": bool(list(log.parent.glob("*.mdmp"))), "run": run_dir.name, "run_path": str(run_dir),
    })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+", choices=sorted(TRACKS))
    ap.add_argument("--variant", default="default", choices=sorted(VARIANTS))
    ap.add_argument("--minutes", type=float, default=8)
    ap.add_argument("--cars", type=int, default=6)
    ap.add_argument("--port", type=int, default=2148)
    ap.add_argument("--speed", type=float, default=3, help="with --watch: the game's time multiplier (default 3x)")
    ap.add_argument("--watch", action="store_true", help="in the game window (only when nobody else uses the game)")
    a = ap.parse_args()
    for track in a.tracks:
        r = run(track, a.variant, a.minutes, a.cars, a.port, a.watch, a.speed)
        print(" ".join(f"{k}={v}" for k, v in r.items()), flush=True)


if __name__ == "__main__":
    main()
