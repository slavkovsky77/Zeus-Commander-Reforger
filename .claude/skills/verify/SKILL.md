---
name: verify
description: Check that a change did what it was for - matches with the change against matches without it, the goal's measure before and after, and what the owner would see on screen (frames from the recordings). Use after every fix, and when the owner asks whether something works now.
---

# Did it work

1. **Before** - the goal's measure on the matches just before the change (`python lab/goals.py`,
   `lab/measures.py RUN_DIR`). Write the numbers down now; later matches overwrite "latest".

2. **After** - the same kind of match with the change:
   - Quick: one headless match with the same options, for a measure that headless shows (building,
     trucks, drone routes). Use the change's off-switch for an A/B on the same build when the
     difference is small.
   - Then the watched matches - the watched loop picks the change up from its next match. A goal
     judged on watched matches is verified there, not headless.

3. **Look, don't just count.** For what the owner sees, take frames from the recording at the
   moments the log names (`python lab/report.py good|bad "..." --at HH:MM:SS` gathers them) and look at
   them: is the truck on the road, the drone over land?

4. **Compare like with like**: the same map, strategists, mods and match length; several matches when
   the measure is noisy. One match is an anecdote, say so.

5. **The verdict, plainly**: fixed (before -> after, in how many matches), better but not met, no
   change, or worse (revert or rethink - say which). A change that doesn't move its measure is not a
   fix, even if the code looks right.

6. **Write it down** (`record` skill): the numbers into the note, PLAN.md and the changelog; the
   goal's status when it is met.
