"""The Reforger commander's engine page and changelog - the same two pages as the Arma 3 lab's
(how it works now with per-build charts; every build's history), built from the lab's own files.

    python lab/engine_page.py <out_dir> [--changelog-url URL]

Writes <out_dir>/reforger_engine.html and <out_dir>/reforger_changelog.html. The prose below is kept
by hand as the work goes; the charts and the probe table come from the match logs (progress.py).
"""
import html
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import progress  # noqa: E402
import probe_report  # noqa: E402

E = html.escape
STATUS_URL = "https://claude.ai/artifact/NRTbYF1byVzTPtECaAyVhy"
RESEARCH_URL = "https://claude.ai/artifact/HeQBbPV4PanCcGWGRBmAGp"
ARMA3_URL = "https://claude.ai/artifact/8iF2jyqs5rgjxxbQUKtqWx"

VERDICT = {
    "Running now": "The watched loop at 2x (1.5x on Everon), two armies only (no FIA), fireteams of 5, drone trucks with operators, Arma 3's side panels; a headless head-to-head beside it at 1x.",
    "Today's result": "Working with the game's own cover (r10) gave the best headless match so far: 4-2 in bases, exchange 1.36, soldiers in the game's cover 40% of the time (AI Conflict alone 24-27%). Reforger runs at 2x in solo; drones now show on screen.",
    "Being built next": "Measuring fireteams, bounding and drone sites in the two-army matches; drone sites moving forward with the front; riding to the attack more often.",
}

# (chip class, chip text, title, text) - what changed most recently.
NOW = [
    ("good", "r14", "Drones where enemies are known",
     "In the two-army matches drones were sent to enemy bases nobody had been seen at and hovered there until lost (23 of 84 hit). Now a team goes to an enemy-held objective only if enemies were seen near it - else to the nearest enemy seen within 1.5 km, or no team. Next watched match: 25 of 36 hit (69%), drones 62% of losses, the US +1 with a loss ratio of 1.35. A faster tempo (60 s, 4 up) gave nothing - the drone sites and the teams in the air are the limit."),
    ("good", "r14", "Two armies: stacking under Arma 3's limit",
     "With fireteams and no FIA, stacking is 2-5% (Arma 3's limit 10%, first time under it), teams of 3 soldiers 7-8 m apart; drones cause 60-79% of losses - inside the front-line band of 70-96% in the best matches."),
    ("good", "r14", "Two armies only, drone trucks",
     "Your test scenario: -zcrNoFIA splits FIA's bases between the two sides at the start, so the front is in the middle from the first minute; the base game's ambient FIA patrols (which spawn near any player, the camera too) are blocked. Drones launch only from drone sites - a drone truck with a 2-man operator team, at the main base and later a forward base; destroy the truck or both operators and that base has no drones (the main site is rebuilt after 5 min); a side that has seen an enemy site sends every third team at it."),
    ("good", "r13", "Fireteams of 5, changed in AI Conflict itself",
     "AI Conflict now runs 20 teams of 5 per side (12 attack, 8 defend) in a wedge instead of 10 squads of 10 in single file - the same 100 soldiers. First measures: 2.3 soldiers per team on average (teams fill one by one), 7.5 m to the nearest friend in the field (a squad in single file sat at 3-5 m). The doctrine commits 4 defender teams."),
    ("good", "r13", "Bounding on by default",
     "Refined Arma 3 bounding (two halves, one covers while the other moves 35-60 m; only with the enemy 60-350 m away and 4+ men): the probe lost 5 instead of 14, exchange 3.4, two bases taken."),
    ("good", "watch", "Arma 3's side panels, closer on fights, drones to the end",
     "BLUFOR left, OPFOR right, in Arma 3's colours: who commands, plan, what its teams do now, drones and drone sites, the latest decisions (captures green, losses red, plans and storms yellow); score, game time and speed on top; losses, cover and stacking along the bottom. Fights from 60 m, close-ups over the shoulder; a drone is followed until it hits and the camera stays on the explosion; stuck drones get a new target after 25 s."),
    ("bug", "r13", "A cut situation report",
     "With 20 fireteams on Everon's 39 bases the report passed 8191 characters, where string.Format stops - the bridge couldn't read it and the doctrine never planned (watched Everon 17:13). Now joined, not formatted."),
    ("good", "r10", "Best headless match so far",
     "First headless match with the cover layer working with the game's own cover: the USSR doctrine took Moss Hill at 10.7 min, then Arleville and Signal Hill - 4-2 in bases, exchange 1.36, 14 lost. Our soldiers sat in the game's own cover 40.5% of the time (AI Conflict alone 24-27%); drones caused 50% of all losses, ours killed 78, 2 lost to theirs. Arma 3's stricter measure (something solid within 3 m toward the enemy) still reads 9.5% - the game's cover includes leaning out to shoot."),
    ("good", "watch", "Drones on screen, the picture fills the window",
     "Every drone in the air carries an 'FPV US / FPV USSR' tag, and the drone shot follows 16 m behind at the drone's height (before, it looked at the ground 30 m below from 45 m away - the drone was off the picture). The solo game opens in its own maximised window mode at the screen's resolution; resizing it from outside had left the picture at 1280x720 in a corner."),
    ("risk", "r12", "Covered dismount: third try",
     "Routing the vehicle to a hidden road point beside the objective sent the trucks the long way round, away from it. Now the squad rides AI Conflict's own route and gets out at the first spot 180-450 m short that the objective can't see. Probe running."),
    ("bug", "drones", "Two harbour bugs on Arland",
     "Arland's harbour main base: the drone launch spot search took the flat sea for level ground (60 drones lost in the water), and my first fix fell back to the base's own centre - the drones then went off among the side's own soldiers (57 lost in one probe). Now: never the sea, searched out to 250 m, no clear spot - no team. AI Conflict's barracks search there also ran out of budget (that side never recruited): lab servers now give it its maximum."),
    ("risk", "bound", "Bounding: not yet",
     "Arma 3's bounding (two halves, one covers while the other moves 35-60 m) made the first probe worse: 46 lost instead of 14 - squads bounded with the enemy 14 m away and down to 2 men. Refined to 60-350 m from the enemy and 4+ men; off by default."),
    ("good", "speed", "Reforger runs at 2x - like Arma 3's watched games",
     "The game's diagnostic build has a Diag Menu (hold Win+Alt) with Cheats > \"DTime multiplier\" (0.01-20x): each frame advances the game that much further. Measured: 30 game seconds in 15.0 real seconds, 60 fps steady, drones 16 of 16 hits. It works only where the game hosts the match itself (solo), not on a dedicated server - the same rule as Arma 3's setAccTime. The watch loop now runs solo at 2x, set automatically by key presses, in a normal maximised window; the headless matches stay at 1x beside it. (Earlier today I said it wasn't possible: I had searched the game for 'time scale', not 'DTime'.)"),
    ("design", "r12", "Covered dismount on light vehicles (first design)",
     "Your direction: modern combat is driving to a point with cover, dismounting there, then clearing the position. AI Conflict drives a motorized squad to the road nearest the objective and lets it out 150 m short, in the open. For our side the vehicle now stops 200-400 m short at the nearest road point the objective can't see (a crest, a treeline or buildings in between), and the squad goes on on foot. Motorized squads get light vehicles first (US M998, USSR UAZ-452; trucks only when the squad doesn't fit) - there are no motorcycles in the vanilla game. Probe running."),
    ("good", "r11", "How far the infantry walks, riding to the attack",
     "Arma 3's two measures, from the squads' reports (each now says whether its leader rides): today attacking squads walk 270-710 m on foot to their objective (median per match; Arma 3's target 300 m), and none rode."),
    ("design", "r11", "How the engine actually behaves",
     "New engine measures from every match: Reforger's AI kills at a median 22-38 m - close range: the game's attack logic walks a soldier on until he is 15 m from his target. Watched Everon matches ran their server at 12-18 fps (headless 49-60): the match on screen had the least computer to think with - now it runs solo on its own."),
    ("risk", "r10", "Cover: work with the game, not against it",
     "Second cover probe: from cover fell to 5.3%. Reading the game's own attack logic: a soldier in cover moves on after 5 s when not under fire, keeps closing to 15 m, and our stance request cancelled his move to cover. Now our layer leaves soldiers in or moving to the game's cover alone, makes them hold it 20 s (Arma 3's value), and asks the game's own cover search for soldiers in the open. The game's own in-cover share is charted too (US side, AI Conflict alone: 27%). The r10 probe didn't test it - our drones killed Moss Hill's garrison before our soldiers arrived."),
    ("design", "watch", "A clearer panel, the game window only",
     "The panel says what is happening in plain words: the score and game time, each side's commander (our doctrine, with Gemini, or AI Conflict alone) and its plan, drone teams sent and in the air, and the last three events (captures, storms, drone teams). Recordings now capture the game window only - before, they showed the desktop (VS Code, a browser, a notification) whenever you used the PC."),
    ("good", "r9", "A soldier layer: cover in a firefight",
     "Arma 3's fn_coverFight on Reforger, for our strategist's side: a soldier who knows an enemy within 400 m and has nothing solid toward it moves to the nearest covered spot within 25 m (the game's own individual move; not the squad leader, not in a storm). Probe: 90% of the soldiers in contact stood in the open; fighting from cover rose to 11.6% from 1.4-6.7%, and the attack took Moss Hill and Arleville as before. Arma 3 reached 30-40%: prone where there is no cover and staying in cover come next."),
    ("design", "r9", "Drones hunt enemy soldiers",
     "Every other launch goes for the biggest group of enemy soldiers a side has seen (5+ within 100 m). It hasn't fired yet: both armies mostly fight FIA garrisons and seldom see each other, so drones hit FIA."),
    ("good", "r8", "Drones wear them down, a short storm finishes",
     "First headless match with the drone doctrine: the USSR took Airport Base at 13.7 min and Farm at 21 min, each 75 s after the storm order (before drones, 5-12 min), and was storming a third base at the end - 3-2, the USSR lost 16. Drones caused 49% of all losses (front band 70-96%). On screen, Everon: Old Wood 3 min after the storm, the US lost 4."),
    ("design", "r8", "Drone warfare doctrine",
     "Your direction: modern combat, heavy drone use. The doctrine names drone targets: FPV prep fire on the objective while the force gathers, and pressure during the assault and storm - a team every 90 s, up to 3 in the air. AI Conflict's side flies drones too (every 4 min, at its squads' main target), and the headless matches load the drone mods, so drones count in every measurement. Judged like the Arma 3 page: the drones' share of losses against the front-line band 70-96%."),
    ("design", "r8", "The attack sized by what the side has seen",
     "As on Arma 3, the AI never cheats: each side remembers the enemies its soldiers saw in the last minute, and the situation report gives each base the known defenders. The force needed is twice the known defenders plus 4 (at least 25), and the storm comes once our soldiers near the objective see 2 or fewer defenders left - else after 4 minutes, as before."),
    ("good", "r7", "Watch buttons work",
     "Tested on screen with taps sent like a phone stream: NEXT, CLOSER, a tap that picked up a US squad leader (the camera follows him, LOCKED), AUTO back to the director."),
    ("good", "r7", "Arma 3's soldier measurements",
     "Same definitions as the Arma 3 page: fighting from cover (of the soldiers who know an enemy within 300 m, something solid within 3 m toward the nearest, or a roof), sitting ducks (deaths standing or lying still in the open), stacking (6+ friends within 25 m, counted in the field - AI Conflict gathers its recruits at the main base). First numbers: from cover 5-8%, sitting ducks 27-63%, the USSR assault force 69-90% stacked. These are the biggest gaps to Arma 3."),
    ("design", "r7", "Which cover, and what hides from drones",
     "Each covered soldier's cover is named: toward the enemy the ground (a crest), a building, a tree, a vehicle or another object; overhead a roof or tree canopy - what hides him from a drone, which a crest doesn't. Every death logs both, so we can see whether canopy saves soldiers from FPVs."),
    ("design", "r7", "The watch buttons",
     "For watching on the phone: PREV / NEXT SHOT, PREV / NEXT GROUP, LOCK, ACTION, CLOSER / WIDER, OVERVIEW, AUTO; a tap on a soldier or vehicle follows it, elsewhere the camera flies there for 30 s. The tap is read a moment late (the phone stream clicks before it moves, note 80)."),
    ("risk", "r7", "Careful storm: mixed so far",
     "Moss Hill probes: careful (25) took it once in two (15 and 32 lost); full (1000) three in three (28-46 lost). Careful is the default now and the headless matches will tell."),
    ("good", "r6", "A careful storm",
     "On Arma 3 you wanted soldiers who move cover to cover, and the storm made them run in. A storm order raises the "
     "priority of the attack orders, and Reforger's soldiers stop taking cover to follow them. At priority 25 the squad "
     "still keeps advancing, but soldiers drop into fire positions and shoot. Moss Hill probe: taken 10.8 min after the storm "
     "order (full storm: 8-12.5 min), and the USSR lost 15 soldiers around it instead of 28-39, while FIA lost about the same (36)."),
    ("design", "r6", "Why priority 100 and 1000 were the same",
     "Reforger adds a waypoint's priority to the group's move (50; fighting a spotted enemy group is 70) and to each soldier's "
     "formation movement (30; taking a fire position 60, attacking a chosen target 90). Anything over 60 overrides all of "
     "that, so 100 and 1000 behave alike - the probes agreed (39 lost in both). Only danger reactions with their own +1000 "
     "still win."),
    ("risk", "r6", "Trucks from the start cost more than they save",
     "AI Conflict's own commander never gives infantry a vehicle - only a player can make a squad motorized. Our doctrine "
     "now can, through the same call. First probe: squads spent minutes walking to truck spawn sites and boarding, 12 trucks "
     "were abandoned, 7 trips fell back to walking, and the side took nothing in 28 min. Next: trucks only for the long "
     "marches to the next base (1-1.4 km), where squads took 7-18 min on foot."),
    ("good", "r4", "Storm takes the hill",
     "Squads used to stop 300-600 m short and trade shots for 20+ minutes. With storm, Moss Hill fell in every clean match, at "
     "15-20 min; headless, the USSR doctrine went from 1-2, 1-2 to 3-2, 2-1, 3-2."),
    ("bug", "r5", "Two matches shared one memory",
     "The watched and the headless match used the same strategist bridge, and the doctrine remembered its phase per side only, "
     "so two matches with the same strategist on the same side reset each other. Now memory is per match and side."),
]

FLOW = """flowchart LR
  G[AI Conflict<br/>squads, supplies, bases] -->|every 90 s: situation report| B[Strategist bridge<br/>Python: rules or Gemini]
  B -->|plan: priorities, demand,<br/>commit, storm, motorize| C[Our commander layer<br/>ZeusCommanderReforger]
  C -->|scores and orders| G
  C -->|camera shots, overlay| W[Watcher's game<br/>recorded]"""

PHASES = [
    ("Pick", "Our rules, or Gemini with your doctrine text, choose the objective among the bases AI Conflict can attack (reached by the radio network)."),
    ("Gather", "The staging base (ours, nearest the objective) is the main effort; the objective is avoided so nobody walks in alone. Go at 25 soldiers there, 60% after 5 min, or after 10 min."),
    ("Assault", "The objective is the main effort with a heavy demand. While none of our bases is being captured, 2 of AI Conflict's 4 defender squads join (commit)."),
    ("Storm", "4 min into the assault, with 60% of the force sent there: the attack orders get a higher priority so the squads go in (r6 probes: 25 careful, 1000 full)."),
    ("Called off", "No capture 10 min after the force got there with nobody on the objective, or 15 min with soldiers on it, or 20 min from the order - never while the base is being seized. The next pick avoids it."),
    ("Bled out", "After 6 min, fewer than 35% of the needed soldiers still sent there: back to gather with a bigger need."),
    ("Follow-on", "A base taken and the force still near: straight on to the next one (momentum), defenders released and committed again."),
]

DRONES = ("When a doctrine side attacks, it launches a team of 4 FPVs from your FPV AI Drones mod at its own base nearest the "
          "objective; the drones fly a Move waypoint there and go for soldiers within 200 m (every third team for vehicles). At "
          "most 2 teams in the air per side, a new team every 4 minutes. Watched matches only so far, and only the doctrine side: "
          "4-6 teams, 10-16 strikes, 8-21 kills per match, all FIA so far.")

CAMERA = [
    ("CAPTURE", "a base changed hands in the last 40 s"),
    ("STORM", "a side storms a base - the climax of an assault"),
    ("FPV DRONE", "cut to a team as soon as it is airborne, follow one until it hits, 4 s on the impact"),
    ("COMMANDER", "a side's main effort moved to another base, with the commander's intent"),
    ("ASSAULT / FIGHT", "a side's soldiers massed at a base they don't hold, or US against USSR; close-ups follow"),
    ("ON THE MOVE", "the soldier or vehicle farthest out in the field"),
    ("OBJECTIVE / STAGING", "instead of a repeated hot zone: each side's main effort in turn"),
    ("HOT ZONE", "both main efforts and the fights, at most 2.2 km across"),
]

PROBLEMS = [
    ("risk", "Soldiers walk into the open", "Reforger's AI fights from cover 5-13% of the time (Arma 3 30-40%) and at 22-38 m: the game's attack leaves cover after 5 s and closes to 15 m. An assault force is 69-90% stacked - FPV bait. r10 holds cover 20 s; bounding and spacing next.", "review notes 113, 124, 125"),
    ("risk", "Drones invisible on screen", "Drones do hit (Everon 14:54: 22 of 25 finished drones hit soldiers), but the director's drone shot showed an empty field - from the screen they seem not to work.", "review note 125"),
    ("risk", "Infantry walks 270-710 m", "Nobody rides: AI Conflict never motorizes infantry by itself. Light vehicles with a covered dismount are in the r12 probe.", "review notes 127, 128"),
    ("design", "Careful or full storm?", "Careful (25) costs less but took Moss Hill once in two; full took it three in three. Careful is the default; the headless matches will tell.", "review note 106"),
    ("risk", "Slow follow-on after a capture", "Squads sent 1-1.4 km on to the next base take 7-18 min: AI Conflict holds them at the base just taken, then walks them in 220 m steps.", "review note 109"),
    ("risk", "Arland favours the US", "In the controls (AI Conflict on both sides) the US ends 2-1 three times out of four: read the USSR side's results against that.", "4 controls"),
    ("risk", "Few matches per build", "Each build has 1-4 matches per line, so single points jump. Captures are rare (0-3 a match).", ""),
    ("design", "FIA garrisons spawn near observers", "AI Conflict spawns FIA garrisons only where someone is near; in watched matches the camera is someone. Measure on headless matches.", ""),
]

NEXT = [
    "Covered dismount probe (r12): light vehicles to a point the objective can't see, then on foot - walk and ride measured.",
    "r10 cover measured in a match where our soldiers fight (the solo watched matches).",
    "Bounding and spacing like Arma 3's soldier layer: one team covers while the other moves; no 6+ bunches near the enemy.",
    "The director's drone shot: find the drone and follow it to the hit, so drones show on screen.",
    "Motorize only for long marches (over 1 km), measured as the walk and the follow-on time.",
    "Short scenario tests (squads already 600 m from the objective) for the soldier layer, so each change is tested in minutes.",
]

FACTS = [
    "AI Conflict (Apache-2.0) runs both commanders: per side 10 squads of up to 10 soldiers, 6 attack and 4 defend for the whole match, refilled one soldier at a time at the main base. We change it from our own addon (modded classes), without a fork.",
    "Each side can attack only bases its radio network reaches; at the start that is one base, and which one varies by match (Arland USSR: Airport Base or Moss Hill).",
    "A base is taken through the game's own capture point: our soldiers there and no enemy inside. AI Conflict sends attackers to the capture point, which can be away from the base's own position.",
    "AI Conflict walks squads to an objective in 220 m approach steps, and a Reforger group under fire stops to fight at each step - squads stalled 300-600 m out.",
    "Reforger AI priorities (SCR_AIAction): group move 50, fighting a spotted group 70; soldier formation movement 30, fire position 60, attack a chosen target 90, danger reactions +1000. A waypoint's priority level adds to the move.",
    "AI Conflict's commander never gives infantry a vehicle; a squad made motorized (by a player, or our doctrine) gets one of 10 trucks per side for routes over 400 m, dropped 150 m short.",
    "FIA garrisons spawn only where an observer is near (a player or the camera).",
    "A drone kill has no killer in the game's death event: the lab credits a death with no killer within 5 s of an FPV detonation to the drone.",
    "Speed: only the game's diagnostic build can run faster (Diag Menu > Cheats > DTime multiplier, 0.01-20x), and only where it hosts the match itself - a dedicated server can't (its diagnostic build lacks the setting). 2x measured at 60 fps. Headless servers run at 1x, up to four side by side.",
    "Reforger's attack logic (SCR_AICombatMoveLogic_Attack): in cover a soldier waits 5 s (20 s under fire) before moving on, out of cover 3 s (6 s), and closes to 15 m (or his weapon's minimum + 5 m); it looks for cover within 30 m on each move.",
    "AI Conflict's vehicles: light transport (US M998, USSR UAZ-452), armed light (M1025 M2, UAZ-469 PKM, BRDM-2) and trucks (M923, Ural); no motorcycles in the vanilla game. Dismount distance is a setting (-aicfVehicleDismountDistanceMeters, 30-500 m, default 150).",
]

# The changelog: (build, name, date, what, why, result)
CHANGELOG = [
    (14, "two armies, drone sites", "19 Oct, from 17:56",
     ["-zcrNoFIA test scenario: FIA's bases split between the sides at the start; FIA ambient patrols blocked; the watched matches run it.",
      "Drone sites: drone truck + 2 operators at the main base and a forward base; launches only from a ready site; lost when the truck or both operators are destroyed; counter-drone strikes at enemy sites a side has seen.",
      "Stuck drones retargeted after 25 s at the goal, home after 90 s; the camera stays on a drone's impact 4 s."],
     "Martin: for testing just two factions, no FIA; drone operators or drone trucks you can destroy; drones stuck in the air; I don't see the explosion.",
     "First two-army probe (before the patrol fix): no capture in 20 min, USSR stormed at 18.5 min; teams 2.3 soldiers, 7.5 m apart; our drones killed 33, none lost to theirs."),
    (13, "fireteams, side panels, bounding", "19 Oct, from 16:58",
     ["AI Conflict changed (branch zcr): 20 fireteams of 5 per side in a wedge instead of 10 squads of 10 in a column.",
      "Arma 3's side panels in its colours; firefights from 60 m, close-ups over the shoulder; drones followed to the hit.",
      "Bounding on by default; team size and spacing measured; the doctrine commits 4 defender teams.",
      "The situation report joined instead of formatted (it was cut at 8191 characters on Everon)."],
     "Martin: groups of 2-5, never single file down a road; BLUFOR left, OPFOR right like Arma 3, coloured; zoom in on fights; rework AI Conflict itself.",
     "Bounding probe: 5 lost instead of 14, exchange 3.4. Headless US Gemini doctrine with fireteams 3-2."),
    (12, "covered dismount, light vehicles, drones on screen", "19 Oct, from 15:40",
     ["Motorized squads get AI Conflict's light vehicles first (US M998, USSR UAZ-452), trucks only when the squad doesn't fit (-zcrMotorizeTruck for trucks).",
      "Covered dismount for our side: everyone out at the first spot on the drive 180-450 m short of the objective that it can't see (third design; routing to a hidden point sent trucks the long way round).",
      "Drones on screen: an FPV tag on every drone, the drone shot at the drone's height. The solo game opens in its own maximised mode.",
      "Drone launch spots never in the sea; with no clear spot no team (a fallback to the base centre killed 57 own soldiers in one probe). AI Conflict's barracks search at its maximum (Arland's harbour base).",
      "Bounding (Arma 3's fn_bound) as an A/B setting - first probe worse, refined, off by default."],
     "Martin: NPCs should use motorcycles and small cars, not only APCs - modern combat is driving to a point with cover, then clearing the position; drones don't work; the screen doesn't show what's happening.",
     "r10 build headless: 4-2, exchange 1.36, in the game's cover 40%. Watched at 2x: USSR+Gemini Moss Hill 2.8 min after the storm (+1), US doctrine Le Moule 1.2 min after it (+1); drones 28/36 and 31/44 hits. US doctrine headless 2-3 (Arleville storm failed). Dismount probe running."),
    (11, "walk and ride, engine measures, 2x", "19 Oct, from 15:25",
     ["Arma 3's 'how far the infantry walks' and 'riding to the attack' (squads report whether they ride); engine measures: fighting distance, server fps.",
      "Solo matches at 2x: the game hosts the match, the Diag Menu's time multiplier set by key presses; a normal maximised window.",
      "Recordings of the game window only; a clearer panel (score, plans in plain words, drones, last events)."],
     "Martin: measure as on Arma 3, and how the engine really works; make the game faster by any means; the screen doesn't show what's happening.",
     "2.0x measured at 60 fps; walk 270-710 m, rode 0%; kills at 22-38 m; watched Everon servers had run at 12-18 fps."),
    (10, "cover with the game", "19 Oct, from 15:05",
     ["The cover layer leaves soldiers in or moving to the game's own cover alone, holds that cover at least 20 s (the game: 5 s), and asks the game's own cover search for soldiers in the open.",
      "The game's own in-cover share measured (incover=)."],
     "Second cover probe: from cover fell 11.6% -> 5.3%; Martin: they walk across open fields like nothing is happening.",
     "Not yet tested in a fight: in the probe our drones cleared the garrison before our soldiers arrived."),
    (9, "cover layer", "19 Oct, from 14:31",
     ["Soldier layer (Arma 3's coverFight): soldiers in contact without cover move to the nearest covered spot within 25 m - our strategist's side, on by default.",
      "Drones hunt the enemy soldiers a side has seen (every other launch).",
      "Matches where a side never recruited (an AI Conflict start-up failure) are left out of the charts."],
     "Martin: get as close as Arma 3 - there soldiers took cover; heavy drone use.",
     "Probe: fighting from cover 11.6% (without 1.4-6.7%), Moss Hill and Arleville taken as before."),
    (8, "drone doctrine", "19 Oct, from 13:00",
     ["Drone warfare doctrine: the plan names drone targets - prep fire while gathering, pressure during assault and storm; a team every 90 s, up to 3 up.",
      "Both sides fly drones (AI Conflict's side a baseline: every 4 min, up to 2); headless matches load the drone mods.",
      "Each side's knowledge (enemies its soldiers saw in the last minute); the force needed is 2x the known defenders + 4; storm when 2 or fewer are left in sight.",
      "Watch buttons tested on screen; captions name the soldier's role."],
     "Martin: modern combat realistic style - heavy drone use by the bot, a drone warfare doctrine; get as close as Arma 3.",
     "Headless with drones: USSR doctrine 3-2, US doctrine 3-3 with two bases each 3-4 min after the storm, USSR Gemini 2-2; watched Everon: USSR Gemini 3-1 (Villeneuve 3 min after the storm, 6 lost). First headless drone match: USSR doctrine 3-2 - Airport Base at 13.7 min and Farm at 21 min, each 75 s after the storm order; USSR lost 16; drones caused 49% of all losses (15 USSR teams, 7 US, 55 strikes). Watched Everon: Old Wood 3 min after the storm, the US lost 4, drones 51% of losses."),
    (7, "soldier measures, watch buttons", "19 Oct, from 12:29",
     ["Arma 3's soldier measurements (ZCR_Sampler): fighting from cover, sitting ducks, stacking in the field; which cover (ground, building, tree, vehicle, object; roof or canopy overhead).",
      "Careful storm (priority 25) by default.",
      "Watch buttons as on Arma 3: PREV/NEXT SHOT, PREV/NEXT GROUP, LOCK, ACTION, CLOSER/WIDER, OVERVIEW, AUTO, tap to follow or fly there."],
     "Martin: on Arma 3 we measured sitting ducks and cover - good things to measure; in the age of drones, ground cover isn't cover; I'll watch on the phone, the buttons were great.",
     "From cover 5-8%, sitting ducks 27-63%, the USSR assault force 69-90% stacked - the gaps to Arma 3 are at the soldier level."),
    (6, "motorize, careful storm", "19 Oct, from 10:30",
     ["Attack squads can ride trucks (motorize), through AI Conflict's own configuration path - its commander never gives infantry a vehicle.",
      "Storm priority as a setting (-zcrStormPriority); probes with a fixed first objective (bridge --first-target, lab/probe.py).",
      "lab/progress.py and this page: measurements per build from every match log."],
     "Martin: storm makes the soldiers reckless; the follow-on after a capture is slow.",
     "Careful storm (25): Moss Hill in 10.8 min after the storm order, 15 USSR lost (full storm: 28-39). Motorize from the start: no capture in 28 min - trucks only for long marches next."),
    (5, "fixes", "19 Oct, from 07:55",
     ["Doctrine memory per match and side (reports carry the server's match id).",
      "'Bled out' counts every squad sent to the objective; the stall clock starts when the force gets within 900 m.",
      "Capture points and 'being seized' in the situation report; never call off an assault while the base is being seized."],
     "Two matches with the same strategist reset each other; Everon's objectives are 1.4 km apart.",
     "Headless USSR doctrine 3-2 at the end (Farm 50 s before the whistle); Everon US 2-2 with Military Depot taken 3 min after the storm."),
    (4, "storm", "19 Oct, from 05:53",
     ["Storm: 4 min into the assault, with 60% of the force there, the attack orders get a player order's priority and the squads already sent are re-ordered.",
      "Camera: a storm shot, and a cut to FPV drones as soon as they are airborne."],
     "Squads stopped 300-600 m short under fire (Moss Hill: 40-65 soldiers at 270-600 m for 23 min).",
     "Moss Hill in every clean match at 15-20 min; headless USSR doctrine 3-2 and 2-1; costlier: 30-45 lost a match."),
    (3, "commit", "19 Oct, from 04:52",
     ["Commit: 2 of AI Conflict's 4 defender squads join the assault while none of our bases is being captured.",
      "The attacking force counted from AI Conflict's own orders; Arland's USSR main base is 430 m from Airport Base, so the old count was the home garrison."],
     "Assaults trickled in: squads refill one at a time and defenders never attack.",
     "Commits in every doctrine match (6-10 soldiers each); still no USSR capture headless until storm."),
    (2, "attack doctrine", "19 Oct, from 03:45",
     ["Arma 3's attack doctrine as the strategist: gather at the nearest base, then assault; an assault that stops gaining ground is called off.",
      "Only bases AI Conflict can attack; Gemini picks the objective (llm-phased) or our rules do (phased).",
      "Camera: assault shots for fights against FIA garrisons."],
     "Strategists picked bases out of reach; squads stood near Airport Base for 15 min without taking it.",
     "On screen the USSR won 3-2 with drones; headless the doctrine didn't beat AI Conflict yet."),
    (1, "first loop", "18-19 Oct night",
     ["Head-to-head lab: a strategist per side (rules or Gemini through OpenRouter), the other side on AI Conflict alone.",
      "Watched and recorded matches with an Arma 3-style camera director and overlay; crash dialogs detected.",
      "FPV drone teams from Martin's mod for the strategist side."],
     "Martin: build the commander bot on AI Conflict and run a self-improving loop like Arma 3's.",
     "The loop ran all night: 13 recordings, 12 headless matches."),
]


def probe_rows() -> list:
    rows = []
    for run in sorted(progress.RUNS.glob("probe-*")):
        logs = sorted(run.glob("logs/*/console.log"))
        if not logs:
            continue
        text = logs[-1].read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\[ZCR\]\[STORM\] t=\d+ faction=(\S+) base=(.*?) squads=", text)
        if not m:
            continue
        side, base = m.group(1), m.group(2)
        cli = re.search(r"-zcrStormPriority (\d+)", text)
        r = probe_report.report(run, base, side)
        sm = progress.soldier_metrics(text.splitlines(), side)
        rows.append({"cover": sm.get("cover"), "incover": sm.get("incover"), "ducks": sm.get("ducks"), "run": run.name, "base": base, "priority": int(cli.group(1)) if cli else 1000,
                     "motorize": "motorize=1" in text, "storm": r["storm"], "taken": r["taken"],
                     "lost_near": r["lost_near"].get(side, 0), "fia_near": r["lost_near"].get("FIA", 0),
                     "lost": r["lost"].get(side, 0)})
    return rows


def engine(changelog_url: str) -> str:
    rows = progress.rows_all()
    agg = progress.aggregate(rows)
    charts = progress.html(agg, rows)
    probes = probe_rows()
    build = max(b for b, *_ in progress.BUILDS)
    now = datetime.now()
    verdict = "".join(f"<div><b>{E(k)}</b>{E(v)}</div>" for k, v in VERDICT.items())
    cards = "".join(f'<div class="finding"><div class="head"><span class="chip {c}">{E(t)}</span><strong>{E(h)}</strong></div><p>{E(p)}</p></div>'
                    for c, t, h, p in NOW)
    ptable = "".join(
        f"<tr><td>{E(p['run'][6:-16])}</td><td>{E(p['base'])}</td><td class='num'>{p['priority']}</td><td>{'yes' if p['motorize'] else ''}</td>"
        f"<td class='num'>{'' if p['storm'] is None else round(p['storm'] / 60, 1)}</td>"
        f"<td class='num'>{'not taken' if p['taken'] is None else round((p['taken'] - p['storm']) / 60, 1) if p['storm'] else round(p['taken'] / 60, 1)}</td>"
        f"<td class='num'>{p['lost_near']}</td><td class='num'>{p['fia_near']}</td><td class='num'>{p['lost']}</td>"
        f"<td class='num'>{'' if p['cover'] is None else str(p['cover']) + '%'}</td><td class='num'>{'' if p['ducks'] is None else str(p['ducks']) + '%'}</td></tr>"
        for p in probes)
    phases = "".join(f'<div class="phase"><div class="tag">{i + 1}<small>{E(n)}</small></div><div><p>{E(t)}</p></div></div>'
                     for i, (n, t) in enumerate(PHASES))
    camera = "".join(f'<div class="btn"><b>{E(a)}</b><span>{E(b)}</span></div>' for a, b in CAMERA)
    probs = "".join(f'<div class="prob"><span class="chip {c} st">{E(c)}</span><h3>{E(t)}</h3><p>{E(d)}</p>'
                    + (f'<p class="ev">{E(ev)}</p>' if ev else "") + "</div>" for c, t, d, ev in PROBLEMS)
    nxt = "".join(f"<li>{E(n)}</li>" for n in NEXT)
    facts = "".join(f"<li>{E(f)}</li>" for f in FACTS)
    style = (HERE / "engine_style.css").read_text(encoding="utf-8")
    return f"""<title>Reforger Commander Engine</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
{style}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Reforger commander · build r{build} · {now.strftime('%d %b %Y').lstrip('0')} · {now.strftime('%H:%M')}</div>
  <h1>How it works now</h1>
  <p class="lede">Zeus Commander's commander on Arma Reforger. AI Conflict keeps running both sides' squads; on one side our strategist (our rules or Gemini) sets the plan on top, with Arma 3's attack doctrine. This page explains the current build and measures it build by build, like the <a href="{ARMA3_URL}">Arma 3 engine page</a>. Every build's history is in the <a href="{changelog_url}">changelog</a>; the night of 18-19 Oct, with its videos, is on the <a href="{STATUS_URL}">night report</a>.</p>
  <div class="verdict">{verdict}</div>
</header>
<nav class="toc" aria-label="Contents">
  <a href="#now">Now</a><a href="#progress">Progress</a><a href="#probes">Probes</a><a href="#how">How a match runs</a><a href="#commander">Commander</a><a href="#drones">Drones</a><a href="#camera">Camera</a><a href="#problems">Open problems</a><a href="#next">Next</a><a href="#engine">Engine facts</a><a href="{changelog_url}">Changelog ↗</a>
</nav>

<h2 id="now">Now <span class="ref">BUILD R{build}</span></h2>
<div class="findings">{cards}</div>

<h2 id="progress">Progress <span class="ref">MEASURED PER BUILD</span></h2>
<p>Every chart is read from the match logs: the side with our strategist against the side on AI Conflict alone. The first three are the Arma 3 page's soldier measurements with the same definitions (in-game sampler from r6, so they start with the next matches).</p>
{charts}

<h2 id="probes">Probes <span class="ref">A/B, HEADLESS</span></h2>
<p>Short headless matches to test one change: the USSR on our rules doctrine, the US on AI Conflict alone, plans every 30 s. Times in minutes; "taken" counts from the storm order. Losses within 500 m of the objective, and in the whole match.</p>
<div class="table-wrap"><table><tr><th>Probe</th><th>Objective</th><th>Storm priority</th><th>Trucks</th><th>Storm at</th><th>Taken after</th><th>Own lost there</th><th>FIA lost there</th><th>Own lost</th><th>In cover</th><th>Sitting ducks</th></tr>{ptable}</table></div>

<h2 id="how">How a match runs</h2>
<p>AI Conflict runs Reforger's Conflict mode with AI on both sides: each side has 10 squads that refill at the main base from supplies, and FIA garrisons hold the bases in between. A base counts once it is linked to the HQ by radio. Our addon sits on AI Conflict's commander: every 15 s on its tick, and every 90 s a situation report goes to the strategist bridge (Python), which answers with a plan.</p>
<pre class="mermaid">{E(FLOW)}</pre>

<h2 id="commander">The commander</h2>
<p>The plan names a main effort, its demand (how many soldiers converge on it), bases to hold or avoid, and the doctrine's orders: commit, storm, motorize. Gemini, with your doctrine text, picks the objectives (llm-phased); the phases are our rules either way.</p>
<div class="phases">{phases}</div>

<h2 id="drones">Drones</h2>
<p>{E(DRONES)}</p>

<h2 id="camera">The camera</h2>
<p>Watched matches are played by the game on screen and recorded to <code>D:\\work\\reforger-commander\\videos</code>, each with a list of moments. The director picks the next shot every 14-30 s, in this order:</p>
<div class="btns">{camera}</div>

<h2 id="problems">Open problems</h2>
{probs}

<h2 id="next">Being built and next</h2>
<ul>{nxt}</ul>

<h2 id="engine">Engine facts</h2>
<ul>{facts}</ul>

<footer>Built by <code>python lab/engine_page.py</code> from D:\\work\\reforger-commander. Research and plan: <a href="{RESEARCH_URL}">Reforger research</a>. Review notes: D:\\work\\ac-lab\\REVIEW_NOTES.md (88-109).</footer>
</div>
"""


def changelog(engine_url: str) -> str:
    style = (HERE / "engine_style.css").read_text(encoding="utf-8")
    items = []
    for b, name, when, what, why, result in CHANGELOG:
        items.append(f'<details class="ver"{" open" if b == CHANGELOG[0][0] else ""}><summary><span class="vn">r{b}</span>'
                     f'<span class="when">{E(when)}</span>{E(name)}</summary><ul>' + "".join(f"<li>{E(w)}</li>" for w in what)
                     + f'</ul><p class="why">{E(why)}</p><p class="res">{E(result)}</p></details>')
    return f"""<title>Reforger Commander Changelog</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
{style}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Reforger commander · changelog</div>
  <h1>Every build</h1>
  <p class="lede">What each build of the Reforger commander changed, why, and what the matches showed - newest first. How the current build works, with the charts: <a href="{engine_url}">engine page</a>.</p>
</header>
<h2>Builds</h2>
{''.join(items)}
<footer>Built by <code>python lab/engine_page.py</code>.</footer>
</div>
"""


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    cl = sys.argv[sys.argv.index("--changelog-url") + 1] if "--changelog-url" in sys.argv else "#"
    en = sys.argv[sys.argv.index("--engine-url") + 1] if "--engine-url" in sys.argv else "#"
    (out / "reforger_engine.html").write_text(engine(cl), encoding="utf-8")
    (out / "reforger_changelog.html").write_text(changelog(en), encoding="utf-8")
    print(f"written {out / 'reforger_engine.html'} and {out / 'reforger_changelog.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
