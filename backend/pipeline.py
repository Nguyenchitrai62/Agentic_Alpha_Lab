"""Pipeline jobs that fill the web database. The API never runs the pipeline; these jobs do (scheduled or by admin).

- check:       ensure_data(): one data-completeness pass (candle gaps repaired, stale trade plans and missing walk-forward
               replays found / rebuilt); runs at backend startup and as the first step of every cycle.
- candles:    Binance USD-M 4h / 1h / 1d klines for the five majors (incremental).
- signal:      the frozen v205 pipeline for the latest closed 4h bar (scripts/v197_advisor.py), stored as a 'live' run.
- forward:     prospective paper trading of v205 since its freeze (scripts/forward_v205.py) -> equity('forward').
- walkforward: one-off backfill of the out-of-sample 2021-2026 replay (engine_user): per-bar target weights with
               entry/SL/TP levels, every fill/stop/take-profit/rung, and the equity curve.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import catalog, db, multiphase
from .config import ROOT, SETTINGS, log

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
INTERVALS = {"4h": 4 * 3600_000, "1h": 3600_000, "1d": 86400_000}
HISTORY_START = {"4h": "2021-06-01", "1h": "2023-06-01", "1d": "2020-01-01"}
PIPELINE = "v205"
_job_lock = threading.Lock()
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _ms(ts) -> int:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return int(t.timestamp() * 1000)


def run_job(kind: str, fn, triggered_by: str = "scheduler") -> dict:
    if not _job_lock.acquire(blocking=False):
        log.warning("job %s skipped: another pipeline job is running", kind)
        return {"status": "busy", "message": "another pipeline job is running"}
    try:
        started = db.now_ms()
        log.info("job %s started (by %s)", kind, triggered_by)
        with db.write() as c:
            job_id = c.execute("INSERT INTO jobs(kind, status, started_at, triggered_by) VALUES(?, 'running', ?, ?)",
                               (kind, started, triggered_by)).lastrowid
        try:
            msg = fn()
            status = "done"
        except Exception as exc:
            msg, status = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}", "failed"
        with db.write() as c:
            c.execute("UPDATE jobs SET status = ?, finished_at = ?, message = ? WHERE id = ?",
                      (status, db.now_ms(), str(msg)[:4000], job_id))
        secs = (db.now_ms() - started) / 1000
        if status == "done":
            log.info("job %s done in %.0fs: %s", kind, secs, str(msg)[:300])
        else:
            log.error("job %s FAILED after %.0fs: %s", kind, secs, str(msg)[:1500])
        return {"status": status, "message": msg, "job_id": job_id}
    finally:
        _job_lock.release()



# ---------------------------------------------------------------- candles
def job_candles() -> str:
    from agentic_alpha_lab.data.binance_usdm import fetch_klines
    from agentic_alpha_lab.data.coverage import missing_ranges
    import requests
    sess = requests.Session()
    total = 0
    now = datetime.now(timezone.utc)
    now_ms = _ms(now)
    repaired = 0
    for sym in SYMS:
        for iv, step in INTERVALS.items():
            span = db.one("SELECT MIN(t) AS a, MAX(t) AS b FROM candles WHERE symbol = ? AND interval = ?", (sym, iv))
            first = _ms(pd.Timestamp(HISTORY_START[iv], tz="UTC"))
            last = now_ms // step * step - step
            coverage_key = f"candle_start_{sym}_{iv}"
            known_start = db.kv_get(coverage_key)
            ranges = []
            if known_start is None and span["a"] is not None and span["a"] > first:
                ranges.append((first, span["a"] - step, True))  # historical prefix may precede listing
            start = known_start if known_start is not None else (span["a"] if span["a"] is not None else first)
            times = [r["t"] for r in db.rows("SELECT t FROM candles WHERE symbol=? AND interval=? ORDER BY t", (sym, iv))]
            gaps = missing_ranges(times, start, last, step)
            repaired += len(gaps)
            ranges.extend((a, b, False) for a, b in gaps)
            # Refresh the newest closed candle too, never a forming candle.
            if last >= start and not any(a <= last <= b for a, b, _ in ranges):
                ranges.append((last, last, False))
            for a, b, before_listing in ranges:
                try:
                    k = fetch_klines(sym, iv, pd.Timestamp(a, unit="ms", tz="UTC").to_pydatetime(),
                                     pd.Timestamp(b + step, unit="ms", tz="UTC").to_pydatetime(), session=sess)
                except RuntimeError as exc:
                    if before_listing and "returned no klines" in str(exc):
                        continue
                    raise
                if k.empty:
                    continue
                ot = pd.to_datetime(k["open_time"], utc=True)
                recs = [(sym, iv, int(t.timestamp() * 1000), float(o), float(h), float(l), float(c_), float(v))
                        for t, o, h, l, c_, v in zip(ot, k["open"], k["high"], k["low"], k["close"], k["volume"])]
                with db.write() as c:
                    c.executemany("INSERT OR REPLACE INTO candles(symbol, interval, t, o, h, l, c, v) VALUES(?,?,?,?,?,?,?,?)", recs)
                total += len(recs)
            times = [r["t"] for r in db.rows("SELECT t FROM candles WHERE symbol=? AND interval=? ORDER BY t", (sym, iv))]
            if not times:
                raise RuntimeError(f"{sym} {iv}: no closed candles available")
            # Persist the listing/history boundary so later deletions at the front are detectable.
            start = known_start if known_start is not None else min(times)
            unresolved = missing_ranges(times, start, last, step)
            if unresolved:
                raise RuntimeError(f"{sym} {iv}: missing closed candles remain: {unresolved[:3]}")
            db.kv_set(coverage_key, start)
    db.kv_set("pipeline_candle_check", {"checked_at": db.now_ms(), "gap_ranges_repaired": repaired, "status": "complete"})
    return f"candles upserted: {total}; gap ranges repaired: {repaired}"


def job_aggflow(archive: bool = True) -> str:
    """Large-order flow feed (v236 whale-flow features): the live REST collector every run, the public daily archive once a day."""
    env = {**__import__("os").environ, "PYTHONUTF8": "1"}
    msgs = []
    today = pd.Timestamp.now(tz="UTC")
    failures = []
    if archive and db.kv_get("aggflow_archive_day", "") != str(today.date()):
        p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/fetch_aggtrades_flow.py"), "--since", "2026-03"], cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=3600)
        if p.returncode == 0:  # the order-level archive (v240 O1) from the same daily files
            p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/fetch_aggtrades_flow.py"), "--orders", "--since", "2026-03"], cwd=str(ROOT),
                               capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=3600)
        if p.returncode == 0:
            db.kv_set("aggflow_archive_day", str(today.date()))
        msgs.append(f"archive {'ok' if p.returncode == 0 else 'FAILED: ' + p.stderr[-200:]}")
        if p.returncode != 0:
            failures.append("archive")
    for extra in ([], ["--orders"]):
        p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/aggflow_live.py"), *extra], cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=1800)
        msgs.append(("live orders " if extra else "live ") + ("ok" if p.returncode == 0 else "FAILED: " + p.stderr[-200:]))
        if p.returncode != 0:
            failures.append("live orders" if extra else "live")
            if "missing flow archive" in p.stderr or "flow archive has missing" in p.stderr:
                db.kv_set("aggflow_archive_day", "")  # force source repair on the next retry
    if failures:
        raise RuntimeError("aggflow incomplete: " + ", ".join(msgs))
    return "aggflow: " + ", ".join(msgs)


def refresh_candles_quietly() -> bool:
    """Incremental candle (and large-order flow) refresh between cycles, without a jobs row; skipped while another job runs."""
    if not _job_lock.acquire(blocking=False):
        return False
    try:
        log.info("plans refreshed after gap checks: %s", job_cycle())
        return True
    except Exception as exc:
        log.warning("refresh incomplete: %s", exc)
        return False
    finally:
        _job_lock.release()


# ---------------------------------------------------------------- live signal
def job_signal(asof: str | None = None) -> str:
    """Live signal run of the decision bar (the latest closed one, or `asof` = a missed bar's close for the backfill)."""
    cmd = [SETTINGS.python_exe, str(ROOT / "scripts/v197_advisor.py"), "--equity", str(SETTINGS.default_equity_usdt)]
    env = {**__import__("os").environ, "PYTHONUTF8": "1"}
    if asof:
        env["ADVISOR_ASOF"] = asof
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"advisor failed ({p.returncode}): {p.stderr[-1500:]}")
    adv = json.loads((ROOT / "artifacts/research/advisor_shadow/v197_advice_latest.json").read_text(encoding="utf-8"))
    decision = pd.Timestamp(adv["decision_bar_close"]) + pd.Timedelta(milliseconds=1)  # start of the bar the orders are for
    gross = sum(abs(b["weight"]) for b in adv["books"])
    with db.write() as c:
        c.execute("DELETE FROM runs WHERE source = 'live' AND decision_time = ?", (_ms(decision),))
        run_id = c.execute("INSERT INTO runs(source, decision_time, pipeline, created_at, scale, governor, gross, payload) "
                           "VALUES('live', ?, ?, ?, ?, ?, ?, ?)",
                           (_ms(decision), adv.get("pipeline", PIPELINE), db.now_ms(), adv.get("portfolio_scale"),
                            adv.get("governor_g"), gross, json.dumps(adv))).lastrowid
        c.executemany("INSERT INTO run_books(run_id, symbol, side, weight, entry, sl, tp, confidence, strength, members_agree) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?)",
                      [(run_id, b["symbol"], b["side"].split(" ")[0], b["weight"], b.get("limit_entry"), b.get("stop_loss_market"),
                        b.get("take_profit_limit"), b.get("confidence"), b.get("strength"), int(bool(b.get("members_agree"))))
                       for b in adv["books"]])
        c.executemany("INSERT INTO run_sleeve(run_id, symbol, rung, buy_limit, tp, sl, size_frac) VALUES(?,?,?,?,?,?,?)",
                      [(run_id, r["symbol"], r["rung_sigma"], r["buy_limit"], r["take_profit_limit"], r["stop_loss_market"], r["size_frac"])
                       for r in adv["dip_sleeve"]])
    return f"live run {run_id} for bar {decision}"


# ---------------------------------------------------------------- gap check + backfill of missed cycles
def job_backfill() -> str:
    """Before every cycle: find every required 4h decision bar a missed cycle left without an advisor row of the member
    advisors the five pipelines read (shadow.jsonl), and recompute each one AS OF its bar (ADVISOR_ASOF: only data up to that bar).
    Candles and the whale-flow feed resume from their last stored point, and the trade plans replay their whole window every run, so
    after this step nothing is missing."""
    env = {**__import__("os").environ, "PYTHONUTF8": "1", "ADVISOR_SHADOW_BACKFILL": "1"}
    p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/advisor_shadow.py")], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env, timeout=3600)
    if p.returncode != 0:
        raise RuntimeError(f"shadow backfill failed ({p.returncode}): {p.stderr[-1000:]}")
    return (p.stdout.strip().splitlines() or ["backfill: no output"])[-1]


# ---------------------------------------------------------------- prospective log (all frozen advisors)
def job_shadow_fast() -> str:
    """Only the four advisors the trade plans read (runs before the plans; the full prospective log follows after them)."""
    p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/advisor_shadow.py")], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONUTF8": "1", "ADVISOR_SHADOW_FAST": "1"}, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"shadow (fast) failed ({p.returncode}): {p.stderr[-1500:]}")
    return f"shadow fast: {p.stdout.count(chr(34) + 'logged_at' + chr(34))} new rows"


def job_shadow() -> str:
    """Append this bar's rows of every frozen advisor (v151 / v233 T3 / ...) to the prospective log shadow.jsonl.

    The trade plan reads its live books from that log, so it must run inside the cycle (before the trade plan), not in a
    session-scoped loop. advisor_shadow.py holds a lock file and skips rows already logged, so a duplicate run is harmless."""
    p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/advisor_shadow.py")], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONUTF8": "1"}, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"shadow log failed ({p.returncode}): {p.stderr[-1500:]}")
    n = p.stdout.count('"logged_at"')
    return f"shadow log: {n} new rows"


def job_dip_log() -> str:
    """Prospective log of the dip-sleeve rules (scripts/dip_sleeve_forward.py); runs last in the cycle (not needed for the plan)."""
    p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/dip_sleeve_forward.py")], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONUTF8": "1"}, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"dip log failed ({p.returncode}): {p.stderr[-1500:]}")
    return "dip log: " + (p.stdout.strip().splitlines() or ["ok"])[-1][:200]


# ---------------------------------------------------------------- forward paper trading
def job_forward() -> str:
    p = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/forward_v205.py")], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONUTF8": "1"}, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"forward failed ({p.returncode}): {p.stderr[-1500:]}")
    fw = json.loads((ROOT / "artifacts/research/advisor_shadow/forward_v205.json").read_text(encoding="utf-8"))
    curve = fw.pop("equity_curve", [])
    with db.write() as c:
        c.execute("DELETE FROM equity WHERE source = 'forward'")
        # equity after the holding bar (t+4h .. t+8h)
        c.executemany("INSERT INTO equity(source, t, equity) VALUES('forward', ?, ?)",
                      [(_ms(pd.Timestamp(t) + pd.Timedelta(hours=8)), float(e)) for t, e in curve])
        c.execute("INSERT INTO kv(k, v) VALUES('forward_summary', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(fw),))
    return f"forward: {fw.get('bars', 0)} bars, net {fw.get('net_return_pct')}%"


# ---------------------------------------------------------------- executable trade plan (trade mode)
PLAN_PIPELINES = tuple((v["candidate"], f"trade_plan_{p}", f"trade_plan_{p}.json")
                       for p, v in catalog.PIPELINES.items() if p not in catalog.PLAN_ALIASES)
H4_MS = 4 * 3600_000


def plan_order(slot: int) -> list[str]:
    """Unfinished plans for this 4h cycle first; configured pipeline priority within each group."""
    rank = catalog.plan_pipes()
    return sorted(rank, key=lambda p: (
        (db.kv_get(f"plan_status_{p}", {}) or {}).get("completed_slot") == slot,
        rank.index(p)))


def job_trade_plan() -> str:
    """Refresh all five plans, prioritizing unfinished plans in the configured order."""
    msgs, failures = [], []
    slot = db.now_ms() // H4_MS * H4_MS
    for pipe in plan_order(slot):
        key = f"trade_plan_{pipe}"
        try:
            if pipe in multiphase.PIPES:  # v376 R2-4P: due phase sub-plans (forward_trade_phase.py) + the merged plan
                msgs.append(multiphase.refresh(db, slot=slot))
                continue
            cmd = [SETTINGS.python_exe, str(ROOT / "scripts/forward_trade.py"),
                   "--candidate", catalog.PIPELINES[pipe]["candidate"]]
            cfg = ROOT / "configs/trade_policy.json"
            if cfg.exists():
                cmd += ["--policy", str(cfg)]
            p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env={**__import__("os").environ, "PYTHONUTF8": "1"}, timeout=1800)
            if p.returncode != 0:
                raise RuntimeError(f"trade plan failed ({p.returncode}): {p.stderr[-1500:]}")
            plan = json.loads((ROOT / "artifacts/research/advisor_shadow" / f"{key}.json").read_text(encoding="utf-8"))
            if _ms(plan["decision_bar"]) < slot:
                raise RuntimeError("trade plan artifact is older than the required decision bar")
            bars = plan.pop("bars", [])
            from . import history_tm
            history_tm.store_paper(pipe, dict(plan, bars=bars), db)
            db.kv_set(key, plan)
            msgs.append(f"{key}: " + ", ".join(f"{c['symbol'][:-4]} {c['state']}" for c in plan["coins"].values())
                        + f"; paper {plan['net_return_pct']}%")
            db.kv_set(f"plan_status_{pipe}", {"completed_slot": slot, "completed_at": db.now_ms()})
        except Exception as exc:
            msg = f"{key} FAILED: {type(exc).__name__}: {exc}"
            log.error("%s", msg)
            failures.append(msg)
    if failures:
        raise RuntimeError(" | ".join(msgs + failures))
    return " | ".join(msgs)


def job_phase_plans() -> str:
    """Hourly (minute offset of every hour): the multi-phase pipelines' sub-plan of the phase whose shifted 4h bar just closed
    (any due phase) + the merged plan; the 4h cycle of the other pipelines is not touched."""
    return " | ".join(multiphase.refresh(db) for _ in multiphase.PIPES)


# ---------------------------------------------------------------- data completeness check (startup + every cycle)
DATA_CHECK_KEY = "data_check"
SUMMARY_FAILURES_KEY = "summary_build_failures"
PLAN_DIR = "artifacts/research/advisor_shadow"


def due_slot(now_ms: int | None = None) -> int:
    """Start of the 4h bar whose trade plans must exist now (the previous bar until the schedule offset has passed)."""
    now_ms = db.now_ms() if now_ms is None else now_ms
    slot = now_ms // H4_MS * H4_MS
    return slot - H4_MS if now_ms < slot + SETTINGS.schedule_offset_minutes * 60_000 else slot


def candle_gaps(now_ms: int | None = None) -> list[str]:
    """Cheap SQL-only inspection of the stored klines: missing series, stale last closed candle, interior holes, and an
    unverified or truncated history start. The repair itself is job_candles (exact gap ranges + refetch)."""
    now_ms = db.now_ms() if now_ms is None else now_ms
    issues = []
    for sym in SYMS:
        for iv, step in INTERVALS.items():
            name = f"{sym} {iv}"
            last = now_ms // step * step - step  # newest closed candle (never the forming one)
            r = db.one("SELECT COUNT(*) AS n, MIN(t) AS a, MAX(t) AS b FROM candles WHERE symbol = ? AND interval = ?", (sym, iv))
            if not r or not r["n"]:
                issues.append(f"{name}: no candles")
                continue
            if r["b"] < last:
                issues.append(f"{name}: {(last - r['b']) // step} closed candle(s) missing at the end")
            holes = (r["b"] - r["a"]) // step + 1 - r["n"]
            if holes > 0:
                issues.append(f"{name}: {holes} interior gap candle(s)")
            known = db.kv_get(f"candle_start_{sym}_{iv}")
            if known is None:
                issues.append(f"{name}: history start not verified yet")
            elif r["a"] > known:
                issues.append(f"{name}: {(r['a'] - known) // step} candle(s) missing at the start")
    return issues


# code that defines a trade plan: a plan generated before any of these files changed is rebuilt (e.g. a new paper start or rule)
PLAN_CODE = ("scripts/forward_trade.py", "scripts/forward_v205.py", "scripts/manual_dip_agents.py", "scripts/v321_r2_dip_agents.py",
             "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def plan_code_mtime_ms() -> int:
    return max((int((ROOT / f).stat().st_mtime * 1000) for f in PLAN_CODE if (ROOT / f).exists()), default=0)


def stale_plans(now_ms: int | None = None) -> dict[str, str]:
    """Catalog pipelines (best first) whose trade plan is missing in the DB, missing on disk, older than the due 4h bar, or
    generated before the plan code last changed."""
    slot = due_slot(now_ms)
    code_ms = plan_code_mtime_ms()
    out = {}
    for pipe in catalog.plan_pipes():
        plan = db.kv_get(f"trade_plan_{pipe}")
        done = (db.kv_get(f"plan_status_{pipe}", {}) or {}).get("completed_slot")
        reason = None
        if not plan:
            reason = "no stored plan"
        elif not isinstance(done, int) or done < slot:
            reason = "not completed for the due 4h bar"
        elif not (ROOT / PLAN_DIR / f"trade_plan_{pipe}.json").exists():
            reason = "plan file missing"
        else:
            try:
                if _ms(plan["decision_bar"]) < slot:
                    reason = "plan older than the last closed 4h bar"
            except Exception:  # noqa: BLE001 - an unparseable bar is judged by the completion marker alone
                pass
            try:
                if not reason and plan.get("generated_at") and _ms(plan["generated_at"]) < code_ms:
                    reason = "plan code changed after the plan was generated"
            except Exception:  # noqa: BLE001
                pass
        if not reason and pipe in multiphase.PIPES:  # its four clock-shifted sub-plans, each due hourly on its own grid
            reason = multiphase.stale_reason(db, now_ms if now_ms is not None else db.now_ms())
        if reason:
            out[pipe] = reason
    return out


def missing_summaries() -> list[str]:
    """Catalog pipelines (best first) without a walk-forward replay: summary_tm_<p> missing or no tm_<p> equity rows."""
    return [p for p in catalog.plan_pipes()
            if not db.kv_get(f"summary_tm_{p}")
            or not db.one("SELECT 1 AS x FROM equity WHERE source = ? LIMIT 1", (f"tm_{p}",))]


def static_inputs_missing() -> list[str]:
    """Frozen research inputs the replays and plans read; they cannot be rebuilt here, only reported."""
    from . import history_tm
    paths = [history_tm.SIZE_TABLE, history_tm.G2_TABLE, history_tm.R2_TABLE, RD / "engine_user/engine_user.py",
             ROOT / "scripts/forward_trade.py"]
    return [str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p) for p in paths if not p.exists()]


def build_missing_summaries(force: bool = False) -> str:
    """history_tm.build (~1-3 min each) only for catalog pipelines whose replay is missing, best first. A pipeline whose
    build failed is retried at most once per 4h unless forced, so the 15-minute refresh does not loop on it."""
    missing = missing_summaries()
    if not missing:
        return "summaries: complete"
    from . import history_tm
    failures = db.kv_get(SUMMARY_FAILURES_KEY, {}) or {}
    now = db.now_ms()
    msgs, failed = [], []
    for pipe in missing:
        prev = failures.get(pipe) or {}
        if not force and now - int(prev.get("at", 0)) < H4_MS:
            msgs.append(f"tm_{pipe} skipped (build failed {(now - prev['at']) // 60_000} min ago)")
            continue
        log.info("data check: building the missing walk-forward replay tm_%s", pipe)
        try:
            msgs.append(multiphase.build_summary(db) if pipe in multiphase.PIPES else history_tm.build(pipe, db))
            failures.pop(pipe, None)
        except Exception as exc:  # noqa: BLE001 - one broken replay must not stop the others
            err = f"{type(exc).__name__}: {exc}"[:500]
            failures[pipe] = {"at": now, "error": err}
            msgs.append(f"tm_{pipe} FAILED: {err}")
            failed.append(pipe)
            log.error("data check: tm_%s build failed: %s", pipe, err)
    db.kv_set(SUMMARY_FAILURES_KEY, failures)
    msg = "summaries: " + " | ".join(msgs)
    if failed:
        raise RuntimeError(msg)
    return msg


# whale-flow stores read by the live A member: each 4h row's taker notional must be ~1x the kline quote volume (a re-fetch that
# appended a source on top of existing rows doubled 2026-09 once; system audit 2026-10-03)
FLOW_STORES = ("data/raw/aggflow_20260928_orders", "data/raw/aggflow_20260928")


def flow_volume_issues(days: int = 45, lo: float = 0.7, hi: float = 1.3) -> list[str]:
    """Days in the last `days` whose median 4h ratio taker flow / kline quote volume (DB 4h candles, v x mid price) is outside
    [lo, hi], per flow store and symbol."""
    out = []
    since = db.now_ms() - days * 86_400_000
    for store in FLOW_STORES:
        for sym in SYMS:
            path = ROOT / store / f"{sym}_flow_4h.parquet"
            if not path.exists():
                continue
            f = pd.read_parquet(path)
            f = f[f.index >= pd.Timestamp(since, unit="ms", tz="UTC")]
            tot = f[[c for c in f.columns if c.startswith(("buy_", "sell_"))]].sum(axis=1)
            rows = db.rows("SELECT t, o, c, v FROM candles WHERE symbol = ? AND interval = '4h' AND t >= ?", (sym, since))
            if tot.empty or not rows:
                continue
            qv = pd.Series({pd.Timestamp(r["t"], unit="ms", tz="UTC"): r["v"] * (r["o"] + r["c"]) / 2 for r in rows})
            r = (tot / qv.reindex(tot.index)).replace([float("inf")], float("nan")).dropna()
            day = r.groupby(r.index.floor("1D")).median()
            bad = day[(day < lo) | (day > hi)]
            if len(bad):
                out.append(f"{store.rsplit('/', 1)[-1]}/{sym}: {len(bad)} day(s) with flow/volume outside [{lo}, {hi}] "
                           f"(e.g. {bad.index[0].date()} x{bad.iloc[0]:.2f})")
    return out


def ensure_data(build_summaries: bool = False, now_ms: int | None = None) -> dict:
    """One data-completeness pass: inspect everything the pipelines need and repair what can be repaired.

    candles   (5 majors x 4h/1h/1d) gaps or a stale last closed candle -> job_candles (gap ranges refetched)
    plans     trade_plan_<p> missing in the DB / on disk / older than the due 4h bar -> reported (plans_stale); the caller
              runs the pipeline cycle, which regenerates them best first
    summaries summary_tm_<p> or its tm_<p> rows missing -> history_tm.build, only when build_summaries (slow)
    static    frozen research tables / engine files missing -> reported only

    Idempotent and cheap (a few indexed SQL reads) when nothing is missing. Never raises: problems land in the report
    ('errors' = input repairs that failed, 'warnings' = non-blocking), which is also stored in kv 'data_check'."""
    now_ms = db.now_ms() if now_ms is None else now_ms
    report = {"checked_at": now_ms, "due_slot": due_slot(now_ms), "candles": [], "candles_repaired": False,
              "plans_stale": {}, "summaries_missing": [], "static_missing": [], "fixed": [], "errors": [], "warnings": []}

    def guard(section, fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - the check must never take the server down
            report["errors" if section == "candles" else "warnings"].append(f"{section}: {type(exc).__name__}: {exc}"[:600])
            return None

    report["candles"] = guard("candles", lambda: candle_gaps(now_ms)) or []
    if report["candles"]:
        msg = guard("candles", job_candles)
        if msg is not None:
            report["candles_repaired"] = True
            report["fixed"].append(msg)
    report["summaries_missing"] = guard("summaries", missing_summaries) or []
    if build_summaries and report["summaries_missing"]:
        msg = guard("summaries", build_missing_summaries)
        if msg is not None:
            report["fixed"].append(msg)
        report["summaries_missing"] = guard("summaries", missing_summaries) or []
    report["plans_stale"] = guard("plans", lambda: stale_plans(now_ms)) or {}
    report["flow"] = guard("flow", flow_volume_issues) or []
    if report["flow"]:
        report["warnings"].append("flow store size check: " + "; ".join(report["flow"]))
    report["static_missing"] = guard("static", static_inputs_missing) or []
    if report["static_missing"]:
        report["warnings"].append("static inputs missing (not repairable here): " + ", ".join(report["static_missing"]))

    found = []
    if report["candles"]:
        found.append(f"candles {len(report['candles'])} issue(s) ({'; '.join(report['candles'][:3])})")
    if report["plans_stale"]:
        found.append("stale plans " + ", ".join(f"{p} ({r})" for p, r in report["plans_stale"].items()))
    if report["summaries_missing"]:
        found.append("missing replays " + ", ".join(report["summaries_missing"]))
    parts = ["data check: " + ("; ".join(found) if found else "nothing missing")]
    if report["fixed"]:
        parts.append("fixed: " + " | ".join(report["fixed"]))
    if report["errors"] or report["warnings"]:
        parts.append("problems: " + " | ".join(report["errors"] + report["warnings"]))
    report["message"] = " - ".join(parts)[:4000]
    try:
        db.kv_set(DATA_CHECK_KEY, report)
    except Exception as exc:  # noqa: BLE001
        log.warning("data check: report not stored: %r", exc)
    (log.warning if report["errors"] else log.info)("%s", report["message"][:1500])
    return report


def job_check() -> str:
    """Jobs-table wrapper of the fast check (no replay builds): fails when an input repair failed."""
    report = ensure_data(build_summaries=False)
    if report["errors"]:
        raise RuntimeError(report["message"])
    return report["message"]


def job_summaries() -> str:
    return build_missing_summaries()


# ---------------------------------------------------------------- walk-forward history (one-off, heavy)
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H4 = 4 * 3600_000
OPEN_EPS, CLOSE_EPS = 0.01, 0.004  # position size (fraction of equity) that opens / closes an order (hysteresis)


def build_orders(events: list[dict], bars: list[dict], cols: list[str]) -> list[tuple]:
    """Turn engine fills/exits into orders: one row per position episode (book) or per filled dip bid.

    A book order opens when the position leaves ~0, averages in on adds, and closes on its stop-loss, take-profit, a
    rebalance back to ~0 or a flip. SL/TP are the levels at the opening fill (entry -/+ 4 and 8 sigma_d of that bar).
    """
    sig = {(_ms(b["t"]), cols[j]): b["sig_d"][j] for b in bars for j in range(len(cols))}
    rows, book = [], {}
    pending = {}
    for e in events:  # append order: a rung fill is always followed by its own exit
        sym, t, kind = e["symbol"], _ms(e["t"]), e["kind"]
        if kind.startswith("rung"):
            if kind == "rung_fill":
                pending[sym] = (t, e["price"], e["weight"])
            elif sym in pending:
                ft, fp, fw = pending.pop(sym)
                reason = {"rung_tp": "TP", "rung_sl": "SL", "rung_timeout": "Hết 4h (market)"}[kind]
                rows.append((sym, "dip", "LONG", ft // H4 * H4, ft, fp, None,
                             None, fw, 0, t, e["price"], reason, 100 * (e["price"] / fp - 1), fp, 1, "limit (dip)"))
            continue
    for sym in cols:
        evs = sorted((e for e in events if e["symbol"] == sym and e["kind"].startswith("book")), key=lambda e: e["t"])
        pos, o = 0.0, None

        def levels(t):  # the engine's stop / take-profit for the average entry, with sigma_d of the bar at t
            sd = sig.get((t // H4 * H4, sym)) or sig.get((t // H4 * H4 - H4, sym))
            k = 1 if o["side"] == "LONG" else -1
            return (o["avg_px"] * (1 - k * 4 * sd), o["avg_px"] * (1 + k * 8 * sd)) if sd else (o["sl"], o["tp"])

        def close(t, px, reason):
            nonlocal o
            side = 1 if o["side"] == "LONG" else -1
            sl, tp = levels(t)
            if reason == "TP":
                tp = px  # the take-profit limit fills exactly at its level
            elif reason == "SL" and sl is not None and (px - sl) * side > 0:
                sl = px  # the level in force was at the fill (a gap-through fills beyond it and keeps sl)
            rows.append((sym, "book", o["side"], o["signal_t"], o["entry_t"], o["entry_px"], sl, tp, o["size"],
                         o["adds"], t, px, reason, 100 * side * (px / o["avg_px"] - 1), o["avg_px"], o["fills"], o["entry_type"]))
            o = None

        def open_(t, px, size, e):
            nonlocal o
            side = "LONG" if size > 0 else "SHORT"
            sd = sig.get((t // H4 * H4, sym))
            k = 1 if size > 0 else -1
            o = dict(side=side, signal_t=t // H4 * H4, entry_t=t, entry_px=px, avg_px=px, size=abs(size), adds=0, fills=1,
                     sl=px * (1 - k * 4 * sd) if sd else None, tp=px * (1 + k * 8 * sd) if sd else None,
                     entry_type=e.get("entry_type", "limit"))

        for e in evs:
            t, px = _ms(e["t"]), e["price"]
            if e["kind"] in ("book_stop", "book_tp"):
                if o:
                    close(t, px, "SL" if e["kind"] == "book_stop" else "TP")
                pos = 0.0
                continue
            new = pos + e["weight"]
            if o is None:
                if abs(new) >= OPEN_EPS:
                    open_(t, px, new, e)
            elif (new > 0) != (o["side"] == "LONG") and abs(new) >= CLOSE_EPS:
                close(t, px, "Đảo chiều")
                if abs(new) >= OPEN_EPS:
                    open_(t, px, new, e)
            elif abs(new) < CLOSE_EPS:
                close(t, px, "Rebalance về 0")
            else:
                o["fills"] += 1
                if abs(new) > abs(pos):
                    o["avg_px"] = (o["avg_px"] * abs(pos) + px * (abs(new) - abs(pos))) / abs(new)
                    o["size"], o["adds"] = max(o["size"], abs(new)), o["adds"] + 1
            pos = new
        if o:  # still open at the end of the replay
            sl, tp = levels(_ms(bars[-1]["t"]))
            rows.append((sym, "book", o["side"], o["signal_t"], o["entry_t"], o["entry_px"], sl, tp, o["size"],
                         o["adds"], None, None, "Đang mở", None, o["avg_px"], o["fills"], o["entry_type"]))
    return rows


HIDDEN_START = "2025-09-24"  # the most recent walk-forward year (the hidden year)


def confidence_of(orders: list[tuple], bars: list[dict], cols: list[str], A: pd.DataFrame, B: pd.DataFrame) -> list[tuple]:
    """Append (confidence, strength, agree) to every order with the live advisor's rule at the opening decision:
    agree = both annual members (A, B) point in the order's direction; strength = min(|target| / (0.4 * scale), 1);
    CAO if agree and strength >= 0.5, TRUNG BINH if agree and strength >= 0.2, else THAP. Dip orders get 'DIP'."""
    bar_at = {_ms(b["t"]): b for b in bars}
    col_ix = {c: j for j, c in enumerate(cols)}
    out = []
    for o in orders:
        if o[1] != "book":
            out.append(o + ("DIP", None, None))
            continue
        b, j = bar_at.get(o[3]), col_ix[o[0]]
        row_t = pd.Timestamp(o[3] - H4, unit="ms", tz="UTC")  # the decision row (books index) behind this holding bar
        k = 1 if o[2] == "LONG" else -1
        try:
            a, bb = float(A.at[row_t, o[0]]), float(B.at[row_t, o[0]])
        except KeyError:
            a = bb = 0.0
        agree = a != 0 and np.sign(a) == k and np.sign(bb) == k
        strength = min(abs(b["target"][j]) / (0.4 * b["scale"]), 1.0) if b and b["scale"] > 0 else 0.0
        conf = "CAO" if agree and strength >= 0.5 else ("TRUNG BINH" if agree and strength >= 0.2 else "THAP")
        out.append(o + (conf, round(strength, 3), int(agree)))
    return out


def confidence_stats(orders: list[tuple]) -> dict:
    """Win rate / average result per confidence level, first four walk-forward years vs the hidden year."""
    hid = _ms(pd.Timestamp(HIDDEN_START, tz="UTC"))
    groups: dict = {}
    for o in orders:
        if o[13] is None:  # still open
            continue
        per = "hidden" if o[4] >= hid else "dev"
        g = groups.setdefault(o[17], {}).setdefault(per, [])
        g.append((o[13], o[12]))
    stats = {}
    for conf, by in groups.items():
        stats[conf] = {}
        for per, rows in by.items():
            pn = np.array([r[0] for r in rows])
            win = pn > 0
            stats[conf][per] = dict(n=int(len(pn)), win_rate=round(float(win.mean()), 3), avg_pct=round(float(pn.mean()), 3),
                                    avg_win_pct=round(float(pn[win].mean()), 3) if win.any() else None,
                                    avg_loss_pct=round(float(pn[~win].mean()), 3) if (~win).any() else None,
                                    tp_rate=round(float(np.mean([r[1] == "TP" for r in rows])), 3),
                                    sl_rate=round(float(np.mean([r[1] == "SL" for r in rows])), 3))
    return {"rule": "CAO: 2 members agree and strength >= 0.5; TRUNG BINH: agree and >= 0.2; THAP: otherwise; "
                    "win = order result > 0 (price move vs average entry, before fees)",
            "dev": "anchors 2021-2024", "hidden": f"from {HIDDEN_START}", "levels": stats}


def job_walkforward() -> str:
    eu = _load("engine_user_web", RD / "engine_user/engine_user.py")
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    events, bars = [], []
    res = eu.simulate(books, opens, prep, m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239,
                      sleeve_risk_budget=0.12, size_mult=1.5, align=(1.5, 0.5), events=events, bars=bars)
    summary = {k: res[k] for k in ("monthly_5y", "monthly_dev4", "monthly_last_year", "dd_4h", "dd_1m", "gate_dd", "losing_years")}
    summary["yearly"] = [(y["anchor"], y["net_pct"], y["dd_1m_pct"]) for y in res["yearly"]]
    with db.write() as c:
        c.execute("DELETE FROM run_books WHERE run_id IN (SELECT id FROM runs WHERE source = 'walkforward')")
        c.execute("DELETE FROM runs WHERE source = 'walkforward'")
        c.execute("DELETE FROM trades WHERE source = 'walkforward'")
        c.execute("DELETE FROM equity WHERE source = 'walkforward'")
        c.execute("DELETE FROM orders WHERE source = 'walkforward'")
        orders = confidence_of(build_orders(events, bars, cols), bars, cols, A, B)
        c.executemany("INSERT INTO orders(source, symbol, kind, side, signal_t, entry_t, entry_px, sl, tp, size, adds, exit_t, exit_px, "
                      "exit_reason, pnl_pct, avg_px, fills, entry_type, confidence, strength, agree) "
                      "VALUES('walkforward',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", orders)
        c.execute("INSERT INTO kv(k, v) VALUES('confidence_stats', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                  (json.dumps(confidence_stats(orders)),))
        now = db.now_ms()
        for b in bars:
            t = _ms(b["t"])
            rid = c.execute("INSERT INTO runs(source, decision_time, pipeline, created_at, scale, governor, gross) VALUES('walkforward',?,?,?,?,?,?)",
                            (t, PIPELINE, now, b["scale"], b["governor"], float(np.abs(b["target"]).sum()))).lastrowid
            recs = []
            for j, sym in enumerate(cols):
                w, sd, o = b["target"][j], b["sig_d"][j], b["open"][j]
                held = b["qty"][j] * o if np.isfinite(o) else 0.0
                ae = b["entry"][j]
                if abs(held) > 1e-6 and np.isfinite(ae) and np.isfinite(sd):
                    k = 1 if held > 0 else -1
                    pos = (held, ae, ae * (1 - k * 4 * sd), ae * (1 + k * 8 * sd))
                else:
                    pos = (0.0, None, None, None)
                side = "LONG" if w > 0.005 else ("SHORT" if w < -0.005 else "FLAT")
                if side == "FLAT" or not np.isfinite(sd) or not np.isfinite(o):
                    recs.append((rid, sym, side, w, None, None, None, None, None, None) + pos)
                    continue
                entry = o * (1 - 0.001) if w > 0 else o * (1 + 0.001)
                sl = entry * (1 - 4 * sd) if w > 0 else entry * (1 + 4 * sd)
                tp = entry * (1 + 8 * sd) if w > 0 else entry * (1 - 8 * sd)
                recs.append((rid, sym, side, w, entry, sl, tp, None, None, None) + pos)
            c.executemany("INSERT INTO run_books(run_id, symbol, side, weight, entry, sl, tp, confidence, strength, members_agree, "
                          "held, avg_entry, pos_sl, pos_tp) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        c.executemany("INSERT INTO trades(source, t, symbol, kind, side, price, weight, extra) VALUES('walkforward',?,?,?,?,?,?,?)",
                      [(_ms(e["t"]), e["symbol"], e["kind"], e.get("side"), e.get("price"), e.get("weight"),
                        json.dumps({k: v for k, v in e.items() if k not in ("t", "symbol", "kind", "side", "price", "weight")}))
                       for e in events])
        c.executemany("INSERT INTO equity(source, t, equity) VALUES('walkforward', ?, ?)", [(_ms(b["t"]) + 4 * 3600_000, b["equity"]) for b in bars])
        c.execute("INSERT INTO kv(k, v) VALUES('walkforward_summary', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(summary),))
    db.optimize()
    return f"walk-forward: {len(bars)} bars, {len(events)} trade events, {len(orders)} orders, 5y {summary['monthly_5y']}%/month, last year {summary['monthly_last_year']}"


def job_walkforward_tm() -> str:
    """Walk-forward history of the executable trade-mode pipelines (D2 / T3 / W2 / O1) for the history and performance pages."""
    from . import history_tm
    return " | ".join(history_tm.build(pipe, db) for pipe in history_tm.PIPELINES)


def job_cycle() -> str:
    """Scheduled cycle after each 4h close: data check (ensure_data: candle gaps repaired, stale plans / missing replays
    found) -> candles + whale flow -> gap check + as-of backfill of missed bars -> the member advisors (O1 flow set + Coinbase
    member) -> every catalog pipeline's trade plan, best pipeline first (plan_order) -> missing walk-forward replays (slow, so
    after the plans) -> scorecard. The retired research logs (full shadow log, v205 live signal, v205 forward, dip log) no
    longer run."""
    out, failures, t0 = [], [], datetime.now(timezone.utc)
    db.kv_set("pipeline_input_check", {"status": "checking", "started_at": db.now_ms()})
    check: dict = {}

    def data_check():
        check.update(ensure_data(build_summaries=False))
        return check["message"]

    def candles():  # the check already ran the full candle repair successfully: do not fetch twice in one cycle
        return "candles: repaired by the data check" if check.get("candles_repaired") else job_candles()

    for name, fn in (("check", data_check), ("candles", candles), ("aggflow", job_aggflow), ("backfill", job_backfill),
                     ("shadow", job_shadow_fast), ("trade_plan", job_trade_plan)):
        try:
            out.append(fn())
        except Exception as exc:
            out.append(f"{name} FAILED: {type(exc).__name__}: {exc}")
            failures.append(name)
            db.kv_set("pipeline_input_check", {"status": "failed", "failed_step": name, "checked_at": db.now_ms()})
            break  # Never compute new plans from incomplete inputs; retry the repair first.
        # minute of the bar at which the step finished (the trade plan must be out before minute 5)
        out[-1] += f" [{name} done at +{(datetime.now(timezone.utc) - t0).total_seconds() + (t0.hour % 4) * 3600 + t0.minute * 60 + t0.second:.0f}s into the bar]"
    if failures:
        raise RuntimeError(" | ".join(out))
    db.kv_set("pipeline_input_check", {"status": "complete", "checked_at": db.now_ms()})
    if check.get("summaries_missing"):  # display/ranking data only: never blocks or delays the plans
        try:
            out.append(build_missing_summaries())
        except Exception as exc:  # noqa: BLE001
            out.append(f"summaries incomplete: {exc}"[:1000])
    try:  # prospective scorecard (live paper vs walk-forward expectation); informational, never blocks the cycle
        sc = subprocess.run([SETTINGS.python_exe, str(ROOT / "scripts/prospective_scorecard.py")], cwd=str(ROOT), capture_output=True, text=True,
                            timeout=600)
        out.append("scorecard ok" if sc.returncode == 0 else f"scorecard failed ({sc.returncode})")
    except Exception as exc:  # noqa: BLE001
        out.append(f"scorecard failed: {type(exc).__name__}")
    return " | ".join(out)
