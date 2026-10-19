"""What a match did, read back from the server log - the Reforger lab's measurements.

    python lab/metrics.py <profile>/logs/<run>/console.log

From our lines ([ZCR][LOSS], [ZCR][PLAN], [ZCR][SNAPSHOT], [ZCR][BRIDGE_MISS]) and AI Conflict's
(BASE_OWNER_CHANGED): soldiers and vehicles lost per side and by what, captures per side, plan
changes and where they came from (doctrine, llm, fallback), bridge misses, match length.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

KV = re.compile(r"(\w+)=(\S*)")
CLOCK = re.compile(r"^\s*(\d{1,2}):(\d\d):(\d\d)(?:\.(\d+))?")


def clock(line: str):
    m = CLOCK.match(line)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + float("0." + (m.group(4) or "0"))


def fields(line: str, tag: str) -> dict:
    return dict(KV.findall(line.split(tag, 1)[1]))


def measure(lines) -> dict:
    lines = list(lines)
    # FPV detonations (Martin's FPV AI Drones logs each): a death with no killer within 5 s after
    # one is the drone's - Reforger gives a drone kill no instigator.
    detonations = [c for c in (clock(l) for l in lines if "FPVAI: drone" in l and " detonated" in l) if c is not None]
    lost = defaultdict(Counter)        # side -> {"man": n, "vehicle": n}
    by = defaultdict(Counter)          # side -> {killer kind: n}
    friendly = 0
    captures = Counter()
    no_fia_split = False
    plans = Counter()
    misses = 0
    snapshots = 0
    t_end = 0
    score = {}
    drone_kills = Counter()            # side whose soldier an FPV drone killed
    drone_teams = Counter()
    for line in lines:
        if "[ZCR][LOSS]" in line:
            f = fields(line, "[ZCR][LOSS]")
            lost[f.get("side", "?")][f.get("kind", "?")] += 1
            by[f.get("side", "?")][f.get("killer_kind", "none")] += 1
            if "FRIENDLY" in f.get("relation", ""):
                friendly += 1
            t = clock(line)
            no_killer = f.get("killer_kind", "none") == "none"
            if any(k in f.get("killer", "").lower() for k in ("fpv", "drone")) or (
                    no_killer and t is not None and any(0 <= t - d <= 5 for d in detonations)):
                drone_kills[f.get("side", "?")] += 1
            t_end = max(t_end, int(f.get("t", 0) or 0))
        elif "BASE_OWNER_CHANGED]" in line:
            f = fields(line, "BASE_OWNER_CHANGED]")
            # Not the two-army scenario's split at the start (-zcrNoFIA hands FIA's bases out at t=15).
            if f.get("new_owner") and not (f.get("old_owner") == "FIA" and no_fia_split):
                captures[f["new_owner"]] += 1
        elif "CLI Params:" in line and "-zcrNoFIA" in line:
            no_fia_split = True
        elif "[ZCR][PLAN]" in line:
            plans[fields(line, "[ZCR][PLAN]").get("source", "?")] += 1
        elif "[ZCR][BRIDGE_MISS]" in line:
            misses += 1
        elif "[ZCR][DRONES]" in line and " team=" in line:
            drone_teams[fields(line, "[ZCR][DRONES]").get("side", "?")] += 1
        elif "[ZCR][SCORE]" in line:
            f = fields(line, "[ZCR][SCORE]")
            score = {k: int(v) for k, v in f.items() if v.lstrip("-").isdigit()}
            t_end = max(t_end, score.get("t", 0))
        elif "[ZCR][SNAPSHOT]" in line:
            snapshots += 1
            t_end = max(t_end, int(fields(line, "[ZCR][SNAPSHOT]").get("t", 0) or 0))
    return {
        "minutes": round(t_end / 60, 1),
        "lost": {s: dict(c) for s, c in lost.items()},
        "lost_to": {s: dict(c) for s, c in by.items()},
        "friendly_fire": friendly,
        "captures": dict(captures),
        "plans": dict(plans),
        "bridge_misses": misses,
        "snapshots": snapshots,
        "drone_teams": dict(drone_teams),
        "drone_kills": dict(drone_kills),   # by the side that lost the soldier
        "drone_strikes": len(detonations),
        "score": score,   # bases held at the last round: US, USSR, FIA, objectives
    }


def main() -> int:
    path = Path(sys.argv[1])
    print(json.dumps(measure(path.read_text(encoding="utf-8", errors="replace").splitlines()), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
