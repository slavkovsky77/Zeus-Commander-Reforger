# Vehicle knowledge base - Arma Reforger AI vehicles

What we know about AI vehicles in Arma Reforger 1.8: how the game's own driver works, how every Workshop mod we
could find tries to fix it, and what our own tests showed. Built 23 Oct 2026 (Martin: "build on what's already built
and build a knowledge base from the mods that work with vehicles"). Each fix we write starts here: the technique that
already exists, who proved it, and how it did on our tracks.

| File | What's in it |
|---|---|
| [engine.md](engine.md) | The game's driver: what it does, what script can and can't change, the settings in prefabs, patch history |
| [problems.md](problems.md) | Problem by problem (head-on, rear-end, stuck, corner cutting, off-road, arrival crowds, departures, combat, gunnery): every known technique, who has it, our status |
| [mods.md](mods.md) | Each vehicle mod: mechanism, numbers, hooks, licence, our test result |
| [tests.md](tests.md) | Our test tracks and their results so far |

## Rules for using it

- **Licences.** APL mods (JMVehicleAI, AI Turret Reload Fix, Competent AI driving) may be reused with credit. APL-ND
  mods (DCO_AI, CRX, REAPER) and mods with no stated licence (DCO's GitHub repo, Advanced AI Command - not checked):
  we read them, describe the technique and write our own code - never copy theirs. Study copies stay outside this repo
  (`D:\work\dco-reforger`, `D:\work\dco-reforger-workshop`, `D:\work\_mods_dl\_src\<id>`).
- **Credit.** A technique taken from a mod names the mod and author in the code comment and the commit.
- **Measure.** A technique counts as working for us only after the test track (and then a watched match) shows it.
- Get a mod's code with `python lab/workshop.py unpack <workshop id>`.
