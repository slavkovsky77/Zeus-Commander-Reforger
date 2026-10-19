"""Run a probe match (lab/reforger.py) that needs a given base within reach of a side at the start -
AI Conflict gives each side one base to attack first, and which one varies from match to match.
Relaunches (up to --tries) until the first report shows it, then lets the match run.

    python lab/probe.py --need "Moss Hill" --side USSR -- --map arland --minutes 24 --label probe-ab-p25
        --port 2137 --bridge --bridge-url http://127.0.0.1:8772 --us none --plan-seconds 30 --extra "-zcrStormPriority 25"
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def stop(label: str) -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'ArmaReforgerServer*' -and "
                    f"$_.CommandLine -like '*\\runs\\{label}-*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"],
                   capture_output=True)


def first_report(run: Path, side: str, timeout: float = 420):
    snaps = run / "profile" / "zcr" / "snapshots.jsonl"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if snaps.exists():
            for line in snaps.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("faction") == side:
                    return r
        time.sleep(5)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--need", required=True)
    ap.add_argument("--side", default="USSR")
    ap.add_argument("--tries", type=int, default=4)
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    rest = [x for x in a.rest if x != "--"]
    label = rest[rest.index("--label") + 1]
    for attempt in range(1, a.tries + 1):
        before = set((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
        proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), *rest])
        run = None
        for _ in range(60):
            new = set((ROOT / ".runtime" / "runs").glob(f"{label}-*")) - before
            if new:
                run = max(new, key=lambda p: p.stat().st_mtime)
                break
            time.sleep(2)
        r = first_report(run, a.side) if run else None
        reach = [b["name"] for b in (r or {}).get("bases", []) if b.get("attackable")]
        print(f"{time.strftime('%H:%M:%S')} try {attempt}: {run.name if run else '?'} - {a.side} can reach {reach}", flush=True)
        if a.need in reach:
            return proc.wait()
        stop(label)
        proc.kill()
        time.sleep(5)
    print(f"{a.need} never within reach in {a.tries} tries")
    return 1


if __name__ == "__main__":
    sys.exit(main())
