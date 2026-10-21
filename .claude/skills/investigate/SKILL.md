---
name: investigate
description: Find why a goal's measure fails or why the AI did something wrong - from the number to the match, the log lines of the units involved, and the code that decided it (this addon, the AI Conflict fork, or the game's own AI). Adds a lab probe when the logs don't say. Use after measure shows a failing goal, or when the owner reports a problem.
---

# From a number to a cause

1. **One match, one case.** Take the match where the measure failed worst and one concrete case: one
   truck job, one drone team, one squad. Averages don't have causes; cases do.

2. **Its log lines, in order.** `grep` the match's `console.log` for the unit (`job=L1_...`,
   `team=8`, `slot=A3`) and read its story end to end: orders, phase changes, the last line before it
   stopped. Put the clocks together (game seconds vs real ms: the wall clock at the line start). Look
   at what else happened at the same place and second (losses `[ZCR][LOSS]`, drone hits
   `[ZCR][DRONETHREAT] scatter`), not just the unit's own lines.

3. **The code that decided it.** The commander: `ZeusCommanderReforger/Scripts/Game/ZeusCommanderReforger/`.
   AI Conflict: the fork at `paths.ai_conflict` (`AIConflictCore/Scripts/Game/AIConflict/`). The game's
   own AI and API: `paths.reforger_api` (Bohemia's Script Diff). Find the line that logs the event
   and read back from it to the decision.

4. **The logs don't say?** Add a probe: a `-zcrSomethingProbe` option in `ZCR_SpotProbe.c` that prints
   `[ZCR][SOMETHING_PROBE]` lines with what you need (positions, owners, values), run one headless
   match with it, read the lines. Probes stay in the code, off by default.

5. **Measure before calling it a bug.** How often does it happen across matches? Is it the cause of the
   failing measure, or one of several? Check the other cases the same way until the pattern is clear.

6. **Write the finding down now** - into the goal's review note: what happened (unit, place, time),
   which code decided it, why that is wrong, how many cases. Then fix it (`fix` skill), or put it in
   PLAN.md when it is bigger than one change.

Things that are not bugs are findings too: the owner's remark measured and not confirmed is said
clearly ("measured: 2 of 40, not the cause").
