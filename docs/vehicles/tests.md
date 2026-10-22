# Our vehicle tests

## The driving test track (lab/drivetest.py, ZCR_DriveTest)
Crewed vehicles shuttle A -> B -> A (via a trap point when given) on the game's own maps with no commander:
Game Master Arland / Eden (`arland-test`, `everon-test`) or vanilla Conflict Arland with AI Conflict off
(`arland-conflict-test`, `-aicfOff`). Logged per car: legs and their time, jams, stuck spells, failed drives,
pushes, collisions, oncoming slow-downs, lost cars with the reason. `python lab/drivetest.py <track> --variant <v>`;
watch one in the window with `reforger.py --solo --watch` (the director follows the test cars).

| Date | Track | Variant | Legs | Lost | Notes |
|---|---|---|---|---|---|
| 22 Oct 22:28 | mosshill (plain map, no via) | raw / ours | 11 / 10 | 0 / 2 | the 2 lost cars met head-on at 1947,1185; cars never went through the trap |
| 22 Oct 22:40 | mosshill (plain, via the trap) | raw / ours | 8 / 12 | 0 / 0 | raw: one car stuck 405 s; ours: longest 168 s; nothing caught at the trap on the plain map |
| 22 Oct 22:52 | mosshill-conflict (AI Conflict on) | raw / ours | 0 / 7 | 3 / 1 | the trap catches here: cars jammed at 2291,1277; AI Conflict's war around the track |
| 22 Oct 23:04 | mosshill-conflict (AI Conflict off) | raw / ours | stopped | - | first two cars lost at 36-49 s in every run on this map |
| 22 Oct 23:14 | watched in the window | ours | - | cars 1-2 at 41/49 s, 3+5 head-on at 359 s | Martin: cars wobble at 3x, crash into each other |

## Watched matches (lab app Progress: traffic, stuck, bumps)
| Block | Arland jams / long stops a match | Everon | Crashes |
|---|---|---|---|
| 22 Oct 15:00-18:20, no moves | ~6 / ~5 | ~1 / ~1.5 | 5 of 19 |
| JMVehicleAI as shipped | 21, 7 / 10, 4 | 13 (8 min), 18 / 3, 7 | 1 of 4 |
| JMVehicleAI tuned | 10, 14 / 9, 9 | 13, 5, 1 / 5, 1, 1 | 0 of 5 |
| Push back-offs (21:15-23:10) | 5, 14, 9, 10 / 1, 2, 4, 2 | 3, 2, 2 / 0, 2, 2 | 1 of 11 |

## Headless pairs
- Road price 0.1 vs 0.3 (Arland, 12 min): moving vehicles off the road 4% vs 13%, "unreachable" log lines 25 vs 73.
- Push: 8-m back-offs moved 5.3 and 7.7 m in 3.5 s (Arland, 10 min).

## Next: the driving night (NIGHT.md, lab/drivenight.py)
5 tracks (headon, mosshill-conflict, trucks, northfarm, everonexit) x raw / ours / no oncoming / road price /
Competent AI driving / CRX / JMVehicleAI / best, twice each; the winner in 3 h of watched matches.
