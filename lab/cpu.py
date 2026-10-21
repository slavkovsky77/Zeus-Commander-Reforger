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


def watched_running() -> bool:
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
    if what in ("on", "off"):
        print(pin_headless(what == "on") or "no headless server running")
    print(status() or "no game processes")
