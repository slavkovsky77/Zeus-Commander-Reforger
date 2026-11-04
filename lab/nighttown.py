"""The night of 4 Nov: the battle for Beauregard headless, one battle at a time, until a deadline (Martin: "over night you
can test both gemini vs gemini but also gemini vs rule based"). Each battle is one run of the integration test "town"
(lab/towntest.py via lab/sublab.py), rotating Gemini against the code from the nearer HQ, from the farther HQ, then Gemini
against Gemini.

    python lab/nighttown.py --until 08:30 [--minutes 30] [--port 2180]

Between battles it waits while .runtime/chain_hold exists (script edits on disk not yet compile-checked) and stops when
.runtime/night/stop exists. Log: .runtime/night/town.log.
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HOLD = ROOT / ".runtime" / "chain_hold"
STOP = ROOT / ".runtime" / "night" / "stop"
LOG = ROOT / ".runtime" / "night" / "town.log"
ROTATION = [("gemini-v-code", "harbour"), ("gemini-v-code", "south"), ("gemini-v-gemini", "harbour")]


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--until", default="08:30", help="no new battle after this clock time (HH:MM)")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--port", type=int, default=2180)
    a = ap.parse_args()
    hh, mm = (int(x) for x in a.until.split(":"))
    n = 0
    while True:
        if STOP.exists():
            log("stop file - done")
            return 0
        if HOLD.exists():
            log("hold file - waiting for the compile check")
            while HOLD.exists() and not STOP.exists():
                time.sleep(15)
            continue
        now = datetime.now()
        deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now.hour < 12 and now >= deadline:
            log(f"past {a.until} - done after {n} battles")
            return 0
        scenario, variant = ROTATION[n % len(ROTATION)]
        log(f"battle {n + 1}: {scenario} from the {variant} HQ, {a.minutes:g} min")
        t0 = time.time()
        r = subprocess.run([sys.executable, "-u", str(HERE / "sublab.py"), "run", "town", "--scenario", scenario, "--variant", variant,
                            "--repeat", "1", "--minutes", str(a.minutes), "--port", str(a.port)], cwd=str(ROOT),
                           capture_output=True, text=True)
        tail = " | ".join((r.stdout or "").strip().splitlines()[-3:])
        log(f"battle {n + 1} done in {round((time.time() - t0) / 60)} min, exit {r.returncode}: {tail[:400]}")
        n += 1


if __name__ == "__main__":
    sys.exit(main())
