"""Zeus Commander's attack doctrine (Arma 3, fn_aiTick.sqf section 5) at the strategist level:
instead of squads trickling to a target one by one, a side picks an objective, gathers its force
at its own base nearest to it, and only then goes in - all through the plan's priorities and
demands, which steer AI Conflict's commander.

Phases per side (kept between rounds; a new match resets them):
  pick     choose the objective: our rules doctrine, or the LLM (llm-phased) - the only round the
           model is asked, so the LLM is called a few times a match, not every 90 s
  gather   the staging base (ours, nearest the objective) is the main effort and holds; the
           objective is avoided so nobody walks in alone. Go when the force within 600 m of the
           staging base reaches the need (2.5 squads, +1 squad per failed attempt here), or 60% of
           it after 5 min, or whatever is there after 10 min
  assault  the objective is the main effort with a heavy demand. Taken: the next objective, and
           straight on if the force is still there (momentum). Bled out (under 35% of the need
           sent to it after 6 min): back to gather, with a bigger need. No capture after 10 min
           (Arma 3: an assault that stops gaining is called off): the objective counts a failure
           and another one is picked - untried objectives first
Our own threatened bases are always held. In the assault, while none of them is threatened, two of
AI Conflict's DEFEND squads join it (commit): Arma 3's doctrine keeps a minimal garrison. After 4 min
of the assault with the force there, it storms: the squads sent there go in without stopping to
fight at range (Reforger groups under fire otherwise hold 300-600 m out).
"""
import math

import doctrine
from plan import bases_by_id, own_bases

NEED = 25.0          # soldiers: two and a half full squads
NEED_PER_FAIL = 10.0
GATHER_RADIUS = 600
ASSAULT_RADIUS = 900   # squads sent to the objective, on their way in (force_at)
ASSAULT_MAX = 600      # s without a capture: called off, another objective...
ASSAULT_MAX_ON_IT = 900   # ...unless we hold ground on it (ON_IT soldiers within 250 m): until then
ON_IT = 10.0
COMMIT = 2             # DEFEND squads that join the assault while none of our bases is threatened
STORM_AFTER = 240      # s into the assault, with STORM_FORCE of the need sent there: storm it
STORM_FORCE = 0.6


def _dist(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["z"] - b["z"])


def force_near(report: dict, at: dict, radius: float) -> float:
    return float(sum(s.get("alive", 0) for s in report.get("squads", [])
                     if "x" in s and math.hypot(s["x"] - at["x"], s["z"] - at["z"]) <= radius))


def capture_point(base: dict) -> dict:
    """Where AI Conflict sends attackers: the base's capture point when the report has it."""
    return {"x": base.get("cx", base["x"]), "z": base.get("cz", base["z"])}


def force_at(report: dict, target: dict, radius: float = 900) -> float:
    """Soldiers attacking the objective: squads AI Conflict has sent there (their target) and within
    the radius - it stages them 400-500 m out before going in - plus anyone within 250 m of it.
    Squads at a staging base nearby with other orders don't count (Arland's USSR main base is
    430 m from Airport Base)."""
    total = 0.0
    for s in report.get("squads", []):
        if "x" not in s:
            continue
        d = math.hypot(s["x"] - target["x"], s["z"] - target["z"])
        if (s.get("target") == target["id"] and d <= radius) or d <= 250:
            total += s.get("alive", 0)
    return total


def staging_base(report: dict, target: dict):
    own = [b for b in own_bases(report) if b["id"] != target["id"]]
    return min(own, key=lambda b: _dist(b, target)) if own else None


class Phased:
    def __init__(self, picker=None, name: str = "phased"):
        self.name = name
        self.picker = picker          # (report, doctrine_text) -> (base id or None, intent, raw)
        self.state = {}               # side ("match:faction" when the report names its match) -> dict

    def _pick(self, report: dict, text: str, avoid: set):
        """An objective we don't own and haven't failed at three times."""
        faction = report.get("faction")
        bases = bases_by_id(report)
        ok = lambda b: (b is not None and b in bases and b not in avoid and bases[b].get("owner") != faction
                        and bases[b].get("attackable", True))
        raw = ""
        if self.picker:
            try:
                target, intent, raw = self.picker(report, text)
                if ok(target):
                    return target, intent, raw
            except Exception as e:   # the model failed: our rules pick
                raw = f"picker failed: {type(e).__name__}: {e}"
        rules = dict(report)
        rules["bases"] = [b for b in report.get("bases", []) if b["id"] not in avoid]
        target = doctrine.decide(rules).get("main_effort")
        return (target if ok(target) else None), "", raw

    def decide(self, report: dict, doctrine_text: str = "") -> tuple:
        faction = report.get("faction")
        t = report.get("t", 0)
        # One bridge serves the watched and the headless match at once: memory per match and side.
        key = f"{report['match']}:{faction}" if report.get("match") else faction
        st = self.state.get(key)
        if st is None or t < st.get("last_t", 0):
            st = {"phase": "pick", "fails": {}, "since": t}
            self.state[key] = st
        st["last_t"] = t
        bases = bases_by_id(report)
        raw = ""
        hold = [b["id"] for b in own_bases(report) if b.get("threatened")]
        target = bases.get(st.get("target"))
        # The objective is ours now (on to the next one), or out of reach of our radio network now.
        if st["phase"] in ("gather", "assault") and target is not None and target.get("owner") != faction                 and not target.get("attackable", True):
            st.update(phase="pick", since=t, taken=None)
        if st["phase"] in ("gather", "assault") and (target is None or target.get("owner") == faction):
            taken = st["phase"] == "assault" and target is not None
            st.update(phase="pick", since=t, taken=st.get("target") if taken else None)
        if st["phase"] == "pick":
            tried = {b for b, n in st["fails"].items() if n >= 1}
            tid, intent, raw = self._pick(report, doctrine_text, tried)
            if tid is None and tried:
                # Nothing untried within reach: the failed ones again, the least failed first.
                tid, intent, raw = self._pick(report, doctrine_text, {b for b, n in st["fails"].items() if n >= 3})
            if tid is None or tid not in bases:
                return {"intent": f"{faction}: nothing within reach - hold", "main_effort": None, "supporting": [],
                        "hold": hold[:3], "avoid": [], "concentration": "normal"}, raw
            target = bases[tid]
            stage = staging_base(report, target)
            need = NEED + NEED_PER_FAIL * st["fails"].get(tid, 0)
            st.update(target=tid, stage=stage["id"] if stage else None, need=need, since=t, llm_intent=intent)
            # Momentum: the force that just took a base is still together near the new objective.
            here = force_near(report, target, 1500)
            st["phase"] = "assault" if st.get("taken") is not None and here >= 0.6 * need else "gather"
        target = bases[st["target"]]
        stage = bases.get(st.get("stage"))
        need = st["need"]
        elapsed = t - st["since"]
        name = target.get("name") or f"base {target['id']}"
        if st["phase"] == "gather":
            have = force_near(report, stage, GATHER_RADIUS) if stage else need
            if have >= need or (elapsed >= 300 and have >= 0.6 * need) or elapsed >= 600 or stage is None:
                st.update(phase="assault", since=t)
                elapsed = 0
            else:
                sname = stage.get("name") or f"base {stage['id']}"
                return {"intent": f"Gathering at {sname} for the attack on {name}: {have:.0f} of {need:.0f} soldiers there",
                        "main_effort": stage["id"], "supporting": [], "hold": [stage["id"], *[h for h in hold if h != stage["id"]]][:3],
                        "avoid": [target["id"]], "concentration": "heavy"}, raw
        # Assault.
        near = force_at(report, target, ASSAULT_RADIUS)
        # Arma 3 calls an assault off when it stops gaining ground: here, no capture in 10 min and
        # nobody on the objective - with soldiers on it, a capture takes 5-10 min more, so 15 min;
        # never while the base is being seized.
        on_it = force_near(report, capture_point(target), 150 if "cx" in target else 250) >= ON_IT
        stalled = not target.get("seizing") and (
            elapsed >= ASSAULT_MAX_ON_IT or (elapsed >= ASSAULT_MAX and not on_it))
        if (elapsed >= 360 and near < 0.35 * need) or stalled:
            st["fails"][target["id"]] = st["fails"].get(target["id"], 0) + 1
            st.update(phase="pick" if stalled else "gather", since=t, need=need + NEED_PER_FAIL)
            if st["phase"] == "pick":
                return self.decide(report, doctrine_text)
            return {"intent": f"The attack on {name} bled out - falling back to gather more", "main_effort": stage["id"] if stage else None,
                    "supporting": [], "hold": hold[:3], "avoid": [target["id"]], "concentration": "heavy"}, raw
        intent = st.get("llm_intent") or ""
        # Defenders go back only when a base of ours is being taken (seizing) - "threatened" also
        # means a few enemies near it, which flipped the commit every round or two.
        own = own_bases(report)
        seized = any(b.get("seizing") for b in own) if any("seizing" in b for b in own) else bool(hold)
        commit = 0 if seized else COMMIT
        storm = elapsed >= STORM_AFTER and near >= STORM_FORCE * need
        verb = "Storming" if storm else "Assault on"
        lead = f"{verb} {name} with {near:.0f} soldiers on it" + (f", {commit} defender squads committed" if commit else "")
        return {"intent": f"{lead}. {intent}" if intent else lead, "main_effort": target["id"], "supporting": [],
                "hold": hold[:3], "avoid": [], "concentration": "heavy", "commit": commit,
                "storm": target["id"] if storm else None}, raw
