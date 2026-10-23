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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runner", choices=["inftest", "guntest", "drivetest"])
    ap.add_argument("scenario")
    ap.add_argument("--variant", default="game")
    ap.add_argument("--minutes", type=float, default=12)
    a = ap.parse_args()
    tag = f"{a.runner}-{a.scenario}-{a.variant}-watch"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    VIDEOS.mkdir(exist_ok=True)
    mkv = VIDEOS / f"{stamp}_{tag}.mkv"
    runner = subprocess.Popen([sys.executable, "-u", str(HERE / f"{a.runner}.py"), a.scenario, "--variant", a.variant, "--minutes", str(a.minutes), "--watch"],
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
    else:
        print("no game window found - nothing recorded", flush=True)
    return runner.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
