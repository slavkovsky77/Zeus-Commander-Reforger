# The game's AI driver (Arma Reforger 1.8.0.13)

## How it drives
- A group with a vehicle gets a waypoint; the engine plans a route over the **road network** (built from the map's
  roads at start, filtered by the AIWorld's accepted road types) joined to the **vehicle navmesh** ("BTRlike", agent
  radius 2.6 m since 1.2) for the off-road parts, and the driver follows it. Driving itself is native code.
- **It cuts corners** to the next path point and can prefer a field to a road loop (Bohemia forum: "AI cuts the corner
  and beelines to the next waypoint - use many waypoints"). On our maps 220 of 310 trapped vehicles were 30-80 m off the
  road in fenced fields, UNREACHABLE.
- **No lane discipline, no yielding.** Two cars on one lane keep the middle at full speed until they hit (two head-on
  crashes in two test runs, both drivers dead). Trailing cars don't watch the car ahead (Advanced AI Command's author:
  "the second truck rams it").
- **No real reversing.** A waypoint behind is often UNREACHABLE; setting reverse gear once is overridden by the AI
  driver on the next frame (JMVehicleAI's author tested it). It must be re-applied every ~100 ms (BlackReign) or
  replaced by a physics push (JMVehicleAI, ours).
- **Giving up.** When a drive fails (`EMoveError` STUCK / UNREACHABLE), `SCR_AIProcessFailedMovementResult` orders the
  whole group out (`SCR_AIGetOutActivity`) - the vehicle stays on the road as a blocker.
- **Speed-up hurts.** At the watched game's 3x time multiplier the drivers wobble (Martin, 22 Oct): steering corrections
  overshoot in bigger steps. Tests at 1x and 3x not yet compared.
- **Start of a match.** On vanilla Conflict without AI Conflict, the first two test cars were lost 36-49 s after the
  start in 4 of 4 runs at the same spot (1906,1126); cause not known yet (the track now logs why a car is lost).

## What script can change
| Lever | API | Notes |
|---|---|---|
| Cruise speed | `AICarMovementComponent.SetCruiseSpeed(kmh)`, `ResetCruiseSpeed()` | The one driving control the API gives. Used by JMVehicleAI, Advanced AI Command, CRX, DCO, ours. AICarMovementComponent is engine code and can't be modded (BlackReign). |
| Push the vehicle | `Physics.SetVelocity`, `SetAngularVelocity`, re-applied every 100-250 ms | The AI driver doesn't override it. JMVehicleAI's anti-stuck, our back-offs (`ZCR_Push`). No transform jump, so no replication trouble. |
| Gear / throttle / steering | `VehicleWheeledSimulation.SetGear/SetThrottle/SetSteering/SetBreak` (tracked: `VehicleTrackedSimulation`) | Overridden by the AI unless re-applied every ~100 ms (BlackReign: 22 pulses = 2.2 s). Reverse gear index = gears - forward gears - 2 (JMVehicleAI, from `SCR_ToggleHandbrakeAction`). |
| Teleport | `BaseGameEntity.Teleport` + `RplComponent.ForceNodeMovement` | Works, but our watched matches crashed more with hand moves; replaced by the push. |
| Waypoints | `AIGroup.AddWaypoint/RemoveWaypoint`, `AIWaypoint.SetCompletionRadius` | Several waypoints along the road keep it on the road (forum); a via waypoint forces a route through a point (our test track). |
| Road network | `SCR_AIWorld.GetRoadNetworkManager()`: `GetClosestRoad`, `GetRoadsInAABB`, `GetReachableWaypointInRoad`; `BaseRoad.GetPoints/GetWidth` | No route-finding along roads; our own graph would be needed. `RequestRoadNetworkRebuild(min, max)` exists. |
| Navmesh | `AIPathfindingComponent.SetAreaCosts(config)`, `GetClosestPositionOnNavmesh`; `AIWorld.RequestNavmeshRebuild/RequestNavmeshLoad` | Area costs take a config resource; not tried yet. |
| Group formation | `SCR_AIGroupVehicleManager`, formation "Column" | CRX and Advanced AI Command put multi-vehicle groups in Column; our rides are one vehicle per group. |

## Settings in prefabs (changed by overriding the prefab in an addon)
| Setting | Where | Default | Tried |
|---|---|---|---|
| Price of roadnetwork paths | `Prefabs/AI/SCR_AIWorld.et` | 0.3 (off-road = 1) | 0.1 (ZCR Road Price): moving vehicles off the road 13% -> 4% in one headless pair |
| Price of crossroad on Road network | same | 0.1 | - |
| Navmesh edge path cost coefficient | same, BTRlike navmesh | 3 | - |
| Actual road width percentage / Min Road Width | same | 0.8 / 2 m | - |
| Turn radius | `ChimeraAIPathfindingComponent` on the vehicle prefab | per vehicle | Competent AI driving: 25 m APCs (BRDM-2, BTR-70, LAV-25), 40 m trucks (M923A1, Ural-4320) - on the night's truck track |

## Patch history (driving-related)
- 1.2 (Jun 2024): AI drives and uses road networks; vehicle navmesh agent radius 2 -> 2.6 m.
- 1.6.0.54 (Oct 2025): "AI pathfinding to help AI drivers overcome decision blockade"; reverse speed limited like forward;
  gates opened when reversing; obstacle avoidance direction fixes.
- 1.7 (May 2026): driving physics overhaul (weight, torque, suspension) - not an AI change.
- 1.8.0.10 (Aug 2026): crash fixes for vehicles colliding at speed with passengers, unsafe transform updates during
  physics, entering/leaving turrets; AI pathfinding crash fixes. Nothing on driving behaviour.
- 1.9 Experimental (Sep 2026): powertrain overhaul (less friction in turns; vehicles without a driver steer themselves).

## Bug reports
Steam "AI trucks are totally broken" (70% stop with hazard lights, crew out, never move; 20% stuck on terrain);
Feedback Tracker T191334 (pathfinding glitches), T177755 (AI won't get out of the way of vehicles), AREXP-492
(stuck on wheelbarrows), ARGF-388 (supply trucks stop at the harbour); Arma 3's T75076 (no reversing) and T61600
(convoys in forward-reverse loops).

## Documentation and where to read the real thing
- Official: the [Script API reference](https://community.bistudio.com/wikidata/external-data/arma-reforger/ArmaReforgerScriptAPIPublic/group__AI.html)
  (generated, few explanations), [Behavior Editor: Nodes](https://community.bistudio.com/wiki/Arma_Reforger:Behavior_Editor:_Nodes)
  (AI behaviour trees), the [Navmesh Tutorial](https://community.bistudio.com/wiki/Arma_Reforger:Navmesh_Tutorial),
  [AI changes in 1.2](https://reforger.armaplatform.com/news/modding-update-june-7-2024) and
  [Dev Report #20](https://reforger.armaplatform.com/news/dev-report-20) - the only official words on AI driving. No
  vehicle-AI tutorial exists.
- The code: Bohemia's game scripts for 1.8.0.13 in `D:\work\reforger-api\Arma-Reforger-Script-Diff-1.8.0.13\scripts`
  (generated engine declarations under `Game/generated`). 139 scripts on AI and vehicles: group vehicles
  (`SCR_AIGroupVehicleManager`, `SCR_AIGetUsableVehicle`, `SCR_AIFindAvailableVehicle`), seats (`SCR_AIGetInActivity`,
  `SCR_AIGetOutActivity`, `SCR_AIChangeCompartment`, `SCR_AIOccupyDriversInUsedVehicles`, `SCR_AIFindTurrets`), moving
  (`SCR_AIGetVehicleWaypointParameters`, `AICarMovementComponent`), stuck (`SCR_AIRemoveStuckVehicle`: "when the vehicle
  cannot be moved it removes it from the group's list of owned vehicles" - the crew walks, nothing frees the vehicle),
  combat (`AITurretAimingComponent`, `SCR_AIDecoTargetWithinTurretAimingLimits`, `SCR_AIDangerReaction_Vehicle`,
  `SCR_AIDangerReaction_VehicleHorn`, `SCR_AICombatMoveLogic_MoveFromIncomingVehicle`), small things (lights, handbrake,
  doors). `ChimeraAIVehicleControlComponent` (the AI's vehicle control) exposes nothing to script.
