"""The modern assault doctrine (26 Oct, Martin, review note 420: "more hit and run - modern-style combat assaults
with quick dismounts near positions, some kind of storms with heavy drone support; imagine building modern-style
Ukraine combat tactics"). A sibling of lab/phased.py (Zeus Commander's Arma 3 doctrine: gather a big force, then go
in), with the same report and plan lines, and four differences:

  drones first   the side's FPV teams surge on the objective (plan line `surge <tempo s> <max up>`, read by
                 ZCR_Drones) while the strike force gets ready, keep hitting during the strike and while it pulls
                 back - the drones prepare and cover every move, the infantry only goes in behind them
  a fast strike  no long gather: SHAPE_MIN of drone strikes, then whoever is at the staging base goes (the need is a
                 share of the side's own attack soldiers, not phased's fixed 25 - with teams of 2-6 and 50 soldiers a
                 side it was rarely met and storms stopped). The strike rides in (AI Conflict's rides on routes over
                 400 m, our covered dismount 180-450 m short) and storms at once: the squads go in without stopping
                 to trade shots at range
  hit and run    no capture within STRIKE_MAX of the force getting there (or the strike bleeds out): pull back to the
                 staging base for REGROUP while the drones keep hitting the objective, then strike again - up to
                 WAVES times, then another objective
  momentum       a base taken with the force still together: straight on to the next one, no shaping pause

Phases per side (kept between rounds, a new match resets them): pick -> shape -> strike -> (pullback -> strike)...
The plan rounds come every 90 s (-zcrPlanSeconds), so every timing here is a few rounds long.
"""
import doctrine
from phased import capture_point, force_at, force_near, force_sent, staging_base
from plan import bases_by_id, own_bases

NEED_SHARE = 0.4      # of the side's attack soldiers alive: the strike force
NEED_MIN = 6.0
NEED_MAX_SHARE = 0.7  # never more than this share (an unreachable need stalls the side)
SHAPE_MIN = 90        # s of drone strikes on the objective before the strike
SHAPE_MAX = 240       # at most: then whoever is at the staging base goes
GATHER_RADIUS = 600
STRIKE_RADIUS = 900
ARRIVED_SHARE = 0.35  # of the need near the objective: the strike force is there
STRIKE_MAX = 360      # s from the force getting there without a capture (and nobody on it): pull back
STRIKE_MAX_ON_IT = 600  # with soldiers on the objective
STRIKE_TOTAL = 720    # s from the strike order
BLED_AFTER = 240      # s into the strike, under BLED_SHARE of the need sent there: pull back
BLED_SHARE = 0.3
ON_IT = 4.0           # soldiers within the capture point's radius
REGROUP = 150         # s back at the staging base, the drones still on the objective
WAVES = 3             # strikes on one objective before another is picked
COMMIT = 4            # DEFEND teams that join the strike while none of our bases is being taken
SURGE = (40, 5)       # drone tempo (s between launches) and drones up: shaping and the strike
COVER = (60, 4)       # pulling back


def attack_soldiers(report: dict) -> float:
    return float(sum(s.get("alive", 0) for s in report.get("squads", []) if s.get("role") == "ATTACK"))


class Modern:
    def __init__(self, picker=None, name: str = "modern"):
        self.name = name
        self.picker = picker      # (report, doctrine_text) -> (base id or None, intent, raw)
        self.state = {}           # "match:faction" -> dict

    def _pick(self, report: dict, text: str, avoid: set):
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
            except Exception as e:
                raw = f"picker failed: {type(e).__name__}: {e}"
        rules = dict(report)
        rules["bases"] = [b for b in report.get("bases", []) if b["id"] not in avoid]
        target = doctrine.decide(rules).get("main_effort")
        return (target if ok(target) else None), "", raw

    def need(self, report: dict, target: dict) -> float:
        mine = attack_soldiers(report)
        need = max(NEED_MIN, NEED_SHARE * mine, 1.5 * target.get("enemies", 0) + 2)
        return min(need, max(NEED_MIN, NEED_MAX_SHARE * mine))

    def decide(self, report: dict, doctrine_text: str = "") -> tuple:
        decision, raw = self._decide(report, doctrine_text)
        decision.setdefault("motorize", False)
        return decision, raw

    def _decide(self, report: dict, doctrine_text: str = "") -> tuple:
        faction = report.get("faction")
        t = report.get("t", 0)
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
        if st["phase"] != "pick" and (target is None or target.get("owner") == faction or not target.get("attackable", True)):
            taken = st["phase"] == "strike" and target is not None and target.get("owner") == faction
            st.update(phase="pick", since=t, taken=st.get("target") if taken else None)
        if st["phase"] == "pick":
            tried = {b for b, n in st["fails"].items() if n >= 1}
            tid, intent, raw = self._pick(report, doctrine_text, tried)
            if tid is None and tried:
                tid, intent, raw = self._pick(report, doctrine_text, {b for b, n in st["fails"].items() if n >= 3})
            if tid is None or tid not in bases:
                return {"intent": f"{faction}: nothing within reach - hold", "main_effort": None, "supporting": [],
                        "hold": hold[:3], "avoid": [], "concentration": "normal"}, raw
            target = bases[tid]
            stage = staging_base(report, target)
            st.update(target=tid, stage=stage["id"] if stage else None, since=t, wave=1, llm_intent=intent, arrived=None)
            # Momentum: the force that just took a base is still together near the next one - straight in.
            momentum = st.get("taken") is not None and force_near(report, target, 1500) >= 0.5 * self.need(report, target)
            st["phase"] = "strike" if momentum else "shape"
            st["taken"] = None
        target = bases[st["target"]]
        stage = bases.get(st.get("stage"))
        need = self.need(report, target)
        elapsed = t - st["since"]
        name = target.get("name") or f"base {target['id']}"
        sname = (stage.get("name") or f"base {stage['id']}") if stage else "the line"
        others = [h for h in hold if stage is None or h != stage["id"]]
        if st["phase"] == "shape":
            have = force_near(report, stage, GATHER_RADIUS) if stage else need
            if stage is None or (elapsed >= SHAPE_MIN and have >= need) or elapsed >= SHAPE_MAX:
                st.update(phase="strike", since=t, arrived=None)
                elapsed = 0
            else:
                return {"intent": f"Drones on {name} before the strike: {have:.0f} of {need:.0f} soldiers ready at {sname}",
                        "main_effort": stage["id"], "supporting": [], "hold": [stage["id"], *others][:3],
                        "avoid": [target["id"]], "concentration": "heavy", "drones": [target["id"]], "surge": list(SURGE)}, raw
        if st["phase"] == "pullback":
            have = force_near(report, stage, GATHER_RADIUS) if stage else 0
            if elapsed >= REGROUP and (have >= 0.5 * need or elapsed >= 2 * REGROUP or stage is None):
                st.update(phase="strike", since=t, arrived=None, wave=st.get("wave", 1) + 1)
                elapsed = 0
            else:
                return {"intent": f"Pulled back from {name} to {sname} (wave {st.get('wave', 1)} of {WAVES}), the drones keep hitting it",
                        "main_effort": stage["id"] if stage else None, "supporting": [],
                        "hold": ([stage["id"]] if stage else []) + others[:2], "avoid": [target["id"]],
                        "concentration": "heavy", "drones": [target["id"]], "surge": list(COVER)}, raw
        # The strike: ride in, dismount close, storm at once with the drones on it.
        near = force_at(report, target, STRIKE_RADIUS)
        on_it = force_near(report, capture_point(target), 150 if "cx" in target else 250) >= ON_IT
        if st.get("arrived") is None and near >= ARRIVED_SHARE * need:
            st["arrived"] = t
        there = t - st["arrived"] if st.get("arrived") is not None else 0
        stalled = not target.get("seizing") and (
            elapsed >= STRIKE_TOTAL or there >= STRIKE_MAX_ON_IT or (there >= STRIKE_MAX and not on_it))
        bled = not target.get("seizing") and elapsed >= BLED_AFTER and force_sent(report, target) < BLED_SHARE * need
        if stalled or bled:
            if st.get("wave", 1) >= WAVES:
                st["fails"][target["id"]] = st["fails"].get(target["id"], 0) + 1
                st.update(phase="pick", since=t)
                return self._decide(report, doctrine_text)
            st.update(phase="pullback", since=t)
            why = "bled out" if bled else "no capture"
            return {"intent": f"Strike on {name} {why} - pulling back to {sname}, the drones keep hitting it",
                    "main_effort": stage["id"] if stage else None, "supporting": [],
                    "hold": ([stage["id"]] if stage else []) + others[:2], "avoid": [target["id"]],
                    "concentration": "heavy", "drones": [target["id"]], "surge": list(COVER)}, raw
        own = own_bases(report)
        seized = any(b.get("seizing") for b in own) if any("seizing" in b for b in own) else bool(hold)
        commit = 0 if seized else COMMIT
        lead = (f"Strike {st.get('wave', 1)} on {name}: storming with {near:.0f} soldiers and the drones on it"
                + (f", {commit} defender teams committed" if commit else ""))
        intent = st.get("llm_intent") or ""
        return {"intent": f"{lead}. {intent}" if intent else lead, "main_effort": target["id"], "supporting": [],
                "hold": hold[:3], "avoid": [], "concentration": "heavy", "commit": commit,
                "storm": target["id"], "drones": [target["id"]], "surge": list(SURGE)}, raw
