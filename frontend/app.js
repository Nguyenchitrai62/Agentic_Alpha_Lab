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
    h: { symbol: store.get("hSym", "BTCUSDT"), interval: store.get("hIv", "4h"), range: store.get("hRange2", "3Th"),
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
  const REASON = { TP: "Chạm TP", SL: "Chạm SL", "SL hoà vốn": "SL hoà vốn", "Đóng limit": "Đóng bằng limit", "Hết giờ": "Hết giờ (dip)", "Hết dữ liệu mô phỏng": "Hết dữ liệu mô phỏng (23/09)",
                  "Rebalance về 0": "Đóng (rebalance)", "Đảo chiều": "Đảo chiều", "Đang mở": "Đang mở", "Hết 4h (market)": "Hết 4h" };
  const histSource = () => `tm_${state.h.pipe || "v285"}`;
  // walk-forward replay (until the research data end) + the prospective paper window (since the freeze), oldest first per endpoint order
  async function histBoth(kind, symbol) {
    const pipe = state.h.pipe || "v285";
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
    let v = (location.hash || "#todo").slice(1);
    if (!["todo", "live", "history", "perf", "admin"].includes(v) || (v === "admin" && state.user.role !== "admin")) v = "todo";
    state.view = v;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    showOnly(v);
    ({ todo: loadTodo, live: loadLive, history: initHistory, perf: loadPerf, admin: loadAdmin })[v]();
    updateTitle();
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
    [state.live.latest, state.live.plan] = await Promise.all([api("/api/signals/latest?source=live"),
      api(`/api/trade_plan?pipeline=${planPipe()}`).catch(() => null)]);
    if (!state.live.conf) state.live.conf = await api("/api/confidence").catch(() => null);
    // paper results of the four pipelines side by side (prospective evidence)
    state.live.paper = await Promise.all(PIPES.map((p) => p.v).map((v) =>
      api(`/api/trade_plan?pipeline=${v}`).then((pl) => [v, pl]).catch(() => [v, null])));
  }
  async function loadLive() {
    mountTv(state.live.symbol);
    try {
      await loadPlans();
      renderWatchlist(); renderPlan(); renderDips(); loadRecent(); updateTitle();
    } catch (e) { toast(e.message); }
  }
  async function renderPipeStatus() {
    const el = $("pipeStatus"); if (!el) return;
    try {
      const h = await api("/health"), c = h.last_cycle, ok = c && c.status === "done";
      el.innerHTML = `<span><i class="dot ${ok ? "" : "bad"}"></i>Pipeline tự chạy mỗi 4h (1 phút sau khi nến 4h đóng) · lệnh cập nhật lại mỗi 15 phút</span>
        <span>Lần chạy gần nhất: <b>${c ? dt(c.started_at) : "—"}</b> (${c ? (ok ? "xong" : c.status) : "—"})</span>
        <span>Lần tới: <b>${h.next_cycle_utc ? dt(Date.parse(h.next_cycle_utc)) : "—"}</b></span>`;
    } catch (e) { el.textContent = ""; }
  }
  // ---- evidence table: the walk-forward record of every paper pipeline
  async function loadEvidence() {
    try { state.evid = await api("/api/pipelines_summary"); renderEvidence(); } catch (e) { /* the table is optional */ }
  }
  function renderEvidence() {
    const ev = state.evid; if (!ev) return;
    const cur = planPipe();
    const mo = (net) => (Math.pow(1 + net / 100, 1 / 12) - 1) * 100;
    const f = (x, d = 2) => x == null || !isFinite(x) ? "—" : Number(x).toFixed(d);
    const rows = PIPES.map((p) => {
      const s = ev[p.v]?.walkforward || {}, y = s.yearly || [];
      const dev = y.slice(0, 4).map((r) => mo(r[1]));
      const worst = dev.length ? Math.min(...dev) : null;
      const last = s.monthly_last_year, gate = last >= 5 && s.monthly_5y >= 5 && s.gate_dd <= 20 && !s.losing_years;
      const win = s.win_dev != null ? `${(100 * s.win_dev).toFixed(0)}% / ${(100 * (s.win_hidden ?? 0)).toFixed(0)}%` : "—";
      const pap = ev[p.v]?.paper_net_pct;
      return `<tr class="${cur === p.v ? "on" : ""}" data-pipe="${p.v}"><td><b>${p.nm}</b>${p.star ? ' <span class="star">★</span>' : ""}</td>
        <td>${f(s.monthly_dev4)}</td><td>${f(worst)}</td><td class="${s.gate_dd > 20 ? "down" : ""}">${f(s.gate_dd, 1)}%</td>
        <td>${f(s.monthly_5y)}</td><td class="${last >= 5 ? "up" : ""}"><b>${f(last)}</b></td><td>${s.losing_years ?? "—"}</td><td>${win}</td>
        <td>${pap == null ? "—" : sgn(pap)}</td><td>${gate ? '<span class="up">đạt</span>' : '<span class="muted">chưa</span>'}</td></tr>`;
    });
    table($("pipeEvid"), ["Pipeline", "4 năm dev %/th", "Năm dev tệ nhất", "DD", "5 năm %/th", "Năm giấu %/th", "Năm lỗ",
      "Thắng dev / giấu", "Paper", "Gate 5%"], rows);
    $("pipeEvid").onclick = (e) => { const r = e.target.closest("[data-pipe]"); if (r) setPlanPipe(r.dataset.pipe); };
  }

  async function loadTodo() {
    try {
      renderPipeStatus();
      await loadPlans();
      renderPipeBar(); renderBoard(); renderCards(); updateTitle();
      loadEvidence();
    } catch (e) { toast(e.message); }
  }

  // ---- executable trade plan (trade mode): what should be on the exchange now
  const planOf = (sym) => state.live.plan?.coins?.[sym];
  // paper pipelines (prospective evidence); O1 = the most robust walk-forward foundation, the default view
  const PIPES = [
    { v: "v285", nm: "CB", ds: "C4 + 20% model Coinbase premium · năm giấu 5.17%/tháng, vượt gate · SL dip 4σ nến 5m + SL sàn 8σ", star: "khuyên dùng" },
    { v: "v269", nm: "C4", ds: "O1 + SL lệnh dip 4σ theo nến 5m đóng cửa (bot canh) + SL sàn 8σ · DD thấp nhất" },
    { v: "v240", nm: "O1", ds: "cá voi theo lệnh thật · sleeve 0.18 · SL chạm" },
    { v: "v266", nm: "C5", ds: "O1 + SL lệnh dip theo nến 5m đóng cửa (bot canh) + SL sàn 8σ · lãi cao hơn, DD sát 20% · thử nghiệm" },
    { v: "v236", nm: "W2", ds: "dòng tiền cá voi · lãi TB cao nhất" },
    { v: "v233", nm: "T3", ds: "chỉ báo TradingView" },
    { v: "v205", nm: "D2", ds: "pipeline cũ" },
  ];
  const PIPE_LABEL = Object.fromEntries(PIPES.map((p) => [p.v, p.nm]));
  function planPipe() {
    try { const v = localStorage.getItem("planPipe4"); return PIPES.some((p) => p.v === v) ? v : "v285"; } catch { return "v285"; }
  }
  async function setPlanPipe(v) {
    try { localStorage.setItem("planPipe4", v); } catch { /* per-viewer convenience only */ }
    const cached = (state.live.paper || []).find(([k]) => k === v);
    state.live.plan = cached?.[1] || await api(`/api/trade_plan?pipeline=${v}`).catch(() => null);
    renderPipeBar(); renderBoard(); renderCards(); renderWatchlist(); renderPlan(); renderEvidence();
  }
  function renderPipeBar() {
    const cur = planPipe(), paper = Object.fromEntries(state.live.paper || []);
    $("pipeBar").innerHTML = PIPES.map((p) => {
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
      const slm = lastEvent(sym, ["sl_move"]);
      const u = px ? (L ? 1 : -1) * (px / p.avg_entry - 1) * 100 : p.upnl_pct;
      const items = [`Trên sàn phải đang có: <b>${p.side} ${q} ${C}</b> (giá vào TB ${fmtPx(p.avg_entry)}, ≈ ${usdt(p.weight)} USDT)`,
        `Lệnh <b>Stop-loss</b> (Stop Market) tại <b class="down">${fmtPx(p.sl)}</b>${p.break_even ? " — đã dời về hoà vốn" : ""}${recent(slm) ? ` <span class="warn">← vừa đổi lúc ${dt(Date.parse(slm.t))}, hãy sửa lệnh SL trên sàn</span>` : ""}`,
        `Lệnh <b>Take-profit</b> (Limit) tại <b class="up">${fmtPx(p.tp)}</b>`];
      if (c.order) {
        const o = c.order, kind = { add: "nhồi thêm", reduce: "chốt bớt", close: "đóng hết vị thế" }[o.kind] || o.kind;
        items.push(`<b>Việc mới:</b> đặt lệnh <b>LIMIT ${o.side === "BUY" ? "MUA" : "BÁN"}</b> tại <b>${fmtPx(o.price)}</b> để <b>${kind}</b>${o.amount ? ` (${pct(o.amount, 0)} vị thế)` : ""}; huỷ nếu đến ${dt(Date.parse(o.valid_until))} chưa khớp`);
      } else {
        items.push(`Ngoài ra <b>không cần làm gì</b> — cứ để SL/TP chạy tới quyết định kế tiếp (${dt(Date.parse(plan.next_decision))})`);
      }
      body = `<div class="act ${L ? "long" : "short"}">ĐANG GIỮ ${p.side} ${C} · lãi/lỗ ${sgn(u)}</div>` + step(items);
    } else {
      const cl = lastEvent(sym, ["book_close", "book_stop", "book_tp"]);
      body = `<div class="act flat">KHÔNG LÀM GÌ VỚI ${C}</div>` + step([
        `Pipeline không có lệnh nào cho ${C} lúc này.`,
        recent(cl) ? `Vị thế vừa ${{ book_close: "đóng bằng limit", book_stop: "chạm Stop-loss", book_tp: "chạm Take-profit" }[cl.kind]} tại ${fmtPx(cl.price)} — nếu trên sàn còn vị thế / lệnh ${C} thì đóng / huỷ.`
          : `Nếu trên sàn đang có lệnh chờ hoặc vị thế ${C} từ gợi ý cũ: huỷ / đóng để khớp với kế hoạch.`,
        `Kiểm tra lại ở quyết định kế tiếp: ${dt(Date.parse(plan.next_decision))}.`]);
    }
    if (!withTimeline) return body;
    const evs = (plan.events || []).filter((e) => e.symbol === sym).slice(-6).reverse();
    return body + `<div class="timeline">${evs.map((e) => `<div><span class="muted">${dt(Date.parse(e.t))}</span> ${EVVI[e.kind] || e.kind}
        ${e.kind.startsWith("sl_") ? "" : (e.side === "buy" ? "mua" : "bán")} ${fmtPx(e.price)}${e.why ? ` <span class="muted">(${esc(e.why)})</span>` : ""}</div>`).join("") || '<div class="muted small">Chưa có sự kiện.</div>'}</div>`;
  }
  function compactPlan(sym) {
    const c = planOf(sym), px = state.live.prices[sym]?.c;
    const row = (k, v, d = "", cls = "") => `<div class="pb-row ${cls}"><span class="k">${k}</span><span class="v">${v}</span><span class="d">${d}</span></div>`;
    const rel = (x, base) => (base ? `${x >= base ? "+" : ""}${((x / base - 1) * 100).toFixed(2)}%` : "");
    if (!c || c.state === "flat") {
      return `<div class="plan-box flat"><div class="pb-head"><span class="act-badge flat">ĐỨNG NGOÀI</span></div>
        <div class="muted small">Không có lệnh cho ${coin(sym)} — không cần làm gì.</div></div>`;
    }
    if (c.state === "pending") {
      const o = c.order, buy = o.side === "BUY";
      return `<div class="plan-box ${buy ? "long" : "short"}"><div class="pb-head"><span class="act-badge ${buy ? "wait-long" : "wait-short"}">${buy ? "LONG" : "SHORT"}</span>
          <span class="muted small">lệnh limit chờ khớp · ${qty(sym, o.weight, o.price)} ${coin(sym)} (≈ ${usdt(o.weight)} USDT)</span></div>
        ${lotWarn(sym, o.weight, o.price)}
        ${row("Entry", fmtPx(o.price), px ? `cách giá ${((o.price / px - 1) * 100).toFixed(2)}%` : "")}
        ${row("Take-profit", fmtPx(o.tp_if_filled), rel(o.tp_if_filled, o.price), "tp")}
        ${row("Stop-loss", fmtPx(o.sl_if_filled), rel(o.sl_if_filled, o.price), "sl")}
        <div class="muted small">Huỷ nếu chưa khớp lúc ${dt(Date.parse(o.valid_until))}</div></div>`;
    }
    const p = c.position, L = p.side === "LONG", u = px ? (L ? 1 : -1) * (px / p.avg_entry - 1) * 100 : p.upnl_pct;
    return `<div class="plan-box ${L ? "long" : "short"}"><div class="pb-head"><span class="act-badge ${L ? "long" : "short"}">${p.side}</span>
        <span class="muted small">đang giữ ${qty(sym, p.weight, p.avg_entry)} ${coin(sym)} (≈ ${usdt(p.weight)} USDT) · P/L ${sgn(u)}</span></div>
      ${lotWarn(sym, p.weight, p.avg_entry)}
      ${row("Entry", fmtPx(p.avg_entry))}
      ${row("Take-profit", fmtPx(p.tp), rel(p.tp, p.avg_entry), "tp")}
      ${row("Stop-loss", fmtPx(p.sl), rel(p.sl, p.avg_entry) + (p.break_even ? " · hoà vốn" : ""), "sl")}
      <div class="muted small">${c.order ? `Lệnh chờ: limit ${c.order.side === "BUY" ? "mua" : "bán"} @ ${fmtPx(c.order.price)}` : "Không cần làm gì thêm"}</div></div>`;
  }
  function renderPlan() {
    const sym = state.live.symbol, plan = state.live.plan;
    $("planPanel").innerHTML = `<div class="panel-h"><span>${coin(sym)} · ${PIPE_LABEL[planPipe()] || ""}</span>
      <span class="muted small">${plan?.next_decision ? "cập nhật kế tiếp " + dt(Date.parse(plan.next_decision)) : ""}</span></div>${compactPlan(sym)}
      <p class="fine">Hướng dẫn từng bước cho cả 5 coin ở tab <a href="#todo">Pipeline</a>.</p>`;
  }
  function renderCards() {
    const el = $("todoCards"); if (!el) return;
    const plan = state.live.plan, nm = PIPE_LABEL[planPipe()] || "";
    el.innerHTML = SYMS.map((s) => {
      const p = state.live.prices[s];
      return `<div class="panel plan card" id="card-${s}">
        <div class="panel-h"><span>${coin(s)} · ${nm}</span>
          <span class="card-price"><span class="px card-px" id="cpx-${s}">${p ? fmtPx(p.c) : ""}</span> <span class="small" id="cch-${s}">${p ? sgn((p.c / p.o - 1) * 100) : ""}</span></span></div>
        <div id="cbox-${s}">${compactPlan(s)}</div>
        <details class="steps-d"><summary>Hướng dẫn từng bước</summary>${planHtml(s)}</details></div>`;
    }).join("");
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
  function lastEvent(sym, kinds) { return (state.live.plan?.events || []).filter((e) => e.symbol === sym && kinds.includes(e.kind)).slice(-1)[0]; }
  const recent = (e) => e && Date.now() - Date.parse(e.t) < 4 * 3600 * 1000;
  function boardCells(s) {
    const c = planOf(s), px = state.live.prices[s]?.c;
    if (!c || c.state === "flat") {
      const cl = lastEvent(s, ["book_close", "book_stop", "book_tp"]);
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
    const slm = lastEvent(s, ["sl_move"]);
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
    $("boardMeta").textContent = !plan?.coins ? `${PIPE_LABEL[planPipe()]} · chưa có kế hoạch lệnh (chờ chu kỳ 4h kế tiếp)`
      : `${PIPE_LABEL[planPipe()]} · cập nhật ${dt(Date.parse(plan.generated_at))} · quyết định kế tiếp ${dt(Date.parse(plan.next_decision))}`;
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
      renderWatchlist(); renderPlan(); renderDips(); loadRecent(); mountTv(tr.dataset.sym); updateTitle();
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
        box.innerHTML = compactPlan(sym); (state.live.boxT ||= {})[sym] = Date.now();
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
      <tbody>${confLine(lv.dev, "4 năm đầu")}${confLine(lv.hidden, "Năm giấu")}</tbody></table>
      <div class="muted small">Lưu ý: nhãn tin cậy hiện tại chưa phân biệt tốt (97% lệnh là "Thấp"); đang nghiên cứu điểm tin cậy mới.</div></div>`;
  }

  function renderDips() {
    const sym = state.live.symbol;
    const rows = (state.live.latest?.sleeve || []).filter((r) => r.symbol === sym);
    // C4 / C5: the dip stop fires on a 5m CLOSE (bot) at 4 / 5 sigma, plus a native 8-sigma touch stop on the exchange
    const closeK = { v285: 4, v269: 4, v266: 5 }[planPipe()];
    if (closeK) {
      table($("dipTbl"), ["Bậc", "Mua limit", "TP", "SL nến 5m đóng", "SL sàn (đặt sẵn)", "Vốn"], rows.map((r) => {
        const s = r.buy_limit > 0 ? (r.buy_limit - r.sl) / (5 * r.buy_limit) : 0; // sigma from the advisor's 5-sigma stop
        return `<tr><td>${r.rung}σ</td><td>${fmtPx(r.buy_limit)}</td><td class="up">${fmtPx(r.tp)}</td>
        <td class="down">${fmtPx(r.buy_limit * (1 - closeK * s))}</td><td class="down">${fmtPx(r.buy_limit * (1 - 8 * s))}</td><td>${pct(r.size_frac)}</td></tr>`;
      }), "Không có lệnh chờ");
    } else {
      table($("dipTbl"), ["Bậc", "Mua limit", "TP", "SL", "Vốn"], rows.map((r) => `<tr><td>${r.rung}σ</td><td>${fmtPx(r.buy_limit)}</td>
      <td class="up">${fmtPx(r.tp)}</td><td class="down">${fmtPx(r.sl)}</td><td>${pct(r.size_frac)}</td></tr>`), "Không có lệnh chờ");
    }
    const d = state.live.conf?.levels?.DIP;
    const note = $("dipNote") || Object.assign(document.createElement("div"), { id: "dipNote", className: "muted small" });
    note.innerHTML = d ? `Lịch sử lệnh dip: thắng <b>${(100 * d.dev.win_rate).toFixed(0)}%</b> (${d.dev.n} lệnh, 4 năm đầu) · năm giấu <b>${(100 * d.hidden.win_rate).toFixed(0)}%</b> (${d.hidden.n} lệnh) · TB thắng +${d.dev.avg_win_pct.toFixed(2)}% / thua ${d.dev.avg_loss_pct.toFixed(2)}%` : "";
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
  function initHistory() {
    if (!histInit) {
      histInit = true;
      state.h.pipe = planPipe();
      seg($("hPipe"), PIPES.map((p) => p.v), state.h.pipe, (v) => { state.h.pipe = v; loadHistory(); },
        (v) => PIPES.find((p) => p.v === v).nm + (v === "v285" ? " ★" : ""));
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
    if (!days) { H.chart.timeScale().fitContent(); return; }
    const from = lastT - days * 86400e3;
    if (from < H.times[0] && !H.noOlder) await loadOlder(from);
    const i = Math.max(0, idxAt(from));
    H.chart.timeScale().setVisibleLogicalRange({ from: i, to: H.times.length + 8 });
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
    try {
      const pipe = state.perfPipe || planPipe(), src = `tm_${pipe}`, nm = PIPES.find((p) => p.v === pipe).nm;
      seg($("pPipe"), PIPES.map((p) => p.v), pipe, (v) => { state.perfPipe = v; loadPerf(); },
        (v) => PIPES.find((p) => p.v === v).nm + " — " + PIPES.find((p) => p.v === v).ds);
      const [ov, wfEq, st] = await Promise.all([api(`/api/overview?pipeline=${pipe}`), api(`/api/equity?source=${src}&points=3000`),
        api(`/api/orders/stats?source=${src}`)]);
      const wf = ov.walkforward || {}, plan = ov.plan || {};
      $("perfKpis").innerHTML = [
        [`${nm}: 5 năm walk-forward`, wf.monthly_5y, "%/tháng (TB hình học)"], ["4 năm đầu (dùng để chọn)", wf.monthly_dev4, "%/tháng"],
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
