"""bot_testnetfix (F1 PostOnly + V4 risk guard wiring). No network, no keys, fake exchange only."""
import json
from dataclasses import asdict

import pandas as pd

from bot import mirror
from bot.bybit_v5 import BybitError
from bot.run import Runner, _is_postonly_reject_msg, to_exchange

T0 = pd.Timestamp("2026-10-05 04:00", tz="UTC")
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
        "ETHUSDT": dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01")}


class FakeExchange:
    def __init__(self, equity=10000.0, reject_postonly=False, fail_postonly_msg=None):
        self._equity = equity
        self.orders = {}
        self.execs = []
        self.place_calls = []
        self.place_payloads = []
        self.reject_postonly = reject_postonly
        self.fail_postonly_msg = fail_postonly_msg
        self.s = {"last_close": {"BTCUSDT": 80000.0, "ETHUSDT": 3000.0}, "last_ms": {}}
        self.saved = 0

    def instruments(self, symbols):
        return {s: INST[s] for s in symbols}

    def equity_usdt(self):
        return self._equity

    def step(self, now=None):
        return None

    def save(self):
        self.saved += 1

    def klines(self, symbol, interval="5", limit=3):
        return []

    def open_orders(self):
        return [dict(orderLinkId=k, symbol=v["symbol"], price=v.get("price"),
                      triggerPrice=v.get("triggerPrice"), qty=v.get("qty"))
                for k, v in self.orders.items()]

    def executions(self, start_ms):
        return [e for e in self.execs if int(e["execTime"]) >= int(start_ms)]

    def place(self, p):
        self.place_calls.append(p.get("orderLinkId"))
        self.place_payloads.append(dict(p))
        if p.get("timeInForce") == "PostOnly":
            if self.fail_postonly_msg is not None:
                raise BybitError(self.fail_postonly_msg)
            if self.reject_postonly:
                return None  # paper-style PostOnly cross reject
        self.orders[p["orderLinkId"]] = dict(p)
        return dict(orderLinkId=p["orderLinkId"])

    def amend(self, symbol, link, **kw):
        if link not in self.orders:
            return None
        self.orders[link].update(kw)
        return dict(orderLinkId=link)

    def cancel(self, symbol, link):
        return self.orders.pop(link, None) and dict(orderLinkId=link)


def _mk_runner(tmp_path, plan_dict, state_dict, ex, mode="paper", **kw):
    d = tmp_path / "botstate"
    d.mkdir(parents=True, exist_ok=True)
    plan_f = d / "plan.json"
    plan_f.write_text(json.dumps(plan_dict))
    r = Runner.__new__(Runner)
    r.mode = mode
    r.plan_path = plan_f
    r.risk_mult = float(kw.get("risk_mult", 1.0))
    r.corr = bool(kw.get("corr", False))
    r.tag = None
    r.dip_mult = float(kw.get("dip_mult", 1.0))
    r.bear_book = bool(kw.get("bear_book", False))
    r.dip_cooldown_h = float(kw.get("dip_cooldown_h", 0.0))
    r.dip_sl_coin = dict(kw.get("dip_sl_coin", {}))
    r.dip_gross_cap = float(kw.get("dip_gross_cap", 0.0) or 0.0)
    r.adopt_fresh = bool(kw.get("adopt_fresh", False))
    r.no_risk_guard = bool(kw.get("no_risk_guard", False))
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

    def _log(rec):
        r.logs.append(rec)
        with open(r.dir / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    r.log = _log
    return r


def _pending_plan(weight=0.2, price=80000.0):
    now = pd.Timestamp.now(tz="UTC")
    return {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"BTCUSDT": {"subs": [{"phase": 0, "state": "pending",
                                             "order": {"kind": "open", "side": "BUY", "price": price, "weight": weight,
                                                       "issued": str(now - pd.Timedelta(minutes=10)),
                                                       "valid_until": str(now + pd.Timedelta(hours=4)),
                                                       "sl_if_filled": 70000.0, "tp_if_filled": 95000.0}}], "dips": []}}}


# ---- F1: PostOnly ----

def test_entry_is_postonly_tp_reduce_stay_gtc():
    book_entry = mirror.Order("e1", "BTCUSDT", "Buy", 0.02, "entry", price=80000.0,
                              meta=dict(kind="book", phase=0))
    p = to_exchange(book_entry, INST)
    assert p["orderType"] == "Limit" and p["timeInForce"] == "PostOnly" and "reduceOnly" not in p
    dip_entry = mirror.Order("d1", "BTCUSDT", "Buy", 0.02, "entry", price=78000.0,
                             meta=dict(kind="dip", phase=0))
    assert to_exchange(dip_entry, INST)["timeInForce"] == "PostOnly"
    add = mirror.Order("a1", "BTCUSDT", "Buy", 0.02, "add", price=80000.0)
    assert to_exchange(add, INST)["timeInForce"] == "PostOnly"
    tp = mirror.Order("t1", "BTCUSDT", "Sell", 0.02, "tp", price=95000.0, reduce_only=True, piece="p")
    pt = to_exchange(tp, INST)
    assert pt["timeInForce"] == "GTC" and pt["reduceOnly"] is True
    red = mirror.Order("r1", "BTCUSDT", "Sell", 0.02, "reduce", price=81000.0, reduce_only=True, piece="p")
    assert to_exchange(red, INST)["timeInForce"] == "GTC"
    stop = mirror.Order("s1", "BTCUSDT", "Sell", 0.02, "stop", trigger=70000.0, reduce_only=True, piece="p")
    ps = to_exchange(stop, INST)
    assert ps["orderType"] == "Market" and "timeInForce" not in ps


def test_is_postonly_reject_msg():
    assert _is_postonly_reject_msg("110079: PostOnly order would cross")
    assert _is_postonly_reject_msg("170146: post-only will be rejected")
    assert _is_postonly_reject_msg("PostOnly order crosses")
    assert not _is_postonly_reject_msg("10006: Too many visits")
    assert not _is_postonly_reject_msg("some timeout")


def test_postonly_reject_paper_none_logs_and_retries(tmp_path):
    plan = _pending_plan()
    ex = FakeExchange(reject_postonly=True)  # paper-style: place returns None
    r = _mk_runner(tmp_path, plan, {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    acts = r.cycle()
    assert any(rec.get("op") == "postonly_reject" for rec in r.logs)
    # rejected: nothing recorded, so next cycle retries the same entry (never market)
    assert r.state["links"] == {}
    assert not [p for p in ex.place_payloads if p.get("orderType") == "Market"]
    assert any(a.get("op") == "place" for a in acts)
    r.logs.clear()
    acts2 = r.cycle()
    assert any(rec.get("op") == "postonly_reject" for rec in r.logs)
    assert any(a.get("op") == "place" for a in acts2)
    assert not [p for p in ex.place_payloads if p.get("orderType") == "Market"]


def test_postonly_reject_bybit_error_logs_not_error(tmp_path):
    plan = _pending_plan()
    ex = FakeExchange(fail_postonly_msg="110079: PostOnly order would cross, reject")
    r = _mk_runner(tmp_path, plan, {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()
    assert any(rec.get("op") == "postonly_reject" for rec in r.logs)
    assert not [rec for rec in r.logs if rec.get("op") == "error"]
    assert r.state["links"] == {}  # retry next cycle at the same price
    assert not [p for p in ex.place_payloads if p.get("orderType") == "Market"]


# ---- V4: risk guard wiring ----

def test_guard_blocks_oversize_entry_and_logs(tmp_path):
    # weight 2.0 x 10000 / 80000 = 0.25 BTC ~ 20000 notional > single 1x cap
    plan = _pending_plan(weight=2.0)
    ex = FakeExchange()
    r = _mk_runner(tmp_path, plan, {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()
    assert any(rec.get("op") == "risk_reject" for rec in r.logs)
    assert ex.place_calls == []  # rejected orders are not sent
    assert r.state["links"] == {}


def test_guard_never_blocks_protection(tmp_path):
    led = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.05,
                       entry=80000.0, sl=70000.0, tp=95000.0, opened=str(T0))}
    plan = {"generated_at": str(pd.Timestamp.now(tz="UTC")), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"BTCUSDT": {"subs": [{"phase": 0, "state": "position",
                                            "position": {"side": "LONG", "sl": 70000.0, "tp": 95000.0}}], "dips": []}}}
    ex = FakeExchange(equity=1.0)  # tiny equity: entries would fail, protection must pass
    r = _mk_runner(tmp_path, plan, {"ledger": led, "links": {}, "last_exec_ms": 0}, ex)
    r.ex._equity = 1.0
    r.cycle()
    # stops/TPs are reduce-only: no risk_reject against them, and they are placed
    assert not [rec for rec in r.logs if rec.get("op") == "risk_reject" and rec.get("link", "").endswith(("S", "T"))]
    assert ex.place_calls  # protection placed despite tiny equity


def test_no_risk_guard_flag_disables(tmp_path):
    plan = _pending_plan(weight=2.0)
    ex = FakeExchange()
    r = _mk_runner(tmp_path, plan, {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex, no_risk_guard=True)
    assert r.no_risk_guard is True
    r.cycle()
    assert not [rec for rec in r.logs if rec.get("op") == "risk_reject"]
    assert ex.place_calls  # oversize entry passes through when the guard is off


def test_guard_default_on_and_small_orders_pass(tmp_path):
    r = Runner.__new__(Runner)
    assert getattr(r, "no_risk_guard", False) is False  # default guard ON (attr absent -> on)
    plan = _pending_plan(weight=0.02)  # ~16 USDT notional: well inside every cap
    ex = FakeExchange()
    r2 = _mk_runner(tmp_path, plan, {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    r2.cycle()
    assert not [rec for rec in r2.logs if rec.get("op") == "risk_reject"]
    assert ex.place_calls  # normal paper behaviour identical: small entries still placed
    assert ex.place_payloads[0].get("timeInForce") == "PostOnly"


def test_guard_per_coin_cap_uses_open_positions(tmp_path):
    # 0.28 BTC open ~22400; +0.02 (~1600) fits 2.5x cap 25000, +0.05 (~4000) exceeds
    led = {"p1": dict(symbol="BTCUSDT", side=1, qty=0.28, entry=80000.0, kind="book", phase=0)}
    plan = _pending_plan(weight=0.05)  # 0.05*10000/80000 = 0.00625 BTC ~500 notional... too small
    # use a bigger weight so a single entry alone exceeds the remaining per-coin room
    plan = _pending_plan(weight=1.0)  # 0.125 BTC ~10000 notional; 22400+10000 > 25000
    ex = FakeExchange()
    r = _mk_runner(tmp_path, plan, {"ledger": dict(led), "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()
    rej = [rec for rec in r.logs if rec.get("op") == "risk_reject"]
    assert rej and rej[0].get("reason") == "per_coin_cap"
    assert ex.place_calls == []
