"""The attack plans of lab/attackplan.py drawn on the map, as lines of attack (Martin, 29 Oct: "I imagine having lines of
attack"): one image per HQ with its 2-3 candidate plans A/B/C - for Martin's morning page and for the model that picks one
(lab/attackpick.py).

  red shading       ground the objective sees (a crouching soldier there is in view of a defender on it)
  thin dashed line  the drive from the HQ to the plan's assembly point (a circle: the teams get out there)
  arrows            the three teams' lanes from the assembly point into the objective
  bar across lanes  the hold line: the teams wait there for each other, then go in together
  triangle + line   the support position and its line of fire onto the objective
  green dots        where a team on the lane hides from a drone (a roof or canopy); small squares: pull-offs on the drive

    python lab/attackdraw.py farm      # .runtime/attack/farm_plans.json (+ farm_scan.jsonl) -> farm_hq<N>.png
"""
import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mapimage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".runtime" / "attack"
COLOURS = {"A": (25, 110, 220), "B": (230, 120, 20), "C": (140, 60, 190)}


def draw(plans: dict, scan: Path, hq_index: int, slug: str = "arland", zoom: int = 4, only: str = "") -> Image.Image:
    hq = dict(plans["hqs"][hq_index])
    if only:
        hq["plans"] = [p for p in hq["plans"] if p["id"] == only]
    obj = plans["objective"]
    base, mpp, world = mapimage.base_map(slug, "topo", zoom)
    xs = [hq["x"], obj["x"]] + [p[0] for pl in hq["plans"] for p in pl["drive"]["points"]]
    zs = [hq["z"], obj["z"]] + [p[1] for pl in hq["plans"] for p in pl["drive"]["points"]]
    margin = 250
    x0, x1 = min(xs) - margin, max(xs) + margin
    z0, z1 = min(zs) - margin, max(zs) + margin
    px = lambda x, z: ((x - x0) / mpp, (z1 - z) / mpp)
    crop = base.crop((int(x0 / mpp), int((world - z1) / mpp), int(x1 / mpp), int((world - z0) / mpp))).convert("RGBA")
    over = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    s = max(1.0, crop.size[0] / 1400)
    f_small, f_mid, f_big = mapimage.font(int(14 * s)), mapimage.font(int(17 * s), True), mapimage.font(int(24 * s), True)

    lines = scan.read_text(encoding="utf-8").splitlines()
    step = json.loads(lines[0])["step"]
    half = step / 2 / mpp
    for l in lines[1:]:
        c = json.loads(l)
        if c["seen"] > 0:
            x, y = px(c["x"], c["z"])
            d.rectangle([x - half, y - half, x + half, y + half], fill=(220, 30, 30, 40 + 15 * c["seen"]))

    for pl in hq["plans"]:
        col = COLOURS.get(pl["id"], (40, 40, 40))
        pts = [px(x, z) for x, z in pl["drive"]["points"]]
        for i in range(0, len(pts) - 1, 2):
            d.line([pts[i], pts[i + 1]], fill=col + (200,), width=int(3 * s))
        for po in pl["pulloffs"]:
            x, y = px(po["x"], po["z"])
            d.rectangle([x - 4 * s, y - 4 * s, x + 4 * s, y + 4 * s], outline=col + (255,), width=int(2 * s))
        holds = []
        for ln in pl["lanes"]:
            wp = [px(x, z) for x, z in ln["waypoints"]]
            d.line(wp, fill=col + (235,), width=int(5 * s), joint="curve")
            if len(wp) >= 2:
                (ax, ay), (bx, by) = wp[-2], wp[-1]
                ang = math.atan2(by - ay, bx - ax)
                tip = 14 * s
                d.polygon([(bx, by), (bx - tip * math.cos(ang - 0.45), by - tip * math.sin(ang - 0.45)),
                           (bx - tip * math.cos(ang + 0.45), by - tip * math.sin(ang + 0.45))], fill=col + (255,))
            for h in ln["hiding"]:
                if h["hide"]:
                    x, y = px(*h["hide"])
                    d.ellipse([x - 4 * s, y - 4 * s, x + 4 * s, y + 4 * s], fill=(30, 160, 60, 230))
            # The hold line: a bar across the lane at its hold point.
            i = min(range(len(ln["waypoints"])), key=lambda j: math.dist(ln["waypoints"][j], ln["hold"]))
            a_, b_ = ln["waypoints"][max(0, i - 1)], ln["waypoints"][min(len(ln["waypoints"]) - 1, i + 1)]
            hx_, hy_ = px(*ln["hold"])
            ang = math.atan2(-(b_[1] - a_[1]), b_[0] - a_[0]) + math.pi / 2
            bar = 22 / mpp
            d.line([(hx_ - bar * math.cos(ang), hy_ - bar * math.sin(ang)), (hx_ + bar * math.cos(ang), hy_ + bar * math.sin(ang))],
                   fill=(20, 20, 20, 255), width=int(5 * s))
            holds.append((hx_, hy_))
        a = pl["assembly"]
        x, y = px(a["x"], a["z"])
        r = 11 * s
        d.ellipse([x - r, y - r, x + r, y + r], outline=col + (255,), width=int(4 * s), fill=(255, 255, 255, 200))
        d.text((x - 5 * s, y - 10 * s), pl["id"], fill=col + (255,), font=f_mid)
        sp = pl.get("support")
        if sp:
            sx, sy = px(sp["x"], sp["z"])
            ox, oy = px(obj["x"], obj["z"])
            d.line([(sx, sy), (ox, oy)], fill=col + (120,), width=int(2 * s))
            t = 10 * s
            d.polygon([(sx, sy - t), (sx - t, sy + t * 0.8), (sx + t, sy + t * 0.8)], fill=col + (255,), outline=(255, 255, 255, 255))

    ox, oy = px(obj["x"], obj["z"])
    star = [(ox + 18 * s * math.cos(math.pi / 2 + i * math.pi / 5) * (1 if i % 2 == 0 else 0.45),
             oy - 18 * s * math.sin(math.pi / 2 + i * math.pi / 5) * (1 if i % 2 == 0 else 0.45)) for i in range(10)]
    d.polygon(star, fill=(200, 20, 20, 255), outline=(255, 255, 255, 255))
    d.text((ox + 20 * s, oy - 14 * s), obj["name"].upper(), fill=(150, 0, 0, 255), font=f_big)
    hx, hy = px(hq["x"], hq["z"])
    d.rectangle([hx - 10 * s, hy - 10 * s, hx + 10 * s, hy + 10 * s], fill=(20, 20, 20, 255))
    d.text((hx + 14 * s, hy - 12 * s), "HQ", fill=(20, 20, 20, 255), font=f_big)

    # The legend and each plan's numbers.
    rows = [f"{pl['id']}  from the {pl['approach']}: drive {pl['drive']['length_m']} m, assembly {pl['assembly']['from_objective_m']} m out, "
            f"lane {pl['lanes'][0]['length_m']} m ({pl['lanes'][0]['seen_pct']}% in view), cover in reach {pl['lanes'][0]['cover_within_40m_pct']}%"
            for pl in hq["plans"]]
    rows += ["red: ground the objective sees  -  dashed: drive  -  circle: assembly  -  arrows: lanes",
             "black bar: hold line  -  triangle: support position  -  green: hiding spots  -  squares: pull-offs"]
    pad = 8 * s
    hgt = len(rows) * 20 * s + 2 * pad
    d.rectangle([0, 0, crop.size[0], hgt], fill=(255, 255, 255, 215))
    for i, r in enumerate(rows):
        pl = hq["plans"][i] if i < len(hq["plans"]) else None
        d.text((pad, pad + i * 20 * s), r, fill=(COLOURS.get(pl["id"]) if pl else (40, 40, 40)) + (255,), font=f_small)
    d.text((pad, crop.size[1] - 22 * s), "map: Enfumap (enfumap.com)", fill=(0, 0, 0, 160), font=f_small)
    return Image.alpha_composite(crop, over).convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--zoom", type=int, default=4)
    a = ap.parse_args()
    plans = json.loads((OUT / f"{a.name}_plans.json").read_text(encoding="utf-8"))
    for i, hq in enumerate(plans["hqs"]):
        for only in [""] + [p["id"] for p in hq["plans"]]:
            img = draw(plans, OUT / f"{a.name}_scan.jsonl", i, zoom=a.zoom, only=only)
            f = OUT / f"{a.name}_hq{i + 1}{('_' + only) if only else ''}.png"
            img.save(f)
            print(f"written {f} {img.size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
