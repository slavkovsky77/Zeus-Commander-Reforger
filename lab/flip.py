"""The mass-boarding test's strategist (26 Oct, the crash bisect - note 421). The bad-matrix crash came 40 game seconds into
a match, while 5-6 rides boarded at once at the main bases, and only with the AI Conflict fork whose pads let every ride
spawn at once. This makes that moment happen again and again in one match: every plan round the side's main effort flips
between the two of its reachable bases farthest apart (an enemy base it can attack, or its own), with defenders
committed - every team gets a new long order at the same time, so every team asks for a ride at once.
"""
import math

from plan import bases_by_id, own_bases


class Flip:
    name = "flip"

    def __init__(self, cfg: dict | None = None):
        self.state = {}    # "match:faction" -> number of flips

    def decide(self, report: dict, doctrine_text: str = "") -> tuple:
        faction = report.get("faction")
        key = f"{report.get('match')}:{faction}"
        n = self.state.get(key, 0)
        self.state[key] = n + 1
        bases = [b for b in report.get("bases", []) if b.get("owner") == faction or b.get("attackable")]
        if len(bases) < 2:
            hq = next((b["id"] for b in own_bases(report) if b.get("hq")), None)
            return {"intent": "flip: fewer than two bases within reach - hold", "main_effort": hq, "supporting": [], "hold": [],
                    "avoid": [], "concentration": "normal"}, ""
        far = max(((a, b) for i, a in enumerate(bases) for b in bases[i + 1:]),
                  key=lambda p: math.hypot(p[0]["x"] - p[1]["x"], p[0]["z"] - p[1]["z"]))
        target = far[n % 2]
        other = far[(n + 1) % 2]
        d = math.hypot(target["x"] - other["x"], target["z"] - other["z"])
        return {"intent": f"flip {n}: everyone to {target.get('name')} ({d:.0f} m from {other.get('name')})",
                "main_effort": target["id"], "supporting": [], "hold": [], "avoid": [other["id"]] if other.get("owner") != faction else [],
                "concentration": "heavy", "commit": 4}, ""
