# Workshop texts - Zeus Commander Reforger 0.1.0 (alpha)

What to paste into Workbench's publish dialog for each item (4 Nov 2026). Version **0.1.0** everywhere (the Workshop takes
numbers only; "Alpha" is in the titles). Visibility: see the decision in RELEASE_ALPHA.md (recommended: *unlisted* first).
Publish in this order - each item needs the ones above it on the Workshop already: 1, 2, 3, (4), 5.

| # | Item | Folder (release-alpha) | GUID | Depends on |
|---|---|---|---|---|
| 1 | AI Conflict Core - Zeus Commander edition | reforger-ai-conflict/AIConflictCore | CF39E4A7CCBBF845 | Arma Reforger |
| 2 | AI Conflict Arland - Zeus Commander edition | reforger-ai-conflict/AIConflictArland | ACAA98B674F022BB | 1 |
| 3 | Zeus Commander Reforger | reforger-commander/ZeusCommanderReforger | CA2CA4E14BB55417 | 1, 2 |
| 4 | FPV AI Drones (Reforger) - Martin's separate mod, only if the alpha keeps drones | reforger-local-mods/FPV_AI_Drones (repo fpv-ai-reforger) | 3257E44260058CE5 | Realistic Combat Drones |
| 5 | Zeus Commander: The Battle for Beauregard (Alpha) | reforger-commander/ZCR_Alpha | CF67CCE40B62DA50 | 1, 2, 3, 4, DCO_AI Reforger, Competent AI driving, Realistic Combat Drones |

Dependencies from other authors (never bundled, only listed):

| Workshop id | Name | Author | Licence | Why |
|---|---|---|---|---|
| 5EDAAE0D3CC60D6B | DCO_AI Reforger 0.4.145 | Richz (DCO) | APL-ND | soldiers' and squads' tactics; our commander switches its per-squad features through its public API |
| 68FCF11534562F2E | Competent AI driving 1.0.0 | see its page | APL | AI drivers take wider turns (no forward-reverse loops) |
| 65AD60E204191D37 | Realistic Combat Drones 2.3.7 | SalamiBoiDev | APL | the FPV drones themselves (FPV AI Drones flies them) |

---

## 1. AI Conflict Core - Zeus Commander edition

**Title:** AI Conflict Core - Zeus Commander edition

**Summary (one line):** Ishafel's AI Conflict, with the changes Zeus Commander Reforger needs. Not compatible with the original.

**Description:**

AI Conflict by Ishafel runs AI armies in Arma Reforger's Conflict: squads, recruitment, trucks and APCs, bases, supplies
and the radio network. This is a modified copy of it, made for **Zeus Commander Reforger**. It is not made or endorsed by
Ishafel. Original: https://github.com/Ishafel/Arma-Reforger-AI-Conflict - all credit for AI Conflict goes to Ishafel and
its contributors.

What this edition changes:
- Squads per side, fireteam size and when teams set out can be set by a scenario.
- Attack teams follow a plan per team: a drop point out of the enemy's sight, a route from cover to cover, wait or go.
- A second wave: when the attack is down to half its men and home is safe, the home-defence teams join it.
- Soldiers stuck in rocks hop free; teams thrown out of their ride near the target go on foot at once.
- Rides wait until the whole team is aboard and leave a base one at a time; a failed ride gets a new one quickly.
- In a one-point battle both sides can take the point (alone in its core for 30 seconds).
- A scenario can carry its own launch settings, so players don't need command-line parameters.

Use it **instead of** the original AI Conflict Core, never together with it (both define the same classes).

Licence: Apache License 2.0, as the original. LICENSE and NOTICE (what was changed, file by file) are in the addon.

**Tags:** AI, Conflict, Scripts (as offered by the dialog)

**Dependencies:** Arma Reforger only.

## 2. AI Conflict Arland - Zeus Commander edition

**Title:** AI Conflict Arland - Zeus Commander edition

**Summary:** AI Conflict's Arland scenarios, for the Zeus Commander edition of AI Conflict Core.

**Description:**

Ishafel's AI Conflict scenarios on Arland (easy, medium, hard), changed only to run on *AI Conflict Core - Zeus Commander
edition*. Original: https://github.com/Ishafel/Arma-Reforger-AI-Conflict (credit: Ishafel and contributors). Not made
or endorsed by Ishafel. Do not load together with the original AI Conflict.

Licence: Apache License 2.0, as the original; LICENSE and NOTICE in the addon.

**Tags:** Scenario, AI, Conflict

**Dependencies:** AI Conflict Core - Zeus Commander edition.

## 3. Zeus Commander Reforger

**Title:** Zeus Commander Reforger

**Summary:** A commander for AI Conflict's armies: where to attack, with how much, by ride or on foot, with drones.

**Description:**

Zeus Commander Reforger steers the AI commander of AI Conflict. Each side gets a plan - its main effort, the bases it
holds and avoids, how many defenders join the attack, when to storm - and AI Conflict carries it out with all its own
rules. On top of that:
- Fireteams move through cover and stay low in danger: no standing up when enemies or drones are near.
- Rides: vehicles wait for their team, give way on one-lane bridges, get unstuck, and drop teams out of sight of the target.
- Drone teams: the commander decides how many FPV drone teams it keeps (2-6) and where they fly; drones look round
  before they dive and hunt groups of soldiers (needs FPV AI Drones and Realistic Combat Drones).
- With DCO_AI Reforger loaded (see the alpha scenario), riders stay mounted to their drop point and quiet squads far from
  the enemy use DCO's light detail (better frame rate).
- Houses at the objective are searched and occupied first; fortifications are built facing the enemy.

On its own it does nothing visible: play it through a scenario - **Zeus Commander: The Battle for Beauregard (Alpha)**.

Built on AI Conflict by Ishafel (Apache 2.0) - this addon copies none of its code and changes it only through its own
modded classes.

**Tags:** AI, Conflict, Scripts

**Dependencies:** AI Conflict Core - Zeus Commander edition; AI Conflict Arland - Zeus Commander edition.

## 4. FPV AI Drones (Reforger) - only if the alpha keeps drones

Martin's own mod, ported from his Arma 3 FPV AI Drones; its own repo (fpv-ai-reforger) and its own release. Not prepared
here beyond the packed build check. Its texts: from that repo's README when Martin decides (see RELEASE_ALPHA.md).
Dependency: Realistic Combat Drones (SalamiBoiDev, APL) - it flies RCD's drones, changes none of RCD's classes.

## 5. Zeus Commander: The Battle for Beauregard (Alpha)

**Title:** Zeus Commander: The Battle for Beauregard (Alpha)

**Summary:** Two AI armies fight for the town of Beauregard on Arland. Join a side or watch.

**Description:**

The first playable alpha of Zeus Commander Reforger. The US and the Soviets start at their main bases on Arland; Farm is a
Soviet base; **Beauregard**, the town by the sea, is neutral and the only objective. Both commanders put everything on it:
fireteams ride out, get dropped out of sight, go in from cover to cover, storm the town and hold it once taken. When an
attack is down to half its men, the home-defence teams come as a second wave. FPV drone teams hunt over the town all the
time. A battle is usually decided within 15-45 minutes - and it can change hands.

How to play: Play > Scenarios > *Zeus Commander: The Battle for Beauregard (Alpha)* - pick a side and spawn among the AI
teams, or host it on a server (scenario id `{E035D09029D235F6}Missions/ZCR_Alpha_Beauregard.conf`). Everything is set
by the scenario; server admins can still change any setting with the launch parameters listed in RELEASE_ALPHA.md.

This is an alpha: expect bugs (known issues below). Reports with the server's console.log are welcome.

Known issues:
- The game can crash after an FPV drone hits a burning BTR-70 (about 1 battle in 77).
- DCO_AI Reforger sometimes logs a null pointer in DCO_ArmorPair (harmless so far).
- Soldiers at Beauregard use the houses only partly (14-34% indoors).

Includes: the battle's mission, our bridge to DCO_AI Reforger (riders stay mounted, light detail for quiet squads - only
DCO's public switches, nothing of DCO changed or copied) and a cheaper road price for AI pathfinding.

Credits: AI Conflict by Ishafel; DCO_AI Reforger by Richz; Realistic Combat Drones by SalamiBoiDev; Competent AI driving.

**Tags:** Scenario, Conflict, AI

**Dependencies:** AI Conflict Core - Zeus Commander edition; AI Conflict Arland - Zeus Commander edition; Zeus Commander
Reforger; FPV AI Drones; DCO_AI Reforger; Competent AI driving; Realistic Combat Drones.
