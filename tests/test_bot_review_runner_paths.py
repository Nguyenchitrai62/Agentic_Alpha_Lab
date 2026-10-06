"""Review 2026-10-06 (F3/F4): normal-cycle robustness. NO network, NO keys.

Each test asserts the CORRECT behaviour; all fail on current code.
F3: one equity_usdt blip must not abort the cycle (ledger-only path already survives it).
F4: an old dip ledger piece without frac/dist must not crash desired().
"""
import json

import pandas as pd
import pytest

from bot import mirror
from bot.bybit_v5 import BybitError


T0 = pd.Timestamp("2026-10-05 04:00", tz="UTC")
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}


class BlipExchange:
    """equity_usdt raises once (one signed-call blip), then recovers."""

    def __init__(self):
        self.orders = {}
        self.execs = []
        self._blipped = False
        self.s = {"last_close": {}, "last_ms": {}}
        self.saved = 0

    def instruments(self, symbols):
        return {s: INST[s] for s in symbols}

    def equity_usdt(self):
        if not self._blipped:
            self._blipped = True
            raise BybitError("10006: Too many visits (blip)")
        return 10000.0

    def step(self, now=None):
        return None

    def save(self):
        self.saved += 1

    def klines(self, symbol, interval="5", limit=3):
        return []

    def open_orders(self):
        return []

    def executions(self, start_ms):
        return []

    def place(self, p):
        self.orders[p["orderLinkId"]] = dict(p)
        return dict(orderLinkId=p["orderLinkId"])

    def amend(self, symbol, link, **kw):
        return dict(orderLinkId=link) if link in self.orders else None

    def cancel(self, symbol, link):
        return self.orders.pop(link, None) and dict(orderLinkId=link)


def _mk_runner(tmp_path, plan_dict, state_dict, ex, **kw):
    from bot.run import Runner
    d = tmp_path / "botstate_rev"
    d.mkdir(parents=True, exist_ok=True)
    plan_f = d / "plan.json"
    plan_f.write_text(json.dumps(plan_dict, default=str))
    r = Runner.__new__(Runner)
    r.mode = "paper"
    r.plan_path = plan_f
    r.risk_mult = 1.0
    r.corr = False
    r.tag = None
    r.dip_mult = 1.0
    r.bear_book = False
    r.adopt_fresh = False
    r.no_risk_guard = True
    r.carry_f = 0.0
    r.dip_cooldown_h = 0.0
    r.dip_sl_coin = {}
    r.dip_gross_cap = 0.0
    r.maint_start = None
    r.maint_end = None
    r._maint_active = False
    r._bear_at = None
    r._bear = False
    r._last_plan = None
    r._skip_logged = {}
    r._kline_cache_dir_override = None
    r.dir = d
    r.state_f = d / "state.json"
    r.state = state_dict
    r.state_f.write_text(json.dumps(state_dict, default=str))
    r.ex = ex
    r.equity_arg = 10000.0
    r.inst = dict(INST)
    r.logs = []
    r.log = lambda rec: r.logs.append(rec)
    return r


def _fresh_plan():
    now = pd.Timestamp.now(tz="UTC")
    return {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {}}


def test_cycle_survives_one_equity_blip(tmp_path):
    # F3: a single equity_usdt failure must not raise out of cycle().
    ex = BlipExchange()
    r = _mk_runner(tmp_path, _fresh_plan(),
                   {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()  # must not raise
    assert ex._blipped is True


def test_have_blip_does_not_abort_cycle(tmp_path):
    # F3 mirror: a single open_orders failure must not raise out of cycle().
    ex = BlipExchange()
    calls = {"n": 0}
    orig = ex.open_orders

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise BybitError("simulated open_orders timeout")
        return orig()

    ex.open_orders = flaky
    r = _mk_runner(tmp_path, _fresh_plan(),
                   {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()  # must not raise
    assert calls["n"] >= 1


def test_old_dip_ledger_without_frac_no_crash():
    # F4: pre-frac ledgers must not raise KeyError out of desired().
    plan = {"generated_at": str(T0), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"BTCUSDT": {"subs": [], "dips": []}}}
    old = {"d1": dict(kind="dip", phase=0, symbol="BTCUSDT", side=1, qty=0.01,
                      entry=78000.0, tp=78780.0, backstop=71760.0,
                      t_exit=str(T0 + pd.Timedelta(hours=4)), opened=str(T0))}
    want = mirror.desired(plan, T0 + pd.Timedelta(minutes=20), 10000, old)
    assert isinstance(want, dict)


def test_executions_paginates_past_100(monkeypatch):
    # F7: executions() follows nextPageCursor until empty (page cap bounds it).
    from bot.bybit_v5 import Bybit
    pages = [
        {"list": [dict(execId=f"e{i}", execTime=str(i)) for i in range(100)],
         "nextPageCursor": "cur1"},
        {"list": [dict(execId="e100", execTime="100")]},
    ]
    calls = {"n": 0}

    def fake_get(self, path, **kw):
        calls["n"] += 1
        return dict(pages[min(calls["n"] - 1, 1)])

    monkeypatch.setattr(Bybit, "get", fake_get)
    out = Bybit().executions(0)
    assert len(out) == 101 and calls["n"] == 2


class _RaceFakeExchange:
    """Category-aware fake for the F6 race: linear holds a book fill plus a
    carry futures fill; spot holds the carry spot fill."""

    def __init__(self, linear, spot):
        self.linear_execs = list(linear)
        self.spot_execs = list(spot)
        self.inverse_execs = []

    def executions(self, start_ms, category="linear"):
        src = self.spot_execs if category == "spot" else (
            self.inverse_execs if category == "inverse" else self.linear_execs)
        return [e for e in src if int(e["execTime"]) >= int(start_ms)]

    def open_orders(self, category="linear"):
        return []

    def place(self, p):
        return dict(orderLinkId=p.get("orderLinkId"))


def test_book_fill_not_skipped_by_carry_sync_race():
    # F6 race: a book fill landing between the two polls must still reach the
    # ledger. _carry_sync advances only its own carry cursor past carry execs;
    # sync_fills then still sees the book exec via last_exec_ms.
    import bot.run as runmod
    from bot import carry as carry_mod
    from dataclasses import asdict
    t0 = int(pd.Timestamp("2026-10-05 04:00", tz="UTC").timestamp() * 1000)
    t_book, t_carry = t0 + 60_000, t0 + 120_000
    book_link = "b0BTCxE"
    book_order = mirror.Order(book_link, "BTCUSDT", "Buy", 0.01, "entry",
                              price=80000.0, position_idx=1, piece="b0BTCx",
                              meta=dict(kind="book", phase=0))
    cstate = {"positions": {"BTC": dict(
        coin="BTC", symbol="BTCQ", category="linear", spot_symbol="BTCUSDT",
        qty=0.03, S_entry=80000.0, F_entry=82000.0, delivery_ms=t0 + 90 * 86_400_000,
        entry_time="2026-10-05", spot_filled=False, fut_filled=False,
        S_fill=None, F_fill=None, spot_qty_filled=0.0, fut_qty_filled=0.0,
        spot_link="cBTCtS", fut_link="cBTCtF", unhedged_cycles=0, attempts=1)},
        "entered": [], "history": []}
    ex = _RaceFakeExchange(
        linear=[dict(execId="book1", orderLinkId=book_link, execQty="0.01",
                     execPrice="80000", execTime=str(t_book)),
                dict(execId="cfut1", orderLinkId="cBTCtF", execQty="0.03",
                     execPrice="82000", execTime=str(t_carry))],
        spot=[dict(execId="cspot1", orderLinkId="cBTCtS", execQty="0.03",
                    execPrice="80000", execTime=str(t_carry))])
    r = runmod.Runner.__new__(runmod.Runner)
    r.mode, r.carry_f = "testnet", 0.25
    r.state = {"ledger": {}, "links": {book_link: dict(order=asdict(book_order))},
               "last_exec_ms": t0, "seen_exec": [], "carry": cstate}
    r.ex = ex
    r.logs = []
    r.log = lambda rec: r.logs.append(rec)
    r.inst = dict(INST)
    r._carry_sync()
    # Carry saw both its legs; the book cursor must not have jumped past the book fill.
    assert r.state["carry"]["positions"]["BTC"].get("spot_filled") is True
    assert r.state["carry"]["positions"]["BTC"].get("fut_filled") is True
    assert int(r.state.get("last_exec_ms") or 0) <= t_book
    r.sync_fills()
    assert r.state["ledger"].get("b0BTCx", {}).get("qty", 0) > 0
