"""Headless head-to-head matches back to back - the measuring half of the Reforger lab (the watch
loop is the other half, on screen).

    python lab/batch.py --hours 6 --parallel 1 --minutes 30
    python lab/batch.py --matchups everon:none:llm,everon:llm:none --parallel 2

A matchup is map:US strategist:USSR strategist, each none (AI Conflict alone), doctrine (our
rules) or llm (the model in lab/bridge.local.json). Every matchup is also played with the sides
swapped, so a map's advantage for one side cancels out. Each result goes to
.runtime/batch_results.jsonl (matchup, build, metrics with the final score) - progress.py reads it.
"""
import argparse
import json
import subprocess
import sys
import time
from argparse import Namespace
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import bridges  # noqa: E402
import metrics  # noqa: E402
import reforger  # noqa: E402
from watch_loop import git_commit, kill, log, read_log  # noqa: E402

RESULTS = ROOT / ".runtime" / "batch_results.jsonl"
DEFAULT = "everon:none:llm,everon:llm:none,everon:none:doctrine,everon:doctrine:none"


class Run:
    def __init__(self, map_name: str, us: str, ussr: str, port: int, minutes: float, scenario: str = ""):
        """scenario: "" (Conflict with FIA) or "nofia" (two armies only, -zcrNoFIA)."""
        self.map, self.us, self.ussr, self.minutes = map_name, us, ussr, minutes
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.label = f"b-{map_name}-{us}-v-{ussr}" + (f"-{scenario}" if scenario else "")
        self.profile = ROOT / ".runtime" / "runs" / f"{self.label}-{stamp}"
        self.profile.mkdir(parents=True)
        o = Namespace(map=map_name, port=port, client=False, drones=True, watch=False, plan_seconds=90,
                      bridge=False, bridge_url="", us=us, ussr=ussr, extra="-zcrNoFIA" if scenario == "nofia" else "")
        cmd = reforger.command(o, self.profile)
        self.commit = git_commit()
        self.proc = subprocess.Popen(cmd, cwd=str(Path(cmd[0]).parent),
                                     stdout=open(self.profile / "stdout.log", "w", encoding="utf-8", errors="replace"),
                                     stderr=subprocess.STDOUT)
        self.started = time.time()
        self.ready_at = None
        self.ended = ""
        log(f"start {self.label} on port {port} (build {self.commit})")

    def poll(self) -> bool:
        """True while the match should go on."""
        if self.proc.poll() is not None:
            self.ended = f"server exited ({self.proc.returncode})"
            return False
        if self.ready_at is None:
            if reforger.READY in read_log(self.profile):
                self.ready_at = time.time()
            elif time.time() - self.started > 600:
                self.ended = "not ready in 10 minutes"
                return False
            return True
        return time.time() - self.ready_at < self.minutes * 60

    def finish(self) -> dict:
        kill(self.proc)
        m = metrics.measure(read_log(self.profile).splitlines())
        row = {"at": datetime.now().isoformat(timespec="seconds"), "map": self.map, "us": self.us, "ussr": self.ussr,
               "commit": self.commit, "ended": self.ended, "profile": str(self.profile), "metrics": m}
        with open(RESULTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        sc = m.get("score", {})
        log(f"done {self.label}: {m['minutes']} min, bases US {sc.get('US')} USSR {sc.get('USSR')} FIA {sc.get('FIA')}"
            f", captures {m['captures']}, lost {m['lost']}" + (f" - {self.ended}" if self.ended else ""))
        return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6)
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--matchups", default=DEFAULT)
    a = ap.parse_args()
    # map:us:ussr or map:us:ussr:nofia (two armies only)
    queue = [tuple((m.split(":") + [""])[:4]) for m in a.matchups.split(",") if m]
    needed = {s for _, us, ussr, _ in queue for s in (us, ussr) if s in reforger.BRIDGES}
    bridges.ensure(tuple(needed))
    end = time.time() + a.hours * 3600
    running, n = [], 0
    while True:
        still = []
        for r in running:
            if r.poll():
                still.append(r)
            else:
                r.finish()
        running = still
        if time.time() < end - a.minutes * 60:
            while len(running) < a.parallel:
                # The matchups can change between matches: .runtime/batch_matchups.txt overrides.
                override = ROOT / ".runtime" / "batch_matchups.txt"
                if override.exists():
                    new = [tuple((m.split(":") + [""])[:4]) for m in override.read_text(encoding="utf-8").strip().split(",") if m.count(":") in (2, 3)]
                    if new and new != queue:
                        queue = new
                        bridges.ensure(tuple({x for _, u, v, _ in queue for x in (u, v) if x in reforger.BRIDGES}))
                        log(f"matchups now {override.read_text(encoding='utf-8').strip()}")
                map_name, us, ussr, scenario = queue[n % len(queue)]
                port = 2120 + (n % 8)
                n += 1
                running.append(Run(map_name, us, ussr, port, a.minutes, scenario))
                time.sleep(20)   # stagger the loading
        elif not running:
            return 0
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())
