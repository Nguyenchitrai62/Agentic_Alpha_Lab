/* Alpha Lab frontend: static SPA (Vercel) talking to the FastAPI backend through the Cloudflare tunnel. */
(() => {
  "use strict";
  const CFG = window.APP_CONFIG || {};
  const API = (CFG.apiBaseUrl || "").replace(/\/$/, "");
  const SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
  const IV_MS = { "1h": 3600e3, "4h": 4 * 3600e3, "1d": 86400e3 };
  const TZ = -new Date().getTimezoneOffset() * 60; // charts show local time
  const $ = (id) => document.getElementById(id);
  const state = { token: localStorage.getItem("aal_token") || "", user: null, view: "signal",
                  sig: { symbol: "BTCUSDT", interval: "4h", data: null },
                  hist: { symbol: "BTCUSDT", interval: "4h" }, charts: {} };

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const coin = (s) => s.replace("USDT", "");
  const fmtPx = (p) => p == null ? "—" : Number(p).toLocaleString("en-US", { maximumFractionDigits: p >= 1000 ? 1 : p >= 10 ? 2 : p >= 1 ? 4 : 5 });
  const pct = (x, d = 1) => x == null || !isFinite(x) ? "—" : (x * 100).toFixed(d) + "%";
  const signed = (x, d = 2) => x == null ? "—" : `<span class="${x >= 0 ? "pos" : "neg"}">${x >= 0 ? "+" : ""}${Number(x).toFixed(d)}%</span>`;
  const dt = (ms) => ms == null ? "—" : new Date(ms).toLocaleString("vi-VN", { hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  const toChart = (ms) => Math.floor(ms / 1000) + TZ;
  const fromChart = (t) => (t - TZ) * 1000;
  const isoDay = (ms) => new Date(ms).toISOString().slice(0, 10);
  const CONF = { CAO: "Cao", "TRUNG BINH": "Trung bình", THAP: "Thấp" };
  const KIND = { book_fill: "Khớp entry", book_stop: "Stop-loss", book_tp: "Take-profit", rung_fill: "Khớp mua dip",
                 rung_tp: "TP dip", rung_sl: "SL dip", rung_timeout: "Đóng dip (hết 4h)" };
  const sideCls = (s) => s === "LONG" ? "long" : s === "SHORT" ? "short" : "flat";
  const sideVi = (s) => s === "LONG" ? "LONG ▲" : s === "SHORT" ? "SHORT ▼" : "Đứng ngoài";

  function toast(msg, ms = 3500) {
    const el = $("toast"); el.textContent = msg; el.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (el.hidden = true), ms);
  }

  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (state.token) headers.Authorization = "Bearer " + state.token;
    if (opts.body) headers["Content-Type"] = "application/json";
    let r;
    try { r = await fetch(API + path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined }); }
    catch (e) { throw new Error("Không kết nối được máy chủ API."); }
    if (r.status === 401 && state.token) { logout(); throw new Error("Phiên đăng nhập hết hạn."); }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Lỗi ${r.status}`);
    return data;
  }

  function table(el, head, rows) {
    el.innerHTML = `<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") ||
      `<tr><td colspan="${head.length}" class="muted">Chưa có dữ liệu</td></tr>`}</tbody>`;
  }

  function seg(el, items, active, onPick, label = (x) => x) {
    el.innerHTML = items.map((x) => `<button data-v="${x}" class="${x === active ? "active" : ""}">${label(x)}</button>`).join("");
    el.onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      el.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      onPick(b.dataset.v);
    };
  }

  // ------------------------------------------------------------------ charts
  function makeChart(key, el, extra = {}) {
    if (state.charts[key]) state.charts[key].remove();
    const LC = window.LightweightCharts;
    const c = LC.createChart(el, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: "#8a9bb8", fontSize: 11 },
      grid: { vertLines: { color: "rgba(34,49,79,.5)" }, horzLines: { color: "rgba(34,49,79,.5)" } },
      rightPriceScale: { borderColor: "#22314f" },
      timeScale: { borderColor: "#22314f", timeVisible: true, secondsVisible: false },
      crosshair: { mode: LC.CrosshairMode.Normal },
      ...extra,
    });
    state.charts[key] = c;
    return c;
  }
  const candleSeries = (c) => c.addCandlestickSeries({ upColor: "#22c55e", downColor: "#ef4444", borderVisible: false,
    wickUpColor: "#22c55e", wickDownColor: "#ef4444", priceFormat: { type: "custom", formatter: fmtPx, minMove: 0.00001 } });
  const toCandles = (rows) => rows.map((r) => ({ time: toChart(r.t), open: r.o, high: r.h, low: r.l, close: r.c }));

  // ------------------------------------------------------------------ auth
  async function initGsi() {
    let clientId = CFG.googleClientId;
    if (!clientId) {
      try { clientId = (await api("/api/public/config")).google_client_id; }
      catch (e) { $("loginMsg").textContent = e.message; return; }
    }
    if (!clientId) { $("loginMsg").textContent = "Máy chủ chưa cấu hình GOOGLE_CLIENT_ID."; return; }
    const wait = () => new Promise((res) => { const t = setInterval(() => { if (window.google?.accounts?.id) { clearInterval(t); res(); } }, 100); });
    await wait();
    google.accounts.id.initialize({ client_id: clientId, callback: onCredential, auto_select: false, ux_mode: "popup" });
    google.accounts.id.renderButton($("gsiButton"), { theme: "filled_black", size: "large", shape: "pill", text: "signin_with", locale: "vi" });
  }

  async function onCredential(resp) {
    $("loginMsg").textContent = "Đang đăng nhập…";
    try {
      const out = await api("/api/auth/google", { method: "POST", body: { credential: resp.credential } });
      state.token = out.token; localStorage.setItem("aal_token", out.token);
      state.user = out.user; $("loginMsg").textContent = "";
      enter();
    } catch (e) { $("loginMsg").textContent = e.message; }
  }

  function logout() {
    state.token = ""; state.user = null; localStorage.removeItem("aal_token");
    try { google.accounts.id.disableAutoSelect(); } catch (e) { /* not loaded */ }
    showOnly("login"); $("tabs").hidden = true; $("userBox").innerHTML = "";
    if (!$("gsiButton").childElementCount) initGsi();
  }

  function showOnly(view) {
    document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "view-" + view));
  }

  function enter() {
    const u = state.user;
    $("userBox").innerHTML = `${u.picture ? `<img src="${esc(u.picture)}" alt="" referrerpolicy="no-referrer">` : ""}
      <div><div class="name">${esc(u.name || u.email)}</div><div class="role">${u.role === "admin" ? "Admin" : u.role === "viewer" ? "Người xem" : "Chờ duyệt"}</div></div>
      ${u.local ? '<span class="tag">local</span>' : '<button class="btn sm" id="logoutBtn">Đăng xuất</button>'}`;
    if (!u.local) $("logoutBtn").onclick = logout;
    if (u.role === "pending") { $("pendingEmail").textContent = u.email; showOnly("pending"); $("tabs").hidden = true; return; }
    $("tabs").hidden = false; $("adminTab").hidden = u.role !== "admin";
    route();
  }

  // ------------------------------------------------------------------ routing
  function route() {
    let v = (location.hash || "#signal").slice(1);
    if (!["signal", "history", "perf", "admin"].includes(v) || (v === "admin" && state.user.role !== "admin")) v = "signal";
    state.view = v;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    showOnly(v);
    ({ signal: loadSignal, history: initHistory, perf: loadPerf, admin: loadAdmin })[v]();
  }
  $("tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) location.hash = b.dataset.view; };
  window.addEventListener("hashchange", () => state.user && state.user.role !== "pending" && route());
  $("pendingLogout").onclick = logout;

  // ------------------------------------------------------------------ current signal
  async function loadSignal() {
    try {
      const [latest, ov] = await Promise.all([api("/api/signals/latest?source=live"), api("/api/overview")]);
      state.sig.data = latest;
      renderSignal(latest, ov);
      drawSignalChart();
    } catch (e) { toast(e.message); }
  }

  function renderSignal(d, ov) {
    const run = d.run;
    const fw = ov.forward || {}, wf = ov.walkforward || {};
    const books = (d.books || []).slice().sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight));
    const longs = books.filter((b) => b.weight > 0).reduce((s, b) => s + b.weight, 0);
    const shorts = books.filter((b) => b.weight < 0).reduce((s, b) => s + b.weight, 0);
    $("sigKpis").innerHTML = run ? [
      ["Nến quyết định", dt(run.decision_time), "lệnh hiệu lực đến " + dt(run.decision_time + IV_MS["4h"])],
      ["Tổng vốn dùng", pct(run.gross, 0), `long ${pct(longs, 0)} · short ${pct(-shorts, 0)}`],
      ["Hệ số rủi ro", (run.scale ?? 0).toFixed(2) + "×", "governor " + (run.governor ?? 0).toFixed(2)],
      ["Walk-forward 5 năm", wf.monthly_5y != null ? wf.monthly_5y.toFixed(2) + "%/tháng" : "—", "DD " + (wf.gate_dd ?? "—") + "%"],
      ["Paper trading", fw.net_return_pct != null ? signed(fw.net_return_pct) : "—", fw.days != null ? `${fw.days} ngày từ ${String(fw.freeze || "").slice(0, 10)}` : ""],
      ["Cập nhật", dt(run.created_at), ov.last_job ? `job ${ov.last_job.kind}: ${ov.last_job.status}` : ""],
    ].map(([k, v, s]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("")
      : `<div class="kpi"><div class="k">Chưa có tín hiệu</div><div class="v">—</div><div class="s">Admin cần chạy pipeline</div></div>`;
    $("sigValid").textContent = run ? `(nến ${dt(run.decision_time)})` : "";
    table($("booksTbl"), ["Coin", "Hướng", "Vốn dùng", "Entry limit", "Stop-loss", "Take-profit", "SL %", "TP %", "Tin cậy"],
      books.map((b) => {
        const slp = b.entry && b.sl ? Math.abs(b.sl / b.entry - 1) : null, tpp = b.entry && b.tp ? Math.abs(b.tp / b.entry - 1) : null;
        return `<tr class="click ${b.symbol === state.sig.symbol ? "sel" : ""}" data-sym="${b.symbol}"><td><b>${coin(b.symbol)}</b></td>
          <td class="${sideCls(b.side)}">${sideVi(b.side)}</td><td>${pct(Math.abs(b.weight))}</td><td>${fmtPx(b.entry)}</td>
          <td class="neg">${fmtPx(b.sl)}</td><td class="pos">${fmtPx(b.tp)}</td><td>${pct(slp)}</td><td>${pct(tpp)}</td>
          <td>${esc(CONF[b.confidence] || b.confidence || "—")}${b.members_agree ? "" : " <span class='muted small'>(lệch)</span>"}</td></tr>`;
      }));
    $("booksTbl").onclick = (e) => { const tr = e.target.closest("tr[data-sym]"); if (tr) pickSigSymbol(tr.dataset.sym); };
    table($("sleeveTbl"), ["Coin", "Bậc", "Mua limit", "TP", "SL", "Vốn"],
      (d.sleeve || []).map((r) => `<tr class="click" data-sym="${r.symbol}"><td>${coin(r.symbol)}</td><td>${r.rung}σ</td><td>${fmtPx(r.buy_limit)}</td>
        <td class="pos">${fmtPx(r.tp)}</td><td class="neg">${fmtPx(r.sl)}</td><td>${pct(r.size_frac)}</td></tr>`));
    $("sleeveTbl").onclick = (e) => { const tr = e.target.closest("tr[data-sym]"); if (tr) pickSigSymbol(tr.dataset.sym); };
  }

  function pickSigSymbol(sym) {
    state.sig.symbol = sym;
    seg($("sigSymbols"), SYMS, sym, pickSigSymbol, coin);
    document.querySelectorAll("#booksTbl tr[data-sym]").forEach((tr) => tr.classList.toggle("sel", tr.dataset.sym === sym));
    drawSignalChart();
  }

  async function drawSignalChart() {
    const { symbol, interval, data } = state.sig;
    seg($("sigSymbols"), SYMS, symbol, pickSigSymbol, coin);
    seg($("sigIntervals"), ["1h", "4h", "1d"], interval, (v) => { state.sig.interval = v; drawSignalChart(); });
    try {
      const rows = await api(`/api/candles?symbol=${symbol}&interval=${interval}&limit=${interval === "1d" ? 400 : 500}`);
      const c = makeChart("sig", $("sigChart"));
      const b = (data?.books || []).find((x) => x.symbol === symbol);
      const levels = [b?.entry, b?.sl, b?.tp].filter((x) => x && b.side !== "FLAT");
      const s = candleSeries(c);
      if (levels.length) {  // keep entry / SL / TP inside the visible price range
        s.applyOptions({ autoscaleInfoProvider: (orig) => {
          const r = orig(); if (!r) return r;
          return { ...r, priceRange: { minValue: Math.min(r.priceRange.minValue, ...levels), maxValue: Math.max(r.priceRange.maxValue, ...levels) } };
        } });
      }
      s.setData(toCandles(rows));
      const LS = LightweightCharts.LineStyle;
      if (b && b.side !== "FLAT" && b.entry) {
        s.createPriceLine({ price: b.entry, color: "#3b82f6", lineWidth: 2, lineStyle: LS.Solid, title: `Entry ${b.side}` });
        s.createPriceLine({ price: b.sl, color: "#ef4444", lineWidth: 2, lineStyle: LS.Solid, title: "SL" });
        s.createPriceLine({ price: b.tp, color: "#22c55e", lineWidth: 2, lineStyle: LS.Solid, title: "TP" });
      }
      (data?.sleeve || []).filter((r) => r.symbol === symbol).forEach((r) =>
        s.createPriceLine({ price: r.buy_limit, color: "#f59e0b", lineWidth: 1, lineStyle: LS.Dashed, title: `Dip ${r.rung}σ` }));
      if (data?.run) {
        const tb = Math.floor(data.run.decision_time / IV_MS[interval]) * IV_MS[interval];
        s.setMarkers([{ time: toChart(tb), position: "aboveBar", color: "#3b82f6", shape: "arrowDown", text: "Quyết định" }]
          .filter(() => rows.some((r) => r.t === tb)));
      }
      c.timeScale().setVisibleLogicalRange({ from: Math.max(0, rows.length - 150), to: rows.length + 8 });
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------------ history
  let histInit = false;
  function initHistory() {
    if (!histInit) {
      histInit = true;
      seg($("hSymbols"), SYMS, state.hist.symbol, (v) => { state.hist.symbol = v; loadHistory(); }, coin);
      seg($("hIntervals"), ["1h", "4h", "1d"], state.hist.interval, (v) => { state.hist.interval = v; loadHistory(); });
      $("hSource").onchange = () => { setHistRange(); loadHistory(); };
      $("hLoad").onclick = loadHistory;
      ["hBook", "hDip", "hLevels", "hMinW"].forEach((id) => ($(id).onchange = loadHistory));
      setHistRange();
    }
    loadHistory();
  }

  function setHistRange() {
    const wf = $("hSource").value === "walkforward";
    const end = wf ? Date.UTC(2026, 8, 23) : Date.now();
    $("hTo").value = isoDay(end);
    $("hFrom").value = isoDay(end - (wf ? 120 : 30) * 86400e3);
  }

  async function loadHistory() {
    const { symbol, interval } = state.hist;
    const source = $("hSource").value;
    const start = $("hFrom").value, end = $("hTo").value + "T23:59:59Z";
    const q = `symbol=${symbol}&start=${start}&end=${end}`;
    try {
      const [cand, pos, trd] = await Promise.all([
        api(`/api/candles?${q}&interval=${interval}&limit=5000`),
        api(`/api/positions?${q}&source=${source}&limit=5000`),
        source === "walkforward" ? api(`/api/trades?${q}&source=${source}&limit=5000`) : Promise.resolve([]),
      ]);
      if (!cand.length) { toast("Không có nến trong khoảng này."); return; }
      if (cand.length >= 5000) toast("Khoảng quá dài cho khung này; chỉ hiện 5000 nến cuối.");
      const c = makeChart("hist", $("hChart"));
      const s = candleSeries(c);
      s.setData(toCandles(cand));
      const step = IV_MS[interval];
      // position in force at each candle open (two-pointer over decision times)
      const inForce = []; let j = -1;
      for (const k of cand) { while (j + 1 < pos.length && pos[j + 1].t <= k.t) j++; inForce.push(j >= 0 && k.t - pos[j].t < 3 * step + IV_MS["4h"] ? pos[j] : null); }
      if ($("hLevels").checked) {
        const LT = LightweightCharts.LineType;
        const mk = (color) => c.addLineSeries({ color, lineWidth: 1, lineType: LT.WithSteps, priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false, priceFormat: { type: "custom", formatter: fmtPx, minMove: 0.00001 } });
        const sl = mk("rgba(239,68,68,.85)"), tp = mk("rgba(34,197,94,.85)");
        sl.setData(cand.map((k, i) => inForce[i]?.sl ? { time: toChart(k.t), value: inForce[i].sl } : { time: toChart(k.t) }));
        tp.setData(cand.map((k, i) => inForce[i]?.tp ? { time: toChart(k.t), value: inForce[i].tp } : { time: toChart(k.t) }));
      }
      const w = c.addHistogramSeries({ priceScaleId: "w", priceFormat: { type: "percent" }, priceLineVisible: false, lastValueVisible: false });
      c.priceScale("w").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      w.setData(cand.map((k, i) => ({ time: toChart(k.t), value: inForce[i] ? inForce[i].weight * 100 : 0,
        color: inForce[i] && inForce[i].weight < 0 ? "rgba(239,68,68,.45)" : "rgba(59,130,246,.45)" })));
      // trade markers, one per (candle, kind, side)
      const showBook = $("hBook").checked, showDip = $("hDip").checked, minW = +$("hMinW").value, seen = new Set(), markers = [];
      for (const e of trd) {
        const isDip = e.kind.startsWith("rung");
        if ((isDip && !showDip) || (!isDip && !showBook)) continue;
        if (e.kind === "book_fill" && Math.abs(e.weight || 0) < minW) continue;  // hide small rebalances
        const tb = Math.floor(e.t / step) * step, key = tb + e.kind + e.side;
        if (seen.has(key) || tb < cand[0].t) continue; seen.add(key);
        let m;
        const sz = ` ${Math.round(Math.abs(e.weight || 0) * 100)}%`;
        if (e.kind === "book_fill") m = e.side === "buy" ? { position: "belowBar", color: "#22c55e", shape: "arrowUp", text: "Mua" + sz } : { position: "aboveBar", color: "#ef4444", shape: "arrowDown", text: "Bán" + sz };
        else if (e.kind === "book_stop") m = { position: "aboveBar", color: "#ef4444", shape: "circle", text: "SL" };
        else if (e.kind === "book_tp") m = { position: "aboveBar", color: "#22c55e", shape: "circle", text: "TP" };
        else if (e.kind === "rung_fill") m = { position: "belowBar", color: "#f59e0b", shape: "arrowUp", text: "Dip" };
        else if (e.kind === "rung_tp") m = { position: "aboveBar", color: "#f59e0b", shape: "circle", text: "TP" };
        else if (e.kind === "rung_sl") m = { position: "belowBar", color: "#ef4444", shape: "square", text: "SL dip" };
        else continue;
        markers.push({ time: toChart(tb), ...m });
      }
      markers.sort((a, b) => a.time - b.time);
      s.setMarkers(markers);
      c.subscribeClick((p) => { if (p.time) showAt(fromChart(p.time), source); });
      renderTrades(trd);
      if (pos.length) showAt(pos[pos.length - 1].t, source);
      else { $("hAtTime").textContent = "—"; table($("hAtTbl"), ["Coin", "Hướng", "Vốn dùng", "Entry", "SL", "TP"], []); }
    } catch (e) { toast(e.message); }
  }

  async function showAt(ms, source) {
    try {
      const d = await api(`/api/signals/at?t=${Math.round(ms)}&source=${source}`);
      $("hAtTime").textContent = `nến ${dt(d.run.decision_time)} · vốn dùng ${pct(d.run.gross, 0)}`;
      table($("hAtTbl"), ["Coin", "Hướng", "Vốn dùng", "Entry", "SL", "TP"],
        d.books.map((b) => `<tr><td><b>${coin(b.symbol)}</b></td><td class="${sideCls(b.side)}">${sideVi(b.side)}</td><td>${pct(Math.abs(b.weight))}</td>
          <td>${fmtPx(b.entry)}</td><td class="neg">${fmtPx(b.sl)}</td><td class="pos">${fmtPx(b.tp)}</td></tr>`));
    } catch (e) { $("hAtTime").textContent = "—"; }
  }

  function renderTrades(trd) {
    const rows = trd.slice(-400).reverse().map((e) => {
      let x = {}; try { x = JSON.parse(e.extra || "{}"); } catch (err) { /* ignore */ }
      return `<tr><td>${dt(e.t)}</td><td>${KIND[e.kind] || e.kind}</td><td class="${e.side === "buy" ? "long" : "short"}">${e.side === "buy" ? "Mua" : "Bán"}</td>
        <td>${fmtPx(e.price)}</td><td>${pct(Math.abs(e.weight || 0))}</td><td>${x.ret != null ? signed(x.ret * 100) : ""}</td></tr>`;
    });
    table($("hTrades"), ["Thời gian", "Loại", "Chiều", "Giá", "Tỷ trọng", "Lãi/lỗ dip"], rows);
  }

  // ------------------------------------------------------------------ performance
  async function loadPerf() {
    try {
      const [ov, wfEq, fwEq] = await Promise.all([api("/api/overview"), api("/api/equity?source=walkforward&points=3000"), api("/api/equity?source=forward&points=3000")]);
      const wf = ov.walkforward || {}, fw = ov.forward || {};
      $("perfKpis").innerHTML = [
        ["5 năm walk-forward", wf.monthly_5y, "%/tháng (TB hình học)"], ["4 năm đầu (chọn mô hình)", wf.monthly_dev4, "%/tháng"],
        ["Năm gần nhất (năm giấu)", wf.monthly_last_year, "%/tháng"], ["DD toàn giai đoạn", wf.gate_dd, "% (max 4h / 1 phút)"],
        ["Năm lỗ", wf.losing_years, "năm"],
      ].map(([k, v, s]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v ?? "—"}</div><div class="s">${s}</div></div>`).join("");
      table($("yearTbl"), ["Năm (mốc)", "Lợi nhuận năm", "%/tháng", "DD (1 phút)"],
        (wf.yearly || []).map(([a, net, dd], i, all) => `<tr><td>${esc(String(a).slice(0, 7))} → ${+String(a).slice(0, 4) + 1}${String(a).slice(4, 7)}${i === all.length - 1 ? ' <span class="pill">năm giấu</span>' : ""}</td><td>${signed(net, 1)}</td>
          <td>${signed((Math.pow(1 + net / 100, 1 / 12) - 1) * 100)}</td><td>${dd}%</td></tr>`));
      const c = makeChart("wf", $("wfChart"), { rightPriceScale: { borderColor: "#22314f", mode: LightweightCharts.PriceScaleMode.Logarithmic } });
      c.addAreaSeries({ lineColor: "#3b82f6", topColor: "rgba(59,130,246,.3)", bottomColor: "rgba(59,130,246,0)", lineWidth: 2 })
        .setData(wfEq.map((r) => ({ time: toChart(r.t), value: r.equity })));
      c.timeScale().fitContent();
      const f = makeChart("fw", $("fwChart"));
      f.addLineSeries({ color: "#22c55e", lineWidth: 2 }).setData(fwEq.map((r) => ({ time: toChart(r.t), value: r.equity })));
      f.timeScale().fitContent();
      const st = fw.stats || {};
      $("fwSummary").innerHTML = fw.freeze ? `<dl class="kv">
        <dt>Đóng băng mô hình</dt><dd>${esc(String(fw.freeze).slice(0, 16))} UTC</dd>
        <dt>Đã chấm đến</dt><dd>${esc(String(fw.scored_until || "").slice(0, 16))} UTC</dd>
        <dt>Số nến 4h</dt><dd>${fw.bars} (${fw.days} ngày)</dd>
        <dt>Lợi nhuận ròng</dt><dd>${signed(fw.net_return_pct)}</dd>
        <dt>Quy đổi %/tháng</dt><dd>${fw.monthly_equiv_pct ?? "— (cần ≥ 1 ngày)"}</dd>
        <dt>DD tối đa (1 phút)</dt><dd>${fw.max_dd_1m_pct}%</dd>
        <dt>Lệnh book khớp / SL / TP</dt><dd>${st.fills ?? 0} / ${st.stops ?? 0} / ${st.tps ?? 0}</dd>
        <dt>Lệnh dip khớp / SL / TP</dt><dd>${st.rungs ?? 0} / ${st.rung_stops ?? 0} / ${st.rung_tps ?? 0}</dd>
        <dt>Phí / funding</dt><dd>${pct(st.fees, 3)} / ${pct(st.funding, 3)}</dd></dl>
        <p class="fine">Dữ liệu sau thời điểm đóng băng là bằng chứng sạch duy nhất (mô hình chưa từng thấy).</p>` : `<p class="muted">Chưa có dữ liệu paper trading.</p>`;
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------------ admin
  let jobsTimer = null;
  async function loadAdmin() {
    document.querySelectorAll("[data-run]").forEach((b) => (b.onclick = async () => {
      if (b.dataset.run === "walkforward" && !confirm("Tính lại toàn bộ walk-forward 5 năm?")) return;
      try { await api("/api/admin/run", { method: "POST", body: { kind: b.dataset.run } }); toast("Đã bắt đầu: " + b.dataset.run); setTimeout(loadJobs, 800); }
      catch (e) { toast(e.message); }
    }));
    $("addUser").onclick = async () => {
      const email = $("newEmail").value.trim(); if (!email) return;
      try { await api("/api/admin/users", { method: "POST", body: { email, approved: true } }); $("newEmail").value = ""; loadUsers(); }
      catch (e) { toast(e.message); }
    };
    loadJobs(); loadUsers();
  }

  async function loadJobs() {
    try {
      const jobs = await api("/api/admin/jobs?limit=40");
      table($("jobsTbl"), ["#", "Loại", "Trạng thái", "Bắt đầu", "Thời gian", "Bởi", "Kết quả"], jobs.map((j) =>
        `<tr><td>${j.id}</td><td>${esc(j.kind)}</td><td><span class="pill ${esc(j.status)}">${esc(j.status)}</span></td><td>${dt(j.started_at)}</td>
          <td>${j.finished_at ? ((j.finished_at - j.started_at) / 1000).toFixed(0) + "s" : "…"}</td><td>${esc(j.triggered_by || "")}</td>
          <td class="jobmsg" title="${esc(j.message || "")}">${esc((j.message || "").slice(0, 160))}</td></tr>`));
      clearTimeout(jobsTimer);
      if (state.view === "admin" && jobs.some((j) => j.status === "running")) jobsTimer = setTimeout(loadJobs, 4000);
    } catch (e) { toast(e.message); }
  }

  async function loadUsers() {
    try {
      const users = await api("/api/admin/users");
      table($("usersTbl"), ["Email", "Tên", "Quyền", "Lần cuối", ""], users.map((u) => {
        const admin = u.role === "admin";
        return `<tr><td>${esc(u.email)}</td><td>${esc(u.name || "")}</td><td>${admin ? "Admin" : u.approved ? "Người xem" : "Chờ duyệt"}</td>
          <td>${dt(u.last_seen)}</td><td>${admin ? "" : `<button class="btn sm" data-email="${esc(u.email)}" data-ap="${u.approved ? 0 : 1}">${u.approved ? "Thu hồi" : "Duyệt"}</button>`}</td></tr>`;
      }));
      $("usersTbl").onclick = async (e) => {
        const b = e.target.closest("button[data-email]"); if (!b) return;
        try { await api("/api/admin/users", { method: "POST", body: { email: b.dataset.email, approved: b.dataset.ap === "1" } }); loadUsers(); }
        catch (err) { toast(err.message); }
      };
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------------ boot
  setInterval(() => { if (state.view === "signal" && state.user && state.user.role !== "pending" && !document.hidden) loadSignal(); }, 120000);

  async function boot() {
    if (state.token) {
      try { state.user = await api("/api/auth/me"); enter(); return; }
      catch (e) { if (state.token) logout(); return; }
    }
    try {  // on the server machine itself the backend signs in as the local admin (no Google login)
      state.user = await api("/api/auth/me"); enter(); return;
    } catch (e) { /* not local: Google sign-in */ }
    showOnly("login");
    initGsi();
  }
  boot();
})();
