"""Wait for the running watch loop and batch to finish their current match, then stop them
cleanly (a new loop with new code takes over). Used when the loops' own code changes - matchup
changes alone are picked up between matches without this.

    python lab/switch_loops.py watch batch
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".runtime"
MARK = {"watch": ("watch_*.out", " video "), "batch": ("batch_*.out", " done ")}   # the newest log of each loop
SCRIPT = {"watch": "watch_loop.py", "batch": "batch.py"}


def count(name: str) -> int:
    pattern, needle = MARK[name]
    logs = sorted(RUNTIME.glob(pattern), key=lambda p: p.stat().st_mtime)
    return logs[-1].read_text(encoding="utf-8", errors="replace").count(needle) if logs else 0


def ps(filter_ps: str) -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command", filter_ps], capture_output=True)


def stop(name: str) -> None:
    ps(f"Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {{ $_.CommandLine -like '*{SCRIPT[name]}*' }} | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    # Anything the loop started in the seconds since its last match ended.
    tag = "\\runs\\w" if name == "watch" else "\\runs\\b-"
    ps(f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -like 'ArmaReforger*' -and $_.CommandLine -like '*{tag}*' "
       "-and ((Get-Date) - $_.CreationDate).TotalSeconds -lt 120 } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    if name == "watch":
        ps("Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    print(f"{time.strftime('%H:%M:%S')} stopped the {name} loop after its match", flush=True)


def main() -> int:
    names = sys.argv[1:] or ["watch", "batch"]
    start = {n: count(n) for n in names}
    left = set(names)
    while left:
        for n in list(left):
            if count(n) > start[n]:
                stop(n)
                left.discard(n)
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
