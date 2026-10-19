"""Compare probe matches on one objective: when the strategist side stormed and took it, how close its
squads got over time, and what it cost.

    python lab/probe_report.py "Moss Hill" USSR .runtime/runs/probe-ab-p1000-* .runtime/runs/probe-ab-p25-*
"""
import glob
import json
import math
import re
import sys
from pathlib import Path


def log_of(run: Path):
    logs = sorted(run.glob("logs/*/console.log"))
    return logs[-1] if logs else None


def report(run: Path, base: str, side: str) -> dict:
    snaps = [json.loads(l) for l in (run / "profile" / "zcr" / "snapshots.jsonl").read_text(
        encoding="utf-8", errors="replace").splitlines() if l.strip()]
    mine = [r for r in snaps if r.get("faction") == side]
    b = next((x for x in mine[-1]["bases"] if x.get("name") == base), None) if mine else None
    out = {"run": run.name, "storm": None, "taken": None, "closest": [], "lost_near": {}, "lost": {}}
    if b is None:
        return out
    cx, cz = b.get("cx", b["x"]), b.get("cz", b["z"])
    for r in mine[::3]:
        d = [math.hypot(s["x"] - cx, s["z"] - cz) for s in r.get("squads", [])
             if "x" in s and s.get("target") == b["id"]]
        out["closest"].append((r["t"], round(min(d)) if d else None))
    log = log_of(run)
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if log else []:
        if "[ZCR][STORM]" in line and f"faction={side}" in line and f"base={base}" in line and out["storm"] is None:
            out["storm"] = int(re.search(r"t=(\d+)", line).group(1))
        elif "[ZCR][CAPTURE]" in line and f"base={base}" in line and f"to={side}" in line:
            out["taken"] = int(re.search(r"t=(\d+)", line).group(1))
        elif "[ZCR][LOSS]" in line:
            kv = dict(re.findall(r"(\w+)=(\S+)", line.split("[ZCR][LOSS]")[1]))
            who = kv.get("side", "?")
            out["lost"][who] = out["lost"].get(who, 0) + 1
            try:
                if math.hypot(float(kv["x"]) - cx, float(kv["z"]) - cz) < 500:
                    out["lost_near"][who] = out["lost_near"].get(who, 0) + 1
            except (KeyError, ValueError):
                pass
    return out


def main() -> int:
    base, side, pats = sys.argv[1], sys.argv[2], sys.argv[3:]
    for pat in pats:
        for run in sorted(glob.glob(pat)):
            r = report(Path(run), base, side)
            took = f"taken at {r['taken']} s" + (f", {r['taken'] - r['storm']} s after the storm" if r["taken"] and r["storm"] else "") if r["taken"] else "not taken"
            print(f"{r['run']}: storm at {r['storm']} s, {took}")
            print("  closest squad sent there (t, m):", " ".join(f"{t}:{d}" for t, d in r["closest"] if d is not None))
            print("  lost within 500 m:", r["lost_near"], " lost in the match:", r["lost"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
