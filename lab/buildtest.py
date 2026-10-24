"""The base-building sub-lab (25 Oct, Martin: "before the real match let's test building of the base by the infantry guys";
"let's make a sub-lab for that, I want to test it and look at it"). AI Conflict runs on Arland as in a match but without
squads (each side capped at 1 soldier - only its builders and supply trucks come out), each side gets the given bases
(ZCR_BuildTest, -zcrBuildTest) and every base it holds is kept at a full supply store - so only the building is
tested: where AI Conflict's planner puts each building, whether it is on or next to a road, and how the base's builder (one
soldier) walks there and builds it. The camera follows the builders.

    python lab/buildtest.py near2                          # each side its 2 bases nearest its HQ, 12 game minutes
    python lab/buildtest.py near2 --variant noaccess       # without our depot access check (AI Conflict's own placement)
    python lab/buildtest.py farm --minutes 15 --watch      # in the game window (lab/watch_test.py records it)

Prints one line: buildings decided / placed / built (by kind), searches given up, builders, their walk and build
times, work blocked, failed moves, buildings on a road or right beside one, depot sites refused by the access check.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# scenario: (map, -zcrBuildTest spec)
SCENARIOS = {
    "near2": ("arland", "US=2;USSR=2"),
    "near4": ("arland", "US=4;USSR=4"),
    "hq": ("arland", "US=0;USSR=0"),
    # The Farm (fenced paddocks, stone walls - the supply vans' trap, notes 382-388) and Beauregard, to the US.
    "farm": ("arland", "US=2209,2909|3297,2860;USSR=1"),
}
SCENARIO_WORDS = {
    "near2": "each side holds its HQ and its 2 bases nearest to it, every store kept full - the builders build all they can",
    "near4": "each side holds its HQ and its 4 bases nearest to it - more builders at once",
    "hq": "each side holds only its HQ - its builder alone",
    "farm": "the US gets the Farm (fenced paddocks and stone walls) and Beauregard; the Soviets their nearest base",
}

VARIANTS = {
    # name: (extra server parameters, words)
    "default": ("", "AI Conflict's builders with our changes (depot access check, depot first, fortifications)"),
    "noaccess": ("-aicfDepotNoAccess", "without our depot access check - AI Conflict's own depot placement"),
    "nofort": ("-aicfFortificationsPerBase 0", "no fortifications - only the buildings a base needs"),
}

BASE = "-zcrNoFIA -zcrLabWeather -zcrNoArmour -zcrArmourVanilla -aicfMaxAgentsPerFaction 1 -aicfMaxBuildersPerFaction 6"


def _title(scenario: str, variant: str) -> str:
    sys.path.insert(0, str(ROOT / "lab"))
    import sublab
    return sublab.title("building", scenario, variant)


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False, speed: float = 3) -> dict:
    map_name, spec = SCENARIOS[scenario]
    extra = VARIANTS[variant][0]
    label = f"buildtest-{scenario}-{variant}-p{port}" if not watch else f"buildtest-{scenario}-{variant}-watch"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", map_name, "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "none", "--ussr", "none",
            "--extra", f"{BASE} -zcrTestTitle {_title(scenario, variant)} -zcrBuildTest {spec} {extra}".strip()]
    if watch:
        argv += ["--watch", "--solo"]
        if speed > 1:
            argv[argv.index("--extra") + 1] += f" -zcrSpeed {speed:g}"
            argv[argv.index("--minutes") + 1] = str(round(minutes / speed, 2))
    subprocess.run(argv, cwd=str(ROOT), stdout=None if watch else subprocess.DEVNULL, stderr=None if watch else subprocess.DEVNULL,
                   creationflags=0 if watch else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


EVENT = re.compile(r"\[AICF\]\[STAGE\d\]\[\w+\]\[(\w+)\] (.*)")
FIELD = re.compile(r"(\w+)=(<[^>]*>|\S+)")


def _roads(slug: str = "arland"):
    f = ROOT / ".runtime" / "maps" / slug / "map_roads.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def road_gap(x: float, z: float, roads, near: float = 60) -> float:
    """Metres from (x, z) to the nearest road's edge (negative: on the road)."""
    best = 1e9
    for r in roads:
        p, half = r["p"], r.get("w", 4) / 2
        for (ax, az), (bx, bz) in zip(p, p[1:]):
            if near and (min(ax, bx) - near > x or max(ax, bx) + near < x or min(az, bz) - near > z or max(az, bz) + near < z):
                continue
            dx, dz = bx - ax, bz - az
            L = dx * dx + dz * dz
            t = 0 if L == 0 else max(0, min(1, ((x - ax) * dx + (z - az) * dz) / L))
            best = min(best, math.hypot(x - (ax + t * dx), z - (az + t * dz)) - half)
    if best > 1e8 and near:
        return road_gap(x, z, roads, 0)   # no road segment near: the whole network
    return best


def _median(v):
    v = sorted(v)
    return round(v[len(v) // 2]) if v else None


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    out = {"scenario": scenario, "variant": variant}
    if not log:
        out["error"] = "no log"
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    ev = []
    for line in text.splitlines():
        m = EVENT.search(line)
        if m:
            ev.append((m.group(1), dict(FIELD.findall(m.group(2)))))
    by = lambda name: [f for e, f in ev if e == name]
    def pos(f, key="position"):
        v = f.get(key, "")
        if not v.startswith("<"):
            return None
        x, _, z = (float(a) for a in v.strip("<>").split(","))
        return x, z
    decided = {f["token"]: f for f in by("CONSTRUCTION_DECISION") if "token" in f}
    placed = {f["token"]: f for f in by("CONSTRUCTION_PLACED") if "token" in f}
    done = {f["token"]: f for f in by("CONSTRUCTION_COMPLETED") if "token" in f}
    cancelled = by("CONSTRUCTION_CANCELLED")
    roads = _roads()
    sites, gaps = [], []
    for tok, f in placed.items():
        p = pos(f)
        if not p:
            continue
        gap = road_gap(p[0], p[1], roads) if roads else None
        if gap is not None:
            gaps.append(gap)
        sites.append(f"{f.get('faction')}:{f.get('type', '').lower()}@{round(p[0])},{round(p[1])}:{'built' if tok in done else 'open'}:road{round(gap) if gap is not None else '?'}m")
    kinds = {}
    for f in placed.values():
        k = f.get("type", "?").lower()
        kinds[k] = kinds.get(k, 0) + 1
    search_s = [(int(placed[t]["t_ms"]) - int(decided[t]["t_ms"])) / 1000 for t in placed if t in decided]
    build_s = [(int(done[t]["t_ms"]) - int(placed[t]["t_ms"])) / 1000 for t in done if t in placed]
    # A builder's walk: target assigned -> first work started, per group and target.
    assigned, walk_s = {}, []
    for e, f in ev:
        key = (f.get("group"), f.get("target"))
        if e == "BUILDER_TARGET_ASSIGNED":
            assigned[key] = int(f.get("t_ms", 0))
        elif e == "BUILDER_WORK_STARTED" and key in assigned:
            walk_s.append((int(f["t_ms"]) - assigned.pop(key)) / 1000)
    blocked = {}
    for f in by("BUILDER_WORK_BLOCKED"):
        blocked[f.get("reason", "?")] = blocked.get(f.get("reason", "?"), 0) + 1
    why_cancel = {}
    for f in cancelled:
        r = f.get("reason", "?")
        why_cancel[r] = why_cancel.get(r, 0) + 1
    out.update({
        "given": len(re.findall(r"\[ZCR\]\[BUILDTEST\] .*event=GIVE", text)),
        "decided": len(decided), "placed": len(placed), "built": len(done),
        "open": len([t for t in placed if t not in done]),
        "kinds": ",".join(f"{k}:{v}" for k, v in sorted(kinds.items())),
        "gave_up": len(cancelled), "gave_up_why": ",".join(f"{k}:{v}" for k, v in sorted(why_cancel.items())),
        "builders": len(by("BUILDER_SPAWN_REQUESTED")),
        "search_s": _median(search_s), "walk_s": _median(walk_s), "build_s": _median(build_s),
        "blocked": sum(blocked.values()), "blocked_why": ",".join(f"{k}:{v}" for k, v in sorted(blocked.items())),
        "move_fails": len(by("BUILDER_MOVE_FAILED")), "return_blocked": len(by("BUILDER_RETURN_BLOCKED")),
        # The log gives a building's centre, not its footprint (a small slot is ~12 m across): on a road = the centre
        # under 2 m from the road's edge; by a road = 2-8 m (its footprint likely touches the road).
        "on_road": len([g for g in gaps if g < 2]), "by_road": len([g for g in gaps if 2 <= g < 8]),
        "road_gap_m": _median(gaps),
        # AI Conflict's supply cache at each base (BASE_STORAGE_PLACED, placed at the start - not by the builders): under 6 m from a road edge (its corner on the road).
        "cache_road": len([1 for x, z in re.findall(r"BASE_STORAGE_PLACED\] .* x=(-?\d+) z=(-?\d+)", text) if roads and road_gap(float(x), float(z), roads) < 5.6]),
        "caches": len(re.findall(r"BASE_STORAGE_PLACED\]", text)),
        "no_access": len(re.findall(r"DEPOT_NO_ROAD_ACCESS", text)),
        "sites": " ".join(sites),
        "script_errors": len([l for l in text.splitlines() if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l]),
        "crashed": bool(list(log.parent.glob("*.mdmp"))), "run": run_dir.name, "run_path": str(run_dir),
    })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="+", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="default", choices=sorted(VARIANTS))
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--port", type=int, default=2148)
    ap.add_argument("--speed", type=float, default=3, help="with --watch: the game's time multiplier (default 3x)")
    ap.add_argument("--watch", action="store_true", help="in the game window (only when nobody else uses the game)")
    a = ap.parse_args()
    for s in a.scenarios:
        r = run(s, a.variant, a.minutes, 0, a.port, a.watch, a.speed)
        print(" ".join(f"{k}={v}" for k, v in r.items()), flush=True)


if __name__ == "__main__":
    main()
