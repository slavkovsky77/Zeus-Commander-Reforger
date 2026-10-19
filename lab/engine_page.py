"""The Reforger commander's engine page and changelog - the same two pages as the Arma 3 lab's
(how it works now with per-build charts; every build's history), built from the lab's own files.

    python lab/engine_page.py <out_dir> [--changelog-url URL]

Writes <out_dir>/reforger_engine.html and <out_dir>/reforger_changelog.html. The prose below is kept
by hand as the work goes; the charts and the probe table come from the match logs (progress.py).
"""
import html
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import progress  # noqa: E402
import probe_report  # noqa: E402

E = html.escape
STATUS_URL = "https://claude.ai/artifact/NRTbYF1byVzTPtECaAyVhy"
RESEARCH_URL = "https://claude.ai/artifact/HeQBbPV4PanCcGWGRBmAGp"
ARMA3_URL = "https://claude.ai/artifact/8iF2jyqs5rgjxxbQUKtqWx"

VERDICT = {
    "Running now": "Nothing on screen. Probes run headless in the background when testing.",
    "Today's result": "A careful storm (priority 25) took Moss Hill as fast as a full storm and lost 15 soldiers instead of 39.",
    "Being built next": "Careful storm as the default; trucks only for long marches; drones on both sides and measured.",
}

# (chip class, chip text, title, text) - what changed most recently.
NOW = [
    ("good", "r6", "A careful storm",
     "On Arma 3 you wanted soldiers who move cover to cover, and the storm made them run in. A storm order raises the "
     "priority of the attack orders, and Reforger's soldiers stop taking cover to follow them. At priority 25 the squad "
     "still keeps advancing, but soldiers drop into fire positions and shoot. Moss Hill probe: taken 10.8 min after the storm "
     "order (full storm: 8-12.5 min), and the USSR lost 15 soldiers around it instead of 28-39, while FIA lost about the same (36)."),
    ("design", "r6", "Why priority 100 and 1000 were the same",
     "Reforger adds a waypoint's priority to the group's move (50; fighting a spotted enemy group is 70) and to each soldier's "
     "formation movement (30; taking a fire position 60, attacking a chosen target 90). Anything over 60 overrides all of "
     "that, so 100 and 1000 behave alike - the probes agreed (39 lost in both). Only danger reactions with their own +1000 "
     "still win."),
    ("risk", "r6", "Trucks from the start cost more than they save",
     "AI Conflict's own commander never gives infantry a vehicle - only a player can make a squad motorized. Our doctrine "
     "now can, through the same call. First probe: squads spent minutes walking to truck spawn sites and boarding, 12 trucks "
     "were abandoned, 7 trips fell back to walking, and the side took nothing in 28 min. Next: trucks only for the long "
     "marches to the next base (1-1.4 km), where squads took 7-18 min on foot."),
    ("good", "r4", "Storm takes the hill",
     "Squads used to stop 300-600 m short and trade shots for 20+ minutes. With storm, Moss Hill fell in every clean match, at "
     "15-20 min; headless, the USSR doctrine went from 1-2, 1-2 to 3-2, 2-1, 3-2."),
    ("bug", "r5", "Two matches shared one memory",
     "The watched and the headless match used the same strategist bridge, and the doctrine remembered its phase per side only, "
     "so two matches with the same strategist on the same side reset each other. Now memory is per match and side."),
]

FLOW = """flowchart LR
  G[AI Conflict<br/>squads, supplies, bases] -->|every 90 s: situation report| B[Strategist bridge<br/>Python: rules or Gemini]
  B -->|plan: priorities, demand,<br/>commit, storm, motorize| C[Our commander layer<br/>ZeusCommanderReforger]
  C -->|scores and orders| G
  C -->|camera shots, overlay| W[Watcher's game<br/>recorded]"""

PHASES = [
    ("Pick", "Our rules, or Gemini with your doctrine text, choose the objective among the bases AI Conflict can attack (reached by the radio network)."),
    ("Gather", "The staging base (ours, nearest the objective) is the main effort; the objective is avoided so nobody walks in alone. Go at 25 soldiers there, 60% after 5 min, or after 10 min."),
    ("Assault", "The objective is the main effort with a heavy demand. While none of our bases is being captured, 2 of AI Conflict's 4 defender squads join (commit)."),
    ("Storm", "4 min into the assault, with 60% of the force sent there: the attack orders get a higher priority so the squads go in (r6 probes: 25 careful, 1000 full)."),
    ("Called off", "No capture 10 min after the force got there with nobody on the objective, or 15 min with soldiers on it, or 20 min from the order - never while the base is being seized. The next pick avoids it."),
    ("Bled out", "After 6 min, fewer than 35% of the needed soldiers still sent there: back to gather with a bigger need."),
    ("Follow-on", "A base taken and the force still near: straight on to the next one (momentum), defenders released and committed again."),
]

DRONES = ("When a doctrine side attacks, it launches a team of 4 FPVs from your FPV AI Drones mod at its own base nearest the "
          "objective; the drones fly a Move waypoint there and go for soldiers within 200 m (every third team for vehicles). At "
          "most 2 teams in the air per side, a new team every 4 minutes. Watched matches only so far, and only the doctrine side: "
          "4-6 teams, 10-16 strikes, 8-21 kills per match, all FIA so far.")

CAMERA = [
    ("CAPTURE", "a base changed hands in the last 40 s"),
    ("STORM", "a side storms a base - the climax of an assault"),
    ("FPV DRONE", "cut to a team as soon as it is airborne, follow one until it hits, 4 s on the impact"),
    ("COMMANDER", "a side's main effort moved to another base, with the commander's intent"),
    ("ASSAULT / FIGHT", "a side's soldiers massed at a base they don't hold, or US against USSR; close-ups follow"),
    ("ON THE MOVE", "the soldier or vehicle farthest out in the field"),
    ("OBJECTIVE / STAGING", "instead of a repeated hot zone: each side's main effort in turn"),
    ("HOT ZONE", "both main efforts and the fights, at most 2.2 km across"),
]

PROBLEMS = [
    ("design", "Careful or full storm?", "Your call. Careful (25) cost a third of the losses in one probe; one probe is not proof. I'd make careful the default and keep full storm for a last push.", "review note 106"),
    ("risk", "Slow follow-on after a capture", "Squads sent 1-1.4 km on to the next base take 7-18 min: AI Conflict holds them at the base just taken, then walks them in 220 m steps.", "review note 109"),
    ("risk", "Trucks cost time", "Motorize for every attack squad made the first probe worse (no capture). Only for long marches, next.", "r6 probe"),
    ("risk", "Drones are one-sided and unmeasured", "Only the doctrine side gets drones, and only in watched matches. Both sides and headless runs needed before drones count in the results.", "review note 98"),
    ("risk", "Arland favours the US", "In the controls (AI Conflict on both sides) the US ends 2-1 three times out of four: read the USSR side's results against that.", "4 controls"),
    ("risk", "Few matches per build", "Each build has 1-4 matches per line, so single points jump. Captures are rare (0-3 a match).", ""),
    ("design", "FIA garrisons spawn near observers", "AI Conflict spawns FIA garrisons only where someone is near; in watched matches the camera is someone. Measure on headless matches.", ""),
]

NEXT = [
    "Careful storm (priority 25) as the default; a second Moss Hill probe and the headless matchups to confirm.",
    "Trucks only for long marches: motorize when the next objective is over 1 km away (Everon), measured as the follow-on time.",
    "Drones for both sides in watched matches, and the drone mods in headless matches: drones on v off.",
    "In-game samplers for the Arma 3 charts we don't have yet: fighting from cover, sitting ducks, stacking.",
    "Phone buttons for the watch mode, as on Arma 3.",
]

FACTS = [
    "AI Conflict (Apache-2.0) runs both commanders: per side 10 squads of up to 10 soldiers, 6 attack and 4 defend for the whole match, refilled one soldier at a time at the main base. We change it from our own addon (modded classes), without a fork.",
    "Each side can attack only bases its radio network reaches; at the start that is one base, and which one varies by match (Arland USSR: Airport Base or Moss Hill).",
    "A base is taken through the game's own capture point: our soldiers there and no enemy inside. AI Conflict sends attackers to the capture point, which can be away from the base's own position.",
    "AI Conflict walks squads to an objective in 220 m approach steps, and a Reforger group under fire stops to fight at each step - squads stalled 300-600 m out.",
    "Reforger AI priorities (SCR_AIAction): group move 50, fighting a spotted group 70; soldier formation movement 30, fire position 60, attack a chosen target 90, danger reactions +1000. A waypoint's priority level adds to the move.",
    "AI Conflict's commander never gives infantry a vehicle; a squad made motorized (by a player, or our doctrine) gets one of 10 trucks per side for routes over 400 m, dropped 150 m short.",
    "FIA garrisons spawn only where an observer is near (a player or the camera).",
    "A drone kill has no killer in the game's death event: the lab credits a death with no killer within 5 s of an FPV detonation to the drone.",
    "Matches run in real time (no speed-up); a 30-minute match takes 30 minutes. Up to four headless servers run side by side at 60 fps.",
]

# The changelog: (build, name, date, what, why, result)
CHANGELOG = [
    (6, "motorize, careful storm", "19 Oct, from 10:30",
     ["Attack squads can ride trucks (motorize), through AI Conflict's own configuration path - its commander never gives infantry a vehicle.",
      "Storm priority as a setting (-zcrStormPriority); probes with a fixed first objective (bridge --first-target, lab/probe.py).",
      "lab/progress.py and this page: measurements per build from every match log."],
     "Martin: storm makes the soldiers reckless; the follow-on after a capture is slow.",
     "Careful storm (25): Moss Hill in 10.8 min after the storm order, 15 USSR lost (full storm: 28-39). Motorize from the start: no capture in 28 min - trucks only for long marches next."),
    (5, "fixes", "19 Oct, from 07:55",
     ["Doctrine memory per match and side (reports carry the server's match id).",
      "'Bled out' counts every squad sent to the objective; the stall clock starts when the force gets within 900 m.",
      "Capture points and 'being seized' in the situation report; never call off an assault while the base is being seized."],
     "Two matches with the same strategist reset each other; Everon's objectives are 1.4 km apart.",
     "Headless USSR doctrine 3-2 at the end (Farm 50 s before the whistle); Everon US 2-2 with Military Depot taken 3 min after the storm."),
    (4, "storm", "19 Oct, from 05:53",
     ["Storm: 4 min into the assault, with 60% of the force there, the attack orders get a player order's priority and the squads already sent are re-ordered.",
      "Camera: a storm shot, and a cut to FPV drones as soon as they are airborne."],
     "Squads stopped 300-600 m short under fire (Moss Hill: 40-65 soldiers at 270-600 m for 23 min).",
     "Moss Hill in every clean match at 15-20 min; headless USSR doctrine 3-2 and 2-1; costlier: 30-45 lost a match."),
    (3, "commit", "19 Oct, from 04:52",
     ["Commit: 2 of AI Conflict's 4 defender squads join the assault while none of our bases is being captured.",
      "The attacking force counted from AI Conflict's own orders; Arland's USSR main base is 430 m from Airport Base, so the old count was the home garrison."],
     "Assaults trickled in: squads refill one at a time and defenders never attack.",
     "Commits in every doctrine match (6-10 soldiers each); still no USSR capture headless until storm."),
    (2, "attack doctrine", "19 Oct, from 03:45",
     ["Arma 3's attack doctrine as the strategist: gather at the nearest base, then assault; an assault that stops gaining ground is called off.",
      "Only bases AI Conflict can attack; Gemini picks the objective (llm-phased) or our rules do (phased).",
      "Camera: assault shots for fights against FIA garrisons."],
     "Strategists picked bases out of reach; squads stood near Airport Base for 15 min without taking it.",
     "On screen the USSR won 3-2 with drones; headless the doctrine didn't beat AI Conflict yet."),
    (1, "first loop", "18-19 Oct night",
     ["Head-to-head lab: a strategist per side (rules or Gemini through OpenRouter), the other side on AI Conflict alone.",
      "Watched and recorded matches with an Arma 3-style camera director and overlay; crash dialogs detected.",
      "FPV drone teams from Martin's mod for the strategist side."],
     "Martin: build the commander bot on AI Conflict and run a self-improving loop like Arma 3's.",
     "The loop ran all night: 13 recordings, 12 headless matches."),
]


def probe_rows() -> list:
    rows = []
    for run in sorted(progress.RUNS.glob("probe-*")):
        logs = sorted(run.glob("logs/*/console.log"))
        if not logs:
            continue
        text = logs[-1].read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\[ZCR\]\[STORM\] t=\d+ faction=(\S+) base=(.*?) squads=", text)
        if not m:
            continue
        side, base = m.group(1), m.group(2)
        cli = re.search(r"-zcrStormPriority (\d+)", text)
        r = probe_report.report(run, base, side)
        sm = progress.soldier_metrics(text.splitlines(), side)
        rows.append({"cover": sm.get("cover"), "ducks": sm.get("ducks"), "run": run.name, "base": base, "priority": int(cli.group(1)) if cli else 1000,
                     "motorize": "motorize=1" in text, "storm": r["storm"], "taken": r["taken"],
                     "lost_near": r["lost_near"].get(side, 0), "fia_near": r["lost_near"].get("FIA", 0),
                     "lost": r["lost"].get(side, 0)})
    return rows


def engine(changelog_url: str) -> str:
    rows = progress.rows_all()
    agg = progress.aggregate(rows)
    charts = progress.html(agg, rows)
    probes = probe_rows()
    build = max(b for b, *_ in progress.BUILDS)
    now = datetime.now()
    verdict = "".join(f"<div><b>{E(k)}</b>{E(v)}</div>" for k, v in VERDICT.items())
    cards = "".join(f'<div class="finding"><div class="head"><span class="chip {c}">{E(t)}</span><strong>{E(h)}</strong></div><p>{E(p)}</p></div>'
                    for c, t, h, p in NOW)
    ptable = "".join(
        f"<tr><td>{E(p['run'][6:-16])}</td><td>{E(p['base'])}</td><td class='num'>{p['priority']}</td><td>{'yes' if p['motorize'] else ''}</td>"
        f"<td class='num'>{'' if p['storm'] is None else round(p['storm'] / 60, 1)}</td>"
        f"<td class='num'>{'not taken' if p['taken'] is None else round((p['taken'] - p['storm']) / 60, 1) if p['storm'] else round(p['taken'] / 60, 1)}</td>"
        f"<td class='num'>{p['lost_near']}</td><td class='num'>{p['fia_near']}</td><td class='num'>{p['lost']}</td>"
        f"<td class='num'>{'' if p['cover'] is None else str(p['cover']) + '%'}</td><td class='num'>{'' if p['ducks'] is None else str(p['ducks']) + '%'}</td></tr>"
        for p in probes)
    phases = "".join(f'<div class="phase"><div class="tag">{i + 1}<small>{E(n)}</small></div><div><p>{E(t)}</p></div></div>'
                     for i, (n, t) in enumerate(PHASES))
    camera = "".join(f'<div class="btn"><b>{E(a)}</b><span>{E(b)}</span></div>' for a, b in CAMERA)
    probs = "".join(f'<div class="prob"><span class="chip {c} st">{E(c)}</span><h3>{E(t)}</h3><p>{E(d)}</p>'
                    + (f'<p class="ev">{E(ev)}</p>' if ev else "") + "</div>" for c, t, d, ev in PROBLEMS)
    nxt = "".join(f"<li>{E(n)}</li>" for n in NEXT)
    facts = "".join(f"<li>{E(f)}</li>" for f in FACTS)
    style = (HERE / "engine_style.css").read_text(encoding="utf-8")
    return f"""<title>Reforger Commander Engine</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
{style}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Reforger commander · build r{build} · {now.strftime('%d %b %Y').lstrip('0')} · {now.strftime('%H:%M')}</div>
  <h1>How it works now</h1>
  <p class="lede">Zeus Commander's commander on Arma Reforger. AI Conflict keeps running both sides' squads; on one side our strategist (our rules or Gemini) sets the plan on top, with Arma 3's attack doctrine. This page explains the current build and measures it build by build, like the <a href="{ARMA3_URL}">Arma 3 engine page</a>. Every build's history is in the <a href="{changelog_url}">changelog</a>; the night of 18-19 Oct, with its videos, is on the <a href="{STATUS_URL}">night report</a>.</p>
  <div class="verdict">{verdict}</div>
</header>
<nav class="toc" aria-label="Contents">
  <a href="#now">Now</a><a href="#progress">Progress</a><a href="#probes">Probes</a><a href="#how">How a match runs</a><a href="#commander">Commander</a><a href="#drones">Drones</a><a href="#camera">Camera</a><a href="#problems">Open problems</a><a href="#next">Next</a><a href="#engine">Engine facts</a><a href="{changelog_url}">Changelog ↗</a>
</nav>

<h2 id="now">Now <span class="ref">BUILD R{build}</span></h2>
<div class="findings">{cards}</div>

<h2 id="progress">Progress <span class="ref">MEASURED PER BUILD</span></h2>
<p>Every chart is read from the match logs: the side with our strategist against the side on AI Conflict alone. The first three are the Arma 3 page's soldier measurements with the same definitions (in-game sampler from r6, so they start with the next matches).</p>
{charts}

<h2 id="probes">Probes <span class="ref">A/B, HEADLESS</span></h2>
<p>Short headless matches to test one change: the USSR on our rules doctrine, the US on AI Conflict alone, plans every 30 s. Times in minutes; "taken" counts from the storm order. Losses within 500 m of the objective, and in the whole match.</p>
<div class="table-wrap"><table><tr><th>Probe</th><th>Objective</th><th>Storm priority</th><th>Trucks</th><th>Storm at</th><th>Taken after</th><th>Own lost there</th><th>FIA lost there</th><th>Own lost</th><th>In cover</th><th>Sitting ducks</th></tr>{ptable}</table></div>

<h2 id="how">How a match runs</h2>
<p>AI Conflict runs Reforger's Conflict mode with AI on both sides: each side has 10 squads that refill at the main base from supplies, and FIA garrisons hold the bases in between. A base counts once it is linked to the HQ by radio. Our addon sits on AI Conflict's commander: every 15 s on its tick, and every 90 s a situation report goes to the strategist bridge (Python), which answers with a plan.</p>
<pre class="mermaid">{E(FLOW)}</pre>

<h2 id="commander">The commander</h2>
<p>The plan names a main effort, its demand (how many soldiers converge on it), bases to hold or avoid, and the doctrine's orders: commit, storm, motorize. Gemini, with your doctrine text, picks the objectives (llm-phased); the phases are our rules either way.</p>
<div class="phases">{phases}</div>

<h2 id="drones">Drones</h2>
<p>{E(DRONES)}</p>

<h2 id="camera">The camera</h2>
<p>Watched matches are played by the game on screen and recorded to <code>D:\\work\\reforger-commander\\videos</code>, each with a list of moments. The director picks the next shot every 14-30 s, in this order:</p>
<div class="btns">{camera}</div>

<h2 id="problems">Open problems</h2>
{probs}

<h2 id="next">Being built and next</h2>
<ul>{nxt}</ul>

<h2 id="engine">Engine facts</h2>
<ul>{facts}</ul>

<footer>Built by <code>python lab/engine_page.py</code> from D:\\work\\reforger-commander. Research and plan: <a href="{RESEARCH_URL}">Reforger research</a>. Review notes: D:\\work\\ac-lab\\REVIEW_NOTES.md (88-109).</footer>
</div>
"""


def changelog(engine_url: str) -> str:
    style = (HERE / "engine_style.css").read_text(encoding="utf-8")
    items = []
    for b, name, when, what, why, result in CHANGELOG:
        items.append(f'<details class="ver"{" open" if b == CHANGELOG[0][0] else ""}><summary><span class="vn">r{b}</span>'
                     f'<span class="when">{E(when)}</span>{E(name)}</summary><ul>' + "".join(f"<li>{E(w)}</li>" for w in what)
                     + f'</ul><p class="why">{E(why)}</p><p class="res">{E(result)}</p></details>')
    return f"""<title>Reforger Commander Changelog</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
{style}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Reforger commander · changelog</div>
  <h1>Every build</h1>
  <p class="lede">What each build of the Reforger commander changed, why, and what the matches showed - newest first. How the current build works, with the charts: <a href="{engine_url}">engine page</a>.</p>
</header>
<h2>Builds</h2>
{''.join(items)}
<footer>Built by <code>python lab/engine_page.py</code>.</footer>
</div>
"""


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    cl = sys.argv[sys.argv.index("--changelog-url") + 1] if "--changelog-url" in sys.argv else "#"
    en = sys.argv[sys.argv.index("--engine-url") + 1] if "--engine-url" in sys.argv else "#"
    (out / "reforger_engine.html").write_text(engine(cl), encoding="utf-8")
    (out / "reforger_changelog.html").write_text(changelog(en), encoding="utf-8")
    print(f"written {out / 'reforger_engine.html'} and {out / 'reforger_changelog.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
