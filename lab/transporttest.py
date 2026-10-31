"""The transport test (31 Oct, Martin: "prepare transport sublab, this sublab will just do moving of manpower as efficiently
as possible (no enemy on the map)"; review note 471). A full Arland match with one side only - AI Conflict's US commander,
no Soviet commander (-aicfAICommanderMode US: the Soviets field nobody), no FIA, no drones - and one point on every list
(-zcrOnePoint): the US moves all its teams from its HQ to that point the way the watched matches do (AI Conflict's rides,
12 teams of 4). How fast does the manpower get there, and what goes wrong on the way?

    python lab/transporttest.py signal --variant rides --minutes 12
    python lab/sublab.py run transport --scenario signal --variant foot --repeat 1

Measures: soldiers within 300 m of the point at game minute 3, 5, 8 and 12 (and as a share of the side's soldiers); when
a quarter, half and three quarters of them were there; the rides - asked, delivered, failed (at the HQ / on the way, and
why), slow get-outs, the most at once; how long boarding and the drive took (medians); the vehicles used; unjams and stuck
vehicles; script errors. Which HQ the US got is random per match (the harbour or the south one) - the run says which.
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
import assaulttest  # noqa: E402  (its BASE setup, ride counter and summary)

SCENARIOS = {
    # name: (assaulttest scenario for the objective, words)
    "signal": ("point", "Signal Hill - 1.6-1.7 km from either HQ, so both HQs give about the same trip"),
    "farm": ("city", "Farm - 1.1 km from the harbour HQ, 2.1 km from the south one (the watched battle's base)"),
}
_TEAMS = assaulttest._sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfArmedRideEvery 0"
VARIANTS = {
    # name: (extra command line, words for the app)
    "rides": (_TEAMS + " -aicfRidesPerBase 3",
              "as the watched Farm battle: 12 teams of 4, transport rides (Humvee / UAZ-469 jeep), at most 3 rides leaving the HQ at a time"),
    "foot": (_TEAMS + " -aicfInfantryRideMeters 100000", "no rides: every team walks - the reference for what the rides are worth"),
    "rides6": (_TEAMS + " -aicfRidesPerBase 6", "as rides, up to 6 rides leaving the HQ at a time"),
}
TRANSIT_FAIL_AT_HQ_M = 150


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False, speed: float = 1) -> dict:
    point = assaulttest.POINTS[SCENARIOS[scenario][0]]
    extra, _ = VARIANTS[variant]
    import bridges
    import sublab
    bridges.ensure(("point",))
    title = sublab.title("transport", scenario, variant)
    label = f"transport-{scenario}-{variant}-p{port}" if not watch else f"transporttest-{scenario}-{variant}-watch"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "point", "--commander-mode", "US", "--mods", assaulttest.MODS, "--plan-seconds", "60",
            "--extra", f"{extra} -zcrOnePoint {point} -zcrTestTitle {title}"]
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


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    out = assaulttest.summarize(run_dir, SCENARIOS[scenario][0], variant, attacker="US")
    out["scenario"] = scenario
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        return out
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    # When a quarter, half and three quarters of the side's soldiers were within 300 m of the point.
    rounds = {}
    for l in lines:
        m = re.search(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=US id=(\d+) role=\w+ men=(\d+) ride=\d x=(-?\d+) z=(-?\d+)", l)
        if m:
            rounds.setdefault(int(m.group(1)), {})[int(m.group(2))] = (int(m.group(3)), float(m.group(4)), float(m.group(5)))
    obj = _objective(run_dir, lines)
    # Which HQ the US got (random per match): where its teams stood in the first round - the harbour (1158, 3282) or the south (1634, 909).
    if rounds:
        zs = sorted(z for _, _, z in rounds[min(rounds)].values())
        out["hq"] = "harbour" if zs[len(zs) // 2] > 2000 else "south"
    for share in (25, 50, 75):
        out[f"t{share}_s"] = -1
        if not obj:
            continue
        for t in sorted(rounds):
            men = sum(n for n, _, _ in rounds[t].values())
            near = sum(n for n, x, z in rounds[t].values() if (x - obj[0]) ** 2 + (z - obj[1]) ** 2 <= assaulttest.NEAR_M ** 2)
            if men >= 8 and near * 100 >= share * men:
                out[f"t{share}_s"] = t
                break
    # The rides: boarding (BOARDING -> TRANSIT) and the drive (TRANSIT -> DISMOUNT), per ride; why the failed ones failed.
    state, since, board, drive, why = {}, {}, [], [], {}
    seen = set()
    for l in lines:
        if "VEHICLE_STATE_CHANGED" not in l or "faction=US " not in l:
            continue
        t = re.search(r"t_ms=(\d+)", l)
        s = re.search(r" slot=(\w+)", l)
        st = re.search(r"new_state=(\w+)|state=(\w+)", l)
        if not (t and s and st):
            continue
        key = (t.group(1), s.group(1))
        if key in seen:
            continue
        seen.add(key)
        slot, now, new = s.group(1), int(t.group(1)) / 1000, st.group(1) or st.group(2)
        old = state.get(slot)
        if new == "TRANSIT" and old == "BOARDING":
            board.append(now - since[slot])
        if new == "DISMOUNT" and old == "TRANSIT":
            drive.append(now - since[slot])
        if new == "FALLBACK" and old != "DISMOUNT":
            r = re.search(r"reason=(\w+)", l)
            why[r.group(1) if r else "?"] = why.get(r.group(1) if r else "?", 0) + 1
        state[slot], since[slot] = new, now
    out["board_s"] = round(statistics.median(board)) if board else -1
    out["drive_s"] = round(statistics.median(drive)) if drive else -1
    out["fail_reasons"] = ", ".join(f"{k} {v}" for k, v in sorted(why.items(), key=lambda kv: -kv[1]))
    cars, spawned = {}, set()
    for l in lines:
        if "VEHICLE_SPAWNED]" in l and "faction=US " in l:
            m = re.search(r"prefab=\{[0-9A-F]+\}Prefabs/Vehicles/\w+/\w+/(\w+)\.et", l)
            k = (re.search(r"t_ms=(\d+)", l) or [None, None])[1], (re.search(r" slot=(\w+)", l) or [None, None])[1]
            if m and k not in spawned:   # lines often come twice
                spawned.add(k)
                cars[m.group(1)] = cars.get(m.group(1), 0) + 1
    out["vehicles"] = ", ".join(f"{k} {v}" for k, v in sorted(cars.items()))
    out["unjams"] = len({l.split("SCRIPT", 1)[-1] for l in lines if "[ZCR][UNJAM]" in l and "side=US " in l and "action=" in l})
    out["stuck"] = len({l.split("SCRIPT", 1)[-1] for l in lines if "[ZCR][MOVEFAIL]" in l and "side=US " in l})
    out["enemy_soldiers"] = len({re.search(r" id=(\d+)", l).group(1) for l in lines if "[ZCR][LIVE]" in l and "side=USSR " in l and "kind=team" in l and re.search(r" id=(\d+)", l)})
    return out


def _objective(run_dir: Path, lines: list):
    """The point's place: the US plan line names its base id, the strategist's snapshot gives where it is."""
    obj_id = None
    for l in lines:
        m = re.search(r"\[ZCR\]\[PLAN\].*faction=US .*Assault test: everything at .+? \(base (\d+)\)", l)
        if m:
            obj_id = int(m.group(1))
            break
    snap = run_dir / "profile" / "zcr" / "snapshots.jsonl"
    if obj_id is None or not snap.exists():
        return None
    for s in snap.read_text(encoding="utf-8", errors="replace").splitlines()[:4]:
        try:
            b = next((b for b in json.loads(s).get("bases", []) if b.get("id") == obj_id), None)
        except ValueError:
            continue
        if b:
            return b["x"], b["z"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="rides", choices=list(VARIANTS))
    ap.add_argument("--minutes", type=float, default=12)
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
