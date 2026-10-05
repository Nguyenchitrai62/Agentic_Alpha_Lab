import hashlib
import hmac

import pandas as pd

from bot import mirror
from bot.bybit_v5 import round_step, sign
from bot.run import to_exchange

T0 = pd.Timestamp("2026-10-05 04:00", tz="UTC")
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
        "SOLUSDT": dict(qty_step="0.1", min_qty="0.1", min_notional="5", tick="0.01")}


def plan(subs=None, dips=None):
    return {"generated_at": str(T0), "phases": [{"phase": p, "capital": 0.25} for p in range(4)],
            "coins": {"BTCUSDT": {"subs": subs or [], "dips": dips or []}}}


def pending(phase=0, side="BUY", price=80000.0, weight=0.2):
    return {"phase": phase, "state": "pending", "order": {"kind": "open", "side": side, "price": price, "weight": weight,
                                                           "issued": str(T0), "valid_until": str(T0 + pd.Timedelta(hours=4)),
                                                           "sl_if_filled": 70000.0, "tp_if_filled": 95000.0}}


def dip(rung, phase=0, lv=78000.0, frac=0.05, stop=None):
    return {"rung": rung, "phase": phase, "buy_limit": lv, "tp": lv * 1.01, "stop": stop or lv * 0.96, "backstop": lv * 0.92,
            "size_frac": frac, "active_from": str(T0 + pd.Timedelta(minutes=16)), "active_until": str(T0 + pd.Timedelta(minutes=239))}


def test_book_entry_window_and_size():
    p = plan([pending()])
    assert mirror.desired(p, T0 + pd.Timedelta(minutes=2), 10000, {}) == {}          # first 5 minutes after the close: nothing
    w = mirror.desired(p, T0 + pd.Timedelta(minutes=6), 10000, {})
    (o,) = w.values()
    assert o.kind == "entry" and o.side == "Buy" and o.position_idx == 1 and abs(o.qty - 0.2 * 10000 / 80000) < 1e-12
    assert mirror.desired(p, T0 + pd.Timedelta(hours=4), 10000, {}) == {}             # expired: never chased
    s = mirror.desired(plan([pending(side="SELL")]), T0 + pd.Timedelta(minutes=6), 10000, {})
    assert next(iter(s.values())).position_idx == 2                                    # shorts on the hedge-mode short side


def test_filled_book_piece_gets_exits_and_amend():
    o = next(iter(mirror.desired(plan([pending()]), T0 + pd.Timedelta(minutes=6), 10000, {}).values()))
    led = {}
    mirror.apply_fill(led, o, 0.025, 80000.0, T0 + pd.Timedelta(minutes=30))
    pos = {"phase": 0, "state": "position", "position": {"side": "LONG", "sl": 70000.0, "tp": 95000.0}}
    w = mirror.desired(plan([pos]), T0 + pd.Timedelta(hours=1), 10000, led)
    assert {x.kind for x in w.values()} == {"stop", "tp"}
    stop = next(x for x in w.values() if x.kind == "stop")
    assert stop.side == "Sell" and stop.reduce_only and stop.trigger == 70000.0 and abs(stop.qty - 0.025) < 1e-12
    have = {k: dict(symbol="BTCUSDT", price=x.price, trigger=x.trigger, qty=x.qty) for k, x in w.items()}
    pos["position"]["sl"] = 80100.0                                                  # break-even move in the plan
    acts = mirror.diff(mirror.desired(plan([pos]), T0 + pd.Timedelta(hours=2), 10000, led), have)
    assert acts == [dict(op="amend", link=stop.link, symbol="BTCUSDT", trigger=80100.0)]


def test_dip_budget_shallow_first():
    # per sub-book budget 0.26 * 0.25 = 0.065; each rung costs 0.5 * (0.04 + 0.02) = 0.03 -> only two rungs rest
    p = plan(dips=[dip(4.0, frac=0.5), dip(2.5, frac=0.5), dip(3.0, frac=0.5)])
    w = mirror.desired(p, T0 + pd.Timedelta(minutes=20), 10000, {})
    assert sorted(o.link[:-1] for o in w.values()) == sorted(mirror.dip_pid(0, "BTCUSDT", k, T0) for k in (2.5, 3.0))
    assert mirror.desired(p, T0 + pd.Timedelta(minutes=10), 10000, {}) == {}          # bids live from minute 16 only


def test_dip_exits_close5_and_time():
    o = next(iter(mirror.desired(plan(dips=[dip(2.5)]), T0 + pd.Timedelta(minutes=20), 10000, {}).values()))
    led = {}
    mirror.apply_fill(led, o, 0.006, 78000.0, T0 + pd.Timedelta(minutes=21))
    (pid,) = led
    p = plan()
    assert mirror.exits(p, T0 + pd.Timedelta(minutes=26), led, {"BTCUSDT": (T0 + pd.Timedelta(minutes=25), 77000.0)}) == []
    assert mirror.exits(p, T0 + pd.Timedelta(minutes=26), led, {"BTCUSDT": (T0 + pd.Timedelta(minutes=25), 74800.0)}) == [(pid, "close5_stop")]
    # a 5m bar that closed before the fill never stops the rung
    assert mirror.exits(p, T0 + pd.Timedelta(minutes=21), led, {"BTCUSDT": (T0 + pd.Timedelta(minutes=20), 70000.0)}) == []
    assert mirror.exits(p, T0 + pd.Timedelta(hours=4), led, {}) == [(pid, "time_exit")]
    w = mirror.desired(p, T0 + pd.Timedelta(minutes=30), 10000, led)
    assert {x.kind for x in w.values()} == {"tp", "stop"}                               # TP limit + native backstop rest


def test_plan_closed_divergence_after_grace():
    o = next(iter(mirror.desired(plan([pending()]), T0 + pd.Timedelta(minutes=6), 10000, {}).values()))
    led = {}
    mirror.apply_fill(led, o, 0.025, 80000.0, T0)
    (pid,) = led
    led[pid]["plan_gone_since"] = str(T0 + pd.Timedelta(hours=1))
    assert mirror.exits(plan(), T0 + pd.Timedelta(hours=1, minutes=1), led, {}) == []
    assert mirror.exits(plan(), T0 + pd.Timedelta(hours=1, minutes=3), led, {}) == [(pid, "plan_closed_divergence")]


def test_diff_cancels_and_places():
    o = mirror.Order("x1", "BTCUSDT", "Buy", 0.01, "entry", price=1.0)
    acts = mirror.diff({"x1": o}, {"old": dict(symbol="BTCUSDT", price=2.0, qty=0.01)})
    assert acts == [dict(op="cancel", link="old", symbol="BTCUSDT"), dict(op="place", order=o)]


def test_rounding_and_payloads():
    assert round_step(0.0129, "0.001") == "0.012" and round_step(1.2345, "0.01", up=True) == "1.24"
    buy = to_exchange(mirror.Order("e", "BTCUSDT", "Buy", 0.0129, "entry", price=80000.06), INST)
    assert buy["qty"] == "0.012" and buy["price"] == "80000" and buy["timeInForce"] == "GTC"
    assert to_exchange(mirror.Order("e", "BTCUSDT", "Buy", 0.0004, "entry", price=80000.0), INST) is None   # below the lot minimum
    st = to_exchange(mirror.Order("s", "SOLUSDT", "Sell", 1.25, "stop", trigger=100.006, reduce_only=True), INST)
    assert st["orderType"] == "Market" and st["triggerPrice"] == "100" and st["triggerDirection"] == 2 and st["reduceOnly"]
    sst = to_exchange(mirror.Order("s", "SOLUSDT", "Buy", 1.25, "stop", trigger=100.001, reduce_only=True, position_idx=2), INST)
    assert sst["triggerPrice"] == "100.01" and sst["triggerDirection"] == 1


def test_sign_matches_hmac():
    want = hmac.new(b"sec", b"1700000000000keyX10000a=1", hashlib.sha256).hexdigest()
    assert sign("sec", "1700000000000", "keyX", "10000", "a=1") == want


class FakePublic:
    """Bybit public client stand-in: 1m klines from a dict symbol -> list of (start_ms, o, h, l, c)."""
    def __init__(self, bars):
        self.bars = bars

    def public(self, path, **kw):
        rows = [b for b in self.bars[kw["symbol"]] if kw["start"] <= b[0] <= kw["end"]]
        return {"list": [[str(b[0])] + [str(x) for x in b[1:]] + ["0", "0"] for b in reversed(rows)]}


def test_paper_exchange_fills(tmp_path):
    from bot.paper import PaperExchange
    m0 = int(pd.Timestamp("2026-10-05 05:00", tz="UTC").timestamp() * 1000)
    bars = {"BTCUSDT": [(m0 + 60_000 * k, *b) for k, b in enumerate([(100, 101, 99.5, 100), (100, 100, 98.9, 99), (99, 99.5, 97, 97.5),
                                                                       (97.5, 102, 97.5, 101)])]}
    ex = PaperExchange(FakePublic(bars), tmp_path / "x.json", 1000.0, ["BTCUSDT"])
    ex.s["last_ms"]["BTCUSDT"] = m0
    ex.s["last_close"]["BTCUSDT"] = 100.0
    ex.place(dict(symbol="BTCUSDT", side="Buy", qty="1", orderLinkId="e", positionIdx=1, orderType="Limit", price="99", timeInForce="GTC"))
    ex.s["orders"]["e"]["t_ms"] = m0 - 1
    ex.step(pd.Timestamp(m0 + 2 * 60_000, unit="ms", tz="UTC"))               # minute 1 low 98.9 < 99 -> filled at 99 (maker)
    assert ex.s["pos"]["BTCUSDT|1"]["qty"] == 1.0 and ex.s["pos"]["BTCUSDT|1"]["avg"] == 99.0
    ex.place(dict(symbol="BTCUSDT", side="Sell", qty="1", orderLinkId="s", positionIdx=1, orderType="Market", triggerPrice="98",
                  triggerDirection=2, reduceOnly=True))
    ex.place(dict(symbol="BTCUSDT", side="Sell", qty="1", orderLinkId="t", positionIdx=1, orderType="Limit", price="99.4", reduceOnly=True))
    for k in ("s", "t"):
        ex.s["orders"][k]["t_ms"] = m0 + 60_000
    ex.step(pd.Timestamp(m0 + 3 * 60_000, unit="ms", tz="UTC"))               # minute 2: high 99.5 > TP and low 97 <= stop -> stop first
    assert ex.s["pos"]["BTCUSDT|1"]["qty"] == 0.0
    fills = {e["orderLinkId"]: float(e["execPrice"]) for e in ex.s["execs"]}
    assert fills == {"e": 99.0, "s": 98.0}
    exp_cash = 1000 - 0.0002 * 99 + (98 - 99) - 0.00055 * 98
    assert abs(ex.s["cash"] - exp_cash) < 1e-9
    ex.step(pd.Timestamp(m0 + 4 * 60_000, unit="ms", tz="UTC"))               # reduce-only TP with a flat position is dropped
    assert "t" not in ex.s["orders"]
