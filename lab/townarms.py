"""The night A/B of the battle for Beauregard by arm (5 Nov night - the subagent's two bets for why the attack stalls 150-300 m
out and fades with time: the storm leg's priority, the side cap), pooled over builds: one line per arm, and the curves of men
near the point per game minute (Martin reads curves, not tables).

    python lab/townarms.py [--since 20261105-0100] [--png out.png] [--json out.json]

An arm: a town variant of lab/assaulttest.py (town-brains, town-storm60, town-cap70, town-storm60-cap70, town-cleanup,
town-nodoor), headless battles of 25+ game minutes only.
"""
import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import towntime  # noqa: E402

R76_FROM = "20261105-071500"
WORDS = {"town-brains": "as it was (town-brains to 07:15)", "town-brains-r76": "town-brains from 07:15 (storm 60 + cleanup)", "town-storm60": "storm priority 60", "town-cap70": "side cap 70",
         "town-storm60-cap70": "storm 60 + cap 70", "town-cleanup": "drone stations cleaned up", "town-nodoor": "no door reaction",
         "town-storm60-cleanup": "storm 60 + stations cleaned up"}


def battles(since: str) -> list:
    out = []
    for run in towntime.town_runs(since):
        b = towntime.parse(run)
        if b.get("error") or b.get("watched") or b.get("last_min", 0) < 25 or b["variant"] not in WORDS:
            continue
        # town-brains itself runs with the storm at 60 and the stations cleaned up from 5 Nov 07:15 (lab/assaulttest.py)
        if b["variant"] == "town-brains" and run.name[-15:] >= R76_FROM:
            b["variant"] = "town-brains-r76"
        out.append(b)
    return out


def mean_of(b: dict, key: str, lo: int, hi: int):
    v = [b["minutes"][m].get(key, 0) for m in b["minutes"] if lo <= m <= hi]
    return sum(v) / len(v) if v else None


def arms(bs: list) -> dict:
    by = defaultdict(list)
    for b in bs:
        by[b["variant"]].append(b)
    rows = {}
    for v, group in by.items():
        caps = [b["first_cap_s"] / 60 for b in group if b.get("first_cap_s") is not None]
        rows[v] = {"words": WORDS[v], "battles": len(group), "taken": len(caps),
                   "taken_by_16": sum(1 for c in caps if c <= 16),
                   "capture_min_median": round(st.median(caps), 1) if caps else None,
                   "a150": round(st.mean(mean_of(b, "att150", 8, 30) or 0 for b in group), 1),
                   "a60": round(st.mean(mean_of(b, "att60", 8, 30) or 0 for b in group), 1),
                   "a300": round(st.mean(mean_of(b, "att300", 8, 15) or 0 for b in group), 1),
                   "lost_30": round(st.mean(b["minutes"].get(29, b["minutes"].get(max(b["minutes"]), {})).get("lost", 0) for b in group)),
                   "ai_agents_30": round(st.mean(b["minutes"].get(29, {}).get("ai", 0) or 0 for b in group)),
                   "runs": [b["run"] for b in group]}
        curve = []
        for m in range(0, 31):
            vals = [b["minutes"][m].get("att150", 0) for b in group if m in b["minutes"]]
            curve.append(round(sum(vals) / len(vals), 2) if vals else None)
        rows[v]["a150_by_minute"] = curve
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="20261105-0100", help="battles started at or after this (YYYYMMDD-HHMM)")
    ap.add_argument("--json", default="")
    ap.add_argument("--png", default="")
    a = ap.parse_args()
    rows = arms(battles(a.since))
    for v, r in sorted(rows.items(), key=lambda x: -x[1]["a150"]):
        print(f"{r['words']:26} {r['battles']} battles, taken {r['taken']} ({r['taken_by_16']} by min 16, median {r['capture_min_median']} min) | "
              f"men within 300 m min 8-15 {r['a300']}, within 150 m min 8-30 {r['a150']}, within 60 m {r['a60']} | lost by min 30 {r['lost_30']}"
              f" | AI agents at 30 {r['ai_agents_30']}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for v, r in sorted(rows.items()):
            ax.plot(range(31), [x if x is not None else float("nan") for x in r["a150_by_minute"]], lw=2,
                    label=f"{r['words']} ({r['battles']})")
        ax.set_xlabel("game minute")
        ax.set_ylabel("attackers within 150 m of the point")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(a.png, dpi=110)
    return 0


if __name__ == "__main__":
    sys.exit(main())
