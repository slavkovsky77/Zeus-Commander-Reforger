"""Play the battle yourself (2 Nov 2026 - Martin: "could you prepare version of farm battle that I could as soldier for one
side?", "I would like to test gameplay as well", "like in general not just farm battle like general I could use it a way I
could actually play it"). The game hosts the same battle as the watched matches - the map, our commanders on both sides,
AI Conflict's teams, rides, drones, armour, the mods and settings in .runtime/watch_mods.txt and watch_extra.txt - but
without our spectator mode: the game's own deploy menu comes up, you pick a side and a base and play as a soldier among the
AI teams, at normal speed. No time limit - it runs until you quit the game.

    python lab/play.py                         # Arland, modern (US) v phased (USSR)
    python lab/play.py --map everon --us phased --ussr modern
    python lab/play.py --extra "-aicfMaxAgentsPerFaction 30"   # more settings for this game
    python lab/assaulttest.py city --variant farm-now --play  # the Farm battle (one base, both sides storm it)

Only one game window at a time: close a watched match first.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bridges  # noqa: E402
import watch_loop  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default="arland", choices=["arland", "everon"])
    ap.add_argument("--us", default="modern", help="the US commander (a strategist bridge: modern, phased, doctrine, llm...)")
    ap.add_argument("--ussr", default="phased", help="the Soviet commander")
    ap.add_argument("--extra", default="", help="more command-line settings for this game, after watch_extra.txt")
    a = ap.parse_args()
    extra_file = watch_loop.ROOT / ".runtime" / "watch_extra.txt"
    extra = (extra_file.read_text(encoding="utf-8").strip() if extra_file.exists() else "") + " " + a.extra
    bridges.ensure(tuple(x for x in (a.us, a.ussr) if x in bridges.BRIDGES))
    o = watch_loop.opts(a.map, False, a.us, a.ussr, f"play-{a.map}", solo=True, extra=extra.strip())
    o.watch = False   # no spectator: the game's deploy menu, a soldier of the side picked
    proc, profile = watch_loop.start(o, "solo")
    print(f"The game is starting (pid {proc.pid}): {a.map}, US {a.us} v USSR {a.ussr}. Pick a side and a base in the deploy menu.",
          flush=True)
    print(f"Log: {profile}", flush=True)
    proc.wait()
    print("The game was closed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
