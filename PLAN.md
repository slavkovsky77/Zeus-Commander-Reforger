# Reforger Commander - plan by theme

Martin's wishes and remarks, grouped by theme, with the review note numbers (ac-lab REVIEW_NOTES.md)
and where each stands. Kept up to date with every change; `python lab/plan_page.py` builds the page.
Status: **Done**, **In progress**, **Todo**, **Measure** (to measure first), **Fixed** (a bug).

## Watching and speed
- [Done] Run the game faster by any means (117, 123, 129) | The diagnostic build's Diag Menu > Cheats > DTime multiplier, only where the game hosts the match (solo): 2.0x measured at 60 fps. The watched loop sets it every match.
- [Done] Watch in a normal window with borders at full resolution (130) | The game opens in its own maximised mode from its settings file.
- [Done] Phone buttons like Arma 3: next / previous shot and group, lock, closer, wider, overview, auto, tap to follow (116, 170, 171, 178) | Under the BLUFOR panel; PREV/NEXT POINT to watch one base; BOTH SIDES / US ONLY / USSR ONLY; TEAMS / VEHICLES / DRONES - what PREV/NEXT steps through.
- [Fixed] Keyboard hijacked, Arma crashed, focus buggy at match start (198) | The speed is set by the game itself now (Diag Menu engine values), no key presses.
- [Done] Free look like the normal game; orbit round a locked unit, right mouse only (194, 195) | FREE LOOK button (WASD, Q/E, Shift); right-mouse drag turns the camera round any shot.
- [Done] A team's actual goal and IDs in the captions (196) | 'USSR team A3 (3 men) - ATTACK Moss Hill - 450 m to go - riding', TEAM GOAL marker.
- [Done] REPORT and good/bad reports with timestamps and logs (202) | REPORT button in the game; /good and /bad skills: the moment, the caption, the team's lines, frames from the recording, a numbered note and the analysis; good ones kept as regression checks.
- [Done] Recordings show only the game, never the desktop (126) | Windows Graphics Capture of the game window.
- [Done] Always sped up (144, 164) | Watched matches at 3x on Arland; headless servers can't (1x, several side by side).
- [Done] Follow a drone until it reaches its target, and stay on the explosion (144, 152) | The drone shot lasts while the drone flies (up to 2 min), then the camera stays on the impact point 4 real seconds at 2x.
- [Done] Try 3x (129, 164) | 3x on Arland: 2.99x at 54-60 fps, a match in 9.4 minutes, drones and soldiers as at 2x. The watched loop runs at 3x.

## The screen
- [Done] Make clear what is happening (125) | Plans in plain words, drones, latest events.
- [Done] Director closer on fights, for a while (149, 150) | Fights 60 m out for 22 s, assaults 70 m, storms 80 m, close-ups over the shoulder (14 m behind, 4 m up) on a soldier in contact.
- [Done] BLUFOR left, OPFOR right, like Arma 3's live logs (138) | Who commands, plan, now doing, drones, latest decisions; score and speed on top; losses, cover and stacking along the bottom.
- [Done] Supply chain and logistics overview for debugging (191) | SUPPLIES in each side panel: stock, main base, change a minute, supply trucks on the road; each base's stock on its label.
- [Done] Arma 3's colours: dark background, side colours, green captures (140) | Captures green, losses red, attacks and storms yellow.
- [Done] Drones visible on screen (125, 136) | An FPV tag on every drone, the camera at the drone's height.

## Soldiers
- [Fixed] Soldiers chilling at the base, all groups one guy (173) | AI Conflict started every team with 1 man and recruited the rest one at a time: teams waited 10-20 min. Now 3 of 5 at the start, out with 3: first team out at 1.8 min.
- [In progress] Reckless soldiers: fights at 1-6 m, nobody prone under drones (200) | Hold 60 m from a seen enemy, prone held under drones, cover spots spread 6 m (r19) - to verify.
- [Done] Drone panic as an optimisation target (201) | Charts and scorecard checks: safe near drones, drone victims standing / prone.
- [In progress] They walk across open fields like nothing is happening (125, 174, 197) | Each 220 m march step now ends in the best cover within 60 m (trees, roofs, buildings, walls) and teams jog; in a fight the game's attack still leaves cover after 5 s (r10 holds it 20 s).
- [In progress] Fight from cover like Arma 3 (30-40%) (113, 124, 133) | In the game's own cover 40% (AI Conflict alone 24-27%); Arma 3's stricter measure 9.5%.
- [In progress] Fireteams of 2-5, never single file down a road (135, 141, 159) | AI Conflict changed: 20 teams of 5 per side, wedge formation. Two-army probe: stacking 4.1% (Arma 3's limit 10%, first time under it), 3.6 soldiers a team, 8 m to the nearest friend.
- [In progress] Bounding: one half covers, the other moves (134, 146) | Refined (60-350 m from the enemy, 4+ men): USSR lost 5 instead of 14, exchange 3.4, two bases. On by default from 19 Oct 17:20; measured in every match.
- [Todo] Spacing against drones (118) | Teams apart from each other near the enemy.

- [Fixed] Enemy infantry chilling at the base, massacred by drones (181) | Drone searches camped the enemy's main base while teams waited there; searches now stay near the front.
- [In progress] Not out in the open - hide in cover, ideally buildings (182) | Idle soldiers anywhere go under a roof or canopy within 40 m, spread 6 m apart; buildings first and fortifications still to do.
- [In progress] Spread out within a team - one drone kills them all (183) | Near a drone each runs to his own spot 6-8 m apart; a wider formation needs our own formation config.
- [Done] Panic when a drone is heard: run, spread out, cover (184) | From 250 m: own covered spot within 40 m, else spread 15-25 m apart, then down. 89-93% react.
- [In progress] With drones about, run like hell to cover (166) | Soldiers within 150 m of an enemy drone run to overhead cover (canopy, buildings) within 30 m or get down; scatter after a hit. Both sides, from r15. Baseline: 89-100% of drone victims in the open.

## Vehicles
- [Fixed] They don't use vehicles at all (175) | Not one ride all day: AI Conflict refused every infantry team a vehicle. Infantry teams now ride light transport (M998, UAZ) on marches over 500 m: 20 teams rode in an 8-minute probe.
- [In progress] Light vehicles, not only trucks and APCs (128) | AI Conflict's light transport (M998, UAZ-452); no motorcycles in the vanilla game.
- [In progress] Drive to a point with cover, dismount, clear the position (128) | Out at the first spot 180-450 m short that the objective can't see; vehicles only for long marches from the main base (over 1 km).
- [Fixed] Vehicles have no tags - who is in them? (187) | A tag over each vehicle: side, vehicle, how many aboard; the camera cuts to vehicles on the move.
- [Fixed] No supplies transported by trucks (203) | AI Conflict had made dispatch manual-only; the automatic scheduler is back for the AI sides.
- [Done] Engineering and goals overview for each side (204) | GOALS in each panel: attack, hold, resupply, engineers now, built so far.
- [In progress] Build bunkers and defenses on points, used for cover; buildings for vehicles (186, 192, 204) | A FORTIFICATION type in our AI Conflict: Conflict's own bunker, two per base near the front; 800 starting supplies in the lab. To see in a match; sandbags, MG nests and defenders posted in them next. Was: AI Conflict's builders already build barracks, armory and vehicle depots with Conflict's building system; a fortification type (bunkers, sandbags, trenches) at points near the front is next, defenders posted in them.
- [Todo] Fireteams and 4-seat cars | A team of 5 fits a UAZ-452; teams of 4 would fit every light car.

## Drones
- [Fixed] 0 drones in the sky (172) | My rule "drones only where enemies are known" grounded them from 18:40 (0-3 teams a match). Now: a search when nothing is known, the drones spot for their side, AI Conflict's side every 2 min.
- [Done] Drone warfare doctrine: heavy drone use (118, 158, 160) | Prep fire while gathering, pressure during the assault; both sides fly drones. Two armies only: drones cause 60-79% of losses (front band 70-96%); drones go where enemies are known. A faster tempo gave nothing (the sites and teams in the air limit it).
- [Fixed] Drones fell at their spawn (122) | Launch spots clear of buildings and trees.
- [Fixed] Drones launched into the sea, then among their own soldiers (132, 137) | Never the sea; no clear spot, no team.
- [Done] Drones hang a minute not knowing what to do - always scan (185) | On after 15 s: to enemies seen, the next search point, or a 250 m sweep, then home.
- [In progress] Drones stop sometimes, stuck in the air (142, 147) | Measured: most lost drones hovered at their goal with nothing to hit (up to 18 a match). From 17:45: a team hovering a minute goes on to the nearest enemy its side saw; none for 2.5 min, it's called home.
- [In progress] Drone operators or drone trucks at bases; destroy them and that position has no drones (143, 155, 157) | Drone sites: a drone truck with a 2-man operator team at the main base, a forward one near the front (ready in 2 min, at most 3); truck destroyed or both operators dead: no drones from there, the main site rebuilt after 5 min; every third team goes for an enemy site the side has seen. Probe: both sides launched all match, 59 of 64 drones hit. Forward sites and counter-drone strikes still to be seen (Everon).

## AI Conflict
- [Fixed] The doctrine never planned on Everon with fireteams (151) | The situation report passed 8191 characters and was cut; now joined, not formatted.
- [In progress] Rework AI Conflict itself, fork it, don't hack around it - our own version (139, 177) | Local branch zcr: fireteams of 3-5 that leave at once, covered march steps at a jog, infantry riding light vehicles; its plumbing (spawning, supplies, capture) stays.
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
- [Done] How soldiers behave when drones come, in detail (167) | Near an enemy drone: % under cover, running, prone; drone victims in the open and standing; soldiers in the field with nothing overhead.
- [Done] A scorecard of what the screen shows, pass/fail per match (176) | lab/scorecard.py: first team out, % at the main base, team size, drone teams, drones up, rides - watched matches first. The measures before missed the regression.
- [Done] Team size and spacing to the nearest friend (141) | Charted from r13: 2.1-3.6 soldiers per team, 6-8 m apart (squads in single file: 3-5 m).

## Lab
- [Done] A plan and a page like Arma 3's, with a chapter for your remarks and one for bugs (145, 148) | This page.
- [Done] Two armies only, no FIA, for faster testing (154, 156) | -zcrNoFIA: FIA's bases split between the sides at the start, the front in the middle from the first minute; FIA's ambient patrols don't spawn. The watched matches run it from 18:09 (.runtime/watch_extra.txt).
- [Done] Our doctrine v our doctrine; AI Conflict alone only as a side check (189, 199) | Watched and batch: rules v rules, Gemini v rules, rules v Gemini, then rules v AI Conflict.
- [In progress] Skills for what Martin repeats, so it's reproducible (190) | /good and /bad done; next: run/restart the lab loops, republish the pages. Run/restart the lab loops, score a match with frames, log a remark into notes + plan + pages, republish the pages.
- [Todo] Short scenario tests (129) | Squads already 600 m from the objective, to test soldier changes in minutes.
