"""Agentic Alpha Lab web API (FastAPI). Read-only for viewers; pipeline jobs are scheduled or started by the admin.

  .venv/Scripts/python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8724
Exposed publicly by the Cloudflare tunnel (api-crypto.nguyenchitrai.id.vn -> http://localhost:8724).
"""

from __future__ import annotations

import gzip
import hashlib
import threading
import time
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse, Response
import orjson

from . import auth, db, pipeline
from .config import SETTINGS, log

APP_VERSION = "1.0.0"
MAX_ROWS = 5000
MAX_CANDLES = 30000
app = FastAPI(title="Agentic Alpha Lab API", version=APP_VERSION, default_response_class=ORJSONResponse)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=list(SETTINGS.cors_origins), allow_origin_regex=SETTINGS.cors_origin_regex or None,
                   allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"], max_age=3600)

# ------------------------------------------------------------------ TTL cache of serialized (and pre-gzipped) responses
# Hot reads never touch SQLite or re-serialize: each cache entry keeps the JSON bytes, their gzip and an ETag.
_cache: OrderedDict[str, tuple[float, bytes, bytes, str]] = OrderedDict()
_cache_lock = threading.Lock()


def cached(request: Request, key: str, ttl: float, fn) -> Response:
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            _cache.move_to_end(key)
    if not (hit and hit[0] > now):
        raw = orjson.dumps(fn(), option=orjson.OPT_SERIALIZE_NUMPY)
        hit = (now + ttl, raw, gzip.compress(raw, 5) if len(raw) > 1024 else b"", '"' + hashlib.blake2b(raw, digest_size=12).hexdigest() + '"')
        with _cache_lock:
            _cache[key] = hit
            while len(_cache) > 3000:
                _cache.popitem(last=False)
    headers = {"ETag": hit[3], "Cache-Control": f"private, max-age={int(min(ttl, 30))}", "Vary": "Authorization, Accept-Encoding"}
    if request.headers.get("if-none-match") == hit[3]:
        return Response(status_code=304, headers=headers)
    if hit[2] and "gzip" in request.headers.get("accept-encoding", ""):
        return Response(hit[2], media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(hit[1], media_type="application/json", headers=headers)


def clear_cache():
    with _cache_lock:
        _cache.clear()


# ------------------------------------------------------------------ per-IP rate limit (token bucket)
_buckets: dict[str, list[float]] = defaultdict(lambda: [40.0, time.time()])
_bucket_lock = threading.Lock()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.headers.get("CF-Connecting-IP") or (request.client.host if request.client else "?")
    with _bucket_lock:
        if len(_buckets) > 20000:
            _buckets.clear()
        tokens, last = _buckets[ip]
        now = time.time()
        tokens = min(40.0, tokens + (now - last) * 10.0)  # 10 req/s sustained, bursts of 40
        if tokens < 1:
            _buckets[ip] = [tokens, now]
            return JSONResponse({"detail": "Too many requests."}, status_code=429)
        _buckets[ip] = [tokens - 1, now]
    return await call_next(request)


def _ms_range(start: str | None, end: str | None) -> tuple[int, int]:
    def p(x, default):
        if not x:
            return default
        return int(x) if x.isdigit() else int(datetime.fromisoformat(x.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp() * 1000)
    return p(start, 0), p(end, 4102444800000)


def _check_symbol(symbol: str) -> str:
    s = symbol.upper()
    if s not in pipeline.SYMS:
        raise HTTPException(400, f"symbol must be one of {pipeline.SYMS}")
    return s


# ------------------------------------------------------------------ public
@app.get("/health")
def health():
    last = db.one("SELECT kind, status, started_at, finished_at FROM jobs ORDER BY id DESC LIMIT 1")
    cyc = db.one("SELECT status, started_at, finished_at, triggered_by FROM jobs WHERE kind = 'cycle' ORDER BY id DESC LIMIT 1")
    return {"status": "ok", "version": APP_VERSION, "pipeline": pipeline.PIPELINE, "last_job": last, "last_cycle": cyc,
            "scheduler": SETTINGS.scheduler_enabled, "next_cycle_utc": _next_cycle["t"], "scheduler_heartbeat_utc": _heartbeat["t"],
            "last_cycle_done_ms": _last_cycle_ms()}


@app.get("/api/public/config")
def public_config():
    return {"google_client_id": SETTINGS.google_client_id, "symbols": pipeline.SYMS, "pipeline": pipeline.PIPELINE}


@app.post("/api/auth/google")
def auth_google(payload: dict = Body(...)):
    cred = str(payload.get("credential", ""))
    if not cred:
        raise HTTPException(400, "credential is required")
    return auth.login(cred)


@app.get("/api/auth/me")
def auth_me(user: dict | None = Depends(auth.current_user)):
    if user is None:
        raise HTTPException(401, "Sign in with Google.")
    return user


# ------------------------------------------------------------------ viewer
@app.get("/api/overview")
def overview(request: Request, pipeline: str | None = None, user: dict = Depends(auth.require_viewer)):
    """pipeline=v205/v233/v236/v240: the walk-forward summary of that executable trade-mode pipeline (history_tm)."""
    if pipeline in ("v205", "v233", "v236", "v240", "v266", "v269", "v285", "v295", "v301"):
        return cached(request, f"overview:{pipeline}", 60, lambda: {"walkforward": db.kv_get(f"summary_tm_{pipeline}", {}),
                                                                   "plan": db.kv_get({"v205": "trade_plan"}.get(pipeline, f"trade_plan_{pipeline}"), {})})

    def load():
        latest = db.one("SELECT id, decision_time, created_at, scale, governor, gross, pipeline FROM runs WHERE source = 'live' "
                        "ORDER BY decision_time DESC LIMIT 1")
        books = db.rows("SELECT symbol, side, weight, entry, sl, tp, confidence, strength, members_agree FROM run_books WHERE run_id = ?",
                        (latest["id"],)) if latest else []
        return {"latest": latest, "books": books, "forward": db.kv_get("forward_summary"),
                "walkforward": db.kv_get("walkforward_summary"),
                "last_job": db.one("SELECT kind, status, started_at, finished_at FROM jobs ORDER BY id DESC LIMIT 1")}
    return cached(request, "overview", 20, load)


@app.get("/api/pipelines_summary")
def pipelines_summary(request: Request, user: dict = Depends(auth.require_viewer)):
    """Walk-forward summary of every paper pipeline (history_tm) + its paper result since the freeze, for the pipeline evidence table."""
    keys = {"v205": "trade_plan", "v233": "trade_plan_v233", "v236": "trade_plan_v236", "v240": "trade_plan_v240",
            "v266": "trade_plan_v266", "v269": "trade_plan_v269", "v285": "trade_plan_v285", "v295": "trade_plan_v295", "v301": "trade_plan_v301"}

    def load():
        out = {}
        for p, k in keys.items():
            plan = db.kv_get(k, {}) or {}
            out[p] = {"walkforward": db.kv_get(f"summary_tm_{p}", {}), "paper_net_pct": plan.get("net_return_pct"), "freeze": plan.get("freeze")}
        return out
    return cached(request, "pipelines_summary", 60, load)


@app.get("/api/trade_plan")
def trade_plan(request: Request, pipeline: str = "v205", user: dict = Depends(auth.require_viewer)):
    """What a trader / bot should have on the exchange now (resting orders, positions with SL/TP) + the event log.

    pipeline=v205 (deployed, default), v233 (T3: TradingView indicator features) or v236 (W2: T3 + whale flow); paper comparison."""
    key = {"v233": "trade_plan_v233", "v236": "trade_plan_v236", "v240": "trade_plan_v240", "v266": "trade_plan_v266", "v269": "trade_plan_v269", "v285": "trade_plan_v285", "v295": "trade_plan_v295", "v301": "trade_plan_v301"}.get(pipeline, "trade_plan")
    return cached(request, key, 20, lambda: db.kv_get(key, {}))


@app.get("/api/signals/latest")
def signal_latest(request: Request, source: str = "live", user: dict = Depends(auth.require_viewer)):
    def load():
        r = db.one("SELECT id, source, decision_time, created_at, scale, governor, gross, pipeline FROM runs WHERE source = ? "
                   "ORDER BY decision_time DESC LIMIT 1", (source,))
        if not r:
            return {"run": None, "books": [], "sleeve": []}
        return {"run": r, "books": db.rows("SELECT * FROM run_books WHERE run_id = ?", (r["id"],)),
                "sleeve": db.rows("SELECT symbol, rung, buy_limit, tp, sl, size_frac FROM run_sleeve WHERE run_id = ? ORDER BY symbol, rung", (r["id"],))}
    return cached(request, f"latest:{source}", 20, load)


@app.get("/api/signals")
def signals(request: Request, source: str = "live", symbol: str | None = None, start: str | None = None, end: str | None = None,
            limit: int = Query(200, ge=1, le=MAX_ROWS), user: dict = Depends(auth.require_viewer)):
    a, b = _ms_range(start, end)
    if symbol:
        sym = _check_symbol(symbol)
        key = f"signals:{source}:{sym}:{a}:{b}:{limit}"
        return cached(request, key, 30, lambda: db.rows(
            "SELECT r.id, r.decision_time, r.scale, r.governor, r.gross, k.side, k.weight, k.entry, k.sl, k.tp, k.confidence, k.strength "
            "FROM runs r JOIN run_books k ON k.run_id = r.id AND k.symbol = ? "
            "WHERE r.source = ? AND r.decision_time BETWEEN ? AND ? ORDER BY r.decision_time DESC LIMIT ?", (sym, source, a, b, limit)))
    key = f"signals:{source}:*:{a}:{b}:{limit}"
    return cached(request, key, 30, lambda: db.rows(
        "SELECT id, decision_time, created_at, scale, governor, gross FROM runs WHERE source = ? AND decision_time BETWEEN ? AND ? "
        "ORDER BY decision_time DESC LIMIT ?", (source, a, b, limit)))


@app.get("/api/signals/at")
def signal_at(request: Request, t: str, source: str = "walkforward", user: dict = Depends(auth.require_viewer)):
    """The run in force at time t (latest decision_time <= t)."""
    ts = _ms_range(t, None)[0]
    r = db.one("SELECT id FROM runs WHERE source = ? AND decision_time <= ? ORDER BY decision_time DESC LIMIT 1", (source, ts))
    if not r:
        raise HTTPException(404, "no run before this time")
    return signal_detail(request, r["id"], user)


@app.get("/api/signals/{run_id}")
def signal_detail(request: Request, run_id: int, user: dict = Depends(auth.require_viewer)):
    def load():
        r = db.one("SELECT id, source, decision_time, created_at, scale, governor, gross, pipeline FROM runs WHERE id = ?", (run_id,))
        if not r:
            raise HTTPException(404, "run not found")
        return {"run": r, "books": db.rows("SELECT * FROM run_books WHERE run_id = ?", (run_id,)),
                "sleeve": db.rows("SELECT symbol, rung, buy_limit, tp, sl, size_frac FROM run_sleeve WHERE run_id = ? ORDER BY symbol, rung", (run_id,))}
    return cached(request, f"run:{run_id}", 300, load)


@app.get("/api/candles")
def candles(request: Request, symbol: str, interval: str = "4h", start: str | None = None, end: str | None = None,
            limit: int = Query(1500, ge=1, le=MAX_CANDLES), user: dict = Depends(auth.require_viewer)):
    sym = _check_symbol(symbol)
    if interval not in pipeline.INTERVALS:
        raise HTTPException(400, f"interval must be one of {list(pipeline.INTERVALS)}")
    a, b = _ms_range(start, end)
    key = f"candles:{sym}:{interval}:{a}:{b}:{limit}"
    return cached(request, key, 30, lambda: list(reversed(db.rows(
        "SELECT t, o, h, l, c, v FROM candles WHERE symbol = ? AND interval = ? AND t BETWEEN ? AND ? ORDER BY t DESC LIMIT ?",
        (sym, interval, a, b, limit)))))


@app.get("/api/positions")
def positions(request: Request, symbol: str, source: str = "walkforward", start: str | None = None, end: str | None = None,
              limit: int = Query(3000, ge=1, le=MAX_CANDLES), user: dict = Depends(auth.require_viewer)):
    sym = _check_symbol(symbol)
    a, b = _ms_range(start, end)
    key = f"pos:{source}:{sym}:{a}:{b}:{limit}"
    return cached(request, key, 60, lambda: list(reversed(db.rows(
        "SELECT r.decision_time AS t, k.weight, k.side, k.entry, k.sl, k.tp, k.held, k.avg_entry, k.pos_sl, k.pos_tp "
        "FROM runs r JOIN run_books k ON k.run_id = r.id AND k.symbol = ? "
        "WHERE r.source = ? AND r.decision_time BETWEEN ? AND ? ORDER BY r.decision_time DESC LIMIT ?", (sym, source, a, b, limit)))))


@app.get("/api/trades")
def trades(request: Request, symbol: str, source: str = "walkforward", start: str | None = None, end: str | None = None,
           limit: int = Query(2000, ge=1, le=MAX_CANDLES), user: dict = Depends(auth.require_viewer)):
    sym = _check_symbol(symbol)
    a, b = _ms_range(start, end)
    key = f"trades:{source}:{sym}:{a}:{b}:{limit}"
    return cached(request, key, 60, lambda: list(reversed(db.rows(
        "SELECT t, kind, side, price, weight, extra FROM trades WHERE source = ? AND symbol = ? AND t BETWEEN ? AND ? ORDER BY t DESC LIMIT ?",
        (source, sym, a, b, limit)))))


@app.get("/api/orders")
def orders(request: Request, symbol: str | None = None, source: str = "walkforward", kind: str | None = None,
           start: str | None = None, end: str | None = None, limit: int = Query(5000, ge=1, le=MAX_CANDLES),
           user: dict = Depends(auth.require_viewer)):
    """Orders (position episodes / dip bids) with signal time, entry, SL, TP, exit and result, newest first."""
    a, b = _ms_range(start, end)
    where, args = ["source = ?", "entry_t BETWEEN ? AND ?"], [source, a, b]
    if symbol:
        where.append("symbol = ?"); args.append(_check_symbol(symbol))
    if kind in ("book", "dip"):
        where.append("kind = ?"); args.append(kind)
    sql = (f"SELECT id, symbol, kind, side, signal_t, entry_t, entry_px, sl, tp, size, adds, exit_t, exit_px, exit_reason, pnl_pct, "
           f"avg_px, fills, entry_type, confidence, strength, agree "
           f"FROM orders WHERE {' AND '.join(where)} ORDER BY entry_t DESC LIMIT ?")
    return cached(request, f"orders:{source}:{symbol}:{kind}:{a}:{b}:{limit}", 120, lambda: db.rows(sql, tuple(args + [limit])))


@app.get("/api/orders/stats")
def orders_stats(request: Request, source: str = "walkforward", user: dict = Depends(auth.require_viewer)):
    """Order counts, win rate and average result per symbol / kind / exit reason."""
    return cached(request, f"ostats:{source}", 300, lambda: db.rows(
        "SELECT symbol, kind, exit_reason, COUNT(*) AS n, AVG(pnl_pct) AS avg_pnl, AVG(pnl_pct > 0) AS win, AVG(size) AS avg_size, "
        "MIN(entry_t) AS first_t, MAX(entry_t) AS last_t FROM orders WHERE source = ? GROUP BY symbol, kind, exit_reason", (source,)))


@app.get("/api/confidence")
def confidence(request: Request, user: dict = Depends(auth.require_viewer)):
    """Historical win rate per confidence level (first four walk-forward years vs the hidden year)."""
    return cached(request, "confidence", 300, lambda: db.kv_get("confidence_stats", {}))


@app.get("/api/equity")
def equity(request: Request, source: str = "walkforward", start: str | None = None, end: str | None = None, points: int = Query(1500, ge=10, le=MAX_ROWS),
           user: dict = Depends(auth.require_viewer)):
    a, b = _ms_range(start, end)

    def load():
        r = db.rows("SELECT t, equity FROM equity WHERE source = ? AND t BETWEEN ? AND ? ORDER BY t", (source, a, b))
        step = max(1, len(r) // points)
        return r[::step] + ([r[-1]] if r and (len(r) - 1) % step else [])
    return cached(request, f"equity:{source}:{a}:{b}:{points}", 60, load)


# ------------------------------------------------------------------ admin
@app.post("/api/admin/run")
def admin_run(payload: dict = Body(...), user: dict = Depends(auth.require_admin)):
    kind = payload.get("kind", "cycle")
    fns = {"cycle": pipeline.job_cycle, "signal": pipeline.job_signal, "candles": pipeline.job_candles, "trade_plan": pipeline.job_trade_plan, "shadow": pipeline.job_shadow,
           "forward": pipeline.job_forward, "walkforward": pipeline.job_walkforward,
           "walkforward_tm": pipeline.job_walkforward_tm}
    if kind not in fns:
        raise HTTPException(400, f"kind must be one of {list(fns)}")

    def work():
        pipeline.run_job(kind, fns[kind], triggered_by=user["email"])
        clear_cache()
    threading.Thread(target=work, daemon=True).start()
    return {"started": kind}


@app.get("/api/admin/jobs")
def admin_jobs(limit: int = Query(50, ge=1, le=500), user: dict = Depends(auth.require_admin)):
    return db.rows("SELECT id, kind, status, started_at, finished_at, triggered_by, message FROM jobs ORDER BY id DESC LIMIT ?", (limit,))


@app.get("/api/admin/users")
def admin_users(user: dict = Depends(auth.require_admin)):
    return db.rows("SELECT email, name, role, approved, first_seen, last_seen FROM users ORDER BY last_seen DESC")


@app.post("/api/admin/users")
def admin_set_user(payload: dict = Body(...), user: dict = Depends(auth.require_admin)):
    email = str(payload.get("email", "")).lower().strip()
    if not email:
        raise HTTPException(400, "email is required")
    approved = 1 if payload.get("approved", True) else 0
    role = "viewer"  # admins are defined only by ADMIN_EMAILS in the local .env
    with db.write() as c:
        c.execute("INSERT INTO users(email, role, approved, first_seen, last_seen) VALUES(?,?,?,?,?) "
                  "ON CONFLICT(email) DO UPDATE SET approved = excluded.approved", (email, role, approved, db.now_ms(), db.now_ms()))
    clear_cache()
    return {"email": email, "approved": bool(approved)}


# ------------------------------------------------------------------ scheduler
_next_cycle: dict = {"t": None}
_heartbeat: dict = {"t": None}  # last time the scheduler loop was alive (the /health watchdog restarts a dead scheduler)


def _keep_awake():
    """Ask Windows not to sleep while the scheduler thread runs (released automatically when the backend exits)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        log.info("scheduler: keep-awake requested (system sleep blocked while the backend runs)")
    except Exception as exc:  # not Windows / not allowed: the watchdog task still restarts missed cycles
        log.warning("scheduler: keep-awake unavailable: %r", exc)


def _last_cycle_ms() -> int:
    r = db.one("SELECT finished_at FROM jobs WHERE kind = 'cycle' AND status = 'done' ORDER BY id DESC LIMIT 1")
    return int(r["finished_at"]) if r and r.get("finished_at") else 0


def _scheduler():
    time.sleep(5)
    _keep_awake()
    _heartbeat["t"] = datetime.now(timezone.utc).isoformat()
    if not db.one("SELECT 1 AS x FROM candles LIMIT 1"):
        pipeline.run_job("candles", pipeline.job_candles, "startup")
    if not db.one("SELECT 1 AS x FROM runs WHERE source = 'live' LIMIT 1"):
        pipeline.run_job("cycle", pipeline.job_cycle, "startup")
    if not db.one("SELECT 1 AS x FROM runs WHERE source = 'walkforward' LIMIT 1"):
        pipeline.run_job("walkforward", pipeline.job_walkforward, "startup")
    # catch-up: a restart / reboot / sleep after a 4h close would otherwise wait up to 4 hours for the next cycle
    if db.now_ms() - _last_cycle_ms() > (4 * 3600 + 10 * 60) * 1000:
        log.info("scheduler: the last completed cycle is older than 4h10m - running a catch-up cycle now")
        pipeline.run_job("cycle", pipeline.job_cycle, "catch-up")
    clear_cache()
    while True:
        try:
            now = datetime.now(timezone.utc)
            nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=4 - now.hour % 4, minutes=SETTINGS.schedule_offset_minutes)
            if nxt - now > timedelta(hours=4):
                nxt -= timedelta(hours=4)
            log.info("scheduler: next pipeline cycle at %s UTC (%s local); candles refresh every 15 min",
                     nxt.strftime("%Y-%m-%d %H:%M"), nxt.astimezone().strftime("%H:%M"))
            _next_cycle["t"] = nxt.isoformat()
            while (wait := (nxt - datetime.now(timezone.utc)).total_seconds()) > 5:
                _heartbeat["t"] = datetime.now(timezone.utc).isoformat()
                time.sleep(min(wait, 900))
                _heartbeat["t"] = datetime.now(timezone.utc).isoformat()
                if (nxt - datetime.now(timezone.utc)).total_seconds() > 60:
                    pipeline.refresh_candles_quietly()  # keep candles <= 15 min old between cycles
                    clear_cache()
            pipeline.run_job("cycle", pipeline.job_cycle, "scheduler")
            clear_cache()
            db.optimize()
        except Exception:  # never let one error kill the scheduler thread silently
            log.exception("scheduler: loop error - retrying in 60 s")
            time.sleep(60)


@app.on_event("startup")
def _startup():
    db.init()
    log.info("backend up on http://%s:%s (db %s); scheduler %s", SETTINGS.host, SETTINGS.port, SETTINGS.db_path,
             "ON" if SETTINGS.scheduler_enabled else "OFF")
    if SETTINGS.scheduler_enabled:
        threading.Thread(target=_scheduler, name="pipeline-scheduler", daemon=True).start()
