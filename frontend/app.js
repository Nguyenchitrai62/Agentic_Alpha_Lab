/* Alpha Lab frontend: static SPA (Vercel) + FastAPI backend (Cloudflare tunnel).
   Live page: TradingView widget (real-time) + current suggestion. History page: Lightweight Charts with every past
   order of the pipeline drawn as TradingView-style position boxes, real-time last candle from Binance websockets. */
(() => {
  "use strict";
  const CFG = window.APP_CONFIG || {};
  const API = (CFG.apiBaseUrl || "").replace(/\/$/, "");
  const SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
  const IV_MS = { "1h": 3600e3, "4h": 4 * 3600e3, "1d": 86400e3 };
  const IV_LABEL = { "1h": "1h", "4h": "4h", "1d": "1D" };
  const FIRST_LOAD = { "1h": 6000, "4h": 20000, "1d": 5000 };
  const RANGES = { "1T": 7, "1Th": 30, "3Th": 91, "6Th": 182, "1N": 365, "3N": 1096, "Tất cả": 0 };
  const TZ = -new Date().getTimezoneOffset() * 60; // charts show local time
  const $ = (id) => document.getElementById(id);
  const store = {
    get(k, d) { try { const v = localStorage.getItem("aal_" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("aal_" + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const state = {
    token: store.get("token", ""), user: null, view: "live",
    live: { symbol: store.get("liveSym", "BTCUSDT"), latest: null, prices: {}, tvSym: null },
    h: { symbol: store.get("hSym", "BTCUSDT"), interval: store.get("hIv", "4h"), range: store.get("hRange", "1N"),
         kind: "book", result: "all", selected: null },
  };

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const coin = (s) => s.replace("USDT", "");
  const fmtPx = (p) => p == null || !isFinite(p) ? "—" : Number(p).toLocaleString("en-US", { minimumFractionDigits: p >= 1000 ? 1 : p >= 10 ? 2 : 4, maximumFractionDigits: p >= 1000 ? 1 : p >= 10 ? 2 : p >= 1 ? 4 : 5 });
  const pct = (x, d = 1) => x == null || !isFinite(x) ? "—" : (x * 100).toFixed(d) + "%";
  const sgn = (x, d = 2) => x == null || !isFinite(x) ? "—" : `<span class="${x >= 0 ? "up" : "down"}">${x >= 0 ? "+" : ""}${Number(x).toFixed(d)}%</span>`;
  const dt = (ms) => ms == null ? "—" : new Date(ms).toLocaleString("vi-VN", { hour12: false, year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  const toChart = (ms) => Math.floor(ms / 1000) + TZ;
  const fromChart = (t) => (t - TZ) * 1000;
  const CONF = { CAO: "Cao", "TRUNG BINH": "Trung bình", THAP: "Thấp" };
  const REASON = { TP: "TP", SL: "SL", "Rebalance về 0": "Đóng (rebalance)", "Đảo chiều": "Đảo chiều", "Đang mở": "Đang mở", "Hết 4h (market)": "Hết 4h" };
  const sideBadge = (s, w) => s === "LONG" ? `<span class="badge long">LONG${w != null ? " " + pct(Math.abs(w), 0) : ""}</span>`
    : s === "SHORT" ? `<span class="badge short">SHORT${w != null ? " " + pct(Math.abs(w), 0) : ""}</span>` : `<span class="badge flat">Đứng ngoài</span>`;
  const hms = (ms) => { if (ms <= 0) return "0:00:00"; const s = Math.floor(ms / 1000); return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };

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

  function table(el, head, rows, empty = "Chưa có dữ liệu") {
    el.innerHTML = `<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") ||
      `<tr><td colspan="${head.length}" class="muted">${empty}</td></tr>`}</tbody>`;
  }

  function seg(el, items, active, onPick, label = (x) => x) {
    el.innerHTML = items.map((x) => `<button data-v="${esc(x)}" class="${x === active ? "active" : ""}">${label(x)}</button>`).join("");
    el.onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      el.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      onPick(b.dataset.v);
    };
  }

  // ------------------------------------------------------------------ Binance websockets (public market data)
  function openWs(url, onMsg, onState) {
    let ws, closed = false, delay = 1000;
    const connect = () => {
      ws = new WebSocket(url);
      ws.onopen = () => { delay = 1000; onState && onState(true); };
      ws.onmessage = (ev) => { try { onMsg(JSON.parse(ev.data)); } catch (e) { /* ignore */ } };
      ws.onclose = () => { onState && onState(false); if (!closed) setTimeout(connect, (delay = Math.min(delay * 2, 30000))); };
      ws.onerror = () => ws.close();
    };
    connect();
    return { close() { closed = true; try { ws.close(); } catch (e) { /* ignore */ } } };
  }
  let tickerWs = null;
  function startTicker() {
    if (tickerWs) return;
    const streams = SYMS.map((s) => s.toLowerCase() + "@miniTicker").join("/");
    tickerWs = openWs(`wss://fstream.binance.com/market/stream?streams=${streams}`, (m) => {
      const d = m.data; if (!d || !d.s) return;
      const prev = state.live.prices[d.s]?.c;
      state.live.prices[d.s] = { c: +d.c, o: +d.o };
      updateTickerCells(d.s, prev);
    }, (ok) => { const el = $("wsState"); if (el) { el.textContent = ok ? "● realtime" : "○ mất kết nối"; el.style.color = ok ? "var(--up)" : "var(--down)"; } });
  }

  // ------------------------------------------------------------------ auth
  async function initGsi() {
    let clientId = CFG.googleClientId;
    if (!clientId) {
      try { clientId = (await api("/api/public/config")).google_client_id; }
      catch (e) { $("loginMsg").textContent = e.message; return; }
    }
    if (!clientId) { $("loginMsg").textContent = "Máy chủ chưa cấu hình GOOGLE_CLIENT_ID."; return; }
    await new Promise((res) => { const t = setInterval(() => { if (window.google?.accounts?.id) { clearInterval(t); res(); } }, 100); });
    google.accounts.id.initialize({ client_id: clientId, callback: onCredential, auto_select: false, ux_mode: "popup" });
    google.accounts.id.renderButton($("gsiButton"), { theme: "filled_black", size: "large", shape: "pill", text: "signin_with", locale: "vi" });
  }

  async function onCredential(resp) {
    $("loginMsg").textContent = "Đang đăng nhập…";
    try {
      const out = await api("/api/auth/google", { method: "POST", body: { credential: resp.credential } });
      state.token = out.token; store.set("token", out.token);
      state.user = out.user; $("loginMsg").textContent = "";
      enter();
    } catch (e) { $("loginMsg").textContent = e.message; }
  }

  function logout() {
    state.token = ""; state.user = null; store.set("token", "");
    try { google.accounts.id.disableAutoSelect(); } catch (e) { /* not loaded */ }
    showOnly("login"); $("tabs").hidden = true; $("userBox").innerHTML = "";
    if (!$("gsiButton").childElementCount) initGsi();
  }

  function showOnly(view) { document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "view-" + view)); }

  function enter() {
    const u = state.user;
    $("userBox").innerHTML = `${u.picture ? `<img src="${esc(u.picture)}" alt="" referrerpolicy="no-referrer">` : ""}
      <div><div class="name">${esc(u.name || u.email)}</div><div class="role">${u.role === "admin" ? "Admin" : u.role === "viewer" ? "Người xem" : "Chờ duyệt"}</div></div>
      ${u.local ? '<span class="tag">local</span>' : '<button class="btn sm" id="logoutBtn">Đăng xuất</button>'}`;
    if (!u.local) $("logoutBtn").onclick = logout;
    if (u.role === "pending") { $("pendingEmail").textContent = u.email; showOnly("pending"); $("tabs").hidden = true; return; }
    $("tabs").hidden = false; $("adminTab").hidden = u.role !== "admin";
    startTicker();
    route();
  }

  // ------------------------------------------------------------------ routing
  function route() {
    let v = (location.hash || "#live").slice(1);
    if (!["live", "history", "perf", "admin"].includes(v) || (v === "admin" && state.user.role !== "admin")) v = "live";
    state.view = v;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    showOnly(v);
    ({ live: loadLive, history: initHistory, perf: loadPerf, admin: loadAdmin })[v]();
  }
  $("tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) location.hash = b.dataset.view; };
  window.addEventListener("hashchange", () => state.user && state.user.role !== "pending" && route());
  $("pendingLogout").onclick = logout;

  // ================================================================== LIVE
  let tvLoader = null;
  function loadTvScript() {
    return tvLoader || (tvLoader = new Promise((res, rej) => {
      const s = document.createElement("script"); s.src = "https://s3.tradingview.com/tv.js"; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    }));
  }
  async function mountTv(sym) {
    if (state.live.tvSym === sym && $("tvChart").childElementCount) return;
    state.live.tvSym = sym;
    try { await loadTvScript(); } catch (e) { $("tvChart").innerHTML = '<p class="muted" style="padding:20px">Không tải được TradingView.</p>'; return; }
    $("tvChart").innerHTML = "";
    new window.TradingView.widget({
      container_id: "tvChart", autosize: true, symbol: `BINANCE:${sym}.P`, interval: "240", timezone: "Asia/Ho_Chi_Minh",
      theme: "dark", style: "1", locale: "vi_VN", toolbar_bg: "#131722", enable_publishing: false, allow_symbol_change: true,
      hide_side_toolbar: false, withdateranges: true, details: false, studies: ["Volume@tv-basicstudies"],
      overrides: { "paneProperties.background": "#131722", "paneProperties.backgroundType": "solid" },
    });
  }

  async function loadLive() {
    mountTv(state.live.symbol);
    try {
      state.live.latest = await api("/api/signals/latest?source=live");
      renderWatchlist(); renderSignal(); renderDips(); loadRecent();
    } catch (e) { toast(e.message); }
  }

  function bookOf(sym) { return (state.live.latest?.books || []).find((b) => b.symbol === sym); }

  function renderWatchlist() {
    const rows = SYMS.map((s) => {
      const b = bookOf(s), p = state.live.prices[s];
      return `<tr data-sym="${s}" class="${s === state.live.symbol ? "sel" : ""}"><td class="sym">${coin(s)}<span class="muted small"> USDT.P</span></td>
        <td class="px" id="px-${s}">${p ? fmtPx(p.c) : "…"}</td><td id="ch-${s}">${p ? sgn((p.c / p.o - 1) * 100) : ""}</td>
        <td>${b ? sideBadge(b.side, b.side === "FLAT" ? null : b.weight) : ""}</td></tr>`;
    });
    $("watchlist").innerHTML = `<thead><tr><th style="text-align:left">Coin</th><th>Giá</th><th>24h</th><th>Gợi ý</th></tr></thead><tbody>${rows.join("")}</tbody>`;
    $("watchlist").onclick = (e) => {
      const tr = e.target.closest("tr[data-sym]"); if (!tr) return;
      state.live.symbol = tr.dataset.sym; store.set("liveSym", tr.dataset.sym);
      renderWatchlist(); renderSignal(); renderDips(); loadRecent(); mountTv(tr.dataset.sym);
    };
  }

  function updateTickerCells(sym, prev) {
    const p = state.live.prices[sym];
    const el = $("px-" + sym);
    if (el) {
      el.textContent = fmtPx(p.c);
      if (prev != null && prev !== p.c) { el.classList.remove("flash-up", "flash-down"); void el.offsetWidth; el.classList.add(p.c > prev ? "flash-up" : "flash-down"); }
      $("ch-" + sym).innerHTML = sgn((p.c / p.o - 1) * 100);
    }
    if (sym === state.live.symbol) updateLiveDistances();
  }

  function renderSignal() {
    const sym = state.live.symbol, run = state.live.latest?.run, b = bookOf(sym);
    if (!run || !b) { $("sigPanel").innerHTML = `<div class="panel-h"><span>Gợi ý hiện tại · ${coin(sym)}</span></div><p class="muted">Chưa có tín hiệu. Admin cần chạy pipeline.</p>`; return; }
    const flat = b.side === "FLAT" || !b.entry;
    const k = b.side === "LONG" ? 1 : -1;
    const slP = flat ? null : k * (b.sl / b.entry - 1), tpP = flat ? null : k * (b.tp / b.entry - 1);
    const until = run.decision_time + IV_MS["4h"];
    $("sigPanel").innerHTML = `
      <div class="sig-head"><div><div class="title">${coin(sym)}/USDT</div><div class="muted small">Binance USD-M · pipeline ${esc(run.pipeline)}</div></div>
        <div>${sideBadge(b.side, flat ? null : b.weight)}</div></div>
      <div class="sig-grid">
        <span class="k">Giá hiện tại</span><span class="v" id="sgPx">${fmtPx(state.live.prices[sym]?.c)}</span><span class="d"></span>
        ${flat ? `<span class="k">Hành động</span><span class="v" style="font-family:inherit">Không mở vị thế mới</span><span class="d"></span>` : `
        <span class="k">Vốn dùng</span><span class="v">${pct(Math.abs(b.weight))}</span><span class="d muted">≈ ${Math.round(Math.abs(b.weight) * 10000).toLocaleString("en-US")} / 10k USDT</span>
        <span class="k">Entry (limit)</span><span class="v">${fmtPx(b.entry)}</span><span class="d" id="sgDist"></span>
        <span class="k">Stop-loss (market)</span><span class="v down">${fmtPx(b.sl)}</span><span class="d down">${(slP * 100).toFixed(2)}%</span>
        <span class="k">Take-profit (limit)</span><span class="v up">${fmtPx(b.tp)}</span><span class="d up">+${(tpP * 100).toFixed(2)}%</span>`}
      </div>
      ${flat ? "" : `<div class="bar-rr"><div class="sl" style="flex:${Math.abs(slP)}"></div><div class="tp" style="flex:${Math.abs(tpP)}"></div></div>
        <div class="muted small">Rủi ro : lợi nhuận = 1 : ${(Math.abs(tpP) / Math.abs(slP)).toFixed(1)} · độ tin cậy ${esc(CONF[b.confidence] || b.confidence || "—")}${b.members_agree ? "" : " (2 mô hình lệch nhau)"}</div>`}
      <div class="meta">
        <span>Nến 4h đóng: <b>${dt(run.decision_time)}</b></span>
        <span>Phát lúc: <b>${dt(run.created_at)}</b></span>
        <span>Hiệu lực đến: <b>${dt(until)}</b> (còn <b id="sgLeft">${hms(until - Date.now())}</b>)</span>
        <span>Tổng vốn dùng danh mục: <b>${pct(run.gross, 0)}</b> · hệ số ${(run.scale ?? 0).toFixed(2)}×</span>
      </div>
      <p class="fine">Lệnh entry là limit chờ trong nến 4h hiện tại; không khớp thì huỷ. Sau khi khớp đặt ngay SL (market) và TP (limit).</p>`;
    updateLiveDistances();
  }

  function updateLiveDistances() {
    const sym = state.live.symbol, p = state.live.prices[sym]?.c, b = bookOf(sym);
    if ($("sgPx") && p) $("sgPx").textContent = fmtPx(p);
    if ($("sgDist") && p && b?.entry) $("sgDist").innerHTML = `<span class="muted">cách giá ${((b.entry / p - 1) * 100).toFixed(2)}%</span>`;
  }
  setInterval(() => {
    const run = state.live.latest?.run, el = $("sgLeft");
    if (run && el && state.view === "live") el.textContent = hms(run.decision_time + IV_MS["4h"] - Date.now());
  }, 1000);

  function renderDips() {
    const sym = state.live.symbol;
    const rows = (state.live.latest?.sleeve || []).filter((r) => r.symbol === sym);
    table($("dipTbl"), ["Bậc", "Mua limit", "TP", "SL", "Vốn"], rows.map((r) => `<tr><td>${r.rung}σ</td><td>${fmtPx(r.buy_limit)}</td>
      <td class="up">${fmtPx(r.tp)}</td><td class="down">${fmtPx(r.sl)}</td><td>${pct(r.size_frac)}</td></tr>`), "Không có lệnh chờ");
  }

  async function loadRecent() {
    const sym = state.live.symbol;
    $("recentSym").textContent = coin(sym) + " · chạy thực";
    try {
      const rows = await api(`/api/signals?source=live&symbol=${sym}&limit=30`);
      table($("recentTbl"), ["Nến 4h", "Gợi ý", "Entry", "SL", "TP"], rows.map((r) => `<tr><td>${dt(r.decision_time)}</td>
        <td>${sideBadge(r.side, r.side === "FLAT" ? null : r.weight)}</td><td>${fmtPx(r.entry)}</td><td class="down">${fmtPx(r.sl)}</td>
        <td class="up">${fmtPx(r.tp)}</td></tr>`), "Chưa có");
    } catch (e) { /* ignore */ }
  }

  // ================================================================== HISTORY
  const H = { chart: null, series: null, wSeries: null, prim: null, ws: null, candles: [], times: [], orders: [], pos: [],
              noOlder: false, loadingOlder: false, gen: 0 };

  function idxAt(t) { // last candle index with time <= t (or -1)
    const a = H.times; let lo = 0, hi = a.length - 1, r = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (a[m] <= t) { r = m; lo = m + 1; } else hi = m - 1; }
    return r;
  }

  class OrdersPrimitive { // TradingView-style long/short position boxes drawn under the candles
    constructor() { this._p = null; const self = this; this._view = { zOrder: () => "bottom", renderer: () => ({ draw: (t) => self.draw(t) }) }; }
    attached(p) { this._p = p; }
    detached() { this._p = null; }
    updateAllViews() {}
    paneViews() { return [this._view]; }
    update() { this._p && this._p.requestUpdate(); }
    draw(target) {
      if (!$("tZone").checked || !H.chart) return;
      const ts = H.chart.timeScale(), s = H.series, last = H.times.length - 1;
      target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
        for (const o of H.orders) {
          if (o.kind !== "book" || o.sl == null || o.tp == null) continue;
          const i1 = idxAt(o.entry_t), i2 = o.exit_t ? idxAt(o.exit_t) : last;
          if (i2 < 0) continue;
          const x1 = ts.logicalToCoordinate(Math.max(i1, 0)), x2 = ts.logicalToCoordinate(i2);
          if (x1 == null || x2 == null || x2 < -5 || x1 > mediaSize.width + 5) continue;
          const ye = s.priceToCoordinate(o.entry_px), ysl = s.priceToCoordinate(o.sl), ytp = s.priceToCoordinate(o.tp);
          if (ye == null || ysl == null || ytp == null) continue;
          const sel = o.id === state.h.selected, w = Math.max(x2 - x1, 2);
          ctx.fillStyle = sel ? "rgba(8,153,129,.28)" : "rgba(8,153,129,.10)";
          ctx.fillRect(x1, Math.min(ye, ytp), w, Math.abs(ytp - ye));
          ctx.fillStyle = sel ? "rgba(242,54,69,.28)" : "rgba(242,54,69,.10)";
          ctx.fillRect(x1, Math.min(ye, ysl), w, Math.abs(ysl - ye));
          ctx.fillStyle = o.side === "LONG" ? "#089981" : "#f23645";
          ctx.fillRect(x1, ye - (sel ? 1 : 0.5), w, sel ? 2 : 1);
          if (sel) {
            const txt = `${o.side} ${pct(o.size, 0)} · ${o.pnl_pct == null ? "đang mở" : (o.pnl_pct >= 0 ? "+" : "") + o.pnl_pct.toFixed(2) + "%"} · ${REASON[o.exit_reason] || o.exit_reason}`;
            ctx.font = "600 11px Inter, sans-serif";
            const tw = ctx.measureText(txt).width + 12, y = Math.min(ye, ytp, ysl) - 20;
            ctx.fillStyle = "rgba(30,34,45,.92)"; ctx.fillRect(x1, y, tw, 18);
            ctx.fillStyle = o.pnl_pct == null ? "#d1d4dc" : o.pnl_pct >= 0 ? "#089981" : "#f23645"; ctx.fillText(txt, x1 + 6, y + 13);
          }
        }
      });
    }
  }

  let histInit = false;
  function initHistory() {
    if (!histInit) {
      histInit = true;
      seg($("hSymbols"), SYMS, state.h.symbol, (v) => { state.h.symbol = v; store.set("hSym", v); loadHistory(); }, coin);
      seg($("hIntervals"), ["1h", "4h", "1d"], state.h.interval, (v) => { state.h.interval = v; store.set("hIv", v); loadHistory(); }, (x) => IV_LABEL[x]);
      seg($("hRanges"), Object.keys(RANGES), state.h.range, (v) => { state.h.range = v; store.set("hRange", v); applyRange(); });
      seg($("oKind"), ["all", "book", "dip"], state.h.kind, (v) => { state.h.kind = v; renderOrders(); },
        (x) => ({ all: "Tất cả", book: "Lệnh 4h", dip: "Dip" })[x]);
      seg($("oResult"), ["all", "win", "loss", "open"], state.h.result, (v) => { state.h.result = v; renderOrders(); },
        (x) => ({ all: "Mọi kết quả", win: "Lãi", loss: "Lỗ", open: "Đang mở" })[x]);
      for (const id of ["tBook", "tDip"]) $(id).onchange = () => setMarkers();
      $("tZone").onchange = () => H.prim && H.prim.update();
      $("tWeight").onchange = () => H.wSeries && H.wSeries.applyOptions({ visible: $("tWeight").checked });
      $("zIn").onclick = () => zoom(0.6); $("zOut").onclick = () => zoom(1 / 0.6);
      $("zFit").onclick = () => H.chart && H.chart.timeScale().fitContent();
      $("zNow").onclick = () => H.chart && H.chart.timeScale().scrollToRealTime();
      initResizer();
      loadHistory();
    } else if (H.chart) { H.prim && H.prim.update(); }
  }

  function initResizer() {
    const b = $("bottom"), saved = store.get("bottomH", 290);
    b.style.height = saved + "px";
    $("resizer").onpointerdown = (e) => {
      e.preventDefault(); const y0 = e.clientY, h0 = b.offsetHeight;
      const mv = (ev) => { b.style.height = Math.max(80, Math.min(window.innerHeight * 0.75, h0 + (y0 - ev.clientY))) + "px"; };
      const up = () => { store.set("bottomH", b.offsetHeight); window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
    };
  }

  function zoom(f) {
    if (!H.chart) return;
    const ts = H.chart.timeScale(), r = ts.getVisibleLogicalRange(); if (!r) return;
    const width = (r.to - r.from) * f;
    ts.setVisibleLogicalRange({ from: r.to - width, to: r.to });
  }

  function makeChart(el) {
    const LC = window.LightweightCharts;
    return LC.createChart(el, {
      autoSize: true,
      layout: { background: { color: "#131722" }, textColor: "#b2b5be", fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { vertLines: { color: "rgba(42,46,57,.6)" }, horzLines: { color: "rgba(42,46,57,.6)" } },
      rightPriceScale: { borderColor: "#2a2e39", scaleMargins: { top: 0.08, bottom: 0.18 } },
      timeScale: { borderColor: "#2a2e39", timeVisible: true, secondsVisible: false, rightOffset: 10, barSpacing: 7, minBarSpacing: 0.3 },
      crosshair: { mode: LC.CrosshairMode.Normal, vertLine: { color: "#758696", labelBackgroundColor: "#2a2e39" }, horzLine: { color: "#758696", labelBackgroundColor: "#2a2e39" } },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: true, price: true }, axisDoubleClickReset: true },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      kineticScroll: { mouse: false, touch: true },
    });
  }

  async function loadHistory() {
    const gen = ++H.gen;
    const { symbol, interval } = state.h;
    $("hLoading").hidden = false;
    try {
      const [cand, orders, pos] = await Promise.all([
        api(`/api/candles?symbol=${symbol}&interval=${interval}&limit=${FIRST_LOAD[interval]}`),
        api(`/api/orders?symbol=${symbol}&source=walkforward&limit=30000`),
        api(`/api/positions?symbol=${symbol}&source=walkforward&limit=30000`),
      ]);
      if (gen !== H.gen) return;
      if (H.chart) { H.chart.remove(); H.chart = null; }
      if (H.ws) { H.ws.close(); H.ws = null; }
      H.candles = cand; H.times = cand.map((c) => c.t); H.orders = orders.slice().reverse(); H.pos = pos; H.noOlder = false;
      const c = H.chart = makeChart($("hChart"));
      H.series = c.addCandlestickSeries({ upColor: "#089981", downColor: "#f23645", borderVisible: false, wickUpColor: "#089981",
        wickDownColor: "#f23645", priceFormat: { type: "custom", formatter: fmtPx, minMove: 0.00001 } });
      H.series.setData(cand.map(toBar));
      H.wSeries = c.addHistogramSeries({ priceScaleId: "w", priceFormat: { type: "percent" }, priceLineVisible: false, lastValueVisible: false,
        visible: $("tWeight").checked });
      c.priceScale("w").applyOptions({ scaleMargins: { top: 0.86, bottom: 0 }, visible: false });
      setWeights();
      H.prim = new OrdersPrimitive(); H.series.attachPrimitive(H.prim);
      setMarkers();
      c.subscribeCrosshairMove(onCrosshair);
      c.subscribeClick((p) => { if (p.time) pickOrderAt(fromChart(p.time)); });
      c.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (r && r.from < 30) loadOlder(); });
      renderOrders();
      requestAnimationFrame(() => requestAnimationFrame(applyRange)); // after autoSize has measured the pane
      onCrosshair({});
      H.ws = openWs(`wss://fstream.binance.com/market/ws/${symbol.toLowerCase()}@kline_${interval}`, (m) => {
        const k = m.k; if (!k || !H.series) return;
        const t = k.t, bar = { t, o: +k.o, h: +k.h, l: +k.l, c: +k.c };
        const lastT = H.times[H.times.length - 1];
        if (t < lastT) return;
        if (t > lastT) { H.candles.push(bar); H.times.push(t); } else H.candles[H.candles.length - 1] = bar;
        H.series.update(toBar(bar));
      });
    } catch (e) { toast(e.message); }
    finally { if (gen === H.gen) $("hLoading").hidden = true; }
  }
  const toBar = (r) => ({ time: toChart(r.t), open: r.o, high: r.h, low: r.l, close: r.c });

  async function loadOlder(untilT) {
    if (H.noOlder || H.loadingOlder || !H.candles.length) return;
    H.loadingOlder = true;
    const gen = H.gen, { symbol, interval } = state.h;
    try {
      const first = H.times[0];
      const q = untilT ? `start=${Math.max(0, Math.floor(untilT))}&end=${first - 1}&limit=30000` : `end=${first - 1}&limit=3000`;
      const older = await api(`/api/candles?symbol=${symbol}&interval=${interval}&${q}`);
      if (gen !== H.gen) return;
      if (!older.length) { H.noOlder = true; return; }
      const ts = H.chart.timeScale(), r = ts.getVisibleLogicalRange();
      H.candles = older.concat(H.candles); H.times = H.candles.map((c) => c.t);
      H.series.setData(H.candles.map(toBar));
      setWeights(); setMarkers();
      if (r) ts.setVisibleLogicalRange({ from: r.from + older.length, to: r.to + older.length });
    } catch (e) { /* retry on next scroll */ }
    finally { H.loadingOlder = false; }
  }

  async function applyRange() {
    if (!H.chart || !H.times.length) return;
    const days = RANGES[state.h.range], lastT = H.times[H.times.length - 1];
    if (!days) { H.chart.timeScale().fitContent(); return; }
    const from = lastT - days * 86400e3;
    if (from < H.times[0] && !H.noOlder) await loadOlder(from);
    const i = Math.max(0, idxAt(from));
    H.chart.timeScale().setVisibleLogicalRange({ from: i, to: H.times.length + 8 });
  }

  function setWeights() {
    if (!H.wSeries) return;
    const pos = H.pos; let j = -1; const step = IV_MS[state.h.interval];
    H.wSeries.setData(H.candles.map((k) => {
      while (j + 1 < pos.length && pos[j + 1].t <= k.t) j++;
      const p = j >= 0 && k.t - pos[j].t < step + IV_MS["4h"] ? pos[j] : null;
      return { time: toChart(k.t), value: p ? p.weight * 100 : 0, color: p && p.weight < 0 ? "rgba(242,54,69,.45)" : "rgba(41,98,255,.45)" };
    }));
  }

  function setMarkers() {
    if (!H.series) return;
    const showBook = $("tBook").checked, showDip = $("tDip").checked, out = [], seen = new Set();
    const add = (t, m, key) => { const i = idxAt(t); if (i < 0 || seen.has(i + key)) return; seen.add(i + key); out.push({ time: toChart(H.times[i]), ...m }); };
    for (const o of H.orders) {
      if (o.kind === "book" && showBook) {
        const L = o.side === "LONG", sel = o.id === state.h.selected;
        add(o.entry_t, L ? { position: "belowBar", color: "#089981", shape: "arrowUp", text: sel ? "LONG" : "L" }
                         : { position: "aboveBar", color: "#f23645", shape: "arrowDown", text: sel ? "SHORT" : "S" }, "e" + o.id);
        const hit = o.exit_reason === "TP" || o.exit_reason === "SL";
        if (o.exit_t) add(o.exit_t, { position: L ? "aboveBar" : "belowBar", color: o.pnl_pct >= 0 ? "#089981" : "#f23645", shape: "circle",
          text: sel || hit ? `${hit ? o.exit_reason + " " : ""}${o.pnl_pct >= 0 ? "+" : ""}${o.pnl_pct.toFixed(1)}%` : "" }, "x" + o.id);
      } else if (o.kind === "dip" && showDip) {
        add(o.entry_t, { position: "belowBar", color: "#ff9800", shape: "arrowUp", text: "" }, "d");
        if (o.exit_reason === "SL") add(o.exit_t, { position: "belowBar", color: "#f23645", shape: "square", text: "SL dip" }, "ds");
      }
    }
    out.sort((a, b) => a.time - b.time);
    H.series.setMarkers(out);
  }

  function onCrosshair(p) {
    const { symbol, interval } = state.h;
    let i = H.times.length - 1;
    if (p && p.time) i = idxAt(fromChart(p.time));
    const k = H.candles[i];
    if (!k) { $("hLegend").innerHTML = ""; return; }
    const ch = (k.c / k.o - 1) * 100, cls = ch >= 0 ? "up" : "down";
    const act = H.orders.find((o) => o.kind === "book" && o.entry_t <= k.t + IV_MS[interval] && (o.exit_t == null || o.exit_t >= k.t));
    $("hLegend").innerHTML = `<div class="l1">${coin(symbol)}USDT.P · ${IV_LABEL[interval]} · Binance <span class="muted small">${dt(k.t)}</span></div>
      <div class="ohlc">O <b class="${cls}">${fmtPx(k.o)}</b> H <b class="${cls}">${fmtPx(k.h)}</b> L <b class="${cls}">${fmtPx(k.l)}</b> C <b class="${cls}">${fmtPx(k.c)}</b> <b class="${cls}">${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%</b></div>
      <div>${act ? `${sideBadge(act.side, act.size)} <span class="muted">vào ${fmtPx(act.entry_px)} · SL ${fmtPx(act.sl)} · TP ${fmtPx(act.tp)} · phát ${dt(act.signal_t)}</span>`
        : '<span class="badge flat">Không có vị thế 4h</span>'}</div>`;
  }

  function pickOrderAt(t) {
    const o = H.orders.find((x) => x.kind === "book" && x.entry_t <= t + IV_MS[state.h.interval] && (x.exit_t == null || x.exit_t >= t));
    if (o) selectOrder(o.id, false);
  }

  function filteredOrders() {
    const { kind, result } = state.h;
    return H.orders.filter((o) => (kind === "all" || o.kind === kind) &&
      (result === "all" || (result === "open" ? o.exit_t == null : o.pnl_pct != null && (result === "win" ? o.pnl_pct > 0 : o.pnl_pct <= 0))));
  }

  function renderOrders() {
    const list = filteredOrders(), done = list.filter((o) => o.pnl_pct != null);
    const wins = done.filter((o) => o.pnl_pct > 0), avg = (a) => a.length ? a.reduce((s, o) => s + o.pnl_pct, 0) / a.length : 0;
    const first = list.length ? Math.min(...list.map((o) => o.signal_t)) : null;
    $("oStats").innerHTML = `<span>Lệnh <b>${list.length}</b></span><span>Thắng <b>${done.length ? (100 * wins.length / done.length).toFixed(1) : 0}%</b></span>
      <span>TB lãi <b class="up">+${avg(wins).toFixed(2)}%</b></span><span>TB lỗ <b class="down">${avg(done.filter((o) => o.pnl_pct <= 0)).toFixed(2)}%</b></span>
      <span>TP/SL <b>${list.filter((o) => o.exit_reason === "TP").length}/${list.filter((o) => o.exit_reason === "SL").length}</b></span>
      <span>Từ <b>${first ? dt(first) : "—"}</b></span>`;
    const rows = list.slice().reverse().slice(0, 800).map((o) => `<tr class="click ${o.id === state.h.selected ? "sel" : ""}" data-id="${o.id}">
      <td>${dt(o.signal_t)}</td><td>${o.kind === "dip" ? '<span class="badge dip">DIP</span>' : "4h"}</td><td>${sideBadge(o.side)}</td>
      <td>${fmtPx(o.entry_px)}</td><td class="down">${fmtPx(o.sl)}</td><td class="up">${fmtPx(o.tp)}</td><td>${pct(o.size)}</td>
      <td>${dt(o.entry_t)}</td><td>${o.exit_t ? dt(o.exit_t) : "—"}</td><td>${fmtPx(o.exit_px)}</td>
      <td>${esc(REASON[o.exit_reason] || o.exit_reason || "")}</td><td>${o.pnl_pct == null ? '<span class="muted">đang mở</span>' : sgn(o.pnl_pct)}</td></tr>`);
    table($("ordersTbl"), ["Phát lúc (nến 4h)", "Loại", "Hướng", "Giá vào", "SL", "TP", "Tỷ trọng", "Khớp lúc", "Thoát lúc", "Giá thoát", "Lý do", "Kết quả"],
      rows, "Không có lệnh");
    $("ordersTbl").onclick = (e) => { const tr = e.target.closest("tr[data-id]"); if (tr) selectOrder(+tr.dataset.id, true); };
  }

  async function selectOrder(id, focus) {
    state.h.selected = id;
    document.querySelectorAll("#ordersTbl tr[data-id]").forEach((tr) => tr.classList.toggle("sel", +tr.dataset.id === id));
    const o = H.orders.find((x) => x.id === id); if (!o || !H.chart) return;
    if (o.entry_t < H.times[0]) await loadOlder(o.entry_t - 60 * IV_MS[state.h.interval]);
    setMarkers(); H.prim.update();
    if (focus) {
      const i1 = idxAt(o.entry_t), i2 = o.exit_t ? idxAt(o.exit_t) : H.times.length - 1;
      const pad = Math.max(20, (i2 - i1) * 0.6);
      H.chart.timeScale().setVisibleLogicalRange({ from: i1 - pad, to: i2 + pad });
    }
  }

  // ================================================================== PERFORMANCE
  async function loadPerf() {
    try {
      const [ov, wfEq, fwEq, st] = await Promise.all([api("/api/overview"), api("/api/equity?source=walkforward&points=3000"),
        api("/api/equity?source=forward&points=3000"), api("/api/orders/stats?source=walkforward")]);
      const wf = ov.walkforward || {}, fw = ov.forward || {};
      $("perfKpis").innerHTML = [
        ["5 năm walk-forward", wf.monthly_5y, "%/tháng (TB hình học)"], ["4 năm đầu (chọn mô hình)", wf.monthly_dev4, "%/tháng"],
        ["Năm gần nhất (năm giấu)", wf.monthly_last_year, "%/tháng"], ["DD toàn giai đoạn", wf.gate_dd, "% (max 4h / 1 phút)"],
        ["Năm lỗ", wf.losing_years, "năm"],
      ].map(([k, v, s]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v ?? "—"}</div><div class="s">${s}</div></div>`).join("");
      table($("yearTbl"), ["Năm", "Lợi nhuận năm", "%/tháng", "DD (1 phút)"],
        (wf.yearly || []).map(([a, net, dd], i, all) => `<tr><td>${esc(String(a).slice(0, 7))} → ${+String(a).slice(0, 4) + 1}${String(a).slice(4, 7)}${i === all.length - 1 ? ' <span class="pill">năm giấu</span>' : ""}</td>
          <td>${sgn(net, 1)}</td><td>${sgn((Math.pow(1 + net / 100, 1 / 12) - 1) * 100)}</td><td>${dd}%</td></tr>`));
      const by = {};
      for (const r of st) {
        const k = r.symbol + "|" + r.kind; const a = by[k] || (by[k] = { symbol: r.symbol, kind: r.kind, n: 0, w: 0, s: 0, tp: 0, sl: 0, nd: 0 });
        a.n += r.n; if (r.avg_pnl != null) { a.nd += r.n; a.w += r.win * r.n; a.s += r.avg_pnl * r.n; }
        if (r.exit_reason === "TP") a.tp += r.n; if (r.exit_reason === "SL") a.sl += r.n;
      }
      table($("coinTbl"), ["Coin", "Loại", "Số lệnh", "Tỷ lệ thắng", "TB/lệnh", "TP", "SL"], Object.values(by)
        .sort((a, b) => a.kind.localeCompare(b.kind) || a.symbol.localeCompare(b.symbol))
        .map((a) => `<tr><td>${coin(a.symbol)}</td><td>${a.kind === "dip" ? '<span class="badge dip">DIP</span>' : "4h"}</td><td>${a.n}</td>
          <td>${a.nd ? (100 * a.w / a.nd).toFixed(1) + "%" : "—"}</td><td>${a.nd ? sgn(a.s / a.nd) : "—"}</td><td>${a.tp}</td><td>${a.sl}</td></tr>`));
      drawLine("wf", $("wfChart"), wfEq, "#2962ff", true);
      drawLine("fw", $("fwChart"), fwEq, "#089981", false);
      const s = fw.stats || {};
      $("fwSummary").innerHTML = fw.freeze ? `<dl class="kv">
        <dt>Đóng băng mô hình</dt><dd>${esc(String(fw.freeze).slice(0, 16))} UTC</dd>
        <dt>Đã chấm đến</dt><dd>${esc(String(fw.scored_until || "").slice(0, 16))} UTC</dd>
        <dt>Số nến 4h</dt><dd>${fw.bars} (${fw.days} ngày)</dd>
        <dt>Lợi nhuận ròng</dt><dd>${sgn(fw.net_return_pct)}</dd>
        <dt>Quy đổi %/tháng</dt><dd>${fw.monthly_equiv_pct ?? "— (cần ≥ 1 ngày)"}</dd>
        <dt>DD tối đa (1 phút)</dt><dd>${fw.max_dd_1m_pct}%</dd>
        <dt>Lệnh 4h khớp / SL / TP</dt><dd>${s.fills ?? 0} / ${s.stops ?? 0} / ${s.tps ?? 0}</dd>
        <dt>Lệnh dip khớp / SL / TP</dt><dd>${s.rungs ?? 0} / ${s.rung_stops ?? 0} / ${s.rung_tps ?? 0}</dd></dl>
        <p class="fine">Dữ liệu sau thời điểm đóng băng là bằng chứng sạch duy nhất (mô hình chưa từng thấy).</p>` : `<p class="muted">Chưa có dữ liệu paper trading.</p>`;
    } catch (e) { toast(e.message); }
  }

  const lineCharts = {};
  function drawLine(key, el, rows, color, log) {
    if (lineCharts[key]) lineCharts[key].remove();
    const LC = window.LightweightCharts;
    const c = lineCharts[key] = LC.createChart(el, {
      autoSize: true, layout: { background: { color: "#1e222d" }, textColor: "#b2b5be", fontSize: 11 },
      grid: { vertLines: { color: "rgba(42,46,57,.6)" }, horzLines: { color: "rgba(42,46,57,.6)" } },
      rightPriceScale: { borderColor: "#2a2e39", mode: log ? LC.PriceScaleMode.Logarithmic : LC.PriceScaleMode.Normal },
      timeScale: { borderColor: "#2a2e39" },
    });
    c.addAreaSeries({ lineColor: color, topColor: color + "55", bottomColor: color + "00", lineWidth: 2 })
      .setData(rows.map((r) => ({ time: toChart(r.t), value: r.equity })));
    c.timeScale().fitContent();
  }

  // ================================================================== ADMIN
  let jobsTimer = null;
  async function loadAdmin() {
    document.querySelectorAll("[data-run]").forEach((b) => (b.onclick = async () => {
      if (b.dataset.run === "walkforward" && !confirm("Tính lại toàn bộ walk-forward 5 năm và bảng lệnh?")) return;
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
  setInterval(() => { if (state.view === "live" && state.user && state.user.role !== "pending" && !document.hidden) loadLive(); }, 120000);

  async function boot() {
    if (state.token) {
      try { state.user = await api("/api/auth/me"); enter(); return; }
      catch (e) { if (state.token) logout(); return; }
    }
    try { // on the server machine itself the backend signs in as the local admin (no Google login)
      state.user = await api("/api/auth/me"); enter(); return;
    } catch (e) { /* not local: Google sign-in */ }
    showOnly("login");
    initGsi();
  }
  boot();
})();
