"""The infantry tests (23 Oct evening, Martin: "maybe I would like to move to DCO - some infantry tests that I would like
to watch"; "I can imagine these as small sub-lab integration tests"; review note 343). Rifle squads only, on real
ground of Arland (picked with -zcrCoverScan: buildings, trees and walls around every 100-m point of the island), played by
the guns test (ZCR_GunTest.c, -zcrGunTest) with the soldier sampler on - the same cover, stance and death measures as the
matches. The runner of the sub-lab "infantry" (lab/sublabs/infantry.toml):

    python lab/inftest.py storm-foot --variant dco --minutes 12
    python lab/inftest.py storm-foot --variant game --watch      # in the game window (only when the game is free)
"""
import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lab"))
import guntest  # noqa: E402

DCO = "5EDAAE0D3CC60D6B"   # DCO_AI Reforger (Workshop, APL-ND: loaded, never copied)

SCENARIOS = {
    # name: (US side, USSR side) - groups kind:count:x,z[:role] joined by + (ZCR_GunTest.c)
    # Storm on foot: a US rifle squad attacks Moss Hill farm on its hilltop (19 buildings, 57 walls within 40 m, 89 m
    # high), held by a Soviet rifle squad; the US start 450 m south at the foot of the hill (23 m): open ground first,
    # woods in the middle, ~100 m of open slope up to the farm.
    "storm-foot": ("squad:1:2270,788:attack", "squad:1:2270,1238:defend"),
    # Village: the same squads, the Soviets holding the village west of Moss Hill (35 buildings, 55 walls within 40 m,
    # 31 m high), the US from 450 m east (51 m): fields with hedges, walls and tree rows on the way (-zcrCoverScan).
    "storm-village": ("squad:1:1920,1138:attack", "squad:1:1470,1138:defend"),
    # With drone operators (Martin, 24 Oct: "each team would get a drone operator - the attacker has drones, then the
    # defender, then both"): a 2-man operator team behind its squad launches FPV teams of 4 at the enemy every 90 s
    # (at most 2 in the air); the soldiers' drone reactions run as in matches. Defender operators stay 120 m behind the
    # position (outside the 60-m 'taken' circle).
    "farm-drones-att": ("squad:1:2270,788:attack+drones:1:2270,720:support", "squad:1:2270,1238:defend"),
    "farm-drones-def": ("squad:1:2270,788:attack", "squad:1:2270,1238:defend+drones:1:2270,1360:support"),
    "farm-drones-both": ("squad:1:2270,788:attack+drones:1:2270,720:support", "squad:1:2270,1238:defend+drones:1:2270,1360:support"),
    "village-drones-att": ("squad:1:1920,1138:attack+drones:1:1990,1138:support", "squad:1:1470,1138:defend"),
    "village-drones-def": ("squad:1:1920,1138:attack", "squad:1:1470,1138:defend+drones:1:1350,1138:support"),
    "village-drones-both": ("squad:1:1920,1138:attack+drones:1:1990,1138:support", "squad:1:1470,1138:defend+drones:1:1350,1138:support"),
}
SCENARIO_WORDS = {
    "storm-foot": "a US rifle squad (9 men) attacks a Soviet rifle squad (6 men) holding Moss Hill farm on its hilltop, 450 m away: "
                  "open ground, woods, then an open slope up to the farm",
    "storm-village": "the same US squad attacks the Soviet squad holding the village west of Moss Hill (35 buildings), 450 m away "
                     "across fields with hedges, walls and tree rows, slightly downhill",
}
VARIANTS = {
    # name: (extra command line, Workshop mods, words). Our mod's attack change (hold 60 m from a seen enemy instead of
    # closing to 15 m, ZCR_CoverLayer's modded SCR_AICombatMoveLogic_Attack) is always loaded - -zcrStandoff 0 turns it
    # off, so "game" and "dco" are those alone (23 Oct 20:25; the first runs had it on: game60, dco60).
    "game": ("-zcrStandoff 0", "", "the game's own soldier AI alone"),
    "ours": ("-zcrSoldierLayer", "", "the game's AI with our soldier layer: hold 60 m from a seen enemy instead of closing to 15 m, never standing in danger"),
    "dco": ("-zcrStandoff 0", DCO, "the DCO_AI Reforger mod (Workshop) on both squads, alone"),
    # Martin, 23 Oct 22:50: "maybe DCO + our hold-back + something" (the first runs with the hold-back on took the farm 3 of 3)
    "dcoours": ("-zcrSoldierLayer", DCO, "DCO with our soldier layer: hold 60 m from a seen enemy instead of closing in, never standing in danger"),
    # Our commander storming through DCO (24 Oct): the attacking squad pushes - DCO's contact drills and overmatch off for
    # that squad (bridge ZCR_DCO); dcopush2 also the attackers' side's pinned / break contact / contact SOP / ambush off.
    "dcopush": ("-zcrStandoff 0 -zcrStormPush", DCO, "full DCO; the attacking squad is ordered to storm: DCO's contact drills and overmatch off for it (our bridge)"),
    "dcopush2": ("-zcrStandoff 0 -zcrStormPush", DCO, "as dcopush, and the attackers' side also has DCO's pinned, break-contact, contact-SOP and ambush drills off"),
    "dcoatt": ("-zcrStandoff 0", DCO, "full DCO attacks; the defenders have DCO turned down (all its switches off, the game's perception) - as close to the game's AI as DCO allows"),
    "dcodef": ("-zcrStandoff 0", DCO, "DCO turned down attacks (all its switches off, the game's perception); full DCO defends"),
    # Drone storms (24 Oct): own-side kills next to drones even with our anti-drone fire holding near friends - is it our
    # fire or DCO's own? The same storm without our small-arms fire at drones (our drone reactions - down, cover - stay).
    "dconoad": ("-zcrStandoff 0 -zcrNoAntiDrone", DCO, "DCO on both squads; our small-arms fire at drones off (soldiers still go down and to cover from drones)"),
    "game60": ("", "", "the game's AI with our 60-m hold-back (the first runs, 23 Oct 19:17-20:20)"),
    "dco60": ("", DCO, "DCO with our 60-m hold-back (the first runs, 23 Oct 19:30-20:20)"),
}


def _title(name: str, scenario: str, variant: str) -> str:
    sys.path.insert(0, str(ROOT / "lab"))
    import sublab
    return sublab.title(name, scenario, variant)


# "DCO turned down" for one side (Martin, 24 Oct 01:10: "vanilla vs DCO, switch attack and defence roles"). DCO can't be
# switched off for one side (it replaces the game's soldier scripts and 18 of its behaviour trees for everyone), so the
# closest is its own per-faction settings: every behaviour switch off, close-quarters drills, stragglers, contact sharing
# and night behaviour off, perception back to the game's 1.0 (DCO's default 1.5). Written into the run's profile.
DCO_MIN = {**{k: False for k in ['behATSpecialist', 'behAmbushDrill', 'behAssaultFire', 'behAwareness', 'behBreakContact', 'behBuddyCallout', 'behCombinedArms', 'behContactSOP', 'behEnemyWeapons', 'behExplosionReactions', 'behHearing', 'behLeaderRTOGrenadier', 'behLeanPeek', 'behMGGunner', 'behMarksman', 'behPinned', 'behPistolCQB', 'behPlayerVoice', 'behProneMove', 'behReactionTime', 'behRearm', 'behRearmEnemySources', 'behReloadDiscipline', 'behSecurity360', 'behSpecialistRecovery', 'behSuppressLastKnown', 'behTargetPriority', 'behWindowFire']},
           "cqbEnabled": False, "stragglerEnabled": False, "shareEnabled": False, "nightEnabled": False, "aiPerception": 1.0}
# The attackers' side with DCO's stalling behaviours off (pinned, break contact, contact SOP, ambush drill).
DCO_PUSH = {"behPinned": False, "behBreakContact": False, "behContactSOP": False, "behAmbushDrill": False}
SEEDS = {
    "dcopush2": {"factions": {"US": DCO_PUSH}},
    "dcoatt": {"factions": {"USSR": DCO_MIN}},   # full DCO attacks (US), the defenders (USSR) DCO turned down
    "dcodef": {"factions": {"US": DCO_MIN}},     # the attackers (US) DCO turned down, full DCO defends (USSR)
}


def seed(variant: str):
    if variant not in SEEDS:
        return None
    d = ROOT / ".runtime" / "seeds" / variant
    (d / "DCO").mkdir(parents=True, exist_ok=True)
    # On top of DCO's Recommended file (the one it writes when there is none): with only the factions block DCO filled
    # the other keys with its code defaults, 4 of them not Recommended (24 Oct, the first dcoatt run).
    base = {}
    rec = ROOT / ".runtime" / "seeds" / "dco_recommended.json"
    if rec.exists():
        base = json.loads(rec.read_text(encoding="utf-8-sig"))
    base.update(SEEDS[variant])
    (d / "DCO" / "DCO_GlobalConfig.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
    return d


def run(scenario: str, variant: str, minutes: float, units: int, port: int, watch: bool = False, speed: float = 3) -> dict:
    us, ussr = SCENARIOS[scenario]
    extra, mods, _ = VARIANTS[variant]
    label = f"inftest-{scenario}-{variant}-p{port}" if not watch else f"inftest-{scenario}-{variant}-watch"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland-test", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "none", "--ussr", "none",
            "--extra", f"-aicfOff -zcrLabWeather -zcrNoFIA -zcrArmourVanilla -zcrNoArmour -zcrTestTitle {_title('infantry', scenario, variant)} -zcrEndWhenDecided -zcrGunTest {us};{ussr} {extra}".strip()]
    if mods:
        argv += ["--mods", mods]
    if seed(variant):
        argv += ["--seed-profile", str(seed(variant))]
    if "drones:" in us + ussr:
        argv += ["--drones"]   # Martin's FPV AI Drones + Realistic Combat Drones
    if watch:
        # The game window at 3x by default (Martin, 24 Oct: "make default speed 3x"): the game's own time multiplier
        # (-zcrSpeed, as the watched matches); the test still lasts 'minutes' game minutes.
        argv += ["--watch", "--solo"]
        if speed > 1:
            argv[argv.index("--extra") + 1] += f" -zcrSpeed {speed:g}"
            argv[argv.index("--minutes") + 1] = str(round(minutes / speed, 2))
    subprocess.run(argv, cwd=str(ROOT), stdout=None if watch else subprocess.DEVNULL, stderr=None if watch else subprocess.DEVNULL,
                   creationflags=0 if watch else getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    out = guntest.summarize(run_dir, scenario, variant)
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    if not log:
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    kv = lambda line: dict(re.findall(r"(\w+)=(-?[\w.]+)", line))
    # In cover while fighting: the sampler's 30-s lines, weighted by how many knew an enemy within 300 m.
    cover = {}
    for side in ("US", "USSR"):
        rows = [kv(l) for l in text.splitlines() if "[ZCR][EXPOSURE]" in l and f"side={side} " in l]
        eng = sum(int(r.get("engaged", 0)) for r in rows)
        cover[side] = {k: round(sum(int(r.get("engaged", 0)) * int(r.get(k, 0)) for r in rows) / eng) if eng else None
                       for k in ("covered", "prone", "incover")}
    deaths = [kv(l) for l in text.splitlines() if "[ZCR][LOSS]" in l and "relation=KILLED_BY_ENEMY" in l]
    stood = [d for d in deaths if d.get("stance") == "STAND"]
    open_ = [d for d in deaths if d.get("covered") in ("0", "false")]
    dist = [int(d["distance"]) for d in deaths if d.get("distance", "").isdigit()]
    first = min((int(d["t"]) for d in deaths if d.get("t", "").isdigit()), default=0)
    # Losses from the head count of the first summary (a US rifle squad is 9 men, a Soviet one 6).
    sums = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST_SUM]" in l]
    men = lambda row, side: int(row.get(f"{side}_men", 0) or 0)
    start = {s: max((men(r, s) for r in sums[:2]), default=0) for s in ("us", "ussr")}
    # Losses from the death log, not the squad's head count: DCO moves soldiers into groups of its own (23 Oct: the
    # head count said 8 US lost, the death log 4, and 5 US soldiers stood on the farm at the end).
    all_deaths = [kv(l) for l in text.splitlines() if "[ZCR][LOSS]" in l and " kind=man " in l]
    lost = {s: sum(1 for d in all_deaths if d.get("side") == s.upper()) for s in ("us", "ussr")}
    # Drone storms (24 Oct): drones launched at each side, soldiers lost to them (no killer, as scorecard.py's 'down'),
    # and to their own side's fire (the farm storm with the defenders' drones: 3 of 9 US soldiers shot by their own team
    # leader firing at a drone over the squad).
    lines = text.splitlines()
    launched = {s: sum(int(kv(l).get("drones", 1) or 1) for l in lines if "why=test-operator" in l and f" side={s.upper()} " not in l)
                for s in ("us", "ussr")}
    # A drone's blast can credit the soldiers it kills to a friend ("killed by friendly AI": 24 Oct, the farm storm without
    # any fire at drones - the grenadier 5 m from the drone's target, 35 ms after him): a "friendly" death within 0.25 s of
    # a drone detonating or of a death with no killer is the drone's (by the log's clock; a real shot 0.6 s before a blast
    # stays friendly fire).
    def clock(l):
        m = re.match(r"(\d+):(\d+):(\d+\.\d+)", l)
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    loss_lines = [l for l in lines if "[ZCR][LOSS]" in l and " kind=man " in l]
    blasts = [c for c in (clock(l) for l in lines if re.search(r"FPVAI: drone\d+ detonated", l)) if c is not None]
    blasts += [c for c in (clock(l) for l in loss_lines if "killer_kind=none" in l) if c is not None]
    # ... or one "killed" by a soldier already dead (14:43, the farm: a rifleman wounded by the blast that killed the team
    # leader died 1.2 s later, credited to him - the distance in the line was the distance to his body; the first farm storm's
    # three "shot by their team leader" were all credited to dead team leaders). The loss log says so since 24 Oct 14:50
    # (killer_dead=1); older runs: an earlier death of that name whose body is at the line's distance (+-1 m, positions
    # are rounded to 1 m - 2 m let a real shot at 1.8 m through).
    dead = [(clock(l), kv(l)) for l in loss_lines]
    def splash(l):
        c = clock(l)
        if c is None:
            return False
        if " killer_dead=1" in l or any(abs(c - b) <= 0.25 for b in blasts):
            return True
        d = kv(l)
        here = (float(d.get("x", 0) or 0), float(d.get("z", 0) or 0))
        return any(dc is not None and dc < c and k.get("victim") == d.get("killer")
                   and abs(math.dist(here, (float(k.get("x", 0) or 0), float(k.get("z", 0) or 0))) - float(d.get("distance", -9) or -9)) <= 1
                   for dc, k in dead)
    ff = [(kv(l), splash(l)) for l in loss_lines if "relation=KILLED_BY_FRIENDLY_AI" in l]
    by_drone = {s: sum(1 for d in all_deaths if d.get("side") == s.upper() and d.get("killer_kind") in ("none", "") and d.get("stance"))
                + sum(1 for d, sp in ff if d.get("side") == s.upper() and sp) for s in ("us", "ussr")}
    friendly = {s: sum(1 for d, sp in ff if d.get("side") == s.upper() and not sp) for s in ("us", "ussr")}
    held = {s: sum(int(kv(l).get("held_friend", 0) or 0) for l in lines if "[ZCR][ANTIDRONE]" in l and f" side={s.upper()} " in l)
            for s in ("us", "ussr")}
    shot_down = {s: sum(1 for l in lines if "[ZCR][ANTIDRONE]" in l and "shot_down=1" in l and f" side={s.upper()} " in l) for s in ("us", "ussr")}
    for s in ("us", "ussr"):
        out.update({f"{s}_drones_at": launched[s], f"{s}_drone_lost": by_drone[s], f"{s}_ff": friendly[s], f"{s}_held_friend": held[s],
                    f"{s}_shot_down": shot_down[s]})
    end = re.findall(r"\[ZCR\]\[TEST_END\] t=(\d+) why=(\w+)", text)
    out.update({
        "ended_s": int(end[-1][0]) if end else None, "ended_why": end[-1][1] if end else "time",
        "us_men": start["us"], "ussr_men": start["ussr"], "us_lost": lost["us"], "ussr_lost": lost["ussr"],
        "taken_s": out.get("taken_us_s", 0),
        "us_cover": cover["US"]["covered"], "ussr_cover": cover["USSR"]["covered"],
        "us_prone": cover["US"]["prone"], "ussr_prone": cover["USSR"]["prone"],
        "us_incover": cover["US"]["incover"], "ussr_incover": cover["USSR"]["incover"],
        "deaths": len(deaths), "died_standing_pct": round(100 * len(stood) / len(deaths)) if deaths else None,
        "died_open_pct": round(100 * len(open_) / len(deaths)) if deaths else None,
        "fight_m": round(statistics.median(dist)) if dist else None, "first_loss_s": first,
        "dco_loaded": DCO in (run_dir / "run.json").read_text(encoding="utf-8") if (run_dir / "run.json").exists() else None,
    })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="+", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="game", choices=sorted(VARIANTS))
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--port", type=int, default=2170)
    ap.add_argument("--speed", type=float, default=3, help="with --watch: the game's time multiplier (default 3x)")
    ap.add_argument("--watch", action="store_true", help="in the game window (the game hosts it; only when nobody else uses the game)")
    a = ap.parse_args()
    for s in a.scenarios:
        print(json.dumps(run(s, a.variant, a.minutes, 0, a.port, a.watch, a.speed)), flush=True)


if __name__ == "__main__":
    main()
