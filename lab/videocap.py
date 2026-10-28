"""Keep only the newest match recordings (Martin, 28 Oct: "make it cap for last 5 games").

videos/ and videos/tests/ hold <stamp>_<label>.mp4 (or .mkv when the remux failed). After every recorded match
the recorders call prune(): every video but the newest KEEP (by the date stamp the names start with) is deleted.
The <video>.md beside each one stays - it is the match's measurements, a few KB.

    python lab/videocap.py            # prune now
    python lab/videocap.py --dry-run  # list what would go
"""
import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "videos"
KEEP = 5


def prune(keep: int = KEEP, dry_run: bool = False) -> list:
    files = [p for d in (VIDEOS, VIDEOS / "tests") if d.is_dir() for p in d.iterdir() if p.suffix in (".mp4", ".mkv")]
    files.sort(key=lambda p: p.name)
    gone = []
    for p in files[:-keep] if keep > 0 else files:
        if p.suffix == ".mkv" and time.time() - p.stat().st_mtime < 120:
            continue  # still being recorded
        if not dry_run:
            try:
                p.unlink()
            except OSError:
                continue  # open in a player
        gone.append(p)
    return gone


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=KEEP)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    gone = prune(a.keep, a.dry_run)
    gb = sum(p.stat().st_size for p in gone) / 1e9 if a.dry_run else None
    for p in gone:
        print(("would delete " if a.dry_run else "deleted ") + p.name)
    print(f"{len(gone)} videos" + (f", {gb:.1f} GB" if gb is not None else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
