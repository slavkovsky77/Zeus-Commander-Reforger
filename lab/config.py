"""Where things are on this machine, for every lab tool: lab/lab.toml (the defaults, committed) overlaid
by lab/lab.local.toml (yours, not committed - copy lab/lab.local.example.toml and fill it in).

    import config
    config.path("paths.ai_conflict")      # a Path; relative paths are taken from the repo root
    config.get("pages.engine", "")        # any value, with a default

    python lab/config.py                  # prints the merged settings and checks the paths exist
"""
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
_cache = None


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load() -> dict:
    global _cache
    if _cache is None:
        data = {}
        for name in ("lab.toml", "lab.local.toml"):
            f = HERE / name
            if f.exists():
                with open(f, "rb") as fh:
                    data = _merge(data, tomllib.load(fh))
        _cache = data
    return _cache


def get(key: str, default=None):
    node = load()
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def path(key: str, default: str = "") -> Path:
    p = Path(get(key, default))
    return p if p.is_absolute() else (ROOT / p).resolve()


def paths(key: str) -> list:
    return [str(Path(p) if Path(p).is_absolute() else (ROOT / p).resolve()) for p in get(key, [])]


def main() -> int:
    bad = 0
    for section, values in load().items():
        print(f"[{section}]")
        for k, v in values.items():
            print(f"  {k} = {v}")
    checks = [("paths.steam", path("paths.steam") / "Arma Reforger"),
              ("paths.steam (server tool)", path("paths.steam") / "Arma Reforger Server"),
              ("paths.ai_conflict", path("paths.ai_conflict") / "AIConflictCore")]
    checks += [(f"paths.mod_dirs[{i}]", Path(p)) for i, p in enumerate(paths("paths.mod_dirs"))]
    for name, p in checks:
        ok = p.exists()
        bad += not ok
        print(f"{'ok  ' if ok else 'MISSING'} {name}: {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
