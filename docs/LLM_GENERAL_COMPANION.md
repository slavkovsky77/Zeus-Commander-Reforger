# The LLM general - optional companion tooling (not in the alpha)

Status 4 Nov 2026: a lab tool. **Not part of Zeus Commander Reforger 0.1.0-alpha**; the alpha's in-game general is the
rules' point general (`-zcrPointGeneral`, docs/RELEASE_ALPHA.md section 2). This page says what the LLM general is and
what it would take to offer it to server owners later.

## What it is
`lab/liveplan.py` runs beside a server, outside the game. Every round it reads the battle from the server's profile
folder (the [ZCR] log lines, the strategist's snapshots), draws drop points, routes from cover to cover and support
spots for each attack team from what that side knows, and lets a picker choose for each team: a drop point, a route,
go / wait / support, the drone teams, a strategy stance. Pickers: `code` (the cheapest - also Python) or `gemini`
(Gemini through OpenRouter, with a map image; anything invalid falls back to the code's pick). It writes
`$profile:zcr/liveplan.txt`; the game reads it with `-zcrLivePlan` (AICF_ZcrAttackPlan.LoadLive).

## Why it is not in the alpha
- It needs Python 3 with the lab's code and data: the 10 m ground scan of the point (.runtime/attack/scan_*.jsonl,
  made by the game with -zcrAttackScan) and the map's tree data (.runtime/maps/arland/map_trees.json). None of it is
  packaged; the Workshop ships game addons only.
- A model key: the server owner's own OpenRouter key, in an environment variable (`OPENROUTER_API_KEY`, see the README).
  Never in a scenario, an addon or a file we publish. Every model call is paid for by whoever owns the key.
- It runs on the server's machine, beside the server - most players host from the game or rent a server.

## What it would take (for a later release)
1. A small standalone package: liveplan.py and what it imports, the ground scan and tree data for each supported point
   (or the scan made at server start), one command: `python liveplan.py --run <server profile folder> --side both
   --picker gemini --objective Beauregard`.
2. A scenario variant with `-zcrLivePlan` on (the in-game point general still plans each side's main effort; the live
   plan adds the per-team routes and drops; without the companion running, the game behaves as the alpha).
3. Key handling as now: read from the environment; a clear message when it is missing (the code picker then plans).
4. A note for server owners on cost and privacy (the model sees a map image and a short text of the battle).
