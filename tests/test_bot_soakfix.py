"""bot_soakfix (B1/B2/B3): protection for every book piece, dust guards, plan_reject. No network, no keys."""
import json
import math
from dataclasses import asdict

import pandas as pd

from bot import mirror

T0 = pd.Timestamp("2026-10-05 04:00", tz="UTC")
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
        "SOLUSDT": dict(qty_step="0.1", min_qty="0.1", min_notional="5", tick="0.01"),
        "XRPUSDT": dict(qty_step="1", min_qty="1", min_notional="5", tick="0.0001")}


def _plan(subs=None, dips=None, sym="BTCUSDT"):
    return {"generated_at": str(T0), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {sym: {"subs": subs or [], "dips": dips or []}}}


def _pending(price=80000.0, sl=70000.0, tp=95000.0, phase=0):
    return {"phase": phase, "state": "pending",
            "order": {"kind": "open", "side": "BUY", "price": price, "weight": 0.2,
                      "issued": str(T0), "valid_until": str(T0 + pd.Timedelta(hours=4)),
                      "sl_if_filled": sl, "tp_if_filled": tp}}


def _dip(rung=2.5, lv=78000.0, tp=None, stop=None, frac=0.05, phase=0):
    lv = float(lv)
    return {"rung": rung, "phase": phase, "buy_limit": lv, "tp": float(tp) if tp is not None else lv * 1.01,
            "stop": float(stop) if stop is not None else lv * 0.96, "backstop": lv * 0.92,
            "size_frac": frac, "active_from": str(T0 + pd.Timedelta(minutes=16)),
            "active_until": str(T0 + pd.Timedelta(minutes=239))}


# ---- B1: every open book piece of a (phase, symbol) gets stop + TP ----

def test_b1_two_book_pieces_both_protected_after_side_flip():
    # side flip: old LONG piece not yet diverged + new SHORT piece filled in the same sub-book.
    led = {
        "pOLD": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02, sl=70000.0, tp=95000.0),
        "pNEW": dict(kind="book", phase=0, symbol="BTCUSDT", side=-1, qty=0.03, sl=90000.0, tp=70000.0),
    }
    sub = {"phase": 0, "state": "position",
           "position": {"side": "SHORT", "sl": 90000.0, "tp": 70000.0}}
    w = mirror.desired(_plan([sub]), T0 + pd.Timedelta(hours=1), 10000, led)
    for pid in ("pOLD", "pNEW"):
        assert pid + "S" in w, (pid, sorted(w))
        assert pid + "T" in w, (pid, sorted(w))
        assert w[pid + "S"].kind == "stop" and w[pid + "T"].kind == "tp"
    # sides follow each piece (long sells, short buys back)
    assert w["pOLDS"].side == "Sell" and w["pNEWS"].side == "Buy"
    # the orphan LONG keeps its own levels (stop below, TP above), not the SHORT plan's
    assert w["pOLDS"].trigger == 70000.0 and w["pOLDT"].price == 95000.0
    assert w["pNEWS"].trigger == 90000.0 and w["pNEWT"].price == 70000.0
    assert w["pOLDS"].position_idx == 1 and w["pNEWS"].position_idx == 2
    # plan add/reduce stays on the first piece only (no duplication)
    sub_add = {"phase": 0, "state": "position",
               "position": {"side": "SHORT", "sl": 90000.0, "tp": 70000.0},
               "order": {"kind": "reduce", "amount": 0.5, "price": 80000.0,
                         "valid_until": str(T0 + pd.Timedelta(hours=4))}}
    w2 = mirror.desired(_plan([sub_add]), T0 + pd.Timedelta(hours=1), 10000, dict(led))
    reds = [o for o in w2.values() if o.kind == "reduce"]
    assert len(reds) == 1


# ---- B3: non-positive / non-finite plan prices are skipped, never raise ----

def test_b3_zero_dip_rung_skipped_no_zerodivision():
    rej = []
    bad = _dip(4.0, lv=0.0, tp=0.0, stop=0.0)
    good = _dip(2.5, lv=78000.0)
    p = _plan(dips=[bad, good])
    w = mirror.desired(p, T0 + pd.Timedelta(minutes=20), 10000, {}, on_reject=rej.append)
    # the zero rung emits nothing, the good rung still rests
    assert all("40" not in k for k in w), w.keys()
    assert len([o for o in w.values() if o.kind == "entry"]) == 1
    assert any(r.get("op") == "plan_reject" for r in rej), rej


def test_b3_book_entry_nonpositive_and_nonfinite_skipped():
    rej = []
    subs = [_pending(price=0.0), _pending(price=float("inf")), _pending(price=float("nan")),
            _pending(price=80000.0)]
    # each pending maps to a distinct pid only via issued; force distinct issued times
    for i, s in enumerate(subs):
        s["order"] = dict(s["order"], issued=str(T0 + pd.Timedelta(minutes=i)))
    p = _plan(subs=subs)
    w = mirror.desired(p, T0 + pd.Timedelta(minutes=30), 10000, {}, on_reject=rej.append)
    assert len([o for o in w.values() if o.kind == "entry"]) == 1
    assert sum(1 for r in rej if r.get("op") == "plan_reject") >= 3


def test_b3_one_bad_row_keeps_protection_running():
    # open dip piece must keep TP + backstop even when the plan has a zero rung and a bad book row.
    o = next(iter(mirror.desired(_plan(dips=[_dip(2.5)]), T0 + pd.Timedelta(minutes=20), 10000, {}).values()))
    led = {}
    mirror.apply_fill(led, o, o.qty, 78000.0, T0 + pd.Timedelta(minutes=21))
    (pid,) = led
    bad_plan = _plan(subs=[_pending(price=0.0)], dips=[_dip(4.0, lv=0.0, tp=0.0, stop=0.0)])
    rej = []
    w = mirror.desired(bad_plan, T0 + pd.Timedelta(minutes=30), 10000, led, on_reject=rej.append)
    assert pid + "T" in w
    assert any(r.get("op") == "plan_reject" for r in rej)


def test_b3_finite_pos_helper():
    assert mirror._finite_pos(1.0) and mirror._finite_pos("2.5")
    assert not mirror._finite_pos(0.0) and not mirror._finite_pos(-1.0)
    assert not mirror._finite_pos(float("nan")) and not mirror._finite_pos(float("inf"))
    assert not mirror._finite_pos(None) and not mirror._finite_pos("x")


# ---- B2: dust guards ----

def test_b2_entry_and_protection_is_dust():
    sol = INST["SOLUSDT"]
    # normal SOL rung: 0.5 x 150 = 75 notional -> not dust
    assert mirror.entry_is_dust(0.5, 151.0, 148.0, sol) is False
    # qty below lot
    assert mirror.entry_is_dust(0.05, 151.0, 148.0, sol) is True
    # qty*TP below $5
    assert mirror.entry_is_dust(0.1, 10.0, 9.0, sol) is True
    # non-positive price counts as dust
    assert mirror.entry_is_dust(0.5, 0.0, 148.0, sol) is True
    assert mirror.protection_is_dust(0.1, 10.0, 9.0, sol) is True
    assert mirror.protection_is_dust(1.0, 150.0, 140.0, sol) is False
    # float-edge just below the lot cannot rest protection (soak SOL dust): strict like to_exchange.
    assert mirror.entry_is_dust(0.09999999999999987, 177.0, 130.0, sol) is True


class _FakeEx:
    def __init__(self, inst=None, equity=10000.0):
        self.inst_map = inst or INST
        self._equity = equity
        self.orders = {}
        self.execs = []
        self.place_calls = []

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
        self.place_calls.append(p.get("orderLinkId"))
        self.orders[p["orderLinkId"]] = dict(p)
        return dict(orderLinkId=p["orderLinkId"])

    def amend(self, symbol, link, **kw):
        if link not in self.orders:
            return None
        self.orders[link].update(kw)
        return dict(orderLinkId=link)

    def cancel(self, symbol, link):
        return self.orders.pop(link, None) and dict(orderLinkId=link)


def _mk_runner(tmp_path, plan_dict, state_dict, ex, **kw):
    from bot.run import Runner
    d = tmp_path / "botstate"
    d.mkdir(parents=True, exist_ok=True)
    plan_f = d / "plan.json"
    plan_f.write_text(json.dumps(plan_dict))
    r = Runner.__new__(Runner)
    r.mode = "paper"
    r.plan_path = plan_f
    r.risk_mult = float(kw.get("risk_mult", 1.0))
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
    r._bear_at = None
    r._bear = False
    r._last_plan = None
    r._skip_logged = {}
    r.maint_start = r.maint_end = None
    r._maint_active = False
    r._kline_cache_dir_override = None
    r.dir = d
    r.state_f = d / "state.json"
    r.state = state_dict
    r.state_f.write_text(json.dumps(state_dict, default=str))
    r.ex = ex
    r.equity_arg = 10000.0
    r.inst = dict(ex.inst_map)
    r.logs = []

    def _log(rec):
        r.logs.append(rec)
        with open(r.dir / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    r.log = _log
    return r


def test_b2a_dust_entry_skipped_with_dust_skip_log(tmp_path):
    # SOL dust rung: tiny limit so qty*TP < $5 but prices still finite-positive (passes B3, caught by B2a).
    lv, tp, stop = 10.0, 10.08, 9.5
    now = pd.Timestamp.now(tz="UTC")
    row = {"rung": 2.5, "phase": 0, "buy_limit": lv, "tp": tp, "stop": stop, "backstop": 9.0,
           "size_frac": 0.05, "active_from": str(now - pd.Timedelta(minutes=10)),
           "active_until": str(now + pd.Timedelta(minutes=200))}
    # switch fixture coin to SOL
    plan = {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"SOLUSDT": {"subs": [], "dips": [row]}}}
    ex = _FakeEx(equity=100.0)  # qty = 0.05*100/10 = 0.5; 0.5*10.08 = 5.04 just above; force dust via smaller equity
    ex._equity = 50.0  # qty = 0.25; notionals ~2.5 < 5 -> dust
    r = _mk_runner(tmp_path, plan, {"ledger": {}, "links": {}, "last_exec_ms": 0}, ex)
    acts = r.cycle()
    assert any(rec.get("op") == "dust_skip" for rec in r.logs), [rec.get("op") for rec in r.logs]
    places = [a for a in acts if a.get("op") == "place"]
    assert not [a for a in places if getattr(a.get("order"), "kind", "") == "entry"]


def test_b2b_dust_open_piece_closed_same_cycle(tmp_path):
    # open SOL dust piece at the lot minimum whose TP* qty < $5: must market-close, never rest unprotected.
    led = {"dDUST": dict(kind="dip", phase=0, symbol="SOLUSDT", side=1, qty=0.1, entry=10.0,
                         tp=10.08, stop5=9.5, backstop=9.0,
                         t_exit=str(pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=4)),
                         frac=0.05, dist=0.05, opened=str(T0))}
    plan = {"generated_at": str(pd.Timestamp.now(tz="UTC")), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"SOLUSDT": {"subs": [], "dips": []}}}
    ex = _FakeEx(equity=10000.0)
    r = _mk_runner(tmp_path, plan, {"ledger": dict(led), "links": {}, "last_exec_ms": 0}, ex)
    r.cycle()
    kinds = [rec.get("op") for rec in r.logs]
    assert "dust_close" in kinds, kinds
    closes = [rec for rec in r.logs if rec.get("op") == "dust_close"]
    assert closes and closes[0]["piece"] == "dDUST"
    assert closes[0]["payload"]["orderType"] == "Market" and closes[0]["payload"]["reduceOnly"] is True


def test_open_piece_keeps_entry_levels_when_plan_tp_turns_zero():
    # soakfix residual: plan TP flips to 0.0 mid-position -> keep the piece's attached levels, never bare.
    led = {"pX": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.02, sl=70000.0, tp=95000.0)}
    sub = {"phase": 0, "state": "position", "position": {"side": "LONG", "sl": 70000.0, "tp": 0.0}}
    w = mirror.desired(_plan([sub]), T0 + pd.Timedelta(hours=1), 10000, led)
    assert w["pXS"].trigger == 70000.0 and w["pXT"].price == 95000.0
