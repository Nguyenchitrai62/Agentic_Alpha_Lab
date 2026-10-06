"""Review demos for soakfix 40e5fdf + bot_reviewfix2 #1-#6 and carry-slice retry. Pure logic + fake exchange only. No network, no keys."""
import json
from dataclasses import asdict

import pandas as pd

from bot import carry, mirror
from bot.bybit_v5 import BybitError

T0 = pd.Timestamp("2026-10-05 04:00", tz="UTC")
NOW = T0 + pd.Timedelta(hours=1)


def _plan(subs=None, sym="BTCUSDT"):
    return {"generated_at": str(T0), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {sym: {"subs": subs or [], "dips": []}}}


def test_review_dip_without_backstop_has_native_stop():
    # Finding #1: open dip piece with backstop=None must still end the cycle with stop+TP.
    led = {"d1": dict(kind="dip", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      tp=80000.0, backstop=None, stop5=75000.0)}
    sub = {"phase": 0, "state": "position",
           "position": {"side": "LONG", "sl": 75000.0, "tp": 80000.0}}
    w = mirror.desired(_plan([sub]), NOW, 10000, led)
    assert "d1T" in w
    assert "d1S" in w, f"dip without backstop has no native stop: {sorted(w)}"


def test_review_tp_zero_keeps_valid_plan_sl():
    # Finding #4: plan tp=0 with a valid tightened plan SL should keep the plan SL, not revert both to entry levels.
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      sl=70000.0, tp=95000.0)}
    sub = {"phase": 0, "state": "position",
           "position": {"side": "LONG", "sl": 79000.0, "tp": 0.0}}
    rej = []
    w = mirror.desired(_plan([sub]), NOW, 10000, led, on_reject=rej.append)
    assert "p1S" in w and "p1T" in w
    assert w["p1S"].trigger == 79000.0, f"valid plan SL discarded on tp=0: {w['p1S'].trigger}"


def test_review_restart_does_not_strip_resting_protection():
    # Finding #2: persisted exit_sent (restart after a logged-but-unfilled market exit) must not
    # cancel the still-resting stop/TP when no exit order is actually in flight.
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      sl=70000.0, tp=95000.0,
                      exit_sent=str(NOW - pd.Timedelta(seconds=30)))}
    sub = {"phase": 0, "state": "position",
           "position": {"side": "LONG", "sl": 70000.0, "tp": 95000.0}}
    w = mirror.desired(_plan([sub]), NOW, 10000, led)
    have = {"p1S": dict(symbol="BTCUSDT", trigger=70000.0, qty=0.02),
            "p1T": dict(symbol="BTCUSDT", price=95000.0, qty=0.02)}
    acts = mirror.diff(w, have)
    cancels = [a for a in acts if a["op"] == "cancel"]
    assert not cancels, f"resting protection stripped while no exit in flight: {cancels}"


# ---- bot_reviewfix2 #3: _protection_only respects in-flight + validates ----

def _protection_runner(inst):
    from bot.run import Runner
    r = Runner.__new__(Runner)
    r.inst = dict(inst)
    return r


def test_reviewfix2_protection_only_respects_inflight():
    inst = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}
    r = _protection_runner(inst)
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      sl=70000.0, tp=95000.0,
                      exit_sent=str(NOW), exit_link="p1Xabc")}
    assert r._protection_only(led, NOW) == {}
    led2 = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                       sl=70000.0, tp=95000.0,
                       exit_sent=str(NOW))}  # phantom: no exit_link
    w2 = r._protection_only(led2, NOW)
    assert "p1S" in w2 and "p1T" in w2


def test_reviewfix2_protection_only_skips_corrupt_without_raise():
    inst = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}
    r = _protection_runner(inst)
    led = {"bad": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                       sl="oops", tp=95000.0),
           "good": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                        sl=70000.0, tp=95000.0)}
    w = r._protection_only(led, NOW)
    assert "badS" not in w and "badT" not in w
    assert "goodS" in w and "goodT" in w


def test_reviewfix2_protection_only_dip_without_backstop():
    inst = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}
    r = _protection_runner(inst)
    led = {"d1": dict(kind="dip", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      tp=80000.0, backstop=None, stop5=75000.0)}
    w = r._protection_only(led, NOW)
    assert "d1T" in w and "d1S" in w


# ---- bot_reviewfix2 #4 per-leg: sl=0 keeps valid plan TP ----

def test_reviewfix2_sl_zero_keeps_valid_plan_tp():
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      sl=70000.0, tp=95000.0)}
    sub = {"phase": 0, "state": "position",
           "position": {"side": "LONG", "sl": 0.0, "tp": 96000.0}}
    rej = []
    w = mirror.desired(_plan([sub]), NOW, 10000, led, on_reject=rej.append)
    assert w["p1T"].price == 96000.0
    assert w["p1S"].trigger == 70000.0
    assert any(x.get("op") == "plan_reject" for x in rej)


# ---- bot_reviewfix2 #6: wrong-side SL/TP rejected, fallback to entry ----

def test_reviewfix2_wrong_side_long_falls_back():
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      sl=70000.0, tp=95000.0)}
    sub = {"phase": 0, "state": "position",
           "position": {"side": "LONG", "sl": 85000.0, "tp": 95000.0}}
    rej = []
    w = mirror.desired(_plan([sub]), NOW, 10000, led,
                       last_close={"BTCUSDT": 80000.0}, on_reject=rej.append)
    assert any(x.get("op") == "plan_reject" and x.get("reason") == "book_protect_wrong_side" for x in rej), rej
    assert w["p1S"].trigger == 70000.0 and w["p1T"].price == 95000.0


def test_reviewfix2_wrong_side_short_falls_back():
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=-1, qty=0.02,
                      sl=90000.0, tp=70000.0)}
    sub = {"phase": 0, "state": "position",
           "position": {"side": "SHORT", "sl": 75000.0, "tp": 70000.0}}
    rej = []
    w = mirror.desired(_plan([sub]), NOW, 10000, led,
                       last_close={"BTCUSDT": 80000.0}, on_reject=rej.append)
    assert any(x.get("op") == "plan_reject" and x.get("reason") == "book_protect_wrong_side" for x in rej), rej
    assert w["p1S"].trigger == 90000.0 and w["p1T"].price == 70000.0


def test_reviewfix2_no_mark_no_wrong_side_check():
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02,
                      sl=70000.0, tp=95000.0)}
    sub = {"phase": 0, "state": "position",
           "position": {"side": "LONG", "sl": 85000.0, "tp": 95000.0}}
    w = mirror.desired(_plan([sub]), NOW, 10000, led)
    assert w["p1S"].trigger == 85000.0  # no mark available: plan levels pass through


# ---- bot_reviewfix2 #5: TP failures count like stops ----

class _FakeEx:
    def __init__(self, inst, equity=10000.0):
        self.inst_map = dict(inst)
        self._equity = equity
        self.orders = {}
        self.execs = []
        self.fail_links = set()

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
        return [dict(orderLinkId=k, symbol=v["symbol"], price=v.get("price"),
                     triggerPrice=v.get("triggerPrice"), qty=v.get("qty"))
                for k, v in self.orders.items()]

    def executions(self, start_ms):
        return [e for e in self.execs if int(e["execTime"]) >= int(start_ms)]

    def place(self, p):
        link = p.get("orderLinkId")
        if link in self.fail_links:
            raise BybitError("simulated place fail " + str(link))
        self.orders[link] = dict(p)
        return dict(orderLinkId=link)

    def amend(self, symbol, link, **kw):
        if link not in self.orders:
            return None
        self.orders[link].update(kw)
        return dict(orderLinkId=link)

    def cancel(self, symbol, link):
        return self.orders.pop(link, None) and dict(orderLinkId=link)


def _mk_runner(tmp_path, plan_dict, state_dict, ex):
    import json as _json
    from bot.run import Runner
    d = tmp_path / "botstate_rf2"
    d.mkdir(parents=True, exist_ok=True)
    plan_f = d / "plan.json"
    plan_f.write_text(_json.dumps(plan_dict))
    r = Runner.__new__(Runner)
    r.mode = "paper"
    r.plan_path = plan_f
    r.risk_mult, r.corr, r.tag, r.dip_mult = 1.0, False, None, 1.0
    r.bear_book, r.adopt_fresh, r.no_risk_guard = False, False, True
    r.carry_f, r.dip_cooldown_h, r.dip_sl_coin, r.dip_gross_cap = 0.0, 0.0, {}, 0.0
    r._bear_at, r._bear, r._last_plan, r._skip_logged = None, False, None, {}
    r.maint_start, r.maint_end, r._maint_active = None, None, False
    r._kline_cache_dir_override = None
    r.dir, r.state_f, r.state, r.ex = d, d / "state.json", state_dict, ex
    r.state_f.write_text(_json.dumps(state_dict, default=str))
    r.equity_arg, r.inst, r.logs = 10000.0, dict(ex.inst_map), []

    def _log(rec):
        r.logs.append(rec)
        with open(r.dir / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, default=str) + "\n")

    r.log = _log
    return r


def test_reviewfix2_tp_failure_triggers_unprotected_close(tmp_path):
    inst = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}
    plan = {"generated_at": str(pd.Timestamp.now(tz="UTC")), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"BTCUSDT": {"subs": [{"phase": 0, "state": "position",
                                            "position": {"side": "LONG", "sl": 70000.0, "tp": 95000.0}}], "dips": []}}}
    led = {"p1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02, sl=70000.0, tp=95000.0)}
    ex = _FakeEx(inst)
    r = _mk_runner(tmp_path, plan, {"ledger": dict(led), "links": {}, "last_exec_ms": 0}, ex)
    ex.fail_links.add("p1T")  # every TP placement fails; stops succeed
    for _ in range(3):
        r.cycle()
    kinds = [rec.get("op") for rec in r.logs]
    assert "unprotected_close" in kinds, kinds


# ---- bot_reviewfix2 carry: done-after-fill + same-bucket retry ----

def _cms(ts):
    return int(pd.Timestamp(ts).timestamp() * 1000)


def _cexp(now):
    n = _cms(now)
    return {"BTC": [dict(symbol="BTC-FRONT", category="linear", delivery_ms=n + 3 * 86_400_000),
                    dict(symbol="BTC-NEXTQ", category="linear", delivery_ms=n + 90 * 86_400_000)]}


def _cquo(spot=80000.0, fut=82000.0, sym="BTC-NEXTQ"):
    return {"BTC": dict(spot_mid=spot, spot_ask=spot, spot_bid=spot,
                        fut_by_sym={sym: dict(bid=fut, ask=fut, mid=fut)})}


def _clots(sym="BTC-NEXTQ"):
    return {"BTCUSDT": dict(qty_step="0.01", min_qty="0.001", min_notional="5", tick="0.1"),
            sym: dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}

# carry slice retry NOT adopted (leader 2026-10-07): a re-sent slice after a restart could double-sell;
# a missed slice is sold with the post-delivery remainder instead (500bf18 behaviour).
