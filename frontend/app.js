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
    token: "", session: null, user: null, view: "live", selectedPipeline: null,
    live: { symbol: store.get("liveSym", "BTCUSDT"), latest: null, prices: {}, tvSym: null },
    h: { symbol: store.get("hSym", "BTCUSDT"), interval: store.get("hIv", "4h"), range: store.get("hRange2", "3Th"),
         kind: "book", result: "all", selected: null },
  };
  let planGeneration = 0, perfGeneration = 0;

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
  const REASON = { TP: "Chạm TP", SL: "Chạm SL", "SL hoà vốn": "SL hoà vốn", "Đóng limit": "Đóng bằng limit", "Hết giờ": "Hết giờ (dip)", "Hết dữ liệu mô phỏng": "Hết dữ liệu mô phỏng (23/09)",
                  "Rebalance về 0": "Đóng (rebalance)", "Đảo chiều": "Đảo chiều", "Đang mở": "Đang mở", "Hết 4h (market)": "Hết 4h" };
  const histSource = () => `tm_${planPipe()}`;
  // walk-forward replay (until the research data end) + the prospective paper window (since the freeze), oldest first per endpoint order
  async function histBoth(kind, symbol) {
    const pipe = planPipe();
    const [a, b] = await Promise.all([api(`/api/${kind}?symbol=${symbol}&source=tm_${pipe}&limit=30000`),
      api(`/api/${kind}?symbol=${symbol}&source=paper_${pipe}&limit=30000`).catch(() => [])]);
    return kind === "orders" ? b.concat(a) : a.concat(b);  // orders come newest first, positions / trades oldest first
  }
  const sideBadge = (s, w) => s === "LONG" ? `<span class="badge long">LONG${w != null ? " " + pct(Math.abs(w), 0) : ""}</span>`
    : s === "SHORT" ? `<span class="badge short">SHORT${w != null ? " " + pct(Math.abs(w), 0) : ""}</span>` : `<span class="badge flat">Đứng ngoài</span>`;
  const hms = (ms) => { if (ms <= 0) return "0:00:00"; const s = Math.floor(ms / 1000); return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };

  function toast(msg, ms = 3500) {
    const el = $("toast"); el.textContent = msg; el.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (el.hidden = true), ms);
  }

  let refreshFlight = null, authEpoch = 0;
  function applySession(out) {
    state.session = out; state.token = out.access_token; state.user = out.user;
    // Access tokens stay in memory; the backend owns the HttpOnly refresh cookie.
  }
  async function refreshSession() {
    if (refreshFlight) return refreshFlight;
    const epoch = authEpoch;
    const run = async () => {
      if (epoch !== authEpoch) throw new Error("Phiên đăng nhập đã thay đổi.");
      let r;
      try { r = await fetch(API + "/api/auth/refresh", { method: "POST", cache: "no-store", credentials: "include" }); }
      catch { throw new Error("Không kết nối được máy chủ API."); }
      if (epoch !== authEpoch) throw new Error("Phiên đăng nhập đã thay đổi.");
      if (r.status === 401) { logout(false); throw new Error("Phiên đăng nhập hết hạn."); }
      if (!r.ok) throw new Error("Không thể làm mới phiên đăng nhập.");
      const out = await r.json();
      if (epoch !== authEpoch) throw new Error("Phiên đăng nhập đã thay đổi.");
      applySession(out);
    };
    refreshFlight = (navigator.locks ? navigator.locks.request("aal-auth-refresh", run) : run())
      .finally(() => { refreshFlight = null; });
    return refreshFlight;
  }
  async function api(path, opts = {}) {
    const sessionRequest = path === "/api/auth/google" || path.startsWith("/api/public/");
    if (!sessionRequest && state.session && state.session.expires_at * 1000 <= Date.now() + 30000) await refreshSession();
    const epoch = authEpoch;
    const send = async () => {
      const headers = { ...(opts.headers || {}) };
      if (state.token && !sessionRequest) headers.Authorization = "Bearer " + state.token;
      if (opts.body) headers["Content-Type"] = "application/json";
      try { return await fetch(API + path, { ...opts, cache: "no-store", credentials: path === "/api/auth/google" ? "include" : "omit", headers, body: opts.body ? JSON.stringify(opts.body) : undefined }); }
      catch { throw new Error("Không kết nối được máy chủ API."); }
    };
    const sentToken = state.token;
    let r = await send();
    if (epoch !== authEpoch) throw new Error("Phiên đăng nhập đã thay đổi.");
    if (r.status === 401 && !sessionRequest && state.session) {
      if (sentToken === state.token) await refreshSession();
      r = await send(); // retry exactly once
    }
    if (epoch !== authEpoch) throw new Error("Phiên đăng nhập đã thay đổi.");
    if (r.status === 401 && state.token && !sessionRequest) { logout(); throw new Error("Phiên đăng nhập hết hạn."); }
    const data = await r.json().catch(() => ({}));
    if (epoch !== authEpoch) throw new Error("Phiên đăng nhập đã thay đổi.");
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
  let tickerLastMessageAt = 0;
  function startTicker() {
    if (tickerWs) return;
    const streams = SYMS.map((s) => s.toLowerCase() + "@miniTicker").join("/");
    tickerWs = openWs(`wss://fstream.binance.com/market/stream?streams=${streams}`, (m) => {
      const d = m.data; if (!d || !d.s) return;
      tickerLastMessageAt = Date.now();
      const prev = state.live.prices[d.s]?.c;
      state.live.prices[d.s] = { c: +d.c, o: +d.o };
      updateTickerCells(d.s, prev);
    }, (ok) => { const el = $("wsState"); if (el) { el.textContent = ok ? "● realtime" : "○ mất kết nối"; el.style.color = ok ? "var(--up)" : "var(--down)"; } });
  }
  function refreshTickerOnResume() {
    if (document.hidden || !state.user || state.user.role === "pending") return;
    // Browsers may suspend background tabs and their WebSockets. Reopen the stream
    // after resume so the title and quote cells catch up from a fresh ticker event.
    if (tickerWs && Date.now() - tickerLastMessageAt > 3000) {
      tickerWs.close();
      tickerWs = null;
    }
    startTicker();
  }
  document.addEventListener("visibilitychange", refreshTickerOnResume);
  window.addEventListener("pageshow", refreshTickerOnResume);
  window.addEventListener("online", refreshTickerOnResume);

  // ------------------------------------------------------------------ auth
  async function initGsi() {
    let clientId = CFG.googleClientId;
    try {
      const config = await api("/api/public/config");
      clientId = clientId || config.google_client_id;
      $("loginAccessNote").textContent = config.automatic_viewer_access
        ? "Đăng nhập Google để xem ngay các pipeline đang mở. Không cần chờ duyệt."
        : "Đăng nhập Google rồi liên hệ admin để được cấp quyền xem.";
    } catch (e) { if (!clientId) { $("loginMsg").textContent = e.message; return; } }
    if (!clientId) { $("loginMsg").textContent = "Máy chủ chưa cấu hình GOOGLE_CLIENT_ID."; return; }
    await new Promise((res) => { const t = setInterval(() => { if (window.google?.accounts?.id) { clearInterval(t); res(); } }, 100); });
    google.accounts.id.initialize({ client_id: clientId, callback: onCredential, auto_select: false, ux_mode: "popup" });
    google.accounts.id.renderButton($("gsiButton"), { theme: "filled_black", size: "large", shape: "pill", text: "signin_with", locale: "vi" });
  }

  async function onCredential(resp) {
    $("loginMsg").textContent = "Đang đăng nhập…";
    try {
      const out = await api("/api/auth/google", { method: "POST", body: { credential: resp.credential } });
      authEpoch++; applySession(out);
      state.user = out.user; $("loginMsg").textContent = "";
      enter();
    } catch (e) { $("loginMsg").textContent = e.message; }
  }

  function logout(revoke = true) {
    const hadSession = Boolean(state.session);
    const wasSignedIn = Boolean(state.user);
    authEpoch++;
    state.token = ""; state.session = null; state.user = null;
    state.selectedPipeline = null; planGeneration++; perfGeneration++;
    store.set("token", ""); store.set("session", null);
    state.live.plan = null; state.live.paper = []; state.live.conf = null; state.evid = null;
    pipelineDraft = null;
    state.h.pipe = null; state.perfPipe = null;
    H.gen++;
    if (H.ws) { H.ws.close(); H.ws = null; }
    if (H.chart) { H.chart.remove(); H.chart = null; }
    H.candles = []; H.times = []; H.orders = []; H.pos = []; H.fills = []; H.posAt = [];
    H.series = null; H.wSeries = null; H.prim = null;
    for (const key of Object.keys(lineCharts)) { lineCharts[key].remove(); delete lineCharts[key]; }
    for (const id of ["pipeEvid", "pipeBar", "board", "todoCards", "planPanel", "watchlist", "hPipe", "ordersTbl", "oStats", "perfKpis", "yearTbl", "coinTbl", "fwSummary", "pPipe", "pipelineSettingsTbl", "pipelineMode", "pipelineSaveStatus", "usersTbl", "jobsTbl", "pipeSelectedNote", "carryBody", "carryMeta"]) {
      const el = $(id); if (el) el.innerHTML = "";
    }
    if (tickerWs) { tickerWs.close(); tickerWs = null; }
    if (revoke && hadSession) fetch(API + "/api/auth/logout", { method: "POST", cache: "no-store", keepalive: true, credentials: "include" }).catch(() => {});
    try { google.accounts.id.disableAutoSelect(); } catch (e) { /* not loaded */ }
    showOnly("login"); $("tabs").hidden = true; $("adminTab").hidden = true; $("userBox").innerHTML = "";
    if (wasSignedIn && !$("gsiButton").childElementCount) initGsi();
  }

  function showOnly(view) { document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "view-" + view)); }

  function enter() {
    const u = state.user;
    $("adminTab").hidden = u.role !== "admin";
    $("userBox").innerHTML = `${u.picture ? `<img src="${esc(u.picture)}" alt="" referrerpolicy="no-referrer">` : ""}
      <div class="name">${esc(u.name || u.email)}</div>
      ${u.local ? '<span class="tag">local</span>' : '<button class="btn sm" id="logoutBtn">Đăng xuất</button>'}`;
    if (!u.local) $("logoutBtn").onclick = logout;
    if (u.role === "pending") {
      clearPipelineData();
      $("pendingEmail").textContent = u.email;
      $("pendingTitle").textContent = u.access_revoked ? "Quyền xem đã được tạm khóa" : "Đang chờ duyệt";
      $("pendingReason").textContent = u.access_revoked
        ? "Admin đã thu hồi quyền xem của tài khoản này. Liên hệ admin để mở lại."
        : "Máy chủ đang yêu cầu admin duyệt tài khoản. Sau khi được mở quyền, bấm kiểm tra lại để tiếp tục.";
      $("pendingContact").href = `mailto:${encodeURIComponent(u.admin_contact_email || "")}`;
      showOnly("pending"); $("tabs").hidden = true; return;
    }
    $("tabs").hidden = false; $("adminTab").hidden = u.role !== "admin"; $("botTab").hidden = !canSeeBot();
    state.h.pipe = null; state.perfPipe = null;
    startTicker();
    route();
  }

  // ------------------------------------------------------------------ routing
  function route() {
    let v = (location.hash || "#todo").slice(1);
    if (!["todo", "bot", "live", "history", "perf", "admin"].includes(v) || (v === "admin" && state.user.role !== "admin")
        || (v === "bot" && !canSeeBot())) v = "todo";
    state.view = v;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    showOnly(v === "bot" ? "todo" : v);
    ({ todo: loadTodo, bot: loadTodo, live: loadLive, history: initHistory, perf: loadPerf, admin: loadAdmin })[v]();
    updateTitle();
  }
  $("tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) location.hash = b.dataset.view; };
  window.addEventListener("hashchange", () => state.user && state.user.role !== "pending" && route());
  $("pendingLogout").onclick = logout;
  async function syncAccountAccess() {
    if (!state.user) return;
    const previous = state.user.role, permissions = JSON.stringify(state.user.allowed_pipelines), user = await api("/api/auth/me");
    state.user = user;
    if (previous !== user.role) { clearPipelineData(); enter(); }
    else if (permissions !== JSON.stringify(user.allowed_pipelines)) {
      clearPipelineData();
      if (user.role !== "pending") route();
    }
    return user;
  }
  $("pendingRetry").onclick = async () => {
    $("pendingRetry").disabled = true; $("pendingMsg").textContent = "Đang kiểm tra quyền xem…";
    try {
      const user = await syncAccountAccess();
      $("pendingMsg").textContent = user?.role === "pending" ? "Quyền xem chưa được mở. Bạn có thể liên hệ admin qua email." : "";
    } catch (e) { $("pendingMsg").textContent = e.message; }
    finally { $("pendingRetry").disabled = false; }
  };

  // ================================================================== LIVE
  let tvLoader = null;
  function loadTvScript() {
    return tvLoader || (tvLoader = new Promise((res, rej) => {
      const s = document.createElement("script"); s.src = "https://s3.tradingview.com/tv.js"; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    }));
  }
  const TV_IVS = [["5", "5m"], ["15", "15m"], ["60", "1h"], ["240", "4h"], ["1D", "1D"]];
  function tvInterval() { const v = store.get("tvIv", "240"); return TV_IVS.some(([k]) => k === v) ? v : "240"; }
  async function mountTv(sym, force = false) {
    const iv = tvInterval();
    if (!force && state.live.tvSym === sym && state.live.tvIv === iv && $("tvChart").childElementCount) return;
    state.live.tvSym = sym; state.live.tvIv = iv;
    try { await loadTvScript(); } catch (e) { $("tvChart").innerHTML = '<p class="muted" style="padding:20px">Không tải được TradingView.</p>'; return; }
    $("tvChart").innerHTML = "";
    new window.TradingView.widget({
      container_id: "tvChart", autosize: true, symbol: `BINANCE:${sym}.P`, interval: iv, timezone: "Asia/Ho_Chi_Minh",
      theme: "dark", style: "1", locale: "vi_VN", toolbar_bg: "#131722", enable_publishing: false, allow_symbol_change: true,
      hide_side_toolbar: false, withdateranges: true, details: false, studies: ["Volume@tv-basicstudies"],
      favorites: { intervals: TV_IVS.map(([k]) => k) },
      overrides: { "paneProperties.background": "#131722", "paneProperties.backgroundType": "solid" },
    });
  }

  async function loadPlans() {
    const gen = ++planGeneration, pipe = planPipe();
    state.live.latest = null;  // the retired v205 live signal is no longer computed; everything comes from the selected pipeline's plan
    if (!pipe) { state.live.plan = null; state.live.paper = []; state.live.planLoading = false; return; }
    state.live.planLoading = true;
    const [plan, paper] = await Promise.all([
      api(`/api/trade_plan?pipeline=${pipe}`).catch(() => null),
      Promise.all(visiblePipes().map((p) => p.v).map((v) =>
        api(`/api/trade_plan?pipeline=${v}`).then((pl) => [v, pl]).catch(() => [v, null]))),
    ]);
    if (gen !== planGeneration || pipe !== planPipe() || !state.user) return;
    state.live.plan = plan; state.live.paper = paper; state.live.planLoading = false;
    if (state.user.role === "admin" && !state.live.conf) state.live.conf = await api("/api/confidence").catch(() => null);
  }
  async function loadLive() {
    mountTv(state.live.symbol);
    try {
      await loadEvidence();
      await loadPlans();
      renderWatchlist(); renderPlan(); updateTitle();
    } catch (e) { toast(e.message); }
  }
  async function renderPipeStatus() {
    const el = $("pipeStatus"); if (!el) return;
    try {
      const h = await api("/api/status"), c = h.last_cycle, ok = c && c.status === "done";
      el.innerHTML = `<span><i class="dot ${ok ? "" : "bad"}"></i>Tín hiệu mới mỗi nến 4h</span>
        <span>Cập nhật: <b>${c ? dt(c.started_at) : "—"}</b>${c && !ok ? ` (${esc(c.status)})` : ""}</span>
        <span>Lần tới: <b>${h.next_cycle_utc ? dt(Date.parse(h.next_cycle_utc)) : "—"}</b></span>`;
    } catch (e) { el.textContent = ""; }
  }
  // ---- evidence table: the walk-forward record of every paper pipeline
  async function loadEvidence() {
    try {
      const evidence = await api("/api/pipelines_summary");
      const permitted = Object.keys(evidence).sort((a, b) => evidence[a].rank - evidence[b].rank).filter((p) => !evidence[p].locked);
      if (state.user.allowed_pipelines?.some((p) => !permitted.includes(p))) clearPipelineData();
      state.user.allowed_pipelines = permitted;
      state.evid = evidence; renderEvidence();
    } catch (e) { toast(e.message); }
  }
  function clearPipelineData() {
    planGeneration++; perfGeneration++;
    state.live.plan = null; state.live.paper = []; state.h.pipe = null; state.h.selected = null; state.perfPipe = null;
    state.live.planLoading = false;
    ++H.gen;
    if (H.chart) { H.chart.remove(); H.chart = null; }
    if (H.ws) { H.ws.close(); H.ws = null; }
    H.orders = []; H.pos = []; H.fills = []; H.candles = []; H.times = [];
    for (const key of Object.keys(lineCharts)) { lineCharts[key].remove(); delete lineCharts[key]; }
    for (const id of ["board", "todoCards", "planPanel", "watchlist", "hLegend", "hPipe", "ordersTbl", "oStats", "perfKpis", "yearTbl", "coinTbl", "fwSummary", "pPipe"]) $(id).innerHTML = "";
  }
  function accessMessage() {
    return `<p class="muted">Các pipeline đang được khóa. Bạn vẫn xem được bảng đánh giá ở tab <a href="#todo">Pipeline</a>.
      <a href="mailto:${esc(encodeURIComponent(state.user?.admin_contact_email || ""))}">Liên hệ admin để mở quyền xem tín hiệu</a>.</p>`;
  }
  // live paper result since the freeze vs the research bootstrap for the same horizon (scripts/prospective_scorecard.py)
  function paperCell(pr) {
    if (!pr || pr.live_pct == null) return "—";
    const days = pr.days != null ? ` <span class="muted small">(${Number(pr.days).toFixed(1)} ngày)</span>` : "";
    const pc = pr.percentile != null ? ` · p${Math.round(pr.percentile)}` : "";
    return `<span class="${pr.live_pct >= 0 ? "up" : "down"}">${Number(pr.live_pct).toFixed(2)}%</span>${pc}${days}`;
  }
  function renderEvidence() {
    const ev = state.evid; if (!ev) return;
    const cur = planPipe(), prod = product(), P = PRODUCTS[prod];
    const mo = (net) => (Math.pow(1 + net / 100, 1 / 12) - 1) * 100;
    const f = (x, d = 2) => x == null || !isFinite(x) ? "—" : Number(x).toFixed(d);
    const order = Object.keys(ev).sort((a, b) => ev[a].rank - ev[b].rank).filter((v) => pipeOf(v)?.product === prod);
    const row = (v, rank) => {
      const p = pipeOf(v);
      const locked = ev[v].locked;
      const email = ev[v].admin_contact_email || state.user?.admin_contact_email || "";
      const contact = locked ? `<div class="pipe-access">${ICON_LOCK} Tín hiệu đang khóa · <a href="mailto:${esc(encodeURIComponent(email))}?subject=${encodeURIComponent("Xin quyền xem pipeline " + p.nm)}">Liên hệ admin qua email</a></div>`
        : "";
      const s = ev[v]?.walkforward || {}, y = s.yearly || [];
      const dev = y.slice(0, 4).map((r) => mo(r[1]));
      const worst = dev.length ? Math.min(...dev) : null;
      const last = s.monthly_last_year;
      const [wd, wh] = P.winKey === "all" ? [s.win_all_dev ?? s.win_dev, s.win_all_hidden ?? s.win_hidden] : [s.win_dev, s.win_hidden];
      const win = wd != null ? `${(100 * wd).toFixed(0)}% / ${(100 * (wh ?? 0)).toFixed(0)}%` : "—";
      const star = v === P.rec ? '<span class="tag">khuyên dùng</span>' : "";
      return `<tr class="${locked ? "locked" : cur === v ? "on" : ""}" ${locked ? 'data-locked="true"' : `data-pipe="${v}"`}><td><div class="pcell"><span class="radio"></span><div>
        <div class="pn-name">${locked ? `<b>#${rank} ${p.nm}</b> ${star}` : `<button type="button" class="pipeline-choice" data-pipe="${v}" aria-pressed="${cur === v}">#${rank} ${p.nm}<span>${cur === v ? "Đang xem" : "Xem tín hiệu"}</span></button> ${star}`}</div><div class="pn-desc">${p.ds}</div>${contact}</div></div></td>
        <td class="${last >= 5 ? "up" : ""}"><b>${f(last)}</b></td><td class="${s.gate_dd > 20 ? "down" : ""}">${f(s.gate_dd, 1)}%</td>
        <td>${pct(wh)}</td><td>${f(s.monthly_dev4)}</td><td>${f(worst)}</td><td>${f(s.monthly_5y)}</td><td>${esc(s.losing_years ?? "—")}</td><td>${win}</td>
        <td>${esc(s.trades_dev ?? "—")} / ${esc(s.trades_hidden ?? "—")}</td><td>${f(s.dd_4h, 1)}% / ${f(s.dd_1m, 1)}%</td>
        <td>${paperCell(ev[v].prospective)}</td></tr>`;
    };
    const winLbl = P.winKey === "all" ? "mọi lệnh" : "lệnh book";
    const head = ["Thứ tự / pipeline", "Test · 1 năm<br>Lãi ròng/tháng (%)", "DD<br>tối đa", `Win ${winLbl}<br>Test`, "Train / chọn model<br>4 năm · Lãi ròng/tháng (%)", "Train: năm thấp nhất<br>Lãi ròng/tháng (%)", "Toàn bộ 5 năm<br>Lãi ròng/tháng (%)", "Số năm<br>thua lỗ", `Win ${winLbl}<br>(Train / Test)`, "Số lệnh book<br>(Train / Test)", "DD<br>(nến 4h / từng phút)", "Paper thực tế<br>lãi · phân vị so với kỳ vọng"];
    table($("pipeEvid"), head, order.map((v, i) => row(v, i + 1)));
    renderPlanCards(order);
    $("evidTitle").textContent = prod === "bot" ? "Chọn bot" : "Chọn pipeline";
    $("pipeOrderNote").textContent = Object.values(ev)[0]?.automatic_order
      ? "Thứ tự trong từng sản phẩm: lợi nhuận/tháng Test cao hơn → DD thấp hơn → Win rate Test cao hơn."
      : "Thứ tự do admin sắp xếp. Trạng thái khóa do admin quản lý riêng cho từng pipeline.";
    $("pipeSelectedNote").textContent = cur
      ? `Đang xem: ${PIPE_LABEL[cur]}. Lựa chọn áp dụng cho Manual / Bot, Market, History và Performance.`
      : "Chưa có pipeline được mở quyền xem tín hiệu.";
    for (const id of ["pipeEvid", "pipeCards"]) $(id).onclick = (e) => { const r = e.target.closest("[data-pipe]"); if (r) setPlanPipe(r.dataset.pipe); };
  }
  // one card per pipeline of the open tab: the headline numbers, the live paper result and either "view signals" or "unlock"
  function renderPlanCards(order) {
    const el = $("pipeCards"); if (!el) return;
    const ev = state.evid, cur = planPipe(), P = PRODUCTS[product()];
    el.style?.setProperty?.("--n", Math.max(1, order.length));
    const f = (x, d = 1) => x == null || !isFinite(x) ? "—" : Number(x).toFixed(d);
    el.innerHTML = order.map((v) => {
      const p = pipeOf(v), e = ev[v], s = e.walkforward || {}, locked = e.locked, on = cur === v;
      const win = P.winKey === "all" ? (s.win_all_hidden ?? s.win_hidden) : s.win_hidden;
      const pr = e.prospective;
      const paper = pr && pr.live_pct != null && pr.days >= 1 ? `${sgn(pr.live_pct)} <span class="muted">· ${Math.floor(pr.days)} ngày</span>`
        : '<span class="muted">mới bắt đầu</span>';
      const email = e.admin_contact_email || state.user?.admin_contact_email || "";
      const cta = locked
        ? `<a class="btn pc-cta unlock" href="mailto:${esc(encodeURIComponent(email))}?subject=${encodeURIComponent("Xin quyền xem pipeline " + p.nm)}">${ICON_LOCK} Liên hệ admin để xem</a>`
        : `<button type="button" class="btn pc-cta ${on ? "primary" : ""}" data-pipe="${v}" aria-pressed="${on}">${on ? "Đang xem tín hiệu" : "Xem tín hiệu"}</button>`;
      return `<article class="plan-card${on ? " on" : ""}${locked ? " locked" : ""}" ${locked ? 'data-locked="true"' : `data-pipe="${v}"`}>
        <div class="pc-top"><span class="pc-name">${esc(p.nm)}</span><span class="pc-badges">
          ${v === P.rec ? `<span class="pc-badge rec">${ICON_STAR} Khuyên dùng</span>` : ""}${locked ? `<span class="pc-badge lock">${ICON_LOCK} Đang khóa</span>` : ""}</span></div>
        <p class="pc-tag" title="${esc(p.tag)}">${esc(p.tag)}</p>
        <dl class="pc-key"><div><dt>Năm ẩn</dt><dd class="${s.monthly_last_year >= 0 ? "up" : "down"}">${f(s.monthly_last_year)}%</dd><span>lãi / tháng</span></div>
          <div><dt>DD tối đa</dt><dd>${f(s.gate_dd)}%</dd><span>sụt vốn</span></div>
          <div><dt>Win</dt><dd>${win != null ? Math.round(100 * win) + "%" : "—"}</dd><span>năm ẩn</span></div></dl>
        <dl class="pc-stats"><div><dt>TB 5 năm</dt><dd>${f(s.monthly_5y)}%/th</dd></div>
          <div><dt>Paper thực tế</dt><dd>${paper}</dd></div></dl>
        ${cta}</article>`;
    }).join("") || '<p class="muted">Chưa có dữ liệu.</p>';
  }

  async function loadTodo() {
    try {
      renderPipeStatus();
      await loadEvidence();
      if (pipeOf(planPipe())?.product !== product()) await ensureProductPipe();
      await loadPlans();
      renderProduct(); renderGoals(); renderPipeBar(); renderBoard(); renderCards(); renderProductPanels(); renderCarry(); updateTitle();
    } catch (e) { toast(e.message); }
  }

  // ---- executable trade plan (trade mode): what should be on the exchange now
  const planOf = (sym) => state.live.plan?.coins?.[sym];
  // multi-phase plans (v376 R2·4P): four clock-shifted sub-books merged into one plan; coins[sym].subs = one single-book-shaped
  // entry per sub-book, coins[sym].dips carry their phase; all weights are fractions of the TOTAL account
  const isMulti = () => !!state.live.plan?.multi_phase;
  const phLabel = (n) => (state.live.plan?.phases || []).find((p) => p.phase === n)?.label ?? `khung +${n}h`;
  const phTag = (u) => u == null ? "" : `<span class="tag phase-tag">${esc(u.label ?? phLabel(u.phase))}</span>`;
  const byPhase = (a, b) => Number(a.phase ?? 0) - Number(b.phase ?? 0);
  const subViews = (sym) => (planOf(sym)?.subs || []).slice().sort(byPhase);
  const liveSub = (u) => (u.state === "position" && u.position) || (u.state === "pending" && u.order);
  const sortedDips = (d) => isMulti() ? d.slice().sort((a, b) => byPhase(a, b) || a.rung - b.rung) : d;
  const phasesPending = () => (state.live.plan?.phases || []).filter((p) => p.started === false).sort(byPhase);
  // paper pipelines (prospective evidence); O1 = the most robust walk-forward foundation, the default view
  // paper pipelines grouped by PRODUCT (one tab each): MANUAL = the Manual tab, a human can follow it (book + bracket dip limits with
  // exchange-native TP / SL; per-pipeline locks); BOT = the Bot tab (full dip ladder, stops watched on 5m closes; the 3 best, no locks,
  // visible to admins and to accounts with the BOT grant). tag = the plain-language card text; ds = the technical description.
  const PIPES = [
    { v: "v367", nm: "M5", tag: "Tỉ lệ thắng cao nhất: lệnh đang lỗ khi tín hiệu tắt được siết SL thay vì đóng", product: "manual", ds: "Book ×0.75 (SL/TP 5σ/10σ) + 2 lệnh limit bắt đáy mỗi coin (3σ / 4σ) kèm TP và SL sàn 8σ; tín hiệu tắt mà lệnh đang lỗ thì siết SL thay vì đóng — win lệnh book ~66%" },
    { v: "v362", nm: "M4", tag: "Lệnh xu hướng SL/TP rộng + 2 lệnh bắt đáy mỗi coin", product: "manual", ds: "Như M5 nhưng đóng lệnh khi tín hiệu tắt (không siết SL)" },
    { v: "v342", nm: "M3", tag: "Lệnh xu hướng + 2 lệnh bắt đáy mỗi coin", product: "manual", ds: "Book ×0.75 (SL/TP 4σ/8σ) + 2 lệnh limit bắt đáy 3σ / 4σ kèm TP và SL sàn 8σ" },
    { v: "v340", nm: "M2", tag: "Lệnh xu hướng + 1 lệnh bắt đáy mỗi coin; DD thấp nhất", product: "manual", ds: "Book ×0.75 (SL/TP 4σ/8σ) + 1 lệnh limit bắt đáy 3σ kèm TP và SL sàn 8σ" },
    { v: "v315", nm: "M1", tag: "Chỉ lệnh theo xu hướng, ít lệnh, dễ theo nhất", product: "manual", ds: "Chỉ lệnh book (không bắt đáy), vào bằng limit hồi giá 0.75σ" },
    { v: "v321", nm: "R2", tag: "Thang 5 lệnh bắt đáy mỗi coin, AI chọn khối lượng và chốt lời", product: "bot", ds: "Book CB + thang bắt đáy 2.5–5σ (SL bot theo nến 5m + SL sàn 8σ), agent RL chọn khối lượng & chốt lời" },
    { v: "v376", nm: "R2·4P", tag: "R2 chạy song song 4 khung giờ, mỗi khung 1/4 vốn - DD thấp hơn", product: "bot", ds: "R2 (book CB + thang bắt đáy 2.5–5σ, agent chọn khối lượng & chốt lời) chạy trên 4 khung 4h lệch 0/1/2/3 giờ (nến bắt đầu 00/04/08.., 01/05/.., 02/06/.., 03/07/.. UTC), mỗi khung 1/4 vốn, không cân bằng lại" },
    { v: "v301", nm: "G2", tag: "Thang 4 lệnh bắt đáy mỗi coin, AI chọn khối lượng và chốt lời", product: "bot", ds: "Như R2 nhưng thang 2.5–4σ, agent học từ 4 độ sâu" },
    { v: "v295", nm: "CS", tag: "Thang 4 lệnh bắt đáy mỗi coin, AI chọn khối lượng", product: "bot", ds: "Book CB + thang bắt đáy 2.5–4σ, agent RL chỉ chọn khối lượng (học từ 35 coin)" },
  ];
  const PRODUCTS = {
    manual: { label: "Giao dịch thủ công (MANUAL)", rec: "v367", winKey: "book",
      note: "Bạn tự đặt lệnh: mỗi 4h vài lệnh limit có sẵn SL/TP trên sàn. Bật Hedge mode để lệnh bắt đáy không bù trừ lệnh SHORT.",
      goals: [
        { name: "Mục tiêu 1 (bắt buộc)", items: [["monthly_5y", "5 năm", ">=", 5, "%/th"], ["monthly_last_year", "Năm Test", ">=", 5, "%/th"],
          ["gate_dd", "DD", "<", 20, "%"], ["win_hidden", "Win lệnh book (Test)", ">=", 0.55, "win"], ["losing_years", "Năm thua lỗ", "==", 0, ""]] },
        { name: "Mục tiêu 2", items: [["monthly_5y", "5 năm", ">=", 8, "%/th"], ["gate_dd", "DD", "<", 15, "%"], ["win_hidden", "Win lệnh book (Test)", ">=", 0.60, "win"]] },
      ] },
    bot: { label: "Bot tự động (BOT)", rec: "v321", winKey: "all",
      note: "Cần bot chạy 24/7: đặt lại thang lệnh bắt đáy mỗi 4h và theo dõi SL trên nến 5m.",
      goals: [
        { name: "Mục tiêu BOT", items: [["monthly_5y", "5 năm", ">=", 8, "%/th"], ["monthly_last_year", "Năm Test", ">=", 8, "%/th"], ["gate_dd", "DD", "<", 15, "%"],
          ["win_all_hidden", "Win mọi lệnh (Test)", ">", 0.65, "win"], ["losing_years", "Năm thua lỗ", "==", 0, ""]] },
      ] },
  };
  const pipeOf = (v) => PIPES.find((p) => p.v === v);
  const ICON_LOCK = '<svg class="ic" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
  const ICON_STAR = '<svg class="ic" viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z" fill="currentColor"/></svg>';
  const product = () => state.view === "bot" ? "bot" : "manual";  // the Pipeline tab = MANUAL, the Bot tab = BOT
  const canSeeBot = () => state.user?.role === "admin" || !!state.user?.bot_access;
  // keep the selected pipeline inside the product of the open tab (the recommended one first)
  async function ensureProductPipe() {
    const p = product(), cur = pipeOf(planPipe());
    if (cur?.product === p) return;
    const allowed = visiblePipes().filter((x) => x.product === p);
    if (!allowed.length) return;
    const rec = allowed.find((x) => x.v === PRODUCTS[p].rec) || allowed[0];
    await setPlanPipe(rec.v);
  }
  function renderProduct() {
    const el = $("productNote"); if (el) el.textContent = PRODUCTS[product()].note;
  }
  // goal progress of the product's selected (or recommended) pipeline: replay metrics vs the targets + the live paper result
  function renderGoals() {
    const el = $("goalPanel"); if (!el || !state.evid) return;
    el.hidden = state.user?.role !== "admin";  // research goal progress: admins only
    const prod = product(), P = PRODUCTS[prod], cur = pipeOf(planPipe());
    const v = cur?.product === prod ? cur.v : P.rec, ev = state.evid[v];
    if (!ev) { el.innerHTML = ""; return; }
    const s = ev.walkforward || {};
    const val = (k) => k === "win_all_hidden" ? (s.win_all_hidden ?? s.win_hidden) : s[k];
    const show = (x, unit) => x == null || !isFinite(x) ? "—" : unit === "win" ? `${(100 * x).toFixed(0)}%` : unit === "" ? String(x) : `${Number(x).toFixed(2)}${unit === "%" ? "%" : ""}`;
    const tgt = (op, t, unit) => `${{ ">=": "≥", "<": "<", ">": ">", "==": "=" }[op]} ${unit === "win" ? (100 * t).toFixed(0) + "%" : t + (unit === "%" ? "%" : "")}`;
    const pass = (x, op, t) => x != null && isFinite(x) && ({ ">=": x >= t, "<": x < t, ">": x > t, "==": x === t }[op]);
    const goals = P.goals.map((g) => {
      const chips = g.items.map(([k, name, op, t, unit]) => {
        const x = val(k), ok = pass(x, op, t);
        return `<span class="goal-chip ${ok ? "ok" : "no"}" title="${esc(name)} ${tgt(op, t, unit)}"><b>${esc(name)}</b> ${show(x, unit)} <span class="muted">${tgt(op, t, unit)}</span> ${ok ? "✓" : "✗"}</span>`;
      }).join("");
      const all = g.items.every(([k, , op, t]) => pass(val(k), op, t));
      return `<div class="goal-row"><span class="goal-name">${esc(g.name)}: <b class="${all ? "up" : "down"}">${all ? "đạt trên mô phỏng" : "chưa đạt"}</b></span>${chips}</div>`;
    }).join("");
    const pr = ev.prospective;
    const paper = pr && pr.live_pct != null
      ? `Paper (dữ liệu mới, chưa ai thấy): <b>${sgn(pr.live_pct)}</b> sau ${Number(pr.days || 0).toFixed(1)} ngày${pr.percentile != null ? ` · phân vị <b>p${Math.round(pr.percentile)}</b> so với kỳ vọng (50 = đúng như nghiên cứu)` : " · chưa đủ dữ liệu để so kỳ vọng"}`
      : "Paper: chưa có dữ liệu (pipeline mới hoặc chưa tới giờ bắt đầu).";
    el.innerHTML = `<div class="panel-h"><span>Tiến độ mục tiêu · ${esc(PIPE_LABEL[v] || v)}${v === P.rec ? ' <span class="tag">khuyên dùng</span>' : ""}</span>
      <span class="muted small">mô phỏng walk-forward 2021-09 → 2026-09</span></div>${goals}
      <div class="goal-paper">${paper}</div>
      <div class="muted small">Đạt trên mô phỏng chưa phải xác nhận cuối: năm Test đã được xem nhiều lần trong nghiên cứu; bằng chứng sạch là kết quả paper trên dữ liệu mới.</div>`;
  }
  // BOT: what the bot must keep doing (MANUAL orders live in the coin cards)
  function renderProductPanels() {
    const bn = $("botNote"); if (!bn) return;
    const cur = pipeOf(planPipe());
    bn.hidden = !(product() === "bot" && cur?.product === "bot");
    if (!bn.hidden) bn.innerHTML = `<b>Vận hành bot · ${esc(cur.nm)}</b><span>Mỗi nến 4h đặt lại toàn bộ lệnh bắt đáy (từ phút 16 đến hết nến).</span>
      <span>SL bắt đáy kích hoạt khi nến 5m đóng dưới mức SL; luôn có SL sàn 8σ phòng mất kết nối.</span><span>Lệnh bắt đáy còn mở cuối nến: đóng ở giá mở nến sau.</span>`;
  }
  // ---- carry quý (paper): sổ cash-and-carry (chỉ đọc)
  async function renderCarry() {
    const body = $("carryBody"); if (!body) return;
    const meta = $("carryMeta");
    try {
      const v = await api("/api/carry");
      const open = Array.isArray(v.open_pairs) ? v.open_pairs : [];
      const done = Array.isArray(v.settled_pairs) ? v.settled_pairs : [];
      const t = v.totals || {};
      const upd = v.updated_at ? dt(Date.parse(v.updated_at)) : "—";
      if (meta) meta.innerHTML = `Cập nhật sổ: <b>${esc(upd)}</b>${v.stale ? ' · <span class="down">sổ đã cũ (hơn 2 giờ chưa chạy)</span>' : ""}`;
      const rule = v.rule || {};
      const ruleLine = (rule.basis_threshold != null || v.rule_sha256)
        ? `<p class="muted small">Quy tắc đông lạnh: vào lệnh khi basis ≥ ${(((rule.basis_threshold ?? 0.04) * 100)).toFixed(0)}%/năm · giữ tới đáo hạn · sha <span class="mono">${esc((v.rule_sha256 || "").slice(0, 12))}</span></p>`
        : "";
      const openTbl = open.length
        ? `<div class="table-wrap" tabindex="0"><table class="tbl compact"><thead><tr><th>Coin</th><th>Hợp đồng</th><th>Vào lúc</th><th>Basis %/năm</th><th>Còn lại</th><th>MtM % vốn phân bổ</th><th>Phí vào</th></tr></thead><tbody>${open.map((p) =>
          `<tr><td>${esc(p.coin ?? "")}</td><td>${esc(p.contract ?? "")}</td><td>${p.entry_time ? esc(dt(Date.parse(p.entry_time))) : "—"}</td>` +
          `<td class="${(p.entry_basis ?? 0) >= 0 ? "up" : "down"}">${p.entry_basis_pct_yr != null ? Number(p.entry_basis_pct_yr).toFixed(2) + "%" : "—"}</td>` +
          `<td>${p.days_to_delivery != null ? Number(p.days_to_delivery).toFixed(0) + " ngày" : "—"}</td>` +
          `<td class="${(p.mtm_alloc ?? 0) >= 0 ? "up" : "down"}">${p.mtm_pct_alloc != null ? (Number(p.mtm_pct_alloc) >= 0 ? "+" : "") + Number(p.mtm_pct_alloc).toFixed(2) + "%" : "—"}</td>` +
          `<td>${p.entry_fees_usdt != null ? Number(p.entry_fees_usdt).toFixed(2) + " USDT" : "—"}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="muted">Không có cặp nào đang mở.</p>`;
      const doneTbl = done.length
        ? `<div class="panel-h sub"><span>Đã tất toán (${done.length})</span></div><div class="table-wrap" tabindex="0"><table class="tbl compact"><thead><tr><th>Coin</th><th>Hợp đồng</th><th>Tất toán</th><th>Lãi/lỗ thực hiện</th></tr></thead><tbody>${done.slice(-10).reverse().map((p) =>
          `<tr><td>${esc(p.coin ?? "")}</td><td>${esc(p.contract ?? "")}</td><td>${p.settled_at ? esc(dt(Date.parse(p.settled_at))) : "—"}</td>` +
          `<td class="${(p.realised_pnl_usdt ?? 0) >= 0 ? "up" : "down"}">${p.realised_pnl_usdt != null ? (Number(p.realised_pnl_usdt) >= 0 ? "+" : "") + Number(p.realised_pnl_usdt).toFixed(2) + " USDT" : "—"}</td></tr>`).join("")}</tbody></table></div>`
        : "";
      const pnl = t.realised_pnl_usdt != null ? Number(t.realised_pnl_usdt) : null;
      body.innerHTML = `${ruleLine}${openTbl}${doneTbl}`
        + `<p class="fine">Tổng lãi/lỗ thực hiện: <b class="${pnl != null && pnl < 0 ? "down" : "up"}">${pnl != null ? (pnl >= 0 ? "+" : "") + pnl.toFixed(2) + " USDT" : "—"}</b>`
        + ` · phí đã trả ${t.fees_paid_usdt != null ? Number(t.fees_paid_usdt).toFixed(2) + " USDT" : "—"}`
        + `. Sổ paper chỉ theo dõi, hệ thống không đặt lệnh thật.</p>`;
    } catch (e) { body.innerHTML = `<p class="muted">Không tải được sổ carry: ${esc(e.message)}</p>`; }
  }
  const PIPE_LABEL = Object.fromEntries(PIPES.map((p) => [p.v, p.nm]));
  function visiblePipes() {
    const ids = state.user?.allowed_pipelines || [];
    return ids.map((v) => PIPES.find((p) => p.v === v)).filter(Boolean);
  }
  function planPipe() {
    const pipes = visiblePipes(), fallback = pipes[0]?.v;
    if (pipes.some((p) => p.v === state.selectedPipeline)) return state.selectedPipeline;
    try { const v = localStorage.getItem("planPipe6"); return pipes.some((p) => p.v === v) ? v : fallback; }
    catch { return fallback; }
  }
  async function setPlanPipe(v) {
    if (!visiblePipes().some((p) => p.v === v)) return;
    state.selectedPipeline = v;
    try { localStorage.setItem("planPipe6", v); } catch { /* per-viewer convenience only */ }

    clearPipelineData();
    const gen = ++planGeneration;
    state.live.planLoading = true;
    renderPipeBar(); renderBoard(); renderCards(); renderWatchlist(); renderPlan(); renderEvidence();
    if (state.view === "history") initHistory();
    else if (state.view === "perf") loadPerf();
    const plan = await api(`/api/trade_plan?pipeline=${v}`).catch((e) => {
      if (gen === planGeneration) toast(e.message);
      return null;
    });
    if (gen !== planGeneration || v !== planPipe() || !state.user) return;
    state.live.plan = plan; state.live.planLoading = false;
    renderPipeBar(); renderBoard(); renderCards(); renderWatchlist(); renderPlan(); renderEvidence(); renderGoals(); renderProductPanels();
  }
  function renderPipeBar() {
    if (!$("pipeBar")) return;  // the Pipeline tab now selects pipelines in the training-results table
    const cur = planPipe(), paper = Object.fromEntries(state.live.paper || []);
    $("pipeBar").innerHTML = visiblePipes().map((p) => {
      const pl = paper[p.v];
      const pn = pl && pl.freeze ? `paper từ ${String(pl.freeze).slice(5, 10).split("-").reverse().join("/")}: ${sgn(pl.net_return_pct)}` : "paper: chưa có";
      return `<button class="pipebtn${cur === p.v ? " on" : ""}" data-pipe="${p.v}">
        <span class="nm">${p.nm}${p.star ? `<span class="star">${p.star}</span>` : ""}</span><span class="ds">${p.ds}</span><span class="pn">${pn}</span></button>`;
    }).join("");
    $("pipeBar").onclick = (e) => { const b = e.target.closest("[data-pipe]"); if (b) setPlanPipe(b.dataset.pipe); };
  }
  function planBadge(c) {
    if (!c) return "";
    if (c.state === "position") return `<span class="badge ${c.position.side === "LONG" ? "long" : "short"}">GIỮ ${c.position.side}</span>`;
    if (c.state === "pending") return `<span class="badge ${c.order.side === "BUY" ? "long" : "short"}">CHỜ ${c.order.side === "BUY" ? "MUA" : "BÁN"}</span>`;
    return `<span class="badge flat">—</span>`;
  }
  const EVVI = { order_issue: "Đặt lệnh limit", order_cancel: "Huỷ lệnh", order_expire: "Lệnh hết hạn", book_fill: "Khớp vào lệnh",
                 book_add: "Khớp nhồi thêm", book_reduce: "Khớp chốt bớt", book_close: "Đóng bằng limit", book_stop: "Chạm SL (market)",
                 book_tp: "Chạm TP (limit)", book_partial: "Chốt một phần", sl_move: "Dời SL" };
  function planHtml(sym, withTimeline = true) {
    const plan = state.live.plan, c = planOf(sym);
    if (!plan || !c) return `<p class="muted">Chưa có kế hoạch lệnh cho ${coin(sym)}.</p>`;
    let body;
    if (isMulti()) {  // one step list per sub-book that has a position / order; phases not started yet: their start time
      const ph = Object.fromEntries((plan.phases || []).map((p) => [p.phase, p]));
      const subs = subViews(sym), act = subs.filter(liveSub);
      body = (act.length ? act.map((u) => `<div class="phase-h">${phTag(u)}</div>` + planBody(sym, u, ph[u.phase]?.next_decision || plan.next_decision)).join("")
        : planBody(sym, { state: "flat" }, plan.next_decision))
        + phasesPending().map((p) => `<div class="phase-h">${phTag(p)} <span class="muted small">bắt đầu lúc ${dt(Date.parse(p.freeze))}</span></div>`).join("");
    } else body = planBody(sym, c, plan.next_decision);
    if (!withTimeline) return body;
    const evs = (plan.events || []).filter((e) => e.symbol === sym).slice(-6).reverse();
    return body + `<div class="timeline">${evs.map((e) => `<div><span class="muted">${dt(Date.parse(e.t))}</span>${e.phase != null && isMulti() ? " " + phTag({ phase: e.phase }) : ""} ${EVVI[e.kind] || e.kind}
        ${e.kind.startsWith("sl_") ? "" : (e.side === "buy" ? "mua" : "bán")} ${fmtPx(e.price)}${e.why ? ` <span class="muted">(${esc(e.why)})</span>` : ""}</div>`).join("") || '<div class="muted small">Chưa có sự kiện.</div>'}</div>`;
  }
  function planBody(sym, c, nextDecision) {  // the step-by-step text of one book (the single plan, or one sub-book of a multi-phase plan)
    let body;
    const C = coin(sym), px = state.live.prices[sym]?.c, step = (items) => `<ol class="steps">${items.map((x) => `<li>${x}</li>`).join("")}</ol>`;
    if (c.state === "pending") {
      const o = c.order, buy = o.side === "BUY", q = qty(sym, o.weight, o.price);
      const lossPct = Math.abs(o.sl_if_filled / o.price - 1), gainPct = Math.abs(o.tp_if_filled / o.price - 1);
      const dist = px ? ` <span class="muted">— cách giá hiện tại ${((o.price / px - 1) * 100).toFixed(2)}%</span>` : "";
      body = `<div class="act ${buy ? "long" : "short"}">ĐẶT LỆNH ${buy ? "MUA (LONG)" : "BÁN (SHORT)"} ${C}</div>` + step([
        `Đặt lệnh <b>LIMIT ${buy ? "MUA" : "BÁN"} ${q} ${C}</b> tại giá <b>${fmtPx(o.price)}</b> (≈ ${usdt(o.weight)} USDT, ${pct(o.weight)} vốn)${dist}`,
        `Gắn <b>Stop-loss</b> (Stop Market) tại <b class="down">${fmtPx(o.sl_if_filled)}</b> — nếu chạm, lỗ ≈ ${Math.round(o.weight * equity() * lossPct)} USDT`,
        `Gắn <b>Take-profit</b> (Limit) tại <b class="up">${fmtPx(o.tp_if_filled)}</b> — nếu chạm, lãi ≈ ${Math.round(o.weight * equity() * gainPct)} USDT`,
        `Nếu đến <b>${dt(Date.parse(o.valid_until))}</b> vẫn chưa khớp: <b>huỷ lệnh</b> (không đuổi giá bằng lệnh market)`,
      ]);
    } else if (c.state === "position") {
      const p = c.position, L = p.side === "LONG", q = qty(sym, p.weight, p.avg_entry);
      const slm = lastEvent(sym, ["sl_move"], c.phase);
      const u = px ? (L ? 1 : -1) * (px / p.avg_entry - 1) * 100 : p.upnl_pct;
      const items = [`Trên sàn phải đang có: <b>${p.side} ${q} ${C}</b> (giá vào TB ${fmtPx(p.avg_entry)}, ≈ ${usdt(p.weight)} USDT)`,
        `Lệnh <b>Stop-loss</b> (Stop Market) tại <b class="down">${fmtPx(p.sl)}</b>${p.break_even ? " — đã dời về hoà vốn" : ""}${recent(slm) ? ` <span class="warn">← vừa đổi lúc ${dt(Date.parse(slm.t))}, hãy sửa lệnh SL trên sàn</span>` : ""}`,
        `Lệnh <b>Take-profit</b> (Limit) tại <b class="up">${fmtPx(p.tp)}</b>`];
      if (c.order) {
        const o = c.order, kind = { add: "nhồi thêm", reduce: "chốt bớt", close: "đóng hết vị thế" }[o.kind] || o.kind;
        items.push(`<b>Việc mới:</b> đặt lệnh <b>LIMIT ${o.side === "BUY" ? "MUA" : "BÁN"}</b> tại <b>${fmtPx(o.price)}</b> để <b>${kind}</b>${o.amount ? ` (${pct(o.amount, 0)} vị thế)` : ""}; huỷ nếu đến ${dt(Date.parse(o.valid_until))} chưa khớp`);
      } else {
        items.push(`Ngoài ra <b>không cần làm gì</b> — cứ để SL/TP chạy tới quyết định kế tiếp (${dt(Date.parse(nextDecision))})`);
      }
      body = `<div class="act ${L ? "long" : "short"}">ĐANG GIỮ ${p.side} ${C} · lãi/lỗ ${sgn(u)}</div>` + step(items);
    } else {
      const cl = lastEvent(sym, ["book_close", "book_stop", "book_tp"], c.phase);
      body = `<div class="act flat">KHÔNG LÀM GÌ VỚI ${C}</div>` + step([
        `Pipeline không có lệnh nào cho ${C} lúc này.`,
        recent(cl) ? `Vị thế vừa ${{ book_close: "đóng bằng limit", book_stop: "chạm Stop-loss", book_tp: "chạm Take-profit" }[cl.kind]} tại ${fmtPx(cl.price)} — nếu trên sàn còn vị thế / lệnh ${C} thì đóng / huỷ.`
          : `Nếu trên sàn đang có lệnh chờ hoặc vị thế ${C} từ gợi ý cũ: huỷ / đóng để khớp với kế hoạch.`,
        `Kiểm tra lại ở quyết định kế tiếp: ${dt(Date.parse(nextDecision))}.`]);
    }
    return body;
  }
  function dipBlock(sym) {  // the dip ladder resting in the bar in progress (from the plan): what to have on the exchange now
    const c = planOf(sym), px = state.live.prices[sym]?.c, d = sortedDips(c?.dips || []), multi = isMulti();
    if (!d.length) return "";
    const now = Date.now(), stOf = (r) => {
      const from = Date.parse(r.active_from), until = Date.parse(r.active_until);
      return now < from ? `đặt lúc ${dt(from)}` : now > until ? "đã hết hạn" : `đang chờ tới ${dt(until)}`;
    };
    const status = multi ? "mỗi khung giờ một thang riêng" : stOf(d[0]);  // multi-phase: each sub-book's ladder has its own window
    const rows = d.map((r) => {
      const q = qty(sym, r.size_frac, r.buy_limit);
      const ag = [r.agent_size !== 1 ? `<span class="${r.agent_size > 1 ? "up" : "down"}">agent ×${r.agent_size}</span>` : "",
                  r.agent_tp !== 1 ? `TP ${r.agent_tp}σ` : ""].filter(Boolean).join(" · ");
      return `<tr class="${r.filled ? "dip-filled" : ""}"><td>${r.rung}σ${r.filled ? ' <span class="up" title="đã khớp">✓</span>' : ""}${multi ? `<span class="note">${phTag(r)} ${stOf(r)}</span>` : ""}</td>
        <td>${fmtPx(r.buy_limit)}${px ? `<span class="note">${((r.buy_limit / px - 1) * 100).toFixed(1)}%</span>` : ""}</td>
        <td class="up">${fmtPx(r.tp)}</td>
        <td class="down">${fmtPx(r.stop)}<span class="note">${r.stop_kind === "close5" ? "bot · nến 5m đóng" : "chạm"}${r.backstop ? ` · sàn ${fmtPx(r.backstop)}` : ""}</span></td>
        <td>${q}<span class="note">≈ ${usdt(r.size_frac)} USDT${ag ? " · " + ag : ""}</span></td></tr>`;
    }).join("");
    return `<details class="dip-d" open><summary>Lệnh chờ bắt đáy nến này <span class="muted small">(${status})</span></summary>
      <div class="tbl-scroll"><table class="tbl compact dip-tbl"><thead><tr><th>Bậc</th><th>Mua limit</th><th>TP</th><th>SL</th><th>Khối lượng</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <div class="muted small">${d.some((r) => r.stop_kind === "close5")
        ? 'Mỗi bậc: 1 lệnh limit mua riêng, kèm TP limit + SL sàn đặt sẵn; bot đóng lệnh nếu nến 5m đóng dưới "SL bot"; lệnh còn mở tới cuối nến thì đóng ở giá mở nến sau.'
        : "Mỗi bậc: 1 lệnh limit mua riêng (chế độ hedge / tài khoản phụ), gắn sẵn TP limit + SL chạm trên sàn; lệnh còn mở tới cuối nến thì đóng (market) ở lần kiểm tra kế tiếp."}</div></details>`;
  }
  function compactPlan(sym) {
    if (state.live.planLoading) return '<p class="muted">Đang tải kế hoạch lệnh…</p>';
    if (!state.live.plan) return `<p class="muted">Chưa có dữ liệu kế hoạch lệnh cho ${esc(PIPE_LABEL[planPipe()] || "pipeline này")}.</p>`;
    if (isMulti()) {  // one box per sub-book with a position / order (all flat: the single flat box) + phases not started yet
      const act = subViews(sym).filter(liveSub);
      const pend = phasesPending().map((p) => `<div class="muted small">${phTag(p)} bắt đầu lúc ${dt(Date.parse(p.freeze))}</div>`).join("");
      return (act.length ? act.map((u) => compactPlanCore(sym, u, phTag(u))).join("") : compactPlanCore(sym)) + pend + dipBlock(sym);
    }
    return compactPlanCore(sym) + dipBlock(sym);
  }
  function compactPlanCore(sym, c = planOf(sym), tag = "") {  // tag: the phase label of a sub-book (multi-phase plans)
    const px = state.live.prices[sym]?.c;
    const row = (k, v, d = "", cls = "") => `<div class="pb-row ${cls}"><span class="k">${k}</span><span class="v">${v}</span><span class="d">${d}</span></div>`;
    const rel = (x, base) => (base ? `${x >= base ? "+" : ""}${((x / base - 1) * 100).toFixed(2)}%` : "");
    if (!c || c.state === "flat") {
      return `<div class="plan-box flat"><div class="pb-head"><span class="act-badge flat">ĐỨNG NGOÀI</span></div>
        <div class="muted small">Không có lệnh cho ${coin(sym)} — không cần làm gì.</div></div>`;
    }
    if (c.state === "pending") {
      const o = c.order, buy = o.side === "BUY";
      return `<div class="plan-box ${buy ? "long" : "short"}"><div class="pb-head"><span class="act-badge ${buy ? "wait-long" : "wait-short"}">${buy ? "LONG" : "SHORT"}</span>${tag}
          <span class="muted small">lệnh limit chờ khớp · ${qty(sym, o.weight, o.price)} ${coin(sym)} (≈ ${usdt(o.weight)} USDT)</span></div>
        ${lotWarn(sym, o.weight, o.price)}
        ${row("Entry", fmtPx(o.price), px ? `cách giá ${((o.price / px - 1) * 100).toFixed(2)}%` : "")}
        ${row("Take-profit", fmtPx(o.tp_if_filled), rel(o.tp_if_filled, o.price), "tp")}
        ${row("Stop-loss", fmtPx(o.sl_if_filled), rel(o.sl_if_filled, o.price), "sl")}
        <div class="muted small">Huỷ nếu chưa khớp lúc ${dt(Date.parse(o.valid_until))}</div></div>`;
    }
    const p = c.position, L = p.side === "LONG", u = px ? (L ? 1 : -1) * (px / p.avg_entry - 1) * 100 : p.upnl_pct;
    return `<div class="plan-box ${L ? "long" : "short"}"><div class="pb-head"><span class="act-badge ${L ? "long" : "short"}">${p.side}</span>${tag}
        <span class="muted small">đang giữ ${qty(sym, p.weight, p.avg_entry)} ${coin(sym)} (≈ ${usdt(p.weight)} USDT) · P/L ${sgn(u)}</span></div>
      ${lotWarn(sym, p.weight, p.avg_entry)}
      ${row("Entry", fmtPx(p.avg_entry))}
      ${row("Take-profit", fmtPx(p.tp), rel(p.tp, p.avg_entry), "tp")}
      ${row("Stop-loss", fmtPx(p.sl), rel(p.sl, p.avg_entry) + (p.break_even ? " · hoà vốn" : ""), "sl")}
      <div class="muted small">${c.order ? `Lệnh chờ: limit ${c.order.side === "BUY" ? "mua" : "bán"} @ ${fmtPx(c.order.price)}` : "Không cần làm gì thêm"}</div></div>`;
  }
  function renderPlan() {
    if (!planPipe()) { $("planPanel").innerHTML = accessMessage(); return; }
    const sym = state.live.symbol, plan = state.live.plan;
    $("planPanel").innerHTML = `<div class="panel-h"><span>${coin(sym)} · ${PIPE_LABEL[planPipe()] || ""}</span>
      <span class="muted small">${plan?.next_decision ? "cập nhật kế tiếp " + dt(Date.parse(plan.next_decision)) : ""}</span></div>${compactPlan(sym)}
      <p class="fine">Hướng dẫn từng bước cho từng coin ở tab <a href="#todo">Pipeline</a>.</p>`;
  }
  // orders to place now for one coin, from the selected pipeline's plan: entry / add / reduce / close / stop move / dip limits
  function ordersFor(s) {
    const c = planOf(s); if (!c) return [];
    if (!isMulti()) return bookOrders(s, c).concat(dipOrders(c.dips));
    // multi-phase: every sub-book's book orders (phase order), then the dip rungs sorted by phase, rung; each tagged with its phase
    return subViews(s).flatMap((u) => bookOrders(s, u).map((o) => ({ ...o, ph: u })))
      .concat(dipOrders(sortedDips(c.dips || [])).map((o) => ({ ...o, ph: o.dip })));
  }
  function dipOrders(dips) {
    return (dips || []).filter((d) => !d.filled).map((d) => ({ kind: `Bắt đáy ${d.rung}σ`, side: "BUY", price: d.buy_limit, sl: d.stop, tp: d.tp,
      w: d.size_frac, until: d.active_until, dip: d }));
  }
  function bookOrders(s, c) {  // one book (the single plan, or one sub-book): entry / add / reduce / close / stop move
    const out = [];
    const add = (kind, side, price, sl, tp, w, until) => out.push({ kind, side, price, sl, tp, w, until });
    if (c.state === "pending") add("Vào lệnh xu hướng", c.order.side, c.order.price, c.order.sl_if_filled, c.order.tp_if_filled, c.order.weight, c.order.valid_until);
    if (c.state === "position" && c.order) add({ add: "Nhồi thêm", reduce: "Chốt bớt", close: "Đóng hết" }[c.order.kind] || c.order.kind,
      c.order.side, c.order.price, null, null, c.order.kind === "add" ? c.order.amount : null, c.order.valid_until);
    if (c.state === "position" && !c.order && recent(lastEvent(s, ["sl_move"], c.phase))) add("Sửa stop-loss", null, null, c.position.sl, null, null, null);
    return out;
  }
  const kv = (k, v, cls = "") => `<div><dt>${k}</dt><dd class="${cls}">${v}</dd></div>`;
  function orderRow(s, o) {
    const l = o.w != null && o.price ? lot(s, o.w, o.price) : null;
    const txt = o.side ? `${o.side} ${s} LIMIT ${fmtPx(o.price)}${l ? " qty " + l.txt : ""}${o.sl ? " SL " + fmtPx(o.sl) : ""}${o.tp ? " TP " + fmtPx(o.tp) : ""}`
      : `${s} SL ${fmtPx(o.sl)}`;
    const side = o.side ? `<span class="badge ${o.side === "BUY" ? "long" : "short"}">${o.side === "BUY" ? "MUA" : "BÁN"}</span>` : "";
    return `<div class="ord"><div class="ord-top"><span class="ord-kind">${esc(o.kind)}</span>${o.ph ? phTag(o.ph) : ""}${side}
        <button type="button" class="btn sm copy-btn" data-copy="${esc(txt)}" aria-label="Copy lệnh ${esc(o.kind)} ${coin(s)}">Copy</button></div>
      <dl class="kv">${kv("Giá limit", o.price ? fmtPx(o.price) : "—")}${kv("Khối lượng", l ? `${l.txt} ${coin(s)}` : "—")}
        ${kv("Stop-loss", o.sl ? fmtPx(o.sl) : "—", "down")}${kv("Take-profit", o.tp ? fmtPx(o.tp) : "—", "up")}</dl>
      ${o.until ? `<div class="ord-foot">Huỷ nếu chưa khớp lúc ${dt(Date.parse(o.until))}</div>` : ""}${l && !l.ok ? `<div class="ord-foot warn">Dưới mức tối thiểu của sàn (${l.min} ${coin(s)})</div>` : ""}</div>`;
  }
  function coinBadge(s) {
    const c = planOf(s);
    if (c?.state === "position") return `<span class="badge ${c.position.side === "LONG" ? "long" : "short"}">GIỮ ${c.position.side}</span>`;
    if (c?.state === "pending") return `<span class="badge ${c.order.side === "BUY" ? "long" : "short"}">CHỜ ${c.order.side === "BUY" ? "MUA" : "BÁN"}</span>`;
    if ((c?.dips || []).some((d) => !d.filled)) return '<span class="badge dip">CHỜ BẮT ĐÁY</span>';
    return '<span class="badge flat">ĐỨNG NGOÀI</span>';
  }
  function coinBody(s) {
    if (state.live.planLoading) return '<p class="muted">Đang tải kế hoạch lệnh…</p>';
    if (!state.live.plan) return `<p class="muted">Chưa có dữ liệu kế hoạch lệnh cho ${esc(PIPE_LABEL[planPipe()] || "pipeline này")}.</p>`;
    const c = planOf(s), px = state.live.prices[s]?.c, parts = [];
    const posHtml = (p, tag, id) => {
      const L = p.side === "LONG", u = px ? (L ? 1 : -1) * (px / p.avg_entry - 1) * 100 : p.upnl_pct;
      return `<div class="pos ${L ? "long" : "short"}"><div class="pos-h"><span>Vị thế đang giữ${tag ? " " + tag : ""}</span><span${id ? ` id="${id}"` : ""}>${sgn(u)}</span></div>
        <dl class="kv">${kv("Giá vào TB", fmtPx(p.avg_entry))}${kv("Khối lượng", `${qty(s, p.weight, p.avg_entry)} ${coin(s)}`)}
          ${kv("Stop-loss", fmtPx(p.sl) + (p.break_even ? " · hoà vốn" : ""), "down")}${kv("Take-profit", fmtPx(p.tp), "up")}</dl></div>`;
    };
    if (isMulti()) { for (const u of subViews(s)) if (u.state === "position" && u.position) parts.push(posHtml(u.position, phTag(u))); }
    else if (c?.state === "position") parts.push(posHtml(c.position, "", `cpl-${s}`));
    const ords = ordersFor(s);
    if (ords.length) parts.push(`<div class="ord-h">Lệnh cần đặt</div>` + ords.map((o) => orderRow(s, o)).join(""));
    else parts.push(`<p class="coin-idle">${c?.state === "position" ? "Không cần đặt thêm lệnh — giữ nguyên SL/TP." : "Không có lệnh mới cho coin này."}</p>`);
    return parts.join("");
  }
  function renderCards() {
    const el = $("todoCards"); if (!el) return;
    if (!planPipe()) { el.innerHTML = accessMessage(); return; }
    const plan = state.live.plan, st = plan?.freeze ? Date.parse(plan.freeze) : NaN;
    const anyStarted = !!plan?.multi_phase && (plan.phases || []).some((p) => p.started);  // multi-phase: cards once one sub-book runs
    if (!state.live.planLoading && st > Date.now() && !anyStarted) {  // a new paper pipeline before its first traded bar: no orders yet
      el.innerHTML = `<p class="note-bar"><b>${esc(PIPE_LABEL[planPipe()] || "")} chưa tới giờ bắt đầu</b>
        <span>Pipeline bắt đầu chạy paper lúc ${dt(st)}; lệnh đầu tiên có sau khi nến 4h đó đóng.</span></p>`;
      return;
    }
    const pend = plan?.multi_phase && !state.live.planLoading ? phasesPending() : [];
    el.innerHTML = (pend.length ? `<p class="note-bar"><b>${esc(PIPE_LABEL[planPipe()] || "")}: ${pend.length} khung giờ chưa tới giờ bắt đầu</b>
        ${pend.map((p) => `<span>${esc(p.label ?? phLabel(p.phase))}: bắt đầu lúc ${dt(Date.parse(p.freeze))}</span>`).join("")}</p>` : "") + SYMS.map((s) => {
      const p = state.live.prices[s];
      return `<article class="coin-card" id="card-${s}">
        <header class="coin-h"><span class="coin-name">${coin(s)}</span>
          <span class="coin-px"><span class="px" id="cpx-${s}">${p ? fmtPx(p.c) : ""}</span> <span class="small" id="cch-${s}">${p ? sgn((p.c / p.o - 1) * 100) : ""}</span></span>
          <span class="coin-badge">${coinBadge(s)}</span></header>
        <div class="coin-body" id="cbox-${s}">${coinBody(s)}</div>
        <details class="steps-d"><summary>Hướng dẫn từng bước</summary>${planHtml(s)}</details></article>`;
    }).join("");
    el.onclick = (e) => {
      const b = e.target.closest(".copy-btn"); if (!b) return;
      navigator.clipboard?.writeText(b.dataset.copy).then(() => toast("Đã copy: " + b.dataset.copy), () => toast(b.dataset.copy));
    };
  }



  function bookOf(sym) { return (state.live.latest?.books || []).find((b) => b.symbol === sym); }

  // account size (per viewer): turns the pipeline's fraction-of-equity weights into coin quantities
  function equity() { try { return Math.max(10, Number(localStorage.getItem("equityUsdt")) || 1000); } catch { return 1000; } }
  // Bybit USDT-perp lot rules (public instruments-info, 2026-09-29): minimum order qty = qty step; minimum notional 5 USDT
  const LOT = { BTCUSDT: [0.001, 3], ETHUSDT: [0.01, 2], SOLUSDT: [0.1, 1], BNBUSDT: [0.01, 2], XRPUSDT: [0.1, 1] };
  function lot(s, w, px) {  // quantity rounded down to the exchange step; ok = the exchange accepts it
    const [step, dec] = LOT[s] || [0.001, 3], want = w * equity() / px, q = Math.floor(want / step + 1e-9) * step;
    return { q, txt: q.toFixed(dec), ok: q >= step && q * px >= 5, min: step, minUsd: Math.max(5, step * px), dec };
  }
  const qty = (s, w, px) => lot(s, w, px).txt;
  function lotWarn(s, w, px) {
    const l = lot(s, w, px);
    return l.ok ? "" : `<div class="lot-warn">⚠ Vốn ${equity().toLocaleString("en-US")} USDT quá nhỏ cho lệnh này: sàn yêu cầu tối thiểu ${l.min} ${coin(s)} (≈ ${Math.ceil(l.minUsd)} USDT) — bỏ qua coin này hoặc tăng vốn.</div>`;
  }
  const usdt = (w) => Math.round(w * equity()).toLocaleString("en-US");
  function lastEvent(sym, kinds, phase) {  // phase: only that sub-book's events (multi-phase plans)
    return (state.live.plan?.events || []).filter((e) => e.symbol === sym && kinds.includes(e.kind) && (phase == null || !isMulti() || e.phase === phase)).slice(-1)[0];
  }
  const recent = (e) => e && Date.now() - Date.parse(e.t) < 4 * 3600 * 1000;
  function boardCells(s) {
    if (isMulti()) {  // one line per sub-book with a position / order, tagged with its phase
      const subs = subViews(s).filter(liveSub);
      if (subs.length) {
        const cells = subs.map((u) => [u, boardCellsOf(s, u)]);
        const col = (k) => cells.map(([u, b]) => `<div class="ph-line">${k === "act" ? phTag(u) : ""}${b[k] || "—"}</div>`).join("");
        return { act: col("act"), px: col("px"), sl: col("sl"), tp: col("tp"), pl: col("pl"), w: col("w") };
      }
    }
    return boardCellsOf(s, planOf(s));
  }
  function boardCellsOf(s, c) {  // one book (the single plan, or one sub-book)
    const px = state.live.prices[s]?.c;
    if (!c || c.state === "flat") {
      const cl = lastEvent(s, ["book_close", "book_stop", "book_tp"], c?.phase);
      const why = recent(cl) ? `<span class="note">vừa ${{ book_close: "đóng (limit)", book_stop: "chạm SL", book_tp: "chạm TP" }[cl.kind]} @ ${fmtPx(cl.price)}</span>` : "";
      return { act: `<span class="act-badge flat">KHÔNG LÀM GÌ</span>${why}`, px: "—", sl: "—", tp: "—", pl: "", w: "" };
    }
    if (c.state === "pending") {
      const o = c.order, buy = o.side === "BUY";
      const dist = px ? `<span class="note">cách giá ${((o.price / px - 1) * 100).toFixed(2)}%</span>` : "";
      return { act: `<span class="act-badge ${buy ? "wait-long" : "wait-short"}">ĐẶT LIMIT ${buy ? "MUA" : "BÁN"} ${qty(s, o.weight, o.price)} ${coin(s)}</span>${lot(s, o.weight, o.price).ok ? "" : '<span class="note warn">dưới mức tối thiểu của sàn</span>'}
                 <span class="note">kèm SL + TP, huỷ lúc ${dt(Date.parse(o.valid_until))} nếu chưa khớp</span>`,
               px: `${fmtPx(o.price)}${dist}`, sl: fmtPx(o.sl_if_filled), tp: fmtPx(o.tp_if_filled), pl: `<span class="muted">chưa khớp</span>`,
               w: `${usdt(o.weight)} USDT` };
    }
    const p = c.position, L = p.side === "LONG", k = L ? 1 : -1;
    const u = px ? k * (px / p.avg_entry - 1) * 100 : p.upnl_pct;
    const slm = lastEvent(s, ["sl_move"], c.phase);
    let todo = "không cần làm gì";
    if (c.order) todo = `đặt LIMIT ${c.order.side === "BUY" ? "MUA" : "BÁN"} @ ${fmtPx(c.order.price)} (${{ add: "nhồi thêm", reduce: "chốt bớt", close: "đóng hết" }[c.order.kind] || c.order.kind})`;
    else if (recent(slm)) todo = `sửa SL thành ${fmtPx(p.sl)}`;
    return { act: `<span class="act-badge ${L ? "long" : "short"}">GIỮ ${p.side} ${qty(s, p.weight, p.avg_entry)} ${coin(s)}</span><span class="note">${todo}</span>${lot(s, p.weight, p.avg_entry).ok ? "" : '<span class="note warn">dưới mức tối thiểu của sàn</span>'}`,
             px: fmtPx(p.avg_entry), sl: `${fmtPx(p.sl)}${p.break_even ? '<span class="note up">đã về hoà vốn</span>' : ""}`, tp: fmtPx(p.tp),
             pl: sgn(u), w: `${usdt(p.weight)} USDT` };
  }
  function wireEquity() {
    const el = $("eqInput"); if (!el || el.dataset.wired) return;
    el.dataset.wired = "1"; el.value = equity();
    el.onchange = () => { try { localStorage.setItem("equityUsdt", String(Math.max(10, Number(el.value) || 1000))); } catch { /* ignore */ }
      renderBoard(); renderCards(); renderPlan(); };
  }
  function renderBoard() {
    const el = $("board"); if (!el) return;
    if (!planPipe()) { el.innerHTML = ""; $("boardMeta").textContent = "Chưa có pipeline được mở quyền xem tín hiệu."; return; }
    wireEquity();
    if (el.hidden) {  // the pipeline tab shows cards only; keep the meta line
      const plan = state.live.plan;
      $("boardMeta").textContent = !plan?.coins ? `${PIPE_LABEL[planPipe()]} · chưa có kế hoạch lệnh (chờ chu kỳ 4h kế tiếp)`
        : `${PIPE_LABEL[planPipe()]} · kế hoạch cập nhật ${dt(Date.parse(plan.generated_at))} · quyết định kế tiếp ${dt(Date.parse(plan.next_decision))}`;
      return;
    }
    const rows = SYMS.map((s) => {
      const p = state.live.prices[s], b = boardCells(s);
      return `<tr data-sym="${s}"><td class="sym">${coin(s)}</td>
        <td class="px" id="b-px-${s}">${p ? fmtPx(p.c) : "…"}</td><td id="b-ch-${s}">${p ? sgn((p.c / p.o - 1) * 100) : ""}</td>
        <td>${b.act}</td><td class="m" id="b-en-${s}">${b.px}</td><td class="m down">${b.sl}</td><td class="m up">${b.tp}</td>
        <td id="b-pl-${s}">${b.pl}</td><td>${b.w}</td></tr>`;
    });
    el.innerHTML = `<thead><tr><th>Coin</th><th>Giá</th><th>24h</th><th>Việc cần làm</th><th>Giá vào / limit</th><th>Stop-loss</th>
      <th>Take-profit</th><th>Lãi/lỗ</th><th>Số tiền</th></tr></thead><tbody>${rows.join("")}</tbody>`;
    const plan = state.live.plan;
    const paperTxt = plan?.freeze && plan.net_return_pct != null
      ? ` · paper từ ${String(plan.freeze).slice(5, 10).split("-").reverse().join("/")}: ${plan.net_return_pct >= 0 ? "+" : ""}${Number(plan.net_return_pct).toFixed(2)}%` : "";
    $("boardMeta").textContent = !plan?.coins ? `${PIPE_LABEL[planPipe()]} · chưa có kế hoạch lệnh (chờ chu kỳ 4h kế tiếp)`
      : `${PIPE_LABEL[planPipe()]}${paperTxt} · cập nhật ${dt(Date.parse(plan.generated_at))} · quyết định kế tiếp ${dt(Date.parse(plan.next_decision))}`;
    el.onclick = (e) => { const tr = e.target.closest("tr[data-sym]"); if (tr) $("card-" + tr.dataset.sym)?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  }
  function shortAct(s) {
    const c = planOf(s);
    if (!c || c.state === "flat") return `<span class="act-badge flat">—</span>`;
    if (c.state === "pending") return `<span class="act-badge ${c.order.side === "BUY" ? "wait-long" : "wait-short"}">CHỜ ${c.order.side === "BUY" ? "MUA" : "BÁN"}</span>`;
    return `<span class="act-badge ${c.position.side === "LONG" ? "long" : "short"}">GIỮ ${c.position.side}</span>`;
  }
  function renderWatchlist() {
    const rows = SYMS.map((s) => {
      const p = state.live.prices[s];
      return `<tr data-sym="${s}" class="${s === state.live.symbol ? "sel" : ""}"><td class="sym">${coin(s)}<span class="muted small"> USDT.P</span></td>
        <td class="px" id="px-${s}">${p ? fmtPx(p.c) : "…"}</td><td id="ch-${s}">${p ? sgn((p.c / p.o - 1) * 100) : ""}</td><td>${shortAct(s)}</td></tr>`;
    });
    $("watchlist").innerHTML = `<thead><tr><th style="text-align:left">Coin</th><th>Giá</th><th>24h</th><th>Lệnh</th></tr></thead><tbody>${rows.join("")}</tbody>`;
    $("watchlist").onclick = (e) => {
      const tr = e.target.closest("tr[data-sym]"); if (!tr) return;
      state.live.symbol = tr.dataset.sym; store.set("liveSym", tr.dataset.sym);
      renderWatchlist(); renderPlan(); mountTv(tr.dataset.sym); updateTitle();
    };
  }
  // browser-tab title = live price of the coin being viewed (market / history page), e.g. "83,874.6"
  const DEFAULT_TITLE = document.title;
  function updateTitle() {
    const sym = state.view === "history" ? state.h.symbol : state.live.symbol, p = state.live.prices[sym];
    document.title = p ? fmtPx(p.c) : DEFAULT_TITLE;
  }

  function updateTickerCells(sym, prev) {
    const p = state.live.prices[sym];
    const flash = (el) => { if (prev != null && prev !== p.c) { el.classList.remove("flash-up", "flash-down"); void el.offsetWidth; el.classList.add(p.c > prev ? "flash-up" : "flash-down"); } };
    for (const [pxId, chId] of [["px-", "ch-"], ["b-px-", "b-ch-"]]) {
      const el = $(pxId + sym);
      if (el) { el.textContent = fmtPx(p.c); flash(el); const ch = $(chId + sym); if (ch) ch.innerHTML = sgn((p.c / p.o - 1) * 100); }
    }
    if ($("cpx-" + sym)) {
      $("cpx-" + sym).textContent = fmtPx(p.c); $("cch-" + sym).innerHTML = sgn((p.c / p.o - 1) * 100);
      const box = $("cbox-" + sym); if (box && !(state.live.boxT?.[sym] > Date.now() - 2000)) {  // at most every 2 s
        box.innerHTML = coinBody(sym); (state.live.boxT ||= {})[sym] = Date.now();
      }
    }
    if ($("b-pl-" + sym)) { const b = boardCells(sym); $("b-pl-" + sym).innerHTML = b.pl; $("b-en-" + sym).innerHTML = b.px; }
    if (sym === (state.view === "history" ? state.h.symbol : state.live.symbol)) updateTitle();
    if (sym === state.live.symbol) {
      updateLiveDistances();
      const pb = document.querySelector("#planPanel .plan-box");
      if (pb && state.view === "live" && !(state.live.pbT > Date.now() - 2000)) { renderPlan(); state.live.pbT = Date.now(); }
    }
  }

  function renderSignal() {
    const sym = state.live.symbol, run = state.live.latest?.run, b = bookOf(sym);
    if (!run || !b) { $("sigPanel").innerHTML = `<div class="panel-h"><span>Gợi ý hiện tại · ${coin(sym)}</span></div><p class="muted">Chưa có tín hiệu. Admin cần chạy pipeline.</p>`; return; }
    const flat = b.side === "FLAT" || !b.entry;
    const k = b.side === "LONG" ? 1 : -1;
    const slP = flat ? null : k * (b.sl / b.entry - 1), tpP = flat ? null : k * (b.tp / b.entry - 1);
    const until = run.decision_time + IV_MS["4h"];
    $("sigPanel").innerHTML = `
      <div class="sig-head"><div><div class="title">Tín hiệu pipeline · ${coin(sym)}</div><div class="muted small">vị thế mục tiêu (bản chỉnh liên tục ${esc(run.pipeline)}), để tham khảo</div></div>
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
      ${flat ? "" : confBlock(b.confidence)}
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

  function confLine(st, label) {
    if (!st) return "";
    return `<tr><td>${label}</td><td>${st.n}</td><td><b>${(100 * st.win_rate).toFixed(0)}%</b></td><td class="up">+${(st.avg_win_pct ?? 0).toFixed(1)}%</td>
      <td class="down">${(st.avg_loss_pct ?? 0).toFixed(1)}%</td><td>${sgn(st.avg_pct)}</td></tr>`;
  }
  function confBlock(level) { // historical win rate of orders opened at the same confidence level (walk-forward replay)
    const lv = state.live.conf?.levels?.[level];
    if (!lv) return "";
    return `<div class="conf"><div class="muted small">Lịch sử các lệnh cùng mức tin cậy "${esc(CONF[level] || level)}" (mô phỏng walk-forward, chưa trừ phí):</div>
      <table class="tbl compact"><thead><tr><th>Giai đoạn</th><th>Số lệnh</th><th>Thắng</th><th>TB thắng</th><th>TB thua</th><th>TB/lệnh</th></tr></thead>
      <tbody>${confLine(lv.dev, "Train / chọn model · 4 năm")}${confLine(lv.hidden, "Test · 1 năm")}</tbody></table>
      <div class="muted small">Lưu ý: nhãn tin cậy hiện tại chưa phân biệt tốt (97% lệnh là "Thấp"); đang nghiên cứu điểm tin cậy mới.</div></div>`;
  }

  function renderDips() {
    const sym = state.live.symbol;
    const rows = (state.live.latest?.sleeve || []).filter((r) => r.symbol === sym);
    // C4 / C5: the dip stop fires on a 5m CLOSE (bot) at 4 / 5 sigma, plus a native 8-sigma touch stop on the exchange
    const closeK = { v321: 4, v376: 4, v301: 4, v295: 4, v285: 4, v269: 4, v266: 5 }[planPipe()];
    const dsz = ["v295", "v301", "v321", "v376", "v340", "v342", "v362", "v367"].includes(planPipe()) ? (planOf(sym)?.dip_size || {}) : null;  // CS / G2: the agents' decision per rung
    const decOf = (r) => { if (!dsz) return null; const k = Object.keys(dsz).find((x) => Number(x) === Number(r.rung)); return k ? dsz[k] : null; };
    const mulOf = (r) => { const d = decOf(r); return d == null ? 1 : Number(typeof d === "object" ? d.size : d); };
    const tpOf = (r) => { const d = decOf(r); return d && typeof d === "object" ? Number(d.tp) : 1; };
    if (closeK) {
      const head = ["Bậc", "Mua limit", "TP", "SL nến 5m đóng", "SL sàn (đặt sẵn)", "Vốn"].concat(dsz ? ["Agent"] : []);
      table($("dipTbl"), head, rows.map((r) => {
        const s = r.buy_limit > 0 ? (r.buy_limit - r.sl) / (5 * r.buy_limit) : 0; // sigma from the advisor's 5-sigma stop
        const m = mulOf(r), tk = tpOf(r);
        const tpPx = tk !== 1 && s > 0 ? r.buy_limit * (1 + tk * s) : r.tp;  // G2: the take-profit agent's multiple of sigma
        return `<tr><td>${r.rung}σ</td><td>${fmtPx(r.buy_limit)}</td><td class="up">${fmtPx(tpPx)}${tk !== 1 ? ` <span class="muted small">(${tk}σ)</span>` : ""}</td>
        <td class="down">${fmtPx(r.buy_limit * (1 - closeK * s))}</td><td class="down">${fmtPx(r.buy_limit * (1 - 8 * s))}</td><td>${pct(r.size_frac * m)}</td>${
          dsz ? `<td class="${m > 1 ? "up" : m < 1 ? "down" : "muted"}">×${m}</td>` : ""}</tr>`;
      }), "Không có lệnh chờ");
    } else {
      table($("dipTbl"), ["Bậc", "Mua limit", "TP", "SL", "Vốn"], rows.map((r) => `<tr><td>${r.rung}σ</td><td>${fmtPx(r.buy_limit)}</td>
      <td class="up">${fmtPx(r.tp)}</td><td class="down">${fmtPx(r.sl)}</td><td>${pct(r.size_frac)}</td></tr>`), "Không có lệnh chờ");
    }
    const d = state.live.conf?.levels?.DIP;
    const note = $("dipNote") || Object.assign(document.createElement("div"), { id: "dipNote", className: "muted small" });
    note.innerHTML = d ? `Lịch sử lệnh dip: Win rate Train <b>${(100 * d.dev.win_rate).toFixed(0)}%</b> (${d.dev.n} lệnh, 4 năm) · Test <b>${(100 * d.hidden.win_rate).toFixed(0)}%</b> (${d.hidden.n} lệnh, 1 năm) · TB thắng +${d.dev.avg_win_pct.toFixed(2)}% / thua ${d.dev.avg_loss_pct.toFixed(2)}%` : "";
    $("dipTbl").after(note);
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
  const H = { chart: null, series: null, wSeries: null, prim: null, ws: null, candles: [], times: [], orders: [], pos: [],  // history chart
              posAt: [], fills: [], noOlder: false, loadingOlder: false, gen: 0 };

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
      if (!H.chart) return;
      const ts = H.chart.timeScale(), s = H.series;
      const vr = ts.getVisibleLogicalRange(); if (!vr) return;
      const lo = Math.max(0, Math.floor(vr.from) - 1), hi = Math.min(H.times.length - 1, Math.ceil(vr.to) + 1);
      const x0 = ts.logicalToCoordinate(lo), x1 = ts.logicalToCoordinate(lo + 1);
      const bs = x0 != null && x1 != null ? Math.max(x1 - x0, 0.5) : 6; // bar spacing in px
      const sel = H.orders.find((o) => o.id === state.h.selected);
      const inSel = (t) => sel && t >= Math.floor(sel.entry_t / IV_MS[state.h.interval]) * IV_MS[state.h.interval] &&
        (sel.exit_t == null || t <= sel.exit_t);
      target.useMediaCoordinateSpace(({ context: ctx }) => {
        // 1) the position actually held in each bar: average entry, and the stop-loss / take-profit in force for it
        if ($("tZone").checked) {
          for (let i = lo; i <= hi; i++) {
            const p = H.posAt[i]; if (!p || !p.held || p.avg_entry == null) continue;
            const x = ts.logicalToCoordinate(i); if (x == null) continue;
            const ye = s.priceToCoordinate(p.avg_entry), ysl = s.priceToCoordinate(p.pos_sl), ytp = s.priceToCoordinate(p.pos_tp);
            if (ye == null || ysl == null || ytp == null) continue;
            const hl = inSel(H.times[i]), L = x - bs / 2;
            ctx.fillStyle = hl ? "rgba(8,153,129,.26)" : "rgba(8,153,129,.09)"; ctx.fillRect(L, Math.min(ye, ytp), bs, Math.abs(ytp - ye));
            ctx.fillStyle = hl ? "rgba(242,54,69,.26)" : "rgba(242,54,69,.09)"; ctx.fillRect(L, Math.min(ye, ysl), bs, Math.abs(ysl - ye));
            ctx.fillStyle = p.held > 0 ? "rgba(8,153,129,.9)" : "rgba(242,54,69,.9)"; ctx.fillRect(L, ye - 0.75, bs, 1.5);
          }
        }
        // 2) every fill at its exact price: ▲ buy limit, ▼ sell limit, ✕ stop-loss, ● take-profit; dip bids in orange
        const tBook = $("tBook").checked, tDip = $("tDip").checked, minW = bs < 3 ? 0.03 : bs < 6 ? 0.01 : 0.002;
        const t0 = H.times[lo], t1 = H.times[hi] + IV_MS[state.h.interval];
        for (const f of H.fills) {
          if (f.t < t0 || f.t >= t1) continue;
          const dip = f.kind.startsWith("rung");
          if ((dip && !tDip) || (!dip && !tBook)) continue;
          const w = Math.abs(f.weight || 0);
          if (f.kind === "book_fill" && w < minW && !inSel(f.t)) continue;
          const i = idxAt(f.t), x = ts.logicalToCoordinate(i), y = s.priceToCoordinate(f.price);
          if (x == null || y == null) continue;
          const r = Math.min(8, 3 + 14 * Math.sqrt(w));
          const col = dip ? "#ff9800" : f.side === "buy" ? "#26d9b0" : "#ff5b6b";
          ctx.fillStyle = col; ctx.strokeStyle = "#0b0e14"; ctx.lineWidth = 1;
          ctx.beginPath();
          if (f.kind === "book_stop" || f.kind === "rung_sl") {
            ctx.strokeStyle = "#ff5b6b"; ctx.lineWidth = 2;
            ctx.moveTo(x - 5, y - 5); ctx.lineTo(x + 5, y + 5); ctx.moveTo(x + 5, y - 5); ctx.lineTo(x - 5, y + 5); ctx.stroke(); continue;
          }
          if (f.kind === "book_tp" || f.kind === "rung_tp" || f.kind === "rung_timeout") {
            ctx.fillStyle = f.kind === "rung_timeout" ? "#9598a1" : dip ? "#ff9800" : "#26d9b0";
            ctx.arc(x, y, f.kind === "book_tp" ? 5 : 3, 0, 2 * Math.PI); ctx.fill(); ctx.stroke(); continue;
          }
          if (f.side === "buy") { ctx.moveTo(x, y); ctx.lineTo(x - r, y + r * 1.4); ctx.lineTo(x + r, y + r * 1.4); }
          else { ctx.moveTo(x, y); ctx.lineTo(x - r, y - r * 1.4); ctx.lineTo(x + r, y - r * 1.4); }
          ctx.closePath(); ctx.fill(); ctx.stroke();
        }
        // 3) label of the selected order
        if (sel) {
          const i = idxAt(sel.entry_t), x = ts.logicalToCoordinate(i), y = s.priceToCoordinate(sel.entry_px);
          if (x != null && y != null) {
            const txt = `${sel.side} · khớp đầu ${fmtPx(sel.entry_px)} · ${sel.fills} lần khớp · ${sel.pnl_pct == null ? "đang mở" : (sel.pnl_pct >= 0 ? "+" : "") + sel.pnl_pct.toFixed(2) + "%"} (${REASON[sel.exit_reason] || sel.exit_reason})`;
            ctx.font = "600 11px Inter, sans-serif";
            const tw = ctx.measureText(txt).width + 12, yy = sel.side === "LONG" ? y + 16 : y - 34;
            ctx.fillStyle = "rgba(30,34,45,.94)"; ctx.fillRect(x - 6, yy, tw, 18);
            ctx.fillStyle = sel.pnl_pct == null ? "#d1d4dc" : sel.pnl_pct >= 0 ? "#26d9b0" : "#ff5b6b"; ctx.fillText(txt, x, yy + 13);
          }
        }
      });
    }
  }

  let histInit = false;
  async function initHistory() {
    await loadEvidence();
    if (!visiblePipes().length) { $("hPipe").innerHTML = accessMessage(); return; }
    seg($("hPipe"), visiblePipes().map((p) => p.v), planPipe(), (v) => { setPlanPipe(v); },
      (v) => PIPES.find((p) => p.v === v).nm);
    if (!histInit) {
      histInit = true;
      seg($("hSymbols"), SYMS, state.h.symbol, (v) => { state.h.symbol = v; store.set("hSym", v); loadHistory(); updateTitle(); }, coin);
      seg($("hIntervals"), ["1h", "4h", "1d"], state.h.interval, (v) => { state.h.interval = v; store.set("hIv", v); loadHistory(); }, (x) => IV_LABEL[x]);
      seg($("hRanges"), Object.keys(RANGES), state.h.range, (v) => { state.h.range = v; store.set("hRange2", v); applyRange(); });
      seg($("oKind"), ["all", "book", "dip"], state.h.kind, (v) => { state.h.kind = v; renderOrders(); },
        (x) => ({ all: "Tất cả", book: "Lệnh 4h", dip: "Dip" })[x]);
      seg($("oResult"), ["all", "win", "loss", "open"], state.h.result, (v) => { state.h.result = v; renderOrders(); },
        (x) => ({ all: "Mọi kết quả", win: "Lãi", loss: "Lỗ", open: "Đang mở" })[x]);
      for (const id of ["tBook", "tDip"]) $(id).onchange = () => { setMarkers(); H.prim && H.prim.update(); };
      $("tZone").onchange = () => H.prim && H.prim.update();
      $("tWeight").onchange = () => H.wSeries && H.wSeries.applyOptions({ visible: $("tWeight").checked });
      $("zIn").onclick = () => zoom(0.6); $("zOut").onclick = () => zoom(1 / 0.6);
      $("zFit").onclick = () => H.chart && H.times.length && showRange(0);
      $("zNow").onclick = () => {  // back to the latest candle, same zoom, with the empty third on the right
        if (!H.chart || !H.times.length) return;
        const r = H.chart.timeScale().getVisibleLogicalRange(); if (!r) return;
        const w = r.to - r.from, last = H.times.length - 1;
        H.chart.timeScale().setVisibleLogicalRange({ from: last + w / 3 - w, to: last + w / 3 });
      };
      initResizer();
      loadHistory();
    } else { loadHistory(); }
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

  // candles take 2/3 of the chart width and the right third stays empty (like TradingView), so the latest candles and orders are easy to see
  function showRange(from) {
    const last = H.times.length - 1, span = Math.max(12, last - from);
    H.chart.timeScale().setVisibleLogicalRange({ from, to: last + span * 0.5 });
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
      const [cand, orders, pos, fills] = await Promise.all([
        api(`/api/candles?symbol=${symbol}&interval=${interval}&limit=${FIRST_LOAD[interval]}`),
        histBoth("orders", symbol),
        histBoth("positions", symbol),
        histBoth("trades", symbol),
      ]);
      if (gen !== H.gen) return;
      if (H.chart) { H.chart.remove(); H.chart = null; }
      if (H.ws) { H.ws.close(); H.ws = null; }
      H.candles = cand; H.times = cand.map((c) => c.t); H.orders = orders.slice().reverse(); H.pos = pos; H.fills = fills; H.noOlder = false;
      const c = H.chart = makeChart($("hChart"));
      H.series = c.addCandlestickSeries({ upColor: "#089981", downColor: "#f23645", borderVisible: false, wickUpColor: "#089981",
        wickDownColor: "#f23645", priceFormat: { type: "custom", formatter: fmtPx, minMove: 0.00001 },
        autoscaleInfoProvider: (orig) => {  // keep the SL / TP of every position in view inside the price scale
          const r = orig(); if (!r || !$("tZone").checked || !H.chart) return r;
          const vr = H.chart.timeScale().getVisibleLogicalRange(); if (!vr) return r;
          let lo = r.priceRange.minValue, hi = r.priceRange.maxValue;
          for (let i = Math.max(0, Math.floor(vr.from)); i <= Math.min(H.posAt.length - 1, Math.ceil(vr.to)); i++) {
            const q = H.posAt[i]; if (!q || !q.held || q.pos_sl == null || q.pos_tp == null) continue;
            lo = Math.min(lo, q.pos_sl, q.pos_tp); hi = Math.max(hi, q.pos_sl, q.pos_tp);
          }
          return { priceRange: { minValue: lo, maxValue: hi }, margins: r.margins };
        } });
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
    if (!days) { showRange(0); return; }
    const from = lastT - days * 86400e3;
    if (from < H.times[0] && !H.noOlder) await loadOlder(from);
    const i = Math.max(0, idxAt(from));
    showRange(i);
  }

  function setWeights() { // position record in force for every candle (4h decision rows mapped onto 1h / 1D candles)
    const pos = H.pos, daily = state.h.interval === "1d"; let j = -1;
    H.posAt = H.candles.map((k) => {
      while (j + 1 < pos.length && pos[j + 1].t <= k.t + (daily ? IV_MS["1d"] - IV_MS["4h"] : 0)) j++;
      return j >= 0 && k.t - pos[j].t < IV_MS[daily ? "1d" : "4h"] ? pos[j] : null;
    });
    if (!H.wSeries) return;
    H.wSeries.setData(H.candles.map((k, i) => {
      const p = H.posAt[i], v = p ? (p.held ?? p.weight) : 0;
      return { time: toChart(k.t), value: v * 100, color: v < 0 ? "rgba(242,54,69,.45)" : "rgba(41,98,255,.45)" };
    }));
  }

  function setMarkers() { // only the selected order; the primitive draws every fill at its exact price
    if (!H.series) return;
    const o = H.orders.find((x) => x.id === state.h.selected), out = [];
    if (o) {
      const L = o.side === "LONG", i = idxAt(o.entry_t);
      if (i >= 0) out.push({ time: toChart(H.times[i]), position: L ? "belowBar" : "aboveBar", color: L ? "#26d9b0" : "#ff5b6b",
        shape: L ? "arrowUp" : "arrowDown", text: `Mở ${o.side}` });
      const k = o.exit_t ? idxAt(o.exit_t) : -1;
      if (k >= 0) out.push({ time: toChart(H.times[k]), position: L ? "aboveBar" : "belowBar", color: o.pnl_pct >= 0 ? "#26d9b0" : "#ff5b6b",
        shape: "circle", text: `${REASON[o.exit_reason] || o.exit_reason} ${o.pnl_pct >= 0 ? "+" : ""}${o.pnl_pct.toFixed(2)}%` });
      out.sort((a, b) => a.time - b.time);
    }
    H.series.setMarkers(out);
  }

  const KINDVI = { book_fill: "khớp lệnh vào (limit)", book_stop: "chạm stop-loss", book_tp: "chạm take-profit", book_add: "nhồi thêm (limit)",
                  book_reduce: "chốt bớt (limit)", book_close: "đóng bằng limit", book_partial: "chốt một phần", sl_move: "dời SL",
                  rung_fill: "khớp dip", rung_tp: "TP dip", rung_sl: "SL dip", rung_timeout: "đóng dip hết giờ" };
  function onCrosshair(p) {
    const { symbol, interval } = state.h;
    let i = H.times.length - 1;
    if (p && p.time) i = idxAt(fromChart(p.time));
    const k = H.candles[i];
    if (!k) { $("hLegend").innerHTML = ""; return; }
    const ch = (k.c / k.o - 1) * 100, cls = ch >= 0 ? "up" : "down";
    const ps = H.posAt[i], step = IV_MS[interval];
    const inBar = H.fills.filter((f) => f.t >= k.t && f.t < k.t + step && !["order_issue", "order_cancel", "order_expire"].includes(f.kind)).slice(0, 4);
    const fl = inBar.map((f) => `<span class="${f.side === "buy" ? "up" : "down"}">${f.side === "buy" ? "▲ mua" : "▼ bán"}</span> ${KINDVI[f.kind] || f.kind} ${fmtPx(f.price)}` +
      (f.kind === "book_fill" ? ` <span class="muted">(${pct(Math.abs(f.weight))} vốn, ${((f.price / k.o - 1) * 100).toFixed(2)}% so với giá mở)</span>` : "")).join(" · ");
    $("hLegend").innerHTML = `<div class="l1">${coin(symbol)}USDT.P · ${IV_LABEL[interval]} · Binance <span class="muted small">${dt(k.t)}</span></div>
      <div class="ohlc">O <b class="${cls}">${fmtPx(k.o)}</b> H <b class="${cls}">${fmtPx(k.h)}</b> L <b class="${cls}">${fmtPx(k.l)}</b> C <b class="${cls}">${fmtPx(k.c)}</b> <b class="${cls}">${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%</b></div>
      <div>${ps && ps.held ? `${sideBadge(ps.held > 0 ? "LONG" : "SHORT", ps.held)} <span class="muted">giá vào TB ${fmtPx(ps.avg_entry)} · SL ${fmtPx(ps.pos_sl)} · TP ${fmtPx(ps.pos_tp)} · mục tiêu ${pct(ps.weight)}</span>`
        : '<span class="badge flat">Không giữ vị thế 4h</span>'}</div>
      ${fl ? `<div>${fl}</div>` : ""}`;
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
      <span>Chạm TP / SL <b>${list.filter((o) => o.exit_reason === "TP").length} / ${list.filter((o) => o.exit_reason === "SL" || o.exit_reason === "SL hoà vốn").length}</b></span>
      <span>Từ <b>${first ? dt(first) : "—"}</b></span>`;
    const rows = list.slice().reverse().slice(0, 800).map((o) => `<tr class="click ${o.id === state.h.selected ? "sel" : ""}" data-id="${o.id}">
      <td>${dt(o.entry_t)}</td><td>${o.kind === "dip" ? '<span class="badge dip">MUA DIP</span>' : "Lệnh 4h"}</td><td>${sideBadge(o.side)}</td>
      <td>${fmtPx(o.avg_px ?? o.entry_px)}${(o.fills ?? 1) > 1 ? `<span class="muted small"> (khớp đầu ${fmtPx(o.entry_px)})</span>` : ""}</td>
      <td>${Math.max(0, (o.fills ?? 1) - 1) || "—"}</td>
      <td class="down">${fmtPx(o.sl)}</td><td class="up">${fmtPx(o.tp)}</td><td>${pct(o.size)}</td>
      <td>${o.exit_t ? dt(o.exit_t) : "—"}</td><td>${fmtPx(o.exit_px)}</td>
      <td>${esc(REASON[o.exit_reason] || o.exit_reason || "")}</td><td>${o.pnl_pct == null ? (o.exit_reason === "Đang mở" ? '<span class="muted">đang mở</span>' : "—") : sgn(o.pnl_pct)}</td></tr>`);
    table($("ordersTbl"), ["Vào lệnh lúc", "Loại", "Hướng", "Giá vào", "Nhồi thêm (lần)", "Stop-loss", "Take-profit",
      "Vốn dùng", "Thoát lúc", "Giá thoát", "Lý do thoát", "Kết quả (sau phí)"], rows, "Không có lệnh");
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
    const gen = ++perfGeneration;
    try {
      await loadEvidence();
      if (gen !== perfGeneration) return;
      if (!visiblePipes().length) { $("pPipe").innerHTML = accessMessage(); return; }
      const pipe = planPipe(), src = `tm_${pipe}`, nm = PIPES.find((p) => p.v === pipe).nm;
      seg($("pPipe"), visiblePipes().map((p) => p.v), pipe, (v) => { setPlanPipe(v); },
        (v) => PIPES.find((p) => p.v === v).nm + " — " + PIPES.find((p) => p.v === v).ds);
      const [ov, wfEq, st] = await Promise.all([api(`/api/overview?pipeline=${pipe}`), api(`/api/equity?source=${src}&points=3000`),
        api(`/api/orders/stats?source=${src}`)]);
      if (gen !== perfGeneration || pipe !== planPipe() || !state.user) return;
      const wf = ov.walkforward || {}, plan = ov.plan || {};
      $("perfKpis").innerHTML = [
        [`${nm}: mô phỏng toàn bộ 5 năm`, wf.monthly_5y, "%/tháng (bình quân theo lãi kép)"], ["Train / chọn model · 4 năm", wf.monthly_dev4, "%/tháng"],
        ["Test · 1 năm", wf.monthly_last_year, "%/tháng"], ["Max DD", wf.gate_dd, "% (mức lớn hơn: nến 4h / từng phút)"],
        ["Số năm thua lỗ", wf.losing_years, "năm"],
      ].map(([k, v, s]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${esc(v ?? "—")}</div><div class="s">${esc(s)}</div></div>`).join("");
      table($("yearTbl"), ["Năm / giai đoạn", "Lợi nhuận năm", "%/tháng", "DD (từng phút)"],
        (wf.yearly || []).map(([a, net, dd], i, all) => `<tr><td>${esc(String(a).slice(0, 7))} → ${+String(a).slice(0, 4) + 1}${String(a).slice(4, 7)} <span class="pill">${i === all.length - 1 ? "Test" : "Train / chọn model"}</span></td>
          <td>${sgn(net, 1)}</td><td>${sgn((Math.pow(1 + net / 100, 1 / 12) - 1) * 100)}</td><td>${esc(dd)}%</td></tr>`));
      const by = {};
      for (const r of st) {
        const k = r.symbol + "|" + r.kind; const a = by[k] || (by[k] = { symbol: r.symbol, kind: r.kind, n: 0, w: 0, s: 0, tp: 0, sl: 0, nd: 0 });
        a.n += r.n; if (r.avg_pnl != null) { a.nd += r.n; a.w += r.win * r.n; a.s += r.avg_pnl * r.n; }
        if (r.exit_reason === "TP") a.tp += r.n; if (r.exit_reason === "SL" || r.exit_reason === "SL hoà vốn") a.sl += r.n;
      }
      table($("coinTbl"), ["Coin", "Loại", "Số lệnh", "Tỷ lệ thắng", "TB/lệnh (sau phí)", "Chạm TP", "Chạm SL"], Object.values(by)
        .sort((a, b) => a.kind.localeCompare(b.kind) || a.symbol.localeCompare(b.symbol))
        .map((a) => `<tr><td>${coin(a.symbol)}</td><td>${a.kind === "dip" ? '<span class="badge dip">MUA DIP</span>' : "Lệnh 4h"}</td><td>${a.n}</td>
          <td>${a.nd ? (100 * a.w / a.nd).toFixed(1) + "%" : "—"}</td><td>${a.nd ? sgn(a.s / a.nd) : "—"}</td><td>${a.tp}</td><td>${a.sl}</td></tr>`));
      drawLine("wf", $("wfChart"), wfEq, "#2962ff", true);
      const curve = (plan.equity_curve || []).map(([t, e]) => ({ t: Date.parse(t) + 4 * 3600 * 1000, equity: e }));
      drawLine("fw", $("fwChart"), curve, "#089981", false);
      $("fwSummary").innerHTML = plan.freeze ? `<dl class="kv">
        <dt>Pipeline</dt><dd>${esc(plan.pipeline || nm)}</dd>
        <dt>Bắt đầu paper</dt><dd>${esc(String(plan.freeze).slice(0, 16))} UTC</dd>
        <dt>Cập nhật</dt><dd>${dt(Date.parse(plan.generated_at))}</dd>
        <dt>Lợi nhuận ròng</dt><dd>${sgn(plan.net_return_pct)}</dd>
        <dt>Số nến 4h đã chạy</dt><dd>${curve.length}</dd></dl>
        <p class="fine">Paper trading tiến cứu: dữ liệu sau thời điểm đóng băng mô hình, là bằng chứng sạch duy nhất (mô hình chưa từng thấy).
          Còn quá ít nến để kết luận.</p>` : `<p class="muted">Chưa có dữ liệu paper trading.</p>`;
    } catch (e) { if (gen === perfGeneration) toast(e.message); }
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
    if (state.user?.role !== "admin") return;
    loadPipelineSettings();
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

  let pipelineDraft = null;
  async function loadPipelineSettings() {
    try { pipelineDraft = await api("/api/admin/pipelines"); renderPipelineSettings(); }
    catch (e) { toast(e.message); }
  }
  function renderPipelineSettings() {
    const draft = pipelineDraft;
    $("pipelineMode").textContent = draft.automatic ? "Thứ tự tự động theo kết quả đánh giá" : "Thứ tự do admin sắp xếp";
    table($("pipelineSettingsTbl"), ["Vị trí", "Pipeline", "Đổi thứ tự", "Quyền xem tín hiệu"], draft.order.map((p, i) => `<tr>
      <td>${i + 1}</td><td><b>${esc(PIPE_LABEL[p])}</b><span class="note">${esc(PIPES.find((x) => x.v === p).ds)}</span></td>
      <td><button class="btn sm" data-move="${i}" data-delta="-1" aria-label="Đưa ${esc(PIPE_LABEL[p])} lên" ${i === 0 ? "disabled" : ""}>↑</button>
        <button class="btn sm" data-move="${i}" data-delta="1" aria-label="Đưa ${esc(PIPE_LABEL[p])} xuống" ${i === draft.order.length - 1 ? "disabled" : ""}>↓</button></td>
      <td>${pipeOf(p)?.product === "bot" ? '<span class="muted small">Tab Bot: không khóa, chỉ tài khoản được cấp quyền Bot</span>'
        : `<button class="btn sm" data-lock="${p}" aria-pressed="${draft.locked[p]}">${draft.locked[p] ? "🔒 Đang khóa · Mở khóa" : "Đang mở · Khóa tín hiệu"}</button>`}</td></tr>`));
    $("pipelineSettingsTbl").onclick = (e) => {
      const lock = e.target.closest("[data-lock]"), move = e.target.closest("[data-move]");
      if (lock) draft.locked[lock.dataset.lock] = !draft.locked[lock.dataset.lock];
      else if (move) {
        const i = Number(move.dataset.move), next = i + Number(move.dataset.delta);
        if (next < 0 || next >= draft.order.length) return;
        [draft.order[i], draft.order[next]] = [draft.order[next], draft.order[i]]; draft.automatic = false;
      } else return;
      renderPipelineSettings(); $("pipelineSaveStatus").textContent = "Có thay đổi chưa lưu.";
    };
    $("reloadPipelineSettings").onclick = async () => { await loadPipelineSettings(); $("pipelineSaveStatus").textContent = "Đã tải lại cấu hình."; };
    $("autoPipelineOrder").onclick = async () => {
      try {
        const current = await api("/api/pipelines_summary");
        draft.order = Object.keys(current).sort((a, b) => {
          const x = current[a].walkforward, y = current[b].walkforward;
          return y.monthly_last_year - x.monthly_last_year || x.gate_dd - y.gate_dd || y.win_hidden - x.win_hidden || a.localeCompare(b);
        });
        draft.automatic = true; renderPipelineSettings(); $("pipelineSaveStatus").textContent = "Thứ tự tự động; trạng thái khóa được giữ nguyên. Bấm Lưu để áp dụng.";
      } catch (e) { toast(e.message); }
    };
    $("savePipelineSettings").onclick = async () => {
      const button = $("savePipelineSettings"); button.disabled = true;
      try {
        pipelineDraft = await api("/api/admin/pipelines", { method: "POST", body: {
          order: draft.automatic ? null : draft.order, locked: draft.locked, revision: draft.revision,
        } });
        renderPipelineSettings(); await loadEvidence();
        $("pipelineSaveStatus").textContent = "Đã lưu. Quyền xem có hiệu lực ngay; thứ tự áp dụng từ lượt chạy tiếp theo.";
      } catch (e) { $("pipelineSaveStatus").textContent = e.message; }
      finally { button.disabled = false; }
    };
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
      table($("usersTbl"), ["Email", "Tên", "Quyền", "Cấp riêng (pipeline MANUAL / tab Bot)", "Lần cuối", ""], users.map((u) => {
        const admin = u.role === "admin";
        const grants = admin ? "Tất cả pipeline + tab Bot" : PIPES.filter((p) => p.product === "manual").map(p => `<label class="grant-choice"><input type="checkbox" data-grant="${esc(p.v)}" ${u.granted_pipelines?.includes(p.v) ? "checked" : ""}>${esc(p.nm)}</label>`).join("")
          + `<label class="grant-choice bot-grant"><input type="checkbox" data-grant="bot" ${u.granted_pipelines?.includes("bot") ? "checked" : ""}>Tab Bot</label>`
          + `<button class="btn sm" data-save-grants="${esc(u.email)}">Lưu quyền</button>`;
        return `<tr><td>${esc(u.email)}</td><td>${esc(u.name || "")}</td><td>${admin ? "Admin" : u.approved ? "Người xem" : u.access_revoked ? "Đã thu hồi" : "Chờ duyệt"}</td><td>${grants}</td>
          <td>${dt(u.last_seen)}</td><td>${admin ? "" : `<button class="btn sm" data-email="${esc(u.email)}" data-ap="${u.approved ? 0 : 1}">${u.approved ? "Thu hồi" : u.access_revoked ? "Khôi phục" : "Duyệt"}</button>`}</td></tr>`;
      }));
      $("usersTbl").onclick = async (e) => {
        const save = e.target.closest("button[data-save-grants]");
        if (save) {
          save.disabled = true;
          const pipelines = Array.from(save.closest("tr").querySelectorAll("input[data-grant]:checked"), input => input.dataset.grant);
          try {
            await api("/api/admin/users", { method: "POST", body: { email: save.dataset.saveGrants, pipelines } });
            toast("Đã lưu quyền pipeline cho " + save.dataset.saveGrants); await loadUsers();
          } catch (err) { toast(err.message); }
          finally { save.disabled = false; }
          return;
        }
        const b = e.target.closest("button[data-email]"); if (!b) return;
        try { await api("/api/admin/users", { method: "POST", body: { email: b.dataset.email, approved: b.dataset.ap === "1" } }); loadUsers(); }
        catch (err) { toast(err.message); }
      };
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------------ boot
  setInterval(() => { if (state.view === "live" && state.user && state.user.role !== "pending" && !document.hidden) loadLive(); }, 120000);
  setInterval(async () => {
    if (!state.user || document.hidden) return;
    try { await syncAccountAccess(); } catch (e) { toast(e.message); return; }
    if (!state.user || state.user.role === "pending") return;
    const previous = JSON.stringify(state.user.allowed_pipelines);
    await loadEvidence();
    if (state.user && previous !== JSON.stringify(state.user.allowed_pipelines)) route();
  }, 60000);

  async function boot() {
    // Remove credentials persisted by older frontend versions.
    try { localStorage.removeItem("aal_token"); localStorage.removeItem("aal_session"); } catch { /* private mode */ }
    try {
      await refreshSession(); enter(); return;
    } catch { /* no valid cookie: local admin or Google sign-in */ }
    try {
      state.user = await api("/api/auth/me"); enter(); return;
    } catch { /* not local */ }
    showOnly("login");
    initGsi();
  }
  boot();
})();
