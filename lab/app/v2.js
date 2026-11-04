// Commander Lab v2 (4 Nov 2026 - Martin: "a lot of things I dont actually use ... I feel a lot of stuff is now redundant
// and maybe too noise. lets improve user experience with what we actually need"). Three views:
//   Map       the battle full screen: the top bar says which battle, who holds the point, the game time, the losses and
//             what each side's general (Gemini or the rules) decided last; a click on a team opens its route - numbered
//             waypoints with their kind and status - its order, Gemini's reason and a remark box about it.
//   Progress  each question as a training curve (runs on x, the moving average, the target, the builds) - "I can't read
//             tables" (2 Nov).
//   Remarks   the remark box and every remark with the loop's reply.
// Data: /api/v2/live (lab/app/v2data.py on top of lab/maplayers.py live()), /api/slow + /api/progress, /api/inbox.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const mmss = (t) => { t = Math.max(0, Math.round(t || 0)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
  const km = (m) => m >= 1000 ? (m / 1000).toFixed(1) + " km" : Math.round(m) + " m";
  const cap = (s) => s ? String(s)[0].toUpperCase() + String(s).slice(1) : "";
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim() || "#888";
  const fmt1 = (v) => v == null || Number.isNaN(v) ? "–" : (Math.round(v * 10) / 10).toString();
  // Remembered per viewer (layer toggles, the last test): wrapped, so a blocked storage only forgets.
  const store = {
    get(k, d) { try { const v = localStorage.getItem("labv2-" + k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem("labv2-" + k, JSON.stringify(v)); } catch (_) { /* remembered for this visit only */ } },
  };
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const shortAt = (at) => { const m = /^(\d{4})-(\d\d)-(\d\d)[ T](\d\d:\d\d)/.exec(String(at || "")); return m ? `${+m[3]} ${MON[+m[2] - 1]} ${m[4]}` : String(at || ""); };
  const ago = (iso) => { const t = Date.parse(iso); if (isNaN(t)) return ""; const m = Math.round((Date.now() - t) / 60000);
    return m < 1 ? "just now" : m < 60 ? m + " min ago" : m < 48 * 60 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " days ago"; };
  const len = (pts) => { let m = 0; for (let i = 1; i < (pts || []).length; i++) m += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return m; };
  const ll = (pts) => pts.map((p) => [p[1], p[0]]);
  const sideCol = () => ({ US: css("--us"), USSR: css("--ussr"), FIA: css("--fia") });

  // ------------------------------------------------------------ header status (the battle's state, the last answer)
  function status(ok, live) {
    $("status-dot").className = "dot" + (ok && live ? " live" : "");
    $("status-when").textContent = ok ? new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "PC not answering";
    $("status-when").style.color = ok ? "" : "var(--bad)";
  }

  // ------------------------------------------------------------ a remark: what was on screen when typing started
  // The moment a remark is about is when its first letter was typed (typing takes 20-30 s and the battle moves on); sent
  // as seconds of typing, so the phone's clock doesn't matter (the same as the old page).
  function remarkBox(form, text, sentEl, kindName, getUnit, after) {
    let since = 0, unitAt = null;
    text.addEventListener("input", () => {
      if (!text.value.trim()) { since = 0; unitAt = null; return; }
      if (!since) { since = Date.now(); unitAt = getUnit ? getUnit() : null; sentEl.textContent = `Moment noted: ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`; }
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = text.value.trim();
      if (!body) return;
      const kind = (form.querySelector(`input[name="${kindName}"]:checked`) || {}).value || "wish";
      const unit = getUnit ? (unitAt || getUnit()) : null;
      const typing_s = since ? Math.round((Date.now() - since) / 1000) : 0;
      sentEl.textContent = "Sending…";
      try {
        const r = await fetch("/api/inbox", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(unit ? { kind, text: body, typing_s, unit } : { kind, text: body, typing_s }) });
        if (!r.ok) throw new Error();
        text.value = ""; since = 0; unitAt = null;
        sentEl.innerHTML = `Sent (${esc(kind)})${unit && unit.who ? " about " + esc(unit.who) : ""}. The reply shows under <a href="#remarks">Remarks</a>.`;
        if (after) after();
        Rem.load();
      } catch (_) { sentEl.textContent = "Not sent - is the PC on?"; }
    });
  }

  // ============================================================ the game camera
  // Martin watches the game over Moonlight on his phone, where a touch on the game window turns the camera (4 Nov): the
  // director takes its commands from here - POST /api/camera {"cmd": "auto" | "point+" | "group+" | "closer" | "wider" |
  // "follow <side> <team id>" | "goto <x> <z>"} (server.py CAMERA_CMDS), into the running game's profile/zcr/camera.txt.
  const Cam = {
    wire() {
      for (const b of document.querySelectorAll("#cambar button[data-cam]")) b.addEventListener("click", () => this.send(b.dataset.cam, b.textContent));
      $("sh-info").addEventListener("click", (e) => {
        const b = e.target.closest("[data-cam]");
        if (b) { e.stopPropagation(); this.send(b.dataset.cam, b.dataset.camWords || b.textContent); }
      });
    },
    on() { const B = MapV.d && MapV.d.battle; return !!(B && B.live && B.watched); },   // a watched battle: a game window to steer
    async send(cmd, words) {
      const msg = $("cam-msg");
      msg.className = "cam-msg";
      msg.textContent = "Sending…";
      try {
        const r = await fetch("/api/camera", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cmd }) });
        let j = {};
        try { j = await r.json(); } catch (_) { /* a plain-text answer */ }
        if (!r.ok || j.error) throw new Error(j.error || (r.status === 404 ? "this lab app has no camera control yet" : "error " + r.status));
        msg.textContent = `${words} - sent`;
      } catch (e) { msg.className = "cam-msg err"; msg.textContent = `Not sent: ${e.message}`; }
      clearTimeout(this.timer);
      this.timer = setTimeout(() => { msg.textContent = ""; }, 6000);
    },
    // The button in the clicked unit's sheet: follow a team, else look at the place.
    button(unit) {
      if (!this.on() || !unit) return "";
      if (unit.kind === "team") return `<button type="button" class="cambtn" data-cam="follow ${esc(unit.side)} ${esc(unit.id)}" data-cam-words="Camera follows ${esc(unit.who)}">Follow this team with the camera</button>`;
      if (unit.x != null && unit.z != null) return `<button type="button" class="cambtn" data-cam="goto ${Math.round(unit.x)} ${Math.round(unit.z)}" data-cam-words="Camera to ${esc(unit.who)}">Camera here</button>`;
      return "";
    },
  };

  // ============================================================ Map
  const DOING = { ATTACK_PRIMARY: "attacking", ATTACK_SUPPORT: "attacking", AREA_SECURITY: "guarding", FORWARD_DEFEND: "defending",
    QRF: "rushing to defend", LONE_SURVIVOR_RETREAT: "last man - going home", INFANTRY_MUSTER: "gathering" };
  const doingOf = (t) => DOING[t.posture] || (t.posture && t.posture !== "-" ? String(t.posture).toLowerCase().replace(/_/g, " ") : String(t.role || "").toLowerCase());
  // A waypoint's kind (lab/liveplan.py wp_kinds) in words: the short name and what it means for the team.
  const KIND = { "edge of trees": ["Edge of a tree line", "cover, the jump-off to the next"], "edge of buildings": ["By buildings", "cover, the jump-off to the next"],
    "in trees": ["Inside woods", "cover while moving"], "in buildings": ["Among buildings", "cover while moving"], "open": ["Open ground", "a dash"],
    "route": ["On the route", ""] };
  const kindWords = (k, point) => k === "Farm" || k === "objective" ? ["The objective" + (point ? " - " + point : ""), "where the attack ends"] : KIND[k] || [cap(k || "on the route"), ""];
  const ORDER = { move: "move there", search: "search and destroy - clear the area", defend: "defend - hold the area", hold: "hold - wait there", action: "action (relay)" };
  const WORLD = { arland: 4096, everon: 12800 };

  const MapV = {
    view: null, base: null, name: null, meta: {}, g: {}, d: null, sel: null, fittedRun: null, busy: false, lastPoll: 0,
    layers: Object.assign({ plans: true, danger: true, soldiers: true, trucks: false }, store.get("layers", {})),
    tiles: store.get("tiles", "topo"),

    open() {
      if (!this.wired) this.wire();
      if (this.view) setTimeout(() => this.view.invalidateSize(), 30);
      this.poll();
    },
    wire() {
      this.wired = true;
      try { this.sel = sessionStorage.getItem("labv2-sel") || null; } catch (_) { this.sel = null; }
      try { const q = new URLSearchParams(location.search).get("sel"); if (q) this.sel = q; } catch (_) {}   // a link to one: /v2?sel=team:US:2
      for (const b of document.querySelectorAll(".chipbtn[data-layer]")) {
        b.setAttribute("aria-pressed", String(!!this.layers[b.dataset.layer]));
        b.addEventListener("click", () => {
          const k = b.dataset.layer;
          this.layers[k] = !this.layers[k];
          b.setAttribute("aria-pressed", String(this.layers[k]));
          store.set("layers", this.layers);
          this.draw();
        });
      }
      $("battle").addEventListener("click", () => this.toggleBar());
      $("battle").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.toggleBar(); } });
      $("btn-fit").addEventListener("click", () => this.fit(true));
      $("btn-full").addEventListener("click", () => this.full());
      document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement) document.body.classList.remove("fs"); setTimeout(() => this.view && this.view.invalidateSize(), 80); });
      $("btn-legend").addEventListener("click", () => {
        const on = $("legend").hidden;
        $("legend").hidden = !on;
        $("btn-legend").setAttribute("aria-expanded", String(on));
        if (on) this.legend();
      });
      $("sh-close").addEventListener("click", (e) => { e.stopPropagation(); this.pick(null); });
      $("sh-min").addEventListener("click", (e) => { e.stopPropagation(); this.fold(); });
      $("sh-head").addEventListener("click", () => this.fold());
      remarkBox($("sh-note"), $("sh-text"), $("sh-sent"), "unitkind", () => this.unit);
      Cam.wire();
      document.addEventListener("keydown", (e) => { if (e.key === "Escape" && this.sel && view === "map") this.pick(null); });
    },
    toggleBar() {
      const b = $("battle"), on = !b.classList.contains("open");
      b.classList.toggle("open", on);
      b.setAttribute("aria-expanded", String(on));
      setTimeout(() => this.view && this.view.invalidateSize(), 30);
    },
    fold() {
      const s = $("sheet");
      s.classList.toggle("min");
      $("sh-min").textContent = s.classList.contains("min") ? "▴" : "▾";
    },
    full() {
      const on = !document.body.classList.contains("fs");
      document.body.classList.toggle("fs", on);
      try {
        if (on && document.documentElement.requestFullscreen && !document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
        else if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {});
      } catch (_) { /* no browser full screen (iPhone): the header still goes */ }
      setTimeout(() => this.view && this.view.invalidateSize(), 80);
    },

    async poll() {
      if (this.busy) return;
      this.busy = true;
      this.lastPoll = Date.now();
      let stage = "fetch";
      try {
        const r = await fetch("/api/v2/live?map=auto");
        if (!r.ok) throw new Error(r.status);
        this.d = await r.json();
        // The live layer keeps every [ZCR][LIVE] row of the last 4 game seconds: a unit seen twice is drawn once, its latest.
        const uniq = (xs, key) => [...new Map((xs || []).map((x) => [key(x), x])).values()];
        this.d.teams = uniq(this.d.teams, (t) => t.side + ":" + t.id);
        this.d.trucks = uniq(this.d.trucks, (t) => t.side + ":" + t.id);
        this.d.builders = uniq(this.d.builders, (t) => t.side + ":" + t.id);
        this.d.vans = uniq(this.d.vans, (t) => t.id);
        status(true, this.d.live);
        stage = "map";
        await this.ensureMap(this.d.map || "arland");
        stage = "draw";
        this.render();
      } catch (e) {
        // The PC not answering and a mistake in this page are different things to be told.
        if (stage === "fetch") status(false);
        else {
          console.error(e);
          $("status").title = `page error (${stage}): ${e && e.message}`;
          if (/[?&]debug/.test(location.search)) $("banner").hidden = false, $("banner").textContent = `page error (${stage}): ${e && e.stack}`;
        }
      }
      this.busy = false;
    },
    async ensureMap(name) {
      if (this.view && this.name === name) return;
      let meta = this.meta[name];
      if (!meta) {
        try { meta = (await (await fetch(`https://enfumap.com/api/v1/maps/${name}`)).json()).data; }
        catch (_) { meta = { worldSize: WORLD[name] || 4096, tiles: null }; }   // no tiles: the marks on a plain ground
        this.meta[name] = meta;
      }
      if (this.view) { this.view.remove(); this.view = null; this.base = null; }
      const ts = meta.tiles ? meta.tiles.tileSize : 256, s = ts / meta.worldSize;
      const crs = L.extend({}, L.CRS.Simple, { transformation: new L.Transformation(s, 0, -s, ts) });
      this.view = L.map("map", { crs, minZoom: 0, maxZoom: (meta.tiles ? meta.tiles.maxNativeZoom : 6) + 3, zoomSnap: 0.25, zoomDelta: 0.5, zoomControl: false });
      L.control.zoom({ position: "bottomright" }).addTo(this.view);
      // The names on the map sit above the lines (readable) and under the units (the fight is at the point: its label
      // must not hide the teams there).
      const lp = this.view.createPane("labels");
      lp.style.zIndex = 450;
      lp.style.pointerEvents = "none";
      this.view.fitBounds([[0, 0], [meta.worldSize, meta.worldSize]]);
      this.name = name;
      this.fittedRun = null;
      for (const k of ["bases", "plans", "danger", "units", "sel"]) this.g[k] = L.layerGroup().addTo(this.view);   // bottom to top
      this.view.on("click", () => { if (this.sel) this.pick(null); });
      this.view.on("zoomend", () => { if (this.d) this.draw(); });   // the soldiers' dots grow when zoomed in
      this.setTiles();
    },
    setTiles() {
      const meta = this.meta[this.name];
      if (!this.view || !meta || !meta.tiles) return;
      if (this.base) this.base.remove();
      const zoom = (meta.tiles.layerMaxNativeZoom || {})[this.tiles];
      this.base = L.tileLayer("https://enfumap.com" + (meta.tiles.layers[this.tiles] || meta.tiles.url), {
        tileSize: meta.tiles.tileSize, maxNativeZoom: zoom == null ? meta.tiles.maxNativeZoom : zoom, noWrap: true,
        attribution: 'Map &copy; <a href="https://enfumap.com" target="_blank" rel="noopener">Enfumap</a>' }).addTo(this.view);
      this.base.bringToBack();
    },
    // The fight, so the first look is the battle, not the whole island: the point and the attack teams within 1.2 km of
    // it (a second wave still at its HQ would zoom the map out to everything); no point - every attack team.
    fit(force) {
      const d = this.d;
      if (!this.view || !d || !d.run || (!force && this.fittedRun === d.run)) return;
      const pt = (d.bases_now || []).find((b) => d.battle && b.name === d.battle.point);
      const atk = (d.teams || []).filter((t) => t.role === "ATTACK");
      const near = pt ? atk.filter((t) => Math.hypot(t.x - pt.x, t.z - pt.z) < 1200) : atk;
      const pts = (near.length ? near : atk).map((t) => [t.z, t.x]);
      if (pt) pts.push([pt.z - 250, pt.x - 250], [pt.z + 250, pt.x + 250]);
      for (const t of d.teams || []) if (pts.length < 2) pts.push([t.z, t.x]);
      if (pts.length >= 2) this.view.fitBounds(L.latLngBounds(pts).pad(0.1), { maxZoom: 5.5, paddingTopLeft: [10, 50] });
      this.fittedRun = d.run;
    },

    render() {
      const d = this.d;
      this.renderBattle();
      $("nobattle").hidden = !!(d && d.run);
      const B = d && d.battle;
      if ($("cambar").hidden === Cam.on()) { $("cambar").hidden = !Cam.on(); setTimeout(() => this.view && this.view.invalidateSize(), 30); }
      $("banner").hidden = !(B && !B.live);
      if (B && !B.live) $("banner").textContent = `The last battle - ended at ${B.ended_at}${B.ended_ago_min != null ? ` (${B.ended_ago_min < 90 ? B.ended_ago_min + " min" : Math.round(B.ended_ago_min / 60) + " h"} ago)` : ""}. Its final positions; the map goes live by itself when the next battle starts.`;
      this.fit(false);
      this.draw();
    },

    // ---- the top bar: which battle, the point and who holds it, the game time, the losses, each side's general
    renderBattle() {
      const d = this.d, B = d && d.battle;
      if (!B) { $("battle").innerHTML = `<div class="l1"><span class="state ended">NO BATTLE</span><span class="muted">Nothing played on Arland or Everon lately.</span></div>`; return; }
      if (B.error) { $("battle").innerHTML = `<div class="l1"><span class="state ${B.live ? "live" : "ended"}">${B.live ? "LIVE" : "ENDED"}</span><span class="muted">${esc(B.run)} - the summary failed: ${esc(B.error)}</span></div>`; return; }
      const own = B.owner === "FIA" ? "neutral" : B.owner ? "held by " + B.owner : "";
      const head = B.point ? `<span class="point">${esc(B.point)}</span>${own ? `<span class="owner c-${esc(B.owner)}">${esc(own)}</span>` : ""}`
        : B.score ? `<span class="point">Bases</span><span class="owner"><span class="c-US">US ${B.score.US}</span> · <span class="c-USSR">USSR ${B.score.USSR}</span></span>` : "";
      const lostV = (s) => (B.lost_vehicles || {})[s] ? ` <span class="muted">+${B.lost_vehicles[s]} veh.</span>` : "";
      const lost = `<span class="lost">lost <span class="sw US"></span>US <b>${(B.lost || {}).US ?? "–"}</b>${lostV("US")} · <span class="sw USSR"></span>USSR <b>${(B.lost || {}).USSR ?? "–"}</b>${lostV("USSR")}</span>`;
      const clock = `<span class="clock">${mmss(B.t)}${B.length_min ? `<span class="muted"> / ${Math.round(B.length_min)}:00</span>` : ""}</span>`;
      const gen = (s) => {
        const g = (B.sides || {})[s] || {};
        const failed = g.failed && g.fail_t != null && (g.answer_t == null || g.fail_t > g.answer_t);
        const tag = g.by === "Gemini" ? (failed ? `<span class="tag fail" title="${esc(g.fail || "")}">Gemini failed</span>` : `<span class="tag gem" title="${esc(g.model || "Gemini")}">Gemini</span>`)
          : `<span class="tag rules" title="${esc(g.doctrine || "")}">Rules</span>`;
        const words = g.reason ? `${g.stance ? `<span class="stance">${esc(g.stance)}</span> · ` : ""}${esc(g.reason)}` : esc(g.intent || (g.doctrine ? "doctrine " + g.doctrine : "no plan yet"));
        const when = g.ago_s != null ? (g.ago_s < 60 ? "just now" : Math.round(g.ago_s / 60) + " min ago") : "";
        return `<div class="gen"><span class="side c-${s}">${s}</span>${tag}<span class="txt">${words}</span>${when ? `<span class="ago">${when}</span>` : ""}</div>`;
      };
      const effort = (s) => { const m = ((B.sides || {})[s] || {}).main; return m ? `${s} main effort → ${esc(m.base)}: ${m.teams} teams, ${m.there ?? 0}/${m.men ?? "?"} there` : ""; };
      const g0 = (B.sides || {}).US || {}, g1 = (B.sides || {}).USSR || {};
      const calls = [g0, g1].filter((g) => g.calls).map((g, i) => `${g === g0 ? "US" : "USSR"} asked ${g.calls}×${g.failed ? `, failed ${g.failed}×` : ""}`).join(" · ");
      const caps = (B.captures || []).map((c) => `${mmss(c.t)} ${esc(c.base)} → ${esc(c.to)}`).join(" · ");
      $("battle").innerHTML = `<div class="l1">${B.live ? '<span class="state live">LIVE</span>' : `<span class="state ended">ENDED ${esc(B.ended_at || "")}</span>`}${head}${clock}${lost}</div>
        ${gen("US")}${gen("USSR")}
        <div class="more-info">${esc(cap(B.title))}${B.watched ? " · watched" : " · headless"}${B.speed && B.speed !== "1" ? ` · ${esc(B.speed)}x` : ""} · started ${esc(B.started)}
          ${[effort("US"), effort("USSR")].filter(Boolean).map((x) => "<br>" + x).join("")}
          ${caps ? `<br>Captures: ${caps}` : ""}${calls ? `<br>Gemini (${esc(g0.model || g1.model || "")}): ${calls}` : ""}
          <br><span class="mono">${esc(B.run)}</span></div>`;
    },

    pick(key) {
      this.sel = key && key !== this.sel ? key : null;
      try { if (this.sel) sessionStorage.setItem("labv2-sel", this.sel); else sessionStorage.removeItem("labv2-sel"); } catch (_) {}
      if (this.sel) { $("sheet").classList.remove("min"); $("sh-min").textContent = "▾"; }
      this.pannedFor = null;
      this.draw();
    },
    // Keep the selected one in sight beside the panel (desktop) or above the sheet (phone) - once per selection, so the
    // map stays where it is moved to afterwards.
    keepInSight() {
      if (!this.sel || !this.selAt || !this.view || this.pannedFor === this.sel) return;
      this.pannedFor = this.sel;
      const sh = $("sheet"), wide = window.matchMedia("(min-width: 820px)").matches;
      this.view.panInside(this.selAt, wide ? { paddingTopLeft: [40, 60], paddingBottomRight: [sh.offsetWidth + 40, 40] }
        : { paddingTopLeft: [30, 60], paddingBottomRight: [30, sh.offsetHeight + 30] });
    },

    // ---- the map
    draw() {
      const d = this.d, g = this.g;
      if (!this.view || !d) return;
      for (const k in g) g[k].clearLayers();
      this.selAt = null;
      this.unit = null;
      if (!d.run) { this.sheet(null); return; }
      const col = sideCol(), sel = this.sel, B = d.battle || {}, point = B.point;
      const marker = (lat, html, size, o) => L.marker(lat, Object.assign({ bubblingMouseEvents: false, keyboard: false,
        icon: L.divIcon({ className: "", iconSize: size, iconAnchor: [size[0] / 2, size[1] / 2], html }) }, o || {}));
      const tip = { className: "tip", direction: "top", offset: [0, -8] };

      // Bases: a ring in the owner's colour, the name; the point bigger. Two "Main Operating Base"s: named by owner.
      for (const b of d.bases_now || []) {
        const c = col[b.owner] || css("--muted"), isPt = point && b.name === point;
        const name = b.hq ? `${b.owner} HQ` : b.name;
        L.circleMarker([b.z, b.x], { radius: isPt ? 13 : b.hq ? 9 : 7, color: c, weight: isPt ? 4 : 3, fillColor: c, fillOpacity: isPt ? .3 : .18, interactive: false }).addTo(g.bases);
        L.marker([b.z, b.x], { opacity: 0, interactive: false, keyboard: false, icon: L.divIcon({ className: "", iconSize: [1, 1] }) })
          .bindTooltip(isPt ? `${esc(b.name)}<small>the point</small>` : esc(name), { permanent: true, direction: "top", offset: [0, isPt ? -14 : -9], className: `lbl ${esc(b.owner)}${isPt ? " point" : ""}`, pane: "labels" })
          .addTo(g.bases);
      }

      // Each side's plans: the main effort and the other attacks (arrows from its attacking teams), the bases it defends
      // (dashed rings), and the lines of attack its teams play (lanes through cover, the get-out ring, the hold bar).
      const dimAll = !!sel;
      if (this.layers.plans) this.drawEfforts(d, col, dimAll);
      if (this.layers.plans) this.drawLanes(d, col, sel);
      if (this.layers.danger) {
        for (const [s, zones] of Object.entries(d.danger || {})) {
          const c = col[s] || css("--muted");
          for (const z of zones || []) {
            const t = `<b>${esc(s)} danger zone ${esc(z.id || "")}</b><br>${z.men} soldiers${z.vehicles ? ` and ${z.vehicles} vehicles` : ""} lost here, the last ${Math.max(0, Math.floor((z.newest_s || 0) / 60))} min ago - a risk its general weighs, not a wall`;
            L.circle([z.z, z.x], { radius: 70, color: c, weight: 3, dashArray: "4 4", fillColor: c, fillOpacity: .12, bubblingMouseEvents: false }).bindTooltip(t, tip).addTo(g.danger);
            L.polyline([[z.z - 35, z.x - 35], [z.z + 35, z.x + 35]], { color: c, weight: 2.5, opacity: .85, interactive: false }).addTo(g.danger);
            L.polyline([[z.z - 35, z.x + 35], [z.z + 35, z.x - 35]], { color: c, weight: 2.5, opacity: .85, interactive: false }).addTo(g.danger);
          }
        }
      }
      // Field fortifications (4 Nov, note 538 - Martin: "llm general could actually build defense lines (bunkers) where it needs"):
      // the spots each general ordered outside any base - a hollow square, solid once built - with a tick the way it faces.
      if (this.layers.plans) {
        for (const [s, forts] of Object.entries(d.forts || {})) {
          const c = col[s] || css("--muted");
          for (const f of forts || []) {
            const t = `<b>${esc(s)} field fortification</b><br>${f.built ? "built" : "ordered by its general, the builders on the way"}`;
            L.rectangle([[f.z - 9, f.x - 9], [f.z + 9, f.x + 9]], { color: c, weight: 3, fillColor: c, fillOpacity: f.built ? .75 : .08, bubblingMouseEvents: false }).bindTooltip(t, tip).addTo(g.plans);
            if (f.facing != null) {
              const r = f.facing * Math.PI / 180;
              L.polyline([[f.z, f.x], [f.z + 26 * Math.cos(r), f.x + 26 * Math.sin(r)]], { color: c, weight: 3, interactive: false }).addTo(g.plans);
            }
          }
        }
      }

      // Teams: a tag with the team's number - solid when attacking, white when defending or guarding, faded for a last
      // man going home; its soldiers as dots (filled standing or crouched, hollow prone, a ring in a vehicle).
      let found = false;
      for (const t of d.teams || []) {
        const key = `team:${t.side}:${t.id}`, c = col[t.side] || css("--muted"), mine = key === sel;
        const atk = t.role === "ATTACK", home = t.posture === "LONE_SURVIVOR_RETREAT";
        if (this.layers.plans && atk && !sel && !home && t.wp && t.wp !== "-") {
          const wp = String(t.wp).split(",").map(Number);
          if (wp.length === 2 && !wp.some(isNaN)) L.polyline([[t.z, t.x], [wp[1], wp[0]]], { color: c, weight: 1.2, opacity: .45, dashArray: "2 6", interactive: false }).addTo(g.plans);
        }
        if (this.layers.soldiers) for (const m of t.mp || []) {
          const hollow = m[2] === "p" || m[2] === "v";
          const down = m[2] === "u";   // unconscious (5 Nov): grey, ringed in the side's colour
          L.circleMarker([m[1], m[0]], { bubblingMouseEvents: false, radius: (mine ? 4 : 2.6) + (this.view.getZoom() >= 5 ? .8 : 0), color: c, weight: hollow || down ? 1.5 : 0, fill: !hollow, fillColor: down ? "#9a9a9a" : c,
            fillOpacity: sel && !mine ? .35 : .9, opacity: sel && !mine ? .35 : 1 })
            .bindTooltip(`${esc(t.side)} team ${esc(t.id)} - ${{ s: "standing", c: "crouched", p: "prone", v: "in a vehicle", u: "unconscious" }[m[2]] || esc(m[2])}`, tip)
            .on("click", () => this.pick(key)).addTo(g.units);
        }
        const cls = `tm ${esc(t.side)}${atk ? "" : " hold"}${home ? " home" : ""}${mine ? " on" : ""}${sel && !mine ? " dim" : ""}`;
        marker([t.z, t.x], `<div class="${cls}">${esc(t.id)}</div>`, [22, 18], { zIndexOffset: mine ? 2000 : atk ? 300 : 0 })
          .bindTooltip(`<b>${esc(t.side)} team ${esc(t.id)}</b> · ${Math.round(t.men || 0)} men · ${esc(doingOf(t))}${t.ride ? " · riding" : ""}${t.to && t.to !== "-" ? " · " + esc(t.to) : ""}`, tip)
          .on("click", () => this.pick(key)).addTo(g.units);
        if (mine) { found = true; this.selAt = L.latLng(t.z, t.x); this.drawTeam(d, t, c); }
      }
      // Supply trucks, test vans, base builders (the Trucks layer).
      for (const t of d.trucks || []) {
        const key = `truck:${t.side}:${t.id}`, mine = key === sel;
        if (!this.layers.trucks && !mine) continue;
        marker([t.z, t.x], `<div class="tr ${esc(t.side)}${sel && !mine ? " dim" : ""}"></div>`, [14, 14], { zIndexOffset: 100 })
          .bindTooltip(`<b>${esc(t.side)} supply truck ${esc(t.id)}</b> · ${esc(String(t.phase || "").replace(/_/g, " ").toLowerCase())}, ${esc(t.from || "")} → ${esc(t.to || "")}`, tip)
          .on("click", () => this.pick(key)).addTo(g.units);
        if (mine) { found = true; this.selAt = L.latLng(t.z, t.x); this.drawTruck(d, t, col[t.side] || "#a05a00"); }
      }
      for (const v of d.vans || []) {
        const key = `van:${v.id}`, mine = key === sel;
        if (!this.layers.trucks && !mine) continue;
        marker([v.z, v.x], `<div class="tr van${sel && !mine ? " dim" : ""}"></div>`, [14, 14])
          .bindTooltip(`<b>Test van ${esc(v.id)}</b> · ${esc(String(v.phase || "").toLowerCase())}${v.to ? " → " + esc(v.to) : ""}`, tip)
          .on("click", () => this.pick(key)).addTo(g.units);
        if (mine) { found = true; this.selAt = L.latLng(v.z, v.x); this.drawVan(d, v); }
      }
      for (const b of d.builders || []) {
        const key = `builder:${b.side}:${b.id}`, mine = key === sel;
        if (!this.layers.trucks && !mine) continue;
        marker([b.z, b.x], `<div class="bd ${esc(b.side)}${sel && !mine ? " dim" : ""}"></div>`, [14, 14])
          .bindTooltip(`<b>${esc(b.side)} builder</b> of ${esc(b.base || "?")} · ${esc(String(b.doing || "").toLowerCase())}${b.what && b.what !== "-" ? " - " + esc(b.what) + " " + esc(b.progress || "") : ""}`, tip)
          .on("click", () => this.pick(key)).addTo(g.units);
        if (mine) { found = true; this.selAt = L.latLng(b.z, b.x); this.drawBuilder(d, b, col[b.side] || css("--muted")); }
      }
      if (sel && !found) this.sheet({ title: esc(sel.split(":").slice(1).join(" ").replace(/^(US|USSR) (\w+)$/, "$1 $2") || sel), sub: "",
        html: `<p class="muted">Not on the map any more - all its men lost, or it was merged into another team${d.live ? "" : ", or the battle ended before"}.</p>`,
        unit: { who: sel.replace(/:/g, " "), kind: sel.split(":")[0], key: sel, run: d.run, t: d.t } });
      else if (!sel) this.sheet(null);
      this.keepInSight();
    },

    drawEfforts(d, col, dim) {
      const g = this.g.plans, now = d.bases_now || [];
      const find = (name, s, own) => { const c = now.filter((b) => b.name === name); return c.find((b) => own ? b.owner === s : b.owner !== s) || c[0]; };
      const op = dim ? .3 : 1;
      for (const [s, e] of Object.entries(d.efforts || {})) {
        const c = col[s] || css("--muted");
        for (const a of e.attack || []) {
          const b = find(a.base, s, false);
          if (!b) continue;
          const there = `${a.there ?? 0}/${a.men} there`;
          if (b.owner === s) {   // teams sent to a base it holds: reinforcing it
            L.circle([b.z, b.x], { radius: 150, color: c, weight: 2, dashArray: "2 7", fill: false, opacity: op, bubblingMouseEvents: false })
              .bindTooltip(`${esc(s)} reinforces ${esc(a.base)}: ${a.teams} teams, ${there}`, { className: "tip" }).addTo(g);
            continue;
          }
          const main = a.base === e.main;
          const from = (d.teams || []).filter((t) => t.side === s && t.role === "ATTACK" && t.to === a.base && t.posture !== "LONE_SURVIVOR_RETREAT");
          let fx, fz;
          if (from.length) { fx = from.reduce((v, t) => v + t.x, 0) / from.length; fz = from.reduce((v, t) => v + t.z, 0) / from.length; }
          else {
            const o = now.filter((x) => x.owner === s).sort((p, q) => Math.hypot(p.x - b.x, p.z - b.z) - Math.hypot(q.x - b.x, q.z - b.z))[0];
            if (!o) continue;
            fx = o.x; fz = o.z;
          }
          const dx = b.x - fx, dz = b.z - fz, L0 = Math.hypot(dx, dz) || 1, ux = dx / L0, uz = dz / L0;
          // Lighter than the teams and their lanes: the arrow says where a side's weight goes, the lanes say how.
          const ex = b.x - ux * 80, ez = b.z - uz * 80, hl = main ? 70 : 50, hw = main ? 36 : 26;
          const words = `${esc(s)} ${main ? "main effort" : "attack"} → ${esc(a.base)} · ${there} · ${a.teams} teams`;
          const label = { permanent: true, direction: "center", className: `lbl effort ${esc(s)}`, pane: "labels" };
          let shaft = null;
          if (L0 > 200) {
            shaft = L.polyline([[fz, fx], [ez - uz * hl * .6, ex - ux * hl * .6]], { color: c, weight: main ? 6 : 3 + Math.min(2, a.men / 6), opacity: (main ? .55 : .4) * op, lineCap: "butt", bubblingMouseEvents: false });
            shaft.bindTooltip(main && !dim ? `${esc(s)} main effort: ${there}` : words, main && !dim ? label : { className: "tip" }).addTo(g);
          }
          const head = L.polygon([[ez, ex], [ez - uz * hl - ux * hw, ex - ux * hl + uz * hw], [ez - uz * hl + ux * hw, ex - ux * hl - uz * hw]],
            { color: "#fff", weight: 1.5, fillColor: c, fillOpacity: (main ? .7 : .5) * op, opacity: op, bubblingMouseEvents: false });
          head.bindTooltip(main && !shaft && !dim ? `${esc(s)} main effort: ${there}` : words, main && !shaft && !dim ? label : { className: "tip" }).addTo(g);
          if (shaft && main && !dim) head.bindTooltip(words, { className: "tip" });
        }
        for (const a of e.defend || []) {
          const b = find(a.base, s, true);
          if (!b) continue;
          L.circle([b.z, b.x], { radius: 190, color: c, weight: 2.5, dashArray: "9 7", fill: false, opacity: .8 * op, bubblingMouseEvents: false })
            .bindTooltip(`${esc(s)} defends ${b.hq ? "its HQ" : esc(a.base)}: ${a.teams} teams, ${a.there ?? 0}/${a.men} there`, { className: "tip" }).addTo(g);
        }
      }
    },

    drawLanes(d, col, sel) {
      const g = this.g.plans;
      const mineSide = sel && sel.startsWith("team:") ? sel.split(":")[1] : null, mineId = mineSide ? Number(sel.split(":")[2]) : null;
      for (const p of d.attack_plans || []) {
        const c = col[p.side] || css("--muted");
        const mine = mineSide === p.side && p.teams.includes(mineId);
        const op = sel ? (mine ? .9 : .25) : .9;
        const tipTxt = `<b>${esc(p.side)} ${p.by === "Gemini" ? "Gemini's" : p.by ? "the rules'" : "stored"} plan ${esc(p.id)}</b> · teams ${p.teams.map((n) => esc(n)).join(", ")}`
          + `<br>Get out ${p.assembly_m != null ? p.assembly_m + " m out (ring)" : "at the ring"}, hidden from the objective; ${p.lanes.length} lane${p.lanes.length === 1 ? "" : "s"} through cover`
          + (p.why ? `<br><i>“${esc(p.why)}”</i>` : "");
        if (p.drive && p.drive.length > 1) L.polyline(ll(p.drive), { color: c, weight: 2, opacity: .6 * op, dashArray: "2 6", interactive: false }).addTo(g);
        if (p.assembly) L.circle([p.assembly[1], p.assembly[0]], { radius: 40, color: c, weight: 2.5, fillColor: c, fillOpacity: .12 * op, opacity: op, bubblingMouseEvents: false }).bindTooltip(tipTxt, { className: "tip" }).addTo(g);
        p.lanes.forEach((lane, i) => {
          if (lane.length < 2) return;
          L.polyline(ll(lane), { color: "#fff", weight: 6, opacity: .65 * op, interactive: false }).addTo(g);
          L.polyline(ll(lane), { color: c, weight: 3, opacity: op, bubblingMouseEvents: false }).bindTooltip(tipTxt, { className: "tip", sticky: true }).addTo(g);
          const a = lane[lane.length - 2], b = lane[lane.length - 1];
          const dx = b[0] - a[0], dz = b[1] - a[1], L0 = Math.hypot(dx, dz) || 1, ux = dx / L0, uz = dz / L0, hl = 26, hw = 13;
          L.polygon([[b[1], b[0]], [b[1] - uz * hl - ux * hw, b[0] - ux * hl + uz * hw], [b[1] - uz * hl + ux * hw, b[0] - ux * hl - uz * hw]],
            { color: "#fff", weight: 1, fillColor: c, fillOpacity: op, opacity: op, interactive: false }).addTo(g);
          const h = (p.holds || [])[i];
          if (h) {
            const j = lane.reduce((best, q, k) => Math.hypot(q[0] - h[0], q[1] - h[1]) < Math.hypot(lane[best][0] - h[0], lane[best][1] - h[1]) ? k : best, 0);
            const q0 = lane[Math.max(0, j - 1)], q1 = lane[Math.min(lane.length - 1, j + 1)];
            const ddx = q1[0] - q0[0], ddz = q1[1] - q0[1], dl = Math.hypot(ddx, ddz) || 1, px = -ddz / dl * 20, pz = ddx / dl * 20;
            L.polyline([[h[1] - pz, h[0] - px], [h[1] + pz, h[0] + px]], { color: "#111", weight: 4, opacity: .8 * op, interactive: false }).addTo(g);
          }
        });
      }
    },

    // ---- the clicked team: its route ahead (dark line, numbered: amber = NEXT, grey = passed), the game's own waypoints
    // (square badges, white dashes), where it walked (thin), and the sheet with all of it in words.
    drawTeam(d, t, c) {
      const g = this.g.sel, point = (d.battle || {}).point;
      const key = `team:${t.side}:${t.id}`;
      const trail = (d.trails || {})[key] || [];
      if (trail.length > 1) L.polyline(ll(trail), { color: c, weight: 3, opacity: .6, interactive: false }).addTo(g);
      const wpIcon = (q, html, cls, z) => L.marker([q[1], q[0]], { bubblingMouseEvents: false, keyboard: false, zIndexOffset: z || 1500,
        icon: L.divIcon({ className: "", iconSize: cls.includes("next") ? [26, 26] : [22, 22], iconAnchor: cls.includes("next") ? [13, 13] : [11, 11], html: `<div class="wp ${cls}">${html}</div>` }) });
      const pl = (d.attack_plans || []).find((p) => p.side === t.side && p.teams.includes(Number(t.id)));
      const rows = [];
      let planHead = "", planWhy = "", ahead = [], laneLen = 0;
      if (pl && pl.lanes.length) {
        const laneIdx = pl.by ? 0 : Number(t.id) % pl.lanes.length;
        const lane = pl.lanes[laneIdx] || [];
        const kinds = (pl.lane_kinds && pl.lane_kinds[laneIdx]) || [];
        const near = lane.reduce((best, q, k) => { const m = Math.hypot(q[0] - t.x, q[1] - t.z); return m < best[0] ? [m, k] : best; }, [1e9, -1]);
        const onLane = near[0] < 60;
        const pre = !onLane && t.ride && pl.go !== 0 && pl.assembly ? [pl.assembly] : [];
        const first = onLane ? near[1] + 1 : 0;
        ahead = onLane ? lane.slice(first) : [...pre, ...lane];
        laneLen = lane.length;
        if (onLane && first > 0) L.polyline(ll(lane.slice(0, first + 1)), { color: "#8d948f", weight: 3, opacity: .8, dashArray: "4 5", interactive: false }).addTo(g);
        const route = ahead.length ? [[t.x, t.z], ...ahead] : null;
        if (route) {
          L.polyline(ll(route), { color: "#fff", weight: 8, opacity: .85, interactive: false }).addTo(g);
          L.polyline(ll(route), { color: css("--sel"), weight: 4, opacity: .95, interactive: false }).addTo(g);
        }
        if (onLane) lane.slice(0, first).forEach((q, k) => {
          const [kw] = kindWords(kinds[k], point);
          wpIcon(q, "✓", "passed", 1200).bindTooltip(`Passed: waypoint ${k + 1} - ${esc(kw)}`, { className: "tip" }).addTo(g);
          rows.push({ cls: "passed", n: "✓", badge: "passed", k: kindWords(kinds[k], point), st: "passed" });
        });
        ahead.forEach((q, k) => {
          const li = onLane ? first + k : k - pre.length;
          const kw = li < 0 ? ["Drop point", "get out of the vehicle here"] : kindWords(kinds[li], point);
          const n = li < 0 ? "D" : String(li + 1), nx = k === 0;
          const dist = nx ? km(Math.hypot(q[0] - t.x, q[1] - t.z)) : "";
          wpIcon(q, esc(n), nx ? "next" : "", nx ? 1700 : 1500).bindTooltip(`${nx ? "NEXT" : "Then"}: waypoint ${esc(n)} of ${laneLen} - ${esc(kw[0])}${dist ? " - " + dist + " away" : ""}`, { className: "tip" }).addTo(g);
          rows.push({ cls: nx ? "next" : "", n, badge: nx ? "next" : "", k: kw, st: nx ? `NEXT · ${dist}` : "then" });
        });
        const h = (pl.holds || [])[laneIdx];
        if (h) L.circleMarker([h[1], h[0]], { radius: 6, color: "#111", weight: 3, fillColor: "#fff", fillOpacity: 1, bubblingMouseEvents: false })
          .bindTooltip(pl.go === 0 ? "Its support position" : "Hold point on its lane - it waits here for the go", { className: "tip" }).addTo(g);
        const to = (pl.team_orders || {})[String(t.id)] || {};
        const by = to.source === "model" ? "Gemini" : to.source === "code" ? "rules" : pl.by === "Gemini" ? "Gemini" : pl.by ? "rules" : "";
        const why = to.why || (pl.why && pl.teams.length === 1 ? pl.why : "") || "";
        const whyWords = /^code: ?cheapest/i.test(why) ? "the cheapest route by the rules' cost (cover, enemy sightlines, length)" : why;
        planHead = `${by === "Gemini" ? "Gemini's" : by === "rules" ? "The rules'" : "The stored"} plan ${esc(pl.id)} · ${ahead.length} waypoint${ahead.length === 1 ? "" : "s"} ahead, ${km(len(route || []))}`;
        planWhy = `<div class="why${by === "Gemini" ? "" : " rules"}"><div><span class="tag ${by === "Gemini" ? "gem" : "rules"}">${by === "Gemini" ? "Gemini" : "Rules"}</span>
          plan <b>${esc(pl.id)}</b> · order <b>${esc(to.order || (pl.go === 0 ? "support" : "go"))}</b>${to.source === "kept" ? " <span class=\"muted\">(kept from an earlier answer)</span>" : ""}</div>
          ${whyWords ? `<q>${esc(whyWords)}</q>` : pl.why ? `<span class="muted">Its route group: “${esc(pl.why)}”</span>` : ""}</div>`;
      }
      // The game's own waypoint queue (ZCR_LiveMap wps= / wpk=): move, search and destroy, defend, hold; storm.
      const queue = t.wps && t.wps.length ? t.wps : null;
      const gameRows = [];
      if (queue) {
        L.polyline(ll([[t.x, t.z], ...queue]), { color: "#000", weight: 4.5, opacity: .35, interactive: false }).addTo(g);
        L.polyline(ll([[t.x, t.z], ...queue]), { color: "#fff", weight: 2.5, opacity: .95, dashArray: "6 5", interactive: false }).addTo(g);
        queue.forEach((q, k) => {
          const wk = (t.wpk || [])[k] || {};
          const storm = Number(wk.level) > 0;
          const w = ORDER[wk.kind] || wk.kind || "order";
          wpIcon(q, String(k + 1), k === 0 ? "game cur" : "game", 1400).bindTooltip(`${k === 0 ? "The game's order now" : "Queued"}: ${esc(w)}${storm ? " - storm" : ""}${wk.radius ? `, done within ${esc(wk.radius)} m` : ""}`, { className: "tip" }).addTo(g);
          gameRows.push({ n: k + 1, cur: k === 0, w, storm, r: wk.radius, dist: k === 0 ? km(Math.hypot(q[0] - t.x, q[1] - t.z)) : "" });
        });
      }
      const now = (t.wpk || [])[0] || {};
      const order = queue ? `${ORDER[now.kind] || now.kind || "move"}${Number(now.level) > 0 ? " · storm (keeps moving under fire)" : ""}` : "";
      const badge = (r) => `<span class="wp ${r.badge}" style="${r.badge === "next" ? "" : "width:22px;height:22px"}">${esc(r.n)}</span>`;
      const html = `<div class="facts">
          ${order ? `<div>The game's order now: <b>${esc(order)}</b>${gameRows[0] ? ` · ${gameRows[0].dist} to it` : ""}</div>` : ""}
          <div>${t.to && t.to !== "-" ? `Assigned <b>${esc(t.to)}</b> · ` : ""}walked ${km(len(trail))} so far${t.ride ? " · riding now" : ""}</div></div>
        ${planWhy}
        ${rows.length ? `<h3>${planHead}</h3><ol class="wps">${rows.map((r) => `<li class="${r.cls}"><span class="n">${badge(r)}</span><span class="k">${esc(r.k[0])}${r.k[1] ? `<small>${esc(r.k[1])}</small>` : ""}</span><span class="st">${esc(r.st)}</span></li>`).join("")}</ol>
          ${pl && pl.chain ? `<p class="muted" style="margin:0;font-size:13px">Cover along the way: ${esc(pl.chain.replace(/Farm$/, point || "the objective"))}</p>` : ""}`
          : `<p class="muted" style="margin:0">Not on a planned route - AI Conflict's own waypoints.</p>`}
        ${gameRows.length ? `<h3>The game's waypoints (${gameRows.length})</h3><ol class="wps">${gameRows.map((r) => `<li class="${r.cur ? "next" : ""}"><span class="n"><span class="wp game${r.cur ? " cur" : ""}" style="width:22px;height:22px">${r.n}</span></span>
          <span class="k">${esc(cap(r.w))}${r.storm ? "<small>storm - keeps moving under fire, runs</small>" : ""}</span><span class="st">${r.cur ? "NOW · " + esc(r.dist) : "queued"}${r.r ? ` · ${esc(r.r)} m` : ""}</span></li>`).join("")}</ol>` : ""}`;
      const what = doingOf(t);
      this.sheet({ title: `<span class="sw ${esc(t.side)}"></span>${esc(t.side)} team ${esc(t.id)}`, sub: `${Math.round(t.men || 0)} men · ${esc(what)} · ${t.ride ? "riding" : "on foot"}`, html,
        unit: { who: `${t.side} team ${t.id}`, kind: "team", side: t.side, id: t.id, role: t.role, men: t.men, ride: t.ride, doing: what, to: t.to,
          posture: t.posture, x: Math.round(t.x), z: Math.round(t.z), wp: t.wp, plan: pl ? pl.id : null, run: d.run, t: d.t } });
    },
    drawTruck(d, t, c) {
      const g = this.g.sel, key = `truck:${t.side}:${t.id}`, trail = (d.trails || {})[key] || [];
      if (trail.length > 1) L.polyline(ll(trail), { color: c, weight: 3, opacity: .6, interactive: false }).addTo(g);
      const route = t.wps && t.wps.length ? [[t.x, t.z], ...t.wps] : null;
      if (route) { L.polyline(ll(route), { color: "#fff", weight: 8, opacity: .85, interactive: false }).addTo(g); L.polyline(ll(route), { color: css("--sel"), weight: 4, interactive: false }).addTo(g); }
      const phase = String(t.phase || "").replace(/_/g, " ").toLowerCase();
      this.sheet({ title: `<span class="sw ${esc(t.side)}"></span>${esc(t.side)} supply truck ${esc(t.id)}`, sub: `${esc(phase)} · ${Math.round(t.kmh || 0)} km/h`,
        html: `<div class="facts"><div><b>${esc(t.from || "?")}</b> → <b>${esc(t.to || "?")}</b></div>
          <div>${t.cargo >= 0 ? `${Math.round(t.cargo)} of ${Math.round(t.cap)} supplies aboard` : "cargo unknown"} · drove ${km(len(trail))}</div>
          <div>${route ? `Road route ahead ${km(len(route))} (dark line, the road graph's waypoints)` : "No road route - the game's own driver picks the way"}</div></div>`,
        unit: { who: `${t.side} supply truck ${t.id}`, kind: "truck", side: t.side, id: t.id, doing: phase, from: t.from, to: t.to, x: Math.round(t.x), z: Math.round(t.z), run: d.run, t: d.t } });
    },
    drawVan(d, v) {
      const g = this.g.sel, key = `van:${v.id}`, trail = (d.trails || {})[key] || [], r = (d.routes || {})[v.id], p = (d.paths || {})[v.id];
      if (trail.length > 1) L.polyline(ll(trail), { color: "#a05a00", weight: 3, opacity: .6, interactive: false }).addTo(g);
      if (r && r.length > 1) L.polyline(ll(r), { color: css("--sel"), weight: 4, opacity: .85, interactive: false }).addTo(g);
      if (p && p.length > 1) L.polyline(ll(p), { color: "#fff", weight: 2.5, dashArray: "6 5", interactive: false }).addTo(g);
      this.sheet({ title: `Test van ${esc(v.id)}`, sub: `${esc(String(v.phase || "").toLowerCase())} · ${Math.round(v.kmh || 0)} km/h`,
        html: `<div class="facts"><div>${v.to ? `To <b>${esc(v.to)}</b> · ` : ""}${Math.round(v.cargo || 0)} supplies · drove ${km(len(trail))}</div>
          <div>${r ? `Planned route ${km(len(r))} (dark)` : "No planned route - the game's own driver picks the way"}${p ? " · white dashes: the game's path now" : ""}</div></div>`,
        unit: { who: `van ${v.id}`, kind: "van", id: v.id, doing: v.phase, to: v.to, x: Math.round(v.x), z: Math.round(v.z), run: d.run, t: d.t } });
    },
    drawBuilder(d, b, c) {
      const g = this.g.sel, doing = String(b.doing || "").toLowerCase(), what = b.what && b.what !== "-" ? b.what : "";
      if (b.sx != null && what) {
        L.polyline([[b.z, b.x], [b.sz, b.sx]], { color: c, weight: 3, opacity: .8, dashArray: "3 4", interactive: false }).addTo(g);
        L.rectangle([[b.sz - 7, b.sx - 7], [b.sz + 7, b.sx + 7]], { color: c, weight: 2, fillColor: "#fff", fillOpacity: .6, interactive: false }).addTo(g);
      }
      this.sheet({ title: `<span class="sw ${esc(b.side)}"></span>${esc(b.side)} builder`, sub: `${esc(doing)} · ${esc(b.base || "?")}`,
        html: `<div class="facts"><div>${what ? `Building <b>${esc(what)}</b> ${esc(b.progress || "")}` : "No building right now"}</div>
          ${doing === "walking" && b.sx != null ? `<div>${km(Math.hypot(b.sx - b.x, b.sz - b.z))} to his work spot (dashes)</div>` : ""}</div>`,
        unit: { who: `${b.side} builder ${b.id}`, kind: "builder", side: b.side, id: b.id, doing, base: b.base, x: Math.round(b.x), z: Math.round(b.z), run: d.run, t: d.t } });
    },

    // The sheet: redrawn every refresh, the remark box below it is not (typing survives).
    sheet(o) {
      const s = $("sheet");
      if (!o) { s.hidden = true; this.unit = null; return; }
      const was = s.hidden;
      s.hidden = false;
      $("sh-title").innerHTML = o.title;
      $("sh-sub").innerHTML = o.sub || "";
      $("sh-info").innerHTML = Cam.button(o.unit) + o.html;
      $("sh-who").textContent = o.unit && o.unit.who ? o.unit.who : "it";
      this.unit = o.unit || null;
      if (was) { $("sh-sent").textContent = ""; setTimeout(() => this.view && this.view.invalidateSize(), 30); }
    },

    legend() {
      const sw = (inner) => `<svg viewBox="0 0 30 20" aria-hidden="true">${inner}</svg>`;
      $("legend").innerHTML = `
        <h3>Teams</h3>
        <div class="it"><span><span class="tm US" style="display:inline-grid">3</span></span><span>An attacking team and its number (blue US, red USSR)</span></div>
        <div class="it"><span><span class="tm US hold" style="display:inline-grid">7</span></span><span>A team defending or guarding; faded: its last man going home</span></div>
        <div class="it">${sw(`<circle cx="6" cy="10" r="3" style="fill:var(--us)"/><circle cx="15" cy="10" r="3" style="fill:none;stroke:var(--us);stroke-width:1.5"/><circle cx="24" cy="10" r="3" style="fill:none;stroke:var(--ussr);stroke-width:1.5"/>`)}<span>Each soldier: filled standing, hollow prone, a ring in a vehicle</span></div>
        <h3>Plans</h3>
        <div class="it">${sw(`<path d="M2 10h17" style="stroke:var(--us);stroke-width:5"/><path d="M18 3l10 7-10 7z" style="fill:var(--us);stroke:#fff"/>`)}<span>A side's attack; thick, labelled: its main effort ("4/28 there" = soldiers within 300 m)</span></div>
        <div class="it">${sw(`<circle cx="15" cy="10" r="8" style="fill:none;stroke:var(--ussr);stroke-width:2;stroke-dasharray:4 3"/>`)}<span>A base the side defends</span></div>
        <div class="it">${sw(`<path d="M2 15c8-2 14-10 26-8" style="fill:none;stroke:#fff;stroke-width:6"/><path d="M2 15c8-2 14-10 26-8" style="fill:none;stroke:var(--us);stroke-width:3"/>`)}<span>A line of attack through cover; ring: where the teams get out; black bar: the hold line</span></div>
        <div class="it">${sw(`<circle cx="15" cy="10" r="8" style="fill:var(--ussr);fill-opacity:.15;stroke:var(--ussr);stroke-width:2;stroke-dasharray:3 3"/><path d="M10 5l10 10M20 5L10 15" style="stroke:var(--ussr);stroke-width:2"/>`)}<span>Danger zone: the side lost soldiers or vehicles here lately - a risk its general weighs, not a wall</span></div>
        <h3>The clicked team</h3>
        <div class="it"><span><span class="wp next" style="display:inline-grid;width:24px;height:24px">3</span></span><span>Its NEXT waypoint; dark: the ones after; grey ✓: passed</span></div>
        <div class="it"><span><span class="wp game cur" style="display:inline-grid">1</span></span><span>The game's own waypoints (white dashes): move, search and destroy, defend, hold, storm</span></div>
        <h3>Map</h3>
        <div class="it">${sw(`<circle cx="15" cy="10" r="7" style="fill:var(--ussr);fill-opacity:.25;stroke:var(--ussr);stroke-width:3"/>`)}<span>A base, ring in the owner's colour; the point is the big one</span></div>
        <div class="row"><span class="muted">Tiles</span><span class="seg" role="group" aria-label="Tiles">
          <button type="button" data-tiles="topo" aria-pressed="${this.tiles === "topo"}">Topo</button><button type="button" data-tiles="satellite" aria-pressed="${this.tiles === "satellite"}">Satellite</button></span></div>
        <p class="muted" style="margin:0;font-size:12px">Map © <a href="https://enfumap.com" target="_blank" rel="noopener">Enfumap</a>, drawn from the game's files; not affiliated with Bohemia Interactive.</p>`;
      for (const b of $("legend").querySelectorAll("button[data-tiles]")) b.addEventListener("click", () => {
        this.tiles = b.dataset.tiles;
        store.set("tiles", this.tiles);
        this.setTiles();
        this.legend();
      });
    },
  };

  // ============================================================ Progress: training curves
  // Each test's questions (lab/sublabs/<name>.toml [[questions]], via /api/slow) and the engine page's match measures
  // (lab/app/progress_specs.py, via /api/progress): one curve per question - a dot per run, the average of the last runs,
  // the target, the first run on each build. Colour follows the thing: Gemini violet, the rules orange, US blue, USSR red.
  const Prog = {
    labs: [], prog: null, at: 0, cur: null, charts: [],
    async open(arg) {
      if (!this.wired) {
        this.wired = true;
        window.addEventListener("resize", () => { for (const c of this.charts) c.resize(); });
        matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (view === "progress") this.render(); });
      }
      if (!window.echarts) {
        $("pg-body").innerHTML = '<div class="empty">Loading the charts…</div>';
        try { await loadScript("/vendor/echarts.min.js"); } catch (_) { $("pg-body").innerHTML = '<div class="empty">The charts library did not load.</div>'; return; }
      }
      if (!this.at || Date.now() - this.at > 120000) await this.load();
      const names = this.items().map((x) => x.key);
      const want = arg && names.includes(arg) ? arg : this.cur && names.includes(this.cur) ? this.cur : names.includes(store.get("test", "")) ? store.get("test", "") : names[0];
      this.pick(want, false);
    },
    async load() {
      try {
        const [slow, prog] = await Promise.all([fetch("/api/slow").then((r) => r.json()), fetch("/api/progress").then((r) => r.json())]);
        this.labs = (slow.sublab || []).filter((l) => (l.all || []).some((r) => !r.watched)).sort((a, b) => String(b.last_at || "").localeCompare(String(a.last_at || "")));
        this.prog = prog && prog.rows ? prog : null;
        this.at = Date.now();
      } catch (_) { $("pg-body").innerHTML = '<div class="empty">The lab app didn\'t answer.</div>'; }
    },
    items() {
      const out = this.labs.map((l) => ({ key: l.name, label: cap(l.title || l.name), n: (l.all || []).filter((r) => !r.watched).length }));
      // 5 Nov (Martin: "what about overall progress why did we drop that? ... it seemed important there was a lot a features"):
      // the whole matches' ~30 measures first in the picker, as on the old page.
      if (this.prog) out.unshift({ key: "matches", label: "Overall progress", n: this.prog.rows.filter((r) => r.kind !== "probe" && r.family !== "control").length });
      return out;
    },
    pick(key, push = true) {
      this.cur = key;
      store.set("test", key);
      if (push && location.hash !== "#progress/" + key) history.replaceState(null, "", "#progress/" + encodeURIComponent(key));
      $("pg-picker").innerHTML = this.items().map((x) => `<button type="button" data-k="${esc(x.key)}" aria-pressed="${x.key === key}">${esc(x.label)}<small>${x.n}</small></button>`).join("");
      for (const b of $("pg-picker").querySelectorAll("button")) b.addEventListener("click", () => this.pick(b.dataset.k));
      const on = $("pg-picker").querySelector('[aria-pressed="true"]');
      if (on) on.scrollIntoView({ block: "nearest", inline: "nearest" });
      this.render();
    },
    render() {
      for (const c of this.charts) c.dispose();
      this.charts = [];
      const body = $("pg-body");
      if (this.cur === "matches") return this.renderMatches(body);
      const l = this.labs.find((x) => x.name === this.cur);
      if (!l) { body.innerHTML = '<div class="empty">No integration tests with runs yet.</div>'; return; }
      const runs = (l.all || []).filter((r) => !r.watched).sort((a, b) => String(a.at).localeCompare(String(b.at)));
      const qs = (l.questions || []).slice();
      const main = l.main || (qs[0] && qs[0].key);
      if (main && !qs.some((q) => q.key === main)) qs.unshift({ key: main, title: cap(main.replace(/_/g, " ")), better: /lost|crash|stuck|fail|jam|hit|error|walk|wait|_s$/.test(main) ? "lower" : "higher" });
      qs.sort((a, b) => (b.key === main) - (a.key === main));
      const S = (sc) => (l.slabel || {})[sc] || sc;
      const tracks = [...new Set(runs.map((r) => r.scenario))];
      const groups = tracks.map((sc, i) => ({ key: sc, name: S(sc), color: entityColor(sc + " " + S(sc), i) }));
      const sm = l.summary || {};
      body.innerHTML = `<div class="card"><h2 class="pg">${esc(l.title || l.name)}</h2><p class="lead">${esc(l.question || "")}</p>
          ${sm.verdict ? `<p class="verdict">${esc(sm.verdict)}${sm.at ? ` <span class="muted">(${esc(sm.at)})</span>` : ""}</p>` : ""}
          <p class="muted" style="margin:0;font-size:13.5px">${runs.length} runs, ${esc(shortAt(runs[0] && runs[0].at))} to ${esc(shortAt(runs[runs.length - 1] && runs[runs.length - 1].at))}${groups.length > 1 ? " · " + groups.map((g) => esc(g.name)).join(", ") : ""} ·
          <a class="plain" href="/#sublab/${encodeURIComponent(l.name)}">its setups, runs and tables on the old page</a></p></div>
        <div class="curves" id="pg-curves"></div>`;
      const box = $("pg-curves");
      const blds = Object.fromEntries((l.builds || []).map((b) => [b.n, b.name]));
      qs.forEach((q, i) => {
        const pts = runs.filter((r) => typeof r[q.key] === "number");
        if (!pts.length) return;
        this.curve(box, {
          big: i === 0, title: q.title || q.key, better: q.better, target: typeof q.target === "number" ? q.target : null,
          why: (q.quote ? `Martin: “${q.quote}” - ` : "") + (q.axis || ""), unit: "",
          xs: pts.map((r) => shortAt(r.at)), groups, split: !!l.split_average && groups.length > 1, avgN: 5,
          points: pts.map((r) => ({ g: r.scenario, v: r[q.key], build: r.build, tip: `${esc(S(r.scenario))} · ${esc((l.vlabel || {})[r.variant] || r.variant)}${r.build != null ? " · build r" + r.build : ""}` })),
          buildName: blds,
        });
      });
      if (!box.children.length) box.innerHTML = '<div class="empty">No numbers in these runs yet.</div>';
    },
    renderMatches(body) {
      const P = this.prog;
      if (!P) { body.innerHTML = '<div class="empty">Measuring the matches - ready in a minute.</div>'; return; }
      const rows = P.rows.filter((r) => r.kind !== "probe" && r.family !== "control").sort((a, b) => String(a.started).localeCompare(String(b.started)));
      const blds = Object.fromEntries((P.builds || []).map((b) => [b.n, b.name]));
      body.innerHTML = `<div class="card"><h2 class="pg">Overall progress - whole matches</h2>
          <p class="lead">The engine page's measures over every watched and headless match, ${esc(shortAt(rows[0] && rows[0].started))} to ${esc(shortAt(rows[rows.length - 1] && rows[rows.length - 1].started))}. No whole matches since then - the work moved to the integration tests.</p>
          <p class="muted" style="margin:0;font-size:13.5px"><a class="plain" href="/#progress">per build and every match on the old page</a></p></div>
        <div class="curves" id="pg-curves"></div>`;
      const box = $("pg-curves");
      const order = ["checks", "lost", "exchange", "cover", "panic", "atbase", "traffic", "fps"];   // the ones asked about most, first
      const charts = P.charts.slice().sort((a, b) => ((order.indexOf(a.id) + 1) || 99) - ((order.indexOf(b.id) + 1) || 99));
      charts.forEach((spec) => {
        const ms = spec.measures.slice(0, 4);
        const pts = rows.filter((r) => ms.some((m) => r[m.key] != null));
        if (pts.length < 3) return;
        // One series per measure (a measure is a thing, so it keeps its slot); each its own moving average.
        const groups = ms.map((m, i) => ({ key: m.key, name: m.label, color: entityColor(m.label, i) }));
        const points = [];
        pts.forEach((r, i) => ms.forEach((m) => { if (r[m.key] != null) points.push({ i, g: m.key, v: r[m.key], build: r.build, tip: `${esc(r.run)}${r.build != null ? " · build r" + r.build : ""}` }); }));
        this.curve(box, {
          big: false, title: spec.title, better: spec.better, target: spec.target ? spec.target[0] : null, targetLabel: spec.target ? spec.target[1] : "",
          why: spec.why, unit: spec.unit || "", xs: pts.map((r) => shortAt(r.started)), groups, split: true, avgN: 10, points, buildName: blds, byIndex: true,
          builds: pts.map((r) => r.build),
        });
      });
    },
    // One training curve. o.points: [{g, v, build, tip, i?}] (i = the x index when several points share a run).
    curve(box, o) {
      const el = document.createElement("div");
      el.className = "card curve" + (o.big ? " big" : " small");
      const n = o.xs.length;
      // Long names sharing their start ("Arland - the whole map US" / "... Soviet") are shown by what differs.
      const short = shortNames(o.groups.map((gr) => gr.name));
      o.groups = o.groups.map((gr, i) => Object.assign({}, gr, { name: short[i] }));
      const split = o.split && o.groups.length > 1;   // one average line per group; one group: the plain curve
      const idx = (p, k) => o.byIndex ? p.i : k;
      // Moving averages: per group when split, else over every run.
      const avgLine = (sel) => {
        const out = new Array(n).fill(null), win = [];
        o.points.forEach((p, k) => { if (!sel(p)) return; win.push(p.v); if (win.length > o.avgN) win.shift(); out[idx(p, k)] = win.reduce((a, b) => a + b, 0) / win.length; });
        return out;
      };
      const lines = split ? o.groups.map((gr) => ({ gr, data: avgLine((p) => p.g === gr.key) })) : [{ gr: { key: "_all", name: `average of the last ${o.avgN}`, color: css("--ink") }, data: avgLine(() => true) }];
      const lastOf = (a) => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
      const meets = (v) => o.target == null || v == null ? null : o.better === "higher" ? v >= o.target : v <= o.target;
      const unit = o.unit ? String(o.unit).replace(/^ /, "") : "";
      const tgtWords = o.target == null ? "" : o.targetLabel && !/^\d/.test(o.targetLabel) ? (/^(target|limit)\b/i.test(o.targetLabel) ? o.targetLabel : "target: " + o.targetLabel) : `target ${o.better === "higher" ? "≥" : "≤"} ${o.target}${unit && unit !== "%" ? " " + unit : unit}`;
      const nowHtml = split
        ? lines.map((ln) => { const v = lastOf(ln.data), ok = meets(v); return `<span class="grp"><i style="background:${ln.gr.color}"></i>${esc(ln.gr.name)} <b class="mono">${fmt1(v)}${esc(unit === "%" ? "%" : "")}</b>${ok === true ? " ✓" : ""}</span>`; }).join("")
        : (() => { const v = lastOf(lines[0].data), ok = meets(v); return `<span class="v">${fmt1(v)}${esc(unit === "%" ? "%" : "")}</span><span class="lab">now - the average of the last ${o.avgN}</span>${ok == null ? "" : `<span class="pill ${ok ? "ok" : "no"}">${ok ? "meets" : "misses"} ${esc(tgtWords)}</span>`}`; })();
      el.innerHTML = `<div class="hd"><h3>${esc(o.title)}</h3><span class="better">${o.better === "higher" ? "↑ higher is better" : o.better === "lower" ? "↓ lower is better" : ""}${o.target != null && split ? " · " + esc(tgtWords) : ""}</span></div>
        <div class="now">${nowHtml}</div><div class="ec" role="img" aria-label="${esc(o.title)} over the runs"></div>${o.why ? `<p class="axis">${esc(o.why)}</p>` : ""}`;
      box.appendChild(el);
      const chart = echarts.init(el.querySelector(".ec"), null, { renderer: "canvas" });
      this.charts.push(chart);
      const ink = css("--ink"), muted = css("--muted"), line = css("--line"), panel = css("--panel"), good = css("--good");
      const series = [];
      const multi = o.groups.length > 1;
      for (const gr of o.groups) {
        const data = new Array(n).fill(null);
        o.points.forEach((p, k) => { if (p.g === gr.key) data[idx(p, k)] = p.v; });
        series.push({ name: gr.name, type: "scatter", data, symbolSize: o.big ? 8 : 7, z: 3,
          itemStyle: { color: multi ? gr.color : muted, opacity: .6, borderColor: panel, borderWidth: 1 } });
      }
      // The build each run was on: a dotted line at the first run on a new build (labelled when there are few).
      const bOf = o.builds || o.points.map((p) => p.build);
      let marks = [];
      for (let k = 0; k < bOf.length; k++) if (bOf[k] != null && (k === 0 || bOf[k - 1] !== bOf[k])) marks.push({ xAxis: o.byIndex ? k : idx(o.points[k], k), name: "r" + bOf[k] });
      if (marks.length > 15) marks = [];   // dozens of builds: the lines would hide the runs (the tooltip still says the build)
      // Labels only where they don't run into the one before (builds a few runs apart).
      const plotW = Math.max(100, el.querySelector(".ec").clientWidth - 84);
      let lastPx = -1e9;
      for (const m of marks) { const px = (m.xAxis + .5) / Math.max(1, n) * plotW; m.show = o.big && px - lastPx >= 34; if (m.show) lastPx = px; }
      const labelBuilds = marks.some((m) => m.show);
      lines.forEach((ln, i) => {
        series.push({ name: ln.gr.name, type: "line", data: ln.data, connectNulls: true, showSymbol: false, smooth: 0.25, z: 4,
          lineStyle: { width: o.big ? 2.5 : 2, color: ln.gr.color }, itemStyle: { color: ln.gr.color },
          // Lines that end close together would stack their labels: with a line per group the row above carries the values.
          endLabel: { show: !split, formatter: (p) => fmt1(p.value), color: ink, fontSize: 11, fontFamily: '"JetBrains Mono", Consolas, monospace', distance: 4 },
          markLine: i === 0 ? { symbol: "none", silent: true, animation: false, data: [
            ...marks.map((m) => ({ xAxis: m.xAxis, name: m.name, lineStyle: { type: "dotted", color: muted, width: 1, opacity: .8 },
              label: { show: m.show, formatter: m.name, position: "end", color: muted, fontSize: 10, fontFamily: '"JetBrains Mono", Consolas, monospace' } })),
            ...(o.target != null ? [{ yAxis: o.target, name: "target", lineStyle: { type: "dashed", color: good, width: 1.5 },
              label: { formatter: tgtWords, position: "insideEndTop", color: good, fontSize: 10.5, fontFamily: '"JetBrains Mono", Consolas, monospace' } }] : []),
          ] } : undefined });
      });
      // With a line per group the row above the chart is its legend (colour, name, value now); tracks with one average
      // line get the chart's own legend.
      const legendNames = multi && !split ? o.groups.map((gr) => gr.name).concat([lines[0].gr.name]) : [];
      chart.setOption({
        animationDuration: 250,
        textStyle: { fontFamily: '"Source Sans 3", "Segoe UI", system-ui, sans-serif', color: ink },
        grid: { left: 40, right: 44, top: (legendNames.length ? 30 : 8) + (labelBuilds ? 18 : 6), bottom: 26 },
        legend: { show: !!legendNames.length, data: legendNames, top: 0, left: 0, itemWidth: 12, itemHeight: 8, type: "scroll", pageIconColor: ink,
          textStyle: { color: muted, fontSize: 12, fontFamily: '"Source Sans 3", "Segoe UI", system-ui, sans-serif' }, pageTextStyle: { color: muted } },
        tooltip: { trigger: "axis", confine: true, backgroundColor: panel, borderColor: line, textStyle: { color: ink, fontSize: 12.5 },
          axisPointer: { type: "line", lineStyle: { color: muted, width: 1 } },
          formatter: (ps) => {
            const k = ps[0].dataIndex;
            const here = o.points.filter((p, j) => idx(p, j) === k);
            const name = (gk) => (o.groups.find((x) => x.key === gk) || {}).name || gk;
            const head = `<b>${esc(o.xs[k])}</b>` + (here[0] ? `<br>${here[0].tip}${here[0].build != null && o.buildName[here[0].build] ? `<br><i style="opacity:.75">${esc(o.buildName[here[0].build])}</i>` : ""}` : "");
            const vals = here.map((p) => `${multi ? esc(name(p.g)) + ": " : ""}<b>${fmt1(p.v)}${esc(unit === "%" ? "%" : "")}</b>`).join("<br>");
            const avgs = lines.map((ln) => ln.data[k] != null ? `${esc(split ? ln.gr.name + ", average" : ln.gr.name)}: ${fmt1(ln.data[k])}` : "").filter(Boolean).join("<br>");
            return [head, vals, `<span style="opacity:.75">${avgs}</span>`].filter(Boolean).join("<br>");
          } },
        xAxis: { type: "category", data: o.xs, boundaryGap: true, axisLine: { lineStyle: { color: line } }, axisTick: { show: false },
          axisLabel: { show: o.big, color: muted, fontSize: 10.5, fontFamily: '"JetBrains Mono", Consolas, monospace', hideOverlap: true }, splitLine: { show: false } },
        yAxis: { type: "value", min: 0, axisLine: { show: false }, axisTick: { show: false },
          axisLabel: { color: muted, fontSize: 10.5, fontFamily: '"JetBrains Mono", Consolas, monospace' }, splitLine: { lineStyle: { color: line, width: 1 } } },
        series,
      });
    },
  };
  // Colour follows the thing, not its place: Gemini violet, the rules orange, the code aqua, US blue, USSR red; anything
  // else takes the validated categorical slots in order.
  function entityColor(text, i) {
    const t = String(text);
    if (/ussr|soviet/i.test(t)) return css("--ussr");
    if (/gemini/i.test(t)) return css("--gem");
    if (/\brule/i.test(t)) return css("--c2");
    if (/\bcode\b/i.test(t)) return css("--c3");
    if (/(^|\s)US(\s|$)|^arland\b/.test(t)) return css("--us");
    return css(["--c1", "--c2", "--c3", "--c4"][i % 4]);
  }
  function shortNames(names) {
    if (names.length < 2) return names;
    const words = names.map((x) => String(x).split(" "));
    let k = 0;
    while (words.every((w) => w.length > k + 1 && w[k] === words[0][k])) k++;
    return k >= 2 ? words.map((w) => w.slice(k).join(" ")) : names;
  }
  function loadScript(src) {
    return new Promise((ok, no) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  }

  // ============================================================ Remarks
  const Rem = {
    rows: [],
    open() {
      if (!this.wired) { this.wired = true; remarkBox($("rm-form"), $("rm-text"), $("rm-sent"), "rmkind", null); }
      this.load();
    },
    async load() {
      try {
        const r = await fetch("/api/inbox");
        if (!r.ok) return;
        this.rows = (await r.json()).remarks || [];
      } catch (_) { return; }
      const waiting = this.rows.filter((m) => m.status === "new").length;
      $("waiting-n").hidden = !waiting;
      $("waiting-n").textContent = waiting;
      $("waiting-n").title = `${waiting} remark${waiting === 1 ? "" : "s"} waiting for the loop`;
      if (view === "remarks") this.render();
    },
    render() {
      $("rm-count").textContent = this.rows.length ? `${this.rows.length} remark${this.rows.length === 1 ? "" : "s"}, newest first` : "";
      $("rm-list").innerHTML = this.rows.length ? this.rows.map((m) => {
        const u = m.unit && typeof m.unit === "object" ? m.unit : null;
        const st = m.status === "new" ? '<span class="pill wait">waiting for the loop</span>' : m.note ? `<span class="pill plain">note ${esc(m.note)}</span>` : `<span class="pill ok">${esc(m.status || "filed")}</span>`;
        return `<div class="rem"><div class="hd"><span class="kind ${esc(m.kind)}">${esc(m.kind)}</span><span class="when">${esc(shortAt(m.at))} · ${esc(ago(m.at))}</span>${st}</div>
          <div class="text">${esc(m.text)}</div>
          ${u ? `<div class="about">About ${esc(u.who || u.kind || "a unit")}${u.doing ? " (" + esc(u.doing) + ")" : ""}${u.t != null && u.t !== "" ? " · game " + mmss(Number(u.t)) : ""}${u.run ? " · " + esc(u.run) : ""}</div>` : ""}
          ${m.reply ? `<div class="reply"><b>Reply</b>${esc(m.reply)}</div>` : m.status === "new" ? '<div class="waiting">Not read yet - the loop files it at the start of its next step.</div>' : ""}</div>`;
      }).join("") : '<div class="empty">No remarks yet.</div>';
    },
  };

  // ============================================================ views
  let view = null;
  function show(name, arg) {
    view = name;
    for (const a of document.querySelectorAll(".views a")) { if (a.dataset.view === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); }
    for (const v of ["map", "progress", "remarks"]) $("v-" + v).hidden = v !== name;
    if (name === "map") MapV.open();
    if (name === "progress") Prog.open(arg);
    if (name === "remarks") Rem.open();
  }
  function route() {
    const [v, arg] = location.hash.slice(1).split("/");
    show(["map", "progress", "remarks"].includes(v) ? v : "map", arg ? decodeURIComponent(arg) : "");
  }
  window.addEventListener("hashchange", route);
  route();
  Rem.load();
  // The map every 5 s while a battle is live and the map is on screen; between battles every 15 s, and every 30 s from
  // the other views (the live dot in the header).
  setInterval(() => {
    if (document.hidden) return;
    const since = Date.now() - MapV.lastPoll;
    const live = MapV.d && MapV.d.live;
    if (view === "map" ? since > (live ? 4500 : 14500) : since > 29500) MapV.poll();
  }, 1000);
  setInterval(() => { if (!document.hidden) Rem.load(); }, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && view === "map") MapV.poll(); });
  window.LabV2 = { MapV, Prog, Rem };   // for checks from the console
  document.documentElement.dataset.ok = "1";
})();
