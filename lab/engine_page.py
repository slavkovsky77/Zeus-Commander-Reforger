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
    "Running now": "22-23 Oct, two unattended days: watched matches at 3x, Arland and Everon in turn, all vanilla vehicles; the goals for Martin's complaints (no-crash, traffic, building-fast, cover, smooth) judged on every match, the worst one fixed next. 22 Oct 08:15: the night's six crashes came from two of our changes together (moving stuck vehicles by hand and the 'following' rule); following is off, 10 matches clean since.",
    "Supplies (r30-r32)": "Front bases now live on supply trucks (the free refill is off). Depots came late - the building planner checked about one site a second, lost orders when a squad died, and both Arland main bases are coastal with no depot site - fixed in r31-r32: headless, depots at minute 5-6 and 4 loads delivered in 15 minutes. Still open in watched matches: trucks drive slowly (AI vehicles a median 8-19 km/h) and die to drones on the way.",
    "Armour (r26-r27)": "Each side buys a crewed tank and IFV at its HQ - M1A1 Abrams / T-72, M2A2 Bradley / BMP-1 (armour mods, loaded in the watched matches from 05:17), else the game's LAV-25 / BTR-70 - and sends it to its front; the crew stays aboard and fights from the vehicle. Headless armour-5 and -6: all four units got into the assault on their front, 14 and 10 enemy killed, none lost. Open: friendly fire and soldiers run over (1-4 a test, now slowed for), stuck spots out of the HQs, 2 watched-match crashes since armour went live (cause not proven).",
    "Being built next": "Armour: fewer stuck runs out of the HQs; the watched loop with the armour mods; then trucks and building in watched matches, Yunakivka's navmesh.",
}

# (chip class, chip text, title, text) - what changed most recently.
NOW = [
    ("bug", "found", "Reckless soldiers, measured",
     "Martin, 23:35: 'investigate reckless soldiers'. Of 99 dead in the 23:22 match, 78% to drones, 22% to gunfire - none lying prone (64% standing, 12% crouching), half with nothing overhead; gunfire kills at a median of 6 m (1-4 m in the doctrine v doctrine matches). Two causes in the game's own AI: its attack closes on a seen enemy until 15 m, and the drone reaction's 'get down' was undone by the attack logic the next moment. r19: soldiers hold 60 m from an enemy seen in the last 15 s (except within 150 m of an enemy base, which has to be cleared), and prone is held for 15 s by the game's own stance setting."),
    ("good", "r19", "Speed set by the game itself",
     "The 3x came from ~200 key presses in the Diag Menu at each match start: they fought Martin's typing ('keyboard is hijacked'), landed in other menus when the menu list differed, and a retry and then a scan of unknown menu IDs crashed the game three times. A scan before one crash found the setting's engine IDs (switch 375, value 376): the game now sets 3x from script - no keys, measured 2.8x."),
    ("good", "r19", "Watching: free look, orbit, REPORT, IDs",
     "FREE LOOK (WASD, Q/E, Shift - the game's own camera input) and an orbit round any shot, both turning only with the right mouse button held; REPORT writes what the camera shows to the log; captions carry IDs - 'USSR team A3', 'drone team 4' - and a followed team shows its goal ('ATTACK Farm - 450 m to go - riding') with a TEAM GOAL marker; each side's panel shows its SUPPLIES (stock, change a minute, trucks on the road)."),
    ("bug", "r19", "No supply trucks: dispatch was manual",
     "AI Conflict's latest version made supply transport a player's map order only (automatic_dispatch=0): with AI on both sides no truck ever moved. Our fork runs the automatic scheduler again for the AI sides (player orders keep priority)."),
    ("bug", "found", "The regression the measures hid",
     "Martin, 21:40: no cars, no use of cover, no drones, sitting ducks - how didn't you notice? Three gaps: builds were judged on the headless batch, not the watched matches (drone teams 4-9 there, 0-3 in the watched ones); the measures skipped what the screen shows (cover only for soldiers in a fight, stacking only away from the base, whole-match averages hid 10-20 idle minutes); nothing flagged a regression - '0 rides' and '40 drone launches refused' sat in every log. Now lab/scorecard.py checks every match against fixed limits: first team out by 3 min, at most 40% at the main base at 10 min, teams of 2.5+, a drone team every 4 min, drones up 60% of the time, soldiers riding in 25% of samples. The 21:00 match fails 11 of 12; r18 passes nearly all."),
    ("good", "r16", "Teams out at once",
     "AI Conflict started every fireteam with 1 soldier and its one barracks recruited the rest one at a time, so teams waited at the main base 10-20 minutes (first out at 12.5 and 21 min). Our fork starts them with 3 of 5 and sends them out with 3: first team out at 1.3-1.8 min."),
    ("good", "r16-r18", "Drones up all match, and they scan",
     "My own 17:45 rule (drones only where enemies are known) had grounded them: nobody scouted. Now a team with nothing known flies a search near the front, its drones spot for their side (300 m, line of sight), a team with nothing to hit moves on after 15 s or sweeps a 250 m circle; AI Conflict's side every 2 min. Never over the enemy's main base - that camped its spawn. Drones up 50-100% of the time; Martin: 'drones attacks are deadly'."),
    ("good", "r17-r18", "Infantry rides",
     "AI Conflict never let infantry ride (refused 270-746 times a match), and infantry teams had no vehicle kind. Now teams ride light transport (M998, UAZ) from 300 m, 16 vehicles per side; out short of the objective where it can't see them. Soldiers riding in 58-83% of samples; a tag over each vehicle shows who is aboard; the camera cuts to vehicles on the move."),
    ("good", "r18", "Cover and panic",
     "Idle soldiers anywhere go under a roof or canopy within 40 m, 6 m apart. When a drone is heard (250 m) each runs to his own covered spot, or spreads out 15-25 m and then goes down: 89-93% react. March steps end in the best cover nearby, at a jog."),
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
    ("good", "Crashes: the mods' tanks", "Over 4 days 13-15 crashes in 33-40 game hours with armour, 1 in 51 without; no event of our scripts lines up with them. The stress test (6 armour a side, headless) crashes in 6-8 game minutes with the mods' vehicles; IFVs only and the game's LAV-25 / BTR-70 ran 40 minutes clean; tanks only froze or crashed in 8-10 min with or without our APC typing; the Abrams alone in 5.5. The tanks are off from 21:50 (-zcrArmourTanks).", "review notes 246, 269, 271"),
    ("bug", "Armour stuck on the HQs' exit roads", "A probe of the spots: the north HQ's checkpoint (5 Czech hedgehogs, two gates, concrete walls), dragon's teeth on a road east of the Airport, forest tracks out of the south HQ. Road blocks stay (Martin); armour is now bought on a road spot clear of them and of spawn points, nearest its front; a unit still for 2 minutes tries another way in. Soldiers' recruits timed out (5 a match) while the north HQ's armour stood on its spawn area.", "review note 243"),
    ("good", "Armour crews stay aboard", "The game's Search and Destroy searches on foot - the Abrams crew got out a minute after it; armour now moves on Move waypoints (the crew fights from the vehicle) and the mods' tanks are typed APC so gunners stay in their turret. A crew that got out of an intact vehicle is ordered back in (the Bradley's survivor in 15 s).", "review note 243"),
    ("bug", "Supply trucks barely deliver", "Since 13:36 front bases refill only by truck, and they starve (2-41% at the end); 0-1 loads delivered a side a match (goal: 3). Followed job by job (lab/trucks.py): the first depot is built at game minute 15-27; the US's at Farm lost its first three drivers to USSR drones within 2 minutes; later trucks drove 6 game minutes back to the main base to load; the USSR had no depot in 2 of 3 matches (world-placed depots without a base turned its first-depot rules off - fixed in r31, with the main base racing for the first depot).", "review notes 216, 252, 256"),
    ("good", "Drones no longer fly into the sea", "12-30 drones a watched match were lost in the inlet south of the Military Training Area: the teams flew straight across from their launch site and the drone mod holds its height over the sea bed. r31: a way over land round the sea (a grid search, cut to the fewest waypoints) - w11-w14 lost none, 17-24 teams a match rerouted.", "review notes 236, 257"),
    ("good", "Vehicles blew up on mines at the main bases' exits", "Of 342 vehicles lost on 20 Oct, 191 blew up at two places ~300-500 m from the main bases - the first ones a minute into every match. Not the driving: A/B with a 50 km/h limit, AI drivers run a median 12 km/h. A probe of what is there (-zcrProbeSpots) found rows of six TM-62M anti-tank mines across both exit roads in Arland's Conflict world; AI drivers don't see mines. They also burned the supply truck of the test and killed the crews (no killer). Our AI Conflict now removes the world's minefields that lie on roads at the start (3 on Arland, 17 mines).", "review note 226"),
    ("good", "Much more building", "Fortifications 2-7 a side a match (0.4 overnight): depots and fortifications pay their cost only, 5 a base within 2.5 km of the enemy, six types in turn (bunker, MG nests, sandbag positions, guard tower). Work crews: idle soldiers near a site join the builder (60-330 build points a side a match).", "review note 231"),
    ("risk", "Supply trucks: the depot is the last blocker", "Best matches 3-4 deliveries, both sides; others none - no vehicle depot in 20 minutes at crowded bases. Fixed so far: the minefields, the 500 reserve, demand, truck roads beyond a base's edge, the route query's long detours. Now every base tries a depot first while its side has none.", "review note 231"),
    ("good", "Teams no longer wait at the main base for 10+ minutes", "Of the vehicle boardings in the 20 Oct tests, 85% ran out of time (223 against 36): our drone-cover layer sent soldiers waiting for their vehicle into buildings 40-60 m away, the 25-s boarding ran out, the trip started over. The south main base's side had a median 47% at the base at minute 10 (the north 20%). The cover layer now leaves teams that wait for or board a vehicle alone: first watched match, 54 boardings, none timed out.", "review note 228"),
    ("bug", "Two watched matches stopped on the anti-drone fire", "The game's suppression sphere takes sqrt(r^2 - d^2) for a point near its edge; a hair outside it is NaN and the diagnostic build stops (13:00 and 13:04). Our anti-drone fire uses a sphere that clamps it; the loop restarted at 13:06 on the fix: 15 drones shot down, no stop.", "review note 229"),
    ("good", "Point-blank gunfights were a measuring error", "The 'median 3 m' counted friendly kills (crashes, run over) and suicides. Kills by enemy soldiers: median 30 m, 3% under 5 m, 42% at 20-50 m. The fighting-distance chart now counts enemy kills only.", "review note 227"),
    ("design", "Anti-drone balance", "21 drones shot down per side per match - about a third of those launched; probably too many.", "review note 213"),
    ("risk", "Formation spacing", "The wedge's spacing is in the game's formation config; one drone can still take several men.", "review note 183"),
    ("design", "Bunkers", "34 built overnight (0.4 per side per match) - supplies and AI Conflict's reserve are the limit.", "review notes 186, 192"),
    ("risk", "Unattended nights", "The PC slept 02:42-05:13 (now kept awake while the lab runs); after 05:16 no change was made - nothing woke the session between matches.", ""),
]

NEXT = [
    "Verify r19 on the screen and the scorecard: soldiers prone under drones, fights at 60 m, supply trucks on the road.",
    "Fortifications as a building type in our AI Conflict: bunkers and sandbags at points near the front, defenders posted in them.",
    "A goals overview per side: main effort, bases to hold, supplies needed, what the engineers build.",
    "/good and /bad reports with the log and a frame of the moment; scorecard checks for the drone panic (prone, covered, running).",
    "Routes through cover between march steps; a wider formation.",
]

FACTS = [
    "AI Conflict (Apache-2.0) runs both commanders: per side 10 squads of up to 10 soldiers, 6 attack and 4 defend for the whole match, refilled one soldier at a time at the main base. We change it from our own addon (modded classes), without a fork.",
    "Each side can attack only bases its radio network reaches; at the start that is one base, and which one varies by match (Arland USSR: Airport Base or Moss Hill).",
    "A base is taken through the game's own capture point: our soldiers there and no enemy inside. AI Conflict sends attackers to the capture point, which can be away from the base's own position.",
    "AI Conflict walks squads to an objective in 220 m approach steps, and a Reforger group under fire stops to fight at each step - squads stalled 300-600 m out.",
    "Reforger AI priorities (SCR_AIAction): group move 50, fighting a spotted group 70; soldier formation movement 30, fire position 60, attack a chosen target 90, danger reactions +1000. A waypoint's priority level adds to the move.",
    "AI Conflict's commander never gives infantry a vehicle (our fork does: light transport from 300 m, 16 per side); a squad made motorized gets a vehicle for routes over 400 m, dropped 150 m short.",
    "AI Conflict starts every infantry team with one soldier and recruits the rest one at a time at the side's barracks (our fork: 3 of 5 at the start, out with 3).",
    "FIA garrisons spawn only where an observer is near (a player or the camera).",
    "A drone kill has no killer in the game's death event: the lab credits a death with no killer within 5 s of an FPV detonation to the drone.",
    "Speed: only the game's diagnostic build can run faster (Diag Menu > Cheats > DTime multiplier, 0.01-20x), and only where it hosts the match itself - a dedicated server can't (its diagnostic build lacks the setting). 2x measured at 60 fps. Headless servers run at 1x, up to four side by side.",
    "Reforger's attack logic (SCR_AICombatMoveLogic_Attack): in cover a soldier waits 5 s (20 s under fire) before moving on, out of cover 3 s (6 s), and closes to 15 m (or his weapon's minimum + 5 m); it looks for cover within 30 m on each move.",
    "AI Conflict's vehicles: light transport (US M998, USSR UAZ-452), armed light (M1025 M2, UAZ-469 PKM, BRDM-2) and trucks (M923, Ural); no motorcycles in the vanilla game. Dismount distance is a setting (-aicfVehicleDismountDistanceMeters, 30-500 m, default 150).",
]

# The changelog: (build, name, date, what, why, result)
CHANGELOG = [
    (38, "no crashes; trucks out of their depots; rides round unreachable spots; armour unstuck", "22 Oct, 08:00-10:40",
     ["Crashes: two of the night's changes together crashed the watched game - moving stuck vehicles by hand and the 'following' rule that slowed a vehicle behind a slow one (it changed the game's cruise speed). Without the moves 4 of 4 matches clean, without following 6 of 6 (100 moves). Following is off; since then one freeze and no crash in 23 matches.",
      "Supply trucks: a truck that drove past its 3-m waypoint (its depot's exit, 12 m ahead) had to turn back to it - the game's drivers can't reach a point behind them, so the move failed and the driver got out (22 driver exits in one match). Truck waypoints are 8 m and the exit counts once passed: 0 failed truck moves and 6 exits in the next Arland match.",
      "Rides: the same few road points failed match after match - on Everon a farm road inside a fenced yard behind a gate, 'reachable' for the road network, not for the drivers; the team then walked 2-6 km. A point a vehicle couldn't reach is remembered for the match and later rides take one on the approach side.",
      "Armour and armed rides: kept from being moved by hand since 05:10 on an early crash theory. Moved again: half the long stops and jams (2.8 and 2.0 a match against 5.9 and 5.3)."],
     "Martin, 22 Oct 00:30: 'solve those cars and the other issues'.",
     "w26-w48: one freeze (w42), no crash. With all of the above (w43, w45-w48): jams 0-5, long stops 0-6 a match."),
    (37, "cars: follow, back onto the road, the queue's front one; trucks on Everon", "22 Oct, 03:25-05:00",
     ["Cars blocking each other, still Martin's biggest issue. Following: a vehicle with one of its side's vehicles under 5 km/h within 14 m ahead creeps at 4 km/h behind it instead of squeezing past into the field (Everon w5: 16 jams at one farm). Stuck alone 60 game s (was 90): put back on the nearest road 3 m+ wide within 40 m, a few metres on toward its waypoint, facing along the road, where its body has room - the 8-m back-off sent rides into the same rocks again (Arland w8: one sat 10 minutes after three back-offs). The stuck front vehicle of a queue gets the same (Arland w12: 10 jams behind a ride hung on a boulder in a sunken track - only the ones behind were ever moved). Then the crashes: six watched matches from 03:27 crashed, every one seconds after one of these hand moves (4 of 6 within 4 s); a headless server made the same moves 35 times in 30 minutes without one. A safe placement and moving vehicles the Game Master way (Teleport) didn't stop it. Two experiments found the cause: without the hand moves 4 of 4 matches clean; with the moves but without the following rule 6 of 6 clean (100 moves). The two together crashed the game - the following rule is off (no clear gain in jams), the back-offs and parks stay, the road recovery stays off.",
      "Supply trucks on Everon: not one truck job in eleven Everon matches - each truck's search paired every base (39) with every base in need, 16 a tick shared by all depots, and never finished. Our fork lists the bases with supplies once and gives the search its own budget: 18-34 jobs a side, the first deliveries on Everon (w15: 3 + 1). At most 8 trucks of a side out at once (52 jobs a match, none delivered, 2-6 fps lost). Trucks to one base spread their load and unload points 20 m+ apart along the roads (7 of ~30 Arland jams were truck against truck at one point).",
      "Lag on Everon: AI Conflict's commander took 60-94 ms on nearly every tick there (Arland under 20) - a stutter every few seconds: for every squad it recomputed a network calculation over all 39 bases and summed every squad's force for every base. Our fork computes them once a tick and in one pass: headless Everon under 20 ms on 80 of 84 ticks.",
      "Seen for the first time: [ZCR][MOVEFAIL] - the game gives up a group's move in a vehicle (STUCK or UNREACHABLE) and takes the whole group out to walk; 17-42 a match on Everon, supply trucks half of them."],
     "Martin, 22 Oct 00:30: 'solve those fucking cars and the other issues' - two unattended days, first the cars.",
     "Jams a match: Arland 1-16 (typically 6), Everon 0-16 - not clearly better over the night. Trucks: Everon 0 -> 18-34 jobs, first deliveries. Crashes: 6 of 18 matches from 03:27 with hand moves and following both on; 0 of 10 since (w26-w35) - following off. Building unchanged (more search budget and no access lanes both measured: no gain)."),
    (36, "cars that don't block each other; all vanilla; Arland and Everon", "22 Oct, night",
     ["Cars blocking each other (Martin: 'the biggest issue'): a driven vehicle still 45 game s with somewhere to go is logged stuck ([ZCR][STUCKVEH]) or jammed with another vehicle within 10 m ([ZCR][JAM]). The night's first matches showed the cause: rides jammed against abandoned vehicles on the roads and pads - AI Conflict's cleanup counted a dead body in a seat as a protected occupant and kept those vehicles all match (fork: dead bodies don't protect). A jammed vehicle backs off 8 m along its track; an abandoned blocker, or a ride waiting at a pad for its team, is parked 10-14 m aside; a vehicle stuck alone 90 s backs off and plans again ([ZCR][UNJAM]).",
      "Armour: the mods' tanks crash the game and their IFVs drive badly (stress: the game's LAV-25 / BTR-70 half the stuck, 4x the kills); AI Conflict rode the mods' IFVs too. From 02:20 the armour mods are out - every vehicle is the game's own.",
      "Building: roadside depot spots on every try, 4 and 10 m clear of the road; heavy depots and large barracks (1 and 17 placed to 74 and 52 given up) wait 10 game minutes after a failed search; march legs end in cover (score logged, 9-13 of 13 on Arland).",
      "Two maps: Arland and Everon in turn (Martin: 'test it on at least two scenarios'). Goals by severity in the lab app (no-crash, traffic, building-fast, cover, smooth), each judged on every match."],
     "Martin, 21 Oct evening: rate the day's complaints by severity, watch them in the commander lab, fix them over two unattended days - first the cars.",
     "No crash in the 15 matches of the night (no-crash goal met). Jams a match: Arland 17-25 before -> 0-6; Everon 6 -> 0-2; stuck 2 min+: 0-5 a match (9 before the unstick). Site searches: Arland 9-30 game s, Everon 60-86 s; 41-53% still give up."),
    (35, "site searches 3x faster; armour without the mod tanks", "21 Oct, from 21:50",
     ["Building (Martin: 'why is the bot so long choosing sites, like three minutes?'): the searches were throttled, not slow - AI Conflict let all site searches of both sides share 96 queries a second and 4 candidate spots a tick; a search computed 0.18 s in each 40-s window and waited the rest. Our fork: 288 queries a second times the speed-up, 12 candidates a tick, a 10-ms slice. Headless: sites found in a median 17 s real (about 50 game s at 3x); searches that find nothing give up in ~20 s instead of minutes.",
      "Crashes (Martin: 'fix armor crashes ... simulate it'): over 4 days the watched matches crashed 13-15 times in 33-40 game hours with armour, once in 51 without. A stress test (lab/stress.py: headless matches with 6 armour a side, bought again 30 s after a loss) crashes in 6-8 game minutes; switching one thing off at a time: no drones - still crashes; the game's own LAV-25 / BTR-70 - 40 min clean; IFVs only (Bradley, BMP-1) - 40 min clean; tanks only (Abrams, T-72) - froze or crashed in 8-10 min, with or without our APC typing; Abrams alone - crashed in 5.5 min. The mods' tanks are off; the tank slot takes an IFV (-zcrArmourTanks brings them back).",
      "Armour drove into its own vehicles and ran over its soldiers (the T-72 back for a new crew, against its column): the guard that slowed it for soldiers on foot ahead now counts vehicles not the enemy's too.",
      "The lab app: a Crashes tab (with/without armour, every crash and its last 30 s, what comes before a crash, the stress test by variant); [ZCR][ENT] lines before every entity our scripts touch; each effort's time in its phase with minute ticks (amber 'slow', red 'stuck?'); a game FPS graph per match; remarks carry the moment typing began."],
     "Martin, watching: crashes 'a lot', sites chosen for minutes, the T-72 crashing into vehicles.",
     "Headless: placed site searches median 17 s real. Stress: mods' tanks crash in 5.5-10 game min, IFVs and vanilla APCs 40 min clean. Watched matches with the change: from 21:55."),
    (34, "armour back for a new crew; depots off the road", "21 Oct, from 18:34",
     ["Tanks and IFVs lost their gunner and commander to FPV drone hits and drove on with the driver alone (0-1 armour kills a match): now they go back to the nearest own base with supplies, the dead are taken out and new crewmen put in the empty seats (100 supplies each, twice a unit).",
      "Depots (Martin's /bad: 'supply depot was built on the road and vehicles get stuck'): a depot's footprint stays off every road and some road passes within 30 m (not for the forced first depot) - the USSR main base's depot reached 2 m into a 4.5 m road; the Farm depot stood 46 m from any road and its trucks stuck on the farmland.",
      "The lab app's Live tab: each side's efforts - attacks (men there of sent), defences (in place), supply runs as one four-part track (drive to load, load, drive to deliver, unload, metres to go), building sites (% built), site searches (a moving stripe)."],
     "Martin: armour crews killed inside; depots on the road; 'those actions should have visible progresses'.",
     "Watched matches: re-crews in w2-w4; a 12-min headless test placed one depot with the first road rule - loosened (any road near counts)."),
    (33, "building timers at game speed; squads don't wait for vehicle pads", "21 Oct, from 16:45",
     ["The building planner's search windows (2 min), decisions and cooldowns (60 s) ran on real time: at 3x a small barracks searched 6 game minutes, found no site, then the forced fallback found one in 13 s (w17) - and every depot waited for the barracks. They now scale with the speed-up: 40 s and 20 s at 3x (from 16:45).",
      "A squad waiting for a free vehicle pad waited until its whole trip's deadline (10-30 minutes): 8-15 squads a side a match waited over a real minute, up to 594 s, and the side at Arland's cramped south harbour base kept ~40% of its soldiers there at minute 10 (north ~26%, headless the same). Now at most 45 game seconds, then on foot (from 17:07).",
      "The live lab monitor (Martin: 'a monitoring GUI that's part of the process'): the loop's current step, goals, iterations, matches and a box to send it remarks - lab/monitor_page.html, lab/monitor.py."],
     "Goals trucks and on-screen: the first truck at game minute 14-16; one side 40-68% at its main base at minute 10 in 8 of 19 matches.",
     "w25 (timers): first truck at game minute 8.9 (US) and 10.7 (USSR), 8 loads, 5 delivered (w17: 13.8-16.4, 2 delivered). w26: 3 delivered by the US. w27 (pad limit): 15 real seconds a wait then on foot, about 20 times a squad; the USSR still 44% at its base - four attack squads were ordered to secure the main base area that minute (a defence decision, a separate cause). To judge over more matches."),
    (32, "building planner 4-10x faster; building keeps its orders", "21 Oct, from 15:16",
     ["AI Conflict's construction planner ran once a second with 4 candidate sites a tick, shared by every base's order - a depot site search checked about one candidate a second (the harbour main base: 117 in a 2-minute window), and on the watched matches' 3x it ran on real time, a third of that in game time. It now has its own tick: 250 ms, divided by the lab's speed-up (100 ms at 3x).",
      "Building's navmesh queries went through the side's first living squad; when that squad was wiped out every building order in progress was cancelled and searched again (NAVMESH_CONTEXT_CHANGED). An empty group of its own at the main base serves them now.",
      "Measured on the way: both of Arland's main bases are on the coast and find no depot site in 8 minutes, so the race with a second base (r31) is what gets a side its first depot."],
     "The trucks goal: the first depot came at game minute 15-27 in watched matches.",
     "Headless 16 min, all of r31-r32 (1x): depots at minute 4.7 (US) and 6 (USSR), first trucks at 5.3 and 8.2, 11 jobs, 5 loads, 4 delivered (before r31: no depot for one side, 0-1 loads, 0 delivered); no building order lost to a wiped-out squad; server 58.3 fps (58.2 before). Watched w14 (250 ms tick, before the speed scaling): first US truck at game minute 14.6, USSR 28.3 - the searches still took 140-480 real seconds, hence the speed scaling. Watched w17 (100 ms at 3x): 24 truck jobs, 6 loads, 2 delivered, front bases at 38% / 36% at the end (the first match with both sides over 35%), 3 / 2 fortifications, 37.5 fps (30-33 before); first trucks still at game minute 13.8-16.4 - the small barracks come first and their site searches take 6-9 game minutes. w15 and w16 crashed: the morning's armour crash family (same fault addresses), not these changes."),
    (31, "drones round the sea; depots that count; the main base races for the first depot", "21 Oct, from 14:32",
     ["Drones over the sea: since 20 Oct no drone goal is over the sea, but the watched matches still lost 12-26 drones a match in the inlet south of the Military Training Area: the teams flew straight from their launch site across it, and the drone mod holds its height over the sea bed. Teams now fly a way over land: a search over 100 m dry squares round the line, cut down to the fewest waypoints that see each other over land (USSR main base to the Military Training Area: by (2063, 1792) and (1663, 1992), 1 ms). One dry point beside the line (14:12-14:21) wasn't enough: the USSR's teams found none and 30 drones were lost in w8.",
      "First depot (AI Conflict fork): Arland has three world-placed USSR heavy vehicle depots that belong to no base. Trucks can't start from them, but they switched the USSR's first-depot rules off: in 2 of 3 watched matches the USSR built no depot and had no supply truck all match. They no longer count.",
      "The main base searches for the first depot alongside one other base: the US built its first at Farm on the front and its first three drivers were killed by USSR drones within 2 game minutes of leaving (the drone hit logged at the same spot, 0-4 s before). Held for the main base alone, the other bases waited 8-10 minutes in a headless test (the harbour main base found no site in 8 minutes).",
      "The lab: goals.toml and lab/goals.py judge every goal (trucks, drones over the sea, armour, building, the screen checks) on the last 3 watched matches; the loop as Claude Code skills (review page)."],
     "Martin: supply trucks barely deliver, drones crash into the water; and make skills out of the loop so others can run their own goals.",
     "Drones: w11-w14 lost 0 drones over the sea (12-30 a match before), 17-24 teams a match flew round it - goal met. Trucks: w12 (race): first US truck at game minute 13.7 (15-27 before), depots US 2 / USSR 1, 3 loads, none delivered by the end - the trucks drove 12 game minutes from their depot to the source (AI vehicles run a median 8-19 km/h)."),
    (30, "supplies only by truck; supplies on the overlay", "21 Oct, from 13:36",
     ["Front bases refilled for free - 1250 to 3000 in 4 minutes with no truck - so AI Conflict's trucks, which serve bases below 60%, had nothing to do: 0.4 deliveries a watched match. A probe of the bases' supply containers found it: the container a base's stock is summed from regains 100 every few seconds, about 570 a minute. Our AI Conflict switches that gain off at every base except the HQs and its supply depots, every 5 s (BASE_REGEN_OFF). Farm: 1200 to 600 in the next match, no refill.",
      "A first attempt (Conflict's replenish threshold at 0) didn't stop the refill and broke AI Conflict's recruitment, which reads it as a base's ceiling: two watched matches failed their first spawns (13:00, 13:13). Reverted.",
      "On screen (Martin): each point shows its supplies - a number and a dot, green 60%+, amber 30-60%, red under 30% - and 'truck coming' or 'building'; building sites at their spot; a DETAILS button for the long texts. In the map overview only the supplies and those two.",
      "Building: one base of a side searches for its first depot at a time only while the side has no depot at all - as first written (05:17) it held every later depot back too, and depots built a watched match fell from 2.3 to 1.2."],
     "Martin: 'something refills for free' - supply trucks have to matter; and the supplies, supply runs and building on screen without overfilling it.",
     "w5-w7 (13:36-14:08): front bases starve (2-41%), 0-1 loads delivered a side a match - the trucks now matter, and the next problems showed: first trucks at game minute 15-27, drivers killed by drones at a front depot, no USSR depot in 2 of 3."),
    (29, "armour follows the fight; remount on its own vehicle; no forest tracks", "21 Oct, from 07:46 (Martin asleep)",
     ["Remount on the unit's own vehicle (the game's Get In waypoint on it, the vehicle registered with the crew group at crewing and before boarding) - the 07:26 watched crash recorded the AI boarding a vehicle its group doesn't own; 'Get In Nearest' could pick any.",
      "In the assault the goal follows the fight: the middle of the last 150 s's losses within 700 m of the front, re-aimed when it moves 200 m+ (watched two-army matches: armour drove to the enemy base's centre while the fighting was elsewhere).",
      "Spawn spots ranked: no road on towards the front, a unit stuck there before, or a road under 5 m wide (forest tracks by the south HQ held units in most watched matches) go last.",
      "Gunners also hold fire with their own soldiers within 8 m of the line of fire, out to 60 m past the target (armour-11's Abrams killed 10 of its own; armour-16: a miss 35 m out killed a friendly at 68 m); a friendly kill logs the gunner's target.",
      "A unit still stuck after 3 detours is moved along the road to a clear spot 25-250 m on, nearest its front - the way AI Conflict frees its stuck FIA patrol vehicles; not while the director shows it, at most twice (armour-17: 4 moves, both US units freed from the south HQ's spots)."],
     "The night's watched matches: armour stuck by the HQs, little fighting, a crash with a boarding assert.",
     "Headless armour-12 to -15: all four units into the assault in 3 of 4 tests, 6-10 enemy killed, 0-1 own killed except armour-14 (7, a T-72 at its HQ); watched since 07:04: 1 crash in 7 armour matches (6 in 15 before)."),
    (28, "armour: crash suspects out, guns hold for their own men", "21 Oct, from 07:04 (Martin asleep)",
     ["Watched matches crashed in the engine's entity update (heap corruption, access violations) in 6 of 15 matches with armour, 4 in a row 06:19-06:30; none in the 73 before, none in 2 matches 06:42-07:04 without armour units, never in headless tests. Two suspects taken out: a replaced armour waypoint is deleted 20 s later (a stuck unit's waypoint swap came 3-60 s before each crash), and the crew aboard is counted from the crew group instead of walking the vehicle's seats and turret attachments several times a second (most crashes followed an FPV drone going for the armour).",
      "Armour gunners hold fire when their own soldiers are within 20 m of the target or 8 m of the line of fire: armour-6's T-72 killed 3 of its own at once, armour-11's Abrams 10 at 13-321 m.",
      "Armour is bought at the side's base nearest its front (400 m+ short of it) when that base has the supplies and a road spot - from the HQ it drove 1-1.5 km and FPV drones took its crews on the way.",
      "A tracked hull also slows for soldiers within 10 m round it (it turns on the spot); a unit that never moved off its spot tries another way after one still minute; labels read 'US TANK M1A1 Abrams - attacking Farm'."],
     "Overnight evidence: crashes since armour went live, armour's own fire and crushing, long drives under drones.",
     "Watched 07:04 with the changes: no crash (the first of the A/B after two clean matches without armour). Headless armour-11: all four into the assault, 7 enemy killed but 10 own (the line-of-fire hold came after it)."),
    (27, "armour mods in watched matches; crews stay aboard; more building", "21 Oct, from 05:17 (Martin asleep)",
     ["Watched matches load the armour mods: the M1A1 Abrams, M2A2 Bradley, T-72 and BMP-1 fight in the recordings (until 05:17 the game's LAV-25 / BTR-70).",
      "Crews stay aboard: the game takes a crew out of its vehicle through one behaviour for every reason (a failed move releases the vehicle, gunners leave the turret to look round, danger reactions); for our armour's crews it now waits while the vehicle has 35% health or more. In the first watched match with the mods the BMP-1's crew got out three times and the Bradley's and T-72's were lost out of intact vehicles - no armour kill.",
      "Friendly soldiers in the way: every second, a soldier of the side on foot within 30 m ahead of a hull slows it to 5 km/h (35 km/h otherwise) - tanks and IFVs ran over their own MG gunners and medics; the game's AI driver doesn't steer round them.",
      "In the assault a unit holding a firing spot within 200 m of its goal is not 'stuck' any more (it was re-ordered off it).",
      "Building (AI Conflict fork): one base of a side searches for the side's first vehicle depot at a time, the others build - every base searched 7-11 minutes for a depot site first and fortifications came at minute 21-24 of 30 (1 a side a match); the first match after it: 8 bunkers for the US."],
     "Martin: armour should fight; free soldiers should build much more. The first watched matches with armour: crews getting out, own soldiers run over, few fortifications.",
     "Headless armour-5 and -6 (before the stay-aboard change): all four units into the assault, 14 and 10 enemy killed, none lost; 1 and 4 friendly kills. Watched 05:17 (mods, before the crew fixes): armour bought and crewed, no armour kill, crews lost out of intact vehicles; 8 US bunkers. The stay-aboard change is in the watched matches from 05:39."),
    (26, "armour units: tanks and IFVs that fight", "21 Oct, from 04:28 (Martin asleep)",
     ["Armour (Martin: 'usage of more types of vehicles - APC, tanks... maybe use some mods... make AI use them also for combat'): each side keeps a tank and an IFV, bought at its HQ for supplies (800 / 500 / 300 - the HQs sit full at 4000-4200 all match), crewed by the faction's crewmen in the driver and turret seats as a group of their own, and sent to its front: a support point 350 m short, then into the base. AI Conflict's rides drop their team and leave the vehicle empty; these fight.",
      "The armour mods (one Workshop family on SpaceCore and WCS_Armaments): M1A1 Abrams and M2A2 Bradley for the US, T-72 and BMP-1 for the USSR; without them the game's LAV-25 / BTR-70 (what watched matches have had since 04:28). The lab loads them with --armour (lab/pakread.py and the mods' resource databases gave the prefab GUIDs). APC rides take the Bradley / BMP-1 first too.",
      "Crews stay aboard: Move waypoints only (the game's Search and Destroy searches on foot - the Abrams crew got out); tanks typed APC so the game keeps gunners in the turret; a crew that got out of an intact vehicle is ordered back in, then seated if close.",
      "Driving: fronts never a base of the side's own (the first test sent the T-72 to 'assault' its own HQ) and held 3 minutes; goals on the road network; a unit still for 2 minutes tries another way in; bought on a road spot laid on the ground's slope, clear of road blocks and soldier spawn points, nearest the front.",
      "Seen and measured: watch labels over each unit ('US TANK M1A1_Olive - ASSAULT Farm, crew 3/3, 100%') and a director shot that follows one; [ZCR][ARMOUR] log; kills and losses tagged on [ZCR][LOSS]; the scorecard and a new chart 'Armour in combat' (bought, into the assault, kills)."],
     "Martin, going to sleep: 'another important thing to improve is usage of more types of vehicles, APC, tanks etc... make AI use them also for combat. That's important.'",
     "Headless Arland, 5 tests: all four units bought and crewed at 2 min in every test; the Abrams drove to Farm (to 194 m) and the Bradley to Moss Hill, killing FIA soldiers with their guns; an FIA anti-tank soldier hit the Bradley. Open: stuck spots on the HQs' exit roads (probed: hedgehog checkpoint, dragon's teeth, forest tracks), crews that leave after a failed move, and 2 watched-match crashes since 04:28 (cause not proven)."),
    (25, "APC rides; truck drivers left alone; road blocks stay", "21 Oct, from 03:56 (Martin asleep)",
     ["AI Conflict fork: every 2nd armed ride is an APC - LAV-25 (US) or BTR-70 (USSR) with the team aboard and its gunner fighting; armed rides every 2nd infantry ride (was every 3rd). Martin: 'more types of vehicles - APC, tanks - make AI use them for combat too'.",
      "Soldier layers (cover, drone reaction, dispersal, anti-drone fire, work crews) leave AI Conflict's supply truck drivers and builders alone: 99 of 128 of the game's gate-opening chains for supply trucks were broken by our orders to the driver standing at the gate (Martin: 'improve the driving').",
      "Road blocks stay on the map (Martin: 'don't remove barriers and hedgehogs by default, just improve driving'): the r24 removal of gates and road blocks is now opt-in (-aicfClearRoadBlocks); minefields on roads are still removed.",
      "Yunakivka: a neutral supply cache at each of its bases without storage (1000 supplies, any side's trucks load and unload); a navmesh rebuild at run time was tried and is off - the game only refreshes tiles that exist, and SpearHead's map ships none, so soldiers can't walk there (a navmesh has to be generated in Workbench)."],
     "Martin's night notes: improve the driving without removing road blocks; more vehicle types, used in combat.",
     "Watched Arland matches 03:56-04:28: riding 78-92% of samples, 7-14 armed rides a side a match, drones up 69-100%; supply trucks still few (0-5 jobs, 0-2 unloads a side) and bunkers 0-3 a side."),
    (24, "supplies, trucks and building on screen; gates off the roads; Yunakivka", "21 Oct, from 02:00 (Martin asleep)",
     ["Watch view (Martin: 'I should see the state of the supplies; whether trucks carry supplies and how much; I don't see defences being built'): base labels with stock/storage, 'asks for supplies' and SUPPLY DEPOT +150/min; a tag over every supply truck ('US SUPPLY TRUCK 0/315 - to load at Military Training Area'); markers on finished fortifications (BUNKER, MG NEST, SANDBAGS, TOWER) and on buildings going up with progress and crew; the camera cuts to supply trucks and building sites.",
      "AI Conflict fork: closed gates and road blocks on roads off the map at the start - 27 on Arland; trucks stood minutes at a walled checkpoint gate east of the Airport that AI drivers can't open.",
      "AI Conflict fork: a side's first vehicle depot gets the relaxed search of the mandatory barracks after 2 minutes and is completed when placed - one side had no depot (no trucks) in the first watched match.",
      "Yunakivka (Martin: 'test it on Yunakivka, a lot of trenches'): SpearHead's 'SH UHC Yunakivka' is stock Conflict - AI Conflict now starts on it (lab: --map yunakivka with the map mod and its 6 dependencies; lab/pakread.py reads .pak files); bases' radio range 3 km (they were out of reach, nobody attacked); base names from the map labels.",
      "Fixed on the way: a work-crew NULL error; building progress shows its % sign."],
     "Martin's evening remarks (visibility of supplies, trucks, building) and the night's plan (Yunakivka).",
     "Headless Arland, 20 min: both sides with a vehicle depot by 6 min, 21 truck jobs, 4 loads, 4 deliveries (both sides) - best so far. Watched: building and truck shots with tags confirmed on frames. Yunakivka: runs, plans attacks; its bases can't hold supplies without a storage building (next)."),
    (23, "supply depots, trucks every match, drones off the sea", "20 Oct, 16:30-21:18",
     ["Supply depots (Martin: 'if supply points are missing on the map, add them'): Arland's AI Conflict had none (0 of 8 bases a supply source) - the two bases nearest the middle (Beauregard, Military Training Area) gain 150 supplies a minute, any side's trucks load there while neutral (they stay FIA in the two-army setup), the holder loads there like at its main base; tagged SUPPLY DEPOT (green) on the watch labels.",
      "AI Conflict fork: 3 supply trucks run per vehicle depot (was 1 - more only from players' orders); bases ask below 60% and are filled to 80% (at 35% they stayed full for 15 minutes).",
      "AI Conflict fork: every base with its barracks tries a vehicle depot first while its side has none (both sides had a depot in 3 of 3 tests: USSR ~6 min, US ~15 min); fortifications third in the building round - as the last of six they never got a turn in a watched match.",
      "Drones: search sweeps and goals never over the sea - 537 drones in 28 watched matches flew into the inlet south of the Military Training Area (Martin's /bad); the drone mod holds its height over the sea bed (note for its chat).",
      "AI Conflict fork: an abandoned vehicle standing on a road is retired at once - a USSR UAZ given up on a junction blocked a US M998 (Martin's /bad 'now they seem to be stuck').",
      "Work crews: a member deleted in the same tick is skipped (a NULL error in a watched match). Kept: soldiers shooting down incoming drones (Martin's /good, KEEP.md)."],
     "Martin: logistics is very important - add supply points; supply trucks barely deliver; drones crash into the water; vehicles stuck.",
     "Watched matches 20:00-21:00: 7-10 truck jobs a match (was 0-3), trucks on the road on both sides; a run forward depot > main base > front takes ~14 game minutes, so few deliveries finish in a 30-minute match. Fortifications still 0-2 a side in watched matches. Next: supplies, trucks and building visible on screen (review note 239), shorter runs (nearest source)."),
    (22, "trucks deliver, much more building", "20 Oct, from 14:05",
     ["AI Conflict fork: vehicle depots and fortifications pay their cost only - a squad's replacement (500) kept back meant forward bases never afforded a depot (no depot in 14 of 16 matches).",
      "AI Conflict fork: up to 5 fortifications a base within 2.5 km of the enemy (was 2 within 1.5 km), in turn: bunker, two MG nests, two sandbag positions, guard tower - Conflict's own compositions.",
      "Work crews: up to 4 idle soldiers near a building site join the builder from spots round its footprint and add build points (Martin: free guys should build much more).",
      "AI Conflict fork, trucks: the road and the loading up to 100 m beyond a base's edge (Airport Base's road is 233 m from its centre), the nearest road point when the route query gives up on a long detour, a side's first depot searches longer and every base tries one first.",
      "Measures: [ZCR][SUPPLY] each base's stock every minute; lab/trucks.py traces every truck job end to end."],
     "Martin: supply trucks barely deliver (2 in 42 matches overnight); bunkers 0.4 a side a match - free guys should build much more.",
     "Fortifications 2-7 a side a match (0.4 overnight), all six types built; work crews add 60-330 build points a side. Trucks: the best matches 3-4 deliveries with both sides trucking, a load-and-deliver run in under 3 minutes; still matches with no depot after 20 minutes."),
    (21, "supply trucks carry the income", "20 Oct, from 11:14",
     ["AI Conflict fork: the world's minefields lying across roads are removed at the start - TM-62M rows across both main bases' exit roads blew up 191 of 342 vehicles on 20 Oct (found by a probe of the spot; a 50 km/h speed limit A/B ruled out driving).",
      "AI Conflict fork: a main base's vehicle depot keeps searching for a site (6 windows, 3x the sites) - the US main base on the coast never got one, so trucks drove 2.5 km round to load there.",
      "Cover layer: teams waiting for or boarding their vehicle are left where they are - 85% of boardings timed out when they were sent to cover 40-60 m away.",
      "Anti-drone fire: a suppression sphere that clamps its height range (the game's NaN stopped two watched matches).",
      "The main base's long depot search is off by default: it took the planner's whole search budget and no base built a depot.",
      "Driving measured: [ZCR][DRIVE] speeds every 30 s, kmh= on vehicle losses; the game's cruise limit as an option (-zcrCruiseSpeed).",
      "Fighting distance counts enemy kills only: the 'point-blank gunfights' (median 3 m) were crashes and suicides; enemy kills median 30 m.",
      "AI Conflict fork: bases ask for a supply truck below 35% and are filled to 50%; a donor keeps 50% and gives above 55%; a base it owns keeps 200 back (was 500).",
      "Lab income (180 a minute) goes to each side's main base only, so the front bases need trucks.",
      "Engine page: the main problems charted per build at the top; doctrine-v-doctrine matches counted (they were left out of every chart)."],
     "Martin: no supply trucks seen. In the night logs 70 depots were ready, 46 jobs, 39 trucks, 2 unloads: the lab paid income to every base, so no base asked.",
     "Test 1 (65/75/80): 3 jobs, 2 trucks, nothing loaded. Test 2 (35/50/55): the truck burned on the way to load - on the minefield. With the speed A/B: 3 jobs, 1 load, 2 unloads. Mine fix: two matches running."),
    (20, "danger awareness, anti-drone fire, defend in buildings", "20 Oct, from 02:25 (final 05:16)",
     ["Danger layer: high danger (threatened, enemy within 150 m, a kill zone, a drone within 150 m) - never standing; medium - crouched when still.",
      "Drones: prone every second within 150 m with nothing overhead; buildings first for cover; small-arms fire at drones (up to 3 shooters, MGs first) with a chance to bring them down.",
      "Defend orders at each base's building cluster (25 m) instead of the open spawn point; every AI Conflict order a wedge instead of a column.",
      "Kill zones: march steps keep 60 m from the side's losses of the last 3 min.",
      "Vehicles: wrecks removed 60 s after they burn out; a spectator (the watching camera) no longer blocks rescues and cleanup; every third team rides an armed light vehicle.",
      "Builders: depots before armories; the lab gives starting supplies and an income; a fortification (bunker) type."],
     "Martin: they don't care about danger; killed by drones outdoors with a house right there; defense against drones with small arms; the next team walks into the kill zone; vehicles crash into wrecks and get stuck; use combat vehicles; supply trucks not used.",
     "42 matches overnight: screen checks 81% -> 91%; drone victims standing 91% -> 40%, prone 0.5% -> 26%; in high danger standing 72% -> 10%; 21 drones shot down per side per match; riding 45% -> 69%; 205 wrecks removed; losses 56 -> 46. Still open: supply trucks (2 deliveries in 42 matches), point-blank gunfights (median 3 m)."),
    (19, "doctrine v doctrine, held prone, standoff, script speed", "19-20 Oct, from 23:35",
     ["Speed set by the game itself (the Diag Menu's engine values) - no key presses at match start.",
      "Soldiers hold 60 m from an enemy seen in the last 15 s (the game's attack closed to 15 m), except within 150 m of an enemy base.",
      "Prone under a drone held 15 s by the game's stance setting; cover spots 6 m from every soldier already there.",
      "Supply trucks: AI Conflict's automatic scheduler back (it had become manual-only).",
      "Free look and orbit with the right mouse button, REPORT, IDs in captions (team A3, drone team 4), team goals, supplies in the panels.",
      "Charts: what the screen shows (scorecard), pace, dead lying prone; doctrine v doctrine matches as their own line.",
      "GOALS in each side panel: attack, hold, resupply, engineers now, built so far.",
      "Fortifications: a bunker building type for AI Conflict's builders (two per base near the front); 800 starting supplies in the lab.",
      "/good and /bad reports: lab/report.py gathers the moment, the team's log and frames into a numbered note; scorecard checks for the drone panic."],
     "Martin: those keys don't work on free look / the mouse rotates always; keyboard hijacked, Arma crashed; investigate reckless soldiers; no supplies transported by trucks; IDs in the messages; good and bad reports.",
     "Script speed: measured 2.8x with no keys. The rest to be measured when the matches resume."),
    (18, "cover, panic, scan, rides you can see", "19 Oct, from 22:05",
     ["Idle soldiers anywhere go under a roof or canopy within 40 m, 6 m apart.",
      "Drone panic from 250 m: each to his own covered spot, or spread out 15-25 m, then down.",
      "Drones never hang: on after 15 s, a 250 m sweep, then home; searches never over the enemy's main base (it camped the spawn).",
      "Rides from 300 m, 16 vehicles per side; tags over vehicles with who is aboard; the camera cuts to vehicles; riding measured as soldiers in moving vehicles.",
      "Watched and batch matches: our doctrine against our doctrine, AI Conflict alone as the side check."],
     "Martin: infantry chilling on the base while massacred by drones; no units use vehicles; they should panic when they hear a drone; drones hang in the air; vehicles miss tags; doctrine v doctrine.",
     "6-minute probes: soldiers riding in 58-83% of samples, 89-93% react to drones, sweeps instead of hovering; Martin 22:08-22:09: a nice reaction from a Soviet soldier, the dismount worked."),
    (17, "our own AI Conflict: rides, covered steps, jog", "19 Oct, from 21:51",
     ["AI Conflict (our fork) let no infantry team ride - not one ride all day; now infantry teams ride light transport (M998, UAZ) on marches over 500 m.",
      "Each 220 m march step ends at the best cover within 60 m (trees, roofs, buildings, walls, rocks); teams jog between points.",
      "AI Conflict's side flies a drone team every 2 min, up to 3 (was 4 min, 2).",
      "Watch: a TEAMS / VEHICLES / DRONES button - PREV/NEXT steps through teams, vehicles or drones in the air.",
      "lab/scorecard.py: pass/fail per side on what the screen shows - first team out, % at the main base, team size, drone teams, drones up, rides."],
     "Martin: no cars, no use of cover, no drones, sitting ducks - how didn't you notice? You'll have to do our own version of AI Conflict.",
     "8-minute probe: every check passed on both sides - first team out at 1.8 min, 31-33% at the main base, teams of 3.1-3.8, drones up 60-80% of the time, 20 teams rode."),
    (16, "teams out at once, drones search", "19 Oct, from 21:28",
     ["Fireteams start with 3 of 5 and leave the base with 3 (AI Conflict started them with 1 and recruited one soldier at a time: teams waited 10-20 min at the base).",
      "Drones: with no enemy known, a search over the objective, the enemy's other bases and its staging area, instead of no team; the drones spot for their side (300 m, line of sight); a team with no drone left frees its launch slot.",
      "Measures: % of soldiers at the main base (on the panel), drones in the air every 30 s."],
     "Martin: 0 drones in the sky; soldiers chilling at the base doing push-ups; all groups are one guy.",
     "First match: teams left at 1.8 min (12.5 and 21 min before), 16-21% at the base at 10 min (100%), drones: one side searched and flew 7 at once; the other side's slow baseline still flew little."),
    (15, "drone reaction", "19 Oct, from 20:40",
     ["Soldiers within 150 m of an enemy drone stay under a roof or canopy, run to overhead cover within 30 m, or get down; survivors scatter after a hit (Arma 3's droneThreat).",
      "Measured: % covered, running and prone near drones; drone victims in the open and standing."],
     "Martin: infantry walks exposed; with drones about they should run like hell to cover - and measure it in detail.",
     "Baseline before: 89-100% of drone victims in the open. Overshadowed by the regression found at 21:30 (no drones, teams at base)."),
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
    head_charts = progress.headline(agg)
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
  <a href="#main">Main problems</a><a href="#now">Now</a><a href="#progress">All measures</a><a href="#probes">Probes</a><a href="#how">How a match runs</a><a href="#commander">Commander</a><a href="#drones">Drones</a><a href="#camera">Camera</a><a href="#problems">Open problems</a><a href="#next">Next</a><a href="#engine">Engine facts</a><a href="{changelog_url}">Changelog ↗</a>
</nav>

<h2 id="main">The main problems, measured <span class="ref">PER BUILD, FROM R14</span></h2>
{head_charts}

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
