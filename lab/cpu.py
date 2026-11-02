"""Keep the headless lab servers off the watched game's cores.

Note 279 (21 Oct): two or three headless matches beside the watched one cut it from ~40 to 20-25 fps (16-18 with
three); Idle priority does not help, their threads fill the sibling hyper-threads of the cores the game runs on.
While a watched game (ArmaReforgerSteamDiag) runs, every headless server (ArmaReforgerServerDiag) is pinned to the
upper half of the logical processors (0xFF00 of 16); when the watched game ends they get every core back. The
watched game itself is never touched. Windows only (PowerShell sets the affinity); no extra packages.

    python lab/cpu.py on | off | status
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HEADLESS = "ArmaReforgerServerDiag"
WATCHED = "ArmaReforgerSteamDiag"


def _ps(script: str) -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def masks() -> tuple:
    """(all cores, the upper half) as affinity masks."""
    n = os.cpu_count() or 16
    every = (1 << n) - 1
    return every, every ^ ((1 << (n // 2)) - 1)


# AoE mode (memory 'Headless while gaming': when Martin plays Age of Empires, ONE headless server pinned to the upper cores -
# idle priority alone still made AoE stutter). On while .runtime/aoe_mode exists: every new headless server is pinned, and
# each lab launch waits until no other headless server runs (aoe_gate), so several agents' tests take turns.
#     python lab/cpu.py aoe on | aoe off
AOE_MODE = Path(__file__).resolve().parent.parent / ".runtime" / "aoe_mode"


def aoe_on() -> bool:
    return AOE_MODE.exists()


def headless_count() -> int:
    out = _ps(f"(Get-Process {HEADLESS} -ErrorAction SilentlyContinue | Measure-Object).Count")
    try:
        return int(out or 0)
    except ValueError:
        return 0


def aoe_gate(label: str = "", poll_s: int = 20):
    """In AoE mode, wait until no headless server runs, then take the turn (a lock dir, so two waiting launches don't
    start together). Returns a release function (also released when the process exits)."""
    if not aoe_on():
        return None
    import atexit
    lock = AOE_MODE.parent / "aoe_gate.lock"
    waited = 0
    while True:
        if headless_count() == 0 or not aoe_on():
            try:
                lock.mkdir()
                (lock / "owner.txt").write_text(f"{os.getpid()} {label}", encoding="utf-8")
                break
            except FileExistsError:
                # A stale lock (its launcher is gone) is taken over.
                owner = (lock / "owner.txt").read_text(encoding="utf-8").split()[0] if (lock / "owner.txt").exists() else ""
                if owner and not _ps(f"Get-Process -Id {owner} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"):
                    import shutil
                    shutil.rmtree(lock, ignore_errors=True)
                    continue
        if waited % 300 == 0:
            print(f"AoE mode: another headless server runs - {label} waits its turn ({waited} s)", flush=True)
        time.sleep(poll_s)
        waited += poll_s

    def release():
        import shutil
        try:
            if (lock / "owner.txt").read_text(encoding="utf-8").split()[0] == str(os.getpid()):
                shutil.rmtree(lock, ignore_errors=True)
        except OSError:
            pass
    atexit.register(release)
    return release


def watched_running() -> bool:
    if aoe_on():
        return True   # AoE mode: pin as for a watched game
    return WATCHED in _ps(f"Get-Process {WATCHED} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName")


def pin_headless(on: bool, pid: int = 0) -> str:
    """Pin every headless server (or one pid) to the upper half of the cores, or give them all cores back."""
    every, upper = masks()
    mask = upper if on else every
    target = f"Get-Process -Id {pid}" if pid else f"Get-Process {HEADLESS}"
    return _ps(f"{target} -ErrorAction SilentlyContinue | ForEach-Object {{ $_.ProcessorAffinity = [IntPtr]{mask}; "
               f"\"$($_.Id) -> $($_.ProcessorAffinity)\" }}")


def pin_if_watched(pid: int) -> None:
    """A headless server just started: keep it off the watched game's cores if one is on screen."""
    if watched_running():
        print(f"a watched game is running - server {pid} pinned to the upper cores: {pin_headless(True, pid)}", flush=True)


def status() -> str:
    return _ps(f"Get-Process {HEADLESS},{WATCHED} -ErrorAction SilentlyContinue | ForEach-Object {{ \"$($_.ProcessName) $($_.Id) affinity $($_.ProcessorAffinity)\" }}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "status"
    if what == "aoe":
        if len(sys.argv) > 2 and sys.argv[2] == "off":
            AOE_MODE.unlink(missing_ok=True)
            print("AoE mode off")
        else:
            AOE_MODE.write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
            print("AoE mode on: headless servers pinned to the upper cores, one at a time")
            print(pin_headless(True) or "no headless server running")
    elif what in ("on", "off"):
        print(pin_headless(what == "on") or "no headless server running")
    print(status() or "no game processes")
