---
name: good
description: The owner likes something they just saw in a watched commander match (e.g. "/good I love how those guys shot at the drones"). Gathers the evidence of that moment, names exactly which code made it happen, and keeps it as a regression check in KEEP.md. Use whenever the owner types /good or praises a behaviour they are watching.
---

# A good report from the watched match

What the owner likes is a behaviour to keep: it gets the same evidence as a bad report and becomes a
check against regressions.

1. **Gather the evidence** (the moment: their latest REPORT button press within 5 minutes, else 30 s
   before they wrote; `--at HH:MM:SS` if they name a time):

   ```
   python lab/report.py good "<their words, verbatim>"
   ```

2. **Read** `summary.md`, the three frames and `log.txt` in the printed folder. Name exactly what
   happened: which units (team keys, drone team numbers), which code made it happen (the drone reaction,
   the dismount, the drone search...), and the numbers that show it (e.g. dismount out of the objective's
   sight 440 m short, 6 soldiers reacting, scatter after the hit).

3. **Write it** into `summary.md` under "## Analysis" and into the review note ("analysis to follow" ->
   what worked and why).

4. **Keep it**: one line in `KEEP.md` - the behaviour, the evidence folder, and the measure that would
   show it breaking (a scorecard check, a measure in `lab/measures.py`, a log line to count). No measure
   yet: add one, or a PLAN.md item for it. Behaviour worth guarding goes into `goals.toml` as a
   `status = "met"` goal, so `lab/goals.py` flags it when it breaks.

5. **Reply** in a couple of plain lines: what you saw in the frames and the log that made it good, and
   that it's now kept as a check.

Never start a game window for this.
