"""Supply trucks and building, match by match, from the server log.

    python lab/trucks.py probe-truckA probe-truckB      # latest run of each label
    python lab/trucks.py --run .runtime/runs/<run>      # one run

Per match: depots ready, every truck job end to end (phase changes in game minutes; a lost truck with its place
and whether a drone hit was logged there in the 30 s before), what the trucks
waited for, routes AI Conflict could not prove (by base), each side's bases' supplies at 5/15/end min,
what was built (by type and prefab) and what was not (why), and the work crews' build points.
"""
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / ".runtime" / "runs"
KV = re.compile(r"(\w+)=(\S+)")


def console(run: Path):
    logs = sorted(run.glob("logs/*/console.log"))
    return logs[-1] if logs else None


def report(run: Path) -> str:
    log = console(run)
    if not log:
        return f"{run.name}: no log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    out = [f"== {run.name}"]
    c = collections.Counter()
    waits = collections.Counter()
    jobs = collections.defaultdict(list)       # job token -> [(min, event, phase/reason)]
    unproven = collections.Counter()
    built = collections.Counter()
    notbuilt = collections.Counter()
    supply = []
    crew = {}
    game_t = 0                                  # the latest [ZCR] game time (s) - job times are in game minutes
    hits = []                                   # (game s, x, z) drone hits from [ZCR][DRONETHREAT] scatter
    for l in lines:
        g = re.search(r"\[ZCR\]\[\w+\] t=(\d+)", l)
        if g:
            game_t = int(g.group(1))
            h = re.search(r"scatter=\d+ at=(-?\d+) (-?\d+)", l)
            if h:
                hits.append((game_t, int(h.group(1)), int(h.group(2))))
        m = re.search(r"\]\[(LOGISTICS_[A-Z_]+)\]", l)
        if m:
            ev = m.group(1)
            c[ev] += 1
            d = dict(KV.findall(l))
            t_ms = int(d.get("t_ms", "0") or 0)
            if ev == "LOGISTICS_WAITING":
                waits[d.get("reason", "?")] += 1
            elif ev == "LOGISTICS_ROUTE_UNPROVEN":
                unproven[(d.get("base"), d.get("x"), d.get("z"), d.get("radius"))] += 1
            job = d.get("job", "NONE")
            if job != "NONE" and ev in ("LOGISTICS_JOB_RESERVED", "LOGISTICS_REPLANNED", "LOGISTICS_LOAD_COMMITTED",
                                         "LOGISTICS_UNLOAD_COMMITTED", "LOGISTICS_CARGO_LOST", "LOGISTICS_JOB_COMPLETED",
                                         "LOGISTICS_JOB_FAILED", "LOGISTICS_JOB_CANCELLED", "LOGISTICS_CONTROL_LOST",
                                         "LOGISTICS_DRIVER_INTERACTION_FAILED", "LOGISTICS_FALLBACK_STARTED"):
                note = d.get("phase", "") + (f" ({d['reason']})" if d.get("reason") else "")
                if ev == "LOGISTICS_CONTROL_LOST" and d.get("driver_alive") == "0":
                    note = d.get("phase", "") + " (DRIVER KILLED)"
                jobs[f"{d.get('faction')} {job}"].append((round(game_t / 60, 1), ev.replace("LOGISTICS_", ""), note))
            if job != "NONE" and ev == "LOGISTICS_MOTION_SNAPSHOT" and d.get("reason") == "TERMINAL_CONTROL_LOSS":
                pos = re.search(r"position=<(-?[\d.]+),[-\d.]+,(-?[\d.]+)>", l)
                if pos:
                    x, z = float(pos.group(1)), float(pos.group(2))
                    near = [h for h in hits if game_t - 30 <= h[0] <= game_t and (h[1] - x) ** 2 + (h[2] - z) ** 2 < 60 ** 2]
                    where = f"at {x:.0f},{z:.0f}" + (f", drone hit {game_t - near[-1][0]}s before" if near else ", no drone hit logged")
                    jobs[f"{d.get('faction')} {job}"].append((round(game_t / 60, 1), "LOST", where))
        if "CONSTRUCTION_COMPLETED" in l:
            d = dict(KV.findall(l))
            pr = re.search(r"/(E_\w+)\.et", l)
            built[(d.get("faction"), d.get("type"), pr.group(1) if pr else "")] += 1
        elif "CONSTRUCTION_DEFERRED" in l or "CONSTRUCTION_CANCELLED" in l:
            d = dict(KV.findall(l))
            notbuilt[(d.get("type"), d.get("metadata_reason") or d.get("reason"))] += 1
        elif "[ZCR][SUPPLY]" in l:
            supply.append(dict(KV.findall(l)))
        elif "[ZCR][CREW]" in l:
            d = dict(KV.findall(l))
            crew[d.get("side")] = d
    end_t = max((int(s["t"]) for s in supply), default=0)
    out.append(f"game {end_t // 60} min | depots ready {c['LOGISTICS_DEPOT_READY']} | jobs {c['LOGISTICS_JOB_RESERVED']} "
               f"loads {c['LOGISTICS_LOAD_COMMITTED']} unloads {c['LOGISTICS_UNLOAD_COMMITTED']} cargo lost {c['LOGISTICS_CARGO_LOST']}")
    out.append("  waits: " + ", ".join(f"{k} {v}" for k, v in waits.most_common(6)))
    if unproven:
        out.append("  routes not proven: " + ", ".join(f"base {b} at {x},{z} r{r} x{n}" for (b, x, z, r), n in unproven.most_common(6)))
    for job, evs in jobs.items():
        steps = " > ".join(f"{t}m {e}{(' ' + n) if n.strip() else ''}" for t, e, n in evs[:16])
        done = any(e in ("UNLOAD_COMMITTED", "LOST", "JOB_COMPLETED", "JOB_FAILED", "JOB_CANCELLED") for _, e, _ in evs)
        out.append(f"  job {job}: {steps}" + ("" if done else f" > still under way at the end ({end_t // 60}m)"))
    for t in (300, 900, end_t):
        row = [f"{s['side']}{'*' if s.get('main') == '1' else ''} {s['value']}/{s['max']}" for s in supply if abs(int(s["t"]) - t) < 31]
        out.append(f"  supplies {t // 60}m: " + " | ".join(row))
    for side in ("US", "USSR"):
        b = {k[1:]: v for k, v in built.items() if k[0] == side}
        fort = sum(v for k, v in b.items() if k[0] == "FORTIFICATION")
        out.append(f"  {side} built: fortifications {fort}, depots {sum(v for k, v in b.items() if k[0].endswith('DEPOT'))}, "
                   f"barracks {sum(v for k, v in b.items() if 'BARRACKS' in k[0])} | crew {crew.get(side, {}).get('crew', '-')} "
                   f"points {crew.get(side, {}).get('points', '-')}")
    out.append("  not built: " + ", ".join(f"{t} {r} {n}" for (t, r), n in notbuilt.most_common(6)))
    return "\n".join(out)


def main() -> int:
    if "--run" in sys.argv:
        print(report(Path(sys.argv[sys.argv.index("--run") + 1])))
        return 0
    for label in sys.argv[1:]:
        runs = sorted(RUNS.glob(f"{label}-2*"))
        print(report(runs[-1]) if runs else f"{label}: no run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
