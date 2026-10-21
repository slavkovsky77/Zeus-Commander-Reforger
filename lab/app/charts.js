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
    const cats = option.xAxis.data || null;
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

  return { loadProgress, renderLive, resize: () => { for (const c of live) c.resize(); } };
})();
