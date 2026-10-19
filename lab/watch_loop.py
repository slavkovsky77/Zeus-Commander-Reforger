"""Reforger matches back to back on screen, recorded - the Reforger lab's watch loop, like ac-lab's
watch_loop.py + record.py on Arma 3.

    python lab/watch_loop.py --hours 7
    python lab/watch_loop.py --hours 7 --rotation everon:llm,everon:none,arland:doctrine

Per match: a server with AI commanders on both sides (watchers see the whole map), the game on
screen joining it with the director camera (ZCR_Watch), the game window recorded to
videos/<stamp>_<label>.mp4, and next to it <stamp>_<label>.md - the match's measurements and a
moments list (captures, plan changes with the commander's intent, losses, camera shots) with their
time in the video. Strategist per match: none (AI Conflict alone), doctrine (our rules) or llm (the
model in lab/bridge.local.json). A crash dialog, a dead process or a dropped connection ends the
match early; the loop goes on with the next one. Code changes take effect from the next match (both
server and game load the addon from source).
"""
import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
from argparse import Namespace
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import metrics  # noqa: E402
import reforger  # noqa: E402

VIDEOS = ROOT / "videos"
PORT = 2110
from reforger import BRIDGES  # noqa: E402
user32 = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def git_commit() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%h"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "ZeusCommanderReforger", "lab"],
                           capture_output=True, text=True).stdout.strip()
    return r.stdout.strip() + ("+changes" if dirty else "")


def opts(map_name: str, client: bool, us: str, ussr: str, label: str) -> Namespace:
    return Namespace(map=map_name, port=PORT, client=client, drones=True, watch=True, plan_seconds=90,
                     bridge=False, bridge_url="", us=us, ussr=ussr, label=label, minutes=0, dry_run=False)


def start(o: Namespace, tag: str):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    profile = ROOT / ".runtime" / "runs" / f"{o.label}-{tag}-{stamp}"
    profile.mkdir(parents=True)
    cmd = reforger.command(o, profile)
    out = open(profile / "stdout.log", "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(Path(cmd[0]).parent), stdout=out, stderr=subprocess.STDOUT)
    return proc, profile


def read_log(profile: Path) -> str:
    log_file = reforger.console_log(profile)
    return log_file.read_text(encoding="utf-8", errors="replace") if log_file else ""


def wait_for(profile: Path, proc, needle: str, seconds: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < seconds:
        if proc.poll() is not None:
            return False
        if needle in read_log(profile):
            return True
        time.sleep(3)
    return False


# --- windows: the game's window, crash dialogs ---------------------------------------------------
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def windows():
    out = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            out.append((hwnd, pid.value, title.value, cls.value))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def game_window(pid: int):
    best = None
    for hwnd, p, title, cls in windows():
        if p == pid and cls != "#32770":
            r = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            if r.right - r.left >= 640 and (best is None or r.right - r.left > best[1]):
                best = (hwnd, r.right - r.left)
    return best[0] if best else None


def client_rect(hwnd) -> tuple:
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    x, y = max(0, pt.x), max(0, pt.y)
    return x, y, min(r.right - r.left, sw - x) // 2 * 2, min(r.bottom - r.top, sh - y) // 2 * 2


def crash_dialogs(pids: set) -> list:
    """Error or crash-report windows: a dialog of one of our processes, or the crash reporter."""
    found = []
    for hwnd, p, title, cls in windows():
        name = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {p} -ErrorAction SilentlyContinue).ProcessName"],
                              capture_output=True, text=True).stdout.strip() if cls == "#32770" or "crash" in title.lower() else ""
        if (cls == "#32770" and (p in pids or name.lower().startswith(("armareforger", "crashreporter")))) or name.lower() == "crashreporter":
            found.append((p, name, title))
    return found


def kill(proc) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()


def kill_crash_reporters() -> None:
    subprocess.run(["taskkill", "/IM", "CrashReporter.exe", "/F"], capture_output=True)


# --- recording ------------------------------------------------------------------------------------
def ffmpeg_start(out: Path, rect: tuple):
    x, y, w, h = rect
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "0",
            "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop",
            "-vf", "scale=1920:-2" if w > 1920 else "null",
            "-c:v", "h264_mf", "-hw_encoding", "1", "-b:v", "8M", "-pix_fmt", "nv12", str(out)]
    return subprocess.Popen(argv, stdin=subprocess.PIPE)


def ffmpeg_stop(p) -> None:
    try:
        p.communicate(b"q", timeout=30)
    except subprocess.TimeoutExpired:
        p.kill()


# --- the moments list -------------------------------------------------------------------------------
STAMP = re.compile(r"^\s*(\d{1,2}):(\d\d):(\d\d)")


def secs(line: str):
    m = STAMP.match(line)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def mmss(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


def moments(server_log: str, client_log: str, rec_start: int) -> tuple:
    key, shots = [], []
    for line in server_log.splitlines():
        t = secs(line)
        if t is None:
            continue
        v = t - rec_start
        if "[ZCR][CAPTURE]" in line:
            m = re.search(r"base=(.*?) from=(\S*) to=(\S*)", line)   # base names have spaces
            if m:
                key.append((v, f"CAPTURE: {m.group(3) or 'nobody'} takes {m.group(1)} from {m.group(2) or 'nobody'}"))
        elif "[ZCR][DRONES]" in line and " team=" in line:
            f = metrics.fields(line, "[ZCR][DRONES]")
            m = re.search(r"from=(.*?) to=(.*?) distance=", line)   # base names have spaces
            where = f"from {m.group(1)} to {m.group(2)}" if m else ""
            key.append((v, f"DRONES: {f.get('side')} {f.get('kind')} FPV team {where}"))
        elif "[ZCR][PLAN]" in line:
            f = line.split("[ZCR][PLAN]", 1)[1]
            side = re.search(r"faction=(\S+)", f)
            intent = f.split("intent=", 1)[1].strip() if "intent=" in f else ""
            src = re.search(r"source=(\S+)", f)
            if intent:
                key.append((v, f"{side.group(1) if side else '?'} commander ({src.group(1) if src else '?'}): {intent}"))
    for line in client_log.splitlines():
        t = secs(line)
        if t is not None and "[ZCR][CAM]" in line:
            label = line.split("label=", 1)[1].strip() if "label=" in line else line
            shots.append((t - rec_start, label))
    return sorted(key), shots


def write_index(path: Path, video: Path, meta: dict, m: dict, key: list, shots: list) -> None:
    lines = [f"# {video.name}", "",
             f"Map {meta['map']} · strategist {meta['strategist']} · build {meta['commit']} · recorded {meta['started']}"
             f" · {meta['minutes']} min{' · ENDED EARLY: ' + meta['ended'] if meta.get('ended') else ''}", "",
             "## Result", "", "```", json.dumps(m, indent=1), "```", "", "## Moments (video time)", ""]
    lines += [f"- {mmss(v)} {what}" for v, what in key if v >= 0] or ["- nothing yet"]
    lines += ["", "## Camera shots", ""] + [f"- {mmss(v)} {what}" for v, what in shots if v >= 0]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- one match -------------------------------------------------------------------------------------
def match(n: int, map_name: str, us: str, ussr: str, minutes: float, keep_front: bool) -> dict:
    label = f"w{n}-{map_name}-{us}-v-{ussr}"
    meta = {"map": map_name, "us": us, "ussr": ussr, "strategist": f"US {us} v USSR {ussr}", "commit": git_commit(),
            "started": f"{datetime.now():%Y-%m-%d %H:%M}", "minutes": minutes, "ended": ""}
    log(f"match {n}: {map_name}, {meta['strategist']}, {minutes:.0f} min, build {meta['commit']}")
    kill_crash_reporters()
    server, sprof = start(opts(map_name, False, us, ussr, label), "server")
    client = ff = None
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    video = VIDEOS / f"{stamp}_{label}.mp4"
    mkv = video.with_suffix(".mkv")
    rec_start = None
    meta["minutes"] = 0
    try:
        if not wait_for(sprof, server, "ROSTER_READY", 600):
            meta["ended"] = "server did not get ready"
            return meta
        client, cprof = start(opts(map_name, True, us, ussr, label), "client")
        if not wait_for(cprof, client, "[ZCR][CAM]", 300):
            meta["ended"] = "the game did not start the camera"
            return meta
        time.sleep(5)
        hwnd = game_window(client.pid)
        if not hwnd:
            meta["ended"] = "no game window"
            return meta
        if keep_front:
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
            user32.SetForegroundWindow(hwnd)
        VIDEOS.mkdir(exist_ok=True)
        ff = ffmpeg_start(mkv, client_rect(hwnd))
        rec_start = int(time.strftime("%H")) * 3600 + int(time.strftime("%M")) * 60 + int(time.strftime("%S"))
        log(f"recording {mkv.name}")
        t0 = time.time()
        while time.time() - t0 < minutes * 60:
            time.sleep(10)
            if server.poll() is not None:
                meta["ended"] = f"server exited ({server.returncode})"
                break
            if client.poll() is not None:
                meta["ended"] = f"the game exited ({client.returncode})"
                break
            dialogs = crash_dialogs({server.pid, client.pid})
            if dialogs:
                meta["ended"] = f"crash or error dialog: {dialogs[0][1]} '{dialogs[0][2]}'"
                break
            if "event: disconnected" in read_log(cprof):
                meta["ended"] = "the game was disconnected"
                break
        meta["minutes"] = round((time.time() - t0) / 60, 1)
    finally:
        if ff:
            ffmpeg_stop(ff)
        kill(client)
        kill(server)
        kill_crash_reporters()
        if meta["ended"]:
            log(f"ended early: {meta['ended']}")
    server_log = read_log(sprof)
    m = metrics.measure(server_log.splitlines())
    (sprof / "metrics.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    if rec_start is not None and mkv.exists():
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mkv), "-c", "copy", str(video)])
        if r.returncode == 0 and video.exists():
            mkv.unlink()
        else:
            video = mkv
        key, shots = moments(server_log, read_log(cprof), rec_start)
        write_index(video.with_suffix(".md"), video, meta, m, key, shots)
        log(f"video {video.name} ({video.stat().st_size // 1_000_000} MB), {len(key)} moments, {len(shots)} shots")
    meta.update(metrics=m, server_profile=str(sprof))
    with open(ROOT / ".runtime" / "watch_matches.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(meta) + "\n")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=7)
    ap.add_argument("--minutes", type=float, default=30, help="per match")
    ap.add_argument("--rotation", default="everon:none:llm,everon:llm:none,everon:none:doctrine",
                    help="map:US strategist:USSR strategist, each none / doctrine / llm")
    ap.add_argument("--keep-front", action="store_true", help="keep the game on top (only when nobody uses the PC)")
    a = ap.parse_args()
    rotation = [tuple(x.split(":")) for x in a.rotation.split(",") if x]
    import bridges
    bridges.ensure(tuple({s for _, us, ussr in rotation for s in (us, ussr) if s in BRIDGES}))
    end = time.time() + a.hours * 3600
    n = fails = 0
    while time.time() < end:
        # The rotation can change between matches: .runtime/watch_rotation.txt overrides.
        override = ROOT / ".runtime" / "watch_rotation.txt"
        if override.exists():
            new = [tuple(x.split(":")) for x in override.read_text(encoding="utf-8").strip().split(",") if x.count(":") == 2]
            if new and new != rotation:
                rotation = new
                bridges.ensure(tuple({x for _, u, v in rotation for x in (u, v) if x in BRIDGES}))
                log(f"rotation now {override.read_text(encoding='utf-8').strip()}")
        map_name, us, ussr = rotation[n % len(rotation)]
        n += 1
        meta = match(n, map_name, us, ussr, min(a.minutes, max(5, (end - time.time()) / 60 - 3)), a.keep_front)
        fails = fails + 1 if meta.get("ended") and meta.get("minutes", 0) < 2 else 0
        if fails >= 3:
            log("three matches in a row failed to start - stopping")
            return 1
        time.sleep(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
