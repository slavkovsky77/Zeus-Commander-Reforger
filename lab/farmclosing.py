"""lab/farmclosing.py RUN_DIR_OR_RESULT_JSON ... - Attack teams on foot: per 60 game seconds, metres moved, metres closed on Farm, % standing still - by distance band."""
import re, sys, math, json
from collections import defaultdict
from pathlib import Path
FARM = (2209, 2909)
for arg in sys.argv[1:]:
    p = Path(arg)
    if p.suffix == ".json":
        t = p.read_text(); i = t.rfind('{\n "scenario"'); p = Path(json.loads(t[i:])["run_path"])
    L = next(p.glob("logs/*/script.log"))
    pos = defaultdict(list)
    for l in open(L, encoding="utf-8", errors="replace"):
        if "[ZCR][LIVE]" not in l or "kind=team" not in l or "role=ATTACK" not in l: continue
        d = dict(re.findall(r"(\w+)=(\S+)", l))
        pos[(d["side"], d["id"])].append((int(d["t"]), float(d["x"]), float(d["z"]), d.get("ride") == "1", int(d["men"])))
    bands = defaultdict(lambda: [0, 0.0, 0.0, 0])
    for k, pts in pos.items():
        pts.sort(); i = 0
        while i < len(pts):
            j = i
            while j < len(pts) and pts[j][0] - pts[i][0] < 60: j += 1
            if j >= len(pts): break
            a, b = pts[i], pts[j]
            if not a[3] and not b[3] and a[4] > 0:
                da = math.hypot(a[1] - FARM[0], a[2] - FARM[1]); db = math.hypot(b[1] - FARM[0], b[2] - FARM[1])
                if da < 600:
                    band = "<120" if da < 120 else "120-300" if da < 300 else "300-600"
                    mv = math.hypot(b[1] - a[1], b[2] - a[2]); s = bands[(k[0], band)]
                    s[0] += 1; s[1] += mv; s[2] += da - db; s[3] += 1 if mv < 10 else 0
            i = j
    print("==", p.name)
    for (side, band), (n, mv, cl, still) in sorted(bands.items()):
        print(f"  {side:5} {band:8} {n:4} team-min  moved {mv/n:4.0f} m/min  closed {cl/n:4.0f} m/min  still {100*still//n:3}%")
