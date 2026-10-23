"""Integration tests: the saved small scenarios of lab/itests.toml, headless, with pass/fail checks (Martin, 23 Oct: "all
these tests should be reproducible - they will act as integration tests in the future, quick tests").

    python lab/itest.py                  all of them, three at a time
    python lab/itest.py storm spot-far   these
    python lab/itest.py --list           what there is
    python lab/itest.py --serial         one at a time

Checks must pass (exit code 1 if one fails); goals are reported but don't fail the run. Results: .runtime/itests/.
"""
import argparse
import importlib.util
import json
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTS = [2162, 2164, 2166]   # clear of the sub-labs (2148-2152), the night slot and the watched game (2160)


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "lab" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tests() -> list:
    return tomllib.loads((ROOT / "lab" / "itests.toml").read_text(encoding="utf-8"))["test"]


def judge(exprs: list, summary: dict) -> list:
    """Each check against the run's summary: (expression, True/False/None for 'could not be read')."""
    out = []
    env = {k: v for k, v in summary.items()}
    for e in exprs:
        try:
            out.append((e, bool(eval(e, {"__builtins__": {}}, env))))
        except Exception:
            out.append((e, None))
    return out


def run_one(test: dict, port: int) -> dict:
    started = time.time()
    if test["kind"] == "drive":
        summary = load("drivetest").run(test["track"], test.get("variant", "default"), test.get("minutes", 5), test.get("units", 6), port)
    else:
        summary = load("guntest").run(test["scenario"], test.get("variant", "default"), test.get("minutes", 5), 0, port)
    checks = judge(test.get("checks", []), summary)
    goals = judge(test.get("goals", []), summary)
    passed = "error" not in summary and all(ok for _, ok in checks)
    return {"name": test["name"], "what": test.get("what", ""), "passed": passed, "checks": checks, "goals": goals,
            "summary": summary, "seconds": round(time.time() - started)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--serial", action="store_true")
    a = ap.parse_args()
    all_tests = tests()
    if a.list:
        for t in all_tests:
            print(f"{t['name']:22} {t.get('minutes', 5):>4} min  {t.get('what', '')}")
        return 0
    chosen = [t for t in all_tests if not a.names or t["name"] in a.names]
    if not chosen:
        print("no such test; --list shows them")
        return 2
    workers = 1 if a.serial else min(len(PORTS), len(chosen))
    print(f"{len(chosen)} integration tests, {workers} at a time", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, t, PORTS[i % workers]) for i, t in enumerate(chosen)]
        for f in futures:
            r = f.result()
            results.append(r)
            mark = "PASS" if r["passed"] else "FAIL"
            failed = [e for e, ok in r["checks"] if not ok]
            goals = " ".join(f"goal {e}: {'met' if ok else 'not yet'}" for e, ok in r["goals"])
            print(f"{mark}  {r['name']:22} {r['seconds']:>4} s  {('failed: ' + '; '.join(failed)) if failed else ''} {goals}".rstrip(), flush=True)
    out = ROOT / ".runtime" / "itests"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    blob = {"at": time.strftime("%Y-%m-%d %H:%M"), "results": results}
    (out / f"{stamp}.json").write_text(json.dumps(blob, indent=1), encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(blob, indent=1), encoding="utf-8")
    passed = sum(1 for r in results if r["passed"])
    print(f"{passed} of {len(results)} passed - {out / (stamp + '.json')}", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
