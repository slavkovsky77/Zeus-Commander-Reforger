"""The whole-map battle (6 Nov night - Martin: "test battle on everon or arland with not fixed battle point (farm, that city
on b) like we would actually fight for whole map"): the watched battle's setup (assaulttest town-watch) without the one-point
binding - every base is a target, our rules general (the doctrine bridge) plans for both sides, AI Conflict raises, moves and
supplies the armies, drones on, 40 tickets a side.

    python lab/maptest.py --map arland --minutes 60                 # headless (port 2148), the summary at the end
    python lab/maptest.py --map arland --minutes 60 --watch         # the game window, PANORAMA over the map
    python lab/maptest.py --summary RUN_DIR                         # a finished run's summary

Summary: captures (time, base, from -> to), bases each side took, soldiers lost a side, drone launches and kills, script
errors of ours, crashed (the server gone before the end), minutes played. Results in .runtime/maptest/results.jsonl.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import assaulttest  # noqa: E402

OUT = ROOT / ".runtime" / "maptest"
# town-watch's settings without what ties the battle to one point: -zcrOnePoint (added per scenario there), the main-effort
# binding to the point general's plan, the stored attack plans, Gemini, Farm handed to the Soviets.
ONE_POINT = ("-zcrBindMainEffort", "-zcrAttackPlan", "-zcrNoAttackHold", "-zcrLivePlan")
VARIANTS = {
    "doctrine": ("doctrine", "our rules general (the doctrine bridge) for both sides, every base a target"),
    "aicf": ("none", "AI Conflict's own commanders alone, every base a target (what a scenario with no helper program gets)"),
}


def extra() -> str:
    words = assaulttest.VARIANTS["town-watch"][0].replace("-zcrBaseTo Farm:USSR", "").split()
    words = [w for w in words if w not in ONE_POINT]
    return " ".join(words) + " -aicfInitialTickets 40"


def run(map_name: str, variant: str, minutes: float, port: int, watch: bool = False, speed: float = 1, pano: str = "") -> dict:
    strategist, _ = VARIANTS[variant]
    if strategist != "none":
        import bridges
        bridges.ensure((strategist,))
    label = f"maptest-{map_name}-{variant}" + ("-watch" if watch else f"-p{port}")
    more = extra() + f" -zcrTestTitle Whole_map_{map_name}"
    argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", map_name, "--minutes", str(round(minutes / speed, 2) if watch else minutes),
            "--label", label, "--port", str(port), "--us", strategist, "--ussr", strategist, "--drones", "--mods", assaulttest.MODS,
            "--plan-seconds", "60"]
    if watch:
        more += f" -zcrSpeed {speed:g}" + (f" -zcrPano {pano}" if pano else "")
        argv += ["--solo", "--watch"]
    argv += ["--extra", more]
    started = datetime.now()
    subprocess.run(argv, cwd=str(ROOT), stdout=None if watch else subprocess.DEVNULL, stderr=None if watch else subprocess.DEVNULL,
                   creationflags=0 if watch else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"map": map_name, "variant": variant, "error": "no run folder"}
    out = summarize(runs[-1])
    out.update({"map": map_name, "variant": variant, "planned_minutes": minutes, "started": started.isoformat(timespec="seconds")})
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(out) + "\n")
    return out


CAPTURE = re.compile(r"\[ZCR\]\[CAPTURE\] t=(\d+) base=(.+?) from=(\S+) to=(\S+)")
ERR = re.compile(r"SCRIPT\s+\(E\)")


def summarize(run_dir: Path) -> dict:
    out = {"run": run_dir.name, "run_path": str(run_dir)}
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        out["error"] = "no log"
        return out
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    caps = []
    for l in lines:
        m = CAPTURE.search(l)
        if m:
            caps.append({"t": int(m.group(1)), "base": m.group(2), "from": m.group(3), "to": m.group(4)})
    out["captures"] = caps
    out["captures_n"] = len(caps)
    out["took"] = {s: sorted({c["base"] for c in caps if c["to"] == s}) for s in ("US", "USSR")}
    # Script errors of ours: a VM exception whose stack runs through our scripts (ZCR, the AI Conflict fork, FPV AI Drones);
    # AI Conflict's own ERROR reports ([AICF]...[ERROR]) and the game's / DCO's exceptions counted apart.
    ours = other = reports = 0
    for i, l in enumerate(lines):
        if not ERR.search(l):
            continue
        if "[AICF]" in l:
            reports += 1
            continue
        stack = " ".join(lines[i:i + 14])
        if re.search(r"scripts/Game/(ZeusCommanderReforger|ZCR_|AIConflict|FPVAI)", stack):
            ours += 1
        else:
            other += 1
    out["script_errors"] = ours
    out["other_errors"] = other
    out["aicf_reports"] = reports
    m = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8")) if (run_dir / "metrics.json").exists() else {}
    out["minutes"] = m.get("minutes")
    lost = m.get("lost") or {}
    out["us_lost"], out["ussr_lost"] = lost.get("US"), lost.get("USSR")
    out["drone_kills"] = m.get("drone_kills")
    out["drone_strikes"] = m.get("drone_strikes")
    out["drone_teams_sent"] = sum(1 for l in lines if "[ZCR][DRONES]" in l and "kind=" in l and "team=" in l)   # as lab/scorecard.py
    # Crashed: the server stopped writing well before the planned end (no metrics minutes near the plan) or a crash dump.
    out["crashed"] = bool(list(run_dir.glob("**/*.dmp"))) or any("Application crashed" in l or ("CRASH" in l and "[ZCR]" not in l) for l in lines[-200:])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default="arland", choices=["arland", "everon"])
    ap.add_argument("--variant", default="doctrine", choices=sorted(VARIANTS))
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--port", type=int, default=2148)
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--speed", type=float, default=1)
    ap.add_argument("--pano", default="", help="with --watch: -zcrPano x,z[,r,h[,rate]]")
    ap.add_argument("--summary", default="", help="a finished run folder: print its summary")
    a = ap.parse_args()
    if a.summary:
        print(json.dumps(summarize(Path(a.summary)), indent=1))
        return 0
    print(json.dumps(run(a.map, a.variant, a.minutes, a.port, a.watch, a.speed, a.pano), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
