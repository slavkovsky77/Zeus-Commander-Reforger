// Interactive graphs for the lab app (Apache ECharts, lab/app/vendor): the Progress tab (the engine page's graphs,
// per build or every match), the goals match by match with their targets, and the live match's graphs.
// Colours: match kinds take the validated 8-colour categorical palette in a fixed order (a kind keeps its colour
// whatever is shown); sides are US blue / USSR red. Every graph has a table view (some light-mode colours are
// under 3:1 against the card).
window.LabCharts = (() => {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const isDark = () => matchMedia("(prefers-color-scheme: dark)").matches;
  const KIND_COLORS = {
    light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  };
  const kindColor = (i) => KIND_COLORS[isDark() ? "dark" : "light"][i % 8];
  const live = new Set();
  const NAMES = {
    truck_first_min: ["first supply truck", "game minute of the side's first supply truck job"],
    truck_unloads: ["loads delivered", "supply truck loads unloaded at a base, per side"],
    front_supply_pct: ["front bases' supplies", "the side's front bases (not its HQ) at the end of the match, % of their maximum"],
    drones_lost_water: ["drones lost in the sea", "drones the drone mod lost over the sea"],
    armour_assault: ["armour in the assault", "tanks and IFVs that got into the assault on their front, per side"],
    armour_kills: ["killed by armour", "enemy soldiers killed by tanks and IFVs, per side"],
    ended_early: ["ended early", "1 when the watched match ended early (a crash, a dead process, a lost connection)"],
    scorecard_fails: ["screen checks failed", "lab/scorecard.py's hard checks failed, both sides: team out by 3 min, at most 40% at the base at 10 min, teams of 2.5+, drones, riding, safe near drones"],
    forts: ["fortifications", "fortifications the side's engineers finished"],
    depots: ["supply depots", "supply depots the side built"],
  };
  const nameOf = (k) => (NAMES[k] || [k.replace(/_/g, " ")])[0];
  const whyOf = (k, fallback) => (NAMES[k] || [null, fallback])[1];
  const mean = (a) => a.length ? Math.round(10 * a.reduce((s, v) => s + v, 0) / a.length) / 10 : null;

  function base(extra = {}) {
    const ink = css("--ink"), muted = css("--muted"), line = css("--line"), panel = css("--panel");
    return {
      animationDuration: 300,
      textStyle: { fontFamily: "Source Sans 3, Segoe UI, system-ui, sans-serif", color: ink },
      grid: { left: 46, right: 18, top: 44, bottom: 58, containLabel: false },
      legend: { type: "scroll", top: 0, left: 0, right: 0, itemWidth: 14, itemHeight: 3, icon: "rect", textStyle: { color: muted, fontSize: 12 },
                pageIconColor: ink, pageTextStyle: { color: muted } },
      tooltip: { trigger: "axis", confine: true, backgroundColor: panel, borderColor: line, textStyle: { color: ink, fontSize: 12.5 },
                 axisPointer: { type: "line", lineStyle: { color: muted, width: 1 } } },
      dataZoom: [{ type: "inside", filterMode: "none" },
                 { type: "slider", height: 14, bottom: 8, filterMode: "none", borderColor: line, fillerColor: css("--accent-soft"),
                   handleStyle: { color: panel, borderColor: muted }, textStyle: { color: muted, fontSize: 10 }, dataBackground: { lineStyle: { color: line }, areaStyle: { color: line } } }],
      ...extra,
    };
  }
  const axisStyle = () => ({
    axisLine: { lineStyle: { color: css("--line") } }, axisTick: { show: false },
    axisLabel: { color: css("--muted"), fontSize: 10.5, fontFamily: "JetBrains Mono, Consolas, monospace" },
    splitLine: { lineStyle: { color: css("--line"), opacity: 0.7 } },
  });
  const targetLine = (t, unit) => t ? {
    silent: true, symbol: "none", lineStyle: { type: "dashed", color: css("--muted"), width: 1 },
    label: { formatter: t[1] || String(t[0]) + (unit || ""), color: css("--muted"), fontSize: 10.5, position: "insideEndTop" },
    data: [{ yAxis: t[0] }],
  } : undefined;

  // A card with the graph, its explanation and a table view; the chart is made when it scrolls into view.
  function card(container, spec, build) {
    const el = document.createElement("div");
    el.className = "card pchart";
    const better = spec.better === "higher" ? "↑ better" : spec.better === "lower" ? "↓ better" : "";
    el.innerHTML = `<div class="head"><h3>${esc(spec.title)}</h3><span class="better">${better}</span></div>
      <p class="why">${esc(spec.why || "")}</p><div class="ec" role="img" aria-label="${esc(spec.title)}"></div>
      <div class="row"><button class="linkbtn" type="button">Table</button></div><div class="tbl" hidden></div>`;
    container.appendChild(el);
    const box = el.querySelector(".ec");
    let chart = null, option = null;
    const make = () => {
      if (chart) return;
      option = build();
      if (!option) { box.outerHTML = '<p class="muted">No data yet.</p>'; return; }
      chart = echarts.init(box, null, { renderer: "canvas" });
      chart.setOption(option);
      live.add(chart);
    };
    new IntersectionObserver((entries, obs) => { if (entries.some((e) => e.isIntersecting)) { make(); obs.disconnect(); } }, { rootMargin: "300px" }).observe(el);
    el.querySelector(".linkbtn").addEventListener("click", () => {
      make();
      const t = el.querySelector(".tbl");
      t.hidden = !t.hidden;
      if (!t.hidden && option) t.innerHTML = table(option, spec.unit);
    });
    return el;
  }

  function table(option, unit) {
    const cats = option.xAxis.data || (option.yAxis && option.yAxis.data) || null;   // bars lying down keep their names on the y axis
    const series = option.series.filter((s) => s.type !== "scatter" || s.data.length);
    if (cats) {
      return `<table><thead><tr><th></th>${series.map((s) => `<th>${esc(s.name)}</th>`).join("")}</tr></thead><tbody>` +
        cats.map((c, i) => `<tr><td class="mono">${esc(c)}</td>${series.map((s) => { const v = s.data[i]; const y = Array.isArray(v) ? v[1] : (v && v.value !== undefined ? v.value : v); return `<td class="mono">${y == null ? "–" : esc(y) + esc(unit || "")}</td>`; }).join("")}</tr>`).join("") + "</tbody></table>";
    }
    const rows = [];
    for (const s of series) for (const p of s.data) rows.push([p.value ? p.value[0] : p[0], s.name, p.value ? p.value[1] : p[1], p.run || ""]);
    rows.sort((a, b) => String(b[0]).localeCompare(String(a[0])));
    return `<table><thead><tr><th>Match</th><th>Kind</th><th>Value</th></tr></thead><tbody>` +
      rows.slice(0, 120).map((r) => `<tr><td class="mono">${esc(r[0])}</td><td>${esc(r[1])}</td><td class="mono">${esc(r[2])}${esc(unit || "")}</td></tr>`).join("") + "</tbody></table>";
  }

  // ------------------------------------------------------------------ Progress tab
  let data = null, view = "build";

  function rowsFor(spec, fam) {
    return data.rows.filter((r) => fam ? r.family === fam : (r.kind !== "probe" && r.family !== "control"));
  }

  function buildOption(spec) {
    const buildName = Object.fromEntries(data.builds.map((b) => [b.n, b.name]));
    const series = [];
    if (spec.kind === "family") {
      const key = spec.measures[0].key;
      const used = [...new Set(data.rows.filter((r) => r[key] != null && data.families.some((f) => f.id === r.family)).map((r) => r.build))].sort((a, b) => a - b);
      if (!used.length) return null;
      const recent = used.slice(-3);
      const selected = {};
      data.families.forEach((f, i) => {
        const rs = rowsFor(spec, f.id).filter((r) => r[key] != null);
        if (!rs.length) return;
        const pts = used.map((b) => { const v = rs.filter((r) => r.build === b).map((r) => r[key]); return v.length ? { value: mean(v), n: v.length } : null; });
        series.push({ name: f.name, type: "line", data: pts, connectNulls: true, symbolSize: 6, lineStyle: { width: 2 }, itemStyle: { color: kindColor(i) }, color: kindColor(i) });
        selected[f.name] = rs.some((r) => recent.includes(r.build));
      });
      return finishBuild(spec, used, series, buildName, selected);
    }
    const rs = rowsFor(spec, null);
    const used = [...new Set(rs.filter((r) => spec.measures.some((m) => r[m.key] != null)).map((r) => r.build))].sort((a, b) => a - b);
    if (!used.length) return null;
    spec.measures.forEach((m, i) => {
      const pts = used.map((b) => { const v = rs.filter((r) => r.build === b && r[m.key] != null).map((r) => r[m.key]); return v.length ? { value: mean(v), n: v.length } : null; });
      series.push({ name: m.label, type: "line", data: pts, connectNulls: true, symbolSize: 6, lineStyle: { width: 2 }, itemStyle: { color: kindColor(i) }, color: kindColor(i) });
    });
    return finishBuild(spec, used, series, buildName, null);
  }

  function finishBuild(spec, used, series, buildName, selected) {
    if (series[0]) series[0].markLine = targetLine(spec.target, spec.unit);
    const unit = spec.unit || "";
    return base({
      legend: { ...base().legend, selected: selected || undefined, show: series.length > 1 },
      grid: { ...base().grid, top: series.length > 1 ? 44 : 20 },
      tooltip: { ...base().tooltip, formatter: (ps) => {
        const b = used[ps[0].dataIndex];
        return `<b>r${b}</b> <span style="opacity:.75">${esc(buildName[b] || "")}</span><br>` + ps.filter((p) => p.data).map((p) =>
          `${p.marker}${esc(p.seriesName)}: <b>${p.data.value}${esc(unit)}</b> <span style="opacity:.7">(${p.data.n} match${p.data.n > 1 ? "es" : ""})</span>`).join("<br>");
      } },
      xAxis: { type: "category", data: used.map((b) => "r" + b), ...axisStyle(), splitLine: { show: false } },
      yAxis: { type: "value", max: spec.ymax || undefined, ...axisStyle(), axisLabel: { ...axisStyle().axisLabel, formatter: (v) => v + unit.trim().replace(/^min$/, "") } },
      series,
    });
  }

  function matchOption(spec) {
    const series = [];
    const unit = spec.unit || "";
    if (spec.kind === "family") {
      const key = spec.measures[0].key;
      data.families.forEach((f, i) => {
        const pts = rowsFor(spec, f.id).filter((r) => r[key] != null).map((r) => ({ value: [r.started, r[key]], run: r.run, build: r.build }));
        if (pts.length) series.push({ name: f.name, type: "scatter", data: pts, symbolSize: 7, itemStyle: { color: kindColor(i), opacity: 0.85 }, color: kindColor(i) });
      });
    } else {
      const rs = rowsFor(spec, null);
      spec.measures.forEach((m, i) => {
        const pts = rs.filter((r) => r[m.key] != null).map((r) => ({ value: [r.started, r[m.key]], run: r.run, build: r.build }));
        if (pts.length) series.push({ name: m.label, type: "scatter", data: pts, symbolSize: 7, itemStyle: { color: kindColor(i), opacity: 0.85 }, color: kindColor(i) });
      });
    }
    if (!series.length) return null;
    series[0].markLine = targetLine(spec.target, unit);
    return base({
      tooltip: { ...base().tooltip, trigger: "item", formatter: (p) => `${p.marker}<b>${esc(p.seriesName)}</b>: ${p.value[1]}${esc(unit)}<br><span class="mono" style="opacity:.75">${esc(p.value[0])} · r${p.data.build}<br>${esc(p.data.run)}</span>` },
      xAxis: { type: "time", ...axisStyle(), splitLine: { show: false } },
      yAxis: { type: "value", max: spec.ymax || undefined, ...axisStyle() },
      series,
    });
  }

  function goalOption(g) {
    const pts = g.points;
    if (!pts.length) return null;
    const cats = pts.map((p) => p.at.slice(5).replace("-", "."));
    const m = /(>=|<=|==|>|<)\s*(-?[\d.]+)/.exec(g.target || "");
    const t = m ? [Number(m[2]), "target " + m[1].replace(">=", "≥").replace("<=", "≤").replace("==", "=") + " " + m[2]] : null;
    const series = [];
    if (g.per === "side") {
      for (const s of ["US", "USSR"]) {
        series.push({ name: s, type: "line", data: pts.map((p) => p.value && p.value[s] != null ? p.value[s] : null), connectNulls: false,
          symbolSize: 6, lineStyle: { width: 2 }, itemStyle: { color: css("--" + s.toLowerCase()) }, color: css("--" + s.toLowerCase()) });
      }
    } else {
      series.push({ name: nameOf(g.key), type: "line", data: pts.map((p) => p.value), symbolSize: 6, lineStyle: { width: 2 },
        itemStyle: { color: css("--accent") }, color: css("--accent") });
    }
    series[0].markLine = targetLine(t, "");
    // Builds as vertical markers at the first match each one played in.
    const marks = [];
    for (const b of (data && data.builds) || []) {
      const i = pts.findIndex((p) => p.at >= b.from);
      if (i > 0 && pts[i - 1].at < b.from) marks.push({ xAxis: i, name: "r" + b.n, label: { formatter: "r" + b.n }, tip: b.name });
    }
    if (marks.length) {
      series.push({ name: "builds", type: "line", data: [], silent: false, tooltip: { show: false },
        markLine: { symbol: "none", lineStyle: { type: "dotted", color: css("--accent"), width: 1, opacity: 0.7 },
          label: { color: css("--accent"), fontSize: 10, position: "insideStartTop" }, data: marks } });
    }
    return base({
      legend: { ...base().legend, data: series.filter((x) => x.name !== "builds").map((x) => x.name), show: g.per === "side" },
      grid: { ...base().grid, top: g.per === "side" ? 44 : 24 },
      tooltip: { ...base().tooltip, formatter: (ps) => `<b>${esc(pts[ps[0].dataIndex].at)}</b><br>` + ps.map((p) => `${p.marker}${esc(p.seriesName)}: <b>${p.value == null ? (g.key === "truck_first_min" ? "never" : "–") : p.value}</b>`).join("<br>") + `<br><span style="opacity:.7">${esc(pts[ps[0].dataIndex].run)}</span>` },
      xAxis: { type: "category", data: cats, ...axisStyle(), splitLine: { show: false } },
      yAxis: { type: "value", ...axisStyle() },
      series,
    });
  }

  function renderProgress() {
    if (!data) return;
    for (const c of live) c.dispose();
    live.clear();
    const gc = document.getElementById("goalcharts"), pc = document.getElementById("progresscharts");
    gc.innerHTML = ""; pc.innerHTML = "";
    for (const g of data.goal_history || []) {
      card(gc, { title: `${g.title}: ${nameOf(g.key)}`, why: `${whyOf(g.key, g.label)}. Target ${g.target}${g.per === "side" ? ", each side" : ""} - goal ${g.goal}, the last ${g.points.length} watched matches; dotted lines mark the builds.`, better: /[<]/.test(g.target) ? "lower" : /[>]/.test(g.target) ? "higher" : null }, () => goalOption(g));
    }
    for (const spec of data.charts) card(pc, spec, () => (view === "build" ? buildOption(spec) : matchOption(spec)));
  }

  async function loadProgress() {
    try {
      const r = await fetch("/api/progress");
      if (!r.ok) return;
      const d = await r.json();
      if (!d.rows) { document.getElementById("progresscharts").innerHTML = '<div class="empty">Measuring the matches - ready in a minute.</div>'; setTimeout(loadProgress, 20000); return; }
      data = d;
      renderProgress();
    } catch (_) {}
  }

  for (const b of document.querySelectorAll(".seg button[data-view]")) {
    b.addEventListener("click", () => {
      view = b.dataset.view;
      for (const x of document.querySelectorAll(".seg button[data-view]")) x.setAttribute("aria-pressed", String(x === b));
      renderProgress();
    });
  }

  // ------------------------------------------------------------------ the live match's graphs
  const liveCharts = {};
  // keys: the series to draw (the two sides, or one line such as the game's FPS, drawn in the accent colour).
  function liveChart(id, title, series, xmax, ymax, keys) {
    keys = keys || ["US", "USSR"];
    let entry = liveCharts[id];
    const host = document.getElementById("charts");
    if (!entry) {
      const el = document.createElement("div");
      el.className = "livechart";
      el.innerHTML = `<h3>${esc(title)}</h3><div class="ec" role="img" aria-label="${esc(title)}"></div>`;
      host.appendChild(el);
      entry = liveCharts[id] = { chart: echarts.init(el.querySelector(".ec"), null, { renderer: "canvas" }) };
      live.add(entry.chart);
    }
    const opt = base({
      grid: { left: 36, right: 12, top: 12, bottom: 26 },
      legend: { show: false }, dataZoom: [],
      tooltip: { ...base().tooltip, formatter: (ps) => `game minute ${ps[0].value[0]}<br>` + ps.map((p) => `${p.marker}${esc(p.seriesName)}: <b>${p.value[1]}</b>`).join("<br>") },
      xAxis: { type: "value", min: 0, max: xmax, ...axisStyle(), splitLine: { show: false } },
      yAxis: { type: "value", min: 0, max: ymax || undefined, ...axisStyle() },
      series: keys.map((s) => { const c = s === "US" || s === "USSR" ? css("--" + s.toLowerCase()) : css("--accent");
        return { name: s, type: "line", showSymbol: false, data: (series || {})[s] || [], lineStyle: { width: 2 }, itemStyle: { color: c }, color: c, endLabel: { show: false } }; }),
    });
    entry.chart.setOption(opt, { notMerge: true });
  }
  function renderLive(ser, xmax) {
    liveChart("front", "Front bases' supplies, %", ser.front_supply, xmax, 100);
    liveChart("field", "Soldiers in the field", ser.in_field, xmax);
    liveChart("air", "Drones in the air", ser.drones_up, xmax);
    liveChart("lost", "Soldiers lost", ser.lost, xmax);
    liveChart("fps", "Game FPS (average per game minute)", ser.fps, xmax, undefined, ["FPS"]);
  }

  window.addEventListener("resize", () => { for (const c of live) c.resize(); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { for (const k of Object.keys(liveCharts)) { liveCharts[k].chart.dispose(); delete liveCharts[k]; } document.getElementById("charts").innerHTML = ""; renderProgress(); });

  // ------------------------------------------------------------------ Sub-labs tab
  // One track at a time (Martin, 23 Oct: "it's hard to understand these graphs, what is X?"): a track picker, then one
  // graph per question - crashes between cars, cars lost, jams, trips made - with the setups as named rows and the axis
  // saying what it counts. Averages over the headless runs on that track only (tracks differ too much to average over:
  // mines, gates). A setup keeps its colour (its place in the sub-lab's setup list).
  const picked = {};
  function renderSublab(container, lab) {
    for (const c of [...live]) if (c.isDisposed()) live.delete(c);
    container.innerHTML = "";
    const vs = lab.variants || [], all = (lab.all || []).filter((r) => !r.watched);
    // Colour marks only what to compare: grey the game alone, orange our mod as it is now, blue the alternatives.
    const color = (v) => v === lab.baseline ? css("--muted") : v === lab.candidate ? kindColor(1) : kindColor(0);
    const tag = (v) => (lab.vlabel || {})[v] || v;
    const S = (sc) => (lab.slabel || {})[sc] || sc;
    const order = (lab.table || []).map((r) => r.scenario);
    const tracks = order.filter((sc) => all.some((r) => r.scenario === sc));
    if (!tracks.length) { container.innerHTML = '<p class="muted">No runs yet - the graphs appear with the first run.</p>'; return; }
    const key = "sublab-track-" + (lab.name || "");
    let chosen = picked[key];
    try { chosen = chosen || localStorage.getItem(key); } catch (e) { /* no storage: first track */ }
    if (!tracks.includes(chosen)) chosen = tracks[0];
    const bar = document.createElement("div");
    bar.className = "row";
    bar.style.cssText = "gap:8px;align-items:center;flex-wrap:wrap";
    const id = "sl-track-" + (lab.name || "lab");
    bar.innerHTML = `<label for="${id}"><b>Track</b></label><select id="${id}">${tracks.map((sc) => `<option value="${esc(sc)}"${sc === chosen ? " selected" : ""}>${esc(S(sc))}</option>`).join("")}</select>`;
    const words = document.createElement("p");
    words.className = "muted";
    const box = document.createElement("div");
    box.style.cssText = "display:grid;gap:12px";
    container.append(bar, words, box);
    const draw = (sc) => {
      for (const el of box.querySelectorAll(".ec")) { const c = echarts.getInstanceByDom(el); if (c) { live.delete(c); c.dispose(); } }
      box.innerHTML = "";
      const about = ((lab.swords || {})[sc] || "").trim();
      words.textContent = (about ? about.replace(/\.?$/, ". ") : "") + "Grey: the game's driver alone. Orange: our mod as it is now. Blue: the alternatives tried.";
      const runs = all.filter((r) => r.scenario === sc);
      const setups = vs.filter((v) => runs.some((r) => r.variant === v));
      const avg = (v, k) => { const xs = runs.filter((r) => r.variant === v && typeof r[k] === "number").map((r) => r[k]); return xs.length ? mean(xs) : null; };
      const count = (v) => runs.filter((r) => r.variant === v).length;
      // A sub-lab's own questions ([[questions]] in its .toml: key, title, better, axis), else the driving ones.
      const own = (lab.questions || []).map((q) => ({ k: q.key, title: q.title, better: q.better || "lower", axis: q.axis || q.key }));
      const QUESTIONS = own.length ? own : [
        { k: "car_hits", title: "Crashes between cars", better: "lower", axis: "hits per 10-minute run (each car in a crash counts once)" },
        { k: "lost", title: "Cars lost", better: "lower", axis: "cars lost per 10-minute run (destroyed, crew got out, driver dead)" },
        { k: "jams", title: "Jams", better: "lower", axis: "jams per 10-minute run (a car standing 45 s with another car within 10 m)" },
        { k: "legs", title: sc === "traffic" ? "Deliveries made" : "Trips made", better: "higher", axis: sc === "traffic" ? "deliveries per 10-minute run" : "trips from one end to the other per 10-minute run" },
      ];
      for (const q of QUESTIONS) {
        const rows = setups.map((v) => ({ label: `${tag(v)} (${count(v)} run${count(v) === 1 ? "" : "s"})`, value: avg(v, q.k), color: color(v) })).filter((r) => r.value != null);
        if (!rows.length) continue;
        const el = card(box, { title: q.title, better: q.better, why: `Average of the runs on this track. ${q.better === "lower" ? "Shorter bar is better." : "Longer bar is better."}` }, () => base({
          dataZoom: [], legend: { show: false },
          grid: { left: 8, right: 40, top: 6, bottom: 40, containLabel: true },
          xAxis: { type: "value", name: q.axis, nameLocation: "middle", nameGap: 26, nameTextStyle: { color: css("--muted"), fontSize: 11.5 }, ...axisStyle() },
          yAxis: { type: "category", inverse: true, data: rows.map((r) => r.label), ...axisStyle(), splitLine: { show: false },
                   axisLabel: { color: css("--ink"), fontSize: 12.5, fontFamily: "Source Sans 3, Segoe UI, system-ui, sans-serif" } },
          tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
          series: [{ name: q.title, type: "bar", barMaxWidth: 18, itemStyle: { borderRadius: [0, 3, 3, 0] },
                     label: { show: true, position: "right", color: css("--ink"), fontSize: 11.5, fontFamily: "JetBrains Mono, Consolas, monospace" },
                     data: rows.map((r) => ({ value: r.value, itemStyle: { color: r.color } })) }],
        }));
        el.querySelector(".ec").style.height = `${Math.max(150, rows.length * 34 + 64)}px`;
      }
    };
    bar.querySelector("select").addEventListener("change", (e) => {
      picked[key] = e.target.value;
      try { localStorage.setItem(key, e.target.value); } catch (err) { /* remembered for this visit only */ }
      draw(e.target.value);
    });
    draw(chosen);
  }

  // ------------------------------------------------------------------ Integration tests: progress curves
  // (2 Nov, note 506 - Martin: "i really want to see some charts of progress in graphs so I can see like how is
  // optimization doing", "basically we are training AI so same methods should be applied for reviewing"). Like a training
  // run's curves: every run a dot (coloured by track: US blue, Soviet red), the moving average of the last 5 runs as the
  // line, the target dashed, the first run on each build marked (r61, r62...); and the average per build, like an eval
  // per checkpoint.
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const shortAt = (at) => { const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d)/.exec(String(at || "")); return m ? `${+m[3]} ${MONTHS[+m[2] - 1]} ${m[4]}` : String(at || ""); };
  const fmt1 = (v) => v == null ? "–" : (Math.round(v * 10) / 10).toString();
  function sweep(container) {
    for (const c of [...live]) if (c.isDisposed() || !document.body.contains(c.getDom())) { if (!c.isDisposed()) c.dispose(); live.delete(c); }
    for (const el of container.querySelectorAll(".ec")) { const c = echarts.getInstanceByDom(el); if (c) { live.delete(c); c.dispose(); } }
  }
  function qOf(lab, key) {
    return (lab.questions || []).find((x) => x.key === key) || { key, title: key.replace(/_/g, " "), short: key.replace(/_/g, " "),
      better: /lost|crash|stuck|fail|jam|hit|error|walk|wait|_s$/.test(key) ? "lower" : "higher" };
  }
  const trackName = (lab, sc) => (lab.slabel || {})[sc] || sc;
  const trackColor = (lab, sc, i) => /ussr|soviet/i.test(sc + " " + trackName(lab, sc)) ? css("--ussr")
    : (/(^|\W)US$/.test(trackName(lab, sc)) || sc === "arland") ? css("--us") : kindColor((i + 2) % 8);
  const runsWith = (lab, key) => (lab.all || []).filter((r) => !r.watched && typeof r[key] === "number")
    .sort((a, b) => String(a.at).localeCompare(String(b.at)));

  // One measure over every run: the training curve.
  function sublabCurve(container, lab, key, opts = {}) {
    const q = qOf(lab, key);
    const runs = runsWith(lab, key);
    const spec = { title: opts.title || q.title, better: q.better, why: opts.why != null ? opts.why : (q.axis || "") };
    const el = card(container, spec, () => {
      if (!runs.length) return null;
      const tracks = [...new Set(runs.map((r) => r.scenario))];
      const V = (v) => (lab.vlabel || {})[v] || v;
      const N = 5;
      const avg = runs.map((_, i) => { const w = runs.slice(Math.max(0, i - N + 1), i + 1); return Math.round(10 * w.reduce((a, r) => a + r[key], 0) / w.length) / 10; });
      const bname = Object.fromEntries((lab.builds || []).map((b) => [b.n, b.name]));
      const marks = [];
      if (!opts.small) runs.forEach((r, i) => { if (r.build != null && (i === 0 || runs[i - 1].build !== r.build)) marks.push({ xAxis: i, name: bname[r.build] || "", label: { formatter: "r" + r.build } }); });
      if (typeof q.target === "number") marks.push({ yAxis: q.target, name: "target", lineStyle: { type: "dashed", color: css("--good"), width: 1.5 },
        label: { formatter: "target " + q.target, position: "insideEndTop", color: css("--good"), fontSize: 10.5, fontFamily: "JetBrains Mono, Consolas, monospace" } });
      const series = tracks.map((sc, ti) => ({ name: trackName(lab, sc), type: "scatter", symbolSize: opts.small ? 6 : 8, z: 3,
        itemStyle: { color: trackColor(lab, sc, ti), opacity: 0.75 }, data: runs.map((r) => r.scenario === sc ? r[key] : null) }));
      series.push({ name: `average of the last ${N} runs`, type: "line", data: avg, showSymbol: false, smooth: 0.3, z: 4,
        lineStyle: { width: opts.small ? 2 : 3, color: css("--ink") }, itemStyle: { color: css("--ink") },
        markLine: { symbol: "none", silent: false, lineStyle: { type: "dotted", color: css("--muted"), width: 1 },
          label: { position: "end", color: css("--muted"), fontSize: 10, fontFamily: "JetBrains Mono, Consolas, monospace" },
          tooltip: { formatter: (p) => `${esc(p.name)}` }, data: marks } });
      const tip = (ps) => {
        const r = runs[ps[0].dataIndex];
        return [`<b>${esc(shortAt(r.at))}</b> · ${esc(trackName(lab, r.scenario))}`,
          `${esc(V(r.variant))}${r.build != null ? " · build r" + r.build : ""}${r.minutes ? " · " + fmt1(r.minutes) + " min" : ""}`,
          `<b>${esc(q.title)}: ${fmt1(r[key])}</b>`, `average of the last ${N}: ${fmt1(avg[ps[0].dataIndex])}`].join("<br>");
      };
      return base({
        dataZoom: opts.small ? [] : base().dataZoom,
        legend: { ...base().legend, show: !opts.small, data: series.map((x) => x.name) },
        grid: opts.small ? { left: 38, right: 12, top: 14, bottom: 26 } : { left: 42, right: 18, top: 44, bottom: 60 },
        tooltip: { ...base().tooltip, trigger: "axis", formatter: tip },
        xAxis: { type: "category", data: runs.map((r) => shortAt(r.at)), boundaryGap: true, ...axisStyle(), splitLine: { show: false },
                 axisLabel: { ...axisStyle().axisLabel, show: !opts.small } },
        yAxis: { type: "value", min: 0, name: opts.small ? "" : (q.short || ""), nameTextStyle: { color: css("--muted"), fontSize: 11, align: "left" }, ...axisStyle() },
        series,
      });
    });
    el.querySelector(".ec").style.height = (opts.height || 340) + "px";
    if (opts.small) el.classList.add("small");
    return el;
  }

  // One measure per build: the average of the runs on each build (an eval per checkpoint).
  function sublabBuilds(container, lab, key) {
    const q = qOf(lab, key);
    const runs = runsWith(lab, key).filter((r) => r.build != null);
    const el = card(container, { title: `${q.title}, average per build`, better: q.better,
      why: "Each point: the average of every run on that build (all setups tried then). Hover a point for what changed in that build." }, () => {
      if (!runs.length) return null;
      const blds = [...new Set(runs.map((r) => r.build))].sort((a, b) => a - b);
      const info = Object.fromEntries((lab.builds || []).map((b) => [b.n, b]));
      const tracks = [...new Set(runs.map((r) => r.scenario))];
      const mean = (rs) => rs.length ? Math.round(10 * rs.reduce((a, r) => a + r[key], 0) / rs.length) / 10 : null;
      const all = blds.map((b) => mean(runs.filter((r) => r.build === b)));
      const series = [{ name: "all runs", type: "line", data: all, symbol: "circle", symbolSize: 9, z: 4,
        lineStyle: { width: 3, color: css("--ink") }, itemStyle: { color: css("--ink") },
        label: { show: true, position: "top", color: css("--ink"), fontSize: 11, fontFamily: "JetBrains Mono, Consolas, monospace" },
        markLine: typeof q.target === "number" ? { symbol: "none", silent: true, lineStyle: { type: "dashed", color: css("--good"), width: 1.5 },
          label: { formatter: "target " + q.target, position: "insideEndTop", color: css("--good"), fontSize: 10.5 }, data: [{ yAxis: q.target }] } : undefined }];
      if (tracks.length > 1) tracks.forEach((sc, ti) => series.push({ name: trackName(lab, sc), type: "line", connectNulls: true, symbolSize: 6,
        lineStyle: { width: 1.5, type: "dashed", color: trackColor(lab, sc, ti) }, itemStyle: { color: trackColor(lab, sc, ti) },
        data: blds.map((b) => mean(runs.filter((r) => r.build === b && r.scenario === sc))) }));
      return base({
        dataZoom: [],
        legend: { ...base().legend, data: series.map((x) => x.name) },
        grid: { left: 42, right: 18, top: 44, bottom: 30 },
        tooltip: { ...base().tooltip, trigger: "axis", formatter: (ps) => {
          const b = blds[ps[0].dataIndex], i = info[b] || {};
          const n = runs.filter((r) => r.build === b).length;
          return [`<b>build r${b}</b> · ${esc(shortAt(i.live || ""))} · ${n} runs`, `<i>${esc(i.name || "")}</i>`]
            .concat(ps.map((p) => `${esc(p.seriesName)}: <b>${fmt1(p.value)}</b>`)).join("<br>");
        } },
        xAxis: { type: "category", data: blds.map((b) => "r" + b), ...axisStyle(), splitLine: { show: false } },
        yAxis: { type: "value", min: 0, name: q.short || "", nameTextStyle: { color: css("--muted"), fontSize: 11, align: "left" }, ...axisStyle() },
        series,
      });
    });
    el.querySelector(".ec").style.height = "300px";
    return el;
  }

  // A tiny curve for the tests' start page (inline SVG): the moving average of the main measure, the target dashed.
  function sparkline(lab, key, w = 260, h = 56) {
    const q = qOf(lab, key), runs = runsWith(lab, key);
    if (runs.length < 2) return "";
    const N = 5, avg = runs.map((_, i) => { const s = runs.slice(Math.max(0, i - N + 1), i + 1); return s.reduce((a, r) => a + r[key], 0) / s.length; });
    const vals = avg.concat(typeof q.target === "number" ? [q.target] : []);
    const hi = Math.max(...vals) * 1.08 || 1, lo = 0;
    const X = (i) => 2 + (w - 4) * i / (avg.length - 1), Y = (v) => h - 3 - (h - 6) * (v - lo) / (hi - lo);
    const pts = avg.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    const tgt = typeof q.target === "number" ? `<line x1="0" x2="${w}" y1="${Y(q.target).toFixed(1)}" y2="${Y(q.target).toFixed(1)}" stroke="var(--good)" stroke-width="1.2" stroke-dasharray="4 3"/>` : "";
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${esc(q.title)} over the runs">${tgt}<polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linejoin="round"/><circle cx="${X(avg.length - 1).toFixed(1)}" cy="${Y(avg[avg.length - 1]).toFixed(1)}" r="3.2" fill="var(--accent)"/></svg>`;
  }

  return { loadProgress, renderLive, renderSublab, sublabCurve, sublabBuilds, sparkline, shortAt, sweep, resize: () => { for (const c of live) c.resize(); } };
})();
