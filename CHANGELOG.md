# Changelog

## 0.1.0-alpha - 4 November 2026 (Workshop version 0.1.0)

The first public alpha: **Zeus Commander: The Battle for Beauregard (Alpha)**. Lab builds r1-r73 (18 Oct - 4 Nov 2026),
drawn from the lab's build history (lab/engine_page.py CHANGELOG) and PLAN.md. Ships with *AI Conflict - Zeus Commander
edition* 0.1.0 (Ishafel's AI Conflict as of 17 Oct 2026, modified; see that repo's NOTICE.md).

### The battle
- **The battle for Beauregard** (r73): both armies fight for the town by the sea on Arland; Farm is a Soviet base, every
  other base off the lists. In the watched lab battles the town changed hands (Soviets at 15:46, US at 12:22, Soviets
  at 16:42). The capture rule is the same for both sides: alone in the point's core (60 m) for 30 s takes it, both
  inside = contested (r66) - before, the side at the south HQ could never take a base outside its radio network.
- **A commander per side in the game itself**: the point is the main effort - two defender teams join, the attack teams
  storm it, the drones go there; once taken, it is held (the lab's "point" general, now in-game: no helper program).
- **A second wave** (r72): when the attack is down to half its men and home is safe, the home-defence teams join it.
- **Teams that go in** (r71, r72): no parking in front of the objective, the storm order kept to the end, frozen teams
  fixed, storming soldiers run on under drones.
- **Houses at the point first** (r73): soldiers at the point are sent to interior spots (partly - see known issues).

### Infantry
- Fireteams of 4 with a wedge formation, 12 teams a side (from r13, sizes set by the scenario).
- Soldiers stay low under drones: never standing with an enemy drone within 150 m (the alpha's setting; the rule can
  also take enemies and losses nearby into account).
- Teams thrown out of their ride near the target go on foot at once instead of waiting at the car (r69).
- Soldiers stuck in rocks hop free (r69, the fork's AICF_ZcrUnstick).

### Vehicles and rides
- Rides wait for the whole team, then leave a base one at a time, about 6 s apart (r62, r64); a failed ride at a base
  gets a new one after 20 s; a team gets its order back after a ride (r64). Time lost moving teams: 29% -> 15%.
- Riders stay mounted to their drop point unless the vehicle is badly damaged (with DCO_AI Reforger, r69).
- One car at a time over a one-lane bridge (r68): car hits 0 v 3 in the driving test, no deadlock on the deck.
- Soviets ride UAZ-469 jeeps instead of half-empty Urals (r56); vehicles give way at junctions and to oncoming traffic;
  stuck vehicles are freed; AI drivers prefer roads (a lower road price for pathfinding).

### Drones
- FPV drone teams for both sides; the commander decides how many (2-6) every 30 s and where they fly (r67): launches
  23 -> 65 in 20 minutes.
- Drones fly like drones: a look round before the dive, straight in over a crowd or when hit, no hovering (r70 and the
  FPV AI Drones mod); drone sites forward of the bases; soldiers take cover from drones and shoot at them.

### Performance and stability
- A stutter every few seconds fixed (r67): the depot way-out check spread over frames - 10-s windows with a 200 ms+ frame
  68 -> 1, median FPS 53 -> 57.
- Stray rounds piling up at the map origin are cleared (they cost frame rate over long battles).
- Quiet squads far from the enemy use DCO's light detail (DCO's own profiler: 29% of a frame at 157 soldiers).
- A crash after AI Conflict failed to free a loadout preview fixed (r70).

### For players and server admins
- The scenario carries all its settings (m_sAICFLaunchParams): no launch parameters needed. A parameter on a server's
  command line still wins.
- The lab's measurement feeds (the live map, the entity census) are off in the alpha.

### Known issues
- The engine can crash after an FPV drone hits a burning BTR-70 (about 1 battle in 77).
- DCO_AI Reforger logs a null pointer in DCO_ArmorPair now and then.
- Soldiers at the point use the houses only partly: 14-34% indoors.
- Gemini, the LLM general of the lab battles, is not part of the alpha (it needs a helper program and a key); the
  in-game commander is the rules' point general.
