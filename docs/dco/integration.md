# DCO as the tactical layer, Zeus Commander as the strategic one

Martin, 24 Oct 2026 01:05: "DCO will be used as the tactical AI mod and Zeus Commander as strategic". DCO_AI Reforger
(Workshop `5EDAAE0D3CC60D6B`, by Richz/DCO) decides how soldiers fight; our commander decides where squads go and what
they attack. This page is what we know about fitting the two together. Licence: DCO is APL-ND on the Workshop and the
GitHub repo (github.com/817r/DCOReforger) has no licence - we load the official Workshop mod and never change, copy or
ship its code; anything DCO itself needs goes to its author as an issue or pull request (Martin posts them).

## How DCO plugs into the game

- **106 replaced game AI classes** (223 replaced methods): the soldier's decision-making and combat component, attack
  behaviour, every combat-move logic (attack, hide from fire, suppressive), squad perception, fireteams, healing.
- **18 replaced behaviour trees** - files with the game's own paths, so every soldier runs them: `Soldier.bt` (the main
  tree), `Attack_Default`, `Defend`, `Idle_TakeCover`, `HandleCombatMove`, `CombatMoveRequest_Move`, `SuppressBehavior`,
  `ThrowGrenadeTo`, `MoveFromDanger_UnknownFire`, ... plus 17 trees of its own (CQB, bounding, garrison, rearm, ...).
- **Its own commander** (65k lines) - inactive on our maps (no AI commander components in the Conflict worlds).
- Code size: Commander 65k lines, Individual (soldier behaviour) 32k, Group 16k, Settings 13k, Game Master UI 9k.

## The levers DCO gives us (no DCO changes needed)

| Lever | Scope | How |
|---|---|---|
| Settings file | global and per faction | `$profile:DCO/DCO_GlobalConfig.json`, 709 keys (README next to it); a `"factions": {"USSR": {...}}` block overrides one side |
| Behaviour switches | per faction | 28 `beh*` keys (target priority, 360 security, hearing, window fire, MG/AT/marksman roles, break contact, ambush drill, contact SOP, pinned, prone move, suppress last known, ...) |
| Runtime settings | global and per faction | `DCO_API.SetSetting(mod, key, value, faction)`, `GetSetting(key, faction)` |
| Group features | per group | `SCR_AIGroup.DCO_SetFeatureOff(mask, source)` - `DCO_EGroupFeature`: CQB, OVERMATCH, LEAN, WINDOW_FIRE, SPECIALISTS, HEARING, NIGHT, AWARENESS, REARM, CONTACT_DRILLS, TARGET_PRIORITY, EXPLOSION_REACTIONS; presets FULL / BALANCED / LIGHT |

What is **not** possible: switching DCO off for one side or group. The replaced classes and behaviour trees apply to every
soldier; the per-faction switches only turn its optional behaviours off. A true "vanilla side" would need the author to
ship his trees under their own names and pick them per faction - a redesign, not a small PR.

## What clashes with ours

- `SCR_AICombatMoveLogic_Attack`: our 60-m hold-back (ZCR_CoverLayer) and DCO both replace it; with DCO loaded the fights
  are at 7-10 m again - DCO's version wins. Under DCO our hold-back is dead code.
- `SCR_AIGetOutVehicle` (our crews stay aboard), `SCR_AIAttackBehavior`, `SCR_AIGroupUtilityComponent`,
  `SCR_BaseGameMode`, `SCR_CharacterDamageManagerComponent` - also replaced by both; not yet checked in a match which
  wins. Next: a watched match with our commander and DCO (integration test `dco-loads` only proves they compile together).

## Infantry sub-lab results so far (lab/inftest.py, sub-lab infantry)

Storm on foot at Moss Hill farm (US 9 attack, Soviets 6 hold the hilltop) and storm a village, 12 minutes a run:

| Setup | Taken | Attackers lost (of 9) | Notes |
|---|---|---|---|
| game's AI on both sides | 5 of 6 | 3.3 | fights 14-92 m, little cover |
| our soldier layer | 5 of 6 | 3.2 | fights a little further out |
| DCO on both sides | 2 of 6 | 5.0 | more cover, fire from further (village 54-144 m); the defence wins |
| DCO + our soldier layer | 0 of 2 | 9, 9 | our hold-back overridden (fights at 7-10 m) |
| full DCO attacks, "DCO turned down" defends (watched) | 0 of 1 | 3 | defenders in cover 67% |
| "DCO turned down" attacks, full DCO defends (watched) | 1 of 1 (7.3 min) | 2 | fights at 27 m |

"DCO turned down" = every behaviour switch off, close-quarters drills, stragglers, contact sharing and night off,
perception back to the game's 1.0 (the per-faction block, seeded into the run's profile by `reforger.py --seed-profile`).

Reading so far (single runs for the role swap - not firm): DCO's extra behaviours make soldiers cautious - strong in
defence, slow in the attack (attacks with full DCO stall; with its extras off they push through). That is where the
strategic layer should come in: our commander knows which squads are storming.

## Plan

1. **Bridge addon `ZCR_DCO`** (ours, depends on ZeusCommanderReforger and DCO, loaded only together with DCO): when our
   commander orders a squad to storm, switch its DCO contact drills / overmatch off (`DCO_SetFeatureOff`), back on when
   it holds. Measured in the infantry sub-lab (storm with full DCO both sides, storming squad drills off) against plain DCO.
2. **Watched matches with our commander + DCO** (Arland): captures, losses, cover, fighting distance, FPS, crashes; and
   whether crews stay aboard and the storm still works.
3. **Upstream** (issues/PRs Martin posts): only what our side can't do - e.g. a per-faction `enabled` switch for lab
   comparisons (needs the trees question answered by the author), or an API call for group features if the method
   name isn't meant to be public.
