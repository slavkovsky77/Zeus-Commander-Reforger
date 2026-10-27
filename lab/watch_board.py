"""The boarding test (ZCR_BoardTest) in the game window, recorded - for Martin's review of the crash fix and of the
boarding order he asked for (27 Oct: "getting in one by one, that's even more natural"; "cars can all get out at once,
APC one by one, as they have one exit"). The game window hosts the test itself (--solo); only the game window is
recorded (watch_loop's Windows Graphics Capture) to videos/<stamp>_<label>.mp4 with a <video>.md beside it.

    python lab/watch_board.py order    # flat airport apron: M998, M1025, LAV-25 - in one by one, out in the new order
    python lab/watch_board.py fix      # Moss Hill hillside: LAV-25s - the crash fix moves soldiers straight into the seat

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
from watch_test import game_pid  # noqa: E402

VIDEOS = ROOT / "videos"
SHOWS = {
    "order": ("1000,2780;3;board_oneby;all -zcrGetOutOrder -zcrSafeBoardDeg 10",
              "Flat airport apron: an M998, an M1025 and a LAV-25 with US teams. Getting in one by one (the next soldier when the "
              "one before is in); getting out in the new order - the cars' teams at once, the LAV-25's back seats one every "
              "1.6 s (ZCR_GetOutOrder). Armed vehicles keep their driver and gunner aboard."),
    "fix": ("1700,1000;4;board;apc -zcrSafeBoardDeg 10",
            "Moss Hill hillside (17-24 deg - where the climb into a LAV-25 crashes the dedicated server every time): four "
            "LAV-25s, US squads, with the crash fix on (-zcrSafeBoardDeg 10) - a soldier who has walked up to a tilted vehicle "
            "goes straight into his seat, and out the same way. Here the game window hosts the test (it never crashed "
            "there); this is to see how the fix looks."),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("show", choices=list(SHOWS))
    ap.add_argument("--minutes", type=float, default=7)
    ap.add_argument("--port", type=int, default=2178)
    a = ap.parse_args()
    spec, words = SHOWS[a.show]
    tag = f"boardwatch-{a.show}"
    mods = (ROOT / ".runtime" / "watch_mods.txt").read_text(encoding="utf-8").strip()
    VIDEOS.mkdir(exist_ok=True)
    mkv = VIDEOS / f"{datetime.now():%Y-%m-%d_%H%M}_{tag}.mkv"
    runner = subprocess.Popen([sys.executable, "-u", str(HERE / "reforger.py"), "--solo", "--watch", "--map", "arland-test",
                               "--minutes", str(a.minutes), "--label", tag, "--port", str(a.port), "--mods", mods,
                               "--extra", f"-zcrBoardTest {spec}"], cwd=str(ROOT))
    ff = None
    rec_start = datetime.now()
    t0 = time.time()
    while runner.poll() is None and ff is None and time.time() - t0 < 300:
        pid = game_pid(tag)
        hwnd = watch_loop.game_window(pid) if pid else None
        time.sleep(5)
        if hwnd:
            ff = watch_loop.ffmpeg_start(mkv, hwnd)
            rec_start = datetime.now()
            print(f"recording the game window -> {mkv}", flush=True)
    runner.wait()
    if not ff:
        print("no game window found - nothing recorded", flush=True)
        return 1
    watch_loop.ffmpeg_stop(ff)
    mp4 = mkv.with_suffix(".mp4")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mkv), "-c", "copy", str(mp4)])
    if r.returncode != 0 or not mp4.exists() or mp4.stat().st_size == 0:
        print(f"remux failed - the recording stays {mkv}", flush=True)
        return 1
    mkv.unlink(missing_ok=True)
    mp4.with_suffix(".md").write_text(
        f"# Boarding test - {a.show}\nMap Arland test map - boarding test ({a.show})\n\n{words}\n\n"
        f"Spec: -zcrBoardTest {spec}\n\nRecording started: {rec_start:%Y-%m-%d %H:%M:%S}\n", encoding="utf-8")
    print(f"video: {mp4}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
