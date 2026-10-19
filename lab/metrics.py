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


def fields(line: str, tag: str) -> dict:
    return dict(KV.findall(line.split(tag, 1)[1]))


def measure(lines) -> dict:
    lost = defaultdict(Counter)        # side -> {"man": n, "vehicle": n}
    by = defaultdict(Counter)          # side -> {killer kind: n}
    friendly = 0
    captures = Counter()
    plans = Counter()
    misses = 0
    snapshots = 0
    t_end = 0
    score = {}
    for line in lines:
        if "[ZCR][LOSS]" in line:
            f = fields(line, "[ZCR][LOSS]")
            lost[f.get("side", "?")][f.get("kind", "?")] += 1
            by[f.get("side", "?")][f.get("killer_kind", "none")] += 1
            if "FRIENDLY" in f.get("relation", ""):
                friendly += 1
            t_end = max(t_end, int(f.get("t", 0) or 0))
        elif "BASE_OWNER_CHANGED]" in line:
            f = fields(line, "BASE_OWNER_CHANGED]")
            if f.get("new_owner"):
                captures[f["new_owner"]] += 1
        elif "[ZCR][PLAN]" in line:
            plans[fields(line, "[ZCR][PLAN]").get("source", "?")] += 1
        elif "[ZCR][BRIDGE_MISS]" in line:
            misses += 1
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
        "score": score,   # bases held at the last round: US, USSR, FIA, objectives
    }


def main() -> int:
    path = Path(sys.argv[1])
    print(json.dumps(measure(path.read_text(encoding="utf-8", errors="replace").splitlines()), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
