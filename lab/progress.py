"""How the Reforger commander progresses: measurements per build, read back from every match's server
log and situation reports - like the Arma 3 lab's progress.py.

    python lab/progress.py                 # table per build, writes .runtime/progress.json
    python lab/progress.py --html out.html # the engine page's charts (inline SVG)

A build is a milestone of the doctrine (BUILDS below), assigned to a match by its start time. Each
match is measured from the doctrine side's view - the side whose strategist is ours; the other side
runs on AI Conflict alone. Matches with AI Conflict on both sides are the control.

Per match:
  margin      bases held at the end, doctrine side minus the other
  caps        bases the doctrine side took; first_cap: minutes to its first
  assault     minutes from the doctrine side's assault order on a base to taking it
  storm       minutes from the storm order to taking it
  close6      metres from the objective of the nearest squad sent there, 6 min into the first assault
  exchange    soldiers the doctrine side killed per soldier it lost
  intensity   soldiers lost per 20 game minutes, everyone
  stuck       AI Conflict's stuck reports for the doctrine side's squads per 20 game minutes
  drones      FPV teams, strikes and kills per match (watched matches load the drone mods)
  causes      share of all losses: drone, direct fire (a killer), unknown (no killer)
  trips       truck trips AI Conflict started for the doctrine side (motorize, r6)
"""
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = ROOT / ".runtime" / "runs"
sys.path.insert(0, str(HERE))
import metrics  # noqa: E402

# (number, name, live from, what changed) - the changelog page lists the same builds.
BUILDS = [
    (1, "first loop", "2026-10-19 02:40", "Gemini or our rules pick the targets; AI Conflict does the rest"),
    (2, "attack doctrine", "2026-10-19 03:45", "Arma 3's attack doctrine: gather at the nearest base, then assault; an assault that stops gaining is called off"),
    (3, "commit", "2026-10-19 04:52", "two defender squads join the assault; the attacking force counted from AI Conflict's own orders"),
    (4, "storm", "2026-10-19 05:53", "after 4 min of assault the squads go in at a player order's priority"),
    (5, "fixes", "2026-10-19 07:55", "doctrine memory per match (two matches shared it); far objectives no longer 'bled out'"),
    (6, "motorize", "2026-10-19 10:30", "attack squads ride trucks (probes); storm priority as a setting"),
    (7, "soldier measures", "2026-10-19 12:29", "Arma 3's soldier measurements (cover, sitting ducks, stacking); careful storm by default; watch buttons"),
    (8, "drone doctrine", "2026-10-19 13:00", "drone warfare doctrine: prep fire and pressure, both sides fly drones, headless too; force and storm from what the side has seen"),
    (9, "cover layer", "2026-10-19 14:31", "soldier layer: cover in a firefight for our strategist's side (Arma 3's coverFight); drones hunt seen enemy soldiers"),
    (10, "cover with the game", "2026-10-19 15:05", "the soldier layer works with the game's own cover: holds it 20 s (the game: 5 s), asks its cover search, leaves soldiers in it alone"),
]
FAMILIES = [("arland-headless", "Arland headless"), ("arland-watched", "Arland watched"), ("everon-watched", "Everon watched")]
KEYS = ["cover", "incover", "ducks", "stacked", "drone_kills_ours", "lost_to_drones", "margin", "caps", "first_cap", "assault", "storm", "close6", "exchange", "intensity", "stuck",
        "drone_teams", "drone_strikes", "drone_kills", "cause_drone", "cause_direct", "cause_unknown", "trips"]
STAMP = re.compile(r"-(\d{8})-(\d{6})$")


def soldier_metrics(lines: list, side: str) -> dict:
    """Arma 3's soldier measurements (ZCR_Sampler, from r6): fighting from cover, sitting ducks,
    stacking - for one side's soldiers."""
    out = {}
    eng = cov = 0
    eng_g = inc = 0
    stacked = []
    deaths = ducks = 0
    for l in lines:
        if "[ZCR][EXPOSURE]" in l and f"side={side} " in l:
            f = metrics.fields(l, "[ZCR][EXPOSURE]")
            n = int(f.get("engaged", 0))
            eng += n
            cov += n * int(f.get("covered", 0))
            if "incover" in f:
                eng_g += n
                inc += n * int(f["incover"])
        elif "[ZCR][CROWD]" in l and f"side={side} " in l:
            f = metrics.fields(l, "[ZCR][CROWD]")
            # In the field (over 200 m from the main base, where recruits gather) when logged.
            if "field_stacked" in f:
                if f["field_stacked"] != "-1":
                    stacked.append(int(f["field_stacked"]))
            else:
                stacked.append(int(f.get("stacked", 0)))
        elif "[ZCR][LOSS]" in l and " stance=" in l:
            f = metrics.fields(l, "[ZCR][LOSS]")
            if f.get("side") != side or f.get("kind") != "man" or f.get("foot") != "1":
                continue
            deaths += 1
            # A sitting duck: not covered toward his killer, not under a roof, not moving.
            if f.get("covered") != "1" and f.get("roof") != "1" and f.get("moving") != "1":
                ducks += 1
    if eng:
        out["cover"] = round(cov / eng, 1)
    if eng_g:
        out["incover"] = round(inc / eng_g, 1)
    if stacked:
        out["stacked"] = round(statistics.mean(stacked), 1)
    if deaths:
        out["ducks"] = round(100 * ducks / deaths, 1)
        out["deaths_sampled"] = deaths
    return out


def build_of(started: datetime) -> int:
    n = 1
    for num, _, live, _ in BUILDS:
        if started >= datetime.strptime(live, "%Y-%m-%d %H:%M"):
            n = num
    return n


def server_runs():
    for run in sorted(RUNS.iterdir()):
        name = run.name
        if "-client-" in name or not STAMP.search(name):
            continue
        if not (name.startswith("b-") or name.startswith("probe-") or re.match(r"w\d+-", name)):
            continue
        logs = sorted(run.glob("logs/*/console.log"))
        if logs:
            yield run, logs[-1]


def strategist_sides(lines: list) -> dict:
    """{side: strategist} from the server's command line and its plan lines."""
    cli = next((l for l in lines if "CLI Params:" in l), "")
    args = cli.split("CLI Params:", 1)[-1].split()
    get = lambda k: args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else None
    default = get("-zcrBridge")
    sides = {}
    for side, key in (("US", "-zcrBridgeUS"), ("USSR", "-zcrBridgeUSSR")):
        url = get(key) or default
        if url and url != "none":
            src = Counter(metrics.fields(l, "[ZCR][PLAN]").get("source") for l in lines
                          if "[ZCR][PLAN]" in l and f"faction={side} " in l)
            src.pop("doctrine-fallback", None)
            sides[side] = src.most_common(1)[0][0] if src else "?"
    return sides


def measure_run(run: Path, log: Path):
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    m = metrics.measure(lines)
    score = m.get("score") or {}
    if not score or m["minutes"] < 10:
        return None
    started = datetime.strptime("".join(STAMP.search(run.name).groups()), "%Y%m%d%H%M%S")
    sides = strategist_sides(lines)
    if len(sides) == 2:
        return None                      # both sides ours: not a head-to-head against AI Conflict
    side = next(iter(sides), "USSR")     # control: measured as the USSR seat
    other = "US" if side == "USSR" else "USSR"
    mapname = "everon" if "everon" in run.name else "arland"
    kind = "watched" if re.match(r"w\d+-", run.name) else "probe" if run.name.startswith("probe-") else "headless"
    row = {"run": run.name, "started": started.strftime("%Y-%m-%d %H:%M"), "build": build_of(started),
           "map": mapname, "kind": kind, "family": f"{mapname}-{kind}" if sides else "control",
           "side": side, "strategist": sides.get(side, "none"), "minutes": m["minutes"]}
    row["margin"] = score.get(side, 0) - score.get(other, 0)
    cli = next((l for l in lines if "CLI Params:" in l), "").split()
    row["storm_priority"] = int(float(cli[cli.index("-zcrStormPriority") + 1])) if "-zcrStormPriority" in cli else 1000
    row["motorize"] = any("[ZCR][PLAN]" in l and f"faction={side} " in l and "motorize=1" in l for l in lines)

    # Captures, assault and storm orders, by base name.
    caps, assault_at, storm_at = {}, {}, {}
    for l in lines:
        t = None
        if "[ZCR][CAPTURE]" in l:
            f = re.search(r"t=(\d+) base=(.*?) from=(\S*) to=(\S*)", l)
            if f and f.group(4) == side:
                caps.setdefault(f.group(2), int(f.group(1)))
        elif "[ZCR][PLAN]" in l and f"faction={side} " in l and "intent=" in l:
            f = re.search(r"intent=(?:Assault on|Storming) (.*?) with ", l)
            t = metrics.fields(l, "[ZCR][PLAN]")
            if f:
                tt = re.search(r"t=(\d+)", l)
                clock_t = metrics.clock(l)
                assault_at.setdefault(f.group(1), clock_t)
        elif "[ZCR][STORM]" in l and f"faction={side} " in l and "base=" in l:
            f = re.search(r"t=(\d+) faction=\S+ base=(.*?) squads=", l)
            if f:
                storm_at.setdefault(f.group(2), int(f.group(1)))
    # Plan lines carry no match time: convert the order's clock to match seconds by the first loss/score line.
    offset = None
    for l in lines:
        if "[ZCR][SCORE]" in l:
            c = metrics.clock(l)
            t = int(metrics.fields(l, "[ZCR][SCORE]").get("t", 0))
            if c is not None:
                offset = c - t
                break
    row["caps"] = len(caps)
    row["first_cap"] = round(min(caps.values()) / 60, 1) if caps else None
    waits = [(t - (assault_at[b] - offset)) / 60 for b, t in caps.items() if b in assault_at and offset is not None]
    row["assault"] = round(statistics.mean(waits), 1) if waits else None
    storms = [(t - storm_at[b]) / 60 for b, t in caps.items() if b in storm_at]
    row["storm"] = round(statistics.mean(storms), 1) if storms else None

    # Losses: exchange, intensity, causes.
    lost = Counter()
    kills = 0
    causes = Counter()
    det = [c for c in (metrics.clock(l) for l in lines if "FPVAI: drone" in l and " detonated" in l) if c is not None]
    for l in lines:
        if "[ZCR][LOSS]" not in l:
            continue
        f = metrics.fields(l, "[ZCR][LOSS]")
        lost[f.get("side", "?")] += 1
        if f.get("killer_side") == side:
            kills += 1
        c = metrics.clock(l)
        if f.get("killer_kind", "none") == "none":
            causes["drone" if c is not None and any(0 <= c - d <= 5 for d in det) else "unknown"] += 1
        else:
            causes["direct"] += 1
    total = sum(lost.values())
    row["exchange"] = round(kills / max(lost[side], 1), 2)
    row["intensity"] = round(total / m["minutes"] * 20, 1)
    for k in ("drone", "direct", "unknown"):
        row[f"cause_{k}"] = round(100 * causes[k] / total, 1) if total else None
    stuck = sum(1 for l in lines if "GROUP_STUCK_DETECTED" in l and f"faction={side} " in l)
    row["stuck"] = round(stuck / m["minutes"] * 20, 1)
    has_drones = any("[ZCR][DRONES]" in l for l in lines)
    row["drone_teams"] = m["drone_teams"].get(side, 0) if has_drones else None
    row["drone_strikes"] = m["drone_strikes"] if has_drones else None
    row["drone_kills"] = sum(m["drone_kills"].values()) if has_drones else None
    # Both sides fly drones from r8: what our drones killed, and what we lost to theirs.
    row["drone_kills_ours"] = sum(n for s_, n in m["drone_kills"].items() if s_ != side) if has_drones else None
    row["lost_to_drones"] = m["drone_kills"].get(side, 0) if has_drones else None
    row["trips"] = sum(1 for l in lines if "][VEHICLE_REQUESTED]" in l and f"faction={side} " in l)
    row.update(soldier_metrics(lines, side))
    # AI Conflict start-up failure seen once (19 Oct 13:27): a side's barracks never built, so it
    # never recruits - such a match says nothing about the strategist.
    row["recruits"] = sum(1 for l in lines if "INFANTRY_RECRUIT_JOINED" in l and f"faction={side} " in l)
    row["recruits_other"] = sum(1 for l in lines if "INFANTRY_RECRUIT_JOINED" in l and f"faction={other} " in l)
    if m["minutes"] >= 20 and (row["recruits"] == 0 or row["recruits_other"] == 0):
        return None

    # Approach: the nearest squad sent to the first objective, 6 min after the assault order.
    row["close6"] = None
    snaps_path = run / "profile" / "zcr" / "snapshots.jsonl"
    first = min(assault_at.items(), key=lambda kv: kv[1]) if assault_at else None
    if first and offset is not None and snaps_path.exists():
        name, at = first[0], first[1] - offset
        best = None
        for line in snaps_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("faction") != side or r.get("t", 0) < at + 360:
                continue
            b = next((x for x in r.get("bases", []) if x.get("name") == name), None)
            if b is None:
                break
            cx, cz = b.get("cx", b["x"]), b.get("cz", b["z"])
            d = [math.hypot(s["x"] - cx, s["z"] - cz) for s in r.get("squads", []) if "x" in s and s.get("target") == b["id"]]
            best = round(min(d)) if d else None
            break
        row["close6"] = best
    return row


def rows_all() -> list:
    out = []
    for run, log in server_runs():
        try:
            r = measure_run(run, log)
        except Exception as e:   # one broken log must not stop the page
            print(f"skip {run.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if r:
            out.append(r)
    return out


def aggregate(rows: list) -> dict:
    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        for fam in (r["family"], "all" if r["kind"] != "probe" and r["family"] != "control" else "other"):
            for k in KEYS:
                if r.get(k) is not None:
                    agg[fam][r["build"]][k].append(r[k])
            agg[fam][r["build"]]["n"].append(1)
    return {fam: {b: {k: (len(x) if k == "n" else round(statistics.mean(x), 1)) for k, x in ks.items()}
                  for b, ks in sorted(bs.items())} for fam, bs in agg.items()}


def control_baseline(rows: list, key: str):
    vals = [r[key] for r in rows if r["family"] == "control" and r.get(key) is not None]
    return round(statistics.mean(vals), 1) if vals else None


def html(agg: dict, rows: list) -> str:
    from charts import line_chart
    builds = [b for b, *_ in BUILDS]
    notes = {b: name for b, name, *_ in BUILDS}
    charts = []

    def ser(key, fams=FAMILIES):
        return [(name, {b: ks.get(key) for b, ks in agg.get(f, {}).items()}) for f, name in fams]

    def add(title, why, series, **kw):
        used = sorted({b for _, d in series for b, v in d.items() if v is not None})
        if not used:
            return
        charts.append(f'<figure class="pfig"><figcaption><b>{title}</b> {why}</figcaption>'
                      + line_chart(title, used, series, notes={b: notes[b] for b in used}, prefix="r", **kw) + "</figure>")

    add("Fighting from cover", "Of the soldiers (with our strategist) who know an enemy within 300 m, how many have something solid within 3 m toward the nearest one, or a roof. Same measure as Arma 3, ground counts as cover. From r6.",
        ser("cover"), unit="%", ymax=60, target=(40, "target 40%"), better="higher")
    add("In the game's own cover", "Of the same soldiers, how many are at one of the game's own cover points (in cover, exposed to shoot or hidden) - what its attack logic counts as cover. From r10.",
        ser("incover"), unit="%", ymax=60, better="higher")
    add("Sitting ducks", "Of the soldiers lost on foot, how many were standing or lying still in the open: not covered toward the killer, no roof, not moving. From r6.",
        ser("ducks"), unit="%", ymax=100, target=(50, "limit 50%"), better="lower")
    add("Stacking", "Soldiers on foot in the field (over 200 m from their main base, where AI Conflict gathers its recruits) bunched up with 6 or more friends within 25 m. From r6.",
        ser("stacked"), unit="%", target=(10, "limit 10%"), better="lower")
    base_margin_ussr = control_baseline(rows, "margin")
    add("Bases won", "Bases held at the end, the side with our strategist minus the side on AI Conflict alone. On Arland the US seat starts stronger: in the controls (AI Conflict on both sides) the USSR ends "
        f"{base_margin_ussr:+} on average." if base_margin_ussr is not None else "Bases held at the end, our side minus AI Conflict's.",
        ser("margin"), ymax=3, better="higher")
    add("Bases taken", "Bases the side with our strategist took in a match (30 min, watched 28).", ser("caps"), ymax=4, better="higher")
    add("Time to the first capture", "Minutes until the side with our strategist took its first base.", ser("first_cap"), unit=" min", ymax=30, better="lower")
    add("From the assault order to the capture", "Minutes from the doctrine's assault order on a base to taking it - the Arma 3 doctrine's measure of an assault that gains ground.",
        ser("assault"), unit=" min", ymax=25, better="lower")
    add("From the storm to the capture", "Minutes from the storm order to taking the base (from r4).", ser("storm"), unit=" min", ymax=15, better="lower")
    add("How close after 6 minutes", "Metres from the objective of the nearest squad sent there, 6 minutes into the first assault. AI Conflict stages squads 400-500 m out.",
        ser("close6"), unit=" m", target=(250, "250 m"), better="lower")
    add("Exchange", "Soldiers the side with our strategist killed (FIA and enemy) per soldier it lost.", ser("exchange"), target=(1, "even trade"), better="higher")
    add("Does the fight happen", "Soldiers lost per 20 game minutes, everyone.", ser("intensity"))
    add("Stuck squads", "AI Conflict's stuck reports for the squads of the side with our strategist, per 20 game minutes.", ser("stuck"), better="lower")
    mix = [("FPV drones", {b: ks.get("cause_drone") for b, ks in agg.get("all", {}).items()}),
           ("Direct fire", {b: ks.get("cause_direct") for b, ks in agg.get("all", {}).items()}),
           ("Unknown", {b: ks.get("cause_unknown") for b, ks in agg.get("all", {}).items()})]
    add("What causes the losses", "Share of soldiers lost, all matches of each build. A death with no killer within 5 s of an FPV detonation counts as the drone's. The green band is what front-line reports give for drones (the drone warfare doctrine's aim, review note 118).",
        mix, unit="%", ymax=100, band=(70, 96, "front: drones 70-96%"))
    add("Drone exchange", "Soldiers killed by our strategist's drones, and soldiers it lost to the enemy's drones, per match (both sides fly drones from r8).",
        [("Killed by our drones", {b: ks.get("drone_kills_ours") for b, ks in agg.get("all", {}).items()}),
         ("Lost to theirs", {b: ks.get("lost_to_drones") for b, ks in agg.get("all", {}).items()})])
    add("Drones in use", "FPV teams launched, strikes and kills per match - watched matches only until r7; from r8 headless too, and both sides fly drones.",
        [("Teams", {b: ks.get("drone_teams") for b, ks in agg.get("all", {}).items()}),
         ("Strikes", {b: ks.get("drone_strikes") for b, ks in agg.get("all", {}).items()}),
         ("Kills", {b: ks.get("drone_kills") for b, ks in agg.get("all", {}).items()})], ymax=25)
    n = len([r for r in rows if r["family"] != "control" and r["kind"] != "probe"])
    nc = len([r for r in rows if r["family"] == "control"])
    np_ = len([r for r in rows if r["kind"] == "probe"])
    return (f'<p class="pnote">Measured, not estimated: {n} matches against AI Conflict, {nc} controls and {np_} probes (in the table below, not the lines), read back from the logs by '
            f'<code>python lab/progress.py</code>. Each point is the mean of that build\'s matches - most builds have 1-4, so single points jump. '
            f'Lines are per map and kind: headless (measured) and watched (recorded, with drones). Hover a point for its value.</p>'
            '<div class="pgrid">' + "".join(charts) + "</div>")


def main() -> int:
    rows = rows_all()
    agg = aggregate(rows)
    if "--html" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--html") + 1])
        out.write_text(html(agg, rows), encoding="utf-8")
        print(f"charts -> {out}")
    (ROOT / ".runtime" / "progress.json").write_text(json.dumps(
        {"generated": datetime.now().isoformat(timespec="minutes"), "matches": rows, "by_build": agg}, indent=1), encoding="utf-8")
    print(f"{len(rows)} matches -> .runtime/progress.json")
    for r in rows:
        print(f"r{r['build']} {r['run'][:44]:44} {r['side']:4} {r['strategist']:10} margin {r['margin']:+d} caps {r['caps']} "
              f"first {r['first_cap']} assault {r['assault']} storm {r['storm']} close6 {r['close6']} exch {r['exchange']} "
              f"int {r['intensity']} stuck {r['stuck']} trips {r['trips']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
