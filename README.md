# Zeus Commander Reforger

The Zeus Commander AI for Arma Reforger: our doctrine for a trench-and-drone war, and an LLM
strategist, on top of [AI Conflict](https://github.com/Ishafel/Arma-Reforger-AI-Conflict), which
runs AI commanders in Reforger's Conflict mode.

AI Conflict keeps everything it does: squads, recruitment, trucks and APCs, bases, the radio
network. This addon steers its commander through one seam. After AI Conflict builds the candidate
bases for a squad, our side's plan (`ZCR_StrategicPlan`) raises or lowers each base's score and the
force it calls for. AI Conflict then assigns squads with all its own checks. With an empty plan,
nothing changes.

Plan and research: https://claude.ai/artifact/HeQBbPV4PanCcGWGRBmAGp

## Layout

| Path | What |
|---|---|
| `ZeusCommanderReforger/` | The addon (GUID `CA2CA4E14BB55417`), depends on vanilla, `AIConflictCore` and `AIConflictArland` |
| `ZeusCommanderReforger/Scripts/Game/ZeusCommanderReforger/` | `ZCR_StrategicPlan` (per-side plan), `ZCR_AdaptiveCommanderPolicy` (the seam, a `modded class`), `ZCR_Strategist` (situation report every 90 s, asks the bridge), `ZCR_AICommander` (runs it on AI Conflict's tick), `ZCR_LossLog` (every loss, for the lab) |
| `lab/bridge.py` | Between the game and the strategist: rules doctrine, Gemini or Claude; checks every answer, falls back to the doctrine |
| `lab/doctrine.py`, `lab/plan.py`, `lab/providers.py` | The rules doctrine, the plan's checks and weights, the model connectors and prompt |
| `doctrines/<FACTION>.md` | Each side's doctrine text for the LLM's prompt - edit to change how a side fights |
| `lab/reforger.py` | One headless match (server tool needed), measured at the end |
| `lab/metrics.py`, `lab/replay.py` | Measurements from the server log; re-running recorded situation reports through a strategist offline |
| `tests/` | Offline tests: `python -m unittest discover -s tests -v` |

Log lines start with `[ZCR]` (`PLAN`, `SNAPSHOT`, `LOSS`, `BRIDGE_MISS`, `STRATEGIST`); AI Conflict's
own start with `[AICF]`. Game options: `-zcrPlanSeconds` (default 90), `-zcrBridge=<url>`.

## The LLM strategist

1. Put your OpenRouter key in a user environment variable, in your own terminal (never in a file
   here): `setx OPENROUTER_API_KEY "<your key>"`. New terminals see it.
2. `lab/bridge.local.json` (not committed) picks the model: `"provider": "openrouter"`,
   `"model": "google/gemini-3.8-flash"` (or `"anthropic/claude-haiku-5.5"`, any id from
   https://openrouter.ai/models), `"api_key_env": "OPENROUTER_API_KEY"`. Direct `gemini` and
   `claude` connectors work the same way with their own keys.
3. Try it without the game: `python lab/replay.py tests/fixtures/report_small.json`.
4. `python lab/bridge.py`, then start a match with `--bridge`.
5. Without a model, the bridge answers with our rules doctrine (`provider: doctrine`); a failed or
   late model answer falls back to it too.

## Compile check

From PowerShell, with AI Conflict cloned to `D:\work\reforger-ai-conflict`:

```powershell
$tools = 'E:\SteamLibrary\steamapps\common\Arma Reforger Tools'
$game = 'E:\SteamLibrary\steamapps\common\Arma Reforger'
$repo = 'D:\work\reforger-commander'
$logs = Join-Path $repo ('.runtime\workbench-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& "$tools\Workbench\ArmaReforgerWorkbenchSteamDiag.exe" -noThrow -wbsilent `
  -gproj "$repo\ZeusCommanderReforger\addon.gproj" `
  -addonsDir "$game\addons,D:\work\reforger-ai-conflict,$repo" `
  -addons '9178E5822AFE48EA,B52C5F6AEDBF423E,CA2CA4E14BB55417' `
  -logsDir "$logs" -wbModule=ScriptEditor -run -validate | Out-Null
```

Pass: exit 0 and `Script validation successful.` in `script.log`. Resource leaks reported at
Workbench shutdown are not script errors.

Vanilla script reference (Bohemia's Script Diff, 1.8.0.13): `D:\work\reforger-api`.

## Credits

Built on AI Conflict by Ishafel (Apache-2.0); see `NOTICE.md`. Never pushed or published without
Martin's go-ahead.
