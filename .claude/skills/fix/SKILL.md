---
name: fix
description: Make a change to the commander AI or the AI Conflict fork in Enforce Script - the smallest change at the right place, a comment saying why (with the numbers), a compile check, a commit on the working branch. Use when an investigation has found a cause, or the owner asks for a change.
---

# Making a change

1. **The right place.** Change AI Conflict's own code in the fork (`paths.ai_conflict`, its working
   branch) when the behaviour is AI Conflict's - not a `modded class` workaround here. This addon
   (`ZeusCommanderReforger/`) holds the commander, the drones, the armour, the watching camera. Mark
   changed fork code with a `// ZCR (date): why` comment.

2. **The comment says why**, with the case and the numbers that led to it: "Built at a front base
   (the US at Farm) its trucks started under the enemy's drones - the first three drivers killed within
   2 minutes". Someone reading the code later has no other way to know.

3. **An option to turn it off** for A/B tests when it changes behaviour (`-zcrNoX` / `-aicfX`,
   `System.IsCLIParam`), and a log line that shows it working, so a measure can count it.

4. **Enforce Script pitfalls** that cost time before:
   - `%` in a float expression fails - compute an int first.
   - `vector / float` - write `v * (1 / len)`.
   - Don't name a variable `event`; avoid `string + int` (use `string.Format` or `.ToString()`).
   - `pose[3][1] = x` doesn't write through - use a temp vector.
   - An `out` parameter isn't read: pass a temp, not a variable holding a fallback.
   - Bash heredocs mangle backslashes (`\a` becomes a bell) - use the Edit tool for paths.

5. **Compile check** (`run-matches`): 1 minute headless, no script errors, `[ZCR]` lines present. The
   watched loop loads code from source at its next match - a compile error there costs a match.

6. **Commit** on the working branch, message: what changed and why, the numbers. Commit freely;
   **never push** and never publish without the owner's go-ahead.

Then `verify`.
