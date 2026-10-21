"""The plan page: Martin's wishes by theme with their status, from PLAN.md - the Reforger counterpart of
the Arma 3 overview by theme (ac-lab REVIEW_NOTES.md).

    python lab/plan_page.py <out_dir> [--engine-url URL] [--changelog-url URL]

Writes <out_dir>/reforger_plan.html. PLAN.md lines: "## Theme", then "- [Status] wish (notes) | where it stands".
"""
import argparse
import html
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
E = html.escape
CHIP = {"Done": "good", "Fixed": "good", "In progress": "design", "Todo": "risk", "Measure": "risk"}
ORDER = ["In progress", "Todo", "Measure", "Done", "Fixed"]


def parse(text: str) -> list:
    themes = []
    for line in text.splitlines():
        if line.startswith("## "):
            themes.append((line[3:].strip(), []))
            continue
        m = re.match(r"- \[(.+?)\] (.+?)(?: \(([\d, -]+)\))?(?: \| (.*))?$", line.strip())
        if m and themes:
            themes[-1][1].append({"status": m.group(1), "wish": m.group(2), "notes": m.group(3) or "", "now": m.group(4) or ""})
    return themes


sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
NOTES = config.path("paths.notes")   # lab/lab.toml + lab/lab.local.toml
FIRST_REFORGER_NOTE = 88
BUG_WORDS = ("bug", "fell", "falling", "stuck", "stopped", "don't work", "crash", "can't connect", "broken", "desktop", "sucks", "lost")


def review_notes() -> list:
    """Martin's remarks and the lab's findings from REVIEW_NOTES.md (Reforger: note 88 on)."""
    out = []
    if not NOTES.exists():
        return out
    for line in NOTES.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (\d+) \| (.*?) \| (.*) \|\s*$", line)
        if not m or int(m.group(1)) < FIRST_REFORGER_NOTE:
            continue
        n, text, status = int(m.group(1)), m.group(2), m.group(3)
        tag = ""
        t = re.match(r"^\((Reforger[^)]*)\) ?(.*)$", text)
        if t:
            tag, text = t.group(1), t.group(2)
        word = status.split(" - ")[0].split(" (")[0].strip().lower()
        chip = ("Done" if word.startswith(("done", "fixed", "built", "solved", "answered", "checked", "found and fixed"))
                else "In progress" if word.startswith(("in progress", "working", "running", "first step", "changed", "promising"))
                else "Todo" if word.startswith(("planned", "to measure", "todo", "to do", "noted"))
                else "Found")
        mine = any(k in tag for k in ("finding", "result", "bug", "for martin", "for the fpv"))
        fixed = word.startswith(("fixed", "found and fixed"))
        kind = ("bug" if "bug" in tag or (mine and fixed) or (not mine and any(w in text.lower() for w in BUG_WORDS))
                else "finding" if mine else "wish")
        out.append({"n": n, "text": text, "status": status, "chip": chip, "kind": kind})
    return out


def note_rows(items: list) -> str:
    rows = []
    for i in sorted(items, key=lambda x: -x["n"]):
        detail = i["status"].split(" - ", 1)[1] if " - " in i["status"] else i["status"]
        rows.append(f'<div class="prob"><span class="chip st {CHIP.get(i["chip"], "design")}">{E(i["chip"])}</span>'
                    f'<h3>{E(i["text"])}</h3><p>{E(detail)}</p><p><span class="ev">review note {i["n"]}</span></p></div>')
    return "".join(rows)


def page(themes: list, engine_url: str, changelog_url: str) -> str:
    style = (HERE / "engine_style.css").read_text(encoding="utf-8")
    now = datetime.now()
    items = [i for _, its in themes for i in its]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ORDER}
    summary = " · ".join(f"{n} {s.lower()}" for s, n in counts.items() if n)
    nxt = [i for i in items if i["status"] in ("In progress", "Todo", "Measure")]
    toc = '<a href="#remarks">Your remarks</a><a href="#bugs">Bugs</a>' + "".join(f'<a href="#t{k}">{E(t)}</a>' for k, (t, _) in enumerate(themes))
    nts = review_notes()
    wishes = [i for i in nts if i["kind"] == "wish"]
    bugs = [i for i in nts if i["kind"] == "bug"]
    found = [i for i in nts if i["kind"] == "finding"]
    open_w = sum(1 for i in wishes if i["chip"] != "Done")
    open_b = sum(1 for i in bugs if i["chip"] != "Done")
    remarks = (f'<h2 id="remarks">Your remarks <span class="ref">{len(wishes)} · {open_w} OPEN</span></h2>'
               '<p>Everything you asked for or remarked on while watching, newest first, each with its review note and where it stands.</p>'
               + note_rows(wishes)
               + f'<h2 id="bugs">Bugs <span class="ref">{len(bugs)} · {open_b} OPEN</span></h2>'
               '<p>What you saw going wrong and what the lab found broken - with the cause when it is known.</p>'
               + note_rows(bugs)
               + f'<h2 id="found">What the lab found <span class="ref">{len(found)}</span></h2>'
               + note_rows(found)
               + '<h2 id="themes">The plan by theme</h2><p>The same wishes grouped by theme, with what is being built for each.</p>')
    body = []
    for k, (title, its) in enumerate(themes):
        open_n = sum(1 for i in its if i["status"] not in ("Done", "Fixed"))
        body.append(f'<h2 id="t{k}">{E(title)} <span class="ref">{len(its) - open_n} DONE · {open_n} OPEN</span></h2>')
        for i in sorted(its, key=lambda x: ORDER.index(x["status"]) if x["status"] in ORDER else 9):
            notes = f'<span class="ev">review notes {E(i["notes"])}</span>' if i["notes"] else ""
            body.append(f'<div class="prob"><span class="chip st {CHIP.get(i["status"], "design")}">{E(i["status"])}</span>'
                        f'<h3>{E(i["wish"])}</h3><p>{E(i["now"])}</p><p>{notes}</p></div>')
    nxt_html = "".join(f'<li><span class="chip {CHIP.get(i["status"], "design")}">{E(i["status"])}</span> {E(i["wish"])}</li>' for i in nxt)
    return f"""<title>Reforger Commander Plan</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
{style}
.next li {{ margin-block: 6px; }}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Reforger commander · plan · {now.strftime('%d %b %Y').lstrip('0')} · {now.strftime('%H:%M')}</div>
  <h1>The plan</h1>
  <p class="lede">Your wishes and remarks for the Reforger commander bot, by theme, with where each stands - like the Arma 3 overview. Every remark also has a numbered review note (ac-lab REVIEW_NOTES.md). How it works and what it measures: the <a href="{engine_url}">engine page</a>; every build: the <a href="{changelog_url}">changelog</a>.</p>
  <div class="verdict"><div><b>Where it stands</b>{E(summary)}</div><div><b>Being built now</b>{E("; ".join(i["wish"] for i in items if i["status"] == "In progress")[:240])}</div></div>
</header>
<nav class="toc" aria-label="Themes">{toc}<a href="#open">Open items</a></nav>
{remarks}
{''.join(body)}
<h2 id="open">Open items <span class="ref">{len(nxt)}</span></h2>
<ul class="next">{nxt_html}</ul>
<footer>Built by <code>python lab/plan_page.py</code> from D:\\work\\reforger-commander\\PLAN.md.</footer>
</div>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--engine-url", default="https://claude.ai/artifact/XQaVotVAZrcuFPyjzSfodM")
    ap.add_argument("--changelog-url", default="https://claude.ai/artifact/UgVDgk72Grknr7NeoLSzwF")
    a = ap.parse_args()
    themes = parse((ROOT / "PLAN.md").read_text(encoding="utf-8"))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "reforger_plan.html").write_text(page(themes, a.engine_url, a.changelog_url), encoding="utf-8")
    print(f"written {out / 'reforger_plan.html'}: {sum(len(i) for _, i in themes)} items in {len(themes)} themes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
