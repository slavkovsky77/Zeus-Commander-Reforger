# Reforger Commander - plan by theme

Martin's wishes and remarks, grouped by theme, with the review note numbers (ac-lab REVIEW_NOTES.md)
and where each stands. Kept up to date with every change; `python lab/plan_page.py` builds the page.
Status: **Done**, **In progress**, **Todo**, **Measure** (to measure first), **Fixed** (a bug).

## Night 20 Oct (Martin asleep 02:25-10:00; report https://claude.ai/artifact/CgNScfPGHX6GQCJnZpgBGb)
- [Done] Soldiers don't care about danger (212) | Danger layer: high danger never standing, medium crouched when still. In high danger standing 72% -> 10% (42 matches).
- [Done] Killed by drones outdoors with a house right there (211, 221, 222) | Prone every second within 150 m; buildings first; defend orders at the base's building cluster. Drone victims standing 91% -> 40%, prone 0.5% -> 26%.
- [Done] Infantry fires at drones with small arms (213) | Up to 3 shooters, MGs first; 21 shot down per side per match - balance to discuss.
- [Done] The next team walks into the kill zone of the previous one (208) | Kill zones: march steps keep 60 m away, high danger near them for 2 min.
- [Fixed] Vehicles crash into wrecks and get stuck (209, 218, 220) | Wrecks removed after 60 s (205 overnight); the watching camera no longer blocks rescues (failing 77% -> 34%).
- [Done] Combat vehicles in some cases | Every third team rides an armed light vehicle: 6.7 a side a match; riding 45% -> 69%.
- [In progress] Supply trucks not used by the AI (216, 224) | Our AI Conflict: dispatch restored; bases ask below 35% and are filled to 50%, a source keeps 200; lab income only at the main bases. Test: the truck takes its job but burns on the way to the main base to load - at the crash spot below.
- [Fixed] One side sits at its main base for 10+ minutes (228) | 85% of vehicle boardings timed out: the cover layer sent waiting teams into buildings 40-60 m away. Teams waiting for or boarding a vehicle are left alone: 54 boardings, none timed out.
- [Fixed] Watched matches stop on an assert (229) | The game's suppression sphere went NaN at its edge under our anti-drone fire; clamped.
- [Fixed] Vehicles blow up at two spots on the main bases' exit roads (226) | The world's TM-62M mine rows across both exit roads: 191 of 342 vehicles lost on 20 Oct. Our AI Conflict removes minefields on roads at the start. Not speed (A/B: median 12 km/h).
- [Todo] Cars wiggle left-right (217) | Stuck/recovery events as many at 1x as at 3x: the driving AI and wrecks, not the speed-up; to look at in the recordings.
- [Fixed] Point-blank gunfights (227) | A measuring error: the 'median 3 m' counted friendly kills (vehicle crashes, run over) and suicides. Enemy kills: median 30 m, 3% under 5 m.
- [Todo] Count AI opening road blocks and gates (219, KEEP.md) | Martin liked a US medic opening a road block.

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
- [Done] Reckless soldiers: fights at 1-6 m, nobody prone under drones (200, 212) | The 1-6 m were crashes and suicides counted as fights (enemy kills: median 30 m); the danger layer and prone under drones (r20): in high danger standing 72% -> 10%, drone victims prone 0.5% -> 26%.
- [Done] Drone panic as an optimisation target (201) | Charts and scorecard checks: safe near drones, drone victims standing / prone.
- [In progress] They walk across open fields like nothing is happening (125, 174, 197) | Each 220 m march step now ends in the best cover within 60 m (trees, roofs, buildings, walls) and teams jog; in a fight the game's attack still leaves cover after 5 s (r10 holds it 20 s).
- [In progress] Fight from cover like Arma 3 (30-40%) (113, 124, 133) | In the game's own cover 40% (AI Conflict alone 24-27%); Arma 3's stricter measure 9.5%.
- [In progress] Fireteams of 2-5, never single file down a road (135, 141, 159) | AI Conflict changed: 20 teams of 5 per side, wedge formation. Two-army probe: stacking 4.1% (Arma 3's limit 10%, first time under it), 3.6 soldiers a team, 8 m to the nearest friend.
- [In progress] Bounding: one half covers, the other moves (134, 146) | Refined (60-350 m from the enemy, 4+ men): USSR lost 5 instead of 14, exchange 3.4, two bases. On by default from 19 Oct 17:20; measured in every match.
- [Todo] Spacing against drones (118) | Teams apart from each other near the enemy.

- [Fixed] Enemy infantry chilling at the base, massacred by drones (181) | Drone searches camped the enemy's main base while teams waited there; searches now stay near the front.
- [In progress] Not out in the open - hide in cover, ideally buildings (182) | Idle soldiers anywhere go under a roof or canopy within 40 m, spread 6 m apart; buildings first and fortifications still to do.
- [Done] Spread out within a team - one drone kills them all (183) | Wedge instead of column (r20) and own spots near drones: median distance to the nearest friend 7-9 m before r19, 14 m on r19-r20 (target 10 m); stacking 6% (limit 10%).
- [Done] Panic when a drone is heard: run, spread out, cover (184) | From 250 m: own covered spot within 40 m, else spread 15-25 m apart, then down. 89-93% react.
- [In progress] With drones about, run like hell to cover (166) | Soldiers within 150 m of an enemy drone run to overhead cover (canopy, buildings) within 30 m or get down; scatter after a hit. Both sides, from r15. Baseline: 89-100% of drone victims in the open.

## Next (Martin, 20 Oct 14:00)
- [In progress] More vehicle types used in combat - APCs, tanks; mods if needed (243) | Armour units (ZCR_Armour, 21 Oct night): each side buys a tank (M1A1 / T-72) and an IFV (Bradley / BMP-1) from the armour mods (lab --armour, watched matches) at its HQ, crewed, sent to a support point short of the front, then into the base on Move waypoints so the crew stays aboard. Headless: all four bought and crewed at 2 min; the Abrams drove to Farm and killed with its gun. Being fixed: crews getting out (Search and Destroy searches on foot; now Move + remount), fronts on the side's own HQ, stuck spots near the main bases (probed). APC rides take the IFVs first (AI Conflict fork).
- [In progress] Better driving - road blocks stay (242, 244) | Our layers broke 77% of the gate openings (fixed); detours round checkpoints next.
- [Todo] See supplies, trucks and building on screen (239) | Base labels with stock/storage and 'asks for supplies'; supply truck tags (cargo, destination, doing) and overview markers; fortification and building-site markers with crews; director shots of trucks and building. Then shorter supply runs (nearest source) and more building in watched matches.
- [In progress] Supply trucks deliver (216, 224, 231, 235) | Fixed: road minefields, depot reserve, roads beyond a base's edge, long detours, depots first while a side has none (both sides in 3 of 3 tests). Added supply depots: the 2 bases nearest the middle, +150 a minute, any side loads while neutral. Testing.
- [In progress] Free soldiers build much more (231) | 5 fortifications per base within 2.5 km of the enemy, six types (bunker, MG nests, sandbags, tower), no reserve; idle teams joining the work if orders are no longer the limit.
- [Todo] AI lays mines on roads by its own decision (234) | Engineers lay mine rows on approach roads when the doctrine says so; own side knows and avoids them (AI drivers don't see mines). The world's road minefields stay removed by default.
- [Todo] Test on Yunakivka - trenches (233) | Installed: SH-Yunakivka 8.2.4 (6A2C1C65791CE941) and all six dependencies (SH-Trenches, Ukraine Trenches, ...). It ships RAAS/AAS only; AI Conflict runs on Conflict worlds (CTI_Campaign_Arland/Eden). To do: an AIConflictYunakivka addon with a Conflict world on the Yunakivka terrain (game mode, two main bases, 6-8 bases with radio coverage, spawn points), AI Conflict's map key and content profile for it, then headless and watched tests.

## Vehicles
- [Fixed] Vehicles stuck on an abandoned vehicle (237) | AI Conflict abandoned a stuck UAZ on a junction and kept it until its reuse pool was full; abandoned vehicles on a road are retired at once now.
- [Fixed] They don't use vehicles at all (175) | Not one ride all day: AI Conflict refused every infantry team a vehicle. Infantry teams now ride light transport (M998, UAZ) on marches over 500 m: 20 teams rode in an 8-minute probe.
- [In progress] Light vehicles, not only trucks and APCs (128) | AI Conflict's light transport (M998, UAZ-452); no motorcycles in the vanilla game.
- [In progress] Drive to a point with cover, dismount, clear the position (128) | Out at the first spot 180-450 m short that the objective can't see; vehicles only for long marches from the main base (over 1 km).
- [Fixed] Vehicles have no tags - who is in them? (187) | A tag over each vehicle: side, vehicle, how many aboard; the camera cuts to vehicles on the move.
- [Fixed] No supplies transported by trucks (203) | AI Conflict had made dispatch manual-only; the automatic scheduler is back for the AI sides.
- [Done] Engineering and goals overview for each side (204) | GOALS in each panel: attack, hold, resupply, engineers now, built so far.
- [In progress] Build bunkers and defenses on points, used for cover; buildings for vehicles (186, 192, 204) | A FORTIFICATION type in our AI Conflict: Conflict's own bunker, two per base near the front; 800 starting supplies in the lab. To see in a match; sandbags, MG nests and defenders posted in them next. Was: AI Conflict's builders already build barracks, armory and vehicle depots with Conflict's building system; a fortification type (bunkers, sandbags, trenches) at points near the front is next, defenders posted in them.
- [Todo] Fireteams and 4-seat cars | A team of 5 fits a UAZ-452; teams of 4 would fit every light car.

## Drones
- [Fixed] Drones crash into the water (236) | A third of all drones (537 in 28 matches) flew into the sea inlet south of the Military Training Area on our search sweeps; sweeps and goals never over the sea now. Drone mod (other chat): height over water should come from the water surface, not the sea bed.
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
