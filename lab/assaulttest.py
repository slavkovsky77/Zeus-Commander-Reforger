"""The assault sub-lab (28 Oct, Martin: "why teams were not set off, can we analyse ... maybe some sublabs for the tests?";
review note 433). A full Arland match with the watched matches' setup, but one side attacks one base with everything from the
first minute (lab/assault.py's 'assault' general) and the other holds it ('hold') - do the ordered attack teams get there?
The runner of the sub-lab "assault" (lab/sublabs/assault.toml):

    python lab/assaulttest.py ussr --variant now --minutes 10
    python lab/sublab.py run assault --scenario ussr --variant team4 --repeat 2

Measures (the attacker): soldiers within 300 m of the objective at game minute 3, 5 and 8 and as a share of its attack
teams' soldiers then; the first arrival; where its attack orders really sent the teams (AI Conflict's own order lines - our
live line shows only each team's assigned target, which misled us on 28 Oct); lone survivors sent home; failed rides;
the capture; losses on both sides.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import droneloss  # noqa: E402

# The watched matches' setup on 28 Oct (.runtime/watch_extra.txt, watch_mods.txt; armour mods off), frozen so a later
# change to the watched setup doesn't move the sub-lab's baseline.
BASE = ("-zcrNoFIA -zcrArmourVanilla -zcrMoveTurrets -aicfNoHiddenSeat -zcrNoCoverLayer -zcrDangerDronesOnly "
        "-aicfMaxAgentsPerFaction 50 -aicfCapCountsAll -aicfInfantryDeploySize 2 -aicfMusterSize 2 "
        "-aicfMaxBuildersPerFaction 6 -aicfVehicleMinimumRequestAgents 2 -zcrProjSweep")
MODS = "3B9F2C4D5E6A7B81,68FCF11534562F2E,5EDAAE0D3CC60D6B"
SCENARIOS = {
    # name: the attacking side - the other holds. Arland's HQs swap between matches; both generals pick the enemy base
    # nearest the attacker's HQ (on 28 Oct: Military Training Area when the USSR attacks, Farm when the US does).
    "ussr": "USSR",   # the Soviets attack (28 Oct: nobody reached Military Training Area in two 5-minute assaults)
    "us": "US",       # the US attacks
    "point": "BOTH",  # one neutral point (Signal Hill), both sides go for it; nothing else on any list (-zcrOnePoint)
    "city": "BOTH",   # one base, Farm (29 Oct, Martin: "make it in a way there can be fight somewhere, so maybe farm")
    # 4 Nov (Martin, after the Farm battles: "keep farm scenario but lets just do different city, farm can be soviet now I
    # guess", "make it connected in a way in this scenario there is battle of the city"): the battle for Beauregard, the town
    # 1.1 km east of Farm by the sea, Farm a Soviet base now (-zcrBaseTo in the variant).
    "beauregard": "BOTH",
}

# The one-point scenarios' point: Signal Hill 1628 m from one HQ, 1688 m from the other; Farm 1115 m from the
# north-western (harbour) HQ and 2090 m from the southern one - the harbour side holds it first, the other storms it.
# Both sides may attack the point whatever their radio network reaches (fork 1a910e8, ZCR_OnePoint). Tried once each
# on 29 Oct: Arleville (every base dealt, out of one side's radio reach) and Beauregard (every base left neutral).
POINTS = {"point": "Signal_Hill", "city": "Farm", "beauregard": "Beauregard"}
# The live planner's 10 m ground scan of each point other than Farm (-zcrAttackScan all, 29 Oct).
SCANS = {"beauregard": ROOT / ".runtime" / "attack" / "arland" / "scan_3297_2860.jsonl"}
POINT = POINTS["point"]

SCENARIO_WORDS = {
    "ussr": "The Soviets attack the US base nearest their HQ with everything from the first minute; the US holds it",
    "us": "The US attacks the Soviet base nearest its HQ with everything from the first minute; the Soviets hold it",
    "point": "One neutral point in the middle (Signal Hill, 1.6-1.7 km from both HQs) and the two main bases - both sides go for the point with everything; no other base is on any list",
    "city": "One base, Farm (1.1 km from the harbour HQ, 2.1 km from the southern one) - the other bases dealt to the sides but off every list; both sides storm Farm",
    "beauregard": "The battle for the city: Beauregard (the town by the sea 1.1 km east of Farm, 2.2 km from the harbour HQ, 2.6 km from the southern one) - Farm a Soviet base after its battle, the other bases dealt but off every list; both sides storm Beauregard",
}


def _sized(n: int) -> str:
    return BASE.replace("-aicfInfantryDeploySize 2 -aicfMusterSize 2", f"-aicfInfantryDeploySize {n} -aicfMusterSize {n}")


VARIANTS = {
    # name: (extra command line, words for the app)
    "now": (BASE, "as the watched matches: 2-man teams, rides, AI Conflict picks each team's target"),
    "team3": (_sized(3), "teams set out with 3 men (AI Conflict's default), not 2"),
    "team4": (_sized(4), "teams set out with 4 men"),
    "bind": (BASE + " -zcrBindMainEffort", "attack teams go only for the main effort, avoided bases are avoided (-zcrBindMainEffort)"),
    "foot": (BASE + " -aicfInfantryRideMeters 100000", "no rides: every team walks"),
    "team4-bind": (_sized(4) + " -zcrBindMainEffort", "4-man teams that go only for the main effort"),
    "squads12": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort",
                 "12 teams of 4 a side instead of 20 of 2 (the same ~48 soldiers, half the vehicles), binds"),
    "squads12-seat": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort").replace(" -aicfNoHiddenSeat", ""),
                      "12 teams of 4, binds, and AI Conflict seats a passenger whose get-in never starts (its fallback, off since 22 Oct)"),
    "squads12-foot": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfInfantryRideMeters 100000",
                      "12 teams of 4, binds, no rides: every team walks (the reference for what the rides are worth)"),
    "stage50": (BASE + " -zcrBindMainEffort -aicfVehicleSpawnStagingRadiusMeters 50",
                "binds, and a team counts as at its vehicle spot within 50 m, not 25 (spots at the harbour's waterline)"),
    "squads12-queue": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 2").replace(" -aicfNoHiddenSeat", ""),
                       "12 teams of 4, binds, seat fallback on, and at most 2 rides leaving a base at a time - the next team walks"),
    "storm-mounted": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3").replace(" -aicfNoHiddenSeat", ""),
                      "the storm rides in (Martin, 29 Oct: 'storms should be done by vehicles'): 12 teams of 4, binds, seat fallback "
                      "on, rides for every march over 300 m, at most 3 leaving a base at a time (the jam inside the HQ, note 444)"),
    # 29 Oct night (Martin, note 449: "attacks should be planned in some smarter way, we have to read the maps"): the attack
    # plan read from the map (lab/attackplan.py -> .runtime/attack/seed_<point>_<pick>/zcr/attackplan.txt, see SEEDS).
    "storm-plan": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold").replace(" -aicfNoHiddenSeat", ""),
                   "as storm-mounted, and the attack plan read from the map that the model picked: the rides to its assembly point "
                   "hidden from the objective, the teams in along its cover-to-cover lanes"),
    "storm-plan-hold": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan").replace(" -aicfNoHiddenSeat", ""),
                        "as storm-plan, and the hold line: teams wait ~150 m out until 3 are there (or 90 s), then all go in together"),
    "storm-plan-light": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold -aicfApcEvery 0").replace(" -aicfNoHiddenSeat", ""),
                         "as storm-plan, rides in light vehicles only (no APC rides: the BTR-70s jammed the harbour HQ, 29 Oct night)"),
    "storm-plan-light-hold": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfApcEvery 0").replace(" -aicfNoHiddenSeat", ""),
                              "the plan, light rides and the hold line together"),
    "storm-plan-light-hold-noarm": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfApcEvery 0 -zcrNoArmour").replace(" -aicfNoHiddenSeat", ""),
                                    "the plan, light rides, the hold line - and no armour units (29 Oct night: bought at the HQ they stood on its exit road while the rides left)"),
    "storm-plan-light-hold-algo": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfApcEvery 0").replace(" -aicfNoHiddenSeat", ""),
                                   "as storm-plan-light-hold, with the plan the algorithm scored best instead of the model's pick"),
    "storm-plan-trans-hold": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                              "the plan and the hold line, transport rides only (29 Oct night: armed and armoured rides delivered 1 of 39, trucks and vans 31 of 52)"),
    "storm-trans": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                    "the control for the plan runs: today's way with transport rides only and the armour off the HQ exit - no plan"),
    "storm-plan-trans-hold-algo": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                                   "as storm-plan-trans-hold, with the plan the algorithm scored best instead of the model's pick"),
    "storm-plan-trans": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                         "the plan without the hold line, transport rides only - the lanes and the assembly point alone"),
    "storm-plan-close": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                         "the plan with its assembly point 200-400 m out (300-650 before; the covered dismount drops 180-300 m out) and no hold line, transport rides"),
    "storm-plan-algo": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -zcrAttackPlan -zcrNoAttackHold").replace(" -aicfNoHiddenSeat", ""),
                        "as storm-plan, with the plan the algorithm itself scored best"),
    # 29 Oct evening (Martin's go, note 451): the seat fallback stays off, as in the watched matches - both of the night's
    # crashes came after forced seats.
    "storm-safe": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -aicfArmedRideEvery 0",
                   "no plan, transport rides, the seat fallback off (the watched matches' setting) - the control"),
    # The normal matches' setup (2-man teams, every base dealt) with the plans for every base (lab/attackplan.py --all):
    "now-trans": (BASE + " -aicfArmedRideEvery 0", "as the watched matches since 29 Oct evening: transport rides only - the control"),
    "now-plan": (BASE + " -aicfArmedRideEvery 0 -zcrAttackPlan -zcrNoAttackHold",
                 "as now-trans, with attack plans from the map for every base from every base (the origin nearest where a team started)"),
    # 30 Oct 03:15 the van fix (fork: the UAZ-452 counts its 2 front seats - its back is broken for the AI, the van sub-lab):
    "storm-safe-van8": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 3 -aicfArmedRideEvery 0 -aicfVanSeats 8",
                        "storm-safe with the old van (8 seats: Soviet teams of 4 ride the UAZ-452 and its broken back) - the van fix's control"),
    # 1 Nov (Martin: "fuck cap", note 481): no cap on rides out of a base - they start 8 s apart (the fork's default).
    # 1 Nov 22:30 (note 484): the fork has no spacing by default any more (it lost 4 v 5 battles), looks again for a vehicle
    # spot after 10 s, and allows 12 vehicles a side - this variant follows the fork's defaults.
    "storm-plan-measured": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0",
                            "per HQ the approach that did best in the measured runs, or no plan where none beat it (lab/attackscore.py); transport rides with neither cap nor spacing (the fork's defaults), 12 vehicles a side; the seat fallback off"),
    # 31 Oct night (the transport test, note 480): the 3-rides-per-base cap cost the most there - no cap moved +8% (north HQ)
    # to +50% (south HQ) more soldiers, no jam at the HQ. Does the Farm battle jam at the HQ without it (the 29 Oct reason)?
    "storm-plan-measured-cap0": (_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -aicfRidesPerBase 0 -aicfRideSpacingMs 0 -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0",
                                 "as storm-plan-measured, with neither the cap nor the spacing on rides leaving a base"),
    # 2 Nov 18:10 (Martin: "transport is for now good", "lets run one farm battle"): the Farm battle with the transport
    # test's setup - the seat fallback on (his call of 30 Oct, note 456, never applied here), and the fork's and ZCR's
    # 2 Nov defaults (boarding hold, departure queue, 20-s retry at a base, order restore, ride detour).
    "farm-now": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0").replace(" -aicfNoHiddenSeat", ""),
                 "storm-plan-measured with the transport test's setup: the seat fallback on, and every 2 Nov transport fix (the defaults)"),
    # 3 Nov (note 519): the A/B of the contact dismount (fork: a ride within 800 m of its target whose crew got out ends as a
    # dismount there) - farm-now without it, as before 3 Nov.
    "farm-now-nocontact": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -aicfContactDismountM 0").replace(" -aicfNoHiddenSeat", ""),
                           "farm-now without the contact dismount (a crew that got out is put back in, as before 3 Nov)"),
    # 3 Nov (note 520, Martin: "could we override dco 400m dismount?"): riders stay aboard to the drop point - DCO's per-squad
    # vehicle exit rule 'ordered or damaged' while a man of the squad is aboard (ZCR_DCO, -zcrRideStayMounted).
    "farm-now-staymounted": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -zcrRideStayMounted").replace(" -aicfNoHiddenSeat", ""),
                             "farm-now, and a riding squad leaves its vehicle only at its drop point, when ordered or when the vehicle is badly damaged (DCO's exit rule)"),
    # 2 Nov night (note 515 - Martin: "why gemini is not used for planning attacks?", "attack routes should be planned based
    # on the context (positions of soldiers, cover)", "points where soldiers are dropped should be planned by LLM", "only one
    # side can use it, the other one will not, and we will compare"): farm-now, and ONE side's attack teams get live plans
    # from lab/liveplan.py running beside the battle (--live-side: harbour = the side whose HQ is nearer Farm, south, US or
    # USSR) - drop points, cover routes past the enemies that side knows, go/wait/support; the other side plays farm-now.
    "farm-live": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -zcrLivePlan").replace(" -aicfNoHiddenSeat", ""),
                  "farm-now; one side's live plans picked by the code (the cheapest drop points and routes, go)"),
    "farm-gemini-routes": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -zcrLivePlan").replace(" -aicfNoHiddenSeat", ""),
                           "farm-now; one side's live plans picked by Gemini every ~2.5 game minutes from the map image (drop points, routes, go/wait/support); drones by the rule"),
    # 2 Nov 22:40 (Martin: "maybe even the LLM commander should decide when to use drones"; the drone plan's hook, ZCR 59c8451):
    # farm-gemini's Gemini also decides its side's drone operator teams (1-6) and their target. Its first three battles
    # (21:26-22:55) ran without - lab/livecompare.py tells them apart by liveplan.jsonl's "drones".
    "farm-gemini": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -zcrLivePlan").replace(" -aicfNoHiddenSeat", ""),
                    "farm-gemini-routes, and Gemini also decides the side's drone teams (1-6) and where they fly (farm / enemy_hq / none)"),
    # 3 Nov (notes 517-520): Martin reviews by watching - one battle with everything of his 2 Nov wishes that is built: farm-gemini
    # (Gemini commands one side: drop points, cover routes, wait/go, its drone teams), the dynamic drone teams, the contact
    # dismount (the fork's default), the new drone attack run (the local FPV AI Drones), and the fortifications Gemini planned
    # (-zcrFortPlan, $profile:zcr/fortplan.txt from lab/fortplan.py; elsewhere today's search facing the enemy first).
    "farm-gemini-forts": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -zcrLivePlan -zcrFortPlan -zcrFortFace").replace(" -aicfNoHiddenSeat", ""),
                          "farm-gemini, and both sides build the fortifications Gemini planned from the map (place and facing), the rest facing the enemy"),
    # 3 Nov 14:40: and riders stay in the car to their drop point (note 520: 4 headless battles - soldiers at Farm at minute 12
    # 18 v 9 with the contact dismount alone, Farm taken by 3 sides v 0 in 7 battles; more cars burn with the team aboard).
    "farm-review": ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -zcrLivePlan -zcrFortPlan -zcrFortFace -zcrRideStayMounted").replace(" -aicfNoHiddenSeat", ""),
                    "farm-gemini-forts, and a riding squad stays in its car to the drop point (DCO's exit rule 'ordered or damaged')"),
    # 3 Nov 18:15 (note 530 - Martin: "continue developing so farm is actually captured and both sides actually attack and
    # defend the point"): in the streamed battle drones did 71 of 81 losses and the attack teams stood 120-300 m out with their
    # waypoint on Farm's centre - nobody in its 60 m core but once. The same battle without any drones, to see what they do.
    "farm-now-staymounted-nodrones": (None, "farm-now-staymounted without drones: no drone mods, no drone teams (the A/B of note 530)"),
}
NO_DRONES = {"farm-now-staymounted-nodrones"}
# 3 Nov 18:35 (note 530): AI Conflict parked 2.6 attack teams a battle for good within 400 m of Farm (FIELD_HOLD after three
# "no progress" checks while they fought their way in); the fork now never parks an attack team within 450 m of its target.
# The old rule, for the A/B:
VARIANTS["farm-now-staymounted-hold"] = (VARIANTS["farm-now-staymounted"][0] + " -aicfZcrNoHoldNearM 0",
                                         "farm-now-staymounted with AI Conflict's old field hold in front of the objective (the A/B of note 530)")
VARIANTS["farm-now-staymounted-nodrones"] = (VARIANTS["farm-now-staymounted"][0], VARIANTS["farm-now-staymounted-nodrones"][1])
# 3 Nov 22:20 (note 530): the side that lost Farm never came back - its attack teams whittled, never refilled, 20 of its 50 in
# home-defence teams nobody attacks. The fork's second wave: home-defence teams join the attack when it is down to half.
VARIANTS["farm-now-staymounted-wave"] = (VARIANTS["farm-now-staymounted"][0] + " -aicfZcrSecondWave 1",
                                         "farm-now-staymounted with the second wave: home-defence teams (all but one) join the attack when the attack teams are down to half their men and home is safe")
# 3 Nov night (note 534 - Martin: "two sides battle over the farm but general actually uses brain, not hardcoded shit"):
# Gemini commands BOTH sides (lab/liveplan.py --side both: drop points, routes, go/wait/support, drone teams), no stored
# plan file, the second wave on, riders stay mounted to the drop point.
VARIANTS["farm-brains"] = ((_sized(4) + " -aicfSquadsPerSide 12 -zcrBindMainEffort -zcrAttackPlan -zcrNoAttackHold -aicfArmedRideEvery 0 -zcrLivePlan -zcrRideStayMounted -aicfZcrSecondWave 1").replace(" -aicfNoHiddenSeat", ""),
                           "Gemini commands both sides live (drop points, routes through cover, go/wait/support, drone teams) - no stored plans; second wave on")
# -fpvaiKeepStations (4 Nov night): both crashes of the watched town battles came 1-4 s after the FPV mod deleted a used-up
# drone station - the empty stations stay, to see whether the crashes go.
# -zcrStormRelentless (5 Nov, Martin: "they should definitely move"): DCO's aggressive posture for attack squads near the point.
VARIANTS["town-brains"] = (VARIANTS["farm-brains"][0] + " -zcrBaseTo Farm:USSR -fpvaiKeepStations -zcrStormRelentless",
                           "farm-brains for the battle of a city: Gemini commands both sides, no stored plans, the second wave - Farm a Soviet base")
VARIANTS["town-vs-rules"] = (VARIANTS["town-brains"][0],
                             "the battle of the city, Gemini commands one side (--live-side: harbour or south), the code's rules the other - same routes, drops, danger zones")
# 4 Nov evening: field fortifications tested where they happen - the US holds Beauregard from the start, so its general
# orders field positions in its first rounds (note 538; in the night's battles the town fell too late to see any built).
VARIANTS["town-forts"] = (VARIANTS["town-brains"][0].replace("-zcrBaseTo Farm:USSR", "-zcrBaseTo Farm:USSR,Beauregard:US"),
                          "town-brains with Beauregard American from the start - its general's field fortifications from the first rounds")
# 5 Nov night (Martin: "it takes some time that ai basically fails to attack storm and get units to front", "like it degrades
# with time?"): the town fell at 9-16 min in 5 of the 6 battles before the door fix (780f2a9, 4 Nov 04:51), rarely since -
# town-brains without the AI's navlink-door reaction, as the A/B arm (its own name, so lab/towntest.py's town-brains curve
# doesn't take these battles in; lab/towntime.py compares the two).
VARIANTS["town-nodoor"] = (VARIANTS["town-brains"][0] + " -zcrNoDoorReaction",
                           "town-brains without the AI's navlink-door reaction (as before 4 Nov 04:51) - the A/B of the town captures")
# 5 Nov night (the subagent's study of 27 town battles, lab/towntime.py): teams reach 300 m of the point but hover 150-300 m out
# (a soldier's formation move at storm priority 25 loses to taking fire positions and attacking) - town-storm60; and the attack
# fades with time because supply-truck crews and drone pilots fill the side cap (squad men 96 -> 60, support 34 -> 58 by minute
# 25; REINFORCEMENT_BLOCKED reason=FACTION_LIMIT) - town-cap70. Both: town-storm60-cap70.
VARIANTS["town-storm60"] = (VARIANTS["town-brains"][0] + " -zcrStormPriority 60",
                            "town-brains with the storm's legs at priority 60 (25): the men keep moving under fire rather than stopping at fire positions")
_cap70 = VARIANTS["town-brains"][0].replace("-aicfMaxAgentsPerFaction 50", "-aicfMaxAgentsPerFaction 70")
assert _cap70 != VARIANTS["town-brains"][0]
VARIANTS["town-cap70"] = (_cap70, "town-brains with the side cap at 70 soldiers (50) - room for the attack teams beside the support soldiers")
VARIANTS["town-storm60-cap70"] = (_cap70 + " -zcrStormPriority 60", "town-storm60 and town-cap70 together")
LIVE_BOTH = {"farm-brains", "town-brains", "town-vs-rules", "town-forts", "town-nodoor", "town-storm60", "town-cap70", "town-storm60-cap70"}   # variants whose live planner plans both sides
RULES_VS = {"town-vs-rules"}   # ... one of them by the rules: the side opposite --live-side
# 4 Nov ~02:00 (note 536 - Martin: "I would expect at farm ai to hide and clear house as priority as it is withing capture
# ratio right? and it provides defense?"): DCO's defend and idle positions indoors first (coverPreference 1; Recommended:
# 0 = balanced) and several teams may share a building (Farm has few).
DCO_CFG = {"farm-brains": {"coverPreference": 1, "shareBuildings": True}, "town-brains": {"coverPreference": 1, "shareBuildings": True},
           "town-vs-rules": {"coverPreference": 1, "shareBuildings": True}, "town-forts": {"coverPreference": 1, "shareBuildings": True},
           "town-nodoor": {"coverPreference": 1, "shareBuildings": True}, "town-storm60": {"coverPreference": 1, "shareBuildings": True},
           "town-cap70": {"coverPreference": 1, "shareBuildings": True}, "town-storm60-cap70": {"coverPreference": 1, "shareBuildings": True}}
LIVE = {"farm-live": ("code", False), "farm-gemini-routes": ("gemini", False), "farm-gemini": ("gemini", True), "farm-gemini-forts": ("gemini", True), "farm-review": ("gemini", True), "farm-brains": ("gemini", True), "town-brains": ("gemini", True), "town-vs-rules": ("gemini", True), "town-forts": ("gemini", True), "town-nodoor": ("gemini", True), "town-storm60": ("gemini", True), "town-cap70": ("gemini", True), "town-storm60-cap70": ("gemini", True)}   # variant -> lab/liveplan.py's picker, drones
SEEDS = {"storm-plan": "model", "storm-plan-hold": "model", "storm-plan-light": "model", "storm-plan-light-hold": "model", "storm-plan-light-hold-noarm": "model", "storm-plan-light-hold-algo": "algorithm", "storm-plan-trans-hold": "model", "storm-plan-trans": "model", "storm-plan-close": "close_model", "storm-plan-trans-hold-algo": "algorithm", "storm-plan-algo": "algorithm", "storm-plan-measured": "measured", "storm-plan-measured-cap0": "measured", "farm-now": "measured", "farm-now-nocontact": "measured", "farm-now-staymounted": "measured", "farm-now-staymounted-nodrones": "measured", "farm-now-staymounted-hold": "measured", "farm-now-staymounted-wave": "measured", "farm-live": "measured", "farm-gemini": "measured", "farm-gemini-forts": "measured_forts", "farm-review": "measured_forts", "farm-gemini-routes": "measured", "now-plan": "@arland_all"}   # variant -> which plan pick (lab/attackplan.py --export)
RIDE_FAIL = ("BOARDING_PHASE_DEADLINE_EXCEEDED", "BOARDING_PROGRESS_GRACE_DEADLINE_EXCEEDED", "DRIVER_RECOVERY_EXHAUSTED",
             "VEHICLE_STUCK_PERSISTENT", "MOB_EGRESS_SOFT_NUDGE", "MOB_EGRESS_HIDDEN_RECOVERY", "VEHICLE_FALLBACK_LONE_SURVIVOR")
NEAR_M = 300


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False, speed: float = 1,
        cam_spot: str = "", play: bool = False, live_side: str = "harbour", more: str = "") -> dict:
    attacker = SCENARIOS[scenario]
    extra, _ = VARIANTS[variant]
    if more:   # --extra: lab probes for one run (e.g. -zcrGetOutProbe), the variant unchanged
        extra += " " + more
    if cam_spot:
        extra += f" -zcrCamSpot {cam_spot}"
    us, ussr = ("assault", "hold") if attacker == "US" else ("hold", "assault")
    if attacker == "BOTH":
        us = ussr = "point"
        extra += f" -zcrOnePoint {POINTS[scenario]}"
    sys.path.insert(0, str(ROOT / "lab"))
    import bridges
    import sublab
    bridges.ensure(("point",) if attacker == "BOTH" else ("assault", "hold"))
    title = sublab.title("assault", scenario, variant)
    label = f"assault-{scenario}-{variant}-p{port}" if not watch else f"assaulttest-{scenario}-{variant}-watch"   # lab/watch_test.py finds the game by it
    if play:
        label = f"assaulttest-{scenario}-{variant}-play"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", us, "--ussr", ussr, "--drones", "--mods", MODS, "--plan-seconds", "60",
            "--extra", f"{extra} -zcrTestTitle {title}"]
    if variant in NO_DRONES:   # no drone mods, no drone teams (the A/B of note 530)
        argv.remove("--drones")
    if variant in SEEDS:
        seed = ROOT / ".runtime" / "attack" / f"seed_{POINTS.get(scenario, scenario).lower()}_{SEEDS[variant]}"
        if SEEDS[variant].startswith("@"):   # a whole map's plans (lab/attackplan.py --all)
            seed = ROOT / ".runtime" / "attack" / f"seed_{SEEDS[variant][1:]}"
        if not (seed / "zcr" / "attackplan.txt").exists():
            raise SystemExit(f"no plan file {seed / 'zcr' / 'attackplan.txt'} - run lab/attackplan.py --export first")
        argv += ["--seed-profile", str(seed)]
    elif variant in DCO_CFG:
        # DCO's settings file for this variant: DCO's Recommended file with the variant's keys on top (as lab/inftest.py).
        seed = ROOT / ".runtime" / "seeds" / f"assault-{variant}"
        (seed / "DCO").mkdir(parents=True, exist_ok=True)
        rec = ROOT / ".runtime" / "seeds" / "dco_recommended.json"
        base = json.loads(rec.read_text(encoding="utf-8-sig")) if rec.exists() else {}
        base.update(DCO_CFG[variant])
        (seed / "DCO" / "DCO_GlobalConfig.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
        argv += ["--seed-profile", str(seed)]
    if play:
        # 2 Nov (Martin: "could you prepare version of farm battle that I could as soldier for one side?", "I would like to
        # test gameplay as well"): the game hosts the match as for watching, but without our spectator mode - no director
        # camera, the game's own deploy menu: he picks a side and spawns as a soldier among the AI teams, at 1x.
        argv += ["--solo"]
    elif watch:
        # The game window, at 1x by default (Martin watches at 1x - 28 Oct: 'it jumps because of speed'); always passed, the
        # game keeps its multiplier between runs. The test still lasts 'minutes' game minutes.
        argv += ["--solo", "--watch"]
        argv[argv.index("--extra") + 1] += f" -zcrSpeed {speed:g}"
        argv[argv.index("--minutes") + 1] = str(round(minutes / speed, 2))
    shown = watch or play
    planner = None
    if variant in LIVE:   # the live planner beside the battle (lab/liveplan.py), for one side
        import time
        (ROOT / ".runtime" / "liveplan").mkdir(parents=True, exist_ok=True)
        planner = subprocess.Popen([sys.executable, "-u", str(ROOT / "lab" / "liveplan.py"), "--label", label, "--after", str(time.time()),
                                    "--side", "both" if variant in LIVE_BOTH else live_side, "--picker", LIVE[variant][0]] + (["--drones"] if LIVE[variant][1] else [])
                                   + (["--objective", POINTS[scenario], "--scan", str(SCANS[scenario])] if scenario in SCANS else [])
                                   + (["--rules-side", {"harbour": "south", "south": "harbour", "US": "USSR", "USSR": "US"}.get(live_side, "south")]
                                      if variant in RULES_VS else []), cwd=str(ROOT),
                                   stdout=open(ROOT / ".runtime" / "liveplan" / f"{label}.log", "a", encoding="utf-8"), stderr=subprocess.STDOUT)
    try:
        subprocess.run(argv, cwd=str(ROOT), stdout=None if shown else subprocess.DEVNULL, stderr=None if shown else subprocess.DEVNULL,
                       creationflags=0 if shown else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    finally:
        if planner and planner.poll() is None:
            planner.terminate()
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


def rides(lines: list, side: str, rounds: dict) -> dict:
    """AI Conflict's rides for one side, from its trip state changes (29 Oct, note 444): asked (a vehicle spot planned),
    delivered (the team dismounted), failed (fell back to walking), failed at the HQ (the team's last place within 150 m
    of where the side's teams stood in the first round), and the most rides boarding or driving at the same moment."""
    first = rounds[min(rounds)] if rounds else []
    hq = (sorted(x for _, _, x, _ in first)[len(first) // 2], sorted(z for _, _, _, z in first)[len(first) // 2]) if first else None
    where = {}      # numeric slot -> [(t, x, z)]
    for l in lines:
        if "[ZCR][LIVE]" in l and f"kind=team side={side} " in l:
            m = re.search(r" t=(\d+) kind=team side=\w+ id=(\d+) .* x=(-?\d+) z=(-?\d+)", l)
            if m:
                where.setdefault(int(m.group(2)), []).append((int(m.group(1)), float(m.group(3)), float(m.group(4))))
    state, out, peak = {}, {"rides_asked": 0, "rides_delivered": 0, "rides_contact": 0, "rides_failed": 0, "rides_failed_at_hq": 0, "rides_slow_out": 0}, 0
    for l in lines:
        if "[VEHICLE_STATE_CHANGED]" not in l or f"faction={side} " not in l:
            continue
        st, pv = re.search(r" state=(\w+)", l), re.search(r"previous_state=(\w+)", l)
        slot, t = re.search(r"numeric_slot=(\d+)", l), re.search(r"t_ms=(\d+)", l)
        if not st or not slot or not t:
            continue
        st, slot, t = st.group(1), int(slot.group(1)), int(t.group(1)) // 1000
        if st == "SITE_PLANNED" and pv and pv.group(1) == "WAITING_FOR_SITE":
            out["rides_asked"] += 1
        elif st == "DISMOUNT":
            out["rides_delivered"] += 1
            if "reason=ZCR_CONTACT_DISMOUNT" in l:   # 3 Nov (note 519): the team got out near the objective, on foot from there
                out["rides_contact"] += 1
        elif st == "FALLBACK" and state.get(slot) == "DISMOUNT":
            # Delivered, then a slow get-out (DISEMBARK_TIMEOUT ~20 s after the drop, 30 Oct 23:35): not a failed ride.
            out["rides_slow_out"] += 1
        elif st == "FALLBACK":
            out["rides_failed"] += 1
            seen = [p for p in where.get(slot, []) if p[0] <= t]
            if hq and seen and math.hypot(seen[-1][1] - hq[0], seen[-1][2] - hq[1]) <= 150:
                out["rides_failed_at_hq"] += 1
        state[slot] = st
        peak = max(peak, sum(1 for v in state.values() if v in ("SPAWN_COMMIT", "BOARDING", "TRANSIT")))
    out["rides_peak"] = peak
    return out


def summarize(run_dir: Path, scenario: str, variant: str, objective: tuple | None = None, attacker: str = "") -> dict:
    """objective: (base id, name) for a run without the assault generals (e.g. a watched match, to compare). The point
    scenario: both sides' numbers (us_..., ussr_...), who took the point and when."""
    attacker = attacker or SCENARIOS[scenario]
    if attacker == "BOTH":
        out = {"scenario": scenario, "variant": variant, "run": run_dir.name, "run_path": str(run_dir)}
        sides = {s: summarize(run_dir, scenario, variant, objective, s) for s in ("US", "USSR")}
        out["objective"] = sides["USSR"].get("objective", "?")
        for k in ("at_obj_3", "at_obj_5", "at_obj_5_pct", "at_obj_8", "at_obj_12", "at_obj_15", "first_arrival_s", "to_obj_pct", "lone_survivors", "ride_fails",
                  "captured", "capture_s", "hq_m", "teams_in", "third_in_s", "first_to_third_s", "plan_dismounts", "holds", "hold_go_s", "rides_asked", "rides_delivered", "rides_contact", "rides_failed", "rides_failed_at_hq", "rides_slow_out", "rides_peak"):
            for s in ("US", "USSR"):
                out[f"{s.lower()}_{k}"] = sides[s].get(k)
        out["at_obj_5"] = (sides["US"].get("at_obj_5") or 0) + (sides["USSR"].get("at_obj_5") or 0)
        out["ride_fails"] = (sides["US"].get("ride_fails") or 0) + (sides["USSR"].get("ride_fails") or 0)
        out["us_lost"], out["ussr_lost"] = sides["USSR"].get("def_lost"), sides["USSR"].get("att_lost")
        # Losses to FPV drones (lab/droneloss.py: the game credits a drone's hit to nobody or to a man in the car it hit).
        dl = sides["USSR"].get("drones") or {}
        for s in ("US", "USSR"):
            out[f"{s.lower()}_lost_drones"] = (dl.get(s) or {}).get("to_drones", 0)
            out[f"{s.lower()}_drone_kills"] = (dl.get(s) or {}).get("drone_kills", 0)
        for k in ("minutes", "script_errors", "crashed"):
            out[k] = sides["USSR"].get(k)
        return out
    defender = "US" if attacker == "USSR" else "USSR"
    out = {"scenario": scenario, "variant": variant, "run": run_dir.name, "run_path": str(run_dir)}
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        out["error"] = "no log"
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # The objective: the attacker's plan names it; its place from the strategist's snapshot (base ids = graph nodes).
    obj_id, obj_name = objective if objective else (None, "")
    for l in lines if not objective else []:
        if "[ZCR][PLAN]" in l and f"faction={attacker} " in l:
            m = re.search(r"Assault test: everything at (.+?) \(base (\d+)\)", l)
            if m:
                obj_name, obj_id = m.group(1), int(m.group(2))
                break
    obj = None
    snap = run_dir / "profile" / "zcr" / "snapshots.jsonl"
    if snap.exists() and obj_id is not None:
        for s in snap.read_text(encoding="utf-8", errors="replace").splitlines()[:4]:
            try:
                obj = next((b for b in json.loads(s).get("bases", []) if b.get("id") == obj_id), None) or obj
            except ValueError:
                continue
    callsign = None
    for l in lines:
        m = re.search(r"\[GRAPH_NODE\] node=(\d+) .*callsign=(\d+)", l)
        if m and obj_id is not None and int(m.group(1)) == obj_id:
            callsign = m.group(2)
    out["objective"] = obj_name or "?"
    # Where the attacker's soldiers are: [ZCR][LIVE] team lines, one round every few seconds.
    rounds = {}
    for l in lines:
        if "[ZCR][LIVE]" not in l or f"kind=team side={attacker} " not in l:
            continue
        m = re.search(r" t=(\d+) kind=team side=\w+ id=(\d+) role=(\w+) men=(\d+) ride=\d x=(-?\d+) z=(-?\d+)", l)
        if m:
            rounds.setdefault(int(m.group(1)), []).append((m.group(3), int(m.group(4)), float(m.group(5)), float(m.group(6))))
    first = None
    if obj:
        for t in sorted(rounds):
            if any(math.hypot(x - obj["x"], z - obj["z"]) <= NEAR_M for _, _, x, z in rounds[t]):
                first = t
                break
    # Do the attack teams arrive together (29 Oct night, the attack plan's hold line)? When each first got within 150 m of
    # the objective; the third one's time, and the gap from the first to the third.
    arrived = {}
    for l in lines:
        if not obj or "[ZCR][LIVE]" not in l or f"kind=team side={attacker} " not in l or "role=ATTACK" not in l:
            continue
        m = re.search(r" t=(\d+) kind=team side=\w+ id=(\d+) role=\w+ men=(\d+) ride=\d x=(-?\d+) z=(-?\d+)", l)
        if m and int(m.group(3)) > 0 and int(m.group(2)) not in arrived and math.hypot(float(m.group(4)) - obj["x"], float(m.group(5)) - obj["z"]) <= 150:
            arrived[int(m.group(2))] = int(m.group(1))
    times = sorted(arrived.values())
    out["teams_in"] = len(times)
    out["third_in_s"] = times[2] if len(times) >= 3 else -1
    out["first_to_third_s"] = times[2] - times[0] if len(times) >= 3 else -1
    # The attack plan in the game: rides dropped at its assembly point, the hold line's go.
    out["plan_dismounts"] = sum(1 for l in lines if "[ZCR][DISMOUNT]" in l and f"faction={attacker} " in l and " assembly" in l)
    go = next((l for l in lines if "[ZCR][HOLD]" in l and f"side={attacker} " in l and "event=go" in l), None)
    out["hold_go_s"] = int(re.search(r" t=(\d+)", go).group(1)) if go else -1
    out["holds"] = sum(1 for l in lines if "[ZCR][HOLD]" in l and f"side={attacker} " in l and "event=hold" in l)

    def at(minute):
        if not rounds or not obj:
            return 0, 0
        t = min(rounds, key=lambda k: abs(k - minute * 60))
        if abs(t - minute * 60) > 30:
            return 0, 0
        near = sum(men for _, men, x, z in rounds[t] if math.hypot(x - obj["x"], z - obj["z"]) <= NEAR_M)
        attack = sum(men for role, men, _, _ in rounds[t] if role == "ATTACK")
        return near, attack

    # How far the side's HQ is from the objective (Arland's HQs swap between matches): where its teams stood in the first round.
    if rounds and obj:
        first_round = rounds[min(rounds)]
        hx = sorted(x for _, _, x, _ in first_round)[len(first_round) // 2]
        hz = sorted(z for _, _, _, z in first_round)[len(first_round) // 2]
        out["hq_m"] = round(math.hypot(hx - obj["x"], hz - obj["z"]))
    for mnt in (3, 5, 8, 12, 15):
        near, attack = at(mnt)
        out[f"at_obj_{mnt}"] = near
        out[f"at_obj_{mnt}_pct"] = round(100 * near / attack) if attack else 0
    out["first_arrival_s"] = first if first is not None else -1
    # AI Conflict's attack orders for the attacker (the re-issued copies left out).
    orders = [re.search(r"slot=(\d+) .*role=ATTACK posture=(\w+) (?:old_target=\d+ new_)?target=(\d+) reason=(\w+)", l)
              for l in lines if ("ORDER_ASSIGNED" in l or "TARGET_REASSIGNED" in l) and f"faction={attacker} " in l and "role=ATTACK" in l]
    orders = [m for m in orders if m and m.group(4) != "ORDER_RECOVERY"]
    real = [m for m in orders if m.group(2) != "LONE_SURVIVOR_RETREAT"]
    out["orders"] = len(real)
    out["to_obj_pct"] = round(100 * sum(1 for m in real if m.group(3) == callsign) / len(real)) if real and callsign else 0
    out["lone_survivors"] = sum(1 for m in orders if m.group(2) == "LONE_SURVIVOR_RETREAT")
    # Failed rides: orders AI Conflict re-issued because a ride didn't work out (any of the attacker's teams).
    out["ride_fails"] = sum(1 for l in lines if ("ORDER_ASSIGNED" in l or "TARGET_REASSIGNED" in l) and f"faction={attacker} " in l
                            and re.search(r"reason=(" + "|".join(RIDE_FAIL) + r") ", l))
    cap = [l for l in lines if "[ZCR][CAPTURE]" in l and obj_name and f"base={obj_name} " in l and re.search(r"to=" + attacker + r"(\s|$)", l)]
    out["captured"] = int(bool(cap))
    m = re.search(r" t=(\d+)", cap[0]) if cap else None
    out["capture_s"] = int(m.group(1)) if m else -1
    out.update(rides(lines, attacker, rounds))
    losses = {s: sum(1 for l in lines if "[ZCR][LOSS]" in l and f" side={s} " in l and "kind=man" in l) for s in (attacker, defender)}
    out["att_lost"], out["def_lost"] = losses[attacker], losses[defender]
    out["drones"] = droneloss.by_side(lines)
    last_t = max(rounds) if rounds else 0
    out["minutes"] = round(last_t / 60, 1)
    out["script_errors"] = len([l for l in lines if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l])
    out["crashed"] = bool(list(log.parent.glob("*.mdmp")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="now", choices=list(VARIANTS))
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--port", type=int, default=2160)
    ap.add_argument("--watch", action="store_true", help="in the game window (solo) - only when nobody else uses the game")
    ap.add_argument("--speed", type=float, default=1, help="with --watch: the game's time multiplier (default 1x)")
    ap.add_argument("--play", action="store_true", help="in the game window as a player: the game's deploy menu, pick a side and play among the AI teams (1x)")
    ap.add_argument("--summarize", default="", help="summarize an existing run folder instead of running")
    ap.add_argument("--cam-spot", default="", help="with --watch: x,z,from_s,to_s - the camera follows the ride nearest that spot "
                    "between those game seconds (-zcrCamSpot, 31 Oct: the airfield edge west of Farm)")
    ap.add_argument("--extra", default="", help="more server parameters for this run only, e.g. '-zcrGetOutProbe'")
    ap.add_argument("--live-side", default="harbour", help="farm-live / farm-gemini: the side with live plans - harbour (its HQ "
                    "nearer Farm; HQs are drawn per match), south, US or USSR")
    a = ap.parse_args()
    if a.summarize:
        r = summarize(Path(a.summarize), a.scenario, a.variant)
    else:
        r = run(a.scenario, a.variant, a.minutes, 0, a.port, a.watch, a.speed, a.cam_spot, a.play, a.live_side, a.extra)
        # A headless battle the game crashed in its first half minute (an engine access violation while loading - 3 Nov
        # 13:06 and 18:49, 2 of the last two days' starts): once more, so a chain of A/B battles doesn't lose an arm.
        if not (a.watch or a.play) and r.get("crashed") and (r.get("minutes") or 0) < 0.5:
            print(f"crashed while starting ({r.get('run')}) - starting it once more", file=sys.stderr)
            r = run(a.scenario, a.variant, a.minutes, 0, a.port, a.watch, a.speed, a.cam_spot, a.play, a.live_side, a.extra)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
