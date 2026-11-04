"""The battle for Beauregard as an integration test (4 Nov night - Martin: "over night you can test both gemini vs gemini but
also gemini vs rule based"; results as curves, not tables). Every town battle (lab/assaulttest.py beauregard: town-brains -
Gemini commands both sides; town-vs-rules - Gemini one side, the code's rules the other, on the same live plans) gives one
row per side: who commanded it against whom (gemini-v-gemini, gemini-v-code, code-v-gemini) and from which HQ (harbour, the
side whose HQ is nearer Beauregard; south). The rows go to the sub-lab "town" (lab/sublabs/town.toml), whose page in the lab
app shows each arm as its own curve.

    python lab/towntest.py backfill                                   # every finished town battle not yet in the test
    python lab/sublab.py run town --scenario gemini-v-code --variant harbour --repeat 1    # a new battle

Measures per side and battle: took_pct (100 if it took Beauregard), took_s, held_min, lost / killed (soldiers), at_obj_8 /
at_obj_12 (its soldiers within 300 m at minute 8 / 12), drone_kills, forts_field (field fortifications it built where its
general wanted them - note 538), inside_pct (of its men at the point, the share inside a house - note 536), waits_ended
(teams its general kept waiting 4 minutes that the planner sent on), model_calls.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import assaulttest  # noqa: E402
import sublab  # noqa: E402

OBJECTIVE = "Beauregard"
VARIANTS = ("town-brains", "town-vs-rules")
SINCE = "20261104-0200"


def side_rows(run: Path, variant: str) -> list:
    s = assaulttest.summarize(run, "beauregard", variant)
    if s.get("error") or not s.get("minutes"):
        return []
    log = next(iter(sorted(run.glob("logs/*/console.log"))), None)
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log else []
    pickers, calls = {}, {"US": 0, "USSR": 0}
    lp = run / "profile" / "zcr" / "liveplan.jsonl"
    if lp.exists():
        for l in lp.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(l)
            except ValueError:
                continue
            if e.get("event") == "side":
                pickers[e["side"]] = e.get("picker")
            elif e.get("source") == "gemini" and e.get("side") in calls:
                calls[e["side"]] += 1
    caps = []
    forts = {"US": 0, "USSR": 0}
    inside = {"US": [0, 0], "USSR": [0, 0]}
    for l in lines:
        m = re.search(rf"\[ZCR\]\[CAPTURE\] t=(\d+) base={OBJECTIVE} from=(\w*) to=(\w+)", l)
        if m:
            caps.append((int(m.group(1)), m.group(3)))
        m = re.search(r"\[ZCR\]\[FORTPLAN\] event=placed .*side=(\w+) .*source=field", l)
        if m and m.group(1) in forts:
            forts[m.group(1)] += 1
        m = re.search(r"\[ZCR\]\[HOUSE\] t=\d+ spots=\d+ taken=\d+ us_core=(\d+) us_inside=(\d+) ussr_core=(\d+) ussr_inside=(\d+)", l)
        if m:
            inside["US"][0] += int(m.group(1))
            inside["US"][1] += int(m.group(2))
            inside["USSR"][0] += int(m.group(3))
            inside["USSR"][1] += int(m.group(4))
    waits = {"US": 0, "USSR": 0}
    pl = run / "profile" / "zcr" / "liveplan.log"
    if pl.exists():
        for l in pl.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r" (US|USSR) T\d+ waited \d+ s - goes on", l)
            if m:
                waits[m.group(1)] += 1
    end_t = int(round(s["minutes"] * 60))
    held = {"US": 0, "USSR": 0}
    owner, since = "FIA", 0
    for t, to in caps + [(end_t, None)]:
        if owner in held:
            held[owner] += max(0, t - since)
        owner, since = (to, t) if to else (owner, t)
    rows = []
    for side in ("US", "USSR"):
        k, other = side.lower(), ("USSR" if side == "US" else "US")
        arm = "gemini" if pickers.get(side) == "gemini" else ("code" if pickers.get(side) == "code" else "")
        opp = "gemini" if pickers.get(other) == "gemini" else ("code" if pickers.get(other) == "code" else "")
        if not arm or not opp:
            continue
        hq_m = s.get(f"{k}_hq_m")
        rows.append({"scenario": f"{arm}-v-{opp}", "variant": "harbour" if hq_m and hq_m < s.get(f"{other.lower()}_hq_m", 1e9) else "south",
                     "side": side, "setup": variant, "hq_m": hq_m, "took_pct": 100 if s.get(f"{k}_captured") else 0,
                     "took_s": s.get(f"{k}_capture_s"), "held_min": round(held[side] / 60, 1), "owner_end": owner,
                     "lost": s.get(f"{k}_lost"), "killed": s.get(f"{other.lower()}_lost"),
                     "at_obj_8": s.get(f"{k}_at_obj_8"), "at_obj_12": s.get(f"{k}_at_obj_12"),
                     "drone_kills": s.get(f"{k}_drone_kills"), "forts_field": forts[side],
                     "inside_pct": round(100 * inside[side][1] / inside[side][0]) if inside[side][0] else None,
                     "waits_ended": waits[side], "model_calls": calls[side], "minutes": s["minutes"],
                     "script_errors": s.get("script_errors"), "crashed": s.get("crashed"), "run": run.name, "run_path": str(run)})
    return rows


def at_of(run: Path) -> str:
    m = re.search(r"-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}$", run.name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}" if m else ""


def recorded() -> set:
    return {(x.get("run"), x.get("side")) for x in sublab.rows("town")}


def backfill(since: str = SINCE, min_minutes: float = 15) -> int:
    have, n = recorded(), 0
    runs = []
    for run in (ROOT / ".runtime" / "runs").glob("*beauregard-town-*"):
        m = re.search(r"-(\d{8}-\d{6})$", run.name)
        v = next((v for v in VARIANTS if f"-{v}-" in run.name), None)
        if m and v and m.group(1)[:13] >= since:
            runs.append((m.group(1), v, run))
    for _, v, run in sorted(runs):
        log = next(iter(sorted(run.glob("logs/*/console.log"))), None)
        if log and time.time() - log.stat().st_mtime < 180:
            print(f"skip {run.name}: still running")
            continue
        try:
            sides = side_rows(run, v)
        except Exception as e:   # a run still going, or broken
            print(f"skip {run.name}: {e}")
            continue
        for r in sides:
            if (run.name, r["side"]) in have or (r["minutes"] or 0) < min_minutes:
                continue
            r["at"] = at_of(run)
            r["watched"] = "-watch-" in run.name
            sublab.record("town", r)
            n += 1
    print(f"town: {n} rows added")
    return n


def run(scenario: str, variant: str, minutes: float, units: int, port: int) -> dict:
    """One town battle: scenario = gemini-v-gemini (town-brains) or gemini-v-code / code-v-gemini (town-vs-rules, Gemini
    on the side at HQ 'variant' for gemini-v-code, the code there for code-v-gemini). Returns that side's row; the other
    side's row is recorded too."""
    setup = "town-brains" if scenario == "gemini-v-gemini" else "town-vs-rules"
    other = "south" if variant == "harbour" else "harbour"
    live_side = variant if scenario != "code-v-gemini" else other
    r = assaulttest.run("beauregard", setup, minutes or 30, 0, port, live_side=live_side)
    run_dir = Path(r.get("run_path") or "")
    rows = side_rows(run_dir, setup) if run_dir.is_dir() else []
    for x in rows:
        x["at"] = at_of(run_dir)
        x["watched"] = False
    mine = next((x for x in rows if x["variant"] == variant and x["scenario"] == scenario), None)
    for x in rows:
        if x is not mine:
            sublab.record("town", x)
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
