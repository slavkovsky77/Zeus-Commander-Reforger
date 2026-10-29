"""The model picks one of the attack plans (29 Oct night - Martin gave the go for model calls, review note 449; the split
agreed on 24 Oct for supply routes and building spots, note 394/396: the algorithm computes the candidates exactly, the
model chooses between them with reasons; the algorithm's own pick stays the fallback).

For each HQ: the overview image of its plans (lab/attackdraw.py) and each plan's numbers go to the model of the bridge
config (lab/bridge.local.json, OpenRouter - Gemini Flash); the answer is {"pick", "reason", "risks", "change"}.
Written to .runtime/attack/<name>_picks.json next to the algorithm's pick.

    python lab/attackpick.py farm
"""
import base64
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import providers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".runtime" / "attack"

SYSTEM = ("You are the commander of one side in an Arma Reforger match (a military game). You plan an infantry assault on one "
          "objective. An algorithm has computed 2-3 candidate plans from the map exactly; you choose one. Judge them as a "
          "soldier would: approach through ground the objective cannot see, cover and concealment on the way in, where the "
          "teams get out of the vehicles, whether the support position can fire onto the objective, how exposed the drive "
          "is, enemy drones (teams must be able to hide under a roof or trees), and how long it takes. Answer with JSON only: "
          '{"pick": "A", "reason": "...", "risks": "...", "change": "one change you would make to the picked plan, or none"}.')


def plan_text(hq: dict) -> str:
    rows = []
    for p in hq["plans"]:
        lane = p["lanes"][0]
        sup = p.get("support")
        rows.append(
            f"Plan {p['id']}: from the {p['approach']} ({p['approach_deg']} deg). Drive {p['drive']['length_m']} m from the HQ "
            f"({p['drive']['road_points_seen_by_objective']} road points in the objective's view), about {p['minutes']['drive']} min. "
            f"Assembly (get out) {p['assembly']['from_objective_m']} m from the objective, hidden from it. Three lanes, the main one "
            f"{lane['length_m']} m ({p['minutes']['walk']} min on foot), {lane['seen_pct']}% of it in the objective's view, a roof or "
            f"trees within 40 m on {lane['cover_within_40m_pct']}% of its waypoints; the other lanes "
            + ", ".join(f"{l['length_m']} m / {l['seen_pct']}% in view" for l in p["lanes"][1:]) + ". "
            + (f"Support position {sup['height_over_objective_m']} m above the objective, {sup['sees']}/9 view of it, "
               f"{'in cover' if sup['cover'] else 'in the open'}." if sup else "No support position found.")
            + f" Pull-off spots on the drive: {len(p['pulloffs'])}. Algorithm score {p['score']} (lower is better).")
    return "\n".join(rows)


def ask(llm, image: Path, text: str) -> dict:
    img = Image.open(image).convert("RGB")
    img.thumbnail((1400, 1400))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    t0 = time.time()
    r = providers._post("https://openrouter.ai/api/v1/chat/completions",
                        {"model": llm.model, "temperature": 0.3, "max_tokens": 3000, "response_format": {"type": "json_object"},
                         "messages": [{"role": "system", "content": SYSTEM},
                                      {"role": "user", "content": [{"type": "text", "text": text},
                                                                   {"type": "image_url", "image_url": {"url": url}}]}]},
                        {"authorization": f"Bearer {llm.key}", "x-title": "Zeus Commander Reforger"}, 120)
    if "error" in r:
        raise RuntimeError(f"openrouter: {r['error']}")
    content = r["choices"][0]["message"].get("content") or ""
    out = providers.extract_json(content)
    out["seconds"] = round(time.time() - t0, 1)
    out["usage"] = r.get("usage")
    return out


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "farm"
    cfg = json.loads((ROOT / "lab" / "bridge.local.json").read_text(encoding="utf-8"))
    llm = providers.OpenRouter(cfg)
    plans = json.loads((OUT / f"{name}_plans.json").read_text(encoding="utf-8"))
    picks = {"model": llm.model, "objective": plans["objective"]["name"], "hqs": []}
    for i, hq in enumerate(plans["hqs"]):
        text = (f"Objective: {plans['objective']['name'].title()} (a neutral base; the enemy will try to take and hold it too). "
                f"Your HQ is {hq['from_objective_m']} m away (the black square on the map). You have 7 assault teams of 4 and "
                f"FPV drones; the enemy has drones too.\n\nThe map: red shading is ground the objective sees; each plan's dashed "
                f"line is its drive, the circle its assembly point, arrows its three lanes, the black bars its hold line, the "
                f"triangle its support position, green dots hiding spots.\n\n" + plan_text(hq))
        try:
            ans = ask(llm, OUT / f"{name}_hq{i + 1}.png", text)
        except Exception as e:   # the algorithm's pick stands
            ans = {"pick": None, "error": f"{type(e).__name__}: {e}"}
        picks["hqs"].append({"hq": [hq["x"], hq["z"]], "algorithm_pick": hq["algorithm_pick"], "model": ans, "asked": text})
        print(f"HQ {hq['x']:.0f},{hq['z']:.0f}: algorithm {hq['algorithm_pick']}, model {ans.get('pick')} - {ans.get('reason') or ans.get('error')}")
    (OUT / f"{name}_picks.json").write_text(json.dumps(picks, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
