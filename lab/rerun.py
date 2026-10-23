"""Replay a past run on the code it ran (Martin, 23 Oct: "are we making these experiments reproducible?").

    python lab/rerun.py drivetest-headon-default-p2148-20261023-031226
    python lab/rerun.py D:\\work\\reforger-commander\\.runtime\\runs\\guntest-storm-spotfar-p2152-20261023-161515

Reads the run's run.json (written by lab/reforger.py: arguments, command, git commit, dirty), checks the commit out in a
temporary copy when it isn't the current one (git worktree D:\\work\\zcr-rerun-<commit>), plays the same map, minutes,
flags and mods headless on port 2168, and prints the old and the new summary side by side. The game's AI and physics
have chance in them, so numbers differ run to run - compare them with the spread of the setup's other runs.
A run that changed files without committing them (dirty) can't be replayed exactly; it says so.
"""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 2168


def find(run: str) -> Path:
    p = Path(run)
    if p.is_dir():
        return p
    for base in [ROOT] + sorted(Path("D:/work").glob("zcr-*")) + [Path("D:/work/reforger-commander")]:
        q = base / ".runtime" / "runs" / run
        if q.is_dir():
            return q
    raise SystemExit(f"no run folder {run}")


def summarizer(label: str):
    name = "guntest" if label.startswith("guntest") else "drivetest"
    spec = importlib.util.spec_from_file_location(name, ROOT / "lab" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    a = ap.parse_args()
    old = find(a.run)
    meta_path = old / "run.json"
    if not meta_path.is_file():
        print(f"{old.name} has no run.json (runs before 23 Oct 16:30 didn't save one)")
        return 1
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    args, commit = meta["args"], meta.get("commit", "")
    if meta.get("dirty"):
        print("note: that run had uncommitted changes - the replay uses its commit without them")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    repo = ROOT
    if commit and commit != head:
        repo = Path(f"D:/work/zcr-rerun-{commit[:8]}")
        if not repo.is_dir():
            subprocess.run(["git", "worktree", "add", "--detach", str(repo), commit], cwd=str(ROOT), check=True)
            for rel in ("lab/lab.local.toml", "addons_local/ZCRRoadPrice_3B9F2C4D5E6A7B81/resourceDatabase.rdb"):
                if (ROOT / rel).is_file():
                    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / rel, repo / rel)
        print(f"replaying on commit {commit[:12]} in {repo}")
    label = f"rerun-{args['label']}"
    argv = [sys.executable, "-u", str(repo / "lab" / "reforger.py"), "--map", args["map"], "--minutes", str(args["minutes"]), "--label", label,
            "--port", str(PORT), "--us", args.get("us") or "none", "--ussr", args.get("ussr") or "none", "--extra", args.get("extra", "")]
    if args.get("mods"):
        argv += ["--mods", args["mods"]]
    if args.get("armour"):
        argv += ["--armour"]
    subprocess.run(argv, cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    new = sorted((repo / ".runtime" / "runs").glob(f"{label}-*"))[-1]
    mod = summarizer(args["label"])
    before = mod.summarize(old, "", "")
    after = mod.summarize(new, "", "")
    keys = [k for k in before if isinstance(before.get(k), (int, float)) and not isinstance(before.get(k), bool)]
    print(f"{'':22} {'then':>10} {'now':>10}")
    for k in keys:
        print(f"{k:22} {str(before.get(k)):>10} {str(after.get(k)):>10}")
    print(f"then: {old}\nnow:  {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
