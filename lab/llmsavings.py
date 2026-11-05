"""Where the LLM general's model calls (lab/liveplan.py) go and what the opt-in savings would change - offline, from the runs'
profile/zcr/liveplan.jsonl (and console.log for the men and the known enemies of each round).

    python lab/llmsavings.py calls [--day 2026-11-05]    # calls per run kind and game minute, repeats, the savings simulated
    python lab/llmsavings.py replay [--n 24] [--budget 0.55]   # PAID: saved calls asked again - the strong model twice, cheap ones
    python lab/llmsavings.py score                      # the replayed answers: agreement per team, teams left out, invalid picks

calls: per run kind (watched: "-watch-" in the run folder's name; headless: the rest) the calls, the calls per game minute,
the timer calls (GEMINI_S) and the event ones, and how many repeated the side's previous orders for every team; then the
stretch rule (liveplan.changes over the rounds' digests) and longer intervals simulated over the same rounds, and the model
mix's share of strong calls. replay: a sample stratified over run kind, side and phase (early < 10 min, mid < 25, late)
with reasoning low; resumable (.runtime/llmsavings/replay.jsonl); stops before --budget dollars. Never prints the key.
"""
import argparse
import bisect
import json
import math
import random
import re
import sys
import time
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import liveplan as lp  # noqa: E402

RUNS = lp.ROOT / ".runtime" / "runs"
OUT = lp.ROOT / ".runtime" / "llmsavings"
STAMP = re.compile(r"(\d{8}-\d{6})$")
LOGT = re.compile(r"^(\d\d):(\d\d):(\d\d) t=(\d+) (\w+) (gemini \(|model failed)")
LIVE = re.compile(r"\[ZCR\]\[LIVE\] t=(\d+) kind=team side=(\w+) id=(\d+) role=\w+ men=(\d+)")
KNOWN = re.compile(r"\[ZCR\]\[KNOWN\] t=(\d+) side=(\w+) n=\d+ at=(\S*)")
STRONG = "google/gemini-3.8-flash"
CHEAP = [("lite35", "google/gemini-3.5-flash-lite"), ("lite31", "google/gemini-3.1-flash-lite"), ("lite25", "google/gemini-2.5-flash-lite")]
ALL = {"first", "owner", "team_gone", "team_new", "arrived", "left", "men", "losses", "enemy", "enemy_big", "site", "zone", "armour"}
DEFAULT_ON = {"first"} | {k.strip() for k in "owner,team_gone,arrived,enemy,enemy_big,site".split(",")}
VARIANTS = {
    "today (150 s)": dict(every=150, stretch=1, kinds=ALL),
    "stretch x2, every change": dict(every=150, stretch=2, kinds=ALL),
    "stretch x2, default kinds": dict(every=150, stretch=2, kinds=DEFAULT_ON),
    "stretch x2, w/o new enemy": dict(every=150, stretch=2, kinds=DEFAULT_ON - {"enemy", "enemy_big"}),
    "stretch x3, default kinds": dict(every=150, stretch=3, kinds=DEFAULT_ON),
    "every 225 s": dict(every=225, stretch=1, kinds=ALL),
    "every 300 s": dict(every=300, stretch=1, kinds=ALL),
}


# ---------------------------------------------------------------- the runs of a day
def runs_of(day: str) -> dict:
    """run folder name -> kind, for the runs with a model call on that (local) day."""
    out = {}
    for jl in RUNS.glob("*/profile/zcr/liveplan.jsonl"):
        run = jl.parent.parent.parent
        m = STAMP.search(run.name)
        if not m:
            continue
        start = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
        if not (start - timedelta(hours=6)).strftime("%Y-%m-%d") <= day <= (start + timedelta(hours=8)).strftime("%Y-%m-%d"):
            continue
        times = []
        log = jl.parent / "liveplan.log"
        if log.exists():
            d0 = datetime.combine(start.date(), datetime.min.time())
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                mm = LOGT.match(line)
                if mm:
                    at = d0 + timedelta(hours=int(mm[1]), minutes=int(mm[2]), seconds=int(mm[3]))
                    times.append(at + timedelta(days=1) if at < start - timedelta(minutes=5) else at)
        if any(t.strftime("%Y-%m-%d") == day for t in times):
            out[run.name] = "watched" if "-watch-" in run.name else "headless"
    return out


def rows_of(run: str) -> dict:
    """side -> its rounds (liveplan.jsonl rows with teams), in order."""
    out = defaultdict(list)
    for line in (RUNS / run / "profile" / "zcr" / "liveplan.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if "t" in r and "side" in r and "teams" in r:
            out[r["side"]].append(r)
    return out


def digests(run: str) -> dict:
    """side -> [(row, digest)] - liveplan.digest() rebuilt offline: the row's owner, losses, team states, danger zones, sites,
    vehicles; each team's men and the known enemies from the console log at that game second."""
    men = defaultdict(lambda: defaultdict(dict))
    known = defaultdict(list)
    logs = sorted((RUNS / run).glob("logs/*/console.log"))
    if logs:
        with open(logs[-1], encoding="utf-8", errors="replace") as f:
            for line in f:
                if "[ZCR][LIVE]" in line:
                    m = LIVE.search(line)
                    if m:
                        men[m[2]][int(m[1])][m[3]] = int(m[4])
                elif "[ZCR][KNOWN]" in line:
                    m = KNOWN.search(line)
                    if m:
                        pts = [tuple(map(float, p.split(","))) for p in m[3].split(";") if "," in p]
                        known[m[2]].append((int(m[1]), pts))
    out = {}
    for side, rs in rows_of(run).items():
        rts, kts = sorted(men[side]), [k[0] for k in known[side]]
        seq = []
        for r in rs:
            i = bisect.bisect_right(rts, r["t"] - 10) - 1
            mm = men[side][rts[i]] if i >= 0 else {}
            j = bisect.bisect_right(kts, r["t"]) - 1
            pts = known[side][j][1] if j >= 0 else []
            seq.append((r, {"t": r["t"], "owner": r["owner"], "lost": (r.get("lost") or {}).get(side, 0),
                            "teams": {tid: [st, mm.get(tid, 4)] for tid, st in (r.get("teams") or {}).items()},
                            "groups": [[round(x), round(z), w] for x, z, w in lp.observers_from(pts)],
                            "sites": len(r.get("sites") or []), "zones": [[z["x"], z["z"]] for z in r.get("zones") or []],
                            "armour": sorted(a["unit"] for a in (r.get("armour") or {}).get("units") or [])}))
        out[side] = seq
    return out


def _near(a, b, r):
    if a is None or b is None:
        return a is None and b is None
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= r


def same_order(a, b, status) -> bool:
    """Two validated orders of one team (liveplan.jsonl "orders") the same: go/wait/raid, the route side, the drop point
    (teams at the HQ), the support position or raided site."""
    if a.get("order") != b.get("order") or a.get("route") != b.get("route"):
        return False
    if status == "at_hq" and not _near(a.get("drop_xz"), b.get("drop_xz"), 150):
        return False
    return all(_near(a.get(k), b.get(k), 100) for k, o in (("support_xz", "support"), ("site_xz", "raid")) if a.get("order") == o)


def order_changes(prev, row):
    """(team orders compared, changed, go/wait changed, new teams) between a side's two model answers."""
    po, co = prev.get("orders") or {}, row.get("orders") or {}
    mine = {t: o for t, o in co.items() if str(o.get("source", "")).startswith("model")}
    st = row.get("teams") or {}
    common = [t for t in mine if t in po]
    return (len(common), sum(1 for t in common if not same_order(mine[t], po[t], st.get(t))),
            sum(1 for t in common if mine[t].get("order") != po[t].get("order")), sum(1 for t in mine if t not in po))


def want(st, d, v) -> bool:
    """Commander.want_model with a variant's interval, stretch and change kinds."""
    since = d["t"] - st["t"]
    if since >= v["every"]:
        return not (v["stretch"] > 1 and st["d"] is not None and since < v["stretch"] * v["every"]
                    and not [c for c in lp.changes(st["d"], d) if c[0] in v["kinds"]])
    if since < lp.GEMINI_MIN_S:
        return False
    return d["owner"] != st["owner"] or d["lost"] - st["lost"] >= 4


def cmd_calls(a) -> int:
    runs = runs_of(a.day)
    per = defaultdict(Counter)
    sim = defaultdict(Counter)
    for run, kind in sorted(runs.items()):
        p = per[kind]
        p["runs"] += 1
        seqs = digests(run)
        tmax = max((r["t"] for seq in seqs.values() for r, _ in seq), default=0)
        p["game_min"] += tmax / 60
        p["side_min"] += tmax / 60 * len(seqs)
        for side, seq in seqs.items():
            real = [(r, d) for r, d in seq if "model_s" in r]
            p["calls"] += len(real)
            for k, (r, d) in enumerate(real):
                if k == 0:
                    p["first"] += 1
                    continue
                pr, pd = real[k - 1]
                n, ch, och, new = order_changes(pr, r)
                p["timer" if r["t"] - pr["t"] >= lp.GEMINI_S - 5 else "event"] += 1
                p["team_orders"] += n
                p["team_changed"] += ch
                p["go_wait_changed"] += och
                p["repeat"] += not ch and not new
                if not lp.changes(pd, d):
                    p["quiet"] += 1
            for name, v in VARIANTS.items():
                for every in (0, 3):     # 0: the strong model only; 3: the mix, the strong one on events and 1 call in 3
                    st = {"t": -1e9, "owner": None, "lost": 0, "d": None}
                    cheap_run = 0
                    for r, d in seq:
                        if not r.get("teams") or all(x == "at_farm" for x in r["teams"].values()) or not want(st, d, v):
                            continue
                        strong = not every or any(c[0] in lp.STRONG_ON for c in lp.changes(st["d"], d)) or cheap_run >= every - 1
                        sim[(kind, name, every)]["calls"] += 1
                        sim[(kind, name, every)]["strong"] += strong
                        cheap_run = 0 if strong else cheap_run + 1
                        st = {"t": d["t"], "owner": d["owner"], "lost": d["lost"], "d": d}
    print(f"Model calls on {a.day} (local day):")
    for kind, p in sorted(per.items()):
        later = max(1, p["calls"] - p["first"])
        print(f"  {kind:8} {p['runs']:3} runs, {p['calls']:5} calls, {p['game_min']:6.0f} game min -> {p['calls'] / max(1, p['game_min']):.2f} calls "
              f"a game minute ({p['calls'] / max(1, p['side_min']):.2f} per side); timer {p['timer']}, events {p['event']}, first {p['first']}")
        print(f"           repeated the side's previous orders for every team: {p['repeat']}/{later} ({100 * p['repeat'] / later:.0f}%); "
              f"team orders changed call to call {p['team_changed']}/{p['team_orders']} ({100 * p['team_changed'] / max(1, p['team_orders']):.0f}%), "
              f"go/wait {100 * p['go_wait_changed'] / max(1, p['team_orders']):.1f}%; nothing changed (every kind) before {p['quiet']}")
    print("\nSimulated over the same rounds (calls; the mix: share to the strong model):")
    for kind in sorted(per):
        base = sim[(kind, "today (150 s)", 0)]["calls"] or 1
        for name in VARIANTS:
            c0, c3 = sim[(kind, name, 0)], sim[(kind, name, 3)]
            print(f"  {kind:8} {name:28} {c0['calls']:5} calls ({100 * (c0['calls'] / base - 1):+4.0f}%); "
                  f"mix 1 in 3: {100 * c3['strong'] / max(1, c3['calls']):.0f}% strong")
    return 0


# ---------------------------------------------------------------- replaying saved calls (paid)
def sample(day: str, n: int, seed: int = 5) -> list:
    cand = []
    for run, kind in sorted(runs_of(day).items()):
        zcr = RUNS / run / "profile" / "zcr"
        for side, rs in rows_of(run).items():
            for r in rs:
                img = zcr / "liveplan" / str(r.get("image", ""))
                if "model_s" in r and r.get("prompt") and img.is_file():
                    cand.append({"run": run, "kind": kind, "side": side, "t": r["t"], "image": str(img), "prompt": r["prompt"],
                                 "saved": r.get("answer"), "phase": "early" if r["t"] < 600 else ("mid" if r["t"] < 1500 else "late"),
                                 "objective": "Beauregard" if "beauregard" in run else "Farm"})
    random.Random(seed).shuffle(cand)
    picked, per_run, cells = [], Counter(), Counter()
    for c in cand:
        cell = (c["kind"], c["side"], c["phase"])
        if cells[cell] >= max(1, n // 12) or per_run[c["run"]] >= 2:
            continue
        cells[cell] += 1
        per_run[c["run"]] += 1
        picked.append(c)
    return sorted(picked, key=lambda c: (c["run"], c["t"], c["side"]))


def ask(llm, c, model):
    for k in range(5):
        try:
            ans = lp.ask_model(llm, Path(c["image"]), c["prompt"], model=model, reasoning="low")
            return {"answer": ans, "usage": ans.pop("_usage", None)}
        except urllib.error.HTTPError as e:
            if e.code == 429 and k < 4:      # rate limited: back off 5, 10, 20, 40 s
                time.sleep(5 * 2 ** k)
                continue
            return {"error": f"HTTP {e.code}", "usage": None}
        except ValueError as e:
            return {"error": f"bad JSON: {str(e)[:120]}", "usage": getattr(e, "usage", None)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:120]}", "usage": None}


def cmd_replay(a) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "replay.jsonl"
    done, spent = set(), 0.0
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["run"], r["side"], r["t"], r["name"]))
            spent += (r.get("usage") or {}).get("cost") or 0
    llm = lp.make_llm()
    for c in sample(a.day, a.n):
        lp.OBJECTIVE = c["objective"]
        for name, model in [("strong_a", STRONG), ("strong_b", STRONG)] + CHEAP:
            if (c["run"], c["side"], c["t"], name) in done:
                continue
            if spent >= a.budget:
                print(f"budget reached: ${spent:.3f}")
                return 0
            res = ask(llm, c, model)
            spent += (res.get("usage") or {}).get("cost") or 0
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps({"run": c["run"], "kind": c["kind"], "side": c["side"], "t": c["t"], "name": name, "model": model, **res}) + "\n")
            print(f"{c['kind'][:1]} {c['side']:4} t={c['t']:5} {name:9} {100 * ((res.get('usage') or {}).get('cost') or 0):.2f} c "
                  f"{res.get('error', '')} - ${spent:.3f}", flush=True)
    print(f"spent ${spent:.3f}")
    return 0


TEAM = re.compile(r"^  T(\d+): \d+ men, (fighting at Farm|in a vehicle|at the HQ, about to ride|on foot), \d+ m from Farm(?:, routes from (\S+?))?(?:;|$)")
LISTED = re.compile(r"^  ([A-Z]\w*-[A-Z]|[DPH]\d+): ")


def _orders(ans) -> dict:
    out = {}
    for e in (ans.get("teams") or []) if isinstance(ans, dict) else []:
        try:
            out[int(str(e.get("team", "")).lstrip("Tt"))] = e
        except (ValueError, AttributeError):
            continue
    return out


def _key(e, status):
    order = str(e.get("order", "go")).lower()
    return (order, str(e.get("route") or "").upper(), str(e.get("drop")) if status.startswith("at the HQ") else "",
            str(e.get("site")) if order == "raid" else "", str(e.get("support")) if order == "support" else "")


def _invalid(e, info, listed) -> bool:
    order = str(e.get("order", "go")).lower()
    route = str(e.get("route") or "").upper()
    start = str(e.get("drop")) if info["status"].startswith("at the HQ") else info["start"]
    return (order not in ("go", "wait", "support", "raid") or (info["status"].startswith("at the HQ") and start not in listed)
            or route not in listed or bool(start and not route.startswith(f"{start.upper()}-"))
            or (order == "raid" and str(e.get("site")) not in listed) or (order == "support" and str(e.get("support")) not in listed))


def cmd_score(a) -> int:
    by = defaultdict(dict)
    for line in (OUT / "replay.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        by[(r["run"], r["side"], r["t"])][r["name"]] = r
    picks = {}
    for run in {k[0] for k in by}:
        for side, rs in rows_of(run).items():
            for r in rs:
                if (run, side, r["t"]) in by and "model_s" in r:
                    picks[(run, side, r["t"])] = {"prompt": r["prompt"], "saved": r.get("answer")}
    names = ["strong_a", "strong_b", "saved"] + [n for n, _ in CHEAP]
    agg = defaultdict(Counter)
    cost = Counter()
    for k, res in by.items():
        c = picks.get(k)
        if not c or "strong_a" not in res or res["strong_a"].get("error"):
            continue
        teams, listed = {}, set()
        for line in c["prompt"].splitlines():
            m = TEAM.match(line)
            if m:
                teams[int(m[1])] = {"status": m[2], "start": m[3]}
            m = LISTED.match(line)
            if m:
                listed.add(m[1])
        want_ = {t: i for t, i in teams.items() if i["status"] != "fighting at Farm"}
        refs = [_orders(res[n]["answer"]) for n in ("strong_a", "strong_b") if n in res and not res[n].get("error")]
        ref_a = (res["strong_a"]["answer"] or {})
        for name in names:
            r = {"answer": c["saved"], "usage": None} if name == "saved" else res.get(name)
            if r is None:
                continue
            g = agg[name]
            g["calls"] += 1
            cost[name] += (r.get("usage") or {}).get("cost") or 0
            if r.get("error"):
                g["broken"] += 1
                continue
            got = _orders(r["answer"])
            g["want"] += len(want_)
            miss = sum(1 for t in want_ if t not in got)
            g["missing"] += miss
            g["missing_calls"] += bool(miss)
            bad = sum(1 for t in want_ if t in got and _invalid(got[t], want_[t], listed))
            g["invalid"] += bad
            g["invalid_calls"] += bool(bad)
            for ref in (refs[:1] if name in ("strong_a", "strong_b") else refs):
                for t in want_:
                    if t in got and t in ref:
                        g["pairs"] += 1
                        g["same"] += _key(got[t], want_[t]["status"]) == _key(ref[t], want_[t]["status"])
                        g["same_go_wait"] += str(got[t].get("order", "go")).lower() == str(ref[t].get("order", "go")).lower()
            st = ((r["answer"] or {}).get("strategy") or {}).get("stance")
            g["stance"] += st == (ref_a.get("strategy") or {}).get("stance")
            dr, rd = (r["answer"] or {}).get("drones") or {}, ref_a.get("drones") or {}
            g["drones"] += (dr.get("teams"), dr.get("target")) == (rd.get("teams"), rd.get("target"))
    print("Against the strong model's answers (strong_b and saved: against strong_a = its own noise; the cheap ones against both):")
    print(f"  {'':9} {'calls':>5} {'c/call':>6} {'same order':>10} {'go/wait':>8} {'teams left out':>15} {'invalid picks':>14} {'broken':>6} {'stance':>6} {'drones':>6}")
    for name in names:
        g = agg[name]
        if not g["calls"]:
            continue
        ok = max(1, g["calls"] - g["broken"])
        print(f"  {name:9} {g['calls']:5} {100 * cost[name] / g['calls'] if name != 'saved' else 0:6.2f} {100 * g['same'] / max(1, g['pairs']):9.0f}% "
              f"{100 * g['same_go_wait'] / max(1, g['pairs']):7.0f}% {g['missing']:5}/{g['want']} in {g['missing_calls']:2} calls "
              f"{g['invalid']:4} in {g['invalid_calls']:2} calls {g['broken']:6} {100 * g['stance'] / ok:5.0f}% {100 * g['drones'] / ok:5.0f}%")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["calls", "replay", "score"])
    ap.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--n", type=int, default=24, help="replay/score: the sample's size (2 per kind x side x phase)")
    ap.add_argument("--budget", type=float, default=0.55, help="replay: stop before spending this many dollars in all")
    a = ap.parse_args()
    return {"calls": cmd_calls, "replay": cmd_replay, "score": cmd_score}[a.what](a)


if __name__ == "__main__":
    sys.exit(main())
