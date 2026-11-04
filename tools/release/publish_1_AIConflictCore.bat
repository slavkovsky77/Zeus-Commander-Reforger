@echo off
rem Opens this alpha item in Workbench with its dependencies found (docs/RELEASE_ALPHA.md, Publish steps).
rem Then: Workbench > Publish Project... - paste the texts from docs/WORKSHOP_ALPHA.md.
start "" "E:\SteamLibrary\steamapps\common\Arma Reforger Tools\Workbench\ArmaReforgerWorkbenchSteamDiag.exe" -gproj "D:\work\release\reforger-ai-conflict\AIConflictCore\addon.gproj" -addonsDir "D:\work\release\reforger-ai-conflict,D:\work\release\reforger-commander,D:\work\release\deps,E:\SteamLibrary\steamapps\common\Arma Reforger\addons"
