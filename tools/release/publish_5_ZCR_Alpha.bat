@echo off
rem Opens this alpha item in Workbench with its dependencies found (docs/RELEASE_ALPHA.md, Publish steps).
rem Then: Workbench > Publish Project... - paste the texts from docs/WORKSHOP_ALPHA.md.
start "" "E:\SteamLibrary\steamapps\common\Arma Reforger Tools\Workbench\ArmaReforgerWorkbenchSteamDiag.exe" -gproj "D:\work\release\reforger-commander\ZCR_Alpha\addon.gproj" -addonsDir "D:\work\release\reforger-ai-conflict,D:\work\release\reforger-commander,D:\work\release\deps,E:\SteamLibrary\steamapps\common\Arma Reforger\addons" -addons CF39E4A7CCBBF845,ACAA98B674F022BB,CA2CA4E14BB55417,5EDAAE0D3CC60D6B,68FCF11534562F2E,3257E44260058CE5,65AD60E204191D37
