"""The strategist bridges shared by all lab matches on this PC: llm (the model in
lab/bridge.local.json) on 8765, doctrine (our rules) on 8766. ensure() starts the missing ones and
leaves running ones alone, so the watch loop and the headless batch share them.

    python lab/bridges.py          # start both if they aren't running
"""
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from reforger import BRIDGES  # noqa: E402


def alive(port: int) -> bool:
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3).read().startswith(b"ok")
    except OSError:
        return False


def ensure(names=("llm", "doctrine")) -> None:
    (ROOT / ".runtime").mkdir(exist_ok=True)
    for name in names:
        port = BRIDGES[name]
        if alive(port):
            continue
        args = [sys.executable, "-u", str(HERE / "bridge.py"), "--port", str(port)]
        if name == "doctrine":
            args += ["--provider", "doctrine"]
        log = open(ROOT / ".runtime" / f"bridge-{name}.log", "a", encoding="utf-8")
        subprocess.Popen(args, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
    import time
    for _ in range(20):
        if all(alive(BRIDGES[n]) for n in names):
            return
        time.sleep(0.5)


if __name__ == "__main__":
    ensure()
    print({n: alive(p) for n, p in BRIDGES.items()})
