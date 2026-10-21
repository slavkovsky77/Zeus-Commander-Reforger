---
name: night
description: Run the improvement loop unattended while the owner is away or asleep - keep the PC awake, keep matches running, keep iterating on the goals, keep the pages current, and leave a morning report of what was done, measured and still open. Use when the owner says they are going to sleep, leaving for hours, "run overnight", or "continue while I'm away".
---

# Unattended runs

1. **Keep the PC awake** for the whole time - it sleeps after a few idle minutes and every match
   freezes:

   ```
   python lab/keepawake.py --hours 8
   ```

   (run it in the background). Arm a self-wake (a scheduled check-in every 20-30 minutes) so the session
   comes back even if a long run sends no notification; re-arm it each time it fires.

2. **Matches**: the watched loop if the owner wants recordings to watch in the morning, else a headless
   batch (`run-matches`). Note what runs, on which code, from when.

3. **Iterate** (`improve`): goal by goal, one change at a time, each verified before the next. Focused
   tests, not repeats of the same match. Don't run the same failing experiment twice without a change.

4. **Keep the pages current after every iteration** (`record`) - the owner may look from their phone
   at any time.

5. **The morning report**: a page (`[pages] night`) with
   - what ran (matches, hours, crashes),
   - each goal: before -> after, met or not (`python lab/goals.py`),
   - what changed (commits, one line each, why),
   - what is open and what you would do next,
   - every remark the owner made before leaving, with where it stands,
   - questions that need the owner's decision.
   Plain words, numbers with units, a chart where a trend matters.

6. **Stopping**: when the owner is back or says stop - stop the loops between matches
   (`.runtime/watch_stop`), stop keepawake, delete only an unfinished `.mkv`, launch nothing more.

Never push, never publish anything outside the owner's own pages, never stop other sessions' games.
