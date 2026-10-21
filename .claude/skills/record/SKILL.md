---
name: record
description: Keep the lab's paper trail current - the review note's finding, PLAN.md, the goal's status in goals.toml, KEEP.md, the changelog and engine page, and republishing the owner's pages (engine, changelog, plan, goals, night report). Use after every fix, verification or remark, and at the end of every iteration - the same session, not later.
---

# Writing it down

After every change or finding, all of these - in the same session:

1. **Review note** (`paths.notes`): the note's status column gets the finding - what it was, the
   change (commit), before -> after. A new remark gets a new number.

2. **PLAN.md**: the item under its theme - `[Done]`, `[In progress]`, `[Fixed]`, `[Todo]`, `[Measure]` -
   and where it stands in one line with the numbers.

3. **goals.toml**: `status = "met"` once `python lab/goals.py` says MET (it stays as a regression
   check); a new measure or target when the investigation showed the old one counted the wrong thing.

4. **KEEP.md**: behaviour the owner liked (`good` skill), with the measure that would show it breaking.

5. **Changelog**: the current build's entry in `lab/engine_page.py` (`CHANGELOG`) - what changed and
   why, the numbers; a new build (`BUILDS` in `lab/progress.py`) for a milestone. The engine page's
   `VERDICT` and `PROBLEMS` when the picture changed.

6. **Pages**: rebuild and republish every page listed under `[pages]` in `lab/lab.local.toml`
   (empty: publish a new one and write its link there):
   ```
   python lab/engine_page.py <scratch_dir>        # engine + changelog
   python lab/plan_page.py <scratch_dir>          # the plan by theme
   python lab/goals.py --html <scratch_dir>/goals.html   # the goals page
   ```
   Publish each to its existing link so the owner's bookmarks keep working.

7. **Commit** the notes and pages' sources with the code they describe.

Write for the owner: plain words, the game's own terms, numbers with their units, no jargon. A page
that says "fixed" must have the before -> after that shows it.
