"""The lab app: a live dashboard of the improvement loop, served from this PC (the lab's own files, read live).

    python lab/app/server.py                 # http://127.0.0.1:8790 - on the phone through Tailscale:
                                             #   tailscale serve --bg --http 8790 http://127.0.0.1:8790
                                             #   then http://<this PC>.<tailnet>.ts.net:8790
    python lab/app/server.py wait [--minutes 60]   # returns when the owner sends a remark (for Claude to wake on)
    python lab/app/server.py new                   # the remarks not filed yet, one JSON line each
    python lab/app/server.py file <id> --note 260 --reply "what happens with it"

Tabs: Live (the loop's step, the watched match running - a frame from its recording, score, supplies, events,
graphs over the match - and the remark box), Goals, Loop (each iteration, before -> after), Matches (with their
recordings), Crashes (lab/crashes.py and the armour stress test, lab/stress.py), Progress / Changelog / Plan (the
engine, changelog and plan pages, rebuilt every 10 minutes).
Remarks go to .runtime/inbox.jsonl; the improve skill files them at the start of each iteration.
"""
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
ROOT = LAB.parent
sys.path.insert(0, str(LAB))
import crashes  # noqa: E402
import maplayers  # noqa: E402
import monitor  # noqa: E402
sys.path.insert(0, str(HERE))
import progress_specs  # noqa: E402
import sublab  # noqa: E402
import scorecard  # noqa: E402

RUNTIME = ROOT / ".runtime"
INBOX = RUNTIME / "inbox.jsonl"
PAGES = RUNTIME / "app_pages"
VIDEOS = ROOT / "videos"
PORT = 8790


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- slow data, refreshed in the background

class MapLayers:
    """The Map tab's layers per map (lab/maplayers.py), built in a thread: the first build reads every run's log once
    (minutes), later ones only new runs. Rebuilt when asked for and older than 5 minutes."""
    data = {}
    building = set()
    lock = threading.Lock()

    @classmethod
    def get(cls, name: str, since_h: float = 0) -> dict:
        key = f"{name}:{since_h:g}"
        with cls.lock:
            d = cls.data.get(key)
            stale = not d or time.time() - d.get("_at", 0) > 300
            if stale and key not in cls.building:
                cls.building.add(key)
                threading.Thread(target=cls.build, args=(name, since_h, key), daemon=True).start()
        return d or {"map": name, "building": True}

    @classmethod
    def build(cls, name: str, since_h: float = 0, key: str = ""):
        key = key or f"{name}:{since_h:g}"
        try:
            d = maplayers.layers(name, since_h)
            d["_at"] = time.time()
            with cls.lock:
                cls.data[key] = d
        except Exception as e:
            print(f"[app] map {name}: {e}", flush=True)
        finally:
            with cls.lock:
                cls.building.discard(key)


class Slow:
    data = {"goals": [], "matches": [], "commits": [], "notes": [], "videos": [], "updated": None}
    pages_updated = None
    lock = threading.Lock()

    @classmethod
    def refresh(cls):
        out = {}
        for key, fn in (("goals", monitor.goal_rows), ("matches", lambda: monitor.match_rows(15)),
                        ("commits", monitor.commits), ("notes", lambda: monitor.notes(12)), ("videos", videos),
                        ("progress", progress_specs.progress_data), ("goal_history", progress_specs.goal_history),
                        ("crashes", lambda: crashes.report(4)), ("sublab", sublab.app_data)):
            try:
                out[key] = fn()
            except Exception as e:  # one broken source must not blank the others
                out[key] = cls.data.get(key, [])
                print(f"[app] {key}: {e}", flush=True)
        out["updated"] = now_iso()
        with cls.lock:
            cls.data = out

    @classmethod
    def refresh_pages(cls):
        PAGES.mkdir(parents=True, exist_ok=True)
        for args in (["engine_page.py", str(PAGES)], ["plan_page.py", str(PAGES)]):
            try:
                subprocess.run([sys.executable, str(LAB / args[0]), *args[1:]], cwd=ROOT, capture_output=True, timeout=600,
                               creationflags=monitor.NO_WINDOW)
            except Exception as e:
                print(f"[app] page {args[0]}: {e}", flush=True)
        cls.pages_updated = now_iso()

    @classmethod
    def loop(cls):
        last_pages = 0
        while True:
            cls.refresh()
            if time.time() - last_pages > 600:
                cls.refresh_pages()
                last_pages = time.time()
            time.sleep(90)


def videos(n: int = 14) -> list:
    out = []
    for mp4 in sorted(VIDEOS.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]:
        md = mp4.with_suffix(".md")
        title = ""
        if md.exists():
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
            title = next((l for l in lines[1:6] if l.startswith("Map ")), "")
        out.append({"name": mp4.name, "mb": round(mp4.stat().st_size / 1e6), "title": title,
                    "at": datetime.fromtimestamp(mp4.stat().st_mtime).strftime("%d.%m %H:%M")})
    return out


# ---------------------------------------------------------------- live data from the watched match's log

_live_cache = {"at": 0, "data": None}


def current_run():
    """The watched match's run folder: the newest w<N>- run (the one running, or the last one)."""
    runs = [r for r in scorecard.RUNS.glob("w*-*") if r.is_dir() and re.match(r"w\d+-", r.name)]
    return max(runs, key=lambda r: r.stat().st_mtime) if runs else None


class LiveState:
    """The watched match's log, read incrementally: each call parses only the lines added since the last one."""
    def __init__(self, run):
        self.run, self.offset, self.t = run, 0, 0
        self.series, self.supply, self.events = {}, {}, []
        self.score, self.crowd, self.air, self.riding = None, {}, {}, {}
        self.lost = {"US": 0, "USSR": 0}
        self.efforts, self.efforts_t = {}, {}
        self.fps = {}           # game minute -> [sum, count] of the engine's FPS lines (every 10 s, -logStats)

    def update(self, log: Path):
        kv = re.compile(r"(\w+)=(\S*)")
        with open(log, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        cut = data.rfind(b"\n")
        if cut < 0:
            return
        self.offset += cut + 1
        for l in data[:cut].decode("utf-8", errors="replace").splitlines():
            m = re.search(r"\[ZCR\]\[(\w+)\] t=(\d+)", l)
            if not m:
                fm = re.search(r"DEFAULT\s+: FPS: ([\d.]+)", l)
                if fm:
                    acc = self.fps.setdefault(self.t // 60, [0.0, 0])
                    acc[0] += float(fm.group(1))
                    acc[1] += 1
                    self.series.setdefault("fps", {})["FPS"] = {k: round(v[0] / v[1], 1) for k, v in self.fps.items()}
                    continue
                if "LOGISTICS_UNLOAD_COMMITTED" in l:
                    d = dict(kv.findall(l))
                    self.events.append({"t": self.t, "side": d.get("faction", ""), "kind": "truck", "text": "supply truck unloaded"})
                continue
            kind, t = m.group(1), int(m.group(2))
            self.t = t
            d = dict(kv.findall(l))
            side = d.get("side", "")
            minute = t // 60
            if kind == "SCORE":
                self.score = {k: d.get(k) for k in ("US", "USSR", "FIA")}
            elif kind == "SUPPLY":
                self.supply[(side, d.get("base"))] = d
                front = [float(x["pct"]) for (sd, _), x in self.supply.items() if sd == side and x.get("main") == "0" and x.get("pct")]
                if front:
                    self.series.setdefault("front_supply", {}).setdefault(side, {})[minute] = round(sum(front) / len(front))
            elif kind == "CROWD":
                self.crowd[side] = d
                self.series.setdefault("in_field", {}).setdefault(side, {})[minute] = int(d.get("field", 0) or 0)
            elif kind == "DRONEAIR":
                self.air[side] = d
                self.series.setdefault("drones_up", {}).setdefault(side, {})[minute] = int(d.get("air", 0) or 0)
            elif kind == "RIDING":
                self.riding[side] = d
            elif kind == "EFFORTS" and "json=" in l:
                try:
                    self.efforts[side] = json.loads(l.split("json=", 1)[1])
                    self.efforts_t[side] = t
                except ValueError:
                    pass
            elif kind == "LOSS":
                v = d.get("victim_side") or d.get("side")
                if v in self.lost and d.get("kind") == "man":
                    self.lost[v] += 1
                    self.series.setdefault("lost", {}).setdefault(v, {})[minute] = self.lost[v]
                if d.get("kind") == "vehicle":
                    self.events.append({"t": t, "side": v or "", "kind": "loss", "text": f"{d.get('victim', 'vehicle')} destroyed"})
                if d.get("runover"):
                    self.events.append({"t": t, "side": v or "", "kind": "jam", "text": f"{d.get('victim', 'soldier')} run over by {d.get('runover')}"})
            elif kind == "CAPTURE":
                base = l.split("base=", 1)[-1].split(" from=")[0]
                self.events.append({"t": t, "side": d.get("to", ""), "kind": "capture", "text": f"{base} taken by {d.get('to')} from {d.get('from')}"})
            elif kind == "STORM":
                self.events.append({"t": t, "side": side, "kind": "storm", "text": "storm: " + l.split("] ", 1)[-1][:120]})
            elif kind == "DRONES" and "kind=" in l and " to=" in l:
                to = l.split(" to=", 1)[1].split(" distance=")[0]
                self.events.append({"t": t, "side": side, "kind": "drone", "text": f"drone team {d.get('team')} ({d.get('kind')}) to {to}"})
            elif kind == "JAM":
                self.events.append({"t": t, "side": side, "kind": "jam", "text": f"{d.get('vehicle')} jammed with {d.get('other')} ({d.get('other_side')})"})
            elif kind == "STUCKVEH":
                self.events.append({"t": t, "side": side, "kind": "jam", "text": f"{d.get('vehicle')} stuck"})
            elif kind == "UNJAM" and int(d.get("stuck_s", 0) or 0) >= 60:
                self.events.append({"t": t, "side": side, "kind": "jam", "text": f"{d.get('vehicle')} free after {d.get('stuck_s')} s ({d.get('ended')})"})
            elif kind == "ARMOUR" and d.get("event") in ("BOUGHT", "LOST", "RELOCATED", "GIVEWAY", "RECREW"):
                self.events.append({"t": t, "side": side, "kind": "armour", "text": f"{d.get('prefab', 'armour')} {d.get('event', '').lower()}"})
        self.events = self.events[-60:]

    def view(self) -> dict:
        fronts = {}
        for (side, _), d in self.supply.items():
            if d.get("main") == "0" and d.get("pct"):
                fronts.setdefault(side, []).append(float(d["pct"]))
        return {
            "t": self.t, "score": self.score, "lost": self.lost,
            "supply": [{"side": s, "base": (b or "").split("MapLocation_")[-1].replace("_", " "), "value": d.get("value"),
                        "max": d.get("max"), "pct": d.get("pct"), "main": d.get("main")} for (s, b), d in sorted(self.supply.items())],
            "front_pct": {s: round(sum(v) / len(v)) for s, v in fronts.items()},
            "crowd": {s: {k: d.get(k) for k in ("men", "field", "at_main", "team")} for s, d in self.crowd.items()},
            "air": {s: {k: d.get(k) for k in ("air", "spotted")} for s, d in self.air.items()},
            "riding": {s: d.get("riding") for s, d in self.riding.items()},
            "efforts": self.efforts, "efforts_t": self.efforts_t,
            "events": self.events[-18:][::-1],
            "series": {name: {s: sorted(pts.items()) for s, pts in by.items()} for name, by in self.series.items()},
        }


_state = {"live": None}
_state_lock = threading.Lock()


def live() -> dict:
    if time.time() - _live_cache["at"] < 4 and _live_cache["data"] is not None:
        return _live_cache["data"]
    run = current_run()
    out = {"run": run.name if run else None}
    log = scorecard.console(run) if run else None
    if log:
        with _state_lock:
            st = _state["live"]
            if st is None or st.run != run.name:
                st = _state["live"] = LiveState(run.name)
            st.update(log)
            out.update(st.view())
    w = monitor.watched_now()
    if w.get("running") and not any(re.match(r"w\d+-", s) for s in servers()):
        w["running"] = False            # the loop was stopped without logging the end: no game is running
        w["ended_early"] = w.get("ended_early") or "stopped"
    out["watched"] = w
    out["now"] = json.loads(monitor.NOW.read_text(encoding="utf-8")) if monitor.NOW.exists() else {}
    _live_cache.update(at=time.time(), data=out)
    return out


_servers_cache = {"at": 0, "data": []}


def servers() -> list:
    if time.time() - _servers_cache["at"] > 20:
        _servers_cache.update(at=time.time(), data=monitor.servers())
    return _servers_cache["data"]


# ---------------------------------------------------------------- headless tests running now (sub-labs, integration tests)

_tests_cache = {"at": 0, "data": []}
TEST_RUN = re.compile(r"^(drivetest|guntest|inftest)-(.+)-([a-z0-9]+)-p(\d+)-(\d{8}-\d{6})$")
SUBLAB_OF = {"drivetest": "driving", "guntest": "guns", "inftest": "infantry"}


def _labels(name: str) -> dict:
    try:
        return sublab.load(name)
    except Exception:
        return {}


def tests_now() -> list:
    """Each headless test server running now: which test, which setup in words, how far, and its numbers so far."""
    if time.time() - _tests_cache["at"] < 10:
        return _tests_cache["data"]
    out = []
    for name in servers():
        m = TEST_RUN.match(name)
        if not m:
            continue
        kind, scenario, variant, port, stamp = m.groups()
        d = _labels(SUBLAB_OF[kind])
        run_dir = RUNTIME / "runs" / name
        minutes = None
        try:
            minutes = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["args"]["minutes"]
        except Exception:
            pass
        row = {"run": name, "sublab": d.get("title") or SUBLAB_OF[kind], "scenario": scenario, "variant": variant,
               "scenario_label": (d.get("scenario_labels") or {}).get(scenario, scenario),
               "scenario_words": (d.get("scenario_words") or {}).get(scenario, ""),
               "variant_label": (d.get("variant_labels") or {}).get(variant, variant),
               "variant_words": (d.get("variant_words") or {}).get(variant, ""),
               "started": f"{stamp[9:11]}:{stamp[11:13]}", "minutes": minutes, "port": port}
        log = scorecard.console(run_dir)
        if log:
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
                ts = re.findall(r"\[ZCR\]\[\w+\] t=(\d+)", text[-20000:])
                row["game_s"] = int(ts[-1]) if ts else 0
                if kind == "drivetest":
                    import drivetest
                    sm = drivetest.summarize(run_dir, scenario, variant)
                    keys = [("deliveries", "deliveries"), ("legs", "trips"), ("car_hits", "crashes between cars"), ("lost", "lost"),
                            ("jams", "jams"), ("supplies_delivered", "supplies delivered"), ("men_delivered", "soldiers delivered"),
                            ("crossings", "gave way"), ("junction_slows", "slowed at junctions")]
                elif kind == "inftest":
                    import inftest
                    sm = inftest.summarize(run_dir, scenario, variant)
                    keys = [("us_lost", "attackers lost"), ("ussr_lost", "defenders lost"), ("taken", "position taken"),
                            ("us_cover", "% attackers in cover"), ("ussr_cover", "% defenders in cover"), ("died_open_pct", "% died in the open"),
                            ("fight_m", "fighting distance m")]
                else:
                    import guntest
                    sm = guntest.summarize(run_dir, scenario, variant)
                    keys = [("fired_pct", "% vehicles fired"), ("first_m", "first shot m"), ("rounds", "rounds"),
                            ("vehicles_lost", "vehicles lost"), ("squad_men_lost", "soldiers lost")]
                row["numbers"] = [{"key": k, "label": lab, "value": sm.get(k)} for k, lab in keys
                                  if sm.get(k) not in (None, 0, "") or k in ("car_hits", "lost", "us_lost", "ussr_lost", "taken")]
            except Exception as e:
                row["error"] = str(e)[:120]
        out.append(row)
    _tests_cache.update(at=time.time(), data=out)
    return out


_frame_cache = {"at": 0, "jpg": None}


def frame() -> bytes:
    """A frame from the recording being written (the game window, as it is on screen)."""
    if time.time() - _frame_cache["at"] < 10 and _frame_cache["jpg"]:
        return _frame_cache["jpg"]
    mkv = sorted(VIDEOS.glob("*.mkv"), key=lambda p: p.stat().st_mtime)
    jpg = None
    if mkv and time.time() - mkv[-1].stat().st_mtime < 120:
        out = RUNTIME / "app_frame.jpg"
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-sseof", "-3", "-i", str(mkv[-1]),
                            "-frames:v", "1", "-vf", "scale=1280:-1", "-q:v", "5", str(out)], timeout=20, capture_output=True,
                           creationflags=monitor.NO_WINDOW)
            jpg = out.read_bytes() if out.exists() else None
        except Exception:
            jpg = None
    _frame_cache.update(at=time.time(), jpg=jpg)
    return jpg


def inbox(n: int = 30) -> list:
    if not INBOX.exists():
        return []
    rows = [json.loads(l) for l in INBOX.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-n:][::-1]


def add_remark(kind: str, text: str, typing_s: float = 0) -> dict:
    """A remark into the inbox. seen_at: the moment it is about - when the owner started typing it (typing_s before now)."""
    RUNTIME.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    row = {"id": now.strftime("%Y%m%d-%H%M%S-%f")[:-3], "at": now_iso(), "kind": kind[:20], "text": text[:2000], "status": "new"}
    if 0 < typing_s < 1800:
        row["seen_at"] = (now - timedelta(seconds=typing_s)).strftime("%Y-%m-%dT%H:%M:%S")
    with open(INBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def loop_log() -> list:
    if not monitor.LOG.exists():
        return []
    return [json.loads(l) for l in monitor.LOG.read_text(encoding="utf-8").splitlines() if l.strip()][::-1]


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code: int, body: bytes, ctype: str, extra: dict = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code: int = 200):
        self.send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/live":
                return self.json({**live(), "servers": servers(), "tests": tests_now(), "inbox": inbox(12), "at": now_iso()})
            if path == "/api/slow":
                with Slow.lock:
                    small = {k: v for k, v in Slow.data.items() if k not in ("progress", "goal_history", "crashes")}
                    return self.json({**small, "pages_updated": Slow.pages_updated, "log": loop_log()})
            if path == "/api/progress":
                with Slow.lock:
                    return self.json({**(Slow.data.get("progress") or {}), "goal_history": Slow.data.get("goal_history", [])})
            if path == "/api/crashes":
                with Slow.lock:
                    return self.json({**(Slow.data.get("crashes") or {}), "updated": Slow.data.get("updated")})
            if path == "/charts.js":
                return self.send(200, (HERE / "charts.js").read_bytes(), "application/javascript; charset=utf-8")
            if path == "/vendor/echarts.min.js":
                return self.send(200, (HERE / "vendor" / "echarts.min.js").read_bytes(), "application/javascript",
                                 {"Cache-Control": "max-age=86400"})
            if path == "/api/map":
                q = dict(x.split("=", 1) for x in urlparse(self.path).query.split("&") if "=" in x)
                name = q.get("map", "arland")
                if name not in ("arland", "everon"):
                    return self.json({"error": "unknown map"}, 404)
                try:
                    since_h = float(q.get("since", "24"))
                except ValueError:
                    since_h = 24
                return self.json(MapLayers.get(name, since_h))
            if path in ("/vendor/leaflet.js", "/vendor/leaflet.css"):
                f = HERE / "vendor" / path.rsplit("/", 1)[1]
                ctype = "application/javascript" if f.suffix == ".js" else "text/css"
                return self.send(200, f.read_bytes(), ctype, {"Cache-Control": "max-age=86400"})
            if path == "/api/frame.jpg":
                jpg = frame()
                return self.send(200, jpg, "image/jpeg") if jpg else self.send(404, b"no recording running", "text/plain")
            if path.startswith("/pages/"):
                name = {"engine": "reforger_engine.html", "changelog": "reforger_changelog.html", "plan": "reforger_plan.html"}.get(path[7:])
                f = PAGES / name if name else None
                if not f or not f.exists():
                    return self.send(404, b"<p style='font-family:sans-serif'>Being built - try again in a minute.</p>", "text/html")
                body = (b"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                        b"<style>body{margin:0;font:14px system-ui}</style></head><body>" + f.read_bytes() + b"</body></html>")
                return self.send(200, body, "text/html; charset=utf-8")
            if path.startswith("/video/"):
                return self.video(unquote(path[7:]))
            return self.send(404, b"not found", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def video(self, name: str):
        f = VIDEOS / Path(name).name
        if f.suffix != ".mp4" or not f.exists():
            return self.send(404, b"not found", "text/plain")
        size = f.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = min(int(b), size - 1) if b else min(start + 8_000_000, size - 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_POST(self):
        if urlparse(self.path).path != "/api/inbox":
            return self.send(404, b"not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 10000)) or b"{}")
            text = str(body.get("text", "")).strip()
            if not text:
                return self.json({"error": "empty"}, 400)
            try:
                typing_s = float(body.get("typing_s") or 0)
            except (TypeError, ValueError):
                typing_s = 0
            return self.json(add_remark(str(body.get("kind", "wish")), text, typing_s))
        except Exception as e:
            return self.json({"error": str(e)}, 400)


def wait(minutes: float) -> int:
    """Block until a new remark arrives (or the time runs out) - Claude runs this in the background to wake on it."""
    seen = len(inbox(100000))
    end = time.time() + minutes * 60
    while time.time() < end:
        time.sleep(5)
        rows = inbox(100000)
        if len(rows) > seen:
            for r in rows[: len(rows) - seen][::-1]:
                print(f"new remark: [{r['kind']}] {r['text']}")
            return 0
    print("no new remark")
    return 1


def file_remark(rid: str, note: str, reply: str, status: str = "filed") -> int:
    """Mark a remark handled: python lab/app/server.py file <id> --note 260 --reply "what happens with it"."""
    rows = [json.loads(l) for l in INBOX.read_text(encoding="utf-8").splitlines() if l.strip()] if INBOX.exists() else []
    hit = False
    for r in rows:
        if r.get("id") == rid:
            r.update(status=status, note=note, reply=reply, handled_at=now_iso())
            hit = True
    INBOX.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print("filed" if hit else f"no remark {rid}")
    return 0 if hit else 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "new":
        for r in inbox(100000)[::-1]:
            if r.get("status") == "new":
                print(json.dumps(r))
        return 0
    if len(sys.argv) > 2 and sys.argv[1] == "file":
        arg = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else ""
        return file_remark(sys.argv[2], arg("--note"), arg("--reply"), arg("--status") or "filed")
    if len(sys.argv) > 1 and sys.argv[1] == "wait":
        minutes = float(sys.argv[sys.argv.index("--minutes") + 1]) if "--minutes" in sys.argv else 60
        return wait(minutes)
    threading.Thread(target=Slow.loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[app] http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
