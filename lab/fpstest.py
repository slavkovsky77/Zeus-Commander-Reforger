"""Why the watched game's FPS drops (25 Oct night, Martin: "try to find out why FPS dropped like that - the last major issue
I noticed, maybe it's because of something in our mods"). One solo Arland match per variant in the game window (as the
watched matches: the game hosts it, the director camera on), no recording, nothing else running; the game's own FPS line
(every 10 s: fps, worst frame, AI, dynamic entities) and our census ([ZCR][CENSUS]) bucketed by game minute.

    python lab/fpstest.py --plan
    python lab/fpstest.py                       # every variant once, 12 game minutes each
    python lab/fpstest.py full3x nodco3x        # only these
    python lab/fpstest.py --report

Results: .runtime/fpstest/results.jsonl, REPORT.md.
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
OUT = ROOT / ".runtime" / "fpstest"
sys.path.insert(0, str(HERE))
GAME_MINUTES = 12

DCO = "5EDAAE0D3CC60D6B"
DRIVING_MODS = ("3B9F2C4D5E6A7B81", "68FCF11534562F2E")   # road price, Competent AI driving


def watch_setup():
    mods = [m.strip() for m in (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").replace("\n", ",").split(",") if m.strip()]
    extra = (ROOT / ".runtime" / "watch_extra.txt").read_text(encoding="utf-8").strip()
    return mods, extra


# variant: (speed, mods filter, extra added, drones, words)
VARIANTS = {
    "full3x": (3, None, "", True, "the watched setup at 3x - what Martin watches"),
    "full1x": (1, None, "", True, "the same at normal speed"),
    "full2x": (2, None, "", True, "the same at 2x"),
    "nodco3x": (3, lambda m: m != DCO, "", True, "without DCO (the game's own soldier AI) at 3x"),
    "nodrones3x": (3, None, "", False, "without the drone mods (FPV AI Drones + Realistic Combat Drones) at 3x"),
    "nodrivemods3x": (3, lambda m: m not in DRIVING_MODS, "", True, "without the driving mods (road price, Competent AI driving) at 3x"),
    "cap40_3x": (3, None, "-aicfMaxAgentsPerFaction 40", True, "40 soldiers a side instead of 50 at 3x"),
    "squads14_3x": (3, None, "-aicfSquadsPerSide 14", True, "14 teams a side instead of 20 (AI Conflict fork: -aicfSquadsPerSide) at 3x"),
    "squads10_3x": (3, None, "-aicfSquadsPerSide 10", True, "10 teams a side instead of 20 at 3x"),
    "squads14cap35_3x": (3, None, "-aicfSquadsPerSide 14 -aicfMaxAgentsPerFaction 35", True, "14 teams and at most 35 soldiers a side (50 by default) at 3x"),
    "squads14cap35_2x": (2, None, "-aicfSquadsPerSide 14 -aicfMaxAgentsPerFaction 35", True, "14 teams and at most 35 soldiers a side at 2x"),
    "squads14_2x": (2, None, "-aicfSquadsPerSide 14", True, "14 teams a side at 2x"),
    "teams1_3x": (3, None, "-aicfInfantryDeploySize 1 -aicfMusterSize 1", True, "teams of 1 instead of 2 (half the starting soldiers) at 3x"),
    "cap30_3x": (3, None, "-aicfMaxAgentsPerFaction 30", True, "30 soldiers a side instead of 50 at 3x"),
    "res70_3x": (3, None, "", True, "the watched setup at 3x rendered at 70% resolution (is it the graphics card or the processor?)"),
    "fewveh3x": (3, None, "-aicfMaxVehiclesPerFaction 4", True, "at most 4 vehicles a side (16 by default) at 3x"),
    "lod3x": (3, None, "-zcrAILod", True, "the watched setup at 3x with AI detail by distance from the camera (ZCR_AILod)"),
    "lod1x": (1, None, "-zcrAILod", True, "the same at normal speed"),
    # As the watched loop: the game window recorded (ffmpeg, Windows Graphics Capture), and the US on the model.
    "rec3x": (3, None, "", True, "the watched setup at 3x, the window recorded as in the watched loop"),
    "llmrec3x": (3, None, "", True, "exactly the watched match: 3x, recorded, the US on the model strategist (llm-phased)"),
}
RECORDED = {"rec3x", "llmrec3x"}
LLM = {"llmrec3x"}


def run(variant: str) -> dict:
    speed, keep, add, drones, _ = VARIANTS[variant]
    mods, extra = watch_setup()
    if keep:
        mods = [m for m in mods if keep(m)]
    if add:
        # the later value of a repeated parameter would be ambiguous - replace each one given
        parts = add.split()
        for k, name in enumerate(parts):
            if name.startswith("-") and k + 1 < len(parts) and not parts[k + 1].startswith("-"):
                extra = re.sub(rf"{re.escape(name)} \S+", "", extra)
        extra = f"{extra} {add}"
    if speed > 1:
        extra += f" -zcrSpeed {speed:g}"
    label = f"fps-{variant}"
    us = "llm-phased" if variant in LLM else "phased"
    argv = [sys.executable, "-u", str(HERE / "reforger.py"), "--map", "arland", "--solo", "--watch", "--minutes", str(round(GAME_MINUTES / speed, 2)),
            "--label", label, "--us", us, "--ussr", "phased", "--extra", " ".join(extra.split())]
    if mods:
        argv += ["--mods", ",".join(mods)]
    if drones:
        argv += ["--drones"]
    started = datetime.now()
    if variant in LLM:
        import bridges
        bridges.ensure(("llm-phased",))
    import os
    env = dict(os.environ)
    if variant.startswith("res70"):
        env["ZCR_RES_SCALE"] = "0.7"
    proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    ff = None
    mkv = OUT / f"rec-{variant}.mkv"
    if variant in RECORDED:
        # The game window recorded exactly as the watched loop does (lab/watch_test.py's way); the file is thrown away.
        import time
        import watch_loop
        import watch_test
        t0 = time.time()
        while proc.poll() is None and ff is None and time.time() - t0 < 300:
            pid = watch_test.game_pid(label)
            hwnd = watch_loop.game_window(pid) if pid else None
            if hwnd:
                time.sleep(5)
                OUT.mkdir(parents=True, exist_ok=True)
                ff = watch_loop.ffmpeg_start(mkv, hwnd)
            else:
                time.sleep(5)
    proc.wait()
    if ff:
        watch_loop.ffmpeg_stop(ff)
        mkv.unlink(missing_ok=True)
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"), key=lambda r: r.stat().st_mtime)
    r = summarize(runs[-1]) if runs else {"error": "no run folder"}
    if runs:
        close_crash_reporter(runs[-1])
    r.update({"variant": variant, "at": started.strftime("%Y-%m-%d %H:%M")})
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(r) + "\n")
    return r


FPS = re.compile(r"FPS: ([\d.]+), frame time \(avg: [\d.]+ ms, min: [\d.]+ ms, max: ([\d.]+) ms.*?AI: (\d+), AIChar: (\d+).*?Dynam: (\d+)")
T = re.compile(r"\[ZCR\]\[[A-Z_]+\][^\n]*? t=(\d+)")


def summarize(run_dir: Path) -> dict:
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        return {"error": "no log", "run": run_dir.name}
    t = -1
    buckets = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = T.search(line)
        if m:
            t = int(m.group(1))
            continue
        m = FPS.search(line)
        if m and t >= 0:
            b = min(t // 180, 9)   # 3-game-minute buckets: 0-3, 3-6, ... 27-30
            buckets.setdefault(b, []).append((float(m.group(1)), float(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))))
    text = log.read_text(encoding="utf-8", errors="replace")
    census = re.findall(r"\[ZCR\]\[CENSUS\] t=(\d+) total=(\d+) alive=(\d+) dead=(\d+) veh=(\d+) wrecks=(\d+) waypoints=(\d+) groups=(\d+) ms=(\d+) top=(\S*)", text)
    out = {"run": run_dir.name, "crashed": bool(list(log.parent.glob("*.mdmp"))), "buckets": {}}
    for b, rows in sorted(buckets.items()):
        fps = sorted(r[0] for r in rows)
        out["buckets"][f"{b * 3}-{b * 3 + 3}"] = {
            "fps": round(sum(fps) / len(fps), 1), "fps_low": fps[max(0, len(fps) // 10)], "spikes_pct": round(100 * sum(1 for r in rows if r[1] > 200) / len(rows)),
            "ai": rows[-1][2], "chars": rows[-1][3], "dynamic": rows[-1][4], "samples": len(rows)}
    # The match itself (does it still fight with fewer teams?): captures, losses, the last score line.
    out["captures"] = text.count("[ZCR][CAPTURE]")
    out["losses"] = text.count("[ZCR][LOSS]")
    score = re.findall(r"\[ZCR\]\[SCORE\] t=\d+ (US=\d+ USSR=\d+)", text)
    out["score"] = score[-1] if score else ""
    allfps = [r[0] for rows in buckets.values() for r in rows]
    out["fps"] = round(sum(allfps) / len(allfps), 1) if allfps else None
    out["census"] = [{"t": int(c[0]), "total": int(c[1]), "alive": int(c[2]), "dead": int(c[3]), "veh": int(c[4]), "wrecks": int(c[5]),
                      "waypoints": int(c[6]), "groups": int(c[7]), "ms": int(c[8]), "top": c[9]} for c in census]
    return out


def close_crash_reporter(run_dir: Path) -> None:
    """After our game crashed, the game's crash reporter stays open waiting for input and the next game won't start
    (25 Oct 18:42: the two runs after a crash quit within seconds). Close only the one that started with this crash."""
    dumps = list(run_dir.glob("logs/*/*.mdmp"))
    if not dumps:
        return
    at = int(dumps[0].stat().st_mtime)
    script = ("Get-CimInstance Win32_Process -Filter \"Name='CrashReporter.exe'\" | ForEach-Object { "
              "$t = [int](($_.CreationDate.ToUniversalTime() - [datetime]'1970-01-01').TotalSeconds); "
              f"if ([math]::Abs($t - {at}) -lt 30) {{ Stop-Process -Id $_.ProcessId -Confirm:$false; \"closed $($_.ProcessId)\" }} }}")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=30).stdout.strip()
    if out:
        print(f"crash reporter of {run_dir.name}: {out}", flush=True)


def report() -> Path:
    rows = [json.loads(l) for l in (OUT / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] if (OUT / "results.jsonl").exists() else []
    lines = ["# FPS test (solo Arland, director camera, no recording)", "",
             "| variant | what | fps all | 0-3 min | 3-6 | 6-9 | 9-12 | spikes >200 ms (6-12 min) | AI | crashed |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        b = r.get("buckets", {})
        cell = lambda k: f"{b[k]['fps']} (low {b[k]['fps_low']})" if k in b else "-"
        late = [b[k] for k in ("6-9", "9-12") if k in b]
        spikes = round(sum(x["spikes_pct"] for x in late) / len(late)) if late else "-"
        ai = (b.get("9-12") or b.get("6-9") or {}).get("ai", "-")
        lines.append(f"| {r['variant']} ({r.get('at', '')}) | {VARIANTS.get(r['variant'], ('', '', '', '', ''))[4]} | {r.get('fps')} | {cell('0-3')} | {cell('3-6')} | {cell('6-9')} | {cell('9-12')} | {spikes}% | {ai} | {r.get('crashed')} |")
    lines += ["", "Census (what is on the map, by game time):", ""]
    for r in rows:
        for c in r.get("census", []):
            lines.append(f"- {r['variant']} t={c['t']}: total {c['total']}, alive {c['alive']}, dead {c['dead']}, vehicles {c['veh']}, wrecks {c['wrecks']}, waypoints {c['waypoints']}, groups {c['groups']} ({c['ms']} ms) - {c['top']}")
    p = OUT / "REPORT.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main() -> int:
    global GAME_MINUTES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("variants", nargs="*", default=["full3x", "full1x", "nodco3x", "nodrones3x", "nodrivemods3x", "cap40_3x", "full2x"])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--minutes", type=float, default=GAME_MINUTES, help="game minutes per run (12)")
    a = ap.parse_args()
    GAME_MINUTES = a.minutes
    if a.report:
        print(report().read_text(encoding="utf-8"))
        return 0
    for v in a.variants:
        if a.plan:
            print(v, VARIANTS[v])
            continue
        print(f"{datetime.now():%H:%M:%S} {v}: {VARIANTS[v][4]}", flush=True)
        r = run(v)
        print(f"{datetime.now():%H:%M:%S} {v}: fps {r.get('fps')} " + " ".join(f"{k}:{x['fps']}/{x['spikes_pct']}%/ai{x['ai']}" for k, x in r.get("buckets", {}).items()), flush=True)
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
