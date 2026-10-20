# Keep - what Martin liked, and the measure that shows it breaking

Each line: the behaviour, the evidence (`.runtime/reports/NNN-good/`, review note), and what to watch so a later
change that breaks it shows up.

- **Soldiers open road blocks themselves** - "cool, US medic opened road block" (report 004, note 219; seen before
  02:20 on 20 Oct, the exact moment not given). Measure: not counted yet - to add: barrier and gate actions by AI
  in the log (the game's own smart actions), per match.
- **Small-arms fire brings drones down** - the same report's frames (02:28): "medic shot down an enemy drone at 16 m",
  "rifleman shot down an enemy drone at 33 m" in the US feed. Measure: scorecard "drones shot down" per side
  ([ZCR][ANTIDRONE] shot_down=1), 10 in the 02:23 match.
- **Drone attack, then soldiers getting out of the car react** - "this drone attack and the reaction from NPCs getting
  out of the car was great" (Martin's example, 19 Oct). Measure: scorecard "panic" (safe near drones) and "down"
  (drone victims standing).
- **Vehicle dismount out of the objective's sight** - "vehicles disembark worked, nice" (19 Oct 22:09). Measure:
  [ZCR][DISMOUNT] per match, scorecard "rides".
- **Soldiers hide in the buildings** - "great, our soldiers hide in the buildings" (19 Oct 22:20). Measure: [ZCR][DISPERSE]
  moved / idle in the open; chart "In the open in the field".
