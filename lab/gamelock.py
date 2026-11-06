"""One Reforger game or server at a time across this PC's Claude sessions (6 Nov: the Faces tool tests in the game window
at night while the lab runs its batches - agreed with that session).

    .runtime/game.lock   who holds the game: owner, purpose, start. The holder touches it every minute; one not touched for
                         20 minutes is stale (a crashed holder) and may be taken.
    .runtime/game.want   another session waiting for a slot: owner, time. Before each launch we wait while a want younger than
                         15 minutes from someone else exists (at most 20 minutes) - so a night batch leaves gaps for it.

    with gamelock.hold("commander-lab", "assaulttest town-watch"):
        ... start the server, wait for it ...

    python lab/gamelock.py          # who holds it, who waits
"""
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

RUNTIME = Path(r"D:\work\reforger-commander\.runtime")
LOCK = RUNTIME / "game.lock"
WANT = RUNTIME / "game.want"
STALE_S = 20 * 60
WANT_FRESH_S = 15 * 60
WANT_MAX_WAIT_S = 20 * 60
OWNER = os.environ.get("ZCR_LOCK_OWNER", "commander-lab")


def _age(p: Path) -> float | None:
    try:
        return time.time() - p.stat().st_mtime
    except OSError:
        return None


def _owner(p: Path) -> str:
    try:
        first = p.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return ""
    return first.split(":", 1)[1].strip() if first.lower().startswith("owner:") else first.strip()


def status() -> str:
    out = []
    for name, p in (("lock", LOCK), ("want", WANT)):
        age = _age(p)
        if age is None:
            out.append(f"{name}: none")
        else:
            body = p.read_text(encoding="utf-8", errors="replace").strip().replace("\n", " | ")
            out.append(f"{name}: {body} (touched {round(age)} s ago{', STALE' if name == 'lock' and age > STALE_S else ''})")
    return "\n".join(out)


def _say(msg: str):
    print(f"[gamelock] {msg}", flush=True)


def yield_to_others(owner: str = OWNER):
    """Between runs: let a waiting session in (its want younger than 15 min), at most 20 min."""
    t0, said = time.time(), False
    while time.time() - t0 < WANT_MAX_WAIT_S:
        age = _age(WANT)
        if age is None or age > WANT_FRESH_S or _owner(WANT) == owner:
            return
        if not said:
            _say(f"{_owner(WANT) or 'another session'} wants the game - waiting (at most {WANT_MAX_WAIT_S // 60} min)")
            said = True
        time.sleep(10)
    _say("waited 20 minutes for the other session's want - going on")


def acquire(owner: str = OWNER, purpose: str = "", max_wait_s: float | None = None) -> bool:
    yield_to_others(owner)
    t0, said = time.time(), False
    while True:
        age = _age(LOCK)
        if age is None or age > STALE_S or _owner(LOCK) == owner:
            break
        if not said:
            _say(f"the game is held by {_owner(LOCK)} - waiting")
            said = True
        if max_wait_s is not None and time.time() - t0 > max_wait_s:
            return False
        time.sleep(10)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(f"owner: {owner}\npurpose: {purpose}\nstarted: {datetime.now().isoformat(timespec='seconds')}\npid: {os.getpid()}\n",
                    encoding="utf-8")
    return True


def release(owner: str = OWNER):
    if _owner(LOCK) == owner:
        try:
            LOCK.unlink()
        except OSError:
            pass


@contextmanager
def hold(purpose: str = "", owner: str = OWNER):
    """The lock for the duration of a game or server, touched every minute."""
    acquire(owner, purpose)
    stop = threading.Event()

    def beat():
        while not stop.wait(60):
            if _owner(LOCK) == owner:
                try:
                    os.utime(LOCK, None)
                except OSError:
                    pass

    t = threading.Thread(target=beat, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        release(owner)


def take(purpose: str = "", owner: str = OWNER):
    """hold() for code that can't use a with-block: returns the function that releases it (also run at exit)."""
    import atexit
    cm = hold(purpose, owner)
    cm.__enter__()
    done = []

    def free():
        if not done:
            done.append(1)
            cm.__exit__(None, None, None)

    atexit.register(free)
    return free


if __name__ == "__main__":
    print(status())
    sys.exit(0)
