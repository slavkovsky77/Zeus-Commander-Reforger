"""The Farm battle as an integration test (3 Nov, review notes 511/515 - Martin: "only one side can use it the other one
will not use it and we will compare"; and his way of reviewing: curves, not tables). Every Farm battle (lab/assaulttest.py
city: farm-gemini, farm-gemini-routes, farm-live, farm-now) gives one row per side: who commanded it (gemini - Gemini's
live plans, code - the code's own pick, rules - our rule commander) and from which HQ (harbour, 1.1 km from Farm; south,
2.1 km - the nearer HQ takes Farm more often, so the arms are compared per HQ). The rows go to the sub-lab "farm"
(lab/sublabs/farm.toml), whose page in the lab app shows each arm as its own curve.

    python lab/farmtest.py backfill            # every finished Farm battle not yet in the test
    python lab/sublab.py run farm --scenario gemini --variant harbour --repeat 2    # new battles (Gemini from the harbour)

Measures per side and battle (lab/livecompare.py side_rows): took_pct (100 if it took Farm), held_min (minutes it held
Farm), lost / killed (soldiers), at_obj_8 / at_obj_12 (its soldiers within 300 m of Farm at game minute 8 / 12),
route_legs_pct (its attack legs toward Farm that followed a planned route), expose_pct (its moving soldiers an enemy saw).
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import assaulttest  # noqa: E402
import livecompare  # noqa: E402
import sublab  # noqa: E402

VARIANTS = ("farm-gemini", "farm-gemini-routes", "farm-live", "farm-now")
SINCE = "20261102-1800"   # the capture fix (both sides can take Farm) went live 2 Nov 18:57; farm-now since 18:06


def arm_of(arm: str) -> str:
    if arm.startswith("gemini"):
        return "gemini"
    return arm if arm in ("code", "rules") else ""


def to_row(r: dict, run: Path) -> dict:
    m = re.search(r"-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}$", run.name)
    at = f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}" if m else ""
    return {"scenario": arm_of(r["arm"]), "variant": r["hq"], "side": r["side"], "setup": r["variant"], "arm_detail": r["arm"],
            "at": at, "took_pct": 100 if r.get("took") else 0, "took_s": r.get("took_s"),
            "held_min": round((r.get("held_s") or 0) / 60, 1), "lost": r.get("lost"), "killed": r.get("killed"),
            "at_obj_8": r.get("at_obj_8"), "at_obj_12": r.get("at_obj_12"), "route_legs_pct": r.get("route_legs_pct"),
            "expose_pct": r.get("expose_pct"), "minutes": r.get("minutes"), "script_errors": r.get("script_errors"),
            "model_calls": r.get("model_calls"), "rides_delivered": r.get("rides_delivered"), "rides_failed": r.get("rides_failed"),
            "rides_contact": r.get("rides_contact"), "run": run.name, "run_path": str(run)}


def recorded() -> set:
    return {(x.get("run"), x.get("side")) for x in sublab.rows("farm")}


def backfill(since: str = SINCE, min_minutes: float = 15) -> int:
    have, n = recorded(), 0
    runs = []
    for v in VARIANTS:
        for run in (ROOT / ".runtime" / "runs").glob(f"assault-city-{v}-p*"):
            m = re.search(r"-(\d{8}-\d{6})$", run.name)
            if m and m.group(1)[:13] >= since:
                runs.append((m.group(1), v, run))
    for _, v, run in sorted(runs):
        try:
            sides = livecompare.side_rows(run, v)
        except Exception as e:   # a run still going, or broken
            print(f"skip {run.name}: {e}")
            continue
        for r in sides:
            if (run.name, r["side"]) in have or r["minutes"] < min_minutes:
                continue
            row = to_row(r, run)
            if not row["scenario"]:
                continue
            sublab.record("farm", row)
            n += 1
    print(f"farm: {n} rows added")
    return n


def run(scenario: str, variant: str, minutes: float, units: int, port: int) -> dict:
    """One Farm battle: scenario = the arm to try (gemini: farm-gemini with Gemini on the side at HQ 'variant'; code:
    farm-live; rules: farm-now), variant = harbour / south. Returns that side's row; the other side's row is recorded too."""
    setup = {"gemini": "farm-gemini", "code": "farm-live", "rules": "farm-now"}[scenario]
    r = assaulttest.run("city", setup, minutes or 20, 0, port, live_side=variant)
    run_dir = Path(r.get("run_path") or "")
    rows = [to_row(x, run_dir) for x in livecompare.side_rows(run_dir, setup)] if run_dir.is_dir() else []
    mine = next((x for x in rows if x["variant"] == variant and (scenario == "rules" or x["scenario"] == scenario)), None)
    for x in rows:
        if x is not mine and x["scenario"]:
            sublab.record("farm", x)
    return mine or {"scenario": scenario, "variant": variant, "error": "no rows", "run": run_dir.name}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["backfill"])
    ap.add_argument("--since", default=SINCE)
    a = ap.parse_args()
    backfill(a.since)
    return 0


if __name__ == "__main__":
    sys.exit(main())
