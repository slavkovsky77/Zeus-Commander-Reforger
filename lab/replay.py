"""Re-run recorded situation reports through a strategist, without the game: try a model or a new
doctrine prompt on real match situations and compare with what was decided then.

    python lab/replay.py <profile>/zcr/snapshots.jsonl                # rules doctrine
    python lab/replay.py snapshots.jsonl --config lab/bridge.local.json --faction USSR --every 2

Prints, per report, the plan the strategist would make. Nothing is sent to the game.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import providers  # noqa: E402
from bridge import doctrine_text, load_config  # noqa: E402
from plan import validate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshots")
    ap.add_argument("--config", default="")
    ap.add_argument("--faction", default="")
    ap.add_argument("--every", type=int, default=1, help="use every n-th report")
    a = ap.parse_args()
    cfg = load_config(a.config)
    provider = providers.make(cfg)
    text = Path(a.snapshots).read_text(encoding="utf-8")
    try:
        one = json.loads(text)   # a single report (.json)
        reports = one if isinstance(one, list) else [one]
    except ValueError:           # one report per line (.jsonl, as the game writes them)
        reports = [json.loads(l) for l in text.splitlines() if l.strip()]
    reports = [r for r in reports if not a.faction or r.get("faction") == a.faction][::a.every]
    for r in reports:
        try:
            decision, raw, seconds = providers.timed(provider, r, doctrine_text(cfg, r.get("faction", "")))
            clean, problems = validate(decision, r)
            print(f"{r.get('faction')} t={r.get('t')}s ({seconds}s): {clean['intent']}")
            print(f"   main {clean['main_effort']} support {clean['supporting']} hold {clean['hold']}"
                  f" avoid {clean['avoid']} {clean['concentration']}" + (f"  problems: {problems}" if problems else ""))
        except Exception as e:
            print(f"{r.get('faction')} t={r.get('t')}s: FAILED {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
