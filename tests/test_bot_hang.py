"""bot_hang (2026-10-08): paper_d17bf hung 14 min with 0 CPU (last line
11:16:01 UTC = dip placements, restarted 11:29). No network, no keys.

Covers the two guards added in bot/run.py:
1. bounded lock acquisition -> op=lock_timeout log, refresh skipped, the
   cycle continues with the last good data (kline locks were already bounded
   at 30 s in bot/bybit_v5._kline_locked; this tests the timeout path);
2. cycle watchdog: a cycle exceeding N minutes (N = 10, frozen) logs
   op=cycle_stall and exits non-zero so keepalive / restart_all restarts it.
"""
import json
import time

import pandas as pd

import bot.run as run_mod
from bot.bybit_v5 import (
    _kline_locked,
    _note_lock_timeout,
    cached_1m_rows,
    pop_kline_lock_stats,
)
from bot.run import Runner, _arm_cycle_watchdog

INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}


class FakeExchange:
    def __init__(self, equity=10000.0):
        self._equity = equity
        self.orders = {}
        self.s = {"last_close": {}, "last_ms": {}}

    def instruments(self, symbols):
        return {s: INST[s] for s in symbols}

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
    r.carry_f = 0.0
    r.maint_start = None
    r.maint_end = None
    r._maint_active = False
    r.k2_tilt = None
    r._k2_logged = set()
    r._k2_missing_logged = set()
    r._kline_cache_dir_override = None
    r._bear_at = None
    r._bear = False
    r._last_plan = None
    r._skip_logged = {}
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

    r.log = _log
    return r


def _empty_plan():
    return {"generated_at": str(pd.Timestamp.now(tz="UTC")),
            "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {}}


def test_lock_held_by_another_runner_falls_back_within_budget(tmp_path):
    """Deterministic repro of the hang contention: the kline .lock is held
    (as one of the 12 paper runners can hold it) while this cycle reads/merges
    1m bars. Pre-fix (unbounded acquire) this blocked; now it must return via
    the timeout fallback quickly, keeping the fetched rows (refresh skipped in
    cache, cycle continues with the fetched data)."""
    pop_kline_lock_stats()
    sym = "BTCUSDT"
    t1 = 1_700_000_000_000 - (1_700_000_000_000 % 60_000)
    rows_newest_first = [
        [str(t1), "100.0", "101.0", "99.0", "100.5", "1.0", "100.0"],
        [str(t1 - 60_000), "99.0", "100.0", "98.0", "99.5", "1.0", "99.0"],
        [str(t1 - 120_000), "98.0", "99.0", "97.0", "98.5", "1.0", "98.0"],
    ]

    def _fetch(s, e):
        return list(rows_newest_first)

    from bot.bybit_v5 import kline_cache_path
    lock_path = kline_cache_path(sym, cache_dir=tmp_path).with_suffix(".lock")
    t0 = time.monotonic()
    # Hold the OS lock (same primitive a sibling runner holds) while a second
    # acquire with a short budget must time out instead of hanging.
    with _kline_locked(lock_path, timeout=60.0) as held:
        assert held is True
        rows, hit = cached_1m_rows(sym, t1 - 120_000, t1 + 60_000, _fetch,
                                   cache_dir=tmp_path, ttl=20.0,
                                   now=time.time(), lock_timeout=0.15)
        dt = time.monotonic() - t0
        assert rows == rows_newest_first  # fetched data kept, cache write skipped
        assert hit is False
        assert dt < 10.0, f"lock contention blocked the cycle for {dt:.1f}s"
        _wait, ntimeouts = pop_kline_lock_stats()
        assert ntimeouts >= 1  # get + merge acquires both timed out


def test_lock_timeout_logged_as_op_lock_timeout(tmp_path):
    """A bounded lock timeout inside the cycle surfaces as op=lock_timeout
    (even when the cycle stays fast overall: no slow_cycle)."""
    pop_kline_lock_stats()
    ex = FakeExchange()

    orig_step = ex.step

    def _contended_step(now=None):
        _note_lock_timeout()  # one cache-lock acquisition timed out this cycle
        return orig_step(now)

    ex.step = _contended_step
    r = _mk_runner(tmp_path, _empty_plan(), {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    acts = r.cycle()
    assert isinstance(acts, list)
    to = [l for l in r.logs if l.get("op") == "lock_timeout"]
    assert len(to) == 1, r.logs
    assert to[0]["timeouts"] == 1
    assert not [l for l in r.logs if l.get("op") == "slow_cycle"]


def test_watchdog_fires_logs_stall_and_exits_nonzero():
    """A cycle that never returns: op=cycle_stall is logged and the process is
    told to exit non-zero (exit_fn seam; production default is os._exit(2))."""
    logs, exits = [], []
    cancel = _arm_cycle_watchdog(logs.append, timeout_s=0.05,
                                 exit_fn=lambda: exits.append(2))
    try:
        time.sleep(0.5)
    finally:
        try:
            cancel()
        except Exception:
            pass
    assert len(exits) == 1 and exits[0] == 2
    assert len(logs) == 1 and logs[0].get("op") == "cycle_stall"
    assert logs[0].get("timeout_s") == 0.05


def test_watchdog_cancel_suppresses_fire():
    """A normally finishing cycle cancels the watchdog: no log, no exit."""
    logs, exits = [], []
    cancel = _arm_cycle_watchdog(logs.append, timeout_s=0.05,
                                 exit_fn=lambda: exits.append(2))
    cancel()  # cycle returned before the deadline
    time.sleep(0.3)
    assert logs == [] and exits == []


def test_state_persisted_every_cycle(tmp_path):
    """Premise the watchdog relies on: every cycle() return path persists
    state.json (timing heartbeat), and paper persists exchange.json, so a
    watchdog kill loses at most the in-flight cycle (cursors replay it)."""
    pop_kline_lock_stats()
    ex = FakeExchange()
    r = _mk_runner(tmp_path, _empty_plan(), {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()
    st = json.loads(r.state_f.read_text())
    assert isinstance(st.get("last_cycle_ms"), (int, float))
    assert isinstance(st.get("last_cycle_stages_ms"), dict)
    assert run_mod.CYCLE_WATCHDOG_S == 600.0  # N = 10 frozen per assignment
