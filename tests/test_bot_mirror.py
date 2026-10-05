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


def test_fill_before_plan_refresh_is_protected_and_not_closed():
    o = next(iter(mirror.desired(plan([pending()]), T0 + pd.Timedelta(minutes=6), 10000, {}).values()))
    led = {}
    mirror.apply_fill(led, o, 0.025, 80000.0, T0 + pd.Timedelta(minutes=7))
    stale = plan([pending()])                                                        # the plan still shows the pending entry
    w = mirror.desired(stale, T0 + pd.Timedelta(minutes=8), 10000, led)
    assert {x.kind for x in w.values()} == {"stop", "tp"}
    assert next(x for x in w.values() if x.kind == "stop").trigger == 70000.0      # the entry's attached SL
    assert mirror.exits(stale, T0 + pd.Timedelta(minutes=30), led, {}) == []


def _mkrow(rung, open_px=100.0, sigma=0.01, phase=0):
    """Dip row with known bar open / sigma: buy_limit = open(1 - rung*sigma), stop = buy_limit(1 - 4*sigma)."""
    lv = open_px * (1.0 - rung * sigma)
    return {"rung": rung, "phase": phase, "buy_limit": lv, "tp": lv * 1.01, "stop": lv * (1.0 - 4.0 * sigma),
            "backstop": lv * 0.9, "size_frac": 0.05,
            "active_from": str(T0 + pd.Timedelta(minutes=16)), "active_until": str(T0 + pd.Timedelta(minutes=239))}


def test_corr_mult_counts_flushing_peers():
    dips = {"BTCUSDT": [_mkrow(2.0)], "ETHUSDT": [_mkrow(2.0)], "SOLUSDT": [_mkrow(3.0)], "BNBUSDT": [_mkrow(2.5)]}
    # threshold = 100 * (1 - 2.5 * 0.01) = 97.5 for every coin
    assert mirror.corr_mult(dips, {"BTCUSDT": 100.0, "ETHUSDT": 100.0, "SOLUSDT": 100.0, "BNBUSDT": 100.0}, "BTCUSDT") == 1.0
    assert mirror.corr_mult(dips, {"BTCUSDT": 100.0, "ETHUSDT": 97.0, "SOLUSDT": 100.0, "BNBUSDT": 100.0}, "BTCUSDT") == 0.5
    got = mirror.corr_mult(dips, {"BTCUSDT": 100.0, "ETHUSDT": 97.0, "SOLUSDT": 96.0, "BNBUSDT": 90.0}, "BTCUSDT")
    assert abs(got - 0.25) < 1e-12
    # the coin itself never counts, even when it flushes
    assert mirror.corr_mult(dips, {"BTCUSDT": 90.0, "ETHUSDT": 100.0, "SOLUSDT": 100.0, "BNBUSDT": 100.0}, "BTCUSDT") == 1.0
    # missing coins / no data are skipped, never counted
    assert mirror.corr_mult(dips, {"ETHUSDT": 90.0}, "BTCUSDT") == 0.5
    assert mirror.corr_mult(dips, {}, "BTCUSDT") == 1.0
    assert mirror.corr_mult(dips, None, "BTCUSDT") == 1.0
    # boundary: exactly at 2.5 sigma counts, just above does not
    assert mirror.corr_mult(dips, {"ETHUSDT": 97.5, "SOLUSDT": 100.0, "BNBUSDT": 100.0}, "BTCUSDT") == 0.5
    assert mirror.corr_mult(dips, {"ETHUSDT": 97.5001, "SOLUSDT": 100.0, "BNBUSDT": 100.0}, "BTCUSDT") == 1.0


def test_desired_risk_mult_scales_qty_and_budget():
    p = plan([pending(price=80000.0, weight=0.2)])
    base = next(iter(mirror.desired(p, T0 + pd.Timedelta(minutes=6), 10000, {}).values()))
    scaled = next(iter(mirror.desired(p, T0 + pd.Timedelta(minutes=6), 10000, {}, risk_mult=1.3).values()))
    assert abs(scaled.qty / base.qty - 1.3) < 1e-12
    # budget (engine v400 rule): the budget 0.26 k counts sizes that include k, so k cancels - the admitted set is unchanged and only
    # the quantities scale; cost 0.4 * (0.04 + 0.02) = 0.024 vs 0.065 per sub-book admits 2 rungs either way
    q = plan(dips=[dip(2.5, frac=0.4), dip(3.0, frac=0.4), dip(4.0, frac=0.4)])
    assert len(mirror.desired(q, T0 + pd.Timedelta(minutes=20), 10000, {})) == 2
    w = mirror.desired(q, T0 + pd.Timedelta(minutes=20), 10000, {}, risk_mult=1.3)
    assert len(w) == 2
    qb = mirror.desired(plan(dips=[dip(2.5, frac=0.4)]), T0 + pd.Timedelta(minutes=20), 10000, {})
    (kb,) = qb
    assert abs(w[kb].qty / qb[kb].qty - 1.3) < 1e-12


def test_default_off_equals_old_outputs():
    p = plan([pending()], dips=[dip(2.5), dip(3.0)])
    now = T0 + pd.Timedelta(minutes=20)
    old = mirror.desired(p, now, 10000, {})
    same = mirror.desired(p, now, 10000, {}, risk_mult=1.0, corr=False, last_close=None)
    assert set(same) == set(old) and all(abs(same[k].qty - old[k].qty) < 1e-12 for k in old)
    # corr off ignores last_close entirely
    ignored = mirror.desired(p, now, 10000, {}, risk_mult=1.0, corr=False, last_close={"BTCUSDT": 1.0})
    assert set(ignored) == set(old) and all(abs(ignored[k].qty - old[k].qty) < 1e-12 for k in old)
    # diff default ignores entry qty changes (old behaviour)
    o = mirror.Order("e1", "BTCUSDT", "Buy", 0.01, "entry", price=80000.0)
    want = {"e1": mirror.Order("e1", "BTCUSDT", "Buy", 0.02, "entry", price=80000.0)}
    assert mirror.diff(want, {"e1": dict(symbol="BTCUSDT", price=80000.0, qty=0.01)}) == []


def test_corr_shrinks_dip_and_amends_resting_bid():
    coins = {"BTCUSDT": {"subs": [], "dips": [_mkrow(2.0)]}, "ETHUSDT": {"subs": [], "dips": [_mkrow(2.0)]}}
    p = {"generated_at": str(T0), "phases": [{"phase": 0, "capital": 0.25}], "coins": coins}
    now = T0 + pd.Timedelta(minutes=20)
    w0 = mirror.desired(p, now, 10000, {}, corr=True, last_close={"BTCUSDT": 100.0, "ETHUSDT": 100.0})
    w1 = mirror.desired(p, now, 10000, {}, corr=True, last_close={"BTCUSDT": 100.0, "ETHUSDT": 90.0})
    (k0,) = [k for k, o in w0.items() if o.symbol == "BTCUSDT"]
    (k1,) = [k for k, o in w1.items() if o.symbol == "BTCUSDT"]
    assert k0 == k1 and abs(w1[k1].qty / w0[k0].qty - 0.5) < 1e-12  # n 0 -> 1 halves the rung
    have = {k: dict(symbol=o.symbol, price=o.price, qty=o.qty) for k, o in w0.items()}
    assert mirror.diff(w1, have) == []  # default: entry qty changes never amend
    acts = mirror.diff(w1, have, amend_entry_qty=True)
    assert acts == [dict(op="amend", link=k0, symbol="BTCUSDT", qty=w1[k1].qty)]


def test_corr_shrink_admits_more_rungs_like_the_engine():
    # three other coins flushing -> mult 1/4 -> cost 0.4 * 0.25 * 0.06 = 0.006 per rung -> all 3 BTC rungs fit the 0.065 budget
    flushed = {s: 1.0 for s in ("ETHUSDT", "SOLUSDT", "XRPUSDT")}
    q = plan(dips=[dip(2.5, frac=0.4), dip(3.0, frac=0.4), dip(4.0, frac=0.4)])
    for s in flushed:
        q["coins"][s] = {"subs": [], "dips": [dict(dip(2.5), buy_limit=100.0, stop=96.0)]}
    lc = dict(flushed, BTCUSDT=79000.0)
    w = mirror.desired(q, T0 + pd.Timedelta(minutes=20), 10000, {}, corr=True, last_close=lc)
    btc = [o for o in w.values() if o.symbol == "BTCUSDT"]
    assert len(btc) == 3 and all(abs(o.meta["frac"] - 0.1) < 1e-12 for o in btc)


def test_dip_mult_scales_only_dip_qty_and_keeps_admission():
    q = plan([pending()], dips=[dip(2.5, frac=0.4), dip(3.0, frac=0.4), dip(4.0, frac=0.4)])
    b0 = mirror.desired(q, T0 + pd.Timedelta(minutes=20), 10000, {})
    w = mirror.desired(q, T0 + pd.Timedelta(minutes=20), 10000, {}, dip_mult=1.8)
    assert set(w) == set(b0)
    for k in w:
        ratio = w[k].qty / b0[k].qty
        assert abs(ratio - (1.8 if w[k].meta.get("kind") == "dip" else 1.0)) < 1e-12


def test_is_bear_synthetic():
    assert mirror.is_bear([100.0] * 600) is False            # last == mean -> not below
    assert mirror.is_bear([100.0] * 599 + [90.0]) is True    # 600 bars, last below the mean
    assert mirror.is_bear([100.0] * 1200) is False
    assert mirror.is_bear([100.0] * 1199 + [90.0]) is True
    assert mirror.is_bear([100.0] * 599) is False            # below the 600-bar minimum
    assert mirror.is_bear([]) is False
    # windowing: only the last 1200 count (first 500 at 1000 would flip the full mean, not the window mean)
    assert mirror.is_bear([1000.0] * 500 + [100.0] * 1200) is False
    assert mirror.is_bear([1000.0] * 500 + [100.0] * 1199 + [90.0]) is True


def _add_plan(side="LONG", amount=0.1, price=80000.0):
    sub = {"phase": 0, "state": "position", "position": {"side": side, "sl": 70000.0, "tp": 95000.0},
           "order": {"kind": "add", "amount": amount, "price": price, "valid_until": str(T0 + pd.Timedelta(hours=4))}}
    return plan([sub])


def test_bear_book_halves_long_entry_and_add_only():
    now = T0 + pd.Timedelta(minutes=6)
    pl = plan([pending(side="BUY")])
    base = next(iter(mirror.desired(pl, now, 10000, {}).values()))
    halved = next(iter(mirror.desired(pl, now, 10000, {}, bear_book=True, bear=True).values()))
    assert abs(halved.qty / base.qty - 0.5) < 1e-12 and halved.side == "Buy"
    ps = plan([pending(side="SELL")])
    sbase = next(iter(mirror.desired(ps, now, 10000, {}).values()))
    ssame = next(iter(mirror.desired(ps, now, 10000, {}, bear_book=True, bear=True).values()))
    assert abs(ssame.qty - sbase.qty) < 1e-12 and ssame.side == "Sell"
    # adds: long halved, short unchanged
    now2 = T0 + pd.Timedelta(hours=1)
    led_l = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.025, sl=70000.0, tp=95000.0)}
    bl = mirror.desired(_add_plan("LONG"), now2, 10000, led_l)
    hl = mirror.desired(_add_plan("LONG"), now2, 10000, led_l, bear_book=True, bear=True)
    assert set(bl) == set(hl)
    (kl,) = [k for k, o in bl.items() if o.kind == "add"]
    assert abs(hl[kl].qty / bl[kl].qty - 0.5) < 1e-12
    led_s = {"pS": dict(kind="book", phase=0, symbol="BTCUSDT", side=-1, qty=0.025, sl=70000.0, tp=95000.0)}
    bs = mirror.desired(_add_plan("SHORT"), now2, 10000, led_s)
    hs = mirror.desired(_add_plan("SHORT"), now2, 10000, led_s, bear_book=True, bear=True)
    assert set(bs) == set(hs)
    (ks,) = [k for k, o in bs.items() if o.kind == "add"]
    assert abs(hs[ks].qty - bs[ks].qty) < 1e-12
    # dips unchanged under the bear filter
    q = plan(dips=[dip(2.5), dip(3.0)])
    d0 = mirror.desired(q, T0 + pd.Timedelta(minutes=20), 10000, {})
    d1 = mirror.desired(q, T0 + pd.Timedelta(minutes=20), 10000, {}, bear_book=True, bear=True)
    assert set(d1) == set(d0) and all(abs(d1[k].qty - d0[k].qty) < 1e-12 for k in d0)


def test_bear_book_default_off_identity():
    p = plan([pending()], dips=[dip(2.5), dip(3.0)])
    now = T0 + pd.Timedelta(minutes=20)
    old = mirror.desired(p, now, 10000, {})
    assert old  # guard: the fixture is non-empty
    for kw in (dict(bear_book=False, bear=False), dict(bear_book=False, bear=True), dict(bear_book=True, bear=False),
               dict(bear_book=False), dict(), dict(bear=False)):
        same = mirror.desired(p, now, 10000, {}, **kw)
        assert set(same) == set(old) and all(abs(same[k].qty - old[k].qty) < 1e-12 for k in old)


def test_klines_4h_opens_pages_oldest_first():
    from bot.bybit_v5 import Bybit
    n_all, step = 1200, 14_400_000
    t0 = 1_700_000_000_000
    all_rows = [[t0 + i * step, 100.0 + i] for i in range(n_all)]
    calls = []

    def fake_public(path, **kw):
        calls.append(dict(kw))
        assert path == "/v5/market/kline" and kw["interval"] == "240" and kw["limit"] <= 1000
        rows = [r for r in all_rows if kw.get("end") is None or r[0] <= int(kw["end"])]
        rows = sorted(rows, key=lambda r: r[0], reverse=True)[:kw["limit"]]
        return {"list": [[str(r[0]), str(r[1]), str(r[1]), str(r[1]), str(r[1]), "1", "1"] for r in rows]}

    b = Bybit(base="https://api.bybit.com")
    b.public = fake_public
    opens = b.klines_4h_opens("BTCUSDT")
    assert opens == [100.0 + i for i in range(n_all)]
    assert len(calls) == 2 and calls[0].get("end") is None and calls[1]["limit"] == 200


def _pos_sub(weight, reduce_price=None, phase=0):
    sub = {"phase": phase, "state": "position",
           "position": {"side": "LONG", "sl": 70000.0, "tp": 95000.0, "weight": weight}}
    if reduce_price is not None:
        sub["order"] = {"kind": "reduce", "amount": 0.5, "price": reduce_price,
                        "valid_until": str(T0 + pd.Timedelta(hours=4))}
    return sub


def _trims(w):
    return {k: o for k, o in w.items() if o.kind == "reduce" and o.meta.get("bear_trim")}


def test_bear_trim_long_once_in_bear():
    now = T0 + pd.Timedelta(hours=1)
    p = plan([_pos_sub(0.2)])
    led = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.05, sl=70000.0, tp=95000.0)}
    lc = {"BTCUSDT": 80000.0}
    w = mirror.desired(p, now, 10000, led, bear_book=True, bear=True, last_close=lc)
    tr = _trims(w)
    assert len(tr) == 1
    (link, o), = tr.items()
    bar_start = pd.Timestamp(now).floor("4h")
    assert link == "pLB" + mirror.t36(bar_start)
    assert o.side == "Sell" and o.reduce_only and o.position_idx == 1 and o.piece == "pL"
    assert abs(o.qty - (0.05 - 0.5 * 0.2 * 10000 / 80000)) < 1e-12
    assert abs(o.price - 80000.0 * 1.001) < 1e-9
    assert o.meta.get("valid_until") == str(bar_start + pd.Timedelta(hours=4))
    # runner records the trim: no second trim in the same or the next 4h bar of the same bear episode
    led["pL"]["trimmed_bear"] = True
    assert _trims(mirror.desired(p, now, 10000, led, bear_book=True, bear=True, last_close=lc)) == {}
    nxt = T0 + pd.Timedelta(hours=5)
    assert _trims(mirror.desired(p, nxt, 10000, led, bear_book=True, bear=True, last_close=lc)) == {}


def test_bear_trim_not_in_bull():
    now = T0 + pd.Timedelta(hours=1)
    p = plan([_pos_sub(0.2)])
    led = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.05, sl=70000.0, tp=95000.0)}
    lc = {"BTCUSDT": 80000.0}
    assert _trims(mirror.desired(p, now, 10000, dict(led), bear_book=True, bear=False, last_close=lc)) == {}
    assert _trims(mirror.desired(p, now, 10000, dict(led), bear_book=False, bear=True, last_close=lc)) == {}
    assert _trims(mirror.desired(p, now, 10000, dict(led))) == {}


def test_bear_trim_never_below_half_and_shorts_untouched():
    now = T0 + pd.Timedelta(hours=1)
    lc = {"BTCUSDT": 80000.0}
    half = 0.5 * 0.2 * 10000 / 80000
    p = plan([_pos_sub(0.2)])
    small = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=half * 0.9, sl=70000.0, tp=95000.0)}
    assert _trims(mirror.desired(p, now, 10000, small, bear_book=True, bear=True, last_close=lc)) == {}
    exact = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=half, sl=70000.0, tp=95000.0)}
    assert _trims(mirror.desired(p, now, 10000, exact, bear_book=True, bear=True, last_close=lc)) == {}
    big = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.10, sl=70000.0, tp=95000.0)}
    (o,) = _trims(mirror.desired(p, now, 10000, big, bear_book=True, bear=True, last_close=lc)).values()
    assert abs((0.10 - o.qty) - half) < 1e-12  # never trims below half
    short = {"pS": dict(kind="book", phase=0, symbol="BTCUSDT", side=-1, qty=0.10, sl=70000.0, tp=95000.0)}
    ps = plan([{"phase": 0, "state": "position",
                "position": {"side": "SHORT", "sl": 90000.0, "tp": 70000.0, "weight": 0.2}}])
    assert _trims(mirror.desired(ps, now, 10000, short, bear_book=True, bear=True, last_close=lc)) == {}


def test_bear_trim_uses_plan_reduce_price():
    now = T0 + pd.Timedelta(hours=1)
    p = plan([_pos_sub(0.2, reduce_price=81000.0)])
    led = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.05, sl=70000.0, tp=95000.0)}
    (o,) = _trims(mirror.desired(p, now, 10000, led, bear_book=True, bear=True,
                                 last_close={"BTCUSDT": 80000.0})).values()
    assert o.price == 81000.0


def test_bear_trim_default_off_identity():
    now = T0 + pd.Timedelta(hours=1)
    p = plan([_pos_sub(0.2)])
    led = {"pL": dict(kind="book", phase=0, symbol="BTCUSDT", side=1, qty=0.05, sl=70000.0, tp=95000.0)}
    old = mirror.desired(p, now, 10000, {k: dict(v) for k, v in led.items()})
    assert old  # guard: stop + tp present
    for kw in (dict(bear_book=False, bear=False), dict(bear_book=False, bear=True),
               dict(bear_book=True, bear=False), dict(),
               dict(bear_book=False, bear=True, last_close={"BTCUSDT": 80000.0})):
        same = mirror.desired(p, now, 10000, {k: dict(v) for k, v in led.items()}, **kw)
        assert set(same) == set(old) and all(abs(same[k].qty - old[k].qty) < 1e-12 for k in old)


def _dip_at(rung, bar_open, phase=0, lv=78000.0, frac=0.05, stop=None):
    a0 = pd.Timestamp(bar_open) + pd.Timedelta(minutes=16)
    return {"rung": rung, "phase": phase, "buy_limit": lv, "tp": lv * 1.01, "stop": stop or lv * 0.96,
            "backstop": lv * 0.92, "size_frac": frac,
            "active_from": str(a0), "active_until": str(a0 + pd.Timedelta(minutes=223))}


def _stopped_ledger(sym="BTCUSDT", phase=0, s=None):
    s = pd.Timestamp(s or (T0 + pd.Timedelta(hours=1)))
    led = {"dSTOP": dict(kind="dip", phase=phase, symbol=sym, side=1, qty=0.0, entry=78000.0,
                         tp=78000.0 * 1.01, stop5=78000.0 * 0.96, backstop=78000.0 * 0.92,
                         t_exit=str(T0 + pd.Timedelta(hours=4)), frac=0.05, dist=0.04, opened=str(T0))}
    mirror.note_dip_stop(led, "dSTOP", s)
    return led


def test_dip_cooldown_blocks_in_window_allows_after():
    s = T0 + pd.Timedelta(hours=1)
    led = _stopped_ledger(s=s)
    b_blocked = T0 + pd.Timedelta(hours=4)
    p = plan(dips=[_dip_at(2.5, b_blocked)])
    now = b_blocked + pd.Timedelta(minutes=20)
    assert mirror.desired(p, now, 10000, led)  # guard: off by default something rests
    assert mirror.desired(p, now, 10000, led, dip_cooldown_h=24) == {}
    b_after = s + pd.Timedelta(hours=24, minutes=1)
    p2 = plan(dips=[_dip_at(2.5, b_after - pd.Timedelta(minutes=20) + pd.Timedelta(minutes=20))])
    # rebuild with exact bar so now sits inside the window
    bar2 = s + pd.Timedelta(hours=25)
    p2 = plan(dips=[_dip_at(2.5, bar2)])
    now2 = bar2 + pd.Timedelta(minutes=20)
    assert mirror.desired(p2, now2, 10000, led, dip_cooldown_h=24)  # s+25h > s+24h: allowed
    # exact upper edge s+H is still blocked, one minute later is free
    bar_edge = s + pd.Timedelta(hours=24)
    pe = plan(dips=[_dip_at(2.5, bar_edge)])
    assert mirror.desired(pe, bar_edge + pd.Timedelta(minutes=20), 10000, led, dip_cooldown_h=24) == {}
    bar_free = s + pd.Timedelta(hours=24, minutes=1)
    pf = plan(dips=[_dip_at(2.5, bar_free)])
    assert mirror.desired(pf, bar_free + pd.Timedelta(minutes=20), 10000, led, dip_cooldown_h=24)
    # per-phase and per-coin isolation: phase 1 and ETH rungs are unaffected by a phase-0 BTC stop
    p_ph1 = {"generated_at": str(T0), "phases": [{"phase": p, "capital": 0.25} for p in range(4)],
             "coins": {"BTCUSDT": {"subs": [], "dips": [_dip_at(2.5, b_blocked, phase=1)]}}}
    assert mirror.desired(p_ph1, now, 10000, led, dip_cooldown_h=24)
    p_eth = {"generated_at": str(T0), "phases": [{"phase": 0, "capital": 0.25}],
             "coins": {"ETHUSDT": {"subs": [], "dips": [_dip_at(2.5, b_blocked)]}}}
    assert mirror.desired(p_eth, now, 10000, led, dip_cooldown_h=24)


def test_dip_cooldown_same_bar_and_open_pieces_unaffected():
    s = T0 + pd.Timedelta(minutes=30)
    led = _stopped_ledger(s=s)
    # same holding bar (B = T0 < s): s < B is false -> not blocked
    p = plan(dips=[_dip_at(2.5, T0), _dip_at(3.0, T0)])
    now = T0 + pd.Timedelta(minutes=40)
    assert len(mirror.desired(p, now, 10000, {}, dip_cooldown_h=24)) == 2
    assert len(mirror.desired(p, now, 10000, led, dip_cooldown_h=24)) == 2
    # open pieces keep their TP + backstop even while later bars are cooled
    o = next(iter(mirror.desired(plan(dips=[dip(2.5)]), T0 + pd.Timedelta(minutes=20), 10000, {}).values()))
    led2 = _stopped_ledger(s=T0 + pd.Timedelta(hours=1))
    mirror.apply_fill(led2, o, 0.006, 78000.0, T0 + pd.Timedelta(minutes=21))
    b_next = T0 + pd.Timedelta(hours=4)
    p_next = plan(dips=[_dip_at(2.5, b_next)])
    w = mirror.desired(p_next, b_next + pd.Timedelta(minutes=20), 10000, led2, dip_cooldown_h=24)
    kinds = {x.kind for x in w.values()}
    assert kinds == {"tp", "stop"}  # the open rung is protected; no NEW entry bid rests
    assert not [x for x in w.values() if x.kind == "entry"]


def test_dip_cooldown_tp_and_time_exits_do_not_trigger():
    # a closed dip piece with no stop marker (TP / time exit) never cools
    led = {"dTP": dict(kind="dip", phase=0, symbol="BTCUSDT", side=1, qty=0.0, entry=78000.0,
                       tp=78000.0 * 1.01, stop5=78000.0 * 0.96, backstop=78000.0 * 0.92,
                       t_exit=str(T0 + pd.Timedelta(hours=4)), frac=0.05, dist=0.04, opened=str(T0))}
    b_next = T0 + pd.Timedelta(hours=4)
    p = plan(dips=[_dip_at(2.5, b_next)])
    now = b_next + pd.Timedelta(minutes=20)
    assert mirror.desired(p, now, 10000, led, dip_cooldown_h=24)
    # a TP fill via apply_fill leaves no marker either
    o = next(iter(mirror.desired(plan(dips=[dip(2.5)]), T0 + pd.Timedelta(minutes=20), 10000, {}).values()))
    led2: dict = {}
    mirror.apply_fill(led2, o, 0.006, 78000.0, T0 + pd.Timedelta(minutes=21))
    (pid,) = led2
    tp_order = next(x for x in mirror.desired(plan(), T0 + pd.Timedelta(minutes=30), 10000, led2).values() if x.kind == "tp")
    mirror.apply_fill(led2, tp_order, 0.006, 78000.0 * 1.01, T0 + pd.Timedelta(minutes=40))
    assert "stop_exit_t" not in led2[pid]
    assert mirror.desired(p, now, 10000, led2, dip_cooldown_h=24)


def test_dip_sl_coin_changes_stop_and_budget_of_that_coin_only():
    row = _mkrow(2.0, open_px=100.0, sigma=0.01)
    lv = float(row["buy_limit"])
    assert abs(mirror.dip_stop_price(row, "XRPUSDT", None) - float(row["stop"])) < 1e-12
    assert abs(mirror.dip_stop_price(row, "XRPUSDT", {}) - float(row["stop"])) < 1e-12
    want = lv * (1.0 - 5.5 * 0.01)
    assert abs(mirror.dip_stop_price(row, "XRPUSDT", {"XRPUSDT": 5.5}) - want) < 1e-9
    assert abs(mirror.dip_risk_dist(row, "XRPUSDT", {"XRPUSDT": 5.5}) - 5.5 * 0.01) < 1e-12
    # desired(): the XRP bid carries the wider stop, BTC is untouched
    coins = {"BTCUSDT": {"subs": [], "dips": [_mkrow(2.0)]},
             "XRPUSDT": {"subs": [], "dips": [_mkrow(2.0)]}}
    p = {"generated_at": str(T0), "phases": [{"phase": 0, "capital": 0.25}], "coins": coins}
    now = T0 + pd.Timedelta(minutes=20)
    w = mirror.desired(p, now, 10000, {}, dip_sl_coin={"XRPUSDT": 5.5})
    by_sym = {o.symbol: o for o in w.values()}
    assert abs(by_sym["XRPUSDT"].meta["stop"] - want) < 1e-9
    assert abs(by_sym["BTCUSDT"].meta["stop"] - float(_mkrow(2.0)["stop"])) < 1e-12
    # budget: wider XRP stop costs more, so fewer XRP rungs fit while BTC still fits two
    def _xrp_plan(rungs):
        return {"generated_at": str(T0), "phases": [{"phase": 0, "capital": 0.25}],
                "coins": {"XRPUSDT": {"subs": [], "dips": [dict(_mkrow(r, open_px=100.0, sigma=0.01), size_frac=0.5) for r in rungs]}}}
    qx0 = _xrp_plan([2.5, 3.0])
    assert len(mirror.desired(qx0, now, 10000, {})) == 2  # 0.5*0.06 x2 = 0.06 fits the 0.065 budget
    assert len(mirror.desired(qx0, now, 10000, {}, dip_sl_coin={"XRPUSDT": 5.5})) == 1  # 0.5*0.075 x2 = 0.075 does not
    qb = plan(dips=[dip(2.5, frac=0.5), dip(3.0, frac=0.5)])
    assert len(mirror.desired(qb, now, 10000, {})) == 2
    assert len(mirror.desired(qb, now, 10000, {}, dip_sl_coin={"XRPUSDT": 5.5})) == 2  # BTC untouched by the XRP override


def test_dip_cascade_defaults_reproduce_old_outputs():
    p = plan([pending()], dips=[dip(2.5), dip(3.0)])
    now = T0 + pd.Timedelta(minutes=20)
    led = {"dSTOP": dict(kind="dip", phase=0, symbol="BTCUSDT", side=1, qty=0.0, opened=str(T0),
                         stop_exit_t=str(T0 + pd.Timedelta(hours=1)))}
    old = mirror.desired(p, now, 10000, {})
    for kw in (dict(), dict(dip_cooldown_h=0.0), dict(dip_cooldown_h=0), dict(dip_sl_coin=None),
               dict(dip_sl_coin={}), dict(dip_sl_coin={"BTCUSDT": 4.0}),
               dict(dip_cooldown_h=0.0, dip_sl_coin=None)):
        same = mirror.desired(p, now, 10000, {}, **kw)
        assert set(same) == set(old)
        for k in old:
            assert abs(same[k].qty - old[k].qty) < 1e-12 and same[k].price == old[k].price
            assert same[k].trigger == old[k].trigger and same[k].meta.get("stop") == old[k].meta.get("stop")
    # a recorded stop is ignored while the cooldown is off
    off = mirror.desired(p, now, 10000, led)
    assert set(off) == set(old)
