---
name: measure
description: Judge where the commander AI stands - every goal in goals.toml on the latest matches (lab/goals.py), the per-match screen checks (lab/scorecard.py), supply trucks and building (lab/trucks.py), any single measure (lab/measures.py). Use after matches finish, before choosing what to work on, when the owner asks "how is it going" or "did it get better", and to fill numbers into notes and pages.
---

# Measuring

```
python lab/goals.py                 # every goal on its last 3 matches; REGRESSION and Next lines
python lab/goals.py --last 5 --json # more matches; .runtime/goals.json for the pages
python lab/scorecard.py             # the latest watched and headless match, hard checks per side
python lab/scorecard.py --today     # every match of today, one line each
python lab/trucks.py --run RUN_DIR  # supply trucks job by job (how each ended), supplies, building
python lab/measures.py RUN_DIR      # every measure of one match
python lab/progress.py              # measurements per build (the engine page's charts)
```

**How to read them:**
- **Per match, not averages.** A goal is met when it passes in enough of its latest matches
  (`met_when`). Averages over a night hide the match the owner watched.
- **What the owner sees first**: watched matches, the screen checks. A headless pass is a hint.
- **A match still running is not a result**: its log is still growing; wait for it to finish.
- **Too few matches** is an answer - say it, and run more instead of guessing.
- **Units:** `[ZCR] t=` is game seconds (3x in watched matches); `[AICF] t_ms=` is real milliseconds
  since the server started; match the two by the wall clock at the start of each line.
- **Say what a number counts.** "3 unloads" means three truck loads delivered, both sides, in a 30
  game-minute match - say that, not "logistics improved".

When a number surprises you, look at the match it came from (log lines, frames from the recording)
before reporting it. A measure that counts the wrong thing is a bug in the measure: fix it and say so
(one night's "3 m gunfights" were crashes counted as fights).
