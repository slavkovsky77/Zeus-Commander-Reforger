"""The bridge between the game and the strategist.

    python lab/bridge.py                       # lab/bridge.local.json, else lab/bridge.example.json
    python lab/bridge.py --config my.json

The game server (ZCR_Strategist, started with -zcrBridge=http://127.0.0.1:8765) POSTs a side's
situation report to /plan every 90 s. The bridge asks the configured strategist - our rules
doctrine, Gemini or Claude - checks the answer against the report, and returns the plan as plain
lines. If the model fails, is late or answers nonsense, the rules doctrine answers instead
(source=doctrine-fallback). Every round is logged to .runtime/bridge/<date>.jsonl: report, prompt
answer, plan, problems and timing - the lab reads it, and replay.py re-runs it offline.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import doctrine  # noqa: E402
import providers  # noqa: E402
from plan import to_lines, validate  # noqa: E402

ROOT = HERE.parent


def load_config(path: str = "") -> dict:
    for p in [Path(path)] if path else [HERE / "bridge.local.json", HERE / "bridge.example.json"]:
        if p.is_file():
            cfg = json.loads(p.read_text(encoding="utf-8"))
            cfg["_path"] = str(p)
            return cfg
    raise FileNotFoundError("no bridge config")


def doctrine_text(cfg: dict, faction: str) -> str:
    p = ROOT / cfg.get("doctrines_dir", "doctrines") / f"{faction}.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


class Strategist:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.provider = providers.make(cfg)
        self.log_dir = ROOT / cfg.get("log_dir", ".runtime/bridge")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def plan(self, report: dict) -> str:
        faction = report.get("faction", "?")
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "faction": faction, "t": report.get("t"),
                 "round": report.get("round"), "provider": self.provider.name, "report": report}
        source = self.provider.name
        try:
            decision, raw, seconds = providers.timed(self.provider, report, doctrine_text(self.cfg, faction))
            entry.update(raw=raw, seconds=seconds, decision=decision)
            clean, problems = validate(decision, report)
            if clean["main_effort"] is None and self.provider.name != "doctrine":
                raise ValueError("; ".join(problems) or "no main effort")
        except Exception as e:   # the model failed: our doctrine answers
            entry["error"] = f"{type(e).__name__}: {e}"
            source = "doctrine-fallback"
            clean, problems = validate(doctrine.decide(report), report)
        entry.update(plan=clean, problems=problems, source=source)
        lines = to_lines(clean, source)
        entry["answer"] = lines
        with open(self.log_dir / f"{datetime.now():%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"{entry['at']} {faction} t={report.get('t')} {source}: {clean.get('intent')}"
              + (f"  [{entry['error']}]" if "error" in entry else ""), flush=True)
        return lines


def make_handler(strategist: Strategist):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, text: str):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(200, f"ok provider={strategist.provider.name}\n") if self.path == "/health" else self._send(404, "no\n")

        def do_POST(self):
            if self.path.rstrip("/") != "/plan":
                return self._send(404, "no\n")
            n = int(self.headers.get("content-length", 0))
            try:
                report = json.loads(self.rfile.read(n).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                return self._send(400, f"error bad report: {e}\n")
            self._send(200, strategist.plan(report))

        def log_message(self, *args):
            pass

    return Handler


def serve(cfg: dict) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", int(cfg.get("port", 8765))), make_handler(Strategist(cfg)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="")
    ap.add_argument("--port", type=int, default=0, help="override the config's port")
    ap.add_argument("--provider", default="", help="override the config's provider (e.g. doctrine)")
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.port:
        cfg["port"] = a.port
    if a.provider:
        cfg["provider"] = a.provider
    server = serve(cfg)
    print(f"bridge on http://127.0.0.1:{server.server_port} - strategist {cfg.get('provider', 'doctrine')}"
          f" {cfg.get('model', '')} (config {cfg['_path']})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
