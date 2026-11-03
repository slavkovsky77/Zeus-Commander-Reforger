"""Losses to FPV drones, from a match's log (3 Nov, the review battle farm-review: [ZCR][LOSS] gave the US 37 losses and the
Soviets 3 kills, 15 of them 'killed by friendly AI' - the Soviet drones' hits, which the game credits to nobody (a soldier hit:
killer=none) or to a man riding in the car the drone blew up). Each loss within RADIUS_M and -1..+WINDOW_S s of an FPV
detonation ("FPVAI: droneN detonated on ... at <x y z>") goes to that drone's side ("FPVAI: droneN (...) taken over at ...
faction=XX").

  python lab/droneloss.py RUN [RUN ...]     per side: soldiers lost to drones, and whose drones
"""
import math
import re
import sys
from collections import Counter
from pathlib import Path

RUNS = Path(__file__).resolve().parents[1] / ".runtime" / "runs"
RADIUS_M = 25
WINDOW_S = 6
CLOCK = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d+)")
TAKEN = re.compile(r"FPVAI: (drone\d+) \(.*taken over at .* faction=(\w+)")
DET = re.compile(r"FPVAI: (drone\d+) detonated on .* at <(-?[\d.]+) (-?[\d.]+) (-?[\d.]+)>")
KV = re.compile(r"(\w+)=(\S+)")


def clock(line: str):
    m = CLOCK.match(line)
    if not m:
        return None
    h, mi, s, frac = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + float("0." + frac)


def losses(lines) -> list:
    """Every soldier lost, with drone=<the drone's side> when an FPV hit killed him, else drone=None."""
    side_of, dets, out = {}, [], []
    for line in lines:
        if "FPVAI: drone" in line:
            m = TAKEN.search(line)
            if m:
                side_of[m.group(1)] = m.group(2)
                continue
            m = DET.search(line)
            if m:
                c = clock(line)
                if c is not None:
                    dets.append((c, float(m.group(2)), float(m.group(4)), side_of.get(m.group(1), "?")))
        elif "[ZCR][LOSS]" in line and "kind=man" in line:
            d = dict(KV.findall(line))
            c = clock(line)
            try:
                x, z = float(d["x"]), float(d["z"])
            except (KeyError, ValueError):
                continue
            hit = next((s for t, dx, dz, s in reversed(dets) if c is not None and t - 1 <= c <= t + WINDOW_S
                        and math.hypot(dx - x, dz - z) <= RADIUS_M), None)
            out.append({"side": d.get("side"), "t": d.get("t"), "drone": hit, "relation": d.get("relation")})
    return out


def by_side(lines) -> dict:
    """{side: {"lost": n, "to_drones": n, "drone_kills": n}} - drone_kills: enemy soldiers its drones killed."""
    out = {}
    for r in losses(lines):
        v = out.setdefault(r["side"], {"lost": 0, "to_drones": 0, "drone_kills": 0})
        v["lost"] += 1
        if r["drone"] and r["drone"] != r["side"]:
            v["to_drones"] += 1
            out.setdefault(r["drone"], {"lost": 0, "to_drones": 0, "drone_kills": 0})["drone_kills"] += 1
    return out


def main() -> int:
    for name in sys.argv[1:]:
        log = next((RUNS / name / "logs").glob("*/script.log"), None)
        if not log:
            print(name, "no log")
            continue
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        rows = losses(lines)
        print(name)
        for side, v in sorted(by_side(lines).items(), key=lambda kv: str(kv[0])):
            print(f"  {side}: lost {v['lost']}, {v['to_drones']} of them to enemy drones; its drones killed {v['drone_kills']}")
        print("  game's relation for the drone losses:", Counter(r["relation"] for r in rows if r["drone"]).most_common())
    return 0


if __name__ == "__main__":
    sys.exit(main())
