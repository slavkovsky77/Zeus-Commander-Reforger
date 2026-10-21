---
name: goal
description: Turn the owner's wish or complaint about the AI into a goal in goals.toml - the wish in their words, the measure that shows it (from lab/measures.py, or a new one read from the server log), a target and the review note it came from. Use when the owner says what they want the AI to do or stop doing ("the AI should use supply trucks", "drones keep crashing into the water"), or asks to add, change, pause or drop a goal.
---

# A wish becomes a goal

1. **File the remark** as the next numbered review note (`paths.notes`, see `python lab/config.py`):
   the owner's words verbatim, the date, "goal: <id>". A remark that is only a question gets answered;
   not every remark is a goal.

2. **Find the number that shows it.** `python lab/measures.py --list` lists the measures. Pick the one
   that matches what the owner would *see* - not a proxy that is easy to count. Look at its value in
   the latest watched matches (`python lab/measures.py RUN_DIR`) so the target is grounded:
   - "the AI should use supply trucks" -> `truck_unloads` per side, `truck_first_min`, `front_supply_pct`
   - "drones crash into the water" -> `drones_lost_water` per match

3. **No measure fits?** Add one to `lab/measures.py`: find the log line that marks the event (grep a
   match's `console.log`; the commander's lines start with `[ZCR]`, AI Conflict's with `[AICF]`), count
   it in `extra()`, describe it in `MEASURES` (per side or per match). If no log line exists, add one in
   the code first (`fix` skill) - a goal you can't measure can't be met.

4. **Write the goal** into `goals.toml` (format at the top of the file): `id`, `title`, `wish` (their
   words, who, when), `notes`, `status = "active"`, `matches` (watched by default), `met_when`, and one
   `[[goal.measure]]` per number with its `target`. Order matters: the loop works on the first unmet
   goal - put it where the owner's priority says.

5. **Check it parses and reads right**: `python lab/goals.py` - the new goal shows with today's values.

6. **Add it to PLAN.md** under its theme: `- [Todo] wish (note numbers) | goal <id>: measure target`.

Tell the owner the goal in one line: the measure, today's value, the target.

Changing a goal: keep the history - edit the target or status, and say in the note why. A goal the
owner no longer wants: `status = "paused"`, not deleted.
