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
| `ZeusCommanderReforger/Scripts/Game/ZeusCommanderReforger/` | `ZCR_StrategicPlan` (per-side plan), `ZCR_AdaptiveCommanderPolicy` (the seam, a `modded class`) |
| `lab/` | The fight loop (to come): headless matches, logs, metrics, the LLM bridge |

Log lines start with `[ZCR]`; AI Conflict's own start with `[AICF]`.

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
