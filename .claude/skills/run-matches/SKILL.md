---
name: run-matches
description: Start Arma Reforger matches for the commander lab - one headless match to test a change, a headless batch for numbers, or the watched loop (the game on screen, recorded) for what the owner sees. Use when matches are needed to measure a goal, test a fix, compile-check, or when the owner wants to watch.
---

# Running matches

Settings come from `lab/lab.toml` + `lab/lab.local.toml` (`python lab/config.py` checks them).
Server output goes to `.runtime/runs/<label>-<stamp>/`; the match log is `logs/*/console.log`.

**Which kind:**
- **Compile check** after any script change - 1 minute, no commanders:
  `python -u lab/reforger.py --map arland --minutes 1 --label compile-check --port 2146 --us none --ussr none`
  Pass: no `SCRIPT    (E)` lines about compiling, `[ZCR]` lines present.
- **One headless match** to test one measure quickly (1x speed, no window, several can run side by side
  on different ports): `python -u lab/reforger.py --map arland --minutes 16 --label <what> --port 2146
  --drones --us phased --ussr phased [--armour] [--extra="-zcrSomething"]`. Values starting with `-`
  need `--extra="..."` with the `=`.
- **Headless batch** for numbers across many matches: `python lab/batch.py --hours 6 --parallel 1`.
- **Watched loop** - the game on screen, recorded to `videos/`, the director camera, 3x speed in the
  game's diagnostic build: `python lab/watch_loop.py --hours 6 --rotation arland:phased:phased`.
  Per-match server extras: `.runtime/watch_extra.txt`. Stop between matches: create `.runtime/watch_stop`.
  It imports `lab/reforger.py` at start - restart it (`python lab/switch_loops.py watch`) when the
  runner's own options change; script changes are picked up from the next match.

**Which matches judge a goal:** what the owner watches (`matches = "watched"` in goals.toml). Headless
servers never crash the way a game client does and see no drones the way the screen does - use them
to iterate, then confirm on watched matches.

**Strategists:** `none` (AI Conflict alone), `doctrine` (rules), `phased`, `llm`, `llm-phased` - the
bridges start with `python lab/bridges.py`; the model's key is read from the file or variable in
`lab/bridge.local.json`, never printed or copied.

**Rules:**
- One game window at a time. Before stopping any game process, read its command line: stop only what
  this lab started (its `-profile` is under this repo's `.runtime/runs/`). Other sessions' and other
  projects' games are not yours.
- When the owner says stop playing, launch nothing.
- Recordings: delete only an unfinished `.mkv` when stopping; finished `.mp4` and `.md` stay.
- Long runs report back through `python lab/wait_result.py --minutes 45` or a background task -
  don't poll in a loop.
