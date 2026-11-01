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
    "Running now": "Nothing (1 Nov 23:00) - Martin is playing; the long-walk fixes are in and measured.",
    "Supplies (r30-r32)": "Front bases now live on supply trucks (the free refill is off). Depots came late - the building planner checked about one site a second, lost orders when a squad died, and both Arland main bases are coastal with no depot site - fixed in r31-r32: headless, depots at minute 5-6 and 4 loads delivered in 15 minutes. Still open in watched matches: trucks drive slowly (AI vehicles a median 8-19 km/h) and die to drones on the way.",
    "Armour (r26-r27)": "Each side buys a crewed tank and IFV at its HQ - M1A1 Abrams / T-72, M2A2 Bradley / BMP-1 (armour mods, loaded in the watched matches from 05:17), else the game's LAV-25 / BTR-70 - and sends it to its front; the crew stays aboard and fights from the vehicle. Headless armour-5 and -6: all four units got into the assault on their front, 14 and 10 enemy killed, none lost. Open: friendly fire and soldiers run over (1-4 a test, now slowed for), stuck spots out of the HQs, 2 watched-match crashes since armour went live (cause not proven).",
    "Being built next": "The last long walks: a ride that fails at the HQ bars the team 3 min (the cooldown); one stuck soldier sinks the ride; rides through the checkpoints on the main roads; the Farm battle's seat fallback (Martin's call).",
}

# (chip class, chip text, title, text) - what changed most recently.
NOW = [
    ("good", "r61", "Teams walk far only when a ride breaks down",
     "Martin, watching: 'really the only should walk long distances when car broke down'. Two teams walked 2.1 km at the start: one's vehicle spot was taken by another team's vehicle and AI Conflict looked for another only after 60 s - the team was 500 m out by then; the other was refused by the limit of 10 vehicles a side (12 teams). Now a taken spot is looked for again after 10 s (the first such team had its vehicle 19 s later), 12 vehicles a side, and no ride spacing. Watched: trips of 1 km+ on foot 14% (18% overnight), none from these two causes; boarding 29 s, the wait at the base 39 s."),
    ("good", "r61", "A slow drop-off no longer bars the next ride",
     "6 of 8 failed rides in the watched run delivered their team - one soldier was slow to get out - but counted as failed: the team was barred from rides for 3 minutes and walked its next trip, 1.2-2.1 km (5 of its 7 long walks). Now no ban after a slow drop-off. Headless run: all 26 trips by vehicle, 0 of 22 trips of 1 km+ on foot (5 of 35 watched, 17 of 96 overnight). Its 7 script errors are AI Conflict's resupply (the same exception on 25-27 Oct), not this change."),

    ("info", "r60", "Spacing rides apart doesn't help",
     "Martin's 'maybe some kind of timing': rides out of a base 8 s apart. Farm battles, 4 with it v 5 without: rides delivered 30% v 41%, failed at the HQ 18% v 7% (teams queued, then timed out), a base captured in 3 of 4 v 5 of 5; no jam either way. Transport test: north 8.4 v 8.6, south 7.5 v 8.3 soldier-km a minute. Recommend no cap and no spacing - Martin's call."),
    ("info", "r60", "Watched transport run",
     "Martin watched it at 02:04: 7.6 soldier-km a minute, 88% of trips by ride, 25 of 33 rides delivered, none failed at the HQ, boarding 40 s. One Humvee left the road by 14 m beside 7 minefield signs and blew up - 4 dead (most likely a mine)."),
    ("info", "r60", "'Failed' rides at the front",
     "The Farm battles' most common ride failure, 'group cohesion', is checked while driving: every case was 320-700 m from the objective, at the fighting - someone bailing out after the ride carried the team most of the way."),
    ("good", "r59", "No cap on rides - they start 8 s apart",
     "At most 3 rides could be leaving a base; the 4th team walked off while it waited and often walked the whole way (rides held 78-160 s; most of the trips done on foot). Martin: 'fuck cap' - gone; rides out of one base start 8 s apart instead. Transport test, same HQ: 4.8 / 6.2 -> 7.4 / 9.2 soldier-km a minute (south), ~8.4 (north); rides on 82-86% of trips (62%). The Farm battle without it: twice the rides, 43% of the Soviets at Farm by minute 5 (4%), Farm taken at 5:29 - and no jam at the HQ."),
    ("info", "r59", "Where a team's 20 minutes go",
     "Walking about half, aboard a quarter (43 km/h on the road), the rest standing or around the vehicle. The loss was before the ride: the cap, a cooldown after a failed ride (~140 s when it hits), and the team walking back 100-170 m to a vehicle at the base it just reached."),
    ("bad", "r59", "Checkpoints on the main roads trap rides",
     "Four spots are half of all stuck vehicles in 30 runs. Two are checkpoints the main road runs through - granite boulders laid as a chicane at (2025,3464), wooden walls at (3095,2659): the game's drivers fail the chicane. The others: Military Training Area's junkyard and a rocky beach the command truck drives onto."),
    ("info", "r59", "Dropping closer than 150 m doesn't pay",
     "Rides dropping their team 100 m from the target: within the noise, and most routes then found no road that close and drove across country - not taken."),

    ("good", "r58", "Boarding nearly halved",
     "Teams wait about 60 m from their vehicle. The driver used to run over alone while the other three stood still, then they ran the same 60 m. Now they walk over with him (AI Conflict's own per-soldier walk, which it only used beyond 90 m): boarding 60 s -> 35-39 s, the wait at the base 90-100 s -> 65-71 s."),
    ("good", "r58", "Ride vehicles appear by a road",
     "A ride's vehicle took the clear spot nearest the base's centre - at Military Training Area inside its junkyard, and by the main base 60 m off the road: half the stuck vehicles in the transport test were rides still by their pad. Clear spots within 12 m of a road now come first; the main base's moved onto its road."),
    ("bad", "r58", "Military Training Area keeps its junkyard pads",
     "Its spots by the road are on a slope - 1.0-1.5 m difference under the vehicle - and the crash guard from 27 Oct (rides spawned on slopes crashed the server) allows 1.0 m. Loosening it is Martin's call."),
    ("info", "r58", "A whole team loses its ride for one soldier",
     "Every boarding timeout traced: three soldiers in, the fourth idle 2-35 m from the door after the game's get-in stalled and the retries ran out - about 80 s of waiting, then all four walk. Next: leave without him."),

    ("good", "r57", "Rides fail far less",
     "The new transport integration test showed most failed rides were teams not reaching their vehicle in time: the whole team had 90 seconds - real seconds, so 30 game seconds at the 3x Martin watches at - and after a trip it is strung out. Now 180 game seconds: failed rides 38% -> 13%, delivered 41% -> 63% (three runs each)."),
    ("good", "r57", "A taken base is kept, even a quiet one",
     "AI Conflict dropped a friendly base whose spawn point wasn't active yet - a base just taken - from every team's list, so the taken Signal Hill was left and everyone walked home. Now it stays on the list, switched off, and our rules switch it on."),
    ("info", "r57", "Where a ride's time goes",
     "Walk to the vehicle 26 s, boarding 60 s (the driver alone first, then the passengers), drive about 4 min, getting out 14 s. Jogging soldiers make ~12 km/h, so a 1.4 km ride only pays when nothing goes wrong before it leaves - boarding is the next thing to speed up."),

    ("good", "r56", "The Soviets ride jeeps",
     "Martin, watching: 'trucks could carry more than one team, waste of space' and 'why dont you use uaz and some smaller cars for smaller teams?'. Every Soviet ride was a 15-seat Ural with one 4-man team: the van counts only its 2 working seats since 30 Oct, and the UAZ-469 jeep was not on the list. The boarding test: the jeep 99.8% aboard, 10 s to board, as good as the Ural (the van 61-76%). It is now the Soviets' first light ride; in a short check 4 of 4 Soviet rides were jeeps. The US already rode 4-seat Humvees."),
    ("info", "r56", "The airfield spot, watched",
     "A camera mode for the lab (-zcrCamSpot) kept the view on the airfield edge west of Farm and followed the nearest ride. This match no truck stalled there: three Urals drove through at about 33 km/h and dropped their teams at the plan's assembly point. The failed Soviet rides were all at the HQ, while boarding."),

    ("good", "r55", "The van fix seen in the window",
     "The Farm battle with the Soviets at the harbour HQ, the same setup as the 29 Oct match with the old van: Farm taken at 11:36 instead of 19:29, 10 Soviets there by minute 8 instead of 0, boarding timeouts 0 instead of 68, Soviet rides delivered 4 of 11 instead of 1, Soviet losses 5 instead of 16, no script errors (8 before). Every Soviet ride was a Ural."),
    ("good", "r55", "A taken base is held",
     "In the first two battles of the evening the US attack teams were sent back to their own HQ 1.1 km away minutes after taking Farm, and fetched Humvees to drive home. AI Conflict leaves a held base off an attack team's list, so our rule 'main effort taken: hold it' never found it. Now it does: in the third battle all 7 Soviet attack teams stayed, 18-21 Soviets on Farm to the end."),

    ("good", "r54", "The van bug: verified and fixed",
     "Martin's hunch ('it can be just van bug'): in the van sub-lab the UAZ-452's driver and front seats took 56 of 56 soldiers, its six back seats 2-14 of ~40 each, and most who got in couldn't get out; the M998 and the Ural with the same soldiers 100% and 99.9%. The van now counts its two front seats, so bigger Soviet teams ride Urals. Farm test, Soviets at the harbour HQ: Farm taken in 4 of 5 runs with the fix, 0 of 3 with the old van; 12 soldiers there by minute 8 instead of 1."),
    ("good", "r54", "Drone trucks beside cover, operators through cover",
     "The truck parks beside trees or buildings (Martin's report 434: on the runway); operators walk in 100 m legs that end under cover (report 436: on the road); a leg that goes nowhere falls back to the straight walk."),
    ("bad", "r54", "The crash in the game window is not explained",
     "Four crashes of one kind since 25 Oct, all inside the engine's entity update, nothing of ours in common before them. The lead (a soldier moved onto a tilted M60 tripod 0.2 s before) did not reproduce: hundreds of tripod boardings, tilted and flat, 0 crashes."),

    ("good", "r53", "Approaches chosen from what happened",
     "lab/attackscore.py scores every approach from the sub-lab runs: per HQ and approach, soldiers at the objective by minute 12 and whether it was taken. The planner's --export measured takes the best measured approach per HQ, or no plan where none beat AI Conflict's own; Gemini now sees the same results and answered the same: from the harbour HQ the south-west (22 soldiers by minute 12, taken 2 of 3 and 4 of 4), from the south HQ no plan (every plan did worse, 4-6 soldiers against 7)."),
    ("good", "r53", "Trucks and vans only, armour off the exit road",
     "The watched matches ride transport only (armed rides delivered 1 of 39). Armour bought at an HQ now spawns 400 m toward the front in every match - checked: a Soviet APC 353 m from its HQ, 0 script errors."),

    ("good", "r52", "Attacks planned from the map",
     "A ground scan (what a defender on Farm sees, roofs and trees) and three plans per HQ in seconds: an assembly point hidden from Farm, the drive, three cover-to-cover lanes, a hold line, a support position, hiding spots from drones. Gemini picks one from the map image with reasons; the teams play it - rides to the assembly point, legs on the lanes, a hold inside AI Conflict's approach logic. From the harbour HQ the south-west plans took Farm in 6 of 7 runs (19-22 soldiers by minute 12) against 4 of 8 without a plan (14)."),
    ("good", "r52", "Rides that deliver",
     "Transport rides only and the armour no longer parked on the HQ's exit road: the harbour side had 11 soldiers at Farm by minute 8 instead of 3, with no plan at all."),
    ("bad", "r52", "Neither Gemini nor the algorithm reliably picks the good approach",
     "From the south HQ every plan (from the east - a 3 km drive round - or from the south) did worse than no plan; Gemini's first pick for the harbour HQ (from the north) was no better than no plan. Next: choose approaches from measured results."),

    ("good", "r51", "The panels count the soldiers again",
     "Martin: 'it showed 0 soldiers for both sides'. The count came from the camera's soldier list, refreshed only when it cut to a new shot - locked by his buttons from game second 9, before anyone had deployed, it stayed empty all match. Now refreshed every 5 s."),
    ("bad", "r51", "Rides jam inside the HQ",
     "In the one-point runs up to 9 rides of one side were boarding or leaving one HQ at the same moment; 15 of the 16 rides AI Conflict gave up as 'stuck in transit' were still within 70 m of the HQ. With at most 2 leaving at a time: failures 4 instead of 12, 18 soldiers at the point by minute 8 instead of 7 (one headless run) - walking still brings 36-40."),

    ("bad", "r50", "Rides make the assault later and smaller than walking",
     "One point (Signal Hill, 1.6 km from both HQs), 12 teams of 4 a side: on foot 16 US and 24 Soviet soldiers were within 300 m by game minute 8 and 27/17 by minute 12, both sides arriving together; with AI Conflict's rides 8/4 and 4/3 by minute 8 - a few vehicles arrive alone, the rest stall at the HQ (few dry pads at the harbour, a passenger whose get-in never starts) or are given up stuck on the way."),
    ("good", "r50", "Teams no longer come back for nothing",
     "Martin, watching team A10: 'they are walking 1500 meter', then back to the HQ for a car. Of 12 Soviet attack teams 9 had been pulled back to recruit (the side already at its cap) and 5 turned back for a ride; after the fixes 0 and 0, and every team's first order goes to a real target."),
    ("good", "r50", "The main effort binds; a taken objective is held",
     "The holding side raided an avoided base and every attack team flip-flopped between guarding it and the assault (39 target changes); after the capture every attack team went home. With -zcrBindMainEffort the attack teams stay on the main effort and hold it."),

    ("good", "r49", "Drone pilots fly from their post",
     "Martin: 'this is clearly a bug: drone operator being out in the open'. A pilot put his goggles on and froze wherever he was whenever a drone of his side was up - 36% of 491 flights started over 30 m from his covered post, 7% over 200 m; one sat by the Airport Base runway 1 km from it. Now a flight starts only within 15 m of the post."),
    ("good", "r49", "Every base to a side; mostly bunkers",
     "Martin: 'why is FIA owning bases ... make it one side or the other' - the two supply-depot bases are split too now. 'For defense mostly bunkers and covered stuff, not sandbags so much' - 9 matches had built 96 sandbag positions and only 35 bunkers; now of every 8 fortifications 4 are bunkers and 2 roofed towers."),
    ("bad", "r49", "Assaults that never arrive",
     "Martin: 'I see just soldiers chilling at bases'. Of 12 Soviet attack teams in the assault on Military Training Area only 2 were really sent there and both stuck leaving the HQ by vehicle; 3 lone survivors (2-man teams) went home, 2 guarded the HQ, 5 went to other bases - AI Conflict's own scoring overrides the main effort. In 40 minutes no Soviet soldier came within 300 m. The assault sub-lab is built to fix it."),

    ("good", "r48", "Long matches: 40 game minutes",
     "Martin: 'do a longer match than 25 min so we see what actually happens, let's give it 40m'. The watched loop now ends a match on the game clock (under 3x the wall clock stopped it at 33-35 game minutes). Overnight 26 of 28 matches ran 30+ game minutes, 23 the full 40. FPS: 43 in the first 5 minutes, about 28 by minute 10-15, then about 26 to minute 40. Modern won 10, phased 8, 8 drawn; the USSR won 11, the US 7 - on Arland the side matters more than the doctrine so far."),
    ("good", "r48", "Rounds that were never fired",
     "Rifle and machine-gun rounds piled up at the world origin: 1000-1900 by game minute 40, 3000 in 8 minutes of a crash test where the sides fought. Probes found them at exactly 0,0,0, still, with no shooter, never fired by a soldier - made by the game itself (most likely its ballistics for the AI's aiming) and never removed. They cost little (no per-frame update), but they are now deleted every 2 s (-zcrProjSweep); 473 at once caused no crash."),
    ("good", "r48", "What the frames go to",
     "Over 310 census snapshots of 15 matches, vehicles follow the frame rate most closely. The empty ones (about 16) sleep and cost little; what grows is vehicles in use - crewed 6 -> 30 and physics awake 3 -> 22 by game minute 20. The FPS drop is the war growing, not clutter."),
    ("good", "r47", "The crash fixed",
     "Soldiers climbing into a LAV-25 crashed the server - the engine's climbing animation, on a tilted LAV-25 almost every time, on level ground sometimes. A soldier who has walked up to a LAV-25 now goes straight into his seat (ZCR_SafeBoarding; other vehicles the same when tilted over 8 degrees). Battles: 0 of 60 crashed with it, 6 of 60 without; the confirmation 0 of 40."),
    ("good", "r44", "Drone teams on sorties",
     "Martin's model: 'operators have big bags with some drones; the drone truck or a static arsenal is where they resupply; Zeus Commander plans where the truck goes, the operator just knows where he can resupply'. The pilot carries 4 FPVs, walks with his guard to a covered spot 60-200 m from the truck, launches one at a time from the open sky beside it - the goggles go on only while he flies, the controller in hand, holding still - then walks back and loads 45 s. The commander puts the truck 1 km back from where its drones go (the main base's site stays put); the truck has its own driver. Martin: 'fucking great'."),
    ("good", "r43", "The drone operator",
     "Martin: 'the drone operator should be seen with a tag, seek cover, and when he controls a drone have the controller in his hands and goggles, and be stationary'. The operator team's first soldier is the pilot: Realistic Combat Drones' FPV goggles in place of his helmet and its drone controller in his hands while his FPV flies; he kneels at his post in cover and holds still (his AI off for the flight - blind behind the goggles, his guard watches). 'DRONE OPERATOR - flying FPV' on the watch screen. Martin: 'this is fucking great!!!'"),
    ("good", "r43", "One FPV at a time; soldiers into buildings",
     "The drone storms (infantry sub-lab): an operator launches one FPV every 35 s (they flew in fours). Soldiers near a drone with a building's inside within 15 m run in at danger priority and stay while it is near (farm: 5 of 8 runs ended inside; of 89 earlier drone victims 1 was under a roof). Our fire at drones holds while a friend is near the drone or the line of fire. Found on the way: the FPV mod's Soviet stations brought a 6-man squad each (fixed in the mod)."),
    ("good", "r43", "DCO is the tactical layer; 50 soldiers a side",
     "Martin decided 24 Oct 12:47: DCO_AI runs how soldiers fight, our commander decides where squads go (our bridge addon uses DCO's own per-group switches; nothing of DCO changed). FPS follows the soldier count (~37 at 125 AI, ~17 at 240): our AI Conflict fork caps each side at 50 AI soldiers, builders, crews and operators included; DCO's Light detail for squads far from the enemy."),
    ("good", "r42", "Supply runs, as Martin described them",
     "1) An empty truck drives to the supply point, loads the game's supply container (1500 for a Ural), drives to the point to be supplied and unloads. 2) Manpower: a squad waits off the road by the pickup, the truck drives up and calls it in (all 6 aboard in 15-45 s), drives to the destination, they get out. No mixed loads (Martin: 'even real players don't do that'). One truck at a stop at a time: the next waits 120 m short. Headless, 10 minutes: 2 supply trucks 3000 supplies, 4 trucks 6000, none lost; manpower 6-12 soldiers so far - the trucks lose 1-2 minutes turning round at the pickup."),
    ("good", "r42", "Crossing rule",
     "Martin saw trucks hit each other where they met at a junction. The head-on rule only reacts to a car on the same line (8 m either side), so at the junction bend they were noticed 9-26 m apart - three hits in that run. Now two vehicles whose paths cross ahead of both within 50 m, reaching the crossing within 3 s of each other: the later one stops until the other is 6 m past (8 s at most). First run with 4 trucks: 7 give-ways, 1 light touch; measured next against the same run without it."),
    ("good", "r41", "Integration tests",
     "Martin: 'all these tests should be reproducible ... they will act as integration tests'. 12 small scenarios played headless for 3-8 minutes, three at a time, each with pass checks (head-on lane, convoy past a wreck, minefield cleared, traffic, spot far, crews stay aboard, tanks, storm, APC and tank head-on, supply run, manpower run). The first full run caught a real regression the same hour. Every run saves its command, commit and uncommitted changes; lab/rerun.py replays one on its commit."),
    ("good", "r41", "Armour crews stay and fight",
     "When the game gives up a vehicle's move (route blocked) it orders the crew out - BTR crews walked away from undamaged vehicles and were shot on foot. Crews of armed vehicles now stay aboard while it is at least 35% intact and fight from it. On Arland's airfield (one of the map's 9 clear 800-m lines) crews notice enemy vehicles at ~490 m though they can see 750-800 m; spotting 3x faster: 610 m, first shots ~525 m. The storm: an Abrams in overwatch, a LAV-25 carries a squad to 250 m short of the enemy, they dismount and storm, the LAV follows them in."),
    ("good", "r40", "Our vehicle rules, measured",
     "One speed arbiter for every rule (the slowest request wins), the spacing rule and the head-on slow-down (both cars to 15 km/h). 79 night runs on 9 test tracks: head-on crashes on the narrow lane 5 -> 0 a run, Ural trucks both ways 6.5 -> 1.5; no Workshop driving mod (CRX, JMVehicleAI, Competent AI, road price) added anything; a collision forecast (v2) built and shelved. Watched block (16 matches): Arland jams 8 -> 4.8, long stops 4.8 -> 1.4 a match; still ~4 car-on-car hits a match."),
    ("good", "r39", "A game crash found and fixed",
     "The crash log of a watched match pointed into AI Conflict's vehicle cleanup: it asked the engine for an exit spot for a soldier caught getting in or out of a vehicle, with no seat yet - a null read that had ended three watched matches (20 Oct and twice on 22 Oct). Now only a seated soldier is forced out, in the cleanup and the dismount flow. Other crashes still have no script in their stack: the old 03:16 code crashed in 2 of 5 matches too, so they are not tonight's driving changes."),
    ("good", "r39", "Pushed, not teleported",
     "Back-offs (a jammed vehicle backs 8 m) and park-asides (an abandoned blocker moved off the road) gave our best traffic - 2.0 jams and 2.8 long stops a match - but they teleported the vehicle, and hand moves came with crashes. JMVehicleAI's anti-stuck showed another way: set the vehicle's velocity a few times a second and the AI driver doesn't fight it. Our moves now push the vehicle at 2.5 m/s with its heading kept (headless: 8-m back-offs moved 5.3 and 7.7 m in 3.5 s). Watched from 21:15."),
    ("bug", "tested", "JMVehicleAI: worse jams on our maps",
     "The Workshop's driving mod (back up and retry, curve braking, convoy spacing, oncoming traffic waits) in 9 watched matches: as shipped, jams 7-21 a match; tuned by a small addon of ours (no convoy waiting, 15-s yields) Everon 13/5/1, Arland 10/14 - against ~1 and ~6 without it. Its obstacle braking (1,086 times in one match) holds rides behind the vehicles parked at the bases. Dropped; its push kept. New lab rule (Martin): look for an existing mod before building a fix - lab/workshop.py gets and unpacks one."),
    ("good", "r39", "Vehicle weapons measured",
     "Martin: 'measure the use of guns and weapons of vehicles'. The game reports no AI turret shots as events, so each manned turret's loaded rounds are read every second: shots by side and weapon, gunners and vehicles that fired, guns standing empty (AI gunners are said to fire one magazine and never reload - AI Turret Reload Fix), kills by turret gunners. Progress charts: targets and kills, shots fired, guns standing empty; and 'Vehicles hitting things' from the new collision log."),
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
    ("issue", "AI Conflict's own checks", "The original passes 66/66, our fork 51/66 - mostly deliberate changes the checks don't know, plus the supply-truck road routes adding waypoints outside the vehicle handoff (25 Oct).", "review note 442"),

    ("bug", "Attack teams don't reach the objective", "Partly fixed in r50: the main effort binds (-zcrBindMainEffort), no recruit trips or turn-backs. Left: 2-man teams turn into lone survivors after one loss; the rides (above).", "review notes 433, 439"),
    ("bug", "Drone sites in the open", "The drone truck parks on clear ground by design (it took a runway) and operators walk 500-700 m to launch spots by road.", "review notes 434, 436"),
    ("bug", "Armour waits for crew in the open", "A BTR-70 that lost 2 of 3 crew waited 3+ minutes for new crew, unmoving, until a drone hit it.", "review note 435"),

    ("bug", "Crashes in long matches", "3 early ends in 26 long matches: two engine access violations during the entity update (one kind seen 6 times this week) and one freeze the game's watchdog closed after 300 s. None is the LAV-25 crash, and nothing of ours lines up before them. All 3 came with the US on phased and the USSR on modern (3 of 12 such matches, 0 of 15 the other way round; p 0.08 - to watch).", "review note 422"),
    ("design", "Fewer vehicles for frames?", "Vehicles in use grow 6 -> 30 in a match and the FPS follows (about 26 late). AI Conflict allows 16 a side (-aicfMaxVehiclesPerFaction); 4 a side gave no gain in 12 minutes on 25 Oct, before the war had grown. It changes the game - Martin's call.", "review note 422"),
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
    "A ride that fails at the HQ bars the team 3 minutes, and it walks the trip: let it ask again sooner while it is still at the base.",
    "A ride leaves without one stuck soldier instead of failing for the whole team.",
    "Get rides through the checkpoints on the main roads (boulder and wall chicanes trap them).",
    "The Farm battle's seat fallback: still off although Martin said 'back on' on 30 Oct (Martin's call).",
    "The attack-plan arrows: plans updated after a capture, buildings held around the objective (with Martin).",
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
    (61, "teams walk long only when a ride broke down", "1 Nov 21:20 - 22:45",
     ["AI Conflict fork (00798da): a team whose vehicle spot was taken looks again after 10 s, not 60 (-aicfSiteRelookMs); 12 vehicles a side, not 10; no ride spacing by default.",
      "AI Conflict fork (22:45): no 3-minute ride ban after a ride whose drop-off ran out of time (-aicfDropoffCooldown as before).",
      "Transport test: variants nowalk, nowalk2; the older variants pinned to what they ran. The Farm battle follows the fork's defaults (no spacing, 12 vehicles)."],
     "Martin, watching the transport test: 'i still see some team walking long distanes', 'really the only should walk long distances when car broke down or some shit', 'go run again', 'great' (notes 483-485).",
     "Trips of 1 km+ on foot 18% -> 14% (watched), none from a taken spot or the vehicle limit; failed rides 4-9 -> 2 a run, boarding 37-42 -> 29 s, the wait at the base 54-68 -> 39 s."),

    (59, "no ride cap - rides spaced 8 s apart", "31 Oct 22:40 - 1 Nov 00:50",
     ["AI Conflict fork: rides out of one base start 8 game s apart (-aicfRideSpacingMs, 032d534); the Farm battle has no rides-per-base cap any more (Martin: 'fuck cap').",
      "Transport test: a defend team at its forward spot has arrived (it stood up to 7 min uncounted); variants now / cap5 / cap0 / drop100 / spaced / spaced4; the older variants pinned to what they ran.",
      "Assault test: storm-plan-measured-cap0 (the Farm battle with neither cap nor spacing)."],
     "Martin: 'ok lets work on those transports until we are happy with other params', 'cap is retarted maybe some kind of timing so its not at once but fuck cap' (notes 480, 481).",
     "Soldier-km a minute: 6.4 this morning -> 8.4-8.5 (north HQ) and 7.4-9.2 (south HQ); trips on a ride 62% -> 85%; the wait before leaving 93 s -> 50-54 s. The Farm battle without the cap: no jam at the HQ."),

    (58, "faster boarding, ride vehicles by a road", "31 Oct 21:00 - 22:40",
     ["AI Conflict fork: during the driver and gunner phases the other soldiers walk to within 12 m of the vehicle (-aicfWalkOverMeters, on by default; 7e776fd, d47c7d6).",
      "AI Conflict fork: a ride's vehicle appears on clear ground within 12 m of a road first (-aicfPadNearRoadMeters, on by default; a0aa437, d47c7d6); [ZCR][PADROAD] logs each base's spots by a road.",
      "Transport test: runs with the seat fallback on, as the battles (variant 'now'); older variants pinned to what they ran; a stuck-at-pad count."],
     "Martin: 'you should try some optimization on that integration test scenario because I noticed its an issue', 'do what you recommend' (notes 474-479).",
     "Boarding 60 s -> 35-39 s, the wait at the base 90-100 s -> 65-71 s (3 runs); stuck at a pad ~2 a run -> 0 except Military Training Area. Soldier-km a minute within the noise."),

    (57, "the transport integration test, fewer failed rides", "31 Oct 13:45 - 17:35",
     ["The transport integration test (lab/transporttest.py, ZCR_ShuttleTest.c): the US holds every base (-zcrAllBasesTo US), the Soviets field no teams (-aicfNoForces USSR, fork), nobody wins (-aicfNoVictory, fork); every US team is sent base to base and each trip is measured.",
      "AI Conflict fork: a quiet friendly base whose spawn point isn't active stays on the teams' lists switched off (f0ec0ac) - a taken base is no longer abandoned.",
      "AI Conflict fork: a team has 180 game seconds (not 90 real) to reach its vehicle spot (0e6f0d6, e4003bc).",
      "Lab app: the Sub-labs tab is now 'Integration tests'; lab/reforger.py --commander-mode."],
     "Martin: 'prepare transport sublab ... moving of manpower as efficiently as possible (no enemy on the map)', 'soldier are not being transported properly', 'we should measure how efficiently we are transporting soldiers over the map', 'try some optimization' (notes 471, 474-477).",
     "Failed rides 38% -> 13%, delivered 41% -> 63% (3 runs each). Tried without gain: rides only over 1 km, a wider vehicle spot, the team waiting closer to the vehicle."),

    (56, "the Soviets ride jeeps, not half-empty trucks", "31 Oct 12:47 - 13:25",
     ["AI Conflict fork: the UAZ-469 jeep is the Soviets' first light ride, 4 seats counted (ba2859a) - 4-man teams no longer take a 15-seat Ural.",
      "ZCR Director: -zcrCamSpot x,z,from,to keeps the camera on one spot and follows the nearest ride (96ad357); lab/assaulttest.py --cam-spot.",
      "Van sub-lab: the UAZ-469 test uses the jeep's real prefab (bf89041) - the 30 Oct run had a wrong ID and nobody boarded."],
     "Martin, watching the Farm battle: 'trucks could carry more than one team, waste of space', 'why dont you use uaz and some smaller cars for smaller teams?' (review note 465).",
     "Boarding test, Soviet squads: the jeep 99.8% aboard, 10 s to board, 5 left inside in 17 rounds (the Ural 99.9%, 10 s, 9; the van 61-76%, 44). Short check: 4 of 4 Soviet rides were jeeps, 0 script errors. The watched match: no stall at the airfield spot; the Soviets took Farm at 20:32."),

    (55, "the van check in the window, attack teams hold a taken base", "30 Oct 15:33 - 23:56",
     ["AI Conflict fork: a held base stays on an attack or reserve team's list, switched off (m_bZcrHeld), instead of being dropped (271e75c).",
      "ZCR: the main-effort binding (-zcrBindMainEffort) switches a held main effort back on, so the attack teams hold what they took (0249b42) - the 28 Oct rule had never fired.",
      "Three watched Farm battles (the game window, 1x, 20 min): two with the US at the harbour HQ, one with the Soviets there."],
     "Martin: 'if van test is done and fixed try that farm battle again', 'run it in window', 'continue testing it in window' (review notes 461-463).",
     "The van check, Soviets at the harbour HQ: Farm taken 11:36 v 19:29, boarding timeouts 0 v 68, Soviet losses 5 v 16. After the hold fix all 7 Soviet attack teams stayed on Farm (before: 7 US attack teams sent home)."),

    (54, "the van bug fixed, drone sites, plans for every base", "29 Oct 23:20 - 30 Oct 05:30",
     ["AI Conflict fork: the UAZ-452 counts its 2 front seats - its back is broken for the AI - so Soviet teams of 3+ ride the Ural (9dbd19f; -aicfVanSeats 8 = as before); plans per team from the origin nearest where it started, world sections, a 'none' plan, the hold line per plan (da5bb90).",
      "Watched matches: the seat fallback back on (Martin: 'probably back on').",
      "ZCR: drone trucks park beside roofs or tree crowns, operators walk in 100 m legs through cover (d4c7985); -zcrAttackScan all (07fa769); the boarding test takes static weapons and logs every seat (931dff4, cf1d484, 27e087a).",
      "Lab: the van sub-lab (lab/vantest.py), tripod runs in the crash sub-lab, attack plans for every Arland base (lab/attackplan.py --all, the side rule), the lab map's lines of attack (669fee5)."],
     "Martin: 'it can be just van bug that doesn't happen in other vehicles, can you verify?'; 'can you do integration sublab test for van bug?'; 'continue testing and resolving this bug' (review notes 452-459).",
     "The van's back seats: 2-14 of ~40 in, most of those stuck inside after the get-out; the M998 and the Ural 100% / 99.9%. Farm, Soviets at the harbour HQ: taken 4 of 5 with the fix, 0 of 3 before. The tripod crash lead did not reproduce."),

    (53, "transport rides, armour off the exit road, approaches from results", "29 Oct 22:00-22:40",
     ["Watched matches: trucks and vans only (-aicfArmedRideEvery 0 in .runtime/watch_extra.txt); the seat fallback was already off there (-aicfNoHiddenSeat).",
      "ZCR: armour bought at an HQ spawns round a point 400 m toward the front in every match, not only the one-point test (44dacc5; -zcrArmourAtHq for the old spot).",
      "lab/attackscore.py: every one-point run per side - its HQ, the approach it really had, rides, soldiers at the objective by minute 8/12, taken, three teams in; estimates shrunk toward the HQ's no-plan mean. attackplan.py --export measured / explore; attackpick.py shows Gemini the results and lets it answer none (ba7b8bc).",
      "Assault sub-lab: storm-plan-measured and the control storm-safe, both with the seat fallback off (694bb27)."],
     "Martin: 'bro continue fixing open shit you mentioned' (review note 451, on the morning page's next steps).",
     "With the measured results Gemini picks what the runs say: the harbour HQ from the south-west, the south HQ no plan (before: north and south, both no better than no plan)."),

    (52, "attacks planned from the map, rides that deliver", "29 Oct 01:10-06:00",
     ["-zcrAttackScan (ZCR): a 10 m grid round the objective - what 9 defender eye points see, roofs and canopy; lab/attackplan.py: three plans per HQ (assembly hidden from the objective, drive over the road graph, cover-to-cover lanes, hold line, support position, hiding spots, pull-offs); lab/attackdraw.py: lines of attack on Enfumap's map; lab/attackpick.py: Gemini picks with reasons (575b6f1).",
      "AI Conflict fork: the plan per HQ and the approach legs along its lanes (-zcrAttackPlan, 702eaed); the hold line inside the approach route (fa0f7c4); the one-point point attackable whatever the radio network reaches, no FIA patrols (1a910e8, 4d67770).",
      "ZCR: rides steered to the plan's assembly point and dropped there (3da376a); one-point armour 400 m toward the front, not on the HQ's exit road (e22d14f); the town test on Farm, the other bases dealt again (cecbc34).",
      "Assault sub-lab: arrivals together, plan drops, holds, each side's HQ distance in the summary; variants for the plan, the hold line, light and transport rides, the algorithm's pick, the control (3e4187a ... 4eef407)."],
     "Martin: 'attacks should be planned in some smarter way, we have to read the maps', 'where they have cover, where it could hide if something happens - drone?', 'I imagine having lines of attack', 'make it smarter ... continue iterating on this farm scenario' (review notes 447-450).",
     "34 Farm runs: the ride fixes are the big lever (harbour side at Farm by minute 8 from 3 to 11); a good approach adds on top (harbour south-west plans 6 of 7 captures vs 4 of 8); the pickers don't reliably find it."),

    (51, "rides out of the HQ two at a time, the 0-soldiers panel", "29 Oct 00:00-00:25",
     ["The panels' soldier count refreshed every 5 s, not only at a new camera shot (ZCR f8fe76a).",
      "AI Conflict fork: -aicfRidesPerBase N - at most N rides being planned, boarded or still driving out near a base; the next team walks (2322efa, off by default).",
      "The one-point sub-lab buys armour at the HQ, not at the side's base nearest the point (58de3b5); variant squads12-queue.",
      "The assault sub-lab counts rides per side: asked, delivered, failed, failed at the HQ, most at once (2bc2fa3)."],
     "Martin: 'it showed 0 soldiers btw for both sides'; 'transportation of the troops is fucked up' (review notes 443, 444).",
     "The panel bug found and fixed; nearly every ride failure is a jam inside the HQ - with 2 at a time 4 failures instead of 12 and 18 soldiers at the point by minute 8 instead of 7, still behind walking."),

    (50, "rides that don't turn back, the one-point sub-lab", "28 Oct 19:56-22:10",
     ["The bases dealt before AI Conflict's first orders (ZCR fb35f03).",
      "AI Conflict fork: no recruit trip when the side is at its cap or an attack team is over 150 m from the barracks; a ride only within 250 m of a base that can give one, the vehicle from within 300 m; boarding windows in game time, 75 s driver, 90 s passengers (8f89871, 6895736, 29462ff).",
      "-zcrBindMainEffort: attack teams stay on the main effort, avoided bases are off every list, a taken objective is held (402ea6e, 2c382a3).",
      "The one-point sub-lab: -zcrOnePoint (no FIA garrison, fork be6f991), the 'point' general for both sides, scenario 'point' with per-side numbers; variants squads12, squads12-seat, squads12-foot, stage50.",
      "Where a ride is given up as stuck is logged (fork d443a48); the live line prints as plain text; reports find sub-lab tests in the window (caedad8)."],
     "Martin, watching the assault test: 'they are walking 1500 meter the team a10', 'they got into car after 10 minutes', 'then immediately crashed into tree', 'they just walk around', 'returned to main base', 'lets do sublab where there will be only main base and one point', 'there was integration test for that, does that still pass?' (review notes 439-442).",
     "Teams no longer come back for nothing; on one point at 1.6 km walking beats AI Conflict's rides: 16/24 soldiers at the point by minute 8 against 8/4."),

    (49, "watched afternoon: pilots at their post, every base to a side, bunkers", "28 Oct 16:07-17:15",
     ["Drone pilots start a flight only within 15 m of their covered post (5d856ef).",
      "-zcrNoFIA splits the supply-depot bases between the sides too; the watch loop always passes the speed, 1x included (7b306c4); the SPEED button's double-tap guard on real time (6ca50d7).",
      "AI Conflict fork: fortifications 4 bunkers, 2 guard towers, 1 MG nest, 1 sandbag position of every 8.",
      "[ZCR][LIVE] team lines carry AI Conflict's posture and the current waypoint; [ZCR][EFFORTS] counts lone survivors apart; the Map's live layer: attack arrows, defence rings, the plan in words, 'this match only' (6c34b04, b629166).",
      "The assault sub-lab (lab/assault.py generals, lab/assaulttest.py, -zcrBindMainEffort), lab/sublab_batch.py; videos capped at the newest 5 (431c5d8)."],
     "Martin, watching: 'drone operator being out in the open', 'why is FIA owning bases', 'mostly bunkers', 'I see just soldiers chilling at bases', 'Commander Lab could show the main efforts' (review notes 424-438).",
     "The Soviet assaults never arrived: 2 of 12 attack teams really sent to the objective, 3 lone survivors going home, 5 sent elsewhere - the assault sub-lab measures the fixes."),

    (48, "long matches; rounds never fired swept; what the frames go to", "27 Oct 20:13 - 28 Oct 04:10",
     ["Watched loop: a match ends on the game's clock (23000b1); the loop stops before a match when the recordings' drive has under 3 GB free (7c6c40c).",
      "Census: projectiles by kind, place, height and speed; intact vehicles crewed or empty, physics awake or asleep, the empty ones by kind (2b913ed, 672748c, a3e7c8e).",
      "[ZCR][PROJWATCH]: the rounds turning up at the world origin - who fired them, their instigator and parent (68f8b6a, 4b4100e, e875423); -zcrProjSweep deletes the ones parked at 0,0,0 every 2 s, -zcrProjSweepAt once (d905530) - on in the watched setup from match 14."],
     "Martin, 27 Oct: 'continue testing the main game, I guess you can do a longer match than 25 min so we see what actually happens, let's give it 40m or something' (review note 422).",
     "26 of 28 matches ran 30+ game minutes, 23 the full 40; FPS 43 -> about 28 by minute 10-15 -> about 26 at minute 40; 3 early ends, none the LAV-25 crash; 1000-1900 rounds a match at the origin, never fired and cheap - now swept; vehicles in use (crewed 6 -> 30) follow the frames."),
    (47, "the crash fix", "27 Oct, 00:58-07:50",
     ["Crash sub-lab (the boarding test): get-in/out moved straight into the seat or climbed, seat and APC variants, a tilt sweep over a slope scan, fewest-mods variants, the release server build.",
      "ZCR_SafeBoarding: a soldier who has walked up to a LAV-25 goes straight into his seat (no climb); other vehicles the same when tilted over 8 degrees (-zcrSafeBoardDeg, 0 = off); on by default (899bb52). APC passengers out one by one and car teams in one by one built, off until Martin has seen them."],
     "The watched and headless matches crashed (review note 421).",
     "Climbing in crashed in every variant, moved straight into the seat never (0 of 8). Battles: 0 of 60 crashed with the fix, 6 of 60 without; the confirmation 0 of 40."),
    (46, "modern assault doctrine; the crash bisect", "26 Oct, 02:00-23:58",
     ["Modern assault doctrine (lab/modern.py, bridge 'modern'): drones first, quick covered dismounts 180-300 m from the objective, storms with drone support; its night runner (lab/modernnight.py).",
      "Drone sites follow the plan's drone target; a site whose pilot died is lost and the main one rebuilt; forward crews once the front is 700 m from every site.",
      "The crash hunt: crash probes (turret pushes on and off), the crash bisect (our code x the fork, before and after the night), ZCR_PhysWatch, lab/crashlab.py, the boarding sub-lab (ZCR_BoardTest), lab/crashreport.py."],
     "Martin: modern combat - hit and run, quick dismounts near positions, storms with heavy drone support (review notes 419, 420); the crashes (421).",
     "The modern doctrine played overnight (PLAN: modern night); the crash narrowed to boarding a LAV-25 (r47)."),
    (45, "FPS tests and the entity census", "25 Oct, 00:19-19:46",
     ["Entity census every 2 game minutes ([ZCR][CENSUS]): every dynamic entity by kind, the AI's level of detail, waypoints no group holds; lab/fpstest.py - solo matches per variant (speed, DCO, drones, driving mods, soldiers, teams and vehicles a side, resolution, recording).",
      "ZCR_AILod (-zcrAILod): AI detail by distance from the camera; our detour and road-first waypoints deleted once their group has passed them.",
      "Lab: the Decisions tab (every model strategist decision), the live supply map, the base-building sub-lab (ZCR_BuildTest); the model strategist's answers get 2000 tokens."],
     "Martin, 25 Oct: 'fps still drops for some reason as time goes by'.",
     "The FPS follows the soldier count; fewer teams and a side cap measured in full matches (PLAN)."),
    (44, "drone teams on sorties; the commander plans the drone truck", "24 Oct, 16:05-18:40",
     ["Drone teams on sorties (ZCR_DroneOperator): the pilot carries 4 FPVs (a big bag - the assembled ALICE / Kolobok); the team walks to a launch position with overhead cover 60-200 m from its truck, launches one at a time from the nearest open sky, walks back when empty and loads 45 s, then out to a new position ([ZCR][SORTIE]). Goggles on only while he flies (helmet back at landing), the controller in hand, his AI off for the flight.",
      "The commander plans the drone truck (ZCR_DroneSites): a forward site's truck stands at a support point 1000 m back from where its side's drones go (clear dry ground; nearer after a point is given up), driven there by its own driver; the main base's site is static. The operators no longer ride the truck (boarding went in and out).",
      "Main battle: a launch needs an operator team at its launch position with drones in the bag - one FPV at a time (the FPV mod's SetDrones).",
      "Lab: storm farm-site (a US drone site against the farm); lab/report.py finds sub-lab storms and their videos; the scorecard's 'operators' check (goggles and still at 80% of flights)."],
     "Martin, 24 Oct: 'what is a drone site, is it static?'; 'real drone teams move ... yeah I love this'; 'operators should have larger bags with drones and resupply at the drone truck or a static arsenal'; 'Zeus Commander should plan where to move the drone truck'; 'give him a big backpack, goggles only when he is driving drones'; 'that operator is acting a bit weird'.",
     "Farm-site storms in the window: sorties every 3-5 minutes (walk back 38-64 s, load 45 s); the 18:31 storm - 10 flights, goggles 100%, still 80%; the truck drive itself not yet seen (its support point was always within 250 m of where it stood)."),
    (43, "DCO as the tactical layer; 50-a-side cap; drone storms and the drone operator", "24 Oct, 00:00-15:52",
     ["DCO_AI (Workshop) is the tactical layer in our matches; the bridge addon ZCR_DCO (loaded only with DCO) turns our orders into DCO's per-group switches: Light detail for squads with no known enemy within 800 m, every feature off for drone operator teams; the storm push stays behind -zcrStormPush (it failed in the sub-lab).",
      "Soldier cap in our AI Conflict fork: -aicfMaxAgentsPerFaction 50 with -aicfCapCountsAll (builders, truck crews, operators and soldiers DCO moved count too), -aicfMaxBuildersPerFaction 6; the attack minimum follows the muster size.",
      "Infantry sub-lab with drones: farm and village storms with drones for the attacker, the defender or both; a 2-man operator team launches one FPV every 35 s (the FPV mod got SetDrones); a storm ends when one side is wiped out; recorded in the game window (lab/drone_storms.sh).",
      "The drone operator (ZCR_DroneOperator): pilot with FPV goggles and the drone controller, his AI off while his FPV flies, a guard, a post in cover; watch-screen tags and a close camera shot. Test operators and the commander's drone sites.",
      "Drone reactions: a building within 15 m - run in at danger priority, the spot itself inside, kept inside while a drone is near; our fire at drones holds while a friend is near the drone or its line of fire; the loss log marks kills credited to a dead soldier (killer_dead=1).",
      "FPV mod: the Soviet drone stations no longer bring the game's 6-man Soviet squad with them (fpv-ai-reforger 41084aa)."],
     "Martin, 24 Oct: 'ok so let's then go with DCO'; '50 vs 50'; 'infantry attack + drones, just to see DCO infantry react to drones; drones in groups of 4 is a bit unrealistic'; 'the drone operator should be seen in the GUI with a tag ... controller in hands and goggles, stationary'; 'the drone operator should really just hold still when he is driving the drone'.",
     "Watched drone storms (DCO): single drones kill about 70% of the time; runs into buildings 0 of 17 at first, then 5 of 8 on the farm (the village still 0-2); own-side kills turned out to be mostly a log quirk (~1 real a storm, none without our fire). The operator: on screen with his kit, still within 2-3 m through each flight (Martin: 'this is fucking great!!!')."),
    (42, "supply runs; crossing rule; test camera", "23 Oct, 17:00-19:00",
     ["Supply runs in the traffic simulation's shuttle mode (-zcrTrafficShuttle): supply trucks start empty at the destination, load the game's supply container at the supply point (1500 for a Ural) and empty it at the destination; manpower trucks drive up to a squad waiting off the road by the pickup, it boards (6 of 6 in 15-45 s), rides and gets out at the destination, and the next squad turns up once the truck has gone. One truck at a stop at a time (the next waits 120 m short). First runs: trucks stuck after boarding - the next squad had been placed on the road where the truck stopped, the second truck appeared 2 m from the first; both fixed.",
      "Crossing rule (ZCR_Crossing): two AI-driven vehicles heading more than 30 degrees apart whose straight lines cross ahead of both within 50 m, reaching that point within 3 s of each other - the later one stops until the other is 6 m past it (8 s at most), and that vehicle isn't stopped again for 10 s. Cars following each other round a bend are left to the spacing rule. -zcrNoCrossing turns it off.",
      "Test camera: PREV / NEXT step through a test's own vehicles and groups (they stepped through the commander's teams, which a test hasn't got). The drive test seats its driver 1.5 s after the car appears, like the other tests (the watched game left a seat filled in the spawn frame empty).",
      "Soldiers delivered by the traffic simulation are taken off the map only once they are out of the truck (deleting a seated soldier is an engine risk; the watched supply run crashed at 17:25 - cause not proven).",
      "Drive tracks supply and manpower, the nocrossing setup in the driving sub-lab, integration tests supply-run and manpower-run, measures men_delivered, supplies_delivered, crossings."],
     "Martin, 23 Oct: '1. the truck comes to the supply point to pick up supplies -> to the point that should be supplied and unloads them; 2. the same with manpower'; 'these trucks crashed into each other where they met at a crossroad'; 'next/prev vehicle doesn't work in these integration tests'.",
     "Headless, 10 minutes on Arland: 2 supply trucks delivered 3000 supplies, 4 trucks 6000, none lost; manpower 6-12 soldiers (turning round at the pickup costs 1-2 minutes). Crossing rule: 7 give-ways and 1 light touch in a 4-truck run; the comparison without it is next."),
    (41, "armour: crews stay aboard, spot far, the storm; integration tests", "23 Oct, 11:55-16:56",
     ["Guns test (-zcrGunTest, lab/guntest.py): crewed armour of both sides on Arland's airfield - a line-of-sight scan found only 9 clear 800-m lines on the map - or armour against a squad; events for first sight, first detection, first target, first shot. The AI notices enemy vehicles at ~490 m though it can see 750-800 m; with the crews' perception 3x (-zcrCrewPerception 3): noticed at ~610 m, first shots ~525 m.",
      "Crews stay aboard (ZCR_CrewStays): when the game gives up a vehicle's move it takes the whole group out to walk; the crews of armed vehicles (a turret, at least 35% intact) now stay in the driver's and gunner's seats. -zcrCrewsLeave for the old way.",
      "The storm scenario: an Abrams in overwatch and a LAV-25 carrying a US squad against a Soviet squad defending its point with a BTR-70; the riders get out 250 m short and storm (Search and Destroy), the LAV follows them in 20 s later.",
      "Integration tests (lab/itests.toml, lab/itest.py): small headless scenarios with checks that must pass and goals to work towards, three at a time on a pool of ports. Every run writes run.json (arguments, command, commit, uncommitted changes); lab/rerun.py replays a run on its commit in a worktree.",
      "Tanks and APCs on the driving tracks (BTR-70, LAV-25, and the Workshop T-72, BMP-1, M1A1, Bradley)."],
     "Martin, 23 Oct: 'test it on APCs too, with guns used, against each other or against infantry'; 'crew went out and didn't use the vehicles - stop this test and fix it'; 'tank + APC + infantry against infantry in a defence position; the APC carries soldiers close, they disembark and storm'; 'all these tests should be reproducible ... integration tests'.",
     "Watched: the APC duel, armour against infantry, tank against tank and the storm all played as intended (Martin: 'this is fucking great, it worked'). Integration tests: 9 of 10 on the first full run - it caught a regression (spot-far, fixed within the hour); tank head-on makes too few trips headless (watched it looked fine)."),
    (40, "our vehicle rules: head-on slow-down and spacing; the driving night", "22 Oct 22:00 - 23 Oct 10:30",
     ["ZCR Traffic v1: a speed arbiter - every rule that wants a vehicle slower asks, the lowest request is applied (no two rules fighting over the cruise speed) - with the spacing rule (no rear-ending: stop under 9 m, crawl under 16 m, match the speed under 28 m) and the head-on slow-down (two cars each with the other ahead within 90 m on its line: both 15 km/h until past).",
      "Test tracks on the game's empty Game Master maps (lab/drivetest.py): the Moss Hill head-on lane, convoys, a wreck blocking the road (the lead car hit), trucks both ways, fenced fields, the Everon base exit; the traffic simulation (vans, troop trucks and supply trucks between four stops). The driving sub-lab compares setups on every track.",
      "A collision forecast (v2: 24 futures over 4 s from how each car really moves, the fastest speed under 10% risk) - built, measured, shelved: no fewer crashes than v1, slower.",
      "Found on the tracks: the Moss Hill test losses were the world's road mines (test tracks now clear them like matches); the Everon base exit is blocked by closed gates the AI doesn't open (gates stay - Martin's decision)."],
     "Martin, 22 Oct night: 'they still crash into each other'; 'it's one last chance - if it doesn't help I'll probably drop vehicles'.",
     "79 night runs: head-on crashes on the lane 5 -> 0 a run, Ural trucks both ways 6.5 -> 1.5; no Workshop driving mod added anything. Watched block (16 matches): Arland jams 8 -> 4.8, long stops 4.8 -> 1.4 a match, ~4 car-on-car hits a match remain; 1 engine crash."),
    (38, "no crashes; trucks out of their depots; rides round unreachable spots; armour unstuck", "22 Oct, 08:00-10:40",
     ["Crashes: two of the night's changes together crashed the watched game - moving stuck vehicles by hand and the 'following' rule that slowed a vehicle behind a slow one (it changed the game's cruise speed). Without the moves 4 of 4 matches clean, without following 6 of 6 (100 moves). Following is off; since then one freeze and no crash in 23 matches.",
      "Supply trucks: a truck that drove past its 3-m waypoint (its depot's exit, 12 m ahead) had to turn back to it - the game's drivers can't reach a point behind them, so the move failed and the driver got out (22 driver exits in one match). Truck waypoints are 8 m and the exit counts once passed: 0 failed truck moves and 6 exits in the next Arland match.",
      "Rides: the same few road points failed match after match - on Everon a farm road inside a fenced yard behind a gate, 'reachable' for the road network, not for the drivers; the team then walked 2-6 km. A point a vehicle couldn't reach is remembered for the match and later rides take one on the approach side.",
      "Armour and armed rides: kept from being moved by hand since 05:10. Moving them again halved the long stops and jams (2.8 and 2.0 a match against 5.9 and 5.3) but 2 of 8 matches failed (a freeze, then a crash 7 s after a BTR-70 back-off) - kept out again; crashes come first."],
     "Martin, 22 Oct 00:30: 'solve those cars and the other issues'.",
     "w26-w50: one freeze (w42) and one crash (w50), both with armour moved by hand; 0 of 13 with it kept out."),
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
