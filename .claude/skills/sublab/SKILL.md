---
name: sublab
description: Set up a sub-lab for one issue of the Reforger commander - the smallest scenario that reproduces it on the game's own maps (no commander), a runner, named scenarios and variants, a score, and its page in the lab app's Sub-labs tab - so the issue is worked on alone with fast runs. Use when the owner names an issue to isolate ("make a scenario that reproduces X", "faster iteration on X", "a sub-lab for X"), or when investigate finds a cause that needs its own reproduction.
---

# A sub-lab for one issue

One issue, one question, one small scenario, many quick runs. The driving sub-lab (`lab/sublabs/driving.toml`,
runner `lab/drivetest.py`, scenario class `ZCR_DriveTest.c`) is the pattern; copy it.

1. **The question and the pass rule**, in one line each, in the owner's words (from his remark and its review note).
   The measure that answers it must be countable per run (legs driven, lost cars, hits, jams...).

2. **The smallest scenario that reproduces it.** On the game's own maps, nothing else running:
   - Game Master Arland / Eden (`lab/reforger.py --map arland-test` / `everon-test`): the map, roads and navmesh only.
   - Vanilla Conflict with AI Conflict off (`--map arland-conflict-test --extra -aicfOff`): the Conflict bases and
     their objects too (the Moss Hill trap needed them).
   - A scenario class `ZCR_<Name>Test.c`, started by `-zcr<Name>Test "<params>"` from `SCR_BaseGameMode.OnGameStart`
     (a `modded class` in that file - on the test maps nothing else starts our code), `ZCR_LabWeather.Apply()` for
     daylight, spawns its own units (crews with `SpawnCharacterInCompartment`, waypoints with
     `AIWaypoint_Move.et`), logs one `[ZCR][<NAME>TEST]` line per event and a `_SUM` line a minute, and gives the
     director a unit to follow when watched (`ZCR_DriveTest.CameraCar` is the example; `ZCR_Director.NextShot`
     asks it). Put the trap or the meeting point in the units' way (a via waypoint), or nothing reproduces.
   - Check it in the window once: `reforger.py --map <test map> --solo --watch --extra "-aicfOff -zcrLabWeather -zcr<Name>Test ..."`.

3. **The runner** `lab/<name>test.py`: `TRACKS`/scenarios (map, points, kind) and `VARIANTS` (server parameters +
   mods, e.g. `raw` = the game alone, `default` = ours, one per mod or switch), and
   `run(scenario, variant, minutes, units, port) -> dict` returning one flat summary (counts from the console log,
   `script_errors`, `crashed`, the run folder). Idle priority; its own port (2148/2150; the watched game keeps 2001).

4. **Register it:** `python lab/sublab.py new <name> --question "..." --issue "..." --pass-rule "..." --runner
   lab/<name>test.py --scenarios a,b --variants raw,default,... --score "<expression on the run dict>" --keys
   k1,k2,...` -> `lab/sublabs/<name>.toml` (commit it). The score weighs what the owner sees most (lost cars and
   crashes into each other over jams, for driving).

5. **Iterate on the issue alone:** change -> compile check (one 1-2 minute run of the scenario) ->
   `python lab/sublab.py run <name> --scenario s --variant default --repeat 2` (and `--variant raw` once for the
   baseline) -> `python lab/sublab.py report <name>` -> the finding into the review note, the technique into the
   knowledge base (`docs/<issue>/`). Never run while the owner plays unless he says so.

6. **Promote:** when the candidate beats the baseline on every scenario, a watched block with the same settings
   (`.runtime/watch_extra.txt`, `watch_mods.txt`), judged by the goal in `goals.toml` - the sub-lab proves the
   mechanism, the watched match proves what he sees.

7. **The page:** the lab app's **Sub-labs** tab lists every sub-lab with its question, pass rule, the scenario x
   variant table (mean score, n, the first keys) and the last runs - from `lab/sublab.py app_data()`; restart the
   app (`pythonw lab/app/server.py`) after adding one.
