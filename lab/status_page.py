"""The Reforger lab's status page: what runs, the head-to-head results, the night's videos with
their moments, how it works, open problems and the changes - built from the lab's own files.

    python lab/status_page.py <out.html>

Sources: .runtime/batch_results.jsonl (headless head-to-head), .runtime/watch_matches.jsonl and
videos/*.md (watched, recorded matches), git log. Published as an artifact by Claude.
"""
import html
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = ROOT / ".runtime" / "batch_results.jsonl"
WATCHED = ROOT / ".runtime" / "watch_matches.jsonl"
VIDEOS = ROOT / "videos"
NAMES = {"none": "AI Conflict alone", "doctrine": "rules: targets only", "llm": "Gemini: targets only",
         "phased": "rules + attack doctrine", "llm-phased": "Gemini + attack doctrine"}

# Kept by hand as the night goes: what is open, what is next.
PROBLEMS = [
    ("risk", "Few matches yet", "Each matchup gets one or two 30-minute matches tonight. One match decides little; read the margins as a first look, with the control row as the size of chance."),
    ("risk", "Early game is quiet", "AI Conflict's squads start with one soldier and fill up at barracks, so the first 10-15 minutes are mostly marching and fights against FIA garrisons."),
    ("risk", "Drone strikes kill about one in three", "First drone test: 2 teams, 8 detonations on soldiers, 3 deaths; two soldiers were struck twice. A note for the FPV AI Drones chat (review note 98)."),
    ("finding", "Assaults trickle in", "Phased USSR on Arland 'assaulted' Airport Base for 25 minutes without taking it: only 2-3 squads ever went (FIA lost 18, USSR 19 there). AI Conflict refills squads one at a time and sends each as it is ready, and its 4 DEFEND squads never attack. The doctrine's count also took in the home garrison (main base 430 m away) - fixed. Being tested: the doctrine commits 2 DEFEND squads to the assault while nothing of ours is being captured."),
    ("risk", "Captures are rare", "0-2 bases change hands in a 30-minute match, the first at about 16 minutes - the score barely moves, so losses and time to the first capture matter as much."),
    ("design", "Watched matches differ a little", "The camera's observer loads FIA garrisons where it looks, and only watched matches have drones - the measurements come from the headless matches."),
]
NEXT = [
    "Drones in the measured matches too, once the doctrine's own numbers are in: does the commander do better with them?",
    "More matches per matchup, and Everon next to Arland.",
    "The rest of the Arma 3 doctrine: prep fire before the assault (mortars, drones), siege when too weak, storm when few defenders are left.",
    "Phone buttons for the watch mode, as on Arma 3 (next / previous shot, follow a group, map).",
]


def rows(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def margin(r: dict, strategist: str):
    """Bases held at the end by the side that used `strategist`, minus the other side's."""
    sc = r["metrics"].get("score") or {}
    if "US" not in sc or "USSR" not in sc:
        return None
    if r["us"] == strategist and r["ussr"] != strategist:
        return sc["US"] - sc["USSR"]
    if r["ussr"] == strategist and r["us"] != strategist:
        return sc["USSR"] - sc["US"]
    return None


def bar_chart(items: list, unit: str = "") -> str:
    """Horizontal bars around zero: [(label, value, note)]."""
    if not items:
        return "<p class='muted'>No finished matches yet.</p>"
    span = max(1.0, max(abs(v) for _, v, _ in items))
    h = 34 * len(items) + 30
    out = [f'<svg viewBox="0 0 640 {h}" role="img" class="chart">', '<line x1="380" y1="10" x2="380" y2="%d" class="axis"/>' % (h - 18)]
    for i, (label, v, note) in enumerate(items):
        y = 16 + 34 * i
        w = abs(v) / span * 230
        x = 380 if v >= 0 else 380 - w
        cls = "pos" if v > 0 else ("neg" if v < 0 else "zero")
        out.append(f'<text x="8" y="{y + 15}" class="lab">{html.escape(label)}</text>')
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{max(w, 2):.1f}" height="20" class="{cls}"/>')
        tx = x + w + 6 if v >= 0 else x - 6
        anchor = "start" if v >= 0 else "end"
        out.append(f'<text x="{tx:.1f}" y="{y + 15}" class="val" text-anchor="{anchor}">{v:+.1f}{unit} {html.escape(note)}</text>')
    out.append(f'<text x="380" y="{h - 4}" class="tick" text-anchor="middle">0 = even</text></svg>')
    return "".join(out)


def video_rows() -> list:
    out = []
    for md in sorted(VIDEOS.glob("*.md"), reverse=True):
        text = md.read_text(encoding="utf-8")
        lines = text.splitlines()
        info = lines[2] if len(lines) > 2 else ""
        moments = [l[2:] for l in text.split("## Moments (video time)", 1)[-1].split("## Camera shots")[0].splitlines() if l.startswith("- ")]
        try:
            m = json.loads(text.split("```", 2)[1])
            sc = m.get("score") or {}
            score = f"US {sc.get('US', '?')} · USSR {sc.get('USSR', '?')} · FIA {sc.get('FIA', '?')}" if sc else ""
        except (IndexError, ValueError):
            score = ""
        video = md.with_suffix(".mp4") if md.with_suffix(".mp4").exists() else md.with_suffix(".mkv")
        out.append((md.stem, info, score, moments[:4], str(video)))
    return out


def git_log() -> list:
    r = subprocess.run(["git", "-C", str(ROOT), "log", "--since=2026-10-19 02:00", "--format=%h|%ad|%s", "--date=format:%H:%M"],
                       capture_output=True, text=True)
    return [l.split("|", 2) for l in r.stdout.splitlines() if l.count("|") >= 2]


def build() -> str:
    batch = rows(RESULTS)
    watched = rows(WATCHED)
    done = [r for r in batch if r["metrics"].get("minutes", 0) >= 15]
    # Strategist margins (each matched against AI Conflict alone), and the none-v-none control.
    chart = []
    for s in ("llm", "doctrine", "phased", "llm-phased"):
        ms = [m for m in (margin(r, s) for r in done) if m is not None]
        if ms:
            chart.append((NAMES[s], statistics.mean(ms), f"({len(ms)} matches)"))
    ctrl = [r["metrics"]["score"]["USSR"] - r["metrics"]["score"]["US"] for r in done
            if r["us"] == "none" and r["ussr"] == "none" and (r["metrics"].get("score") or {}).get("US") is not None]
    if ctrl:
        chart.append(("control: AI Conflict v itself (USSR minus US)", statistics.mean(ctrl), f"({len(ctrl)} matches)"))

    table = []
    groups = defaultdict(list)
    for r in done:
        groups[(r["map"], r["us"], r["ussr"])].append(r)
    for (mp, us, ussr), rs in sorted(groups.items()):
        def avg(f):
            vals = [f(r) for r in rs if f(r) is not None]
            return f"{statistics.mean(vals):.1f}" if vals else "–"
        table.append(f"<tr><td>{mp}</td><td>{NAMES.get(us, us)}</td><td>{NAMES.get(ussr, ussr)}</td><td class='num'>{len(rs)}</td>"
                      f"<td class='num'>{avg(lambda r: (r['metrics'].get('score') or {}).get('US'))}</td>"
                      f"<td class='num'>{avg(lambda r: (r['metrics'].get('score') or {}).get('USSR'))}</td>"
                      f"<td class='num'>{avg(lambda r: (r['metrics'].get('score') or {}).get('FIA'))}</td>"
                      f"<td class='num'>{avg(lambda r: sum(r['metrics'].get('lost', {}).get('US', {}).values()))}</td>"
                      f"<td class='num'>{avg(lambda r: sum(r['metrics'].get('lost', {}).get('USSR', {}).values()))}</td></tr>")

    vids = video_rows()
    vid_html = []
    for stem, info, score, moments, path in vids[:14]:
        ms = "".join(f"<li>{html.escape(m)}</li>" for m in moments) or "<li class='muted'>no moments yet</li>"
        vid_html.append(f"<div class='vid'><div class='vh'><b>{html.escape(stem)}</b><span>{html.escape(score)}</span></div>"
                        f"<p class='muted'>{html.escape(info)}</p><ul>{ms}</ul><code>{html.escape(path)}</code></div>")

    now = datetime.now().strftime("%H:%M")
    running_watch = len(watched) + 1
    probs = "".join(f"<div class='prob'><span class='chip {c}'>{c}</span><div><b>{html.escape(t)}</b><p>{html.escape(d)}</p></div></div>"
                    for c, t, d in PROBLEMS)
    nxt = "".join(f"<li>{html.escape(n)}</li>" for n in NEXT)
    log = "".join(f"<tr><td class='num'>{t}</td><td><code>{h}</code></td><td>{html.escape(s)}</td></tr>" for h, t, s in git_log())
    strat = [c for c in chart if not c[0].startswith("control")]
    best = max(strat, key=lambda x: x[1]) if strat else None
    verdict_best = f"{best[0]}: {best[1]:+.1f} bases a match against AI Conflict alone" if best else "no finished head-to-head match yet"
    return TEMPLATE.format(
        now=now, n_batch=len(done), n_videos=len(vids), watch_n=running_watch, verdict_best=html.escape(verdict_best),
        chart=bar_chart(chart, ""), table="".join(table) or "<tr><td colspan='9' class='muted'>Waiting for the first 30-minute match.</td></tr>",
        videos="".join(vid_html) or "<p class='muted'>The first recording is on its way.</p>", problems=probs, next=nxt, log=log)


TEMPLATE = """<title>Reforger Commander Lab</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
/* Layout: the Zeus Commander briefing column; APP-6 frame colours mark state. */
:root {{ --bg:#f2f3ef; --surface:#fbfbf8; --ink:#1c2320; --muted:#5a6560; --rule:#d5d9d2; --accent:#2b5d86; --hostile:#b2432e; --unknown:#a77a12; --neutral:#3f7d4f; --chip-ink:#fff; --code-bg:#e7e9e3;
  --display:"Barlow Semi Condensed","Arial Narrow",system-ui,sans-serif; --body:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif; --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#141917; --surface:#1b211f; --ink:#e3e7e2; --muted:#9aa59f; --rule:#2e3633; --accent:#79a9d4; --hostile:#e07a63; --unknown:#d9a93d; --neutral:#74b884; --chip-ink:#101412; --code-bg:#232a27; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --bg:#141917; --surface:#1b211f; --ink:#e3e7e2; --muted:#9aa59f; --rule:#2e3633; --accent:#79a9d4; --hostile:#e07a63; --unknown:#d9a93d; --neutral:#74b884; --chip-ink:#101412; --code-bg:#232a27; color-scheme:dark; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--ink); font:15.5px/1.6 var(--body); padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); padding-block:0 72px; }}
.wrap {{ max-width:900px; margin:0 auto; }}
header {{ padding-block:44px 24px; border-bottom:2px solid var(--ink); display:grid; gap:12px; }}
.eyebrow {{ font:600 12px/1 var(--mono); letter-spacing:.14em; text-transform:uppercase; color:var(--accent); }}
h1,h2,h3 {{ font-family:var(--display); line-height:1.1; margin:0; text-wrap:balance; }}
h1 {{ font-size:clamp(34px,6vw,50px); }}
h2 {{ font-size:27px; margin-top:46px; padding-bottom:8px; border-bottom:1px solid var(--rule); }}
p, li {{ max-width:74ch; }}
.muted {{ color:var(--muted); }}
code {{ font-family:var(--mono); font-size:.85em; background:var(--code-bg); padding:1px 5px; border-radius:3px; overflow-wrap:anywhere; }}
.verdict {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
.verdict > div {{ background:var(--surface); border:1px solid var(--rule); border-left:4px solid var(--accent); padding:10px 14px; min-width:0; }}
.verdict b {{ display:block; font-family:var(--display); font-size:18px; }}
.table-wrap {{ overflow-x:auto; border:1px solid var(--rule); background:var(--surface); margin-top:12px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--rule); vertical-align:top; }}
th {{ font:600 11.5px var(--mono); letter-spacing:.07em; text-transform:uppercase; color:var(--muted); background:var(--bg); }}
td.num {{ font-variant-numeric:tabular-nums; white-space:nowrap; }}
.chart {{ width:100%; max-width:640px; background:var(--surface); border:1px solid var(--rule); margin-top:12px; }}
.chart .axis {{ stroke:var(--muted); stroke-width:1; }} .chart .lab, .chart .val, .chart .tick {{ fill:var(--ink); font:13px var(--body); }}
.chart .pos {{ fill:var(--neutral); }} .chart .neg {{ fill:var(--hostile); }} .chart .zero {{ fill:var(--muted); }}
.vids {{ display:grid; gap:10px; margin-top:12px; }}
.vid {{ background:var(--surface); border:1px solid var(--rule); padding:10px 14px; min-width:0; }}
.vh {{ display:flex; flex-wrap:wrap; justify-content:space-between; gap:4px 12px; }}
.vh span {{ font:500 13px var(--mono); color:var(--muted); }}
.vid ul {{ margin:6px 0; padding-left:18px; font-size:14px; }}
.vid p {{ margin:2px 0; font-size:13px; }}
.chip {{ display:inline-block; font:600 11px/1 var(--mono); letter-spacing:.06em; text-transform:uppercase; padding:4px 7px; border-radius:2px; color:var(--chip-ink); white-space:nowrap; }}
.risk {{ background:var(--unknown); }} .design {{ background:var(--accent); }} .bug {{ background:var(--hostile); }} .good {{ background:var(--neutral); }}
.prob {{ display:grid; grid-template-columns:6.5rem 1fr; gap:6px 12px; padding-block:10px; border-bottom:1px solid var(--rule); }}
.prob p {{ margin:2px 0 0; }}
@media (max-width:560px) {{ .prob {{ grid-template-columns:1fr; }} }}
pre.mermaid {{ background:var(--surface); border:1px solid var(--rule); padding:12px; overflow-x:auto; }}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Reforger lab · night of 18–19 Oct · updated {now}</div>
  <h1>Reforger Commander Lab</h1>
  <p>Zeus Commander's commander on Arma Reforger, built on AI Conflict. Tonight: matches on screen with the camera director and recorded, and headless head-to-head matches. In each, one side gets our strategist (our rules or Gemini) and the other runs on AI Conflict alone.</p>
  <div class="verdict">
    <div><b>Running now</b>Watched match {watch_n} on screen (recorded) and a headless head-to-head beside it.</div>
    <div><b>So far</b>{n_batch} finished head-to-head matches, {n_videos} recordings.</div>
    <div><b>Best so far</b>{verdict_best}</div>
  </div>
</header>

<h2>Does the strategist help?</h2>
<p>Bases held at the end of a 30-minute match by the side with the strategist, minus the other side's. Each strategist plays both US and USSR, so a side's map advantage cancels out. The control row is AI Conflict against itself: how far apart two equal sides land by chance.</p>
{chart}

<h3>Every matchup</h3>
<div class="table-wrap"><table>
<tr><th>Map</th><th>US</th><th>USSR</th><th>n</th><th>Bases US</th><th>Bases USSR</th><th>FIA</th><th>Lost US</th><th>Lost USSR</th></tr>
{table}
</table></div>

<h2>Watch</h2>
<p>Recorded matches, newest first. Videos are in <code>D:\\work\\reforger-commander\\videos</code>; next to each is a <code>.md</code> with the result and every moment with its time in the video: commanders' plans, captures, camera shots.</p>
<div class="vids">{videos}</div>

<h2>How it works</h2>
<pre class="mermaid">
flowchart LR
  classDef ours fill:#2b5d86,stroke:#1e4361,color:#ffffff
  classDef aicf fill:#3f7d4f,stroke:#2d5a39,color:#ffffff
  classDef llm fill:#a77a12,stroke:#7a590d,color:#ffffff
  S["Situation report every 90 s<br/>bases, links, own squads"]:::ours --> B["Bridge on the PC<br/>rules doctrine or Gemini"]:::llm
  B --> P["Plan per side<br/>main effort, holds, avoid, intent"]:::ours
  P --> C["AI Conflict's commander<br/>scores bases + our priority and demand"]:::aicf
  C --> Q["10 squads a side,<br/>trucks, APCs, barracks"]:::aicf
  Q --> S
  D["Director on the server<br/>fights, plans, captures, close-ups"]:::ours --> W["Game on screen<br/>camera, overlay, caption"]:::ours
  W --> V["Video + moments list"]:::ours
</pre>
<p>On screen: the bases in their owner's colour, each side's main effort as a trail of growing squares (as on Arma 3), losses in side colours, soldier tags in close views, a caption for every shot and a panel with both commanders' intent. A strategist side in a watched match also sends FPV drone teams (Martin's FPV AI Drones) to its objective, and the camera follows a drone until it hits. Every match is in the same clear midday, so they compare fairly.</p>
<h3>The strategists</h3>
<div class="table-wrap"><table>
<tr><th>Name</th><th>Picks the objective</th><th>How it fights for it</th></tr>
<tr><td>AI Conflict alone</td><td>AI Conflict's own score</td><td>Squads assigned one by one</td></tr>
<tr><td>rules: targets only</td><td>Our rules: the best reachable base</td><td>Priority and force demand on it</td></tr>
<tr><td>Gemini: targets only</td><td>Gemini, every 90 s</td><td>Priority and force demand on it</td></tr>
<tr><td>rules + attack doctrine</td><td>Our rules, when a new objective is due</td><td>The Arma 3 doctrine: gather at our nearest base, assault in force, fall back when bled out, keep the momentum after a capture</td></tr>
<tr><td>Gemini + attack doctrine</td><td>Gemini, only when a new objective is due</td><td>The same doctrine</td></tr>
</table></div>

<h2>Open problems</h2>
{problems}

<h2>Next</h2>
<ol>{next}</ol>

<h2>Changes tonight</h2>
<div class="table-wrap"><table><tr><th>Time</th><th>Commit</th><th>What</th></tr>{log}</table></div>
<p class="muted">Code: <code>D:\\work\\reforger-commander</code> on AI Conflict (<code>D:\\work\\reforger-ai-conflict</code>, Apache-2.0). Research and plan: the Reforger Commander AI page.</p>
</div>
"""

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".runtime" / "status.html"
    out.write_text(build(), encoding="utf-8")
    print(f"written {out}")
