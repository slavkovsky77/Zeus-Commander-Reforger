"""One lab test in the game window, recorded (23 Oct evening: Martin, out, wants to watch the infantry tests - live through
Moonlight or later from the video). Runs the test runner with --watch, finds the game window, records it like the watch
loop (Windows Graphics Capture of the game window only) to videos/<stamp>_<label>.mp4.

    python lab/watch_test.py inftest storm-foot --variant game --minutes 12
    python lab/watch_test.py inftest storm-foot --variant dco --minutes 12

Only when nobody else uses the game (Martin playing, another chat's game).
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import watch_loop  # noqa: E402

VIDEOS = ROOT / "videos"


def game_pid(tag: str):
    ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                         "Get-CimInstance Win32_Process -Filter \"Name like 'ArmaReforgerSteamDiag%'\" | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"],
                        capture_output=True, text=True, timeout=30).stdout
    for line in ps.splitlines():
        if tag in line:
            return int(line.split()[0])
    return None


def describe(mp4: Path, a, tag: str) -> None:
    """<video>.md: what the test was and how it ended (the lab app's recordings list shows its 'Map' line)."""
    import importlib
    mod = importlib.import_module(a.runner)
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{tag}-*"))
    r = mod.summarize(runs[-1], a.scenario, a.variant) if runs else {}
    words = getattr(mod, "SCENARIO_WORDS", {}).get(a.scenario, "")
    setup = (getattr(mod, "VARIANTS", {}).get(a.variant) or ("", "", a.variant))[-1]
    keys = [k for k in ("taken", "taken_s", "us_lost", "ussr_lost", "us_cover", "ussr_cover", "died_open_pct", "fight_m", "legs", "car_hits", "lost") if k in r]
    lines = [f"# {a.runner} {a.scenario} - {a.variant}", f"Map Arland - {a.scenario}, {a.variant} ({setup})", "", words, "",
             "| measure | value |", "|---|---|"] + [f"| {k} | {r.get(k)} |" for k in keys] + ["", f"Run: {r.get('run', '')}"]
    mp4.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runner", choices=["inftest", "guntest", "drivetest"])
    ap.add_argument("scenario")
    ap.add_argument("--variant", default="game")
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--speed", type=float, default=3, help="the game's time multiplier (default 3x)")
    ap.add_argument("--cars", type=int, default=0, help="drive tests: vehicles (0: the runner's default)")
    a = ap.parse_args()
    tag = f"{a.runner}-{a.scenario}-{a.variant}-watch"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    VIDEOS.mkdir(exist_ok=True)
    mkv = VIDEOS / f"{stamp}_{tag}.mkv"
    runner = subprocess.Popen([sys.executable, "-u", str(HERE / f"{a.runner}.py"), a.scenario, "--variant", a.variant, "--minutes", str(a.minutes), "--watch", "--port", "2178", "--speed", str(a.speed)] + (["--cars", str(a.cars)] if a.cars else []),
                              cwd=str(ROOT))
    ff = None
    t0 = time.time()
    while runner.poll() is None and ff is None and time.time() - t0 < 300:
        pid = game_pid(tag)
        hwnd = watch_loop.game_window(pid) if pid else None
        if hwnd:
            time.sleep(5)
            ff = watch_loop.ffmpeg_start(mkv, hwnd)
            print(f"recording the game window -> {mkv}", flush=True)
        else:
            time.sleep(5)
    runner.wait()
    if ff:
        watch_loop.ffmpeg_stop(ff)
        mp4 = mkv.with_suffix(".mp4")
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mkv), "-c", "copy", str(mp4)])
        if r.returncode == 0 and mp4.exists() and mp4.stat().st_size > 0:
            mkv.unlink(missing_ok=True)
            print(f"video: {mp4}", flush=True)
            describe(mp4, a, tag)
    else:
        print("no game window found - nothing recorded", flush=True)
    return runner.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
