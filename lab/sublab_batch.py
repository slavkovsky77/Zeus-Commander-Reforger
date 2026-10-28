"""A sub-lab's whole table on several headless servers at once (28 Oct, the assault sub-lab: 2 scenarios x 6 variants x 2
runs of 10 game minutes - 4 hours on one server, about 1 on four). Each server works through its share of the
(scenario, variant) cells one run after another with lab/sublab.py run, on its own port.

    python lab/sublab_batch.py assault --servers 4 --repeat 2
    python lab/sublab_batch.py assault --servers 1 --variants now,team4-bind     # while Martin plays: one server only

Stop between runs: create .runtime/sublab_stop (the running ones finish).
Only when the game is free for headless servers (nobody playing, or one server pinned to the upper cores while Martin
plays) - and a new sub-lab's numbers count only after Martin has seen it in the game window.
"""
import argparse
import subprocess
import sys
import threading
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP = ROOT / ".runtime" / "sublab_stop"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--servers", type=int, default=4)
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--minutes", type=float, default=0)
    ap.add_argument("--scenarios", default="", help="comma-separated (default: the sub-lab's)")
    ap.add_argument("--variants", default="", help="comma-separated (default: the sub-lab's)")
    ap.add_argument("--port", type=int, default=2160, help="the first server's port; the next ones 4 apart")
    a = ap.parse_args()
    d = tomllib.loads((ROOT / "lab" / "sublabs" / f"{a.name}.toml").read_text(encoding="utf-8"))
    scenarios = a.scenarios.split(",") if a.scenarios else d["scenarios"]
    variants = a.variants.split(",") if a.variants else d["variants"]
    cells = [(s, v) for s in scenarios for v in variants]
    shares = [cells[i::a.servers] for i in range(a.servers)]
    STOP.unlink(missing_ok=True)

    def worker(n: int, share: list) -> None:
        port = a.port + 4 * n
        for s, v in share:
            if STOP.exists():
                print(f"[batch] server {n}: stopped (.runtime/sublab_stop)", flush=True)
                return
            cmd = [sys.executable, "-u", str(ROOT / "lab" / "sublab.py"), "run", a.name, "--scenario", s, "--variant", v,
                   "--repeat", str(a.repeat), "--port", str(port)]
            if a.minutes:
                cmd += ["--minutes", str(a.minutes)]
            print(f"[batch] server {n} (port {port}): {s} / {v} x{a.repeat}", flush=True)
            subprocess.run(cmd, cwd=str(ROOT))

    threads = [threading.Thread(target=worker, args=(n, share)) for n, share in enumerate(shares) if share]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"[batch] done - python lab/sublab.py report {a.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
