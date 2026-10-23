"""The infantry tests (23 Oct evening, Martin: "maybe I would like to move to DCO - some infantry tests that I would like
to watch"; "I can imagine these as small sub-lab integration tests"; review note 343). Rifle squads only, on real
ground of Arland (picked with -zcrCoverScan: buildings, trees and walls around every 100-m point of the island), played by
the guns test (ZCR_GunTest.c, -zcrGunTest) with the soldier sampler on - the same cover, stance and death measures as the
matches. The runner of the sub-lab "infantry" (lab/sublabs/infantry.toml):

    python lab/inftest.py storm-foot --variant dco --minutes 12
    python lab/inftest.py storm-foot --variant game --watch      # in the game window (only when the game is free)
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
import guntest  # noqa: E402

DCO = "5EDAAE0D3CC60D6B"   # DCO_AI Reforger (Workshop, APL-ND: loaded, never copied)

SCENARIOS = {
    # name: (US side, USSR side) - groups kind:count:x,z[:role] joined by + (ZCR_GunTest.c)
    # Storm on foot: a US rifle squad attacks Moss Hill farm on its hilltop (19 buildings, 57 walls within 40 m, 89 m
    # high), held by a Soviet rifle squad; the US start 450 m south at the foot of the hill (23 m): open ground first,
    # woods in the middle, ~100 m of open slope up to the farm.
    "storm-foot": ("squad:1:2270,788:attack", "squad:1:2270,1238:defend"),
}
SCENARIO_WORDS = {
    "storm-foot": "a US rifle squad (9 men) attacks a Soviet rifle squad (6 men) holding Moss Hill farm on its hilltop, 450 m away: "
                  "open ground, woods, then an open slope up to the farm",
}
VARIANTS = {
    # name: (extra command line, Workshop mods, words)
    "game": ("", "", "the game's own soldier AI (our mod loaded, it only measures)"),
    "dco": ("", DCO, "the DCO_AI Reforger mod (Workshop) on both squads"),
}


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False) -> dict:
    us, ussr = SCENARIOS[scenario]
    extra, mods, _ = VARIANTS[variant]
    label = f"inftest-{scenario}-{variant}-p{port}" if not watch else f"inftest-{scenario}-{variant}-watch"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland-test", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "none", "--ussr", "none",
            "--extra", f"-aicfOff -zcrLabWeather -zcrNoFIA -zcrArmourVanilla -zcrNoArmour -zcrGunTest {us};{ussr} {extra}".strip()]
    if mods:
        argv += ["--mods", mods]
    if watch:
        argv += ["--watch", "--solo"]
    subprocess.run(argv, cwd=str(ROOT), stdout=None if watch else subprocess.DEVNULL, stderr=None if watch else subprocess.DEVNULL,
                   creationflags=0 if watch else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    out = guntest.summarize(run_dir, scenario, variant)
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    kv = lambda line: dict(re.findall(r"(\w+)=(-?[\w.]+)", line))
    # In cover while fighting: the sampler's 30-s lines, weighted by how many knew an enemy within 300 m.
    cover = {}
    for side in ("US", "USSR"):
        rows = [kv(l) for l in text.splitlines() if "[ZCR][EXPOSURE]" in l and f"side={side} " in l]
        eng = sum(int(r.get("engaged", 0)) for r in rows)
        cover[side] = {k: round(sum(int(r.get("engaged", 0)) * int(r.get(k, 0)) for r in rows) / eng) if eng else None
                       for k in ("covered", "prone", "incover")}
    deaths = [kv(l) for l in text.splitlines() if "[ZCR][LOSS]" in l and "relation=KILLED_BY_ENEMY" in l]
    stood = [d for d in deaths if d.get("stance") == "STAND"]
    open_ = [d for d in deaths if d.get("covered") == "false"]
    dist = [int(d["distance"]) for d in deaths if d.get("distance", "").isdigit()]
    first = min((int(d["t"]) for d in deaths if d.get("t", "").isdigit()), default=0)
    # Losses from the head count of the first summary (a US rifle squad is 9 men, a Soviet one 6).
    sums = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST_SUM]" in l]
    men = lambda row, side: int(row.get(f"{side}_men", 0) or 0)
    start = {s: max((men(r, s) for r in sums[:2]), default=0) for s in ("us", "ussr")}
    lost = {s: max(0, start[s] - men(sums[-1], s)) if sums else None for s in ("us", "ussr")}
    out.update({
        "us_men": start["us"], "ussr_men": start["ussr"], "us_lost": lost["us"], "ussr_lost": lost["ussr"],
        "taken_s": out.get("taken_us_s", 0),
        "us_cover": cover["US"]["covered"], "ussr_cover": cover["USSR"]["covered"],
        "us_prone": cover["US"]["prone"], "ussr_prone": cover["USSR"]["prone"],
        "us_incover": cover["US"]["incover"], "ussr_incover": cover["USSR"]["incover"],
        "deaths": len(deaths), "died_standing_pct": round(100 * len(stood) / len(deaths)) if deaths else None,
        "died_open_pct": round(100 * len(open_) / len(deaths)) if deaths else None,
        "fight_m": round(statistics.median(dist)) if dist else None, "first_loss_s": first,
        "dco_loaded": DCO in (run_dir / "run.json").read_text(encoding="utf-8") if (run_dir / "run.json").exists() else None,
    })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="+", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="game", choices=sorted(VARIANTS))
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--port", type=int, default=2170)
    ap.add_argument("--watch", action="store_true", help="in the game window (the game hosts it; only when nobody else uses the game)")
    a = ap.parse_args()
    for s in a.scenarios:
        print(json.dumps(run(s, a.variant, a.minutes, 0, a.port, a.watch)), flush=True)


if __name__ == "__main__":
    main()
