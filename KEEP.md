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
- Soldiers fire at incoming drones and bring some down - a wave of USSR FPVs, 6 shot down in 20 game s by US machine gunners, squad leaders and a medic at 13-120 m, 34 soldiers engaging (report 010-good, 20 Oct 19:55). Breaks if: scorecard 'drones shot down' is 0 for a side whose soldiers had enemy drones near ([ZCR][DRONETHREAT] near>0), or no [ZCR][ANTIDRONE] shot_down=1 lines in a match with enemy drones; chart 'Fire at drones' on the engine page.
- Teams hold a tree line in cover while drones are overhead, and shoot them down from there - USSR team A9 along the road west of the Military Training Area under the pine crowns and by the rocks; USSR covered 67-86% near drones, squad leaders shot down two at 38/56 m (report 014-good, 21 Oct 21:02). Breaks if: scorecard 'panic' (safe near drones) under 60%, 'drones shot down' falls, [ZCR][DISPERSE] moved/open falls.
- A held village defended against a drone wave - US at Arleville shot down 7 USSR drones in a minute, D0's squad leader at 30/31 m from under the trees by the bunker (report 018-good, 21 Oct 21:07). Breaks if: scorecard 'drones shot down' falls; [ZCR][ANTIDRONE] shot_down per drone team sent.
- The storm (23 Oct, review note 329): a LAV-25 carries a rifle squad toward a defended position, stops 250 m short, the squad dismounts and assaults while an Abrams gives fire from overwatch and the LAV's crew stays aboard firing. Evidence: copy D:\work\zcr-guns, run storm-watch-20261023. Measure: integration test "storm" (lab/itests.toml: riders >= 6, dismount_m >= 200) and "crews-stay-aboard" (crew_out == 0).
- The drone operator (24 Oct, review notes 364-368; Martin: "this is fucking great!!!"): a 2-man team - the pilot in FPV goggles kneels at his post in cover with the drone controller in his hands and holds still while his FPV flies (his AI off for the flight), his guard beside him; "DRONE OPERATOR - flying FPV" on the watch screen; the camera shows him close up. Village storm 15:40 (videos/2026-10-24_1540_inftest-village-drones-def-dco-watch.mp4). Measure: [ZCR][OPERATOR] event=kit goggles=1 controller=1 per team, event=flying with at_post within 6 m, men=2 at event=post - no check in a scorecard yet (PLAN).
- Soldiers going into buildings from drones (24 Oct, note 366; Martin: "I really like how they go inside buildings"): DCO's garrisoning plus our runs into a building at danger priority, kept inside while a drone is near - farm storm 5 of 8 runs ended inside. Measure: the storm summary's ussr_shelter_in / ussr_shelter_runs and *_near_drone_covered (lab/inftest.py).
