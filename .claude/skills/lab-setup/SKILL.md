---
name: lab-setup
description: Set up the commander lab on a new machine - Arma Reforger, its server and tools, the AI Conflict fork, the optional drone and armour mods, lab/lab.local.toml, a compile check and a first match. Use when someone clones this repo and wants to run it, when lab tools fail on missing paths, or when the owner moves to another PC.
---

# Setting up the lab

1. **What you need** (Steam): Arma Reforger, Arma Reforger Server, Arma Reforger Tools; Python 3.11+.
   Optional: the FPV AI Drones mod and Realistic Combat Drones (drone teams), the armour mods
   (SpaceCore, WCS_Armaments, M2A2 Bradley, BMP-1, M1A1, T-72) - their IDs are in `lab/reforger.py`.

2. **AI Conflict**: clone the fork next to this repo (`../reforger-ai-conflict`, or anywhere and set
   `paths.ai_conflict`), on its working branch.

3. **Your settings**: copy `lab/lab.local.example.toml` to `lab/lab.local.toml` (not committed) and
   fill in the Steam library folder, the fork, the mod folders and where review notes go. Check:

   ```
   python lab/config.py        # prints the settings, MISSING for a path that doesn't exist
   ```

4. **Compile check** (`run-matches`): 1 minute headless, no script errors, `[ZCR]` lines in the log.

5. **First match**: `python -u lab/reforger.py --map arland --minutes 10 --label first --port 2146
   --us phased --ussr phased` (start the bridges first: `python lab/bridges.py`). Then
   `python lab/scorecard.py .runtime/runs/first-*` and `python lab/goals.py --runs <that run>`.

6. **The LLM strategist** (optional): `lab/bridge.local.json` names the provider, model and where the
   key is (an environment variable or a file); see README.md. Never put a key in a committed file.

7. **Your goals**: edit `goals.toml` (the `goal` skill) - the shipped goals are this project's; keep
   the ones you share, pause the rest.

Report to the owner what works, what is MISSING, and the first match's scorecard.
