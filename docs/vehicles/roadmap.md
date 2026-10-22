# Our vehicle mod - roadmap (23 Oct 2026)

Martin: "what is the plan for our vehicle mod, because none of the existing ones are probably good". None is: the
Workshop's vehicle mods are convoy tools for players (Advanced AI Command, Placeable AI Convoy Routes), combat AI with
some vehicle use (DCO, CRX), single fixes (BlackReign, Competent AI driving, the reload fix) - and the one real driving
mod (JMVehicleAI) made our jams worse.

## What it is
A separate server-side addon, working name **ZCR Traffic**, that any scenario can load (only the base game as a
dependency); our commander depends on it. It doesn't replace the game's driver - nothing can - it **supervises** it with
the levers that work (cruise speed, a physics push, waypoints, prefab settings; see engine.md). Every rule has a switch,
settings, a log line, a measure and a test track.

## Blocks
| Block | Job | Built on | Status |
|---|---|---|---|
| Traffic manager | one 4 Hz tick over all AI vehicles: position, speed, heading, neighbours (grid), stuck timer | `ZCR_Driving` | partly |
| Speed arbiter | each car's cruise speed = the lowest request of all rules; released when none asks | new (rules now set speed each on their own) | to build |
| Oncoming yield | both to 15 km/h when meeting head-on on one lane | `ZCR_Oncoming` | built 22 Oct, untested |
| Spacing governor | speed from the gap to the car ahead (stop / crawl / match / free) | Advanced AI Command's technique, our code | to build |
| Departure gate | cars leave a base or pad a few seconds apart, only with the way clear | Advanced AI Command's staggered start, our test track | to build |
| Stuck ladder | push at 20 s -> re-order once -> reverse pulses -> park aside -> crew walks on, vehicle cleared off camera | `ZCR_Push`, DCO transport, BlackReign | push / park done |
| Route shaping | road price, per-class turn radius, our own road route with waypoints every ~150 m | ZCR Road Price, Competent AI driving's values, `RoadNetworkManager` | road price built |
| Road hygiene | clutter props by roads removed at start; wrecks off the road | Moss Hill finding, `ZCR_Wrecks` | wrecks done |
| Measures | head-ons, rear-ends, jams, long stops, trip times, off-road share | `ZCR_Driving`, `[ZCR][COLLISION]`, `[ZCR][OFFROAD]` | mostly done |
| Test tracks | one per problem, run nightly as a regression suite | `ZCR_DriveTest`, `lab/drivetest.py`, `lab/drivenight.py` | 5 tracks |

## Order - one block at a time, each proven on its track, then in a watched match
1. The driving night: what exists (push, early unjam, oncoming yield, road price) against the mods.
2. Speed arbiter + spacing governor + departure gate (crashes into each other, crowded exits).
3. Stuck ladder (re-order once, reverse pulses, a clean give-up).
4. Route shaping (our road route, turn radius per class).
5. Package as its own addon without AI Conflict dependencies (now: `AICF_BadRoadPoints`, `AICF_FIAPatrolCrew`);
   a Workshop release only if Martin wants one.

## Exit rule (Martin's "last chance")
After steps 1-2, watched matches on Arland: jams <= 3, long stops <= 2, cars hitting each other <= 1 a match - else
vehicles are cut down (rides only for long marches) or dropped.
