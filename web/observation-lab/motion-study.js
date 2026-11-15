/* Motion study panel for the SPHEREx View.
 *
 * Shows the precomputed study for a target (web/assets/motion-study/<field>/study.json, written by
 * backend/observation_lab_core/motion_study.py):
 *   - a 2010–2026 time-lapse at 4.6 µm (WISE/NEOWISE W2 + SPHEREx visit stacks on one grid),
 *   - same-wavelength SPHEREx visit stacks per band,
 *   - flipbook, blink (A/B) and difference views, with measured and expected positions drawn on the image,
 *   - measured-versus-expected offsets with error bars, residuals, the three motion fits, the field-star null
 *     test, the brightness test and a verdict with the rule that produced it.
 * View state is kept in the URL (?ms=…) so any view can be shared.
 */
(() => {
  "use strict";
  const BASE = "/assets/motion-study/";
  const TARGETS = [
    ["barnard", "Barnard’s Star"], ["epsilon-indi", "Epsilon Indi B"], ["wise-0855", "WISE 0855"],
    ["proxima-centauri", "Proxima Centauri"], ["rw-aur", "RW Aurigae"], ["r-dra", "R Draconis"],
    ["vesta", "Vesta (asteroid)"],
  ];
  const MISSION_COLOR = {"WISE": "#c792ea", "NEOWISE-R": "#56c8d8", "SPHEREx": "#f5a35c"};
  const VERDICT_TONE = {"as-predicted": "good", "static": "good", "brightness": "info", "too-small": "neutral",
    "differs": "warn", "not-detected": "warn", "not-measurable": "warn", "saturated": "neutral"};
  const SVGNS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, ...kids) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v; else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else if (v != null) node.setAttribute(k, v);
    }
    node.append(...kids.filter(Boolean));
    return node;
  };
  const svg = (tag, attrs = {}, text) => {
    const node = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text != null) node.textContent = text;
    return node;
  };
  const fmt = (v, d = 0) => Number(v).toLocaleString("en-US", {maximumFractionDigits: d, minimumFractionDigits: d});
  const year = mjd => 2000 + (mjd - 51544.5) / 365.25;

  const ui = {};
  const view = {field: null, data: null, tab: "timelapse", band: "4.6", index: 0, mode: "flip", a: 0, b: null,
    playing: false, timer: 0, images: new Map(), residuals: true};

  function readUrl() {
    const p = new URLSearchParams(location.search).get("ms");
    if (!p) return;
    const [field, tab, band, index, mode] = p.split(".");
    if (TARGETS.some(t => t[0] === field)) { view.field = field; view.fromUrl = true; }
    if (["visits", "timelapse", "sky"].includes(tab)) view.tab = tab;
    if (band) view.band = band.replace("_", ".");
    if (index) view.index = Number(index) || 0;
    if (["flip", "blink", "diff"].includes(mode)) view.mode = mode;
  }
  function writeUrl() {
    if (!view.field) return;
    const url = new URL(location.href);
    url.searchParams.set("ms", [view.field, view.tab, view.band.replace(".", "_"), view.index, view.mode].join("."));
    history.replaceState(history.state, "", url);
  }

  function build() {
    const anchor = document.getElementById("light-panel");
    if (!anchor || document.getElementById("motion-study")) return false;
    ui.root = el("section", {id: "motion-study", class: "motion-study", "aria-labelledby": "ms-title"});
    ui.select = el("select", {id: "ms-target", "aria-label": "Study target"},
      ...TARGETS.map(([k, n]) => el("option", {value: k, text: n})));
    ui.select.addEventListener("change", () => load(ui.select.value));
    ui.verdictBadge = el("span", {class: "ms-badge", id: "ms-badge"});
    const head = el("div", {class: "ms-head"},
      el("div", {},
        el("h2", {id: "ms-title", class: "section-title", text: "Motion study"}),
        el("p", {class: "coord-sub", id: "ms-sub", text: "Measured positions against the catalog track, 2010–2026."})),
      el("div", {class: "ms-head-actions"}, ui.verdictBadge, ui.select));

    ui.tabs = el("div", {class: "ms-tabs", role: "tablist"},
      el("button", {type: "button", role: "tab", "data-tab": "timelapse", text: "2010–2026 time-lapse · 4.6 µm"}),
      el("button", {type: "button", role: "tab", "data-tab": "visits", text: "SPHEREx visits · same wavelength"}));
    ui.tabs.addEventListener("click", e => { const t = e.target.closest("[data-tab]"); if (t) { view.tab = t.dataset.tab; view.index = 0; view.b = null; render(); } });
    ui.bands = el("div", {class: "ms-bands", role: "group", "aria-label": "Wavelength"});
    ui.modes = el("div", {class: "ms-modes", role: "group", "aria-label": "View mode"},
      ...[["flip", "Flipbook"], ["blink", "Blink A/B"], ["diff", "Difference"]].map(([k, n]) =>
        el("button", {type: "button", "data-mode": k, text: n})));
    ui.modes.addEventListener("click", e => { const b = e.target.closest("[data-mode]"); if (b) { setMode(b.dataset.mode); } });

    ui.canvas = el("canvas", {width: 600, height: 600, class: "ms-canvas", role: "img", "aria-label": "Motion study image"});
    ui.overlay = el("div", {class: "ms-overlay-legend"},
      el("span", {class: "ms-key ms-key-exp", text: "Expected (catalog)"}),
      el("span", {class: "ms-key ms-key-meas", text: "Measured"}),
      el("span", {class: "ms-key ms-key-trail", text: "Path"}));
    ui.frameLabel = el("div", {class: "ms-frame-label", "aria-live": "polite"});
    ui.slider = el("input", {type: "range", min: 0, max: 0, value: 0, class: "ms-slider", "aria-label": "Frame"});
    ui.slider.addEventListener("input", () => { stop(); view.index = Number(ui.slider.value); paint(); writeUrl(); });
    ui.play = el("button", {type: "button", class: "btn-outline ms-play", text: "Play"});
    ui.play.addEventListener("click", () => view.playing ? stop() : play());
    ui.setA = el("button", {type: "button", class: "btn-outline", text: "Set A"});
    ui.setB = el("button", {type: "button", class: "btn-outline", text: "Set B"});
    ui.setA.addEventListener("click", () => { view.a = view.index; paint(); });
    ui.setB.addEventListener("click", () => { view.b = view.index; paint(); });
    ui.speed = el("select", {"aria-label": "Speed"}, ...[[700, "Slow"], [380, "Normal"], [160, "Fast"]].map(([v, n]) => el("option", {value: v, text: n})));
    ui.speed.value = "380";
    const controls = el("div", {class: "ms-controls"}, ui.play, ui.slider, ui.speed, ui.setA, ui.setB);
    const stage = el("div", {class: "ms-stage"}, ui.canvas, ui.frameLabel, ui.overlay);

    ui.verdict = el("article", {class: "ms-verdict", "aria-live": "polite"});
    ui.charts = el("div", {class: "ms-charts"});
    ui.residualToggle = el("label", {class: "toggle-chip"}, el("input", {type: "checkbox", checked: ""}), el("span", {text: "Show residuals (measured − expected)"}));
    ui.residualToggle.querySelector("input").addEventListener("change", e => { view.residuals = e.target.checked; drawCharts(); });
    ui.fits = el("div", {class: "ms-fits"});
    ui.checks = el("div", {class: "ms-checks"});
    ui.limits = el("details", {class: "ms-limits"}, el("summary", {text: "Method, limits and credits"}));
    ui.status = el("p", {class: "ms-status", role: "status"});

    ui.root.append(head, ui.status,
      el("div", {class: "ms-grid"},
        el("div", {class: "ms-left"}, ui.tabs, el("div", {class: "ms-toolbar"}, ui.bands, ui.modes), stage, controls),
        el("div", {class: "ms-right"}, ui.verdict, ui.checks)),
      el("div", {class: "ms-chart-head"}, ui.chartTitle = el("h3", {text: "Where it was versus where the catalog says it should be"}), ui.residualToggle),
      ui.charts, ui.fits, ui.limits);
    anchor.before(ui.root);
    document.addEventListener("keydown", e => {
      if (!ui.root.matches(":hover, :focus-within") || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || "")) return;
      if (e.key === "ArrowRight") { step(1); e.preventDefault(); }
      else if (e.key === "ArrowLeft") { step(-1); e.preventDefault(); }
      else if (e.key === " ") { view.playing ? stop() : play(); e.preventDefault(); }
    });
    return true;
  }

  async function load(field) {
    if (!field) return;
    stop();
    view.field = field;
    ui.select.value = field;
    ui.status.textContent = "Loading motion study…";
    try {
      const response = await fetch(BASE + field + "/study.json", {cache: "no-cache"});
      if (!response.ok) throw new Error(response.status === 404 ? "No precomputed study for this target yet." : `HTTP ${response.status}`);
      view.data = await response.json();
      if (view.field !== field) return;
      if (!view.data.timelapse.length) view.tab = "visits";
      ui.status.textContent = "";
      render();
    } catch (error) {
      view.data = null;
      ui.status.textContent = `Motion study unavailable: ${error.message}`;
    }
  }

  function frames() {
    const d = view.data;
    if (!d) return [];
    if (d.mode === "track") {
      if (view.tab === "sky") return d.sky.map(f => ({...f, label: `${f.date} · fixed sky · ${fmt(f.scale_arcsec * f.size / 60, 0)}′ field`}));
      return d.timelapse.map(f => ({...f, label: `${f.date} · SPHEREx D${f.detector} · centred on Vesta`}));
    }
    if (view.tab === "timelapse") return d.timelapse.map(t => ({...t, label: `${t.date} · ${t.mission} · ${t.frames} exposure${t.frames === 1 ? "" : "s"} stacked`}));
    return d.visits.filter(v => v.stacks[view.band]).map(v => {
      const s = v.stacks[view.band];
      const tl = d.timelapse.find(t => t.mission === "SPHEREx" && Math.abs(t.mjd - v.mjd) < 25);
      return {png: s.png, mjd: v.mjd, date: v.first === v.last ? v.first : `${v.first} → ${v.last}`, mission: "SPHEREx",
        expected: tl?.expected, measured: tl?.measured,
        label: `SPHEREx visit ${v.index + 1} · ${v.first === v.last ? v.first : v.first + " → " + v.last} · ${s.frames} exposure${s.frames === 1 ? "" : "s"} at ${fmt(s.wavelength_um, 2)} µm`};
    });
  }

  function image(name) {
    const url = BASE + view.field + "/img/" + name;
    if (!view.images.has(url)) {
      const img = new Image();
      img.decoding = "async";
      img.src = url;
      img.onload = () => paint();
      view.images.set(url, img);
    }
    return view.images.get(url);
  }

  function render() {
    const d = view.data;
    if (!d) return;
    const track = d.mode === "track";
    ui.root.dataset.tone = VERDICT_TONE[d.verdict.code] || "neutral";
    ui.verdictBadge.textContent = d.verdict.title;
    ui.verdictBadge.dataset.tone = VERDICT_TONE[d.verdict.code] || "neutral";
    document.getElementById("ms-sub").textContent = track ? `${d.name} · ${d.kind}. ${d.counts.spherex_frames} SPHEREx exposures in ${d.counts.spherex_visits} visit${d.counts.spherex_visits === 1 ? "" : "s"}.` :
      `${d.name} · ${d.kind}. ${d.counts.spherex_frames} SPHEREx exposures in ${d.counts.spherex_visits} visits` +
      (d.counts.wise_frames ? ` + ${d.counts.wise_frames} WISE/NEOWISE exposures in ${d.counts.wise_visits} visits.` : ".");
    if (track && view.tab === "visits") view.tab = "timelapse";
    if (!track && view.tab === "sky") view.tab = "timelapse";
    const [t1, t2] = ui.tabs.querySelectorAll("[data-tab]");
    t1.textContent = track ? "Follow Vesta · centred on it" : "2010–2026 time-lapse · 4.6 µm";
    t2.textContent = track ? "Fixed sky · watch it cross" : "SPHEREx visits · same wavelength";
    t2.dataset.tab = track ? "sky" : "visits";
    for (const b of ui.tabs.querySelectorAll("[data-tab]")) {
      const on = b.dataset.tab === view.tab;
      b.setAttribute("aria-selected", String(on));
      b.disabled = b.dataset.tab === "timelapse" && !d.timelapse.length;
    }
    ui.bands.replaceChildren(...(view.tab === "visits" ? d.bands.map(b => {
      const button = el("button", {type: "button", "data-band": b.key, "aria-pressed": String(b.key === view.band), text: b.label});
      button.addEventListener("click", () => { view.band = b.key; view.index = 0; view.b = null; render(); });
      return button;
    }) : [el("span", {class: "ms-note", text: track ? (view.tab === "sky" ? "Each exposure drawn on one fixed patch of sky: the data window moves with Vesta, so it keeps going after leaving the original field." : "Every exposure re-centred on Vesta, so the background stars stream past and Vesta stays put.") : d.counts.wise_frames ? "WISE/NEOWISE W2 and SPHEREx at the same 4.6 µm wavelength, one image per visit." : "No WISE/NEOWISE epochs bundled for this target yet."})]));
    if (view.tab === "visits" && !d.bands.some(b => b.key === view.band) && d.bands.length) { view.band = d.bands[0].key; return render(); }
    const list = frames();
    view.index = Math.min(view.index, Math.max(0, list.length - 1));
    if (view.b == null || view.b >= list.length) view.b = Math.max(0, list.length - 1);
    if (view.a >= list.length) view.a = 0;
    ui.slider.max = String(Math.max(0, list.length - 1));
    ui.slider.value = String(view.index);
    for (const f of list) image(f.png);
    setMode(view.mode, false);
    drawVerdict();
    drawCharts();
    drawFits();
    drawChecks();
    drawLimits();
    paint();
    writeUrl();
  }

  function setMode(mode, repaint = true) {
    if (mode === "diff" && view.tab === "visits" && !view.data?.differences?.[view.band] && frames().length < 2) mode = "flip";
    view.mode = mode;
    for (const b of ui.modes.querySelectorAll("[data-mode]")) b.setAttribute("aria-pressed", String(b.dataset.mode === mode));
    ui.setA.hidden = ui.setB.hidden = mode === "flip";
    if (mode !== "flip") stop();
    if (mode === "blink") play();
    if (repaint) { paint(); writeUrl(); }
  }

  function play() {
    stop();
    view.playing = true;
    ui.play.textContent = "Pause";
    const tick = () => {
      if (!view.playing) return;
      if (view.mode === "blink") view.blinkOn = !view.blinkOn; else step(1, true);
      paint();
      view.timer = setTimeout(tick, view.mode === "blink" ? 650 : Number(ui.speed.value));
    };
    view.timer = setTimeout(tick, 200);
  }
  function stop() {
    view.playing = false;
    clearTimeout(view.timer);
    if (ui.play) ui.play.textContent = "Play";
  }
  function step(delta, wrap = false) {
    const n = frames().length;
    if (!n) return;
    view.index = wrap ? (view.index + delta + n) % n : Math.max(0, Math.min(n - 1, view.index + delta));
    ui.slider.value = String(view.index);
    if (!view.playing) { paint(); writeUrl(); }
  }

  // ---- image drawing -------------------------------------------------------------------------------------
  function paint() {
    const d = view.data, list = frames();
    if (!d || !list.length) return;
    const ctx = ui.canvas.getContext("2d"), W = ui.canvas.width;
    const size = list[view.index]?.size || d.grid.size, k = W / size, scaleArcsec = list[view.index]?.scale_arcsec || d.grid.scale_arcsec;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, W);
    let shown = list[view.index], label = shown.label;
    if (view.mode === "blink") {
      shown = list[view.blinkOn ? view.b : view.a];
      label = `${view.blinkOn ? "B" : "A"} · ${shown.label}`;
    }
    if (view.mode === "diff") {
      const a = list[view.a], b = list[view.b];
      const preset = view.tab === "visits" && view.a === 0 && view.b === list.length - 1 && d.differences?.[view.band];
      if (preset) {
        const img = image(d.differences[view.band]);
        if (img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0, W, W);
      } else drawDifference(ctx, image(a.png), image(b.png), W);
      label = `Difference B − A · orange = brighter / arrived in B, blue = fainter / left · A ${a.date} · B ${b.date}`;
      shown = b;
      drawMarks(ctx, k, size, list, view.b, a);
    } else {
      const img = image(shown.png);
      if (img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0, W, W);
      drawMarks(ctx, k, size, list, list.indexOf(shown));
    }
    drawCompass(ctx, W, scaleArcsec, k);
    ui.frameLabel.textContent = label;
    ui.canvas.setAttribute("aria-label", `Motion study image: ${label}`);
  }

  function drawDifference(ctx, a, b, W) {
    if (!(a.complete && a.naturalWidth && b.complete && b.naturalWidth)) return;
    const w = a.naturalWidth, h = a.naturalHeight, off = document.createElement("canvas");
    off.width = w; off.height = h;
    const c = off.getContext("2d");
    c.drawImage(a, 0, 0); const da = c.getImageData(0, 0, w, h);
    c.drawImage(b, 0, 0); const db = c.getImageData(0, 0, w, h);
    const out = c.createImageData(w, h);
    for (let i = 0; i < da.data.length; i += 4) {
      const v = (db.data[i] - da.data[i]) / 255, p = Math.max(0, v), n = Math.max(0, -v);
      out.data[i] = 14 + 241 * p + 30 * n; out.data[i + 1] = 16 + 140 * p + 120 * n; out.data[i + 2] = 22 + 40 * p + 233 * n; out.data[i + 3] = 255;
    }
    c.putImageData(out, 0, 0);
    ctx.drawImage(off, 0, 0, W, W);
  }

  function drawMarks(ctx, k, size, list, current, ghost) {
    const now = list[current];
    if (now?.trail) {           // fixed-sky Vesta view: its path through this visit
      ctx.strokeStyle = "rgba(108,184,255,.55)"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 4]);
      ctx.beginPath(); now.trail.forEach(([x, y], i) => i ? ctx.lineTo((x + .5) * k, (y + .5) * k) : ctx.moveTo((x + .5) * k, (y + .5) * k)); ctx.stroke();
      ctx.setLineDash([]);
    }
    const pts = list.map(f => f.expected).filter(Boolean);
    if (pts.length > 1) {          // catalog path across all frames
      ctx.strokeStyle = "rgba(185,163,245,.45)"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 4]);
      ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo((p.x + .5) * k, (p.y + .5) * k) : ctx.moveTo((p.x + .5) * k, (p.y + .5) * k)); ctx.stroke();
      ctx.setLineDash([]);
    }
    list.slice(0, current + 1).forEach((f, i) => {   // measured history
      if (!f.measured) return;
      ctx.fillStyle = i === current ? "rgba(108,184,255,1)" : "rgba(108,184,255,.35)";
      ctx.beginPath(); ctx.arc((f.measured.x + .5) * k, (f.measured.y + .5) * k, i === current ? 3 : 2, 0, 2 * Math.PI); ctx.fill();
    });
    const f = list[current];
    if (!f) return;
    if (ghost?.measured) {
      ctx.strokeStyle = "rgba(108,184,255,.6)"; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.arc((ghost.measured.x + .5) * k, (ghost.measured.y + .5) * k, 12, 0, 2 * Math.PI); ctx.stroke(); ctx.setLineDash([]);
    }
    if (f.expected) {
      const x = (f.expected.x + .5) * k, y = (f.expected.y + .5) * k;
      ctx.strokeStyle = "#b9a3f5"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x - 16, y); ctx.lineTo(x - 7, y); ctx.moveTo(x + 7, y); ctx.lineTo(x + 16, y);
      ctx.moveTo(x, y - 16); ctx.lineTo(x, y - 7); ctx.moveTo(x, y + 7); ctx.lineTo(x, y + 16); ctx.stroke();
    }
    if (f.measured) {
      const x = (f.measured.x + .5) * k, y = (f.measured.y + .5) * k;
      ctx.strokeStyle = "#6cb8ff"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y, Math.max(9, f.measured.err_px * k * 3), 0, 2 * Math.PI); ctx.stroke();
    }
  }

  function drawCompass(ctx, W, scale, k) {
    const arcmin = 60 / scale * k;   // pixels per arcminute
    ctx.fillStyle = "rgba(0,0,0,.55)"; ctx.fillRect(10, W - 34, arcmin + 20, 24);
    ctx.strokeStyle = "#f5f5f7"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(20, W - 18); ctx.lineTo(20 + arcmin, W - 18); ctx.stroke();
    ctx.fillStyle = "#f5f5f7"; ctx.font = "11px system-ui, sans-serif"; ctx.fillText("1′", 22 + arcmin / 2 - 4, W - 22);
    ctx.textAlign = "center";
    ctx.fillText("N", W - 26, 20); ctx.fillText("E", W - 52, 44); ctx.textAlign = "start";
    ctx.beginPath(); ctx.moveTo(W - 26, 40); ctx.lineTo(W - 26, 24); ctx.moveTo(W - 26, 40); ctx.lineTo(W - 44, 40); ctx.stroke();
  }

  // ---- charts --------------------------------------------------------------------------------------------
  function drawCharts() {
    const d = view.data;
    if (!d) return;
    ui.residualToggle.hidden = d.mode === "track";
    ui.chartTitle.textContent = d.mode === "track" ? "Where Vesta was, exposure by exposure" : "Where it was versus where the catalog says it should be";
    if (d.mode === "track") { ui.charts.replaceChildren(skyPath()); return; }
    ui.charts.replaceChildren(chart("east", "East offset"), chart("north", "North offset"));
  }

  function skyPath() {
    const path = view.data.path, W = 560, H = 300, L = 64, R = 16, T = 26, B = 40;
    const s = svg("svg", {viewBox: `0 0 ${W} ${H}`, class: "ms-chart", role: "img", "aria-label": "Vesta's measured path on the sky"});
    const ras = path.map(p => p.ra), decs = path.map(p => p.dec);
    const cd = Math.cos(decs.reduce((a, b) => a + b, 0) / decs.length * Math.PI / 180);
    let x0 = Math.min(...ras), x1 = Math.max(...ras), y0 = Math.min(...decs), y1 = Math.max(...decs);
    const span = Math.max((x1 - x0) * cd, y1 - y0, .05) * 1.2, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const sx = r => L + (W - L - R) / 2 - (r - cx) * cd / span * (W - L - R), sy = dd => T + (H - T - B) / 2 - (dd - cy) / span * (H - T - B);
    s.append(svg("text", {x: L, y: 16, fill: "#f5f5f7", "font-size": 12, "font-weight": 600}, "Measured path on the sky (east left, north up)"));
    s.append(svg("rect", {x: L, y: T, width: W - L - R, height: H - T - B, fill: "none", stroke: "#2c2c2e"}));
    s.append(svg("text", {x: L, y: H - 22, fill: "#a1a1a6", "font-size": 10}, `RA ${fmt(x1, 2)}°`));
    s.append(svg("text", {x: W - R, y: H - 22, "text-anchor": "end", fill: "#a1a1a6", "font-size": 10}, `RA ${fmt(x0, 2)}°`));
    s.append(svg("text", {x: L - 6, y: T + 10, "text-anchor": "end", fill: "#a1a1a6", "font-size": 10}, `${fmt(y1, 2)}°`));
    s.append(svg("text", {x: L - 6, y: H - B, "text-anchor": "end", fill: "#a1a1a6", "font-size": 10}, `${fmt(y0, 2)}°`));
    s.append(svg("polyline", {points: path.map(p => `${sx(p.ra).toFixed(1)},${sy(p.dec).toFixed(1)}`).join(" "), fill: "none", stroke: "#56c8d8", "stroke-width": 1.5}));
    for (const p of path) {
      if (p.predicted) s.append(svg("circle", {cx: sx(p.predicted[0]), cy: sy(p.predicted[1]), r: 6, fill: "none", stroke: "#b9a3f5", "stroke-width": 1.4}));
      const dot = svg("circle", {cx: sx(p.ra), cy: sy(p.dec), r: 3.6, fill: "#f5a35c", stroke: "#000", "stroke-width": .8});
      dot.append(svg("title", {}, `${p.date}\nRA ${fmt(p.ra, 5)}°, Dec ${fmt(p.dec, 5)}°${p.residual ? `\nJPL difference ${fmt(Math.hypot(...p.residual), 1)}″` : ""}`));
      s.append(dot);
    }
    s.append(svg("text", {x: W - R, y: H - 8, "text-anchor": "end", fill: "#a1a1a6", "font-size": 10}, "orange = measured · violet ring = JPL Horizons"));
    return s;
  }

  function chart(axis, title) {
    const d = view.data, pts = d.astrometry.points, track = d.astrometry.track;
    const W = 560, H = 230, L = 62, R = 14, T = 26, B = 36;
    const s = svg("svg", {viewBox: `0 0 ${W} ${H}`, class: "ms-chart", role: "img"});
    if (!pts.length) { s.append(svg("text", {x: W / 2, y: H / 2, "text-anchor": "middle", fill: "#a1a1a6"}, "No measured positions")); return s; }
    const idx = axis === "east" ? 1 : 2;
    const value = p => view.residuals ? p[axis] - p[`exp_${axis}`] : p[axis];
    const tmin = Math.min(...pts.map(p => p.mjd), ...track.map(t => t[0])), tmax = Math.max(...pts.map(p => p.mjd), ...track.map(t => t[0]));
    let ys = pts.flatMap(p => [value(p) - p.err, value(p) + p.err]);
    if (!view.residuals) ys = ys.concat(track.map(t => t[idx]));
    else ys.push(0);
    let ymin = Math.min(...ys), ymax = Math.max(...ys);
    const pad = (ymax - ymin || 1) * .1; ymin -= pad; ymax += pad;
    const x = t => L + (t - tmin) / (tmax - tmin || 1) * (W - L - R), y = v => T + (ymax - v) / (ymax - ymin) * (H - T - B);
    s.setAttribute("aria-label", `${title} versus time${view.residuals ? " (measured minus expected)" : ""}`);
    s.append(svg("text", {x: L, y: 16, fill: "#f5f5f7", "font-size": 12, "font-weight": 600}, `${title}${view.residuals ? " · measured − expected" : ""} (arcsec)`));
    for (let i = 0; i <= 4; i++) {
      const v = ymin + (ymax - ymin) * i / 4;
      s.append(svg("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#2c2c2e"}));
      s.append(svg("text", {x: L - 6, y: y(v) + 4, "text-anchor": "end", fill: "#a1a1a6", "font-size": 10}, fmt(v, Math.abs(ymax - ymin) < 10 ? 1 : 0)));
    }
    const y0 = Math.ceil(year(tmin)), y1 = Math.floor(year(tmax)), stepY = (y1 - y0) > 8 ? 2 : 1;
    for (let yr = y0; yr <= y1; yr += stepY) {
      const t = 51544.5 + (yr - 2000) * 365.25;
      s.append(svg("text", {x: x(t), y: H - 14, "text-anchor": "middle", fill: "#a1a1a6", "font-size": 10}, String(yr)));
    }
    if (view.residuals) s.append(svg("line", {x1: L, x2: W - R, y1: y(0), y2: y(0), stroke: "#b9a3f5", "stroke-dasharray": "4 4"}));
    else s.append(svg("polyline", {points: track.map(t => `${x(t[0]).toFixed(1)},${y(t[idx]).toFixed(1)}`).join(" "), fill: "none", stroke: "#b9a3f5", "stroke-width": 1.5}));
    for (const p of pts) {
      const c = MISSION_COLOR[p.mission] || "#f5f5f7", px = x(p.mjd), v = value(p);
      s.append(svg("line", {x1: px, x2: px, y1: y(v - p.err), y2: y(v + p.err), stroke: c, "stroke-width": 1.4}));
      const dot = svg("circle", {cx: px, cy: y(v), r: 3.6, fill: c, stroke: "#000", "stroke-width": .8});
      dot.append(svg("title", {}, `${p.date} · ${p.mission} · ${p.frames} exposure${p.frames === 1 ? "" : "s"}\n${title}: ${fmt(p[axis], 2)}″ (expected ${fmt(p[`exp_${axis}`], 2)}″) ± ${fmt(p.err, 2)}″${p.saturated ? `\n${p.saturated} from a saturated core` : ""}`));
      s.append(dot);
    }
    const legend = Object.entries(MISSION_COLOR).filter(([m]) => pts.some(p => p.mission === m));
    legend.forEach(([m, c], i) => {
      s.append(svg("circle", {cx: W - R - 150 + i * 56, cy: 12, r: 4, fill: c}));
      s.append(svg("text", {x: W - R - 143 + i * 56, y: 16, fill: "#a1a1a6", "font-size": 10}, m.replace("-R", "")));
    });
    return s;
  }

  function drawVerdict() {
    const v = view.data.verdict, n = v.numbers || {};
    const rows = view.data.mode === "track" ? [
      ["Exposures", String(n.exposures ?? "—")],
      ["Apparent speed", n.speed_arcsec_per_hr != null ? `${fmt(n.speed_arcsec_per_hr, 1)}″ per hour (${fmt(n.speed_arcsec_per_hr * 24 / 60, 1)}′ per day)` : "—"],
      ["Difference from JPL", n.rms_arcsec != null ? `${fmt(n.rms_arcsec, 1)}″${n.exposures > 1 ? " rms" : ""}` : "—"],
    ] : [
      ["Measured motion", n.measured_mas_yr != null ? `${fmt(n.measured_mas_yr)} ± ${fmt(n.error_mas_yr)} mas/yr` : "—"],
      ["Catalog motion", n.catalog_mas_yr != null ? `${fmt(n.catalog_mas_yr)} mas/yr` : "—"],
      ["Baseline", n.baseline_yr != null ? `${fmt(n.baseline_yr, 1)} years` : "—"],
      ["Predicted shift", n.predicted_shift_arcsec != null ? `${fmt(n.predicted_shift_arcsec, 1)}″` : "—"],
      ["Typical position error", n.typical_position_error_arcsec != null ? `${fmt(n.typical_position_error_arcsec, 2)}″` : "—"],
    ];
    if (n.median_amplitude_mag != null) rows.push(["Brightness change", `${fmt(n.median_amplitude_mag, 2)} mag (threshold ${fmt(n.threshold_mag, 2)})`]);
    ui.verdict.dataset.tone = VERDICT_TONE[v.code] || "neutral";
    ui.verdict.replaceChildren(
      el("p", {class: "ms-eyebrow", text: "Verdict"}),
      el("h3", {text: v.title}),
      el("p", {class: "ms-summary", text: v.summary}),
      el("dl", {}, ...rows.flatMap(([k, val]) => [el("dt", {text: k}), el("dd", {text: val})])),
      el("p", {class: "ms-rule", text: `Rule: ${v.rule}`}));
  }

  function drawFits() {
    if (view.data.mode === "track") { ui.fits.replaceChildren(); return; }
    const f = view.data.astrometry.fits, c = view.data.catalog;
    const row = (name, fit) => el("tr", {},
      el("th", {scope: "row", text: name}),
      el("td", {text: fit ? `${fmt(fit.pmra_mas_yr)} ± ${fmt(fit.pmra_err)}` : "—"}),
      el("td", {text: fit ? `${fmt(fit.pmdec_mas_yr)} ± ${fmt(fit.pmdec_err)}` : "—"}),
      el("td", {text: fit ? `${fmt(fit.baseline_yr, 1)} yr · ${fit.n} pts` : "—"}),
      el("td", {text: fit ? fmt(fit.chi2_red, 2) : "—"}));
    ui.fits.replaceChildren(el("table", {class: "ms-table"},
      el("caption", {text: "Proper-motion fits (mas/yr; parallax removed using the catalog value)"}),
      el("thead", {}, el("tr", {}, ...["", "East (μα*)", "North (μδ)", "Baseline", "Reduced χ²"].map(t => el("th", {scope: "col", text: t})))),
      el("tbody", {},
        row("SPHEREx only", f.spherex), row("WISE/NEOWISE only", f.wise), row("Combined 2010–2026", f.combined),
        el("tr", {class: "ms-catalog-row"}, el("th", {scope: "row", text: "Catalog"}), el("td", {text: fmt(c.pmra_mas_yr, 1)}),
          el("td", {text: fmt(c.pmdec_mas_yr, 1)}), el("td", {colspan: 2, text: c.assumed ? "assumed negligible" : (c.source || "")})))));
  }

  function drawChecks() {
    const d = view.data, fs = d.field_stars, b = d.brightness;
    if (d.mode === "track") {
      const withJpl = d.path.filter(p => p.residual).length;
      ui.checks.replaceChildren(el("h3", {text: "Checks"}), el("ul", {},
        el("li", {}, el("strong", {text: `${d.path.length} exposure${d.path.length === 1 ? "" : "s"}`}), ` in ${d.counts.spherex_visits} visit${d.counts.spherex_visits === 1 ? "" : "s"}; Vesta measured in each one.`),
        el("li", {}, el("strong", {text: `${withJpl} with a JPL position`}), withJpl ? " · the violet ring on the path chart." : " · run scripts/fetch_vesta_track.py to add JPL-tracked exposures.")));
      return;
    }
    const items = [];
    for (const [name, t] of [["SPHEREx", fs.spherex], ["WISE/NEOWISE", fs.wise]]) {
      if (!t || !t.tested) continue;
      items.push(el("li", {}, el("strong", {text: `${t.static} of ${t.tested}`}),
        ` ${name} field stars show no significant motion (null test; median spurious ${fmt(t.median_spurious_mas_yr)} mas/yr).`));
    }
    if (b.tested) {
      items.push(el("li", {}, el("strong", {text: b.variable ? "Brightness changes" : "Brightness steady"}),
        ` · ${fmt(b.median_amplitude_mag, 2)} mag median change between 10-day bins at matching wavelengths (threshold ${fmt(b.threshold_mag, 2)} mag, ${fmt(b.significance, 1)}σ; ${b.method}).`));
    } else items.push(el("li", {}, el("strong", {text: "Brightness not tested"}), ` · ${b.reason}`));
    ui.checks.replaceChildren(el("h3", {text: "Checks"}), el("ul", {}, ...items));
  }

  function drawLimits() {
    const d = view.data;
    const body = el("div", {},
      el("h4", {text: "How it was measured"}),
      el("p", {text: "Every exposure is aligned on its own field stars. The target is fitted near its catalog-predicted place in each exposure, in that exposure’s own pixels (or located from its saturated core). Positions are averaged per visit and fitted with a straight line plus the catalog parallax. The same procedure run on the field stars must show no motion."}),
      el("h4", {text: "Limits"}), el("ul", {}, ...d.limits.map(t => el("li", {text: t}))),
      el("h4", {text: "Credits"}), el("ul", {}, ...d.credits.map(t => el("li", {text: t}))),
      el("p", {class: "ms-rule", text: `Computed ${d.generated_utc.replace("T", " ").replace("Z", " UTC")} by backend/observation_lab_core/motion_study.py.`}));
    ui.limits.replaceChildren(el("summary", {text: "Method, limits and credits"}), body);
  }

  function follow(fieldKey) {
    if (view.fromUrl) { view.fromUrl = false; return; }   // a shared link wins over the first field the page opens
    if (TARGETS.some(t => t[0] === fieldKey) && fieldKey !== view.field) load(fieldKey);
  }

  function start() {
    if (!build()) return;
    readUrl();
    const initial = view.field || (typeof state !== "undefined" && TARGETS.some(t => t[0] === state.field) ? state.field : "barnard");
    load(initial);
    window.addEventListener("sky-session-ready", () => { if (typeof state !== "undefined") follow(state.field); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
