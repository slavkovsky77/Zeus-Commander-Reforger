"""The driving night (22 Oct, Martin: "prepare a nightly plan for trying everything for improving driving - it's one last
chance; if it doesn't help I will probably drop vehicles"). Runs every driving option on the test tracks, picks the best
by a fixed rule, then plays it in watched matches - and writes a morning report.

    python lab/drivenight.py --plan            # print what would run, run nothing
    python lab/drivenight.py                   # the whole night: compile gate, track matrix, watched block
    python lab/drivenight.py --tracks-only     # the matrix without the watched block

Phase 0 - compile gate: one short headless run on the head-on track; any script error stops the night.
Phase 1 - track matrix (headless, two at a time on ports 2148 / 2150, idle priority): each track x variant twice,
          10 minutes each (see MATRIX). Results go to .runtime/drivenight/results.jsonl as they come.
Phase 2 - the winner: per track, variants ranked by the score below; the variant with the best average rank over the
          tracks it ran on wins (ties: fewer mods).
Phase 3 - watched block (unless --tracks-only): the watched loop for --watch-hours with the winner's settings,
          the same match settings as the 22 Oct afternoon baseline (armour off, no armed rides), so jams / long stops /
          collisions compare with it.
Report  - .runtime/drivenight/REPORT.md: the matrix table, the winner, the watched matches against the baseline, and
          the verdict by the rule in NIGHT.md (pass / fail -> plan B: fewer vehicles or none).

Score per run (higher is better): legs driven - 4 x lost cars - 3 x car-on-car hits - 1 x jams - 2 x (oldest open leg
over 300 s). Lost cars and crashes into each other weigh most: that's what Martin sees.
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import drivetest  # noqa: E402
import sublab  # noqa: E402

OUT = ROOT / ".runtime" / "drivenight"
MINUTES = 10
REPEATS = 2

# track: variants (each run REPEATS times)
MATRIX = {
    "headon": ["raw", "default", "nooncoming", "nospacing", "price", "crx", "jmvai", "best"],
    "mosshill-conflict": ["raw", "default", "price", "crx", "jmvai", "best"],
    "trucks": ["raw", "default", "competent", "price", "best"],
    "northfarm": ["raw", "default", "price", "best"],
    "everonexit": ["raw", "default", "price", "best"],
}

# The watched block's base settings: the 22 Oct afternoon baseline (15:00-18:20 and the push block 21:15-23:00).
WATCH_EXTRA = "-zcrNoFIA -zcrArmourVanilla -zcrNoArmour -zcrMoveTurrets -aicfNoHiddenSeat -aicfApcEvery 0 -aicfArmedRideEvery 0"


def score(r: dict) -> float:
    oldest = r.get("oldest_open_s") or 0
    return (r.get("legs") or 0) - 4 * (r.get("lost") or 0) - 3 * (r.get("car_hits") or 0) - (r.get("jams") or 0) - (2 if oldest > 300 else 0)


def plan() -> list:
    runs = []
    for track, variants in MATRIX.items():
        for variant in variants:
            for rep in range(REPEATS):
                runs.append((track, variant, rep))
    return runs


def log(msg: str) -> None:
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "night.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def compile_gate() -> bool:
    r = drivetest.run("headon", "default", 1.5, 2, 2152)
    ok = r.get("script_errors") == 0 and not r.get("crashed") and r.get("spawned", 0) > 0
    log(f"compile gate: {'OK' if ok else 'FAILED'} {r}")
    return ok


def track_matrix(runs: list) -> list:
    results = []
    done = OUT / "results.jsonl"
    if done.exists():
        results = [json.loads(l) for l in done.read_text(encoding="utf-8").splitlines() if l.strip()]
    have = {(r["track"], r["variant"], r.get("rep", 0)) for r in results}
    todo = [x for x in runs if x not in have]
    log(f"track matrix: {len(todo)} runs to go of {len(runs)} ({MINUTES} min each, two at a time)")
    ports = [2148, 2150]
    while todo:
        batch, todo = todo[:2], todo[2:]
        procs = []
        for (track, variant, rep), port in zip(batch, ports):
            argv = [sys.executable, "-u", str(HERE / "drivetest.py"), track, "--variant", variant, "--minutes", str(MINUTES), "--port", str(port)]
            procs.append(((track, variant, rep), subprocess.Popen(argv, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)))
        for (track, variant, rep), p in procs:
            out, _ = p.communicate()
            line = next((l for l in out.splitlines() if l.startswith("track=")), "")
            r = {"track": track, "variant": variant, "rep": rep}
            for kv in line.split():
                k, _, v = kv.partition("=")
                if k in r:
                    continue
                try:
                    r[k] = json.loads(v.lower()) if v not in ("", "None") else None
                except ValueError:
                    r[k] = v
            r["score"] = score(r)
            results.append(r)
            try:
                sublab.record("driving", r)   # the sub-lab's results and the lab app's Sub-labs tab
            except Exception as e:
                log(f"sublab record failed: {e}")
            with open(done, "a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
            log(f"{track} {variant} #{rep + 1}: legs={r.get('legs')} lost={r.get('lost')} car_hits={r.get('car_hits')} jams={r.get('jams')} score={r['score']}")
    return results


def winner(results: list) -> tuple:
    by = {}
    for r in results:
        by.setdefault(r["track"], {}).setdefault(r["variant"], []).append(r["score"])
    ranks = {}
    for track, vs in by.items():
        order = sorted(vs, key=lambda v: -statistics.mean(vs[v]))
        for i, v in enumerate(order):
            ranks.setdefault(v, []).append(i + 1)
    mods = {v: len([m for m in drivetest.VARIANTS[v][1].split(",") if m]) for v in ranks}
    best = sorted(ranks, key=lambda v: (statistics.mean(ranks[v]), mods[v]))[0]
    return best, ranks, by


def watched_block(variant: str, hours: float) -> None:
    extra, mods = drivetest.VARIANTS[variant]
    rt = ROOT / ".runtime"
    (rt / "watch_extra.txt").write_text((WATCH_EXTRA + " " + extra).strip(), encoding="utf-8")
    (rt / "watch_mods.txt").write_text(mods, encoding="utf-8")
    (rt / "watch_armour_mods.txt").write_text("off", encoding="utf-8")
    log(f"watched block: {hours} h with '{variant}' (extra: {extra or '-'}; mods: {mods or '-'})")
    argv = [sys.executable, "-u", str(HERE / "watch_loop.py"), "--hours", str(hours), "--minutes", "30", "--solo", "--speed", "3", "--keep-front",
            "--rotation", "arland:phased:phased,everon:phased:llm-phased,arland:llm-phased:phased,everon:phased:phased"]
    with open(rt / "watch_day.out", "a", encoding="utf-8") as out:
        subprocess.run(argv, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT)


def report(results: list, best: str, ranks: dict, by: dict, watch_since: str) -> None:
    lines = [f"# Driving night {datetime.now():%Y-%m-%d}", "", f"Winner: **{best}** - variants: {drivetest.VARIANTS[best]}", "",
             "## Track matrix (mean of the runs: legs / lost / car hits / jams / score)", "",
             "| track | " + " | ".join(sorted(drivetest.VARIANTS)) + " |", "|---|" + "---|" * len(drivetest.VARIANTS)]
    for track in MATRIX:
        cells = []
        for v in sorted(drivetest.VARIANTS):
            rs = [r for r in results if r["track"] == track and r["variant"] == v]
            if not rs:
                cells.append("")
                continue
            m = lambda k: round(statistics.mean([(r.get(k) or 0) for r in rs]), 1)
            cells.append(f"{m('legs')} / {m('lost')} / {m('car_hits')} / {m('jams')} / **{m('score')}**")
        lines.append(f"| {track} | " + " | ".join(cells) + " |")
    lines += ["", "## Average rank per variant (1 = best on that track)", ""]
    for v, rk in sorted(ranks.items(), key=lambda x: statistics.mean(x[1])):
        lines.append(f"- {v}: {round(statistics.mean(rk), 2)} over {len(rk)} tracks")
    if watch_since:
        lines += ["", f"## Watched block (from {watch_since})", "", "See lab/progress.py / the lab app Progress tab: jams, long stops, vehicles hitting things, "
                  "against the 22 Oct afternoon (Arland ~6 jams / ~5 long stops a match) and the push block (Arland 5-14 / 1-4)."]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"report written: {OUT / 'REPORT.md'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--tracks-only", action="store_true")
    ap.add_argument("--watch-hours", type=float, default=3)
    a = ap.parse_args()
    runs = plan()
    if a.plan:
        hours = len(runs) * MINUTES / 2 / 60
        print(f"compile gate, then {len(runs)} track runs ({MINUTES} min, two at a time: ~{hours:.1f} h), then "
              f"{'no watched block' if a.tracks_only else f'{a.watch_hours} h of watched matches with the winner'}")
        for track, variants in MATRIX.items():
            print(f"  {track:18} {drivetest.TRACKS[track][0]:22} x{REPEATS}: {', '.join(variants)}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    keep = subprocess.Popen([sys.executable, str(HERE / "keepawake.py"), "--hours", "12"], cwd=str(ROOT))
    try:
        if not compile_gate():
            log("stopping: the compile gate failed")
            return
        results = track_matrix(runs)
        best, ranks, by = winner(results)
        log(f"winner: {best} (average ranks: " + ", ".join(f"{v} {round(statistics.mean(r), 2)}" for v, r in ranks.items()) + ")")
        report(results, best, ranks, by, "")
        if not a.tracks_only:
            since = f"{datetime.now():%Y-%m-%d %H:%M}"
            watched_block(best, a.watch_hours)
            report(results, best, ranks, by, since)
    finally:
        keep.terminate()


if __name__ == "__main__":
    main()
