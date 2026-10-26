"""The crash simulation, live (27 Oct - Martin: "I want a reproducible crash test in real time with a clear cause; count
results only from now"). Every 20 s: each mass-boarding run of the crash sub-lab (ZCR_BoardTest, crashlab mb_*) started
since --since, whether it crashed and when, how long before the crash the engine last reset a soldier stuck getting into
a vehicle, and per variant the crashes per run. Written to the lab app's pages (http://<this PC>:8790/pages/crash_live.html,
reloads itself) and printed.

    python lab/crashlive.py --since 00:00            # loop, every 20 s
    python lab/crashlive.py --since 00:00 --once
"""
import argparse
import html
import re
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / ".runtime" / "runs"
PAGE = ROOT / ".runtime" / "app_pages" / "crash_live.html"
STAMP = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d+)")
WORDS = {"mb_apc": "APCs only (LAV-25, BTR-70)", "mb_cars": "cars only (M998, UAZ-452, M1025, UAZ-469)",
         "mb_spawnboard": "mixed, fresh vehicles each cycle", "mb_board": "mixed, same vehicles", "mb_calm": "mixed, plain get-out",
         "mb_apc_stagger": "APCs, soldiers let in one by one (fix candidate)"}


def secs(s: str) -> float:
    m = STAMP.match(s)
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + float("0." + m[4]) if m else -1


def scan(run: Path) -> dict | None:
    logs = sorted(run.glob("logs/*/console.log"))
    if not logs:
        return None
    t = logs[-1].read_text(encoding="utf-8", errors="replace")
    variant = re.match(r"crashlab-(mb_[a-z_]+?)-\d+-p\d+", run.name)
    out = {"run": run.name, "variant": variant[1] if variant else "?", "crashed": bool(list(logs[-1].parent.glob("*.mdmp")))}
    game = [int(x) for x in re.findall(r"\[ZCR\]\[BOARDTEST[_A-Z]*\] t=(\d+)", t)]
    out["game_s"] = max(game) if game else 0
    sums = re.findall(r"\[ZCR\]\[BOARDTEST_SUM\] t=\d+ cycles=(\d+) issued=(\d+) seated=(\d+)", t)
    out["cycles"], out["issued"], out["seated"] = (int(sums[-1][0]), int(sums[-1][1]), int(sums[-1][2])) if sums else (0, 0, 0)
    stuck = [secs(l) for l in t.splitlines() if "Stuck trying to get into vehicle" in l]
    out["stuck"] = len(stuck)
    out["reason"] = ""
    out["stuck_before"] = None
    if out["crashed"]:
        crash = [secs(l) for l in t.splitlines() if "(F): Crashed" in l]
        if crash:
            before = [crash[0] - s for s in stuck if 0 <= crash[0] - s < 3600]
            out["stuck_before"] = round(min(before), 2) if before else None
        cl = logs[-1].parent / "crash.log"
        if cl.exists():
            m = re.search(r"Reason: (.*)", cl.read_text(encoding="utf-8", errors="replace"))
            out["reason"] = m[1][:60] if m else ""
    out["done"] = out["crashed"] or (time.time() - logs[-1].stat().st_mtime > 90)
    return out


def collect(since: str) -> list:
    day = datetime.now().strftime("%Y%m%d")
    cut = since.replace(":", "")
    rows = []
    for run in RUNS.glob("crashlab-mb_*"):
        m = re.search(r"-(\d{8})-(\d{6})$", run.name)
        if not m or m[1] != day or m[2][:4] < cut:
            continue
        r = scan(run)
        if r:
            rows.append(r)
    return sorted(rows, key=lambda r: r["run"].rsplit("-", 2)[-1] + r["run"])


def render(rows: list, since: str) -> str:
    by = {}
    for r in rows:
        by.setdefault(r["variant"], []).append(r)
    summary = []
    for v, g in sorted(by.items()):
        done = [r for r in g if r["done"]]
        crashes = [r for r in g if r["crashed"]]
        when = ", ".join(f"{r['game_s']} s" for r in crashes) or "-"
        gaps = [r["stuck_before"] for r in crashes if r["stuck_before"] is not None]
        summary.append(f"<tr><td><b>{html.escape(WORDS.get(v, v))}</b><br><small>{v}</small></td><td class=num>{len(g) - len(done)}</td>"
                       f"<td class=num>{len(done)}</td><td class=num><b>{len(crashes)}</b></td>"
                       f"<td class=num>{(len(crashes) / len(done)):.0%}</td>" if done else
                       f"<tr><td><b>{html.escape(WORDS.get(v, v))}</b><br><small>{v}</small></td><td class=num>{len(g)}</td><td class=num>0</td>"
                       f"<td class=num><b>{len(crashes)}</b></td><td class=num>-</td>")
        summary[-1] += (f"<td class=num>{when}</td><td class=num>{', '.join(f'{x:.1f} s' for x in gaps) or '-'}</td></tr>")
    runs = "".join(
        f"<tr class='{'crash' if r['crashed'] else ''}'><td><small>{r['run'].split('-2026')[0]}</small></td>"
        f"<td>{'CRASHED' if r['crashed'] else ('done' if r['done'] else 'running')}</td><td class=num>{r['game_s']}</td>"
        f"<td class=num>{r['cycles']}</td><td class=num>{r['seated']}/{r['issued']}</td><td class=num>{r['stuck']}</td>"
        f"<td class=num>{'' if r['stuck_before'] is None else str(r['stuck_before']) + ' s'}</td><td><small>{html.escape(r['reason'])}</small></td></tr>"
        for r in reversed(rows))
    return PAGE_HTML.replace("{SINCE}", since).replace("{NOW}", datetime.now().strftime("%H:%M:%S")).replace("{SUMMARY}", "".join(summary)).replace("{RUNS}", runs)


PAGE_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="20"><title>Crash Simulation</title>
<style>
:root { --bg:#f3f3ef; --surface:#fbfbf8; --ink:#1b211e; --muted:#5d6762; --rule:#d6d9d2; --hot:#b2432e; --hotbg:#f6dfd8; }
@media (prefers-color-scheme: dark) { :root { --bg:#141917; --surface:#1b211f; --ink:#e3e7e2; --muted:#9aa59f; --rule:#2e3633; --hot:#e07a63; --hotbg:#3a2420; color-scheme:dark; } }
body { background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, sans-serif; margin:0; padding:16px max(16px, env(safe-area-inset-left)); }
h1 { font-size:24px; margin:0 0 4px; } h2 { font-size:17px; margin:22px 0 6px; } p { color:var(--muted); margin:4px 0; max-width:70ch; }
.tw { overflow-x:auto; border:1px solid var(--rule); background:var(--surface); }
table { border-collapse:collapse; width:100%; font-size:14px; } th, td { padding:7px 9px; border-bottom:1px solid var(--rule); text-align:left; vertical-align:top; }
th { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); } td.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
tr.crash td { background:var(--hotbg); } tr.crash td:nth-child(2) { color:var(--hot); font-weight:700; } small { color:var(--muted); }
</style></head><body>
<h1>Crash simulation - live</h1>
<p>Runs started since {SINCE}, read at {NOW} (reloads every 20 s). The test: 8 vehicles spawned in one tick on the empty Arland test map, every soldier boarding at once the way AI Conflict does it, dropped, again. A crash = the engine closing with last night's error (BadMatrix33 -> access violation).</p>
<h2>Per variant</h2>
<div class="tw"><table><tr><th>Variant</th><th>Running</th><th>Done</th><th>Crashed</th><th>Crash rate</th><th>Crashed at (game s)</th><th>Last "stuck getting in" reset before the crash</th></tr>{SUMMARY}</table></div>
<h2>Every run</h2>
<div class="tw"><table><tr><th>Run</th><th>State</th><th>Game s</th><th>Cycles</th><th>Seated/ordered</th><th>Stuck resets</th><th>Last reset before crash</th><th>Engine's reason</th></tr>{RUNS}</table></div>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="00:00")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    while True:
        rows = collect(a.since)
        PAGE.parent.mkdir(parents=True, exist_ok=True)
        PAGE.write_text(render(rows, a.since), encoding="utf-8")
        if a.once:
            by = {}
            for r in rows:
                s = by.setdefault(r["variant"], [0, 0, 0])
                s[0] += 1
                s[1] += 1 if r["done"] else 0
                s[2] += 1 if r["crashed"] else 0
            for v, (n, d, c) in sorted(by.items()):
                print(f"{v:16s} runs={n} done={d} crashed={c}")
            for r in rows:
                if r["crashed"]:
                    print(f"  CRASH {r['run'][:40]} at {r['game_s']} s, last stuck reset {r['stuck_before']} s before, {r['reason']}")
            return 0
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())
