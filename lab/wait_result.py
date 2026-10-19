"""Wait until the lab has a new match result (headless or watched), or until a time limit -
so whoever runs the lab is woken to look at it.

    python lab/wait_result.py --minutes 45
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / ".runtime" / "batch_results.jsonl", ROOT / ".runtime" / "watch_matches.jsonl"]


def lines() -> int:
    return sum(len(f.read_text(encoding="utf-8").splitlines()) for f in FILES if f.exists())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=45)
    a = ap.parse_args()
    start, end = lines(), time.time() + a.minutes * 60
    while time.time() < end:
        if lines() > start:
            print(f"{time.strftime('%H:%M:%S')} new result ({lines() - start})")
            return 0
        time.sleep(15)
    print(f"{time.strftime('%H:%M:%S')} no new result in {a.minutes} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
