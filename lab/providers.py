"""The strategist behind the bridge: our rules doctrine, or an LLM (Gemini, Claude, or any model
through OpenRouter).

The LLM gets the side's doctrine text (doctrines/<FACTION>.md, Martin's to write and change) and a
compact situation report, and must answer with one JSON object (see SCHEMA). The API key comes
from an environment variable named in the bridge config - it is never stored in the repo.
"""
import json
import os
import re
import time
import urllib.request

import doctrine
from plan import bases_by_id

SCHEMA = """Answer with exactly one JSON object and nothing else:
{"intent": "<one sentence, your commander's intent, shown to the viewers>",
 "main_effort": <base id to attack or reinforce with most force>,
 "supporting": [<at most 2 base ids for supporting attacks>],
 "hold": [<at most 3 of OUR base ids to hold firmly>],
 "avoid": [<base ids not to waste force on now>],
 "concentration": "normal" or "heavy"}"""

SYSTEM = """You are the operational commander of the {faction} side in an Arma Reforger Conflict match
(a military simulation game). Bases are captured by holding them with soldiers; a base counts only
while linked to your HQ through the radio network (the links). You don't move units yourself: every
1-2 minutes you set the main effort and priorities, and your staff assigns about ten squads of up to
ten soldiers to them, with trucks and APCs. You only know what your side has seen: every base's
owner and links, your own bases' supplies and threats, and your own squads.

Your doctrine:
{doctrine}

{schema}"""


def report_text(report: dict) -> str:
    """The situation report as compact text for the model."""
    faction = report.get("faction")
    lines = [f"Side: {faction}. Game time: {report.get('t', 0) // 60} min. Current intent: {report.get('intent') or 'none'}.", "", "Bases (id, name, owner, links):"]
    for b in report.get("bases", []):
        tags = [t for t, on in (("HQ", b.get("hq")), ("objective", b.get("objective")),
                               ("UNDER THREAT", b.get("threatened"))) if on]
        extra = f" supplies {b['supplies']}" if "supplies" in b else ""
        lines.append(f"  {b['id']}: {b.get('name') or '?'} - {b.get('owner') or 'neutral'}"
                     f"{' (' + ', '.join(tags) + ')' if tags else ''}{extra}; links {b.get('links', [])};"
                     f" at {b.get('x')},{b.get('z')}")
    known = bases_by_id(report)
    lines += ["", "Our squads (slot, role, soldiers alive/size, heading for):"]
    for s in report.get("squads", []):
        target = known.get(s.get("target"), {}).get("name") or ("-" if s.get("target", -1) < 0 else s["target"])
        where = f" at {s['x']},{s['z']}" if "x" in s else ""
        lines.append(f"  {s['slot']}: {s.get('role')} {s.get('alive')}/{s.get('size')}"
                     f"{'' if s.get('ready') else ' (not ready)'}, heading for {target}{where}")
    return "\n".join(lines)


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def extract_json(text: str) -> dict:
    """The first JSON object in a model's answer (it may wrap it in a code fence)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the answer")
    return json.loads(m.group(0))


class Rules:
    name = "doctrine"

    def __init__(self, cfg: dict):
        pass

    def decide(self, report: dict, doctrine_text: str) -> tuple:
        return doctrine.decide(report), ""


class _LLM:
    name = "llm"

    def __init__(self, cfg: dict):
        self.model = cfg.get("model") or ""
        # The key: an environment variable, else a file that holds it (e.g. one another tool of
        # yours already keeps). Only its name or path is in the config, never the key.
        self.key = os.environ.get(cfg.get("api_key_env", ""), "") if cfg.get("api_key_env") else ""
        if not self.key and cfg.get("api_key_file"):
            try:
                text = open(cfg["api_key_file"], encoding="utf-8").read()
                self.key = next((l.strip() for l in text.splitlines() if l.strip()), "")
            except OSError:
                pass
        self.timeout = float(cfg.get("timeout_s", 25))
        if not self.model:
            raise ValueError(f"{self.name}: set \"model\" in the bridge config")
        if not self.key:
            raise ValueError(f"{self.name}: no API key - neither environment variable {cfg.get('api_key_env')!r}"
                             f" nor file {cfg.get('api_key_file')!r} holds one")

    def prompts(self, report: dict, doctrine_text: str) -> tuple:
        system = SYSTEM.format(faction=report.get("faction"), doctrine=doctrine_text.strip() or "(none)", schema=SCHEMA)
        return system, report_text(report)

    def decide(self, report: dict, doctrine_text: str) -> tuple:
        system, user = self.prompts(report, doctrine_text)
        raw = self.ask(system, user)
        return extract_json(raw), raw


class Gemini(_LLM):
    name = "gemini"

    def ask(self, system: str, user: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        r = _post(url, {"systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": user}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}},
                  {"x-goog-api-key": self.key}, self.timeout)
        return r["candidates"][0]["content"]["parts"][0]["text"]


class Claude(_LLM):
    name = "claude"

    def ask(self, system: str, user: str) -> str:
        r = _post("https://api.anthropic.com/v1/messages",
                  {"model": self.model, "max_tokens": 800, "system": system,
                   "messages": [{"role": "user", "content": user}]},
                  {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, self.timeout)
        return "".join(part.get("text", "") for part in r.get("content", []) if part.get("type") == "text")


class OpenRouter(_LLM):
    """Any model through one OpenRouter key: "model" is OpenRouter's id, e.g.
    "google/gemini-3.8-flash" or "anthropic/claude-haiku-5.5" (https://openrouter.ai/models)."""
    name = "openrouter"

    def ask(self, system: str, user: str) -> str:
        r = _post("https://openrouter.ai/api/v1/chat/completions",
                  {"model": self.model, "temperature": 0.4, "max_tokens": 800,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                  {"authorization": f"Bearer {self.key}", "x-title": "Zeus Commander Reforger"}, self.timeout)
        if "error" in r:
            raise RuntimeError(f"openrouter: {r['error']}")
        return r["choices"][0]["message"]["content"] or ""


class PhasedRules:
    """Our rules pick the objective; the Arma 3 attack doctrine (gather, assault, fall back) runs
    it (lab/phased.py)."""
    name = "phased"

    def __init__(self, cfg: dict):
        import phased
        self.p = phased.Phased(None, self.name)

    def decide(self, report: dict, doctrine_text: str) -> tuple:
        return self.p.decide(report, doctrine_text)


class PhasedLLM:
    """The model picks the objective (only when a new one is due), the doctrine fights for it."""
    name = "llm-phased"

    def __init__(self, cfg: dict):
        import phased
        inner = dict(cfg, provider=cfg.get("llm_provider", "openrouter"))
        self.llm = PROVIDERS[inner["provider"]](inner)

        def pick(report, text):
            decision, raw = self.llm.decide(report, text)
            return decision.get("main_effort"), str(decision.get("intent", ""))[:160], raw

        self.p = phased.Phased(pick, self.name)

    def decide(self, report: dict, doctrine_text: str) -> tuple:
        return self.p.decide(report, doctrine_text)


PROVIDERS = {"doctrine": Rules, "gemini": Gemini, "claude": Claude, "openrouter": OpenRouter,
             "phased": PhasedRules, "llm-phased": PhasedLLM}


def make(cfg: dict):
    return PROVIDERS[cfg.get("provider", "doctrine")](cfg)


def timed(provider, report: dict, doctrine_text: str) -> tuple:
    t0 = time.time()
    decision, raw = provider.decide(report, doctrine_text)
    return decision, raw, round(time.time() - t0, 2)
