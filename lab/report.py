"""Martin's good and bad reports while he watches (19 Oct: "mark the timestamp and the unit I am looking
at, so you have sufficient logs and don't guess"). Gathers the evidence for one remark into
.runtime/reports/NNN-good|bad/ and files it as a numbered review note:

    python lab/report.py bad "following USSR team A3: crossing an open field where cover was available"
    python lab/report.py good "this drone attack and the reaction getting out of the car was great"
    python lab/report.py bad "..." --at 23:41:05        # the moment, if not "just now"

The moment: the latest REPORT button press (in-game, [ZCR][REPORT]) of the last 5 minutes, else 30 s
before the remark was written. From the watched match running then (or the last one):
  - summary.md   the remark, the moment (wall clock and game time), the caption on screen then,
                 the REPORT lines, the team named in the remark (team A3) or shown, the scorecard
  - log.txt      the commander's lines from 90 s before to 15 s after, and every line of the named team
  - frame_*.jpg  frames from the recording at -10 s, the moment and +5 s
Prints the folder; Claude reads it, looks at the frames and writes the analysis into the note.
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / ".runtime" / "runs"
REPORTS = ROOT / ".runtime" / "reports"
VIDEOS = ROOT / "videos"
WATCH_LOG = ROOT / ".runtime" / "watch_day.out"
NOTES = Path("D:/work/ac-lab/REVIEW_NOTES.md")
CLOCK = re.compile(r"^(\d\d):(\d\d):(\d\d)\.\d+")


def started(run: Path) -> datetime:
    m = re.search(r"-(\d{8})-(\d{6})$", run.name)
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")


def watched_at(moment: datetime) -> Path:
    """The watched match running at 'moment': the last one started before it."""
    runs = [r for r in RUNS.iterdir() if r.is_dir() and re.match(r"w\d+-.*-solo-\d{8}-\d{6}$", r.name)
            and list(r.glob("logs/*/console.log")) and started(r) <= moment]
    return max(runs, key=started)


def wall(line: str, start: datetime):
    """A log line's wall clock time; a match running over midnight goes on into the next day."""
    m = CLOCK.match(line)
    if not m:
        return None
    t = start.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=int(m.group(3)), microsecond=0)
    if t < start - timedelta(minutes=5):
        t += timedelta(days=1)
    return t


def recording_of(run: Path):
    """(video file, wall clock when its recording started) for the watched match in 'run': the
    recording of its label that started within 5 minutes after the match (labels repeat on restarts)."""
    label = run.name.split("-solo-")[0]
    begin = started(run)
    if not WATCH_LOG.exists():
        return None, None
    for line in WATCH_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"(\d\d:\d\d:\d\d) recording (\S+)\.mkv", line)
        if not m or label not in m.group(2):
            continue
        hh, mm, ss = map(int, m.group(1).split(":"))
        at = begin.replace(hour=hh, minute=mm, second=ss)
        if at < begin - timedelta(minutes=5):
            at += timedelta(days=1)
        if timedelta(0) <= at - begin <= timedelta(minutes=5):
            for ext in (".mp4", ".mkv"):
                if (VIDEOS / (m.group(2) + ext)).exists():
                    return VIDEOS / (m.group(2) + ext), at
            return None, at
    return None, None


def next_number() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    nums = [int(p.name.split("-")[0]) for p in REPORTS.iterdir() if p.name.split("-")[0].isdigit()]
    return max(nums, default=0) + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["good", "bad"])
    ap.add_argument("text")
    ap.add_argument("--at", default="", help="the moment, HH:MM:SS (wall clock); default: the latest REPORT or 30 s ago")
    a = ap.parse_args()

    now = datetime.now().replace(microsecond=0)
    # The moment: --at (today, or yesterday if that time is still ahead), else the latest REPORT press
    # of the last 5 minutes in the match running now, else 30 s before the remark.
    moment, how = None, ""
    if a.at:
        hh, mm, ss = map(int, a.at.split(":"))
        moment, how = now.replace(hour=hh, minute=mm, second=ss), "given"
        if moment > now:
            moment -= timedelta(days=1)
    run = watched_at(moment or now)
    day = started(run)
    log = sorted(run.glob("logs/*/console.log"))[-1]
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    if not moment:
        for line in reversed(lines):
            if "[ZCR][REPORT]" in line and " clock=" in line:
                t = wall(line, day)
                if t and now - t < timedelta(minutes=5):
                    moment, how = t, "REPORT button"
                break
    if not moment:
        moment, how = now - timedelta(seconds=30), "30 s before the remark"

    # The team named in the remark ("team A3") or in the caption on screen.
    team = re.search(r"team ([A-Z]\d+)", a.text, re.I)
    caption, game_t, reports = "", "", []
    window = []
    for line in lines:
        t = wall(line, day)
        if not t:
            continue
        if moment - timedelta(seconds=90) <= t <= moment + timedelta(seconds=15):
            if "[ZCR]" in line:
                window.append(line)
            if "[ZCR][CAM]" in line and " label=" in line and t <= moment:
                caption = line.split(" label=", 1)[1]
            if "[ZCR][REPORT]" in line:
                reports.append(line)
            gt = re.search(r"\[ZCR\]\[[A-Z]+\] t=(\d+)", line)
            if gt and t <= moment:
                game_t = gt.group(1)
    if not team:
        team = re.search(r"team ([A-Z]\d+)", caption)
    key = team.group(1).upper() if team else ""
    team_lines = [l for l in lines if key and (f"slot={key} " in l or f"team {key}" in l or f"team={key}" in l)]

    n = next_number()
    folder = REPORTS / f"{n:03d}-{a.kind}"
    folder.mkdir(parents=True)
    (folder / "log.txt").write_text("\n".join(["# commander lines, 90 s before to 15 s after"] + window
                                              + ["", f"# every line of team {key}" if key else "# no team named"] + team_lines[-400:]),
                                     encoding="utf-8")
    video, rec_start = recording_of(run)
    frames = []
    if video and rec_start:
        for d in (-10, 0, 5):
            off = (moment - rec_start).total_seconds() + d
            if off < 0:
                continue
            out = folder / f"frame_{'+' if d >= 0 else ''}{d}s.jpg"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{off:.1f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=1600:-2", str(out)], timeout=60)
            if out.exists():
                frames.append(out.name)
    card = ""
    try:
        sys.path.insert(0, str(ROOT / "lab"))
        import scorecard
        text, _ = scorecard.report(scorecard.measure(run))
        card = text
    except Exception as e:
        card = f"(scorecard: {e})"
    summary = [
        f"# Report {n} ({a.kind}): {a.text}",
        "",
        f"- match: {run.name}",
        f"- moment: {moment:%H:%M:%S} wall clock ({how}), game t={game_t or '?'} s",
        f"- caption on screen then: {caption or '?'}",
        f"- team: {key or '-'} ({len(team_lines)} lines)",
        f"- recording: {video.name if video else '-'}; frames: {', '.join(frames) or '-'}",
        "",
        "REPORT button lines:" if reports else "No REPORT button press near the moment.",
        *[f"    {r.split('[ZCR][REPORT] ', 1)[-1]}" for r in reports],
        "",
        "Scorecard of the match so far:",
        *[f"    {l}" for l in card.splitlines()],
        "",
        "## Analysis",
        "(to be written)",
    ]
    (folder / "summary.md").write_text("\n".join(summary), encoding="utf-8")

    # The numbered review note.
    note_n = 0
    if NOTES.exists():
        nums = [int(m.group(1)) for m in re.finditer(r"^\| (\d+) \|", NOTES.read_text(encoding="utf-8"), re.M)]
        note_n = max(nums, default=0) + 1
        kind = "good report - keep" if a.kind == "good" else "bad report"
        with open(NOTES, "a", encoding="utf-8") as f:
            f.write(f"| {note_n} | (Reforger, {kind}) {a.text} | reported ({moment:%d %b %H:%M:%S}, {run.name}, game t={game_t or '?'} s; "
                    f"on screen: {caption[:120] or '?'}; evidence .runtime/reports/{folder.name}) - analysis to follow |\n")
    print(f"report {n} -> {folder}")
    print(f"review note {note_n}")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
