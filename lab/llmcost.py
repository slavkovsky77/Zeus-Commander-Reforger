"""What the LLM general (lab/liveplan.py) spent on model calls - today, this week and per day, by run kind (watched: a
run folder with "-watch-" in its name; headless: the rest) and by model. Read from each run's profile/zcr/liveplan.jsonl:
every call's usage as OpenRouter billed it ("usages" since 5 Nov late, else answer._usage). Never calls OpenRouter.

    python lab/llmcost.py              # today, this week (since Monday), the last 7 days
    python lab/llmcost.py --days 14    # more days
    python lab/llmcost.py --json       # the same as JSON (the lab app's Live tab shows today / this week)

Days are local (OpenRouter's activity page counts UTC days - an hour apart in winter). 5 Nov: 1,442 calls, $12.68 here;
OpenRouter showed $11.74 for its UTC day, this file's UTC sum $11.84.
"""
import argparse
import json
import re
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / ".runtime" / "runs"
STAMP = re.compile(r"(\d{8}-\d{6})$")
LOGT = re.compile(r"^(\d\d):(\d\d):(\d\d) t=(\d+) (\w+) (?:gemini \(|model failed)")

_cache = {}     # liveplan.jsonl path -> (mtime, size, [calls])
_lock = threading.Lock()


def _log_times(log: Path, start: datetime) -> dict:
    """(game second, side) -> the wall time of that model call, from liveplan.log (rows written before 'at' was logged)."""
    out = {}
    if not log.exists():
        return out
    day = datetime.combine(start.date(), datetime.min.time())
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LOGT.match(line)
        if m:
            at = day + timedelta(hours=int(m[1]), minutes=int(m[2]), seconds=int(m[3]))
            if at < start - timedelta(minutes=5):
                at += timedelta(days=1)
            out[(int(m[4]), m[5])] = at
    return out


def _calls(jl: Path) -> list:
    """Every model call of one run: {at, kind, model, cost, run}. A growing file (the battle being played) is read on from
    where the last look stopped."""
    st = jl.stat()
    with _lock:
        hit = _cache.get(jl)
    if hit and hit["size"] == st.st_size:
        return hit["calls"]
    run = jl.parent.parent.parent
    m = STAMP.search(run.name)
    start = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S") if m else datetime.fromtimestamp(st.st_mtime)
    kind = "watched" if "-watch-" in run.name else "headless"
    grow = hit is not None and st.st_size > hit["size"]
    times = None
    model0 = hit["model0"] if grow else ""
    out = list(hit["calls"]) if grow else []
    with open(jl, "rb") as f:
        f.seek(hit["offset"] if grow else 0)
        data = f.read()
    whole = data.rfind(b"\n") + 1        # only whole lines; a half-written last one waits for the next look
    offset = (hit["offset"] if grow else 0) + whole
    for line in data[:whole].decode("utf-8", errors="replace").splitlines():
        if '"event": "side"' in line:
            try:
                model0 = json.loads(line).get("model") or model0
            except ValueError:
                pass
            continue
        if '"usages"' not in line and '"_usage"' not in line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if "usages" in r:
            usages = [u for u in r["usages"] if isinstance(u, dict)]
        else:
            u = (r.get("answer") or {}).get("_usage") if isinstance(r.get("answer"), dict) else None
            usages = [u] if isinstance(u, dict) else []
        if not usages:
            continue
        if r.get("at"):
            at = datetime.fromtimestamp(r["at"])
        else:
            if times is None:
                times = _log_times(jl.parent / "liveplan.log", start)
            at = times.get((r.get("t"), r.get("side"))) or start + timedelta(seconds=r.get("t", 0))
        out.append({"at": at, "kind": kind, "model": r.get("model") or model0 or "?", "run": run.name,
                    "cost": sum(float(u.get("cost") or 0) for u in usages), "n": len(usages)})
    with _lock:
        _cache[jl] = {"size": st.st_size, "offset": offset, "calls": out, "model0": model0}
    return out


def all_calls(since: datetime) -> list:
    out = []
    for jl in RUNS.glob("*/profile/zcr/liveplan.jsonl"):
        try:
            if datetime.fromtimestamp(jl.stat().st_mtime) < since:
                continue
            out += [c for c in _calls(jl) if c["at"] >= since]
        except OSError:
            continue
    return out


def _sum(calls: list) -> dict:
    out = {"cost": 0.0, "calls": 0, "by_kind": {}, "by_model": {}}
    for c in calls:
        out["cost"] += c["cost"]
        out["calls"] += c["n"]
        for key, name in (("by_kind", c["kind"]), ("by_model", c["model"])):
            d = out[key].setdefault(name, {"cost": 0.0, "calls": 0})
            d["cost"] += c["cost"]
            d["calls"] += c["n"]
    out["cost"] = round(out["cost"], 3)
    for key in ("by_kind", "by_model"):
        for d in out[key].values():
            d["cost"] = round(d["cost"], 3)
    return out


def summary(days: int = 7, now: datetime = None) -> dict:
    """Today, this week (since Monday 00:00) and each of the last `days` days, in dollars as OpenRouter billed them."""
    now = now or datetime.now()
    today = datetime.combine(now.date(), datetime.min.time())
    monday = today - timedelta(days=today.weekday())
    first = min(monday, today - timedelta(days=days - 1))
    calls = all_calls(first)
    out = {"today": _sum([c for c in calls if c["at"] >= today]), "week": _sum([c for c in calls if c["at"] >= monday]),
           "week_from": monday.strftime("%Y-%m-%d"), "days": [], "at": now.strftime("%Y-%m-%dT%H:%M:%S")}
    for k in range(days):
        d0 = today - timedelta(days=k)
        s = _sum([c for c in calls if d0 <= c["at"] < d0 + timedelta(days=1)])
        out["days"].append({"day": d0.strftime("%Y-%m-%d"), **s})
    return out


def _line(name: str, s: dict) -> str:
    kinds = ", ".join(f"{k} ${v['cost']:.2f} ({v['calls']})" for k, v in sorted(s["by_kind"].items()))
    per = f", {100 * s['cost'] / s['calls']:.2f} c a call" if s["calls"] else ""
    return f"{name:12} ${s['cost']:6.2f}  {s['calls']:5} calls{per}" + (f"  -  {kinds}" if kinds else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = summary(a.days)
    if a.json:
        print(json.dumps(s, indent=1))
        return 0
    print(_line("today", s["today"]))
    print(_line(f"week {s['week_from'][5:]}+", s["week"]))
    models = s["week"]["by_model"]
    if len(models) > 1 or any(m != "google/gemini-3.8-flash" for m in models):
        for m, v in sorted(models.items(), key=lambda kv: -kv[1]["cost"]):
            print(f"  {m:40} ${v['cost']:.2f} ({v['calls']} calls)")
    print()
    for d in s["days"]:
        print(_line(d["day"], d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
