"""The guns test (23 Oct, Martin: "a subtest with guns being used, maybe against each other or against some infantry -
this sub-lab should test some tanks and APCs"; review note 322). Crewed armour of the two sides meets, or armour attacks
the game's rifle squad, across the open airfield of the Arland test map (ZCR_GunTest.c, -zcrGunTest). The runner of the sub-lab
"guns" (lab/sublabs/guns.toml):

    python lab/guntest.py apc-duel --variant default --minutes 8
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# US point, USSR point: the two ends of Arland's airfield, 800 m apart with a clear view (2 m of rise; -zcrLosScan found 9
# clear 800-m lines on the whole island). The north farm road first used hid them from each other until 45-95 m.
US_AT, USSR_AT = "1720,2838", "920,2838"
POINTS = {"US": US_AT, "USSR": USSR_AT, "US2": "1720,2862", "USSR2": "960,2860"}   # second groups beside the first
SCENARIOS = {
    # name: (US side, USSR side): groups kind:count:point[:role] joined by + (ZCR_GunTest.c); the game's own APCs, or the
    # Workshop tanks / IFVs (loaded with --armour)
    "apc-duel": ("lav25:2:{US}", "btr70:2:{USSR}"),           # two LAV-25s against two BTR-70s, driving at each other
    "apc-vs-squad": ("squad:1:{US}", "btr70:2:{USSR}"),       # two BTR-70s attack a US rifle squad (9 men, 2 light anti-tank rockets)
    "tank-duel": ("m1a1:1:{US}", "t72:1:{USSR}"),             # Abrams against T-72 (Workshop mods)
    "ifv-vs-squad": ("squad:1:{US}", "bmp1:2:{USSR}"),        # two BMP-1s attack a US rifle squad (Workshop mods)
    # Storm (Martin, 23 Oct: "NATO: tank + infantry group + APC - the APC carries the infantry to the enemy infantry and APC
    # group; they disembark and storm"): an Abrams in overwatch and a LAV-25 with a US rifle squad aboard against a Soviet
    # rifle squad defending its point (AT, assistant AT, light AT) and a BTR-70 beside it.
    "storm": ("m1a1:1:{US}:overwatch+lav25:1:{US2}:carry", "squad:1:{USSR}:defend+btr70:1:{USSR2}:hold"),
}
WORKSHOP = {"t72", "m1a1", "bmp1", "bradley"}
VARIANTS = {
    # name: (extra command line, Workshop mods)
    "raw": ("-zcrNoUnjam -zcrNoEarlyUnjam -zcrNoOncoming -zcrNoTraffic -zcrCrewsLeave", ""),   # the game's AI alone
    "default": ("", ""),                                                         # our mod as it is now
    "reloadfix": ("", "72DB162D129C40D9"),                                       # ours + the AI Turret Reload Fix mod
    "spotfar": ("-zcrCrewPerception 3", ""),                                     # ours, crews recognise what they see 3x faster
}


def run(scenario: str, variant: str, minutes: float, units: int, port: int) -> dict:
    us, ussr = SCENARIOS[scenario]
    extra, mods = VARIANTS[variant]
    spec = f"{us.format(**POINTS)};{ussr.format(**POINTS)}"
    label = f"guntest-{scenario}-{variant}-p{port}"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", "arland-test", "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "none", "--ussr", "none",
            "--extra", f"-aicfOff -zcrLabWeather -zcrNoFIA -zcrArmourVanilla -zcrNoArmour -zcrGunTest {spec} {extra}".strip()]
    if mods:
        argv += ["--mods", mods]
    if any(g.split(":")[0] in WORKSHOP for k in (us, ussr) for g in k.split("+")):
        argv += ["--armour"]
    subprocess.run(argv, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"scenario": scenario, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], scenario, variant)


def summarize(run_dir: Path, scenario: str, variant: str) -> dict:
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    out = {"scenario": scenario, "variant": variant}
    if not log:
        out["error"] = "no log"
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    kv = lambda line: dict(re.findall(r"(\w+)=(-?[\w.]+)", line))
    spawns = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=SPAWN" in l]
    firsts = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=FIRST_SHOT" in l]
    sights = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=FIRST_SIGHT" in l]
    sight_m = [int(x["m"]) for x in sights if x.get("m", "").lstrip("-").isdigit()]
    ev = lambda name: [int(kv(l)["m"]) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and f"event={name}" in l and kv(l).get("m", "").lstrip("-").isdigit()]
    detect_m, target_m = ev("FIRST_DETECT"), ev("FIRST_TARGET")
    lost = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=LOST" in l]
    sums = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST_SUM]" in l]
    vehicles = [s for s in spawns if s.get("kind") != "squad"]
    first_m = [int(f["m"]) for f in firsts if f.get("m", "").lstrip("-").isdigit()]
    last = sums[-1] if sums else {}
    g = lambda k: int(last.get(k, 0) or 0)
    crews = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=CREW" in l]   # seated 1.5 s after the spawn
    men0 = {s: sum(int(x.get("crew", 0)) for x in crews if x.get("side") == s) for s in ("US", "USSR")}
    squads = {s: sum(1 for x in spawns if x.get("kind") == "squad" and x.get("side") == s) for s in ("US", "USSR")}   # 9 men each
    squad = {s: squads[s] > 0 for s in ("US", "USSR")}
    riders = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=RIDERS" in l]
    dismounts = [kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=DISMOUNT" in l]
    taken = {x.get("side"): int(x.get("t", 0)) for x in (kv(l) for l in text.splitlines() if "[ZCR][GUNTEST]" in l and "event=TAKEN" in l)}
    riders_n = {s: sum(int(x.get("men", 0)) for x in riders if x.get("side") == s) for s in ("US", "USSR")}
    men_start = {s: 9 * squads[s] + men0[s] + riders_n[s] for s in ("US", "USSR")}
    men_lost = {s: max(0, men_start[s] - g(f"{s.lower()}_men")) for s in ("US", "USSR")}
    units_lost = {s: sum(1 for x in lost if x.get("side") == s) for s in ("US", "USSR")}
    # The attacker is the side with vehicles; in a duel both are.
    out.update({
        "vehicles": len(vehicles), "fired": len(firsts),
        "fired_pct": round(100 * len(firsts) / len(vehicles)) if vehicles else 0,
        "first_m": round(statistics.median(first_m)) if first_m else 0,
        "sight_m": round(statistics.median(sight_m)) if sight_m else 0,   # how far apart when they could first see each other
        "detect_m": round(statistics.median(detect_m)) if detect_m else 0,   # when a crewman's perception first listed an enemy
        "target_m": round(statistics.median(target_m)) if target_m else 0,   # when a crewman's combat AI first picked one
        "rounds": g("us_shots") + g("ussr_shots"), "us_rounds": g("us_shots"), "ussr_rounds": g("ussr_shots"),
        "us_units_lost": units_lost["US"], "ussr_units_lost": units_lost["USSR"],
        "us_men_lost": men_lost["US"], "ussr_men_lost": men_lost["USSR"],
        "squad_men_lost": men_lost["US"] if squad["US"] else (men_lost["USSR"] if squad["USSR"] else None),
        "vehicles_lost": sum(1 for x in lost if x.get("kind") != "squad"),
        "loss_lines": text.count("[ZCR][LOSS]"), "turret_kills": len(re.findall(r"\[ZCR\]\[LOSS\].* turret=", text)),
        "empty_turrets": text.count("[ZCR][VEHGUNS_EMPTY]"),
        "riders": sum(riders_n.values()),
        "dismount_m": round(statistics.median([int(x["m"]) for x in dismounts])) if dismounts else 0,       # to the objective
        "dismount_enemy_m": round(statistics.median([int(x["enemy_m"]) for x in dismounts if x.get("enemy_m", "").isdigit()])) if dismounts else 0,
        "taken_us_s": taken.get("US", 0), "taken_ussr_s": taken.get("USSR", 0), "taken": int(bool(taken)),
        "minutes": round(int(last.get("t", 0) or 0) / 60, 1),
        "script_errors": len([l for l in text.splitlines() if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l]),
        "crashed": bool(list(log.parent.glob("*.mdmp"))), "run": run_dir.name,
    })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="+", choices=sorted(SCENARIOS))
    ap.add_argument("--variant", default="default", choices=sorted(VARIANTS))
    ap.add_argument("--minutes", type=float, default=8)
    ap.add_argument("--port", type=int, default=2148)
    a = ap.parse_args()
    for s in a.scenarios:
        print(json.dumps(run(s, a.variant, a.minutes, 0, a.port)), flush=True)


if __name__ == "__main__":
    main()
