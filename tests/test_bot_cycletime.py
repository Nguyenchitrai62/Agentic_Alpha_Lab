"""bot_cycletime: cycle wall-time instrumentation + cache-lock timeout. No network, no keys."""
import importlib.util
import json
import time
from pathlib import Path

import pandas as pd

import bot.run as run_mod
from bot.bybit_v5 import (
    _kline_locked,
    _note_lock_wait,
    cached_call,
    kline_cache_path,
    pop_kline_lock_stats,
)
from bot.run import Runner

T0 = pd.Timestamp("2026-10-05 04:00", tz="UTC")
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}


class FakeExchange:
    def __init__(self, inst=None, equity=10000.0):
        self.inst_map = inst or INST
        self._equity = equity
        self.orders = {}
        self.execs = []
        self.s = {"last_close": {}, "last_ms": {}}

    def instruments(self, symbols):
        return {s: self.inst_map[s] for s in symbols}

    def equity_usdt(self):
        return self._equity

    def step(self, now=None):
        return None

    def save(self):
        return None

    def klines(self, symbol, interval="5", limit=3):
        return []

    def open_orders(self):
        return []

    def executions(self, start_ms):
        return []

    def place(self, p):
        self.orders[p.get("orderLinkId")] = dict(p)
        return dict(orderLinkId=p.get("orderLinkId"))

    def amend(self, symbol, link, **kw):
        if link not in self.orders:
            return None
        self.orders[link].update(kw)
        return dict(orderLinkId=link)

    def cancel(self, symbol, link):
        return self.orders.pop(link, None) and dict(orderLinkId=link)


def _mk_runner(tmp_path, plan_dict, state_dict, ex, mode="paper"):
    d = tmp_path / "botstate"
    d.mkdir(parents=True, exist_ok=True)
    plan_f = d / "plan.json"
    plan_f.write_text(json.dumps(plan_dict))
    r = Runner.__new__(Runner)
    r.mode = mode
    r.plan_path = plan_f
    r.risk_mult = 1.0
    r.corr = False
    r.tag = None
    r.dip_mult = 1.0
    r.bear_book = False
    r.dip_cooldown_h = 0.0
    r.dip_sl_coin = {}
    r.dip_gross_cap = 0.0
    r.adopt_fresh = False
    r.no_risk_guard = True
    r._bear_at = None
    r._bear = False
    r._last_plan = None
    r._skip_logged = {}
    r._kline_cache_dir_override = None
    r.dir = d
    r.state_f = d / "state.json"
    r.state = dict(state_dict)
    r.state_f.write_text(json.dumps(state_dict, default=str))
    r.ex = ex
    r.equity_arg = 10000.0
    r.inst = dict(INST)
    r.logs = []

    def _log(rec):
        r.logs.append(rec)
        with open(r.dir / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    r.log = _log
    return r


def _empty_plan():
    return {"generated_at": str(pd.Timestamp.now(tz="UTC")),
            "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {}}


def test_cycle_writes_timing(tmp_path):
    pop_kline_lock_stats()
    ex = FakeExchange()
    r = _mk_runner(tmp_path, _empty_plan(), {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    acts = r.cycle()
    assert isinstance(acts, list)
    st = json.loads(r.state_f.read_text())
    assert "last_cycle_ms" in st and isinstance(st["last_cycle_ms"], (int, float))
    stages = st.get("last_cycle_stages_ms")
    assert isinstance(stages, dict)
    for k in ("plan_ms", "kline_ms", "sync_ms", "decide_ms", "order_ms", "state_ms"):
        assert k in stages, stages
        assert stages[k] >= 0.0
    assert st["last_cycle_ms"] >= 0.0
    assert not [l for l in r.logs if l.get("op") == "slow_cycle"]
    assert not [l for l in r.logs if l.get("op") == "lock_wait"]


def test_slow_cycle_logged_with_fake_clock(tmp_path, monkeypatch):
    pop_kline_lock_stats()
    ex = FakeExchange()
    r = _mk_runner(tmp_path, _empty_plan(), {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    t = [1000.0]

    def _fake():
        t[0] += 15.0  # each stage step jumps 15 s -> total well over 60 s
        return t[0]

    monkeypatch.setattr(run_mod, "_cycle_now", _fake)
    r.cycle()
    slow = [l for l in r.logs if l.get("op") == "slow_cycle"]
    assert len(slow) == 1
    assert slow[0]["total_ms"] > 60_000
    assert isinstance(slow[0].get("stages"), dict)
    st = json.loads(r.state_f.read_text())
    assert st["last_cycle_ms"] > 60_000


def test_lock_wait_logged_with_fake_wait(tmp_path):
    pop_kline_lock_stats()
    ex = FakeExchange()

    orig_step = ex.step

    def _slow_step(now=None):
        _note_lock_wait(11.0)  # simulate 11 s of cache-lock waiting inside the kline stage
        return orig_step(now)

    ex.step = _slow_step
    r = _mk_runner(tmp_path, _empty_plan(), {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()
    lw = [l for l in r.logs if l.get("op") == "lock_wait"]
    assert len(lw) == 1
    assert lw[0]["lock_wait_ms"] >= 10_000
    st = json.loads(r.state_f.read_text())
    assert st.get("last_cycle_lock_wait_ms", 0) >= 10_000


def test_cache_lock_timeout_falls_back_to_direct_fetch(tmp_path):
    pop_kline_lock_stats()
    sym, field = "BTCUSDT", "close_1m"
    path = kline_cache_path(sym, cache_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({field: {"t": time.time(), "v": 1.0}}), encoding="utf-8")
    lock_path = path.with_suffix(".lock")
    # Hold the OS lock in this process while a second acquire times out.
    with _kline_locked(lock_path, timeout=60.0) as held:
        assert held is True
        calls = [0]

        def _fetch():
            calls[0] += 1
            return 999.0

        v, hit = cached_call(sym, field, _fetch, cache_dir=tmp_path, ttl=3600.0,
                             now=time.time(), lock_timeout=0.15)
        assert calls[0] == 1  # lock held -> timeout -> direct fetch fallback
        assert v == 999.0 and hit is False
        _wait, ntimeouts = pop_kline_lock_stats()
        assert ntimeouts >= 1
    # After release the value can be cached and hit normally.
    pop_kline_lock_stats()
    calls2 = [0]

    def _fetch2():
        calls2[0] += 1
        return 123.0

    v2, hit2 = cached_call("ETHUSDT", "close_1m", _fetch2, cache_dir=tmp_path,
                           ttl=3600.0, now=time.time(), lock_timeout=5.0)
    assert (v2, hit2, calls2[0]) == (123.0, False, 1)
    v3, hit3 = cached_call("ETHUSDT", "close_1m", _fetch2, cache_dir=tmp_path,
                           ttl=3600.0, now=time.time(), lock_timeout=5.0)
    assert (v3, hit3, calls2[0]) == (123.0, True, 1)


SPEC = importlib.util.spec_from_file_location(
    "bot_health", Path(__file__).resolve().parents[1] / "scripts" / "bot_health.py")
_bh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(_bh)


def test_health_shows_last_cycle_ms_and_warns(tmp_path):
    from datetime import datetime, timezone
    d = tmp_path / "bot"
    d.mkdir()
    now = datetime.now(timezone.utc)
    (d / "actions.jsonl").write_text(json.dumps({"t": now.isoformat(), "op": "place"}) + "\n")
    (d / "state.json").write_text(json.dumps({"ledger": {}, "links": {},
                                              "last_cycle_ms": 65000.0,
                                              "last_cycle_stages_ms": {"plan_ms": 1.0}}))
    rep = _bh.check_dir(d, {"generated_at": now.isoformat()}, now, 20.0)
    assert rep["last_cycle_ms"] == 65000.0
    assert rep["status"] == "warning"
    assert any("60s" in w for w in rep["warnings"])
    out = _bh.fmt_report(rep)
    assert "cycle_ms=65.0s" in out
