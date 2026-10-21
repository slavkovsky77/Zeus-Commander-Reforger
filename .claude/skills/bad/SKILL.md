---
name: bad
description: The owner reports something wrong they just saw in a watched commander match (e.g. "/bad following USSR team A3: crossing an open field where cover was available"). Gathers the log and recording frames of that moment, finds the cause and files it as a numbered review note. Use whenever the owner types /bad or reports a problem they are watching right now.
---

# A bad report from the watched match

The owner watches a match on screen and reports what they saw. Don't guess: the evidence for that
moment is in the logs and the recording.

1. **Gather the evidence** - the moment is their latest in-game REPORT button press within 5 minutes,
   else 30 s before they wrote; `--at HH:MM:SS` if they name a time:

   ```
   python lab/report.py bad "<their words, verbatim>"
   ```

   It prints the report folder (`.runtime/reports/NNN-bad/`) and the review note number, and files the
   note in the review notes (`paths.notes`).

2. **Look at it yourself:**
   - `summary.md`: the match, the game time, the caption on screen, the REPORT lines, the team, the scorecard.
   - The frames `frame_-10s.jpg`, `frame_+0s.jpg`, `frame_+5s.jpg`: confirm you see what they describe.
   - `log.txt`: the commander's lines around the moment and every line of the named team (`slot=A3`,
     `team A3`): its orders and goal, cover and drone reactions (`[ZCR][DISPERSE]`, `[ZCR][DRONETHREAT]`),
     march steps, vehicle trips, losses (`[ZCR][LOSS]` with stance, moving, cover, overhead).

3. **The cause** (`investigate` skill): what the soldiers did, which code decided it, why that was
   wrong. Measure how often it happens before calling it a bug.

4. **Write it down**: the analysis into the report's `summary.md` under "## Analysis"; in the review
   note replace "analysis to follow" with a one-line finding (cause; fixed / to fix / not a bug).

5. **Small and clear fix**: make it (`fix` skill), compile-check, commit, PLAN.md item. Bigger: a PLAN.md
   item, and a goal if it is something to keep measuring (`goal` skill).

6. **Reply** in a few plain lines: what the frame and the log show, the cause, what changed or what's
   planned. No headings or tables.

Never start a game window for this; never stop other sessions' games.
