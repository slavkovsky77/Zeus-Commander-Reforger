"""The strategist's decisions for the Commander Lab's Decisions tab (Martin, 25 Oct, note 399: "if we use a language model
or a visual model in decision making about supplies or planning routes, I would like to see that visualised in the
Commander Lab so I can understand better").

The bridge logs every round to .runtime/bridge/<date>.jsonl: the report the game sent (bases, squads), the model's raw
answer (or why it failed), the plan the game got. A decision here is a round where the model was asked (llm-phased:
a new objective was due) - or, with kind=all, any round whose main effort changed (our rules' picks too).

    python lab/decisions.py              # the last decisions, one line each
    python lab/decisions.py --stats      # model answers and failures per day
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / ".runtime" / "bridge"
ARLAND = {"Moss Hill", "Farm", "Beauregard", "Arleville", "Signal Hill", "Military Training Area", "Airport Base"}

_cache = {}   # file -> (mtime, rows)


def _rows(path: Path) -> list:
    st = path.stat().st_mtime
    hit = _cache.get(str(path))
    if hit and hit[0] == st:
        return hit[1]
    rows = []
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for n, line in enumerate(f):
            try:
                r = json.loads(line)
            except Exception:
                continue
            r["_id"] = f"{path.stem}:{n}"
            rows.append(r)
    _cache[str(path)] = (st, rows)
    return rows


def _files(days: int) -> list:
    return sorted(BRIDGE.glob("*.jsonl"))[-max(1, days):]


def slug(report: dict) -> str:
    names = {b.get("name") for b in report.get("bases") or []}
    return "arland" if names & ARLAND else "everon"


def _name(report: dict, base_id) -> str:
    for b in report.get("bases") or []:
        if b.get("id") == base_id:
            return b.get("name") or str(base_id)
    return "" if base_id is None else str(base_id)


def asked(r: dict) -> bool:
    return "llm" in str(r.get("provider")) and bool(r.get("raw"))


def failed(r: dict) -> str:
    raw = str(r.get("raw") or "")
    if raw.startswith("picker failed") or (asked(r) and str(r.get("source", "")).startswith("doctrine-fallback")):
        return raw[:400]
    return ""


def summary(r: dict) -> dict:
    report, plan = r.get("report") or {}, r.get("plan") or {}
    return {"id": r["_id"], "at": r.get("at"), "match": report.get("match"), "faction": r.get("faction"), "t": r.get("t"),
            "provider": r.get("provider"), "asked": asked(r), "failed": failed(r), "seconds": r.get("seconds"),
            "intent": plan.get("intent") or "", "main_effort": _name(report, plan.get("main_effort")), "map": slug(report)}


def listing(days: int = 2, kind: str = "model", limit: int = 300) -> list:
    out = []
    last = {}   # (match, faction) -> main effort
    for f in _files(days):
        for r in _rows(f):
            report, plan = r.get("report") or {}, r.get("plan") or {}
            key = (report.get("match"), r.get("faction"))
            changed = last.get(key) != plan.get("main_effort")
            last[key] = plan.get("main_effort")
            if kind == "model" and not asked(r):
                continue
            if kind == "all" and not (asked(r) or changed):
                continue
            out.append(summary(r))
    return out[-limit:][::-1]


def get(did: str) -> dict:
    day, _, n = did.partition(":")
    path = BRIDGE / f"{day}.jsonl"
    if not path.exists():
        return {"error": "no such day"}
    for r in _rows(path):
        if r["_id"] == did:
            out = summary(r)
            out.update({"report": r.get("report"), "plan": r.get("plan"), "raw": r.get("raw"), "answer": r.get("answer"),
                        "problems": r.get("problems"), "decision": r.get("decision"), "source": r.get("source")})
            return out
    return {"error": "no such decision"}


def stats(days: int = 10) -> list:
    out = []
    for f in _files(days):
        rows = [r for r in _rows(f) if asked(r)]
        bad = [r for r in rows if failed(r)]
        out.append({"day": f.stem, "asked": len(rows), "failed": len(bad), "failed_pct": round(100 * len(bad) / len(rows)) if rows else None})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--kind", default="model", choices=["model", "all"])
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats:
        for s in stats(a.days if a.days > 2 else 10):
            print(s)
        return 0
    for d in listing(a.days, a.kind)[:30]:
        print(f"{d['at']} {d['faction']:4} t={d['t']:>5} {'FAILED ' if d['failed'] else ('model  ' if d['asked'] else 'rules  ')} {d['main_effort'][:22]:22} {d['intent'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
