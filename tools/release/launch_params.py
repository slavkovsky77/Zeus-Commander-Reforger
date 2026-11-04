"""Route every launch-parameter read of the released addons through AICF_Launch (the fork's Core), so a scenario's mission
header can turn features on by default (m_sAICFLaunchParams) - players can't pass command-line parameters.

    python tools/release/launch_params.py D:/work/release/reforger-ai-conflict/AIConflictCore D:/work/release/reforger-ai-conflict/AIConflictArland \
        D:/work/release/reforger-commander/ZeusCommanderReforger D:/work/release/reforger-commander/ZCR_Alpha     # rewrite
    python tools/release/launch_params.py --check <same dirs>                       # 0 left = ok

System.IsCLIParam(x) -> AICF_Launch.Has(x), System.GetCLIParam(x, v) -> AICF_Launch.Get(x, v). AICF_Launch.Has/Get ask the
command line first, so with an empty m_sAICFLaunchParams (the lab's missions) nothing changes. Run on a release branch
after merging master (the lab's own branches keep System.* - the script is the difference, not hand edits).
"""
import re
import sys
from pathlib import Path

PATTERNS = ((re.compile(r"\bSystem\.IsCLIParam\("), "AICF_Launch.Has("), (re.compile(r"\bSystem\.GetCLIParam\("), "AICF_Launch.Get("))
SKIP = {"AICF_Launch.c"}   # the helper itself asks the command line


def main() -> int:
    check = "--check" in sys.argv
    dirs = [Path(a) for a in sys.argv[1:] if a != "--check"]
    files = changed = left = 0
    for d in dirs:
        for f in sorted(d.rglob("*.c")):
            if f.name in SKIP:
                continue
            text = f.read_bytes().decode("utf-8")   # bytes: each file keeps its own line endings
            n = sum(len(p.findall(text)) for p, _ in PATTERNS)
            if not n:
                continue
            files += 1
            if check:
                left += n
                print(f"left: {f} ({n})")
                continue
            for p, new in PATTERNS:
                text = p.sub(new, text)
            f.write_bytes(text.encode("utf-8"))
            changed += n
    print(f"{'left' if check else 'rewritten'}: {left if check else changed} reads in {files} files")
    return 1 if check and left else 0


if __name__ == "__main__":
    sys.exit(main())
