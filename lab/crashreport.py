"""The crash hunt in numbers (26 Oct - Martin, note 421: "I want to see the results of the crash lab in a clear way, with
probabilities of the root cause"). Reads every run of the crash sub-lab (lab/crashlab.py -> .runtime/sublab/crash) and for
each suspect sets the crash rate with it against the rate without it:

  crashes     bad-position crashes (the engine's BadMatrix33/BadVec asserts, then a crash) - last night's kind
  rate        crashes per game hour, with a 90% range
  P(cause)    the probability that the suspect raises the crash rate: the two rates as Poisson processes with Jeffreys
              priors (Gamma(k + 0.5, hours)), sampled 20 000 times - P(rate with > rate without)

    python lab/crashreport.py            # table in the terminal + .runtime/crashreport.html
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
OUT = ROOT / ".runtime" / "crashreport.html"

PRE_FORK = {"prefork", "oldall", "massboard_prefork"}
BATTLE_TODAY = {"default", "prenight", "noturretpush", "nomoves", "nodrones", "noarmed", "physfix", "norides", "phased", "massboard"}

# Suspect: (description, test "with", test "without") on a run row; None = every run not "with".
SUSPECTS = [
    ("Last night's AI Conflict change (free spawn pads, APC seats, footprint step-out)",
     lambda r: r["variant"] in BATTLE_TODAY, lambda r: r["variant"] in PRE_FORK),
    ("Our game code from last night (drones, forward crews, dismount band...) - on today's fork",
     lambda r: r["variant"] in {"default", "nomoves", "nodrones", "noarmed", "physfix", "norides", "phased", "noturretpush"},
     lambda r: r["variant"] == "prenight"),
    ("Armed vehicles pushed out of jams", lambda r: r["variant"] in {"default", "nodrones", "noarmed", "physfix", "norides"},
     lambda r: r["variant"] in {"noturretpush", "nomoves"}),
    ("FPV drones", lambda r: r["variant"] in {"default", "noturretpush", "nomoves", "noarmed", "physfix", "norides"},
     lambda r: r["variant"] == "nodrones"),
    ("Infantry rides (boarding at all)", lambda r: r["variant"] in {"default", "noturretpush", "nomoves", "nodrones", "noarmed", "physfix"},
     lambda r: r["variant"] == "norides"),
    ("The modern strategist", lambda r: r["variant"] in {"default"}, lambda r: r["variant"] == "phased"),
    ("Mass boarding, sub-lab: AI Conflict's drop (release + interrupt) v a plain get-out",
     lambda r: r["variant"] in {"mb_board"}, lambda r: r["variant"] == "mb_calm"),
    ("Mass boarding, sub-lab: fresh vehicles every cycle v the same vehicles",
     lambda r: r["variant"] == "mb_spawnboard", lambda r: r["variant"] == "mb_board"),
    ("Mass boarding, sub-lab: APCs v cars", lambda r: r["variant"] == "mb_apc", lambda r: r["variant"] == "mb_cars"),
]


def rows() -> list:
    import sublab
    p = sublab.results_path("crash")
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if not r.get("run", "").startswith("crashlab-"):
            continue
        if (r.get("minutes") or 0) < 0.3 and not r.get("crashed"):
            continue      # a run that never got going
        r["bad"] = 1 if r.get("crashed") and ("BadMatrix" in (r.get("reason") or "") or (r.get("badmatrix_asserts") or 0) > 0) else 0
        r["hours"] = max((r.get("minutes") or 0) / 60, 1 / 120)
        out.append(r)
    return out


def summary(group: list) -> tuple:
    k = sum(r["bad"] for r in group)
    h = sum(r["hours"] for r in group)
    return len(group), k, h


def rate_range(k: int, h: float) -> tuple:
    if h <= 0:
        return 0, 0, 0
    draws = sorted(random.gammavariate(k + 0.5, 1) / h for _ in range(4000))
    return k / h, draws[int(0.05 * len(draws))], draws[int(0.95 * len(draws))]


def p_higher(k1: int, h1: float, k2: int, h2: float) -> float:
    if h1 <= 0 or h2 <= 0:
        return float("nan")
    n = 20000
    return sum(1 for _ in range(n) if random.gammavariate(k1 + 0.5, 1) / h1 > random.gammavariate(k2 + 0.5, 1) / h2) / n


def main() -> int:
    random.seed(7)
    rs = rows()
    by = {}
    for r in rs:
        by.setdefault(r["variant"], []).append(r)
    lines = []
    lines.append("RUNS BY VARIANT (bad-position crashes only)")
    lines.append(f"{'variant':20s} {'runs':>5s} {'crashes':>8s} {'game h':>7s}  rate/h (90% range)")
    table = []
    for v, g in sorted(by.items()):
        n, k, h = summary(g)
        rt, lo, hi = rate_range(k, h)
        table.append((v, n, k, h, rt, lo, hi))
        lines.append(f"{v:20s} {n:5d} {k:8d} {h:7.1f}  {rt:.2f} ({lo:.2f}-{hi:.2f})")
    lines.append("")
    lines.append("SUSPECTS - P(cause) = probability the suspect raises the crash rate")
    sus = []
    for name, with_, without in SUSPECTS:
        a = [r for r in rs if with_(r)]
        b = [r for r in rs if without(r)]
        na, ka, ha = summary(a)
        nb, kb, hb = summary(b)
        p = p_higher(ka, ha, kb, hb) if na and nb else float("nan")
        sus.append((name, na, ka, ha, nb, kb, hb, p))
        lines.append(f"{p:6.0%}  {name}\n        with: {ka} in {na} runs ({ha:.1f} h)   without: {kb} in {nb} runs ({hb:.1f} h)"
                     if p == p else f"   n/a  {name} (no runs yet)")
    print("\n".join(lines))
    write_html(table, sus)
    print(f"\n{OUT}")
    return 0


def write_html(table, sus) -> None:
    def bar(p):
        if p != p:
            return '<span class="na">not run yet</span>'
        cls = "hi" if p >= 0.9 else "mid" if p >= 0.7 else "lo"
        return f'<div class="bar {cls}"><span style="width:{p * 100:.0f}%"></span></div><b>{p:.0%}</b>'

    srows = "\n".join(
        f"<tr><td>{name}</td><td>{bar(p)}</td><td class=num>{ka} in {na} runs<br><small>{ha:.1f} game h</small></td>"
        f"<td class=num>{kb} in {nb} runs<br><small>{hb:.1f} game h</small></td></tr>"
        for name, na, ka, ha, nb, kb, hb, p in sorted(sus, key=lambda s: -(s[7] if s[7] == s[7] else -1)))
    vrows = "\n".join(f"<tr><td>{v}</td><td class=num>{n}</td><td class=num>{k}</td><td class=num>{h:.1f}</td>"
                      f"<td class=num>{rt:.2f} <small>({lo:.2f}-{hi:.2f})</small></td></tr>" for v, n, k, h, rt, lo, hi in table)
    OUT.write_text(TEMPLATE.replace("{SUSPECTS}", srows).replace("{VARIANTS}", vrows), encoding="utf-8")


TEMPLATE = """<title>Crash Hunt</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root { --bg:#f3f3ef; --surface:#fbfbf8; --ink:#1b211e; --muted:#5d6762; --rule:#d6d9d2; --hi:#b2432e; --mid:#a77a12; --lo:#3f7d4f; --track:#e4e6df; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#141917; --surface:#1b211f; --ink:#e3e7e2; --muted:#9aa59f; --rule:#2e3633; --hi:#e07a63; --mid:#d9a93d; --lo:#74b884; --track:#2a312e; color-scheme:dark; } }
:root[data-theme="dark"] { --bg:#141917; --surface:#1b211f; --ink:#e3e7e2; --muted:#9aa59f; --rule:#2e3633; --hi:#e07a63; --mid:#d9a93d; --lo:#74b884; --track:#2a312e; color-scheme:dark; }
body { background:var(--bg); color:var(--ink); font:15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); padding-block:24px 48px; }
.wrap { max-width:900px; margin:0 auto; }
h1 { font-size:30px; margin:0 0 6px; } h2 { font-size:20px; margin:28px 0 8px; }
p { max-width:72ch; color:var(--muted); }
.tw { overflow-x:auto; border:1px solid var(--rule); background:var(--surface); }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { text-align:left; padding:9px 11px; border-bottom:1px solid var(--rule); vertical-align:top; }
th { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
td.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
small { color:var(--muted); }
.bar { display:inline-block; width:120px; height:10px; background:var(--track); border-radius:5px; vertical-align:middle; margin-right:8px; overflow:hidden; }
.bar span { display:block; height:100%; }
.bar.hi span { background:var(--hi); } .bar.mid span { background:var(--mid); } .bar.lo span { background:var(--lo); }
.na { color:var(--muted); font-style:italic; }
</style>
<div class="wrap">
<h1>Crash hunt</h1>
<p>Last night's crash: the engine finds a broken position on some object (enf_entity.cpp BadMatrix33 / BadVec asserts) and then crashes. Every row below is a set of headless crash-lab runs; only that kind of crash is counted. <b>P(cause)</b> is the probability that the suspect raises the crash rate, from the crash rates with and without it (Poisson, Jeffreys priors, 20 000 samples). Near 50% means the runs can't tell; near 100% means the suspect is in the cause.</p>
<h2>Suspects</h2>
<div class="tw"><table><tr><th>Suspect</th><th>P(cause)</th><th>With it</th><th>Without it</th></tr>
{SUSPECTS}
</table></div>
<h2>Every variant</h2>
<div class="tw"><table><tr><th>Variant</th><th>Runs</th><th>Crashes</th><th>Game hours</th><th>Crashes per game hour (90% range)</th></tr>
{VARIANTS}
</table></div>
<p>Battle variants: the Arland battle, one suspect off each. Pre-night fork: prefork, oldall, massboard_prefork. Sub-lab mb_*: the mass-boarding scenario on the empty test map - 8 vehicles spawned in one tick, every soldier boarding at once the way AI Conflict does it, again and again.</p>
</div>
"""

if __name__ == "__main__":
    sys.exit(main())
