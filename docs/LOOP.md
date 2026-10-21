# The self-improvement loop

How this repo improves the AI: someone watches matches and says what they want, and Claude turns that
into goals with numbers, runs matches, finds causes in the logs, changes the code and checks the
change in more matches. Everything it learns is written down so the next session, or another person,
can pick it up. The steps are Claude Code skills in `.claude/skills/`. You can run your own goals with
them: write your wishes into `goals.toml`, or tell Claude and it writes them there.

## The pieces

| What | Where | Kept by |
|---|---|---|
| Goals: each wish with the numbers that say it is met | `goals.toml` | `goal` skill |
| Measures: the numbers, read from a match's server log | `lab/measures.py` (+ `lab/scorecard.py`) | `goal` skill |
| Where the goals stand on the latest matches, and the next goal | `python lab/goals.py` | `measure` skill |
| Every remark the owner makes, numbered, with its finding | `paths.notes` in `lab/lab.toml` | `good`, `bad`, `record` |
| The wishes by theme and their status | `PLAN.md` | `record` skill |
| Behaviour the owner liked, kept as regression checks | `KEEP.md` | `good` skill |
| What changed, build by build, and why | `lab/engine_page.py` (changelog), git log | `record` skill |
| Pages the owner reads (engine, changelog, plan, goals, night report) | `[pages]` in `lab/lab.local.toml` | `record` skill |
| This machine's paths and page links | `lab/lab.local.toml` (not committed) | `lab-setup` skill |

## One iteration (`improve`)

```
 goals.toml ──> measure ──> next goal ──> investigate ──> fix ──> verify ──> record ──┐
     ^            (goals.py)    (first      (logs, probes,   (code,    (same       (notes,  │
     │                          active,      code: the       compile   matches,    PLAN,    │
     │                          not met)     cause)          check,    before/     pages)   │
     │                                                       commit)   after)               │
     └──────────── the owner watches, says good / bad, adds wishes (goal, good, bad) <──────┘
```

1. **measure** - `python lab/goals.py` judges every goal on its latest matches. A met goal that broke
   is a regression and comes first; then the first active goal that is not met.
2. **investigate** - from the failing number to the cause: which log lines, which unit, which code
   decided it. Measure before calling anything a bug; add a probe when the logs don't say.
3. **fix** - the smallest change at the right place (this addon, or the AI Conflict fork), a compile
   check, a commit on the working branch. Never a push.
4. **verify** - matches with the change, the goal's measure before and after, and what the owner
   would see on screen (frames from the recordings).
5. **record** - the review note's finding, `PLAN.md`, the goal's status, the changelog, the pages.

The owner watches matches meanwhile and reports with `good` and `bad` (or the in-game REPORT button);
each report becomes a numbered note, and a wish becomes a goal.

## Rules the loop keeps

- **Judge what the owner sees.** Watched matches and hard checks per match, not batch averages.
  A headless batch can look fine while the watched matches collapse.
- **Measure first.** A remark is a thing to verify in the logs; say clearly when it is verified.
- **One change, then verify it.** Before/after numbers in the note and the changelog; a fix that
  doesn't move its measure is not a fix.
- **Write it down the same session.** Every remark into the notes, every change into the
  changelog and PLAN, the pages republished.
- **Never push, never publish without the owner's go-ahead.** Commit freely to the working branches.
- **Leave other people's processes alone.** Check a game process's command line before stopping
  anything; only stop what this lab started.

## Running your own goals

1. `lab-setup`: fill `lab/lab.local.toml`, check `python lab/config.py`, compile check, one match.
2. Write a goal (`goal` skill, or edit `goals.toml`): the wish in your words, a measure, a target.
   If no measure fits, the skill adds one to `lab/measures.py` (it reads the server log).
3. `improve`: one iteration, or `night` for many while you sleep (a report in the morning).
4. Watch a match (`run-matches`, watched) and say `good` or `bad` about what you see.
