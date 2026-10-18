"""Our doctrine as plain rules, no model: the strategist the bridge falls back on, and the baseline
an LLM has to beat. Zeus Commander's operational rules on Arma 3, reduced to what a situation
report shows:

- Defend first: our own bases under threat are held (the HQ always counts).
- One main effort: the best enemy or neutral base we can reach, meaning one linked by radio to a
  base we own. Objectives are worth most; nearer to our squads is better.
- One supporting attack on the next best base, unless it sits right beside the main effort.
- Heavy concentration on an enemy HQ or objective: go in with more than they hold (2x, 3x against
  a trench line), so more squads converge.
"""
import math

from plan import own_bases


def _squad_centre(report: dict):
    pts = [(s["x"], s["z"]) for s in report.get("squads", []) if "x" in s and s.get("alive", 0) > 0]
    if not pts:
        own = own_bases(report)
        pts = [(b["x"], b["z"]) for b in own] or [(0.0, 0.0)]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def reachable_targets(report: dict) -> list:
    """Bases we don't own that are linked (either way) to a base we do own."""
    faction = report.get("faction")
    bases = report.get("bases", [])
    ours = {b["id"] for b in bases if b.get("owner") == faction}
    out = []
    for b in bases:
        if b["id"] in ours:
            continue
        linked = any(n in ours for n in b.get("links", [])) or any(
            b["id"] in o.get("links", []) for o in bases if o["id"] in ours)
        if linked:
            out.append(b)
    return out


def decide(report: dict) -> dict:
    faction = report.get("faction")
    cx, cz = _squad_centre(report)
    hold = [b["id"] for b in own_bases(report) if b.get("threatened")]
    hold += [b["id"] for b in own_bases(report) if b.get("hq") and b["id"] not in hold]

    def score(b):
        value = 60 if b.get("objective") else 15
        if b.get("hq"):
            value += 20
        if not b.get("owner"):
            value += 10   # nobody holds it: cheap ground
        return value - 0.015 * math.hypot(b["x"] - cx, b["z"] - cz)

    targets = sorted(reachable_targets(report), key=score, reverse=True)
    if not targets:
        return {"intent": f"{faction}: no base within reach - hold and rebuild", "main_effort": None,
                "supporting": [], "hold": hold[:3], "avoid": [], "concentration": "normal"}
    main = targets[0]
    support = [b["id"] for b in targets[1:]
               if math.hypot(b["x"] - main["x"], b["z"] - main["z"]) > 600][:1]
    heavy = bool(main.get("hq") or (main.get("objective") and main.get("owner")))
    name = main.get("name") or f"base {main['id']}"
    intent = f"Main effort on {name}" + (" with everything we have" if heavy else "")
    if support:
        intent += f", supporting attack on {next(b.get('name') or b['id'] for b in targets if b['id'] == support[0])}"
    if hold:
        intent += f", hold {len(hold)} of our bases"
    return {"intent": intent, "main_effort": main["id"], "supporting": support, "hold": hold[:3],
            "avoid": [], "concentration": "heavy" if heavy else "normal"}
