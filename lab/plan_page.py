"""The plan page: Martin's wishes by theme with their status, from PLAN.md - the Reforger counterpart of
the Arma 3 overview by theme (ac-lab REVIEW_NOTES.md).

    python lab/plan_page.py <out_dir> [--engine-url URL] [--changelog-url URL]

Writes <out_dir>/reforger_plan.html. PLAN.md lines: "## Theme", then "- [Status] wish (notes) | where it stands".
"""
import argparse
import html
import re
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


def page(themes: list, engine_url: str, changelog_url: str) -> str:
    style = (HERE / "engine_style.css").read_text(encoding="utf-8")
    now = datetime.now()
    items = [i for _, its in themes for i in its]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ORDER}
    summary = " · ".join(f"{n} {s.lower()}" for s, n in counts.items() if n)
    nxt = [i for i in items if i["status"] in ("In progress", "Todo", "Measure")]
    toc = "".join(f'<a href="#t{k}">{E(t)}</a>' for k, (t, _) in enumerate(themes))
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
