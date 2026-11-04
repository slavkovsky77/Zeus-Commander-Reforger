"""Data for the lab app's /v2 page (4 Nov 2026 - Martin: "a lot of things I dont actually use ... lets improve user
experience with what we actually need"): the battle on the map and a one-glance summary of it for the top bar.

    live(map)   /api/v2/live?map=auto|arland|everon - the map's live layer (lab/maplayers.py live(), the same data as
                /api/map/live) for the battle being played, else the newest finished one (its last round, live=False),
                plus "battle": which battle, the point and who holds it, game time, losses per side, and per side who
                commands it (Gemini or the rules) and what it decided last, in its own words.

The losses, captures and the rules' intent come from the run's console.log (read incrementally, like the Live tab);
Gemini's decisions from profile/zcr/liveplan.log (lab/liveplan.py writes one line per answer).
"""
import json
import re
import threading
import time
from pathlib import Path

import maplayers

LOSS = re.compile(r"\[ZCR\]\[LOSS\] t=(\d+) victim=\S+ side=(\w*) kind=(\w+)")
CAPTURE = re.compile(r"\[ZCR\]\[CAPTURE\] t=(\d+) base=(.+?) from=(\w*) to=(\w*)")
SCORE = re.compile(r"\[ZCR\]\[SCORE\] t=(\d+) US=(\d+) USSR=(\d+)")
PLAN = re.compile(r"\[ZCR\]\[PLAN\] faction=(\w+) revision=\d+ source=(\S+) .*?intent=(.*)$")
# lab/liveplan.py's lines: "t=1509 USSR gemini (8.9 s, 0 problems): <reason> [strategy: fortify]",
# "t=1509 USSR round: ..., owner USSR, gemini, picture 0.3 s", "t=.. US model failed (...) - the code's pick".
LP_ANSWER = re.compile(r"t=(\d+) (\w+) gemini \(([\d.]+) s, (\d+) problems?\): (.*?)(?: \[strategy: ([\w -]+)\])?\s*$")
LP_ROUND = re.compile(r"t=(\d+) (\w+) round: .*?owner (\w+), ([\w-]+), picture")
LP_FAIL = re.compile(r"t=(\d+) (\w+) model failed \((.*?)\)")
LP_HEAD = re.compile(r"picker (\w+)(?: \(([^)]*)\))?")

_logs = {}          # run name -> what its console.log said so far (read incrementally)
_lock = threading.Lock()
_cache = {}         # map -> (at, result)


def _scan(run_name: str, log: Path) -> dict:
    """Losses, captures, the bases held and the rules' plan, from the lines added to the log since the last call."""
    with _lock:
        st = _logs.get(run_name)
        if st is None or log.stat().st_size < st["offset"]:
            st = _logs[run_name] = {"offset": 0, "lost": {"US": 0, "USSR": 0}, "veh": {"US": 0, "USSR": 0},
                                    "captures": [], "score": None, "plan": {}}
        with open(log, "rb") as f:
            f.seek(st["offset"])
            raw = f.read()
        cut = raw.rfind(b"\n") + 1
        st["offset"] += cut
        for line in raw[:cut].decode("utf-8", "replace").splitlines():
            if "[ZCR][" not in line:
                continue
            m = LOSS.search(line)
            if m:
                side, kind = m.group(2), m.group(3)
                if side in st["lost"]:
                    (st["lost"] if kind == "man" else st["veh"])[side] += 1
                continue
            m = CAPTURE.search(line)
            if m:
                st["captures"].append({"t": int(m.group(1)), "base": m.group(2), "from": m.group(3), "to": m.group(4)})
                continue
            m = SCORE.search(line)
            if m:
                st["score"] = {"US": int(m.group(2)), "USSR": int(m.group(3))}
                continue
            m = PLAN.search(line)
            if m:
                st["plan"][m.group(1)] = {"source": m.group(2), "intent": m.group(3).strip()}
        return st


def _args(run: Path) -> dict:
    try:
        return json.loads((run / "run.json").read_text(encoding="utf-8")).get("args") or {}
    except (OSError, ValueError):
        return {}


def _flag(extra: str, name: str) -> str:
    m = re.search(r"(?:^|\s)-" + name + r"\s+(\S+)", extra or "")
    return m.group(1) if m else ""


def _generals(run: Path) -> dict:
    """Per side: who commands it - Gemini (lab/liveplan.py with the model as picker) or the rules - and its last answer."""
    f = run / "profile" / "zcr" / "liveplan.log"
    if not f.exists():
        return {}
    text = f.read_text(encoding="utf-8", errors="replace")
    head = LP_HEAD.search(text[:2000])
    model = head.group(2) if head and head.group(2) else ""
    out = {}
    # Its first line says which sides it plans and who picks ("side both, picker gemini"): a side is Gemini's from the
    # start, before its first answer (the first round comes about a minute in).
    first = re.search(r"side (\w+), picker (\w+)", text[:2000])
    if first:
        for s in (("US", "USSR") if first.group(1) == "both" else (first.group(1),)):
            out[s] = {"calls": 0, "failed": 0, "source": "code" if first.group(2) == "code" else "waiting"}
    for line in text.splitlines():
        m = LP_ANSWER.search(line)
        if m:
            g = out.setdefault(m.group(2), {"calls": 0, "failed": 0})
            g.update(answer_t=int(m.group(1)), model_s=float(m.group(3)), problems=int(m.group(4)), reason=m.group(5).strip(),
                     stance=(m.group(6) or "").strip())
            g["calls"] += 1
            continue
        m = LP_ROUND.search(line)
        if m:
            g = out.setdefault(m.group(2), {"calls": 0, "failed": 0})
            g.update(round_t=int(m.group(1)), owner=m.group(3), source=m.group(4))
            continue
        m = LP_FAIL.search(line)
        if m:
            g = out.setdefault(m.group(2), {"calls": 0, "failed": 0})
            g["failed"] += 1
            g["fail_t"], g["fail"] = int(m.group(1)), m.group(3)[:160]
    for g in out.values():
        # "code": the side plans by the rules alone; "gemini" / "kept" / "code-fallback": the model is its picker.
        g["by"] = "rules" if g.get("source") == "code" and not g["calls"] else "Gemini"
        g["model"] = model
    return out


def battle(run: Path, d: dict) -> dict:
    """The top bar's battle: which, the point and its owner, game time, losses, each side's general and its last decision."""
    args = _args(run)
    extra = args.get("extra") or ""
    logs = sorted(run.glob("logs/*/console.log"))
    st = _scan(run.name, logs[-1]) if logs else {"lost": {}, "veh": {}, "captures": [], "score": None, "plan": {}}
    point = _flag(extra, "zcrOnePoint").replace("_", " ")
    owners = {b.get("name"): b.get("owner") for b in d.get("bases_now") or []}
    owner = owners.get(point) if point else None
    if point and not owner:
        caps = [c for c in st["captures"] if c["base"] == point]
        owner = caps[-1]["to"] if caps else None
    title = _flag(extra, "zcrTestTitle").replace("_", " ").strip()
    name = run.name
    m = re.search(r"-(\d{8})-(\d{6})$", name)
    started = f"{m.group(2)[:2]}:{m.group(2)[2:4]}" if m else ""
    if not title:
        title = re.sub(r"-(p\d+-)?\d{8}-\d{6}$", "", name).replace("-", " ")
    t = d.get("t") or 0
    gens = _generals(run)
    sides = {}
    for s in ("US", "USSR"):
        g = dict(gens.get(s) or {})
        plan = st["plan"].get(s) or {}
        if not g:
            # No live general on this side: the strategist's doctrine decides (its intent from [ZCR][PLAN]); a model behind
            # the bridge says so in its source.
            src = plan.get("source", "")
            g = {"by": "Gemini" if re.search(r"model|llm|gemini|bridge", src, re.I) else "rules", "doctrine": src}
        if g.get("by") == "Gemini" and not g.get("reason"):
            g["intent"] = f"no answer yet - the last call failed: {g.get('fail', '')}" if g.get("failed") else "waiting for its first answer"
        elif not g.get("reason"):
            g.setdefault("intent", plan.get("intent", ""))
        if g.get("answer_t") is not None:
            g["ago_s"] = max(0, t - g["answer_t"])
        efforts = (d.get("efforts") or {}).get(s) or {}
        if efforts.get("main"):
            main = next((a for a in efforts.get("attack") or [] if a.get("base") == efforts["main"]), None)
            g["main"] = {"base": efforts["main"], "teams": (main or {}).get("teams"), "men": (main or {}).get("men"),
                         "there": (main or {}).get("there")}
        sides[s] = g
    log_at = logs[-1].stat().st_mtime if logs else 0
    return {"run": name, "live": bool(d.get("live")), "title": title, "watched": watched(name), "started": started,
            "ended_at": None if d.get("live") else time.strftime("%H:%M", time.localtime(log_at)),
            "ended_ago_min": None if d.get("live") else round((time.time() - log_at) / 60),
            "t": t, "length_min": args.get("minutes"), "speed": _flag(extra, "zcrSpeed") or None,
            "point": point or None, "owner": owner, "score": st["score"], "lost": st["lost"], "lost_vehicles": st["veh"],
            "captures": st["captures"][-6:], "sides": sides}


NOT_BATTLES = ("compilecheck-",)   # a compile check loads Arland for a minute and writes live rows: never the battle shown


def watched(name: str) -> bool:
    return bool(re.match(r"w\d+-", name)) or "-watch-" in name


def _runs():
    """The newest runs that may be battles, newest first, with the age of their log in seconds."""
    runs = sorted((r for r in maplayers.RUNS.iterdir() if r.is_dir() and not r.name.startswith(NOT_BATTLES)),
                  key=maplayers.run_time, reverse=True)[:40]
    out = []
    for r in runs:
        logs = sorted(r.glob("logs/*/console.log"))
        if logs:
            out.append((r, time.time() - logs[-1].stat().st_mtime))
    return out


def live(map_name: str = "auto") -> dict:
    """The battle being played (on either map for "auto") - a watched one before a headless one - else the newest finished
    one; cached 3 s live, 30 s otherwise."""
    key = map_name
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < (3 if hit[1].get("live") else 30):
        return hit[1]
    maps = ("arland", "everon") if map_name == "auto" else (map_name,)
    runs = _runs()
    found = None
    playing = sorted((r for r, age in runs if age <= 90), key=lambda r: (not watched(r.name), -maplayers.run_time(r)))
    for r in playing:
        for m in maps:
            d = maplayers.live(m, scan=40, only=r.name)
            if d.get("live"):
                found = (m, d)
                break
        if found:
            break
    if not found:
        for r, age in runs:
            for m in maps:
                d = maplayers.live(m, max_age_s=14 * 86400, scan=40, only=r.name)
                if d.get("run"):
                    found = (m, d)
                    break
            if found:
                break
    if not found:
        out = {"map": maps[0], "live": False, "battle": None}
    else:
        m, d = found
        out = {**d, "map": m}
        try:
            out["battle"] = battle(maplayers.RUNS / d["run"], d)
        except Exception as e:   # the summary must not take the map down with it
            out["battle"] = {"run": d["run"], "live": bool(d.get("live")), "error": str(e)[:160]}
    out["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _cache[key] = (time.time(), out)
    return out
