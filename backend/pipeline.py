"""Pipeline jobs that fill the web database. The API never runs the pipeline; these jobs do (scheduled or by admin).

- candles:     Binance USD-M 4h / 1h / 1d klines for the five majors (incremental).
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

from . import db
from .config import ROOT, SETTINGS

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
INTERVALS = {"4h": 4 * 3600_000, "1h": 3600_000, "1d": 86400_000}
HISTORY_START = {"4h": "2021-06-01", "1h": "2025-09-01", "1d": "2020-01-01"}
PIPELINE = "v205"
_job_lock = threading.Lock()
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _ms(ts) -> int:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return int(t.timestamp() * 1000)


def run_job(kind: str, fn, triggered_by: str = "scheduler") -> dict:
    if not _job_lock.acquire(blocking=False):
        return {"status": "busy", "message": "another pipeline job is running"}
    started = db.now_ms()
    with db.write() as c:
        job_id = c.execute("INSERT INTO jobs(kind, status, started_at, triggered_by) VALUES(?, 'running', ?, ?)",
                           (kind, started, triggered_by)).lastrowid
    try:
        msg = fn()
        status = "done"
    except Exception as exc:  # keep the service alive; the error is visible in the admin page
        msg, status = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}", "failed"
    finally:
        _job_lock.release()
    with db.write() as c:
        c.execute("UPDATE jobs SET status = ?, finished_at = ?, message = ? WHERE id = ?", (status, db.now_ms(), str(msg)[:4000], job_id))
    return {"status": status, "message": msg, "job_id": job_id}


# ---------------------------------------------------------------- candles
def job_candles() -> str:
    from agentic_alpha_lab.data.binance_usdm import fetch_klines
    import requests
    sess = requests.Session()
    total = 0
    now = datetime.now(timezone.utc)
    for sym in SYMS:
        for iv, step in INTERVALS.items():
            last = db.one("SELECT MAX(t) AS t FROM candles WHERE symbol = ? AND interval = ?", (sym, iv))["t"]
            # re-fetch the newest stored candle: it may have been stored while still forming
            start = pd.Timestamp(last, unit="ms", tz="UTC") if last else pd.Timestamp(HISTORY_START[iv], tz="UTC")
            k = fetch_klines(sym, iv, start.to_pydatetime(), now, session=sess)
            if k.empty:
                continue
            ot = pd.to_datetime(k["open_time"], utc=True)
            recs = [(sym, iv, int(t.timestamp() * 1000), float(o), float(h), float(l), float(c_), float(v))
                    for t, o, h, l, c_, v in zip(ot, k["open"], k["high"], k["low"], k["close"], k["volume"])]
            with db.write() as c:
                c.executemany("INSERT OR REPLACE INTO candles(symbol, interval, t, o, h, l, c, v) VALUES(?,?,?,?,?,?,?,?)", recs)
            total += len(recs)
    return f"candles upserted: {total}"


# ---------------------------------------------------------------- live signal
def job_signal() -> str:
    cmd = [SETTINGS.python_exe, str(ROOT / "scripts/v197_advisor.py"), "--equity", str(SETTINGS.default_equity_usdt)]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONUTF8": "1"}, timeout=1800)
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


# ---------------------------------------------------------------- walk-forward history (one-off, heavy)
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
        now = db.now_ms()
        for b in bars:
            t = _ms(b["t"])
            rid = c.execute("INSERT INTO runs(source, decision_time, pipeline, created_at, scale, governor, gross) VALUES('walkforward',?,?,?,?,?,?)",
                            (t, PIPELINE, now, b["scale"], b["governor"], float(np.abs(b["target"]).sum()))).lastrowid
            recs = []
            for j, sym in enumerate(cols):
                w, sd, o = b["target"][j], b["sig_d"][j], b["open"][j]
                side = "LONG" if w > 0.005 else ("SHORT" if w < -0.005 else "FLAT")
                if side == "FLAT" or not np.isfinite(sd) or not np.isfinite(o):
                    recs.append((rid, sym, side, w, None, None, None, None, None, None))
                    continue
                entry = o * (1 - 0.001) if w > 0 else o * (1 + 0.001)
                sl = entry * (1 - 4 * sd) if w > 0 else entry * (1 + 4 * sd)
                tp = entry * (1 + 8 * sd) if w > 0 else entry * (1 - 8 * sd)
                recs.append((rid, sym, side, w, entry, sl, tp, None, None, None))
            c.executemany("INSERT INTO run_books(run_id, symbol, side, weight, entry, sl, tp, confidence, strength, members_agree) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?)", recs)
        c.executemany("INSERT INTO trades(source, t, symbol, kind, side, price, weight, extra) VALUES('walkforward',?,?,?,?,?,?,?)",
                      [(_ms(e["t"]), e["symbol"], e["kind"], e.get("side"), e.get("price"), e.get("weight"),
                        json.dumps({k: v for k, v in e.items() if k not in ("t", "symbol", "kind", "side", "price", "weight")}))
                       for e in events])
        c.executemany("INSERT INTO equity(source, t, equity) VALUES('walkforward', ?, ?)", [(_ms(b["t"]) + 4 * 3600_000, b["equity"]) for b in bars])
        c.execute("INSERT INTO kv(k, v) VALUES('walkforward_summary', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(summary),))
    db.optimize()
    return f"walk-forward: {len(bars)} bars, {len(events)} trade events, 5y {summary['monthly_5y']}%/month, last year {summary['monthly_last_year']}"


def job_cycle() -> str:
    """Scheduled cycle after each 4h close: candles -> live signal -> forward paper trading."""
    out = []
    for name, fn in (("candles", job_candles), ("signal", job_signal), ("forward", job_forward)):
        try:
            out.append(fn())
        except Exception as exc:
            out.append(f"{name} FAILED: {type(exc).__name__}: {exc}")
    return " | ".join(out)
