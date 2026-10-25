"""The night queue (25 Oct, Martin: "let's prepare everything for night runs - while I am gaming"). One list of headless
jobs, two at a time at idle priority (Martin plays on this PC first - memory: headless while gaming, at most 2 servers),
resumable, with a morning report.

    python lab/night.py --plan        # what would run, run nothing
    python lab/night.py               # the night (skips jobs already done tonight)
    python lab/night.py --report      # .runtime/night/<night>/REPORT.md from what has finished

Jobs:
  gate     a 3-minute base-building run: any script error stops the night (the cache fix and the build test changed today)
  build    the base-building sub-lab (lab/buildtest.py via lab/sublab.py, results in its table): each scenario with our
           builders and with AI Conflict's own depot placement, twice; HQ-only and no-fortifications once
  match    headless Arland matches with the watched setup (.runtime/watch_mods.txt + watch_extra.txt, phased v phased),
           25 game minutes: AI Conflict's supply trucks on our road routes (default) against the same without
           (-aicfNoRoadRoutes), three each - deliveries, loads, cargo lost, stuck recoveries, failed moves, routes given
Stop between jobs: create .runtime/night/stop.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import cpu  # noqa: E402

NIGHT = (datetime.now() - timedelta(hours=8)).strftime("%Y-%m-%d")   # a night after midnight still belongs to its evening
OUT = ROOT / ".runtime" / "night" / NIGHT
STOP = ROOT / ".runtime" / "night" / "stop"
PORTS = [2148, 2150]
MATCH_MINUTES = 25
BUILD_MINUTES = 15


def jobs() -> list:
    out = [{"id": "gate", "kind": "gate"}]
    builds = []
    for s in ["near2", "farm", "near4"]:
        for v in ["default", "noaccess"]:
            for rep in range(2):
                builds.append({"id": f"build-{s}-{v}-{rep}", "kind": "build", "scenario": s, "variant": v})
    builds += [{"id": "build-hq-default-0", "kind": "build", "scenario": "hq", "variant": "default"},
               {"id": "build-near2-nofort-0", "kind": "build", "scenario": "near2", "variant": "nofort"}]
    matches = []
    for rep in range(3):
        for v, extra in [("routes", ""), ("noroutes", "-aicfNoRoadRoutes")]:
            matches.append({"id": f"match-{v}-{rep}", "kind": "match", "variant": v, "extra": extra})
    # A match and a building run side by side, the matches first (they take longest and matter for the watched games).
    while builds or matches:
        if matches:
            out.append(matches.pop(0))
        if builds:
            out.append(builds.pop(0))
    return out


def log(msg: str) -> None:
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "night.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def done_ids() -> set:
    p = OUT / "results.jsonl"
    if not p.exists():
        return set()
    return {json.loads(l)["id"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}


def save(row: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def match_summary(run_dir: Path) -> dict:
    """AI Conflict's supply trucks in one match: what they moved, what got stuck."""
    log_file = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log_file:
        return {"error": "no log"}
    text = log_file.read_text(encoding="utf-8", errors="replace")
    farm = 0
    for m in re.finditer(r"\[ZCR\]\[MOVEFAIL\] .* x=(\d+) z=(\d+)", text):
        if abs(int(m.group(1)) - 2209) < 300 and abs(int(m.group(2)) - 2909) < 300:
            farm += 1
    minutes = re.findall(r"\[ZCR\]\[LIVE\] t=(\d+)", text)
    return {
        "minutes": round(int(minutes[-1]) / 60, 1) if minutes else None,
        "unloads": text.count("LOGISTICS_UNLOAD_COMMITTED"), "loads": text.count("LOGISTICS_LOAD_COMMITTED"),
        "cargo_lost": text.count("LOGISTICS_CARGO_LOST"), "recoveries": text.count("LOGISTICS_RECOVERY_ATTEMPT"),
        "exit_failures": text.count("LOGISTICS_EXIT_FAILURE"), "routes": text.count("LOGISTICS_ROAD_ROUTE]"),
        "trucks": text.count("LOGISTICS_SPAWN_REQUESTED"), "retired": text.count("LOGISTICS_RETIRED"),
        "movefails": text.count("[ZCR][MOVEFAIL]"), "movefails_farm": farm,
        "script_errors": len([l for l in text.splitlines() if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l]),
        "crashed": bool(list(log_file.parent.glob("*.mdmp"))), "run": run_dir.name,
    }


def start(job: dict, port: int) -> subprocess.Popen:
    idle = getattr(subprocess, "IDLE_PRIORITY_CLASS", 0)
    if job["kind"] == "gate":
        argv = [sys.executable, "-u", str(HERE / "buildtest.py"), "near2", "--minutes", "3", "--port", str(port)]
    elif job["kind"] == "build":
        argv = [sys.executable, "-u", str(HERE / "sublab.py"), "run", "building", "--scenario", job["scenario"], "--variant",
                job["variant"], "--repeat", "1", "--minutes", str(BUILD_MINUTES), "--port", str(port)]
    else:
        mods = (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").strip()
        extra = (ROOT / ".runtime" / "watch_extra.txt").read_text(encoding="utf-8").strip()
        job["label"] = f"night-{job['id']}-p{port}"
        argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", "arland", "--minutes", str(MATCH_MINUTES), "--label", job["label"],
                "--port", str(port), "--us", "phased", "--ussr", "phased", "--mods", mods, "--extra", f"{extra} {job['extra']}".strip()]
    # Each job's output to its own file (a pipe nobody reads while the job runs could fill and stall it).
    (OUT / "jobs").mkdir(parents=True, exist_ok=True)
    job["out"] = str(OUT / "jobs" / f"{job['id']}.out")
    with open(job["out"], "w", encoding="utf-8") as f:
        return subprocess.Popen(argv, cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT, text=True, creationflags=idle)


def finish(job: dict, proc: subprocess.Popen) -> dict:
    proc.wait()
    out = Path(job["out"]).read_text(encoding="utf-8", errors="replace")
    row = {"id": job["id"], "kind": job["kind"], "at": datetime.now().strftime("%H:%M")}
    if job["kind"] == "gate":
        line = next((l for l in out.splitlines() if l.startswith("scenario=")), "")
        kv = dict(x.split("=", 1) for x in line.split() if "=" in x)
        row.update({k: kv.get(k) for k in ("placed", "built", "caches", "cache_road", "script_errors", "crashed", "run")})
    elif job["kind"] == "build":
        line = next((l.strip() for l in out.splitlines() if l.strip().startswith("score=")), "")
        row.update({"scenario": job["scenario"], "variant": job["variant"], "line": line})
    else:
        runs = sorted((ROOT / ".runtime" / "runs").glob(f"{job['label']}-*"))
        row.update({"variant": job["variant"]})
        row.update(match_summary(runs[-1]) if runs else {"error": "no run folder"})
    save(row)
    return row


def report() -> Path:
    rows = [json.loads(l) for l in (OUT / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] if (OUT / "results.jsonl").exists() else []
    lines = [f"# Night {NIGHT}", "", f"{len(rows)} jobs finished.", ""]
    ms = [r for r in rows if r["kind"] == "match" and "unloads" in r]
    if ms:
        lines += ["## AI Conflict's supply trucks: our road routes vs none (headless Arland, watched setup)", "",
                  "| | matches | deliveries | loads | cargo lost | stuck recoveries | failed moves | at the Farm | routes given |", "|---|---|---|---|---|---|---|---|---|"]
        for v in ("routes", "noroutes"):
            g = [r for r in ms if r["variant"] == v]
            if not g:
                continue
            avg = lambda k: round(sum(r.get(k) or 0 for r in g) / len(g), 1)
            lines.append(f"| {v} | {len(g)} | {avg('unloads')} | {avg('loads')} | {avg('cargo_lost')} | {avg('recoveries')} | {avg('movefails')} | {avg('movefails_farm')} | {avg('routes')} |")
        lines += ["", "Per match:", ""] + [f"- {r['id']}: " + " ".join(f"{k}={r.get(k)}" for k in ("minutes", "unloads", "loads", "cargo_lost", "recoveries", "movefails", "routes", "script_errors", "crashed", "run")) for r in ms]
    bs = [r for r in rows if r["kind"] == "build"]
    if bs:
        import sublab
        lines += ["", "## Base building (sub-lab table: lab app, Sub-labs tab)", ""] + [f"- {r['scenario']} / {r['variant']}: {r['line']}" for r in bs]
        try:
            lines += ["", sublab.report("building").read_text(encoding="utf-8")]
        except Exception as e:
            lines += ["", f"(sub-lab report failed: {e})"]
    p = OUT / "REPORT.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--gaming", action="store_true", help="Martin plays on this PC: one server at a time, pinned to the upper half of the cores")
    a = ap.parse_args()
    global PORTS
    if a.gaming:
        # 25 Oct: AoE stuttered while two headless servers ran at idle priority - idle priority doesn't help, their threads
        # fill the sibling hyper-threads of the game's cores (note 279). One server, on the upper half of the cores.
        PORTS = PORTS[:1]
    todo = [j for j in jobs() if j["id"] not in done_ids()]
    if a.plan:
        for j in todo:
            print(j["id"])
        print(f"{len(todo)} jobs; results in {OUT}")
        return 0
    if a.report:
        print(report())
        return 0
    log(f"night {NIGHT}: {len(todo)} jobs, {len(PORTS)} at a time, idle priority")
    gate = next((j for j in todo if j["kind"] == "gate"), None)
    if gate:
        r = finish(gate, start(gate, PORTS[0]))
        log(f"gate: {r}")
        if str(r.get("script_errors")) not in ("0", "None") or str(r.get("crashed")) == "True" or str(r.get("placed")) in ("0", "None"):
            log("gate FAILED - the night stops")
            report()
            return 1
        todo = [j for j in todo if j is not gate]
    running = {}   # port -> (job, proc)
    while todo or running:
        for port in PORTS:
            if port in running or not todo or STOP.exists():
                continue
            job = todo.pop(0)
            running[port] = (job, start(job, port))
            log(f"start {job['id']} on {port}")
        if a.gaming or cpu.watched_running():
            cpu.pin_headless(True)   # every 20 s: servers started since are pinned too
        for port, (job, proc) in list(running.items()):
            if proc.poll() is None:
                continue
            r = finish(job, proc)
            del running[port]
            log(f"done {job['id']}: " + " ".join(f"{k}={v}" for k, v in r.items() if k not in ("id", "kind")))
            report()
        if STOP.exists() and not running:
            log("stop file - the night ends here")
            break
        time.sleep(20)
    log(f"night done - {report()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
