"""The fork's NOTICE (Apache-2.0 section 4: a modified file must say it was changed; the licence and the original
attribution travel with every copy). Written to the fork's root (NOTICE.md) and into the two shipped addon folders
(NOTICE.txt), from git: every file changed or added since the fork point.

    python tools/release/fork_notice.py D:/work/release/reforger-ai-conflict
"""
import subprocess
import sys
from pathlib import Path

FORK_POINT = "8a790b77e6d78171208b9f7771e2c12c8c5dced1"   # Ishafel's "Merge pull request #64" (17 Oct 2026), before our first commit
SHIPPED = ("AIConflictCore", "AIConflictArland")

HEAD = """# NOTICE - AI Conflict, Zeus Commander edition

This is a modified version of **Arma Reforger AI Conflict** by **Ishafel** and its contributors,
https://github.com/Ishafel/Arma-Reforger-AI-Conflict, licensed under the Apache License, Version 2.0 (LICENSE /
license.txt next to this file). The original copyright and licence notices are kept unchanged.

Modified by slavkovsky77 for Zeus Commander Reforger, from 19 October 2026, on top of AI Conflict as of
17 October 2026 (commit 8a790b7, after release 0.1.29). This edition is not made or endorsed by Ishafel. It uses its own
addon GUIDs (Core CF39E4A7CCBBF845, Arland ACAA98B674F022BB) and must not be loaded together with the original AI
Conflict.

What changed, in short: launch parameters for Zeus Commander's commander (squads per side, fireteam size, the one-point
battle), attack plans and live plans per team (routes through cover, drop points, wait/go), a second wave from the
home-defence teams, soldiers stuck in rocks freed, rides that wait for their team and leave a base one at a time,
contact dismounts near the target, the one-point capture rule for both sides, fortifications first at a held point,
a depot way-out check spread over frames, a scenario's own launch parameters (AICF_Launch, m_sAICFLaunchParams).
Changes inside existing files are marked in comments ("ZCR, <date>").

## Files changed (M) or added (A) since the fork point
"""


def main() -> int:
    fork = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/work/release/reforger-ai-conflict")
    out = subprocess.run(["git", "diff", "--name-status", FORK_POINT, "--", *SHIPPED], cwd=fork, capture_output=True, text=True,
                         check=True).stdout.splitlines()
    new = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", *SHIPPED], cwd=fork, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    rows = sorted({tuple(l.split("\t", 1)) for l in out if "\t" in l} | {("A", n) for n in new}, key=lambda r: r[1])
    rows = [r for r in rows if not r[1].endswith(("NOTICE.txt", "resourceDatabase.rdb"))]
    body = HEAD + "\n".join(f"- {s} `{p}`" for s, p in rows) + "\n"
    (fork / "NOTICE.md").write_text(body, encoding="utf-8")
    for addon in SHIPPED:
        mine = [r for r in rows if r[1].startswith(addon + "/")]
        text = HEAD.replace("# NOTICE", "NOTICE") + "\n".join(f"- {s} {p}" for s, p in mine) + "\n"
        (fork / addon / "NOTICE.txt").write_text(text, encoding="utf-8")
    print(f"{len(rows)} files listed: {sum(r[0] == 'M' for r in rows)} changed, {sum(r[0] == 'A' for r in rows)} added")
    return 0


if __name__ == "__main__":
    sys.exit(main())
