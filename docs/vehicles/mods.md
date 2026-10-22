# Vehicle mods, one by one

Downloads and ratings as on the Workshop, 22 Oct 2026. "Read" = we read its code (unpacked with `lab/workshop.py`).

## JMVehicleAI - jm3009 - 6A8490E1621E7B3C - APL - read, tested
1.0.2 for 1.8.0.13, ~170 KB of script, 2,257 downloads, 97%. A manager ticking every 250 ms over every AI vehicle
(`JMVAI_Manager`), settings in `Configs/JMVehicleAI/JMVAI_Settings.conf` (loaded once per world; our addon
`addons_local/ZCRJMVAITune` changes them on its first tick). Driving: speed profiles (wheeled 70, tracked 45 km/h),
curve braking, convoy gaps and cohesion, oncoming yield, horn, obstacle braking 8-40 m, terrain (slopes, roll guard,
water, surface, narrow 6 m -> 20 km/h, night/fog/rain), town caution, circle detection, anti-stuck (6 s, reverse 2.5 s,
3 tries; method 1 physics push 2.5 m/s - method 0 gear+throttle "overridden by the AI driver"), learning per vehicle
type saved in `$profile`. Combat: breakthrough, retreat, short halts, hull turn, remount, hull-down, IFV modes, smoke.
Gunnery: modded `SCR_AIGetAimErrorOffset` and `SCR_AICombatComponent.EvaluateWeaponAndTarget`.
**Our test (9 watched matches):** as shipped jams 4-21 a match, tuned 1-14, Arland long stops 9-10 - worse than
without it (Arland ~6 / ~5); its obstacle braking fired 1,086 times in one match. Kept: the push. Gunnery untested.

## Advanced AI Command - HOLLOWxPOINT - 69A404653EE3F3C4 - licence not checked - read
1.0.2 for 1.7, 12,730 lines. A map order menu for a human player (move, attack, defend, formations, stances, boarding,
convoys, garrisons). Vehicle part (`AAC_OrderExecution`): mounted groups keep Column and only get waypoints; the
**convoy spacing governor** (4 Hz, gap to the vehicle ahead: stop < 9 m, crawl 12 km/h < 16 m, match < 28 m, free
> 45 m; lead slows to 22 / 10 km/h for 60 / 120 m gaps behind); **staggered start** (i x 2 s, cap 8 s, don't wait for
a predecessor still 5 s); a new lead when the lead is lost. Not usable as a mod for an AI commander; the governor and
the staggered start are the best-specified answers to rear-ends and crowded exits.

## BlackReign GroundVehicle Fix - OgyNeo - D6B2CB76BADE18C3 - read
0.1.1, one file, 4 downloads. Modded `SCR_AIGroup` (AICarMovementComponent can't be modded): an active driving path
and 15 s under 1.5 km/h with < 1.25 m progress a second -> reverse pulses (gear reverse, throttle 0.55, steer 0.35,
every 100 ms for 2.2 s), then retry the same waypoint; 2 tries, 8 s cooldown; never teleports, repairs, refuels or
revives disabled assets.

## Competent AI driving - Doggo5852 - 68FCF11534562F2E - APL - read
1.0.0 for 1.6, 2.3 KB, 211 downloads. Five prefab overrides of `ChimeraAIPathfindingComponent` "Turn radius": 25 m on
BRDM-2, BTR-70 and LAV-25 bases, 40 m on M923A1 and Ural-4320. Not on our UAZ / M998 rides. On the night's truck track.

## AI Turret Reload Fix - Hushmodee - 72DB162D129C40D9 - APL - read
1.0.1 for 1.8.0.10, 5.8 KB, 7,332 downloads, 100%. Every 2 s over AI-occupied turrets; a muzzle empty (or not
chambered) for 13.5 s -> `DoReloadWeaponWith` a compatible magazine (same magazine well) from the turret's own
inventory; none there -> no reload. Started from `SCR_BaseGameMode.OnGameStart`, server only.

## CRX Enfusion A.I. - ATiM- - 5F268647F8A1A1F4 - APL-ND - read
1.3.73 for 1.8.0.10, 44,166 lines, 848,538 downloads, 92%. Mostly soldiers. Vehicles: speed per vehicle and per
waypoint (`SetCruiseSpeed`), Column formation for groups with several vehicles, "drive and attack" (modded
`SCR_AICombatMoveLogicVehicleGunnerBase`: moving while the gunner fires, 30 / 50 km/h), vehicle danger reaction.
Ships test missions, among them `CRX_Arland_Field_Optimized_Column_Driving`. Shares 49 modded classes with DCO.

## DCO_AI Reforger - Richz / DCO - 5EDAAE0D3CC60D6B - APL-ND (GitHub 817r/DCOReforger: no licence) - read
0.4.145 for 1.8.0.13, 161,444 lines, 41,269 downloads, 93%. Soldiers, squads, a full commander. Vehicles:
`DCO_VehicleActive` (hide/expose "scoot", recon, withdraw), `DCO_VehicleCombat` (anti-tank threat detection and
evasion, bail-out, fill turrets, dismount unarmed), `DCO_VehiclePositioning` (fire and hide spots, hull-down,
standoff, snap to navmesh), gunner combat move (duels, relocate under fire), `DCO_TransportMission` /
`DCO_DedicatedTransport` (no 10 m in 20 s: within 75 m = arrived, else re-order once, then abandon), motorized laager
~250 m back, mechanized crews stay and support. No driving fix, nothing about drones.

## REAPER_ImprovedAI - r34p3r - 6A5D2DE1B3F96D7F - APL-ND - downloaded
1.0.1 for 1.8.0.13, 160 KB, 11,141 downloads, 93%. Soldiers; vehicle part: boarding for vehicles and helicopters
(a vanilla boarding lifecycle fix). Not read in detail.

## Not downloaded yet
- **Placeable AI Convoy Routes** (Fat Abu Cheese, 69D2CBB99E2BFEC9, APL, 3,045 downloads): routes from points on a
  road, spacing, corner speeds, stops - a road route for a column.
- **Vehicle Handling Improvements** (Centron, 684C17FA3AB40298, APL-SA, 3,624 downloads): reverse gears, torque,
  braking, "no stuck in small dips" - needs the WCS armour mods.
- **Stuck AI Killer** (xrectifyx, 6937764B20EFCFE5): removes AI that barely move.
