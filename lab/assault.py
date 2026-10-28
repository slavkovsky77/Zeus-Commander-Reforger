"""The assault sub-lab's generals (28 Oct, Martin: "why teams were not set off, can we analyse ... maybe some sublabs for
the tests?"; review note 433). In the watched match the Soviets declared an assault on Military Training Area twice and no
one arrived: of 12 attack teams only 2 were really sent there (both stuck leaving the HQ), 3 lone survivors went home, 2
guarded the HQ, 5 went to other bases. These two generals take the strategy out of the question - one side attacks one
base with everything from the first minute, the other holds it - so the sub-lab measures only whether the ordered teams
get there.

    assault  the enemy base (not an HQ) nearest our HQ that we can attack: main effort, heavy, all four defender teams
             committed, storm, the drones on it; never anything else (avoid every other enemy base)
    hold     our base the enemy's 'assault' general picks (ours, linked to a base it holds, nearest its HQ): main effort,
             hold; no attacks (avoid every enemy base), no defenders committed

Both pick the base once per match and keep it (a captured objective stays the main effort). The intent names it:
"Assault test: everything at <name> (base <id>)" - lab/assaulttest.py reads it from [ZCR][PLAN].
"""
import math


def _pick(report: dict, attacker: str):
    bases = report.get("bases", [])
    me = report.get("faction")
    by_id = {b["id"]: b for b in bases}
    hq = next((b for b in bases if b.get("hq") and b.get("owner") == attacker), None)
    if not hq:
        return None
    if me == attacker:
        cands = [b for b in bases if b.get("owner") != attacker and not b.get("hq") and b.get("attackable")]
    else:
        def touches(b):   # linked (either way) to a base the attacker holds
            return any(by_id.get(i, {}).get("owner") == attacker for i in b.get("links") or []) or \
                any(o.get("owner") == attacker and b["id"] in (o.get("links") or []) for o in bases)
        cands = [b for b in bases if b.get("owner") == me and not b.get("hq") and touches(b)]
    if not cands:
        return None
    return min(cands, key=lambda b: math.hypot(b["x"] - hq["x"], b["z"] - hq["z"]))


class _Fixed:
    attacking = True

    def __init__(self, cfg: dict | None = None):
        self.picked = {}   # "match:faction" -> base id

    def decide(self, report: dict, doctrine_text: str = "") -> tuple:
        me = report.get("faction")
        enemy = next((b.get("owner") for b in report.get("bases", []) if b.get("hq") and b.get("owner") != me), None)
        attacker = me if self.attacking else enemy
        key = f"{report.get('match')}:{me}"
        by_id = {b["id"]: b for b in report.get("bases", [])}
        if key not in self.picked:
            b = _pick(report, attacker) if attacker else None
            if b is None:
                hq = next((b["id"] for b in report.get("bases", []) if b.get("hq") and b.get("owner") == me), None)
                return {"intent": "Assault test: no objective in reach yet - hold", "main_effort": hq, "supporting": [], "hold": [],
                        "avoid": [], "concentration": "normal"}, ""
            self.picked[key] = b["id"]
        target = by_id.get(self.picked[key], {"id": self.picked[key], "name": "?"})
        others = [b["id"] for b in report.get("bases", []) if b.get("owner") not in (me, None) and b["id"] != target["id"]]
        if self.attacking:
            return {"intent": f"Assault test: everything at {target.get('name')} (base {target['id']})", "main_effort": target["id"],
                    "supporting": [], "hold": [], "avoid": others, "concentration": "heavy", "commit": 4,
                    "storm": target["id"] if target.get("owner") != me else None,
                    "drones": [target["id"]] if target.get("owner") != me else []}, ""
        return {"intent": f"Assault test: holding {target.get('name')} (base {target['id']})", "main_effort": target["id"],
                "supporting": [], "hold": [target["id"]], "avoid": others, "concentration": "heavy", "commit": 0}, ""


class Assault(_Fixed):
    name = "assault"
    attacking = True


class Hold(_Fixed):
    name = "hold"
    attacking = False


class Point:
    """The one-point sub-lab's general (28 Oct evening, Martin: "only main base and one point they will fight for ... just
    one point!"), both sides: the one neutral base at the start (-zcrOnePoint keeps it FIA's, empty) is the main effort -
    storm it, the drones on it, two defender teams along; every other base not ours avoided; once ours, hold it. The intent
    words are the assault test's, so lab/assaulttest.py's summary finds the point the same way."""
    name = "point"

    def __init__(self, cfg: dict | None = None):
        self.picked = {}

    def decide(self, report: dict, doctrine_text: str = "") -> tuple:
        me = report.get("faction")
        bases = report.get("bases", [])
        by_id = {b["id"]: b for b in bases}
        key = f"{report.get('match')}:{me}"
        if key not in self.picked:
            # The point ZCR names (every other base is neutral too since 29 Oct), else the one neutral base.
            p = next((b for b in bases if report.get("one_point") and b.get("name") == report["one_point"]), None) or \
                next((b for b in bases if not b.get("hq") and b.get("owner") not in ("US", "USSR")), None)
            if p is None:
                hq = next((b["id"] for b in bases if b.get("hq") and b.get("owner") == me), None)
                return {"intent": "Point test: no neutral point found - hold", "main_effort": hq, "supporting": [], "hold": [],
                        "avoid": [], "concentration": "normal"}, ""
            self.picked[key] = p["id"]
        target = by_id.get(self.picked[key], {"id": self.picked[key], "name": "?"})
        mine = target.get("owner") == me
        others = [b["id"] for b in bases if b["id"] != target["id"] and b.get("owner") != me]
        return {"intent": f"Assault test: everything at {target.get('name')} (base {target['id']})", "main_effort": target["id"],
                "supporting": [], "hold": [target["id"]] if mine else [], "avoid": others, "concentration": "heavy", "commit": 2,
                "storm": None if mine else target["id"], "drones": [] if mine else [target["id"]]}, ""
