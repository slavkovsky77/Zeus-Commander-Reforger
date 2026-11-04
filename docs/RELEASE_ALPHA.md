# Zeus Commander Reforger 0.1.0-alpha - ready to press Publish

Prepared overnight 4 Nov 2026 (Martin, 03:37: "current version is great ... i want it out as alpha version now").
**Nothing was uploaded or posted.** Everything up to Workbench's Publish button is ready; Martin's decisions are in
section 7, the exact steps in section 8.

Branches: `release-alpha` in reforger-commander (origin) and in the AI Conflict fork (remote `mine`, never `origin`).
Worktrees on this PC: `D:\work\release\reforger-commander`, `D:\work\release\reforger-ai-conflict`. The lab's own
branches (master, zcr) are untouched: every release change lives on release-alpha, and the two code changes there are
off unless a scenario asks for them.

## 1. What ships - five Workshop items of ours

| # | Workshop item | Folder (release-alpha) | GUID | Packed | Depends on |
|---|---|---|---|---|---|
| 1 | AI Conflict Core - Zeus Commander edition | reforger-ai-conflict/AIConflictCore | CF39E4A7CCBBF845 | 0.82 MB, 221 files | Arma Reforger |
| 2 | AI Conflict Arland - Zeus Commander edition | reforger-ai-conflict/AIConflictArland | ACAA98B674F022BB | 0.02 MB | 1 |
| 3 | Zeus Commander Reforger | reforger-commander/ZeusCommanderReforger | CA2CA4E14BB55417 | 0.33 MB, 69 scripts | 1, 2 |
| 4 | FPV AI Drones (Reforger) - only if drones stay (decision 1) | reforger-local-mods/FPV_AI_Drones (repo fpv-ai-reforger) | 3257E44260058CE5 | 0.04 MB | Realistic Combat Drones |
| 5 | Zeus Commander: The Battle for Beauregard (Alpha) | reforger-commander/ZCR_Alpha | CF67CCE40B62DA50 | 3 files | 1-4, DCO, Competent AI driving, RCD |

Item 5 holds the scenario (`{E035D09029D235F6}Missions/ZCR_Alpha_Beauregard.conf`), our DCO bridge (moved in from
ZCR_DCO) and the road price override (moved in from ZCR Road Price) - one item instead of three.

Workshop dependencies by other authors - listed, never bundled:

| Id | Name | Author | Licence | Used for |
|---|---|---|---|---|
| 5EDAAE0D3CC60D6B | DCO_AI Reforger 0.4.145 | Richz | APL-ND | squad and soldier tactics; we only call its public API (DCO_SetFeatureOff, DCO_API) |
| 68FCF11534562F2E | Competent AI driving 1.0.0 | (its Workshop page) | APL | AI drivers take wider turns |
| 65AD60E204191D37 | Realistic Combat Drones 2.3.7 | SalamiBoiDev | APL | the FPV drones FPV AI Drones flies |

Not in the alpha: ZCR JMVAI Tune (JMVehicleAI isn't used in the battle), the armour mods, ZEUS WARGAME (nothing of it
anywhere), the lab (lab/, tests, docs) - the Workshop gets only the addon folders.

Workshop texts, tags, dependency lists: **docs/WORKSHOP_ALPHA.md**. Changelog: **CHANGELOG.md** (0.1.0-alpha).

## 2. What a player gets - and what runs with no Python at all

Plainly: **with no Python process at all, the whole battle runs** - both armies, the commanders, the drones. What runs
in the game:
- AI Conflict (Zeus Commander edition) raises, moves and supplies both armies; Zeus Commander's seam gives it each
  side's plan; DCO_AI Reforger runs the squads' and soldiers' tactics.
- **The in-game point general** (new on release-alpha, `-zcrPointGeneral`): every 60 s each side plans what the lab's
  Python "point" general planned - Beauregard the main effort, heavy, two defender teams along, storm it and send the
  drones there while it isn't ours, hold it once ours, the other bases avoided. Same plan lines, same game code path.
- The drone plan: 2-6 operator teams a side, decided every 30 s (with a plan from a general; a side without one would
  fall back to the 3-team baseline - not the case here).
- Everything else Zeus Commander does in the lab battles: rides, one-lane bridges, unjamming, danger stances under
  drones, houses at the point, the second wave, fortifications, the drone hunt, the projectile sweep.

What the lab battles had and the alpha doesn't:
- **Gemini** (lab/liveplan.py, OpenRouter): per team a drop point, a route from cover to cover, wait/go/support, the
  drone teams, a strategy stance (assault / fortify / counter_drone), danger zones. In the alpha every team follows AI
  Conflict's own approach to the point (no stored or live attack plan).
- The strategist bridge (lab/bridge.py) - replaced by the in-game point general.
- The lab's DCO settings file (DCO Recommended + coverPreference 1, shareBuildings) - a player's DCO uses his own file.
- The lab's watch mode (director camera, panels), lab weather, the live map feed and the census - lab instruments.

Measured without any helper (tools/release/loadtest.py, headless, port 2198, only the release items):
- **The battle, 26 game minutes, from the release worktrees' source** (D:\work\release\runs\battle-src-20261104-040830):
  both sides planned by the in-game point general every round (25 a side, `source=point-ingame`), no bridge call, no
  live plan. The US took Beauregard from neutral at **9:44** and held it to the end; US teams passing through took the
  Soviets' Farm at 21:44 (as in the lab's 02:27 Gemini battle). Soldiers lost **US 45, USSR 36**; **79 drone
  launches**; at the end the Soviets still had 9 attack teams on Beauregard (7 of 29 men inside). Median **58.9 FPS**
  (headless). The log: 13.6 MB in 26 minutes (the live map feed off).
- For comparison, the three watched Gemini battles of 4 Nov (town-brains): Soviets took Beauregard at 15:46, US at 12:22,
  Soviets at 16:42; losses 20/37, 30/45, 36/34. The alpha's battle looks of the same kind - the town taken in the first
  10-16 minutes, 35-45 losses a side - but one headless battle is one battle: watch one before judging it.

## 3. The scenario's settings

The mission header's new field `m_sAICFLaunchParams` carries the watched battle's settings (town-brains minus the lab's
helpers). Every read of a launch parameter goes through `AICF_Launch` (fork): the command line first, then the
scenario. So a server admin can still change anything, e.g. `-aicfSquadsPerSide 8`. The scenarios of AI Conflict itself
and the lab's missions leave the field empty: nothing changes there. At start the game logs
`[AICF][LAUNCH] scenario=... params=28 list=...` (and names any parameter read before the scenario was known: none).

| Parameter | What it does |
|---|---|
| -aicfAICommanderMode BOTH | AI Conflict commands both armies (a player joins either as a soldier) |
| -aicfConstructionAttempts 512 | the builders' site search budget (Arland's harbour HQ is cramped) |
| -aicfSquadsPerSide 12, -aicfInfantryDeploySize 4, -aicfMusterSize 4, -aicfMaxAgentsPerFaction 50, -aicfCapCountsAll | 12 fireteams of 4 a side, 50 soldiers a side at most |
| -aicfMaxBuildersPerFaction 6, -aicfVehicleMinimumRequestAgents 2, -aicfArmedRideEvery 0 | engineers, rides for teams of 2+, no armed escort rides |
| -aicfZcrSecondWave 1 | home-defence teams join the attack when it is down to half |
| -zcrPlanSeconds 60, -zcrPointGeneral | the in-game point general, a plan every 60 s |
| -zcrOnePoint Beauregard, -zcrBaseTo Farm:USSR, -zcrNoFIA | the battle: Beauregard the one objective, Farm Soviet, no FIA |
| -zcrBindMainEffort, -zcrAttackPlan, -zcrNoAttackHold | attack teams bound to the main effort, no hold short of it |
| -zcrRideStayMounted | riders stay aboard to the drop point (through DCO's exit rule) |
| -zcrDrones | FPV drone teams for both sides |
| -zcrDangerDronesOnly, -zcrNoCoverLayer | the stance rule reacts to drones; the old cover layer off |
| -zcrArmourVanilla, -zcrMoveTurrets | the game's own LAV-25 / BTR-70 as armour; turret vehicles may be moved |
| -zcrProjSweep | stray rounds at the map origin cleared (frame rate) |
| -zcrNoLiveMap, -zcrNoCensus | the lab's live-map feed and entity census off (log size, CPU) |

Left out on purpose: -zcrLivePlan (Gemini), -zcrBridgeUS/USSR, -zcrLabWeather, -zcrTestTitle, -zcrSpeed, -zcrWatch,
-zcrWatchServer (lab only); -maxFPS, -logStats, -noThrow, -backendFreshSession (engine settings for the lab's servers).

## 4. Checks done

- **Script validation** (Workbench, `-wbModule=ScriptEditor -run -validate`): the whole alpha project (fork Core and
  Arland, ZCR, the scenario, FPV AI Drones, DCO, Competent AI driving, RCD) - "Script validation successful" in every
  configuration (Workbench, PC, Xbox, PS4, PS5). Every server start compiled all five items.
- **Packed build** (`tools/release/pack.py`, Workbench `-packAddon`, headless): all five pack in 7-10 s each. What is
  inside (tools/release/paklist.py): every script and resource; the fork's licence and NOTICE (as a comment-only
  script, since plain .txt files are not packed).
- **Load tests** (`tools/release/loadtest.py`, one server of ours at a time, port 2198, pinned off the watched game's
  cores, stopped by its own process id):
  - from source: two smoke runs of 3-5 game minutes (compile, the scenario's 28 parameters, both sides planned in-game,
    drones up) and the 26-minute battle of section 2;
  - **from the packed items only** (D:\work\release\runs\packed-20261104-043558: `D:\work\release\packed` and the three
    Workshop mods, no source project, no -gproj): the server loaded exactly the game's two addons, our five and the
    three dependencies; `[AICF][LAUNCH] ... params=28`; both sides planned in-game; in 11 game minutes no capture yet,
    the Soviets 11 of 18 attackers inside Beauregard, losses 14 / 12, 29 drone launches, median 59.6 FPS; the
    navlink-door error below gone.
  - Not tested: the scenario started from the game's own menu (that needs the game window, which stayed Martin's) and
    a server started with a config.json (it downloads its mods from the Workshop - ours aren't there yet). Both reach
    the same mission header the server's `-server <scenario>` used here.
- **Script errors of ours: 0** after two fixes found by the load tests:
  - a parameter read while the scripts load, before the game exists (a VM exception in AICF_Launch; it now waits for
    the game);
  - `Unknown class 'SCR_AIGoalReaction_OpenNavlinkDoor'` at every start - **ours, and on master too since 23 Oct**:
    ZCR_Gates' modded class lacked the vanilla `[BaseContainerProps()]`, so the AI agent's own "open the navlink door"
    reaction never loaded in any battle. Fixed on release-alpha (one line); on master it is the main session's call
    (it changes the lab's battles a little). The only modded class of the shipped code with that mistake (all checked).
  Left: `Unknown class 'SAL_DroneBulletComponent'` - Realistic Combat Drones' own Ammo_Bullet_Base.et (theirs, in the
  lab's battles too); a null target in vanilla's own aiming node (`SCR_AIGetFireTimes.c:140`, 3 times in the packed
  run, in 3 of the last 60 lab runs too); AI Conflict's routine ERROR reports (Failed move, MEANINGFUL_TASK,
  CORE_ERROR_BRIDGE) and the game's "Failed move" exceptions (its behaviour tree giving up a path) are not script errors.

## 5. Licence and attribution review

- **AI Conflict edition (items 1, 2):** Apache-2.0, as Ishafel's original. Kept: LICENSE (repo), license.txt (each addon),
  the original notices. Added: NOTICE.md (repo) and NOTICE.txt (each addon) - modified by slavkovsky77, credit to
  Ishafel, not endorsed by Ishafel, every file changed (61) or added (16) since the fork point 8a790b7 (17 Oct 2026);
  changes inside files are marked "ZCR, <date>". The packed addons carry both as `AICF_LICENSE_NOTICE.c` (comments
  only). New GUIDs and titles so it can't be mistaken for, or collide on the Workshop with, the original.
- **Zeus Commander Reforger and the alpha scenario (items 3, 5):** ours. NOTICE.md credits AI Conflict (Apache-2.0); no
  AI Conflict code is copied (only modded classes). **No LICENSE file yet** - decision 3.
- **DCO_AI Reforger (APL-ND):** a dependency only. Our bridge calls DCO's public API (DCO_SetFeatureOff, DCO_API, its
  enums); no DCO class is modded, nothing copied. We do not set DCO's settings from code (its settings live in protected
  fields of its own component - setting them would mean modding DCO).
- **Realistic Combat Drones (APL), Competent AI driving (APL):** dependencies only; FPV AI Drones calls RCD's components
  (SAL_DroneControllerComponent...) and mods no RCD class.
- **ZEUS WARGAME:** nothing of it in any shipped folder (searched: no class, name or text).
- Shared names with DCO's code: only vanilla methods both override (CustomEvaluate, PerformReaction...).
- **No secrets:** lab/bridge.local.json and the OpenRouter key are outside every shipped folder (lab/ isn't shipped).

## 6. Known issues (also in the scenario's description)

- The engine can crash after an FPV drone hits a burning BTR-70 - about 1 battle in 77.
- DCO_AI Reforger logs a null pointer in DCO_ArmorPair now and then (DCO's code; harmless so far).
- Soldiers at the point use the houses only partly: 14-34% of the men there are indoors.
- Without Gemini the attack teams take AI Conflict's own approach to the town, not planned routes through cover.
- The log is big: about 13 MB per 25 minutes (the lab's other measurements stay on - the crash trace helps bug reports).
- The scenario writes `[ZCR][ATTACKPLAN] no $profile:zcr/attackplan.txt` once (harmless: no stored plans in the alpha).
- Do not load together with Ishafel's original AI Conflict (same classes).

## 7. Decisions for Martin

1. **Drones in the alpha?** They need FPV AI Drones (Reforger) published as its own item (your separate mod, private
   repo fpv-ai-reforger; packed and loaded fine here). *Recommendation: yes* - the drones are half of what makes the
   battle (71 of 81 losses in a review battle); publish FPV AI Drones first (unlisted), then the scenario. Without
   drones: drop -zcrDrones and the two drone dependencies from ZCR_Alpha (a 2-line change).
2. **The LLM general: the rules now, Gemini later as optional companion tooling.** *Recommendation: ship the in-game
   point general (rules) in 0.1.0; keep Gemini a lab/companion tool* - it needs a Python process beside the server, an
   OpenRouter key of the server owner's (never ours, every model call is paid for) and a server; nobody on the Workshop
   can run it today. Later: a documented "companion" (python liveplan.py --side both against a server's profile folder) for
   server admins who want it.
3. **A licence for Zeus Commander Reforger, the scenario and FPV AI Drones** (none of their repos has a LICENSE file;
   the Workshop asks for one). *Recommendation: APL-SA* (the Arma community's usual choice: free to use and change,
   credit, share alike, not commercial; it also fits FPV AI Drones flying RCD's APL drones). Alternative: Apache-2.0
   like AI Conflict. The fork stays Apache-2.0 either way. Then a LICENSE file goes into each repo.
4. **The fork's names and courtesy to Ishafel.** Titles "AI Conflict Core/Arland - Zeus Commander edition".
   *Recommendation: keep them; message Ishafel before publishing* (Apache-2.0 doesn't require it; it is the decent thing
   and Ishafel may prefer another name or an upstream merge later).
5. **Visibility.** *Recommendation: Unlisted first* - subscribe from a second account or ask a friend, play one battle
   from the Workshop copies, then switch to Public.
6. **DCO's settings.** The lab used coverPreference 1 and shareBuildings on top of DCO's Recommended. *Recommendation:
   don't touch the player's DCO file; tell server admins in the description which two keys we used.*
7. **Watch mode for players** (the director camera and panels): off in the alpha. *Recommendation: keep off for 0.1.0;
   a "spectator" variant of the scenario later.*
8. **Merge the two opt-in code changes back** (AICF_Launch in the fork, the in-game point general in ZCR) into zcr /
   master after tonight's tests: they change nothing for the lab, and the next release then needs only the rewrite
   script. *Recommendation: yes, the main session merges them when its night runs end.*
9. **Ship despite the 1-in-77 crash?** *Recommendation: yes, as an alpha, with the known issue stated.*

## 8. Publish steps (exact)

Before: decisions 1, 3, 5 made; a preview image per item (Workbench asks for one - the frames in
`D:\work\release\workshop-images\` have the lab's panels on; a clean shot with HIDE UI from the next watched battle is
better). Publishing uses your Bohemia account in Workbench; the first publish of each item can only be done in the
Workbench window (its `-publishAddon` command line is for updates).

For each item **in this order: 1, 2, 3, 4, 5** (an item's dependencies must be on the Workshop before it):
1. Double-click `D:\work\release\reforger-commander\tools\release\publish_<n>_<item>.bat` - Workbench opens the item
   with its dependencies found (it needs the junction folder `D:\work\release\deps`, made by tools/release/loadtest.py).
2. In Workbench: **Publish Project** (Workbench menu; "Publish to Workshop").
3. Fill in from docs/WORKSHOP_ALPHA.md: name, summary, description, version **0.1.0**, visibility (decision 5),
   licence (decision 3; the fork: Apache 2.0), tags, preview image; check that the dependency list matches the table
   in section 1.
4. Publish. Wait for "Publishing successful".
5. Next item.

After the last one: subscribe to item 5 in the game, Play > Scenarios > "Zeus Commander: The Battle for Beauregard
(Alpha)", watch a few minutes; or host it on the PC's server with scenario id
`{E035D09029D235F6}Missions/ZCR_Alpha_Beauregard.conf`.

Updates later (from the command line, per item): Workbench with `-gproj <item> -wbModule=ResourceManager -publishAddon
-publishAddonVersion 0.1.1 -publishAddonChangeNote "..."` (see Workbench/docs/EnfusionScriptAPI/html/Page_CLI.html).

## 9. The next alpha from master

1. In each release worktree: merge master (ZCR) / zcr (fork) into release-alpha.
2. `python tools/release/launch_params.py <the four addon folders>` (the rewrite; `--check` must say 0 left).
3. `python tools/release/fork_notice.py D:/work/release/reforger-ai-conflict`.
4. `python tools/release/pack.py`, then `python tools/release/loadtest.py --minutes 25 --packed D:/work/release/packed`.
5. Publish each changed item as an update.

## 10. Where everything is

- reforger-commander `release-alpha`: ZCR_Alpha/ (scenario, DCO bridge, road price), ZeusCommanderReforger/ (launch reads
  rewritten, the in-game point general, the fork's new GUIDs), tools/release/ (launch_params, pack, paklist, loadtest,
  fork_notice, publish_*.bat), docs/RELEASE_ALPHA.md, docs/WORKSHOP_ALPHA.md, CHANGELOG.md.
- reforger-ai-conflict `release-alpha`: AICF_Launch.c, launch reads rewritten, new GUIDs and titles, NOTICE.md,
  NOTICE.txt, AICF_LICENSE_NOTICE.c.
- Not in git (this PC): `D:\work\release\packed` (the five packed items), `D:\work\release\runs` (the load tests),
  `D:\work\release\deps` and `deps-packed` (junctions to the dependencies), `D:\work\release\workshop-images`.
