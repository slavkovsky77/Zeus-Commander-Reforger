# Vehicle problems and every known technique

Status: **ours** = in our code; **built** = in our code, not yet proven; **idea** = known technique, not built;
**tested-worse** = tried, made things worse. Numbers in brackets are review notes.

## 1. Head-on meetings on narrow roads (cars crash into each other)
Seen: two head-on crashes in two test-track runs, both drivers dead; Martin watching the Moss Hill track (305-307).

| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Both slow down when meeting | **ours** `ZCR_Oncoming` (22 Oct) | every 0.5 s: two AI cars each with the other ahead within 90 m, under 8 m off its line, heading at it, both over 8 km/h -> both `SetCruiseSpeed(15)` until passed or 100 m apart | built - on the night's headon track |
| One waits, then checks the road is clear | JMVehicleAI | yield: detect 30 m, the other passes at 15 km/h within 40 m, wait up to 60 s (back-off option) | tested-worse as part of the whole mod (its waits made queues) |
| Honk at soldiers in the way | JMVehicleAI | horn within 15 m, 3.5 m lane | idea |

## 2. Rear-end collisions and convoys (the second car rams the first)
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Spacing governor | Advanced AI Command | 4x a second each trailing truck's cruise speed from the gap to the one ahead: < 9 m stop, < 16 m crawl 12 km/h, < 28 m match its speed, > 45 m free; the one ahead counts as stopped under 1 m/s | idea - the best-specified one; write our own |
| Lead waits for stragglers | Advanced AI Command | a gap of 60 m behind -> lead 22 km/h, 120 m -> 10 km/h (never stops, keeps the route) | idea |
| Convoy gap by time | JMVehicleAI | min 12 m, 2 s time gap, within 120 m, 6 m lane | tested-worse (with its other rules) |
| Convoy cohesion (lead waits up to 60 s) | JMVehicleAI | | tested-worse - turned our separate rides into queues |
| Creep behind a slow car of the side | **ours** Follow (`-zcrFollow`) | 4 km/h behind a car under 5 km/h within 14 m | off since 22 Oct 08:20 (crashed together with teleports; teleports are gone now - worth a retest) |
| Column formation for multi-vehicle groups | CRX, Advanced AI Command, vanilla | the game's Column formation | not applicable - our rides are one car per group |

## 3. Departures from a base (several cars at once at the exit)
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Staggered start | Advanced AI Command | truck i may not roll before i x 2 s after the order (cap 8 s); a predecessor still for 5 s is not waited for | idea - matches our "jams are at the base exits" finding (79% of jams in two squares a match) |
| One at a time with the start clear | **ours** test track only | a car leaves only when nothing is within 10 m of the start, 12 s apart | ours (track) |

## 4. Stuck vehicles
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Physics push back | JMVehicleAI -> **ours** `ZCR_Push` | velocity 2.5 m/s towards the spot every 100 ms, heading kept, up to the distance or 8 s | ours - 5-8 m in 3.5 s, no crash; long stops Arland ~5 -> ~2 a match |
| Back-off and park-aside | **ours** `ZCR_Driving` | jammed pair: the yielder 8 m back; an abandoned or waiting blocker 10-14 m aside; max 4 a vehicle, 30 s apart | ours |
| Early unjam | **ours** | after 20 s still with a car within 10 m (not 45 s) | ours (22 Oct) |
| Reverse pulses, retry the same waypoint | BlackReign GroundVehicle Fix | after 15 s under 1.5 km/h and < 1.25 m a second: reverse gear + throttle 0.55 + steer 0.35 re-applied every 100 ms for 2.2 s; max 2 tries, 8 s cooldown; hooks `SCR_AIGroup` | idea - a second way if the push fails |
| Re-order once, then abandon | DCO transport | < 10 m in 20 s: within 75 m of the goal counts as arrived; else the move is ordered again once (a new route), then the vehicle is abandoned | idea - cheap |
| Delete AI that barely move | Stuck AI Killer | removes or logs stuck AI near players | not wanted on screen |
| Unstuck in small dips | Vehicle Handling Improvements | stronger reverse gears, torque, braking (needs WCS mods) | not tried (needs the armour mods) |

## 5. Corner cutting and off-road routes (fenced fields, rocks)
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Roads cheaper than fields | **ours** ZCR Road Price | `SCR_AIWorld` "Price of roadnetwork paths" 0.3 -> 0.1 | built - off-road 13% -> 4% in one pair; on the night's tracks |
| Wider turn radius | Competent AI driving | `ChimeraAIPathfindingComponent` "Turn radius" 25 m APCs, 40 m trucks | on the night's truck track |
| Curve braking | JMVehicleAI | look 150 m ahead, ignore < 10 degrees, 60 km/h gentle / 18 km/h sharp, brake 3 m/s2 (tracked 2) | tested-worse (with the rest of the mod) |
| Many waypoints along the road | Bohemia forum | the driver beelines between waypoints | idea - needs our own road route (no API) |
| Unreachable ride points avoided | **ours** AI Conflict fork `AICF_BadRoadPoints` | a point a ride failed to reach is avoided by later rides that match | ours |
| Clutter by the road | **ours** finding | Moss Hill: a supply cache 7 m one side, a static wreck and brick piles the other (2292,1277) | idea: remove clutter props by roads at start |

## 6. Arrival crowds (cars meeting at the destination or a turnaround)
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Close enough counts as arrived | DCO transport | within 75 m when no progress | idea |
| Motorized laager | DCO | after dropping the squad the car waits ~250 m back at a forest edge | ours (similar): covered dismount 180-450 m short of the objective |

## 7. Vehicles in combat
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Hide / expose, firing spots with hull-down and standoff, anti-tank evasion, withdraw when outgunned, bail out, fill turrets | DCO (`DCO_VehicleActive`, `DCO_VehicleCombat`, `DCO_VehiclePositioning`, gunner combat move) | ~2,300 lines | idea - run DCO in an armour block |
| Drive and attack | CRX | the driver keeps moving while the gunner fires: 30 km/h medium range, 50 km/h long range | idea (CRX and DCO change the same class - one or the other) |
| Short halts, hull-down, retreat when damaged | JMVehicleAI | halt 5 s, move 10 s; hull-down 15-80 m; retreat at 40% health (tracked 50%) | idea (gunnery part untested) |
| Hold fire with friends near the target | **ours** `ZCR_Armour` | 20 m round the target, 8 m off the line of fire | ours |

## 8. Gunnery
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Reload empty turrets | AI Turret Reload Fix | every 2 s; a muzzle empty 13.5 s -> `TurretControllerComponent.DoReloadWeaponWith` a matching magazine (same magazine well) from the turret's storage | idea - for the armour block |
| Narrower aim error, wait for a better aim | JMVehicleAI | modded `SCR_AIGetAimErrorOffset` for turret gunners (error x0.4, tolerance x0.7, skill 70+) | idea |
| Machine gun or main gun by target | JMVehicleAI | after the game's choice, a turret gunner switches weapon by target type and range (coax up to 300 m on infantry) | idea |
| Shots and empty guns measured | **ours** `ZCR_VehicleGuns` | ammo read every second (AI turret shots raise no event) | ours |

## 9. Soldiers and vehicles
| Technique | Who | Mechanism | Status |
|---|---|---|---|
| Step out of the way of a vehicle | vanilla `SCR_AICombatMoveLogic_MoveFromIncomingVehicle` (CRX relabels it) | in combat only | engine |
| Slow for soldiers ahead | **ours** armour guard | 5 km/h with a friend within 30 m ahead | ours (armour only) |
| Honk | JMVehicleAI | 15 m | idea |
