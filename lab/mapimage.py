"""The map a strategist would look at for one decision (plan page M5: https://claude.ai/artifact/EAVqib8JhtDtkVxGB3KKSV;
review note 390 - Martin: "a visual LLM that could do analysis of the map based on the road network"). One situation
report (a line of a match's profile/zcr/snapshots.jsonl, what one side knows) drawn on Enfumap's tiles:

  - the 1 km grid, the bases with their owner, links, supplies (own bases), the current main effort (the base named in
    the plan's intent), the bases that can be attacked now, threats and seizures, enemies seen near a base
  - the side's own squads: size, role, the base each is heading for, riding or on foot
  - optionally (--traps) where vehicles got stuck and where depots were built (lab/maplayers.py)

Tiles come from Enfumap's public API (https://enfumap.com/developers - credited on the image) and are cached in
.runtime/enfumap/, so a map is fetched once. No model is called here. Needs Pillow (pip install pillow).

    python lab/mapimage.py .runtime/runs/<match>/profile/zcr/snapshots.jsonl            # the last report
    python lab/mapimage.py <snapshots.jsonl> --line 6 --zoom 3 --traps --out x.png
"""
import argparse
import io
import json
import math
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".runtime" / "enfumap"
OUT = ROOT / ".runtime" / "mapimages"
API = "https://enfumap.com/api/v1/maps/"
UA = {"User-Agent": "ZeusCommanderReforger-lab/1.0 (map images for a local AI test; credits Enfumap)"}
OWNER = {"US": (47, 109, 181), "USSR": (194, 59, 46), "FIA": (111, 125, 60)}
TRAP = (224, 123, 0)


def fetch(url: str) -> bytes:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:                      # the API's rate limit: wait as asked
                time.sleep(float(e.headers.get("Retry-After", "2")))
                continue
            raise
    raise RuntimeError(f"Enfumap kept refusing {url}")


def meta(slug: str) -> dict:
    f = CACHE / slug / "meta.json"
    if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
        return json.loads(f.read_text(encoding="utf-8"))
    f.parent.mkdir(parents=True, exist_ok=True)
    d = json.loads(fetch(API + slug))["data"]
    f.write_text(json.dumps(d), encoding="utf-8")
    return d


def base_map(slug: str, style: str, zoom: int) -> tuple:
    """The whole map at 'zoom' stitched from cached tiles; (image, metres per pixel, world size)."""
    m = meta(slug)
    t = m["tiles"]
    url = t["layers"].get(style, t["url"])
    zmax = (t.get("layerMaxNativeZoom") or {}).get(style, t["maxNativeZoom"])
    zoom = min(zoom, zmax)
    n, ts = 2 ** zoom, t["tileSize"]
    img = Image.new("RGB", (n * ts, n * ts), (200, 222, 230))
    version = url.split("?v=")[-1] if "?v=" in url else "0"
    for x in range(n):
        for y in range(n):
            f = CACHE / slug / style / version / str(zoom) / str(x) / f"{y}.webp"
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(fetch("https://enfumap.com" + url.replace("{z}", str(zoom)).replace("{x}", str(x)).replace("{y}", str(y))))
                time.sleep(0.03)
            img.paste(Image.open(io.BytesIO(f.read_bytes())).convert("RGB"), (x * ts, y * ts))
    return img, m["worldSize"] / (n * ts), m["worldSize"]


def font(size: int, bold: bool = False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_situation(snap: dict, slug: str, style: str = "topo", zoom: int = 3, traps: bool = False) -> Image.Image:
    img, mpp, world = base_map(slug, style, zoom)
    size = img.size[0]
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    px = lambda x, z: (x / mpp, (world - z) / mpp)          # world metres -> pixels, north up
    s = max(1.0, size / 2048)                                # scale marks with the image
    f_small, f_mid, f_big = font(int(15 * s)), font(int(18 * s), True), font(int(26 * s), True)

    # The 1 km grid.
    for k in range(0, int(world) + 1, 1000):
        a = k / mpp
        d.line([(a, 0), (a, size)], fill=(0, 0, 0, 40), width=1)
        d.line([(0, size - a), (size, size - a)], fill=(0, 0, 0, 40), width=1)
        if k < world:
            d.text((a + 4 * s, size - 22 * s), f"{k // 1000:02d}", fill=(0, 0, 0, 150), font=f_small)
            d.text((4 * s, size - a - 22 * s), f"{k // 1000:02d}", fill=(0, 0, 0, 150), font=f_small)

    if traps:
        import maplayers
        layers = maplayers.layers(slug)
        for tr in layers["traps"]:
            x, y = px(tr["x"], tr["z"])
            r = (2 + min(7, 1.2 * math.sqrt(tr["count"]))) * s
            d.ellipse([x - r, y - r, x + r, y + r], fill=TRAP + (90,), outline=TRAP + (170,))
        for b in layers["depots_built"]:
            x, y = px(b["x"], b["z"])
            r = 4 * s
            d.rectangle([x - r, y - r, x + r, y + r], outline=(40, 40, 40, 200), width=max(1, int(s)))

    bases = {b["id"]: b for b in snap["bases"]}
    side = snap["faction"]
    intent = snap.get("intent") or ""
    # The main effort: the base the plan's intent names (the longest name that appears, so "Main Operating Base" doesn't
    # hide behind a shorter one). "objective" in the report means a base that counts for victory, not the target.
    named = sorted((b for b in bases.values() if b["name"] and b["name"] in intent), key=lambda b: -len(b["name"]))
    effort = named[0]["id"] if named else None
    own = OWNER.get(side, (60, 60, 60))
    # Links between bases.
    done = set()
    for b in bases.values():
        for l in b.get("links") or []:
            o = bases.get(l)
            key = tuple(sorted((b["id"], l)))
            if not o or key in done:
                continue
            done.add(key)
            (x1, y1), (x2, y2) = px(b["x"], b["z"]), px(o["x"], o["z"])
            steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / (14 * s)))
            for i in range(0, steps, 2):
                d.line([(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps),
                        (x1 + (x2 - x1) * (i + 1) / steps, y1 + (y2 - y1) * (i + 1) / steps)], fill=(30, 30, 30, 120), width=max(1, int(2 * s)))
    # Squads: a line to the base each is heading for, then the squad.
    for q in snap.get("squads", []):
        if q.get("alive", 0) <= 0:
            continue
        x, y = px(q["x"], q["z"])
        tgt = bases.get(q.get("target"))
        if tgt:
            d.line([(x, y), px(tgt["x"], tgt["z"])], fill=own + (70,), width=max(1, int(s)))
    for q in snap.get("squads", []):
        if q.get("alive", 0) <= 0:
            continue
        x, y = px(q["x"], q["z"])
        r = (5 + q["alive"]) * s
        if q.get("ride"):
            d.rectangle([x - r, y - r * .7, x + r, y + r * .7], fill=own + (230,), outline=(255, 255, 255, 230), width=max(1, int(1.5 * s)))
        else:
            d.polygon([(x, y - r), (x + r, y + r * .8), (x - r, y + r * .8)], fill=own + (230,), outline=(255, 255, 255, 230))
        d.text((x + r + 2 * s, y - 8 * s), f"{q['alive']}", fill=(20, 20, 20, 230), font=f_small)
    # Bases on top.
    for b in bases.values():
        x, y = px(b["x"], b["z"])
        c = OWNER.get(b.get("owner"), (90, 90, 90))
        r = (16 if b.get("hq") else 12) * s
        if b["id"] == effort:
            d.ellipse([x - r - 10 * s, y - r - 10 * s, x + r + 10 * s, y + r + 10 * s], outline=(255, 200, 0, 255), width=max(3, int(5 * s)))
        elif b.get("attackable"):
            rr = r + 8 * s
            for k in range(0, 360, 30):                    # dotted ring: can be attacked now
                d.arc([x - rr, y - rr, x + rr, y + rr], k, k + 15, fill=(255, 200, 0, 230), width=max(2, int(2.5 * s)))
        if b.get("threatened") or b.get("seizing"):
            d.ellipse([x - r - 4 * s, y - r - 4 * s, x + r + 4 * s, y + r + 4 * s], outline=(220, 30, 30, 255), width=max(2, int(3 * s)))
        d.ellipse([x - r, y - r, x + r, y + r], fill=c + (235,), outline=(255, 255, 255, 255), width=max(2, int(2.5 * s)))
        label = b["name"] + (" (HQ)" if b.get("hq") else "")
        extra = []
        if b.get("owner") == side and b.get("supplies") is not None:
            extra.append(f"supplies {b['supplies']}")
        if b.get("enemies"):
            extra.append(f"{b['enemies']} enemies seen")
        if b.get("seizing"):
            extra.append("being seized")
        tx, ty = x + r + 6 * s, y - 14 * s
        for i, line in enumerate([label] + extra):
            fnt = f_mid if i == 0 else f_small
            w = d.textlength(line, font=fnt)
            d.rectangle([tx - 3 * s, ty - 1 * s, tx + w + 3 * s, ty + (22 if i == 0 else 18) * s], fill=(255, 255, 255, 200))
            d.text((tx, ty), line, fill=(15, 15, 15, 255), font=fnt)
            ty += (23 if i == 0 else 19) * s

    # Title, legend, credit.
    title = f"{slug.capitalize()} - {side} view - game minute {snap.get('t', 0) // 60} - report {snap.get('round', '?')}"
    d.rectangle([0, 0, size, (64 if intent else 40) * s], fill=(255, 255, 255, 215))
    d.text((12 * s, 6 * s), title, fill=(10, 10, 10, 255), font=f_big)
    if intent:
        d.text((12 * s, 40 * s), "Current plan: " + intent, fill=(40, 40, 40, 255), font=f_small)
    legend = ["Circle: base (blue US, red USSR, green FIA; bigger = HQ)", "Yellow ring: current main effort   Dotted: can be attacked now",
              "Red ring: threatened / being seized",
              f"Triangle: our squad on foot, box: riding; number = soldiers alive", "Dashed line: bases linked by radio; thin line: where a squad heads"]
    if traps:
        legend.append("Orange: where vehicles got stuck in past matches; small square: a depot was built there")
    lh = 20 * s
    y0 = size - (len(legend) + 2) * lh - 10 * s
    d.rectangle([size - 600 * s, y0 - 8 * s, size, size], fill=(255, 255, 255, 215))
    for i, line in enumerate(legend):
        d.text((size - 590 * s, y0 + i * lh), line, fill=(20, 20, 20, 255), font=f_small)
    d.text((size - 590 * s, y0 + (len(legend) + 0.3) * lh), "Map (c) Enfumap (enfumap.com), drawn from the game's files", fill=(60, 60, 60, 255), font=f_small)
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def slug_of(snapshots: Path) -> str:
    name = snapshots.parts[-4] if len(snapshots.parts) >= 4 else ""
    for s in ("arland", "everon"):
        if s in name:
            return s
    return "arland"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshots", type=Path)
    ap.add_argument("--line", type=int, default=-1, help="which report (0 = first, -1 = last)")
    ap.add_argument("--map", default="", help="arland or everon (default: from the run's name)")
    ap.add_argument("--style", default="topo", choices=["topo", "satellite", "drawn"])
    ap.add_argument("--zoom", type=int, default=3, help="2 = 1024 px, 3 = 2048 px")
    ap.add_argument("--traps", action="store_true", help="also where vehicles got stuck and depots were built")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    lines = a.snapshots.read_text(encoding="utf-8").splitlines()
    snap = json.loads(lines[a.line])
    slug = a.map or slug_of(a.snapshots.resolve())
    img = draw_situation(snap, slug, a.style, a.zoom, a.traps)
    out = a.out or OUT / f"{slug}-{snap.get('faction')}-r{snap.get('round')}-t{snap.get('t')}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    print(f"{out} ({img.size[0]} px)")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
