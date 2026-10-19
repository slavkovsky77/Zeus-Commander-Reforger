# Reforger Commander - plan by theme

Martin's wishes and remarks, grouped by theme, with the review note numbers (ac-lab REVIEW_NOTES.md)
and where each stands. Kept up to date with every change; `python lab/plan_page.py` builds the page.
Status: **Done**, **In progress**, **Todo**, **Measure** (to measure first), **Fixed** (a bug).

## Watching and speed
- [Done] Run the game faster by any means (117, 123, 129) | The diagnostic build's Diag Menu > Cheats > DTime multiplier, only where the game hosts the match (solo): 2.0x measured at 60 fps. The watched loop sets it every match.
- [Done] Watch in a normal window with borders at full resolution (130) | The game opens in its own maximised mode from its settings file.
- [Done] Phone buttons like Arma 3: next / previous shot and group, lock, closer, wider, overview, auto, tap to follow (116) | Under the BLUFOR panel.
- [Done] Recordings show only the game, never the desktop (126) | Windows Graphics Capture of the game window.
- [Done] Always sped up (144) | Watched matches at 2x; headless servers can't (1x, several side by side).
- [Done] Follow a drone until it reaches its target, and stay on the explosion (144, 152) | The drone shot lasts while the drone flies (up to 2 min), then the camera stays on the impact point 4 real seconds at 2x.
- [Todo] Try 3x and 4x (129) | Check drones, vehicles and the AI with the bigger time steps.

## The screen
- [Done] Make clear what is happening (125) | Plans in plain words, drones, latest events.
- [Done] Director closer on fights, for a while (149, 150) | Fights 60 m out for 22 s, assaults 70 m, storms 80 m, close-ups over the shoulder (14 m behind, 4 m up) on a soldier in contact.
- [Done] BLUFOR left, OPFOR right, like Arma 3's live logs (138) | Who commands, plan, now doing, drones, latest decisions; score and speed on top; losses, cover and stacking along the bottom.
- [Done] Arma 3's colours: dark background, side colours, green captures (140) | Captures green, losses red, attacks and storms yellow.
- [Done] Drones visible on screen (125, 136) | An FPV tag on every drone, the camera at the drone's height.

## Soldiers
- [In progress] They walk across open fields like nothing is happening (125) | The game's own attack leaves cover after 5 s and closes to 15 m; kills happen at 22-38 m. r10 holds the game's cover 20 s.
- [In progress] Fight from cover like Arma 3 (30-40%) (113, 124, 133) | In the game's own cover 40% (AI Conflict alone 24-27%); Arma 3's stricter measure 9.5%.
- [In progress] Fireteams of 2-5, never single file down a road (135, 141, 159) | AI Conflict changed: 20 teams of 5 per side, wedge formation. Two-army probe: stacking 4.1% (Arma 3's limit 10%, first time under it), 3.6 soldiers a team, 8 m to the nearest friend.
- [In progress] Bounding: one half covers, the other moves (134, 146) | Refined (60-350 m from the enemy, 4+ men): USSR lost 5 instead of 14, exchange 3.4, two bases. On by default from 19 Oct 17:20; measured in every match.
- [Todo] Spacing against drones (118) | Teams apart from each other near the enemy.

## Vehicles
- [In progress] Light vehicles, not only trucks and APCs (128) | AI Conflict's light transport first (M998, UAZ-452); no motorcycles in the vanilla game.
- [In progress] Drive to a point with cover, dismount, clear the position (128) | Out at the first spot 180-450 m short that the objective can't see; vehicles only for long marches from the main base (over 1 km).
- [Todo] Fireteams and 4-seat cars | A team of 5 fits a UAZ-452; teams of 4 would fit every light car.

## Drones
- [Done] Drone warfare doctrine: heavy drone use (118) | Prep fire while gathering, pressure during the assault; both sides fly drones; drones cause 37-50% of losses (front: 70-96%).
- [Fixed] Drones fell at their spawn (122) | Launch spots clear of buildings and trees.
- [Fixed] Drones launched into the sea, then among their own soldiers (132, 137) | Never the sea; no clear spot, no team.
- [In progress] Drones stop sometimes, stuck in the air (142, 147) | Measured: most lost drones hovered at their goal with nothing to hit (up to 18 a match). From 17:45: a team hovering a minute goes on to the nearest enemy its side saw; none for 2.5 min, it's called home.
- [In progress] Drone operators or drone trucks at bases; destroy them and that position has no drones (143, 155, 157) | Drone sites: a drone truck with a 2-man operator team at the main base, a forward one near the front (ready in 2 min, at most 3); truck destroyed or both operators dead: no drones from there, the main site rebuilt after 5 min; every third team goes for an enemy site the side has seen. Probe: both sides launched all match, 59 of 64 drones hit. Forward sites and counter-drone strikes still to be seen (Everon).

## AI Conflict
- [Fixed] The doctrine never planned on Everon with fireteams (151) | The situation report passed 8191 characters and was cut; now joined, not formatted.
- [In progress] Rework AI Conflict itself, fork it, don't hack around it (139) | Local branch zcr of the AI Conflict clone the lab loads; fireteams first.
- [Fixed] A side never recruited at Arland's harbour base (119, 132) | AI Conflict's barracks search at its maximum; the small barracks now builds, the large one still fails there.
- [Todo] Slow follow-on after a capture (109) | Squads walk 1-1.4 km in 220 m steps to the next base.

## Doctrine
- [Done] Arma 3's attack doctrine: gather, assault, commit, storm (99-110) | Storm takes the base in most matches 1-3 min after the order.
- [In progress] Careful or full storm (106) | Careful (25) by default.
- [Todo] Commit counts for fireteams | The plan commits 2 defender units; with teams of 5 that's 10 soldiers instead of 20.

## Measures
- [Done] Arma 3's soldier measures: cover, sitting ducks, stacking (113) | Every match, charted per build.
- [Done] Ground cover told apart from other cover; overhead cover against drones (114) | Ground, building, tree, vehicle, object; roof or canopy.
- [Done] How far the infantry walks, riding to the attack (127) | 270-890 m on foot; nobody rode yet.
- [Done] How the engine behaves: fighting distance, server fps (127) | 22-38 m; watched Everon servers had run at 12-18 fps.
- [Done] Team size and spacing to the nearest friend (141) | Charted from r13: 2.1-3.6 soldiers per team, 6-8 m apart (squads in single file: 3-5 m).

## Lab
- [Done] A plan and a page like Arma 3's, with a chapter for your remarks and one for bugs (145, 148) | This page.
- [Done] Two armies only, no FIA, for faster testing (154, 156) | -zcrNoFIA: FIA's bases split between the sides at the start, the front in the middle from the first minute; FIA's ambient patrols don't spawn. The watched matches run it from 18:09 (.runtime/watch_extra.txt).
- [Todo] Short scenario tests (129) | Squads already 600 m from the objective, to test soldier changes in minutes.
