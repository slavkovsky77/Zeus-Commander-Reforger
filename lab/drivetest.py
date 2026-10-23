"""The driving test track: a few crewed vehicles driven A -> B -> A on one stretch with a known trap, headless, for a
few minutes - a fix tried in minutes on the same stretch instead of waiting for a match to send rides through it
(22 Oct, Martin: "do a simple scenario that reproduces the issue ... to optimise it faster").

    python lab/drivetest.py mosshill                      # the game's driver with our unjam (the default build)
    python lab/drivetest.py mosshill --variant raw        # no unjam at all: the game's driver alone
    python lab/drivetest.py mosshill --variant price      # + the road price addon (roads 10x cheaper than fields)
    python lab/drivetest.py mosshill northfarm --minutes 10 --cars 6

Each run prints one line: legs driven, median and longest leg, legs still open at the end, jams, stuck spells,
failed drives, pushes and the share of moving samples off the road. Runs on its own port, idle priority (the watched
loop keeps the game window); AI Conflict's own war goes on around the track (no switch turns it off), so each track
drives the side that holds its ground.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name: (map, A, B, kind) - A and B snap to the nearest road in the game.
TRACKS = {
    # name: (map, A, B, kind, via or "", both) - A, B and the via point snap to the nearest road in the game.
    # Moss Hill: a farm lane squeezed between a supply cache and a static car wreck with brick piles (2292,1277);
    # 155 stuck/unreachable reports there on 22 Oct, rides of both sides queueing behind. USSR ground.
    "mosshill": ("arland-test", "1700,1000", "2800,1600", "uaz", "2292,1277", False),
    # The same stretch with the Conflict bases in place (Moss Hill's supply cache by the lane) - the trap catches here.
    "mosshill-conflict": ("arland-conflict-test", "1700,1000", "2800,1600", "uaz", "2292,1277", False),
    # Head-on: the Moss Hill route with every second car starting at B - they meet on the narrow lane all the time
    # (two head-on crashes in two runs on 22 Oct, both drivers dead).
    "headon": ("arland-test", "1700,1000", "2800,1600", "uaz", "2292,1277", True),
    # Trucks through the same lane, both ways (supply trucks; Competent AI driving widens their turn radius).
    "trucks": ("arland-test", "1700,1000", "2800,1600", "ural", "2292,1277", True),
    # North farm fields: rides cut across fenced fields (2040,2980 / 2150,2880 / 2250,2970) on their way to the
    # US main base and can't find a way out (UNREACHABLE). US ground.
    "northfarm": ("arland-test", "2450,2950", "1200,3250", "m998", "", False),
    # Everon: the US main base's exit road (5350,9960, 16 m off the road by farm fences).
    "everonexit": ("everon-test", "5700,9650", "4700,9900", "m998", "", False),
}

VARIANTS = {
    # name: (extra server parameters, extra mods)
    "raw": ("-zcrNoUnjam -zcrNoEarlyUnjam -zcrNoOncoming -zcrNoTraffic", ""),  # the game's driver alone
    "default": ("", ""),                                                      # ours: push back-offs, early unjam, oncoming slow-down, spacing
    "nospacing": ("-zcrNoSpacing", ""),                                       # ours without the spacing rule
    "nooncoming": ("-zcrNoOncoming", ""),
    "late": ("-zcrNoEarlyUnjam", ""),                                         # back-offs only after 45 s
    "price": ("", "3B9F2C4D5E6A7B81"),                                        # + roads 10x cheaper than fields
    "competent": ("", "68FCF11534562F2E"),                                    # + Competent AI driving (turn radius, trucks/APCs)
    "crx": ("", "5F268647F8A1A1F4"),                                          # + CRX Enfusion A.I. (column driving, vehicle combat)
    "jmvai": ("-zcrNoUnjam -zcrNoEarlyUnjam -zcrNoOncoming -zcrNoTraffic", "6A8490E1621E7B3C,7A3C51E0D2B94F61"),   # JMVehicleAI, tuned, alone
    "best": ("", "3B9F2C4D5E6A7B81,68FCF11534562F2E"),                         # ours + road price + Competent AI driving
}


def run(track: str, variant: str, minutes: float, cars: int, port: int) -> dict:
    map_name, a, b, kind, via, both = TRACKS[track]
    extra, mods = VARIANTS[variant]
    spec = f"{a};{b};{cars};{kind};{via or '-'}" + (";both" if both else "")
    # The port in the name: two runs of the same track and setup start in the same second on the night's two ports, and
    # run folders are named label + second (23 Oct: every second run of a pair came back empty).
    label = f"drivetest-{track}-{variant}-p{port}"
    argv = [sys.executable, "-u", str(ROOT / "lab" / "reforger.py"), "--map", map_name, "--minutes", str(minutes), "--label", label,
            "--port", str(port), "--us", "none", "--ussr", "none", "--extra", f"-aicfOff -zcrLabWeather -zcrNoFIA -zcrArmourVanilla -zcrNoArmour -zcrDriveTest {spec} {extra}".strip()]
    if mods:
        argv += ["--mods", mods]
    subprocess.run(argv, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
    runs = sorted((ROOT / ".runtime" / "runs").glob(f"{label}-*"))
    if not runs:
        return {"track": track, "variant": variant, "error": "no run folder"}
    return summarize(runs[-1], track, variant)


def summarize(run_dir: Path, track: str, variant: str) -> dict:
    """One flat summary of a finished track run (also for backfilling old runs into the sub-lab)."""
    log = next(iter(sorted(run_dir.glob("logs/*/console.log"))), None)
    out = {"track": track, "variant": variant}
    if not log:
        out["error"] = "no log"
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    legs = [int(x) for x in re.findall(r"\[ZCR\]\[DRIVETEST\] .*event=ARRIVE .*leg_s=(\d+)", text)]
    legs.sort()
    last = re.findall(r"\[ZCR\]\[DRIVETEST_SUM\] .*open_legs=(\d+) oldest_open_s=(\d+)", text)
    moving = sum(int(x) for x in re.findall(r"\[ZCR\]\[OFFROAD\] .*moving=(\d+)", text))
    off = sum(int(x) for x in re.findall(r"\[ZCR\]\[OFFROAD\] .*offroad=(\d+)", text))
    out.update({
        "spawned": text.count("event=SPAWN"), "lost": text.count("event=LOST"),
        "legs": len(legs), "median_leg_s": legs[len(legs) // 2] if legs else None, "max_leg_s": legs[-1] if legs else None,
        "oldest_open_s": int(last[-1][1]) if last else None,
        "jams": text.count("[ZCR][JAM]"), "stuck": text.count("[ZCR][STUCKVEH]"), "move_fails": text.count("[ZCR][MOVEFAIL]"),
        "unreachable": len(re.findall(r"\[ZCR\]\[MOVEFAIL\] .*error=UNREACHABLE", text)), "pushes": text.count("[ZCR][PUSH]"),
        "car_hits": len([l for l in text.splitlines() if "[ZCR][COLLISION]" in l and " other=object " not in l]),
        "oncoming": len(re.findall(r"\[ZCR\]\[ONCOMING\] .* other=", text)),
        "stops": len(re.findall(r"\[ZCR\]\[SPACING\] .*band=stop", text)),
        "offroad_pct": round(100 * off / moving) if moving else None,
        "script_errors": len([l for l in text.splitlines() if re.search(r"SCRIPT +\(E\)", l) and "Leak" not in l and "[AICF]" not in l]),
        "crashed": bool(list(log.parent.glob("*.mdmp"))), "run": run_dir.name,
    })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+", choices=sorted(TRACKS))
    ap.add_argument("--variant", default="default", choices=sorted(VARIANTS))
    ap.add_argument("--minutes", type=float, default=8)
    ap.add_argument("--cars", type=int, default=6)
    ap.add_argument("--port", type=int, default=2148)
    a = ap.parse_args()
    for track in a.tracks:
        r = run(track, a.variant, a.minutes, a.cars, a.port)
        print(" ".join(f"{k}={v}" for k, v in r.items()), flush=True)


if __name__ == "__main__":
    main()
