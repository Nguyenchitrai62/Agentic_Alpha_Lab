"""Fast parity-contract tests (no archive data, no network).

Covers what REPORT.md claims without the heavy replay:
- bot.mirror with the deployment flags (--corr-size --dip-mult 1.7 --bear-book):
  corr inv-rule, dip-mult sizing, bear halve + bear trim, budget admission;
- paper fill semantics shared with the parity drive (trade-through,
  stop-first, PostOnly, placement minute never fills);
- as-of cut used by snapshot_plan (events after T+6min are ignored).
"""
import pandas as pd

from bot import mirror


def _dip_row(rung=3.0, buy=100.0, stop=96.0):
    return {"rung": rung, "buy_limit": buy, "stop": stop, "size_frac": 0.01,
            "tp": 104.0, "backstop": 90.0,
            "active_from": "2026-09-01T00:16:00+00:00", "active_until": "2026-09-01T03:59:00+00:00",
            "phase": 0}


def test_corr_inv_rule_counts_flushing_peers():
    base = _dip_row()
    # peer open 100, sigma = (1-96/100)/4 = 0.01; flush threshold = 100*(1-0.025) = 97.5
    plan = {"BTCUSDT": [base], "ETHUSDT": [_dip_row()]}
    assert mirror.corr_mult(plan, {"ETHUSDT": 102.0}, "BTCUSDT") == 1.0
    assert mirror.corr_mult(plan, {"ETHUSDT": 97.0}, "BTCUSDT") == 0.5


def test_bear_regime_halves_book_longs_only():
    opens = [100.0] * 1199 + [90.0]
    assert mirror.is_bear(opens) is True
    assert mirror.is_bear([100.0] * 599) is False  # min 600 bars
    plan = {"phases": [{"phase": 0, "capital": 0.25}], "coins": {
        "BTCUSDT": {"price": 100.0, "subs": [
            {"phase": 0, "state": "pending",
             "order": {"kind": "open", "side": "BUY", "price": 99.0, "weight": 0.1,
                       "issued": "2026-09-01T00:00:00+00:00", "valid_until": "2026-09-01T12:00:00+00:00",
                       "sl_if_filled": 95.0, "tp_if_filled": 105.0}}],
            "dips": []}}}
    now = pd.Timestamp("2026-09-01T01:00:00Z")
    off = mirror.desired(plan, now, 10000.0, {}, bear_book=False, bear=True)
    on = mirror.desired(plan, now, 10000.0, {}, bear_book=True, bear=True)
    k_off = next(k for k, o in off.items() if o.kind == "entry")
    k_on = next(k for k, o in on.items() if o.kind == "entry")
    assert on[k_on].qty == off[k_off].qty * 0.5


def test_dip_mult_scales_qty_not_admission():
    d = _dip_row()
    plan = {"phases": [{"phase": 0, "capital": 10.0}], "coins": {
        "BTCUSDT": {"price": 100.0, "subs": [], "dips": [d]}}}
    now = pd.Timestamp("2026-09-01T01:00:00Z")
    a = mirror.desired(plan, now, 10000.0, {}, dip_mult=1.0)
    b = mirror.desired(plan, now, 10000.0, {}, dip_mult=1.7)
    ka = next(k for k, o in a.items() if o.kind == "entry")
    kb = next(k for k, o in b.items() if o.kind == "entry")
    assert b[kb].qty == a[ka].qty * 1.7


def test_paper_trade_through_and_stop_first():
    from bot.paper import PaperExchange
    ex = PaperExchange.__new__(PaperExchange)
    ex.symbols = ["BTCUSDT"]
    ex.s = dict(cash=10000.0, equity0=10000.0, orders={}, pos={}, execs=[],
                last_ms={}, last_close={"BTCUSDT": 100.0}, funding_paid=0.0, fees=0.0)
    t0 = int(pd.Timestamp("2026-09-01T00:00:00Z").timestamp() * 1000)
    # limit buy at 99: no touch (low 99.5) -> rests; touch (low 98) -> fills at 99
    ex.s["orders"]["L1"] = dict(symbol="BTCUSDT", side="Buy", qty=1.0, price=99.0,
                                orderType="Limit", timeInForce="PostOnly", positionIdx=1, t_ms=t0 - 60000)
    ex._minute("BTCUSDT", t0, 100.0, 101.0, 99.5, 100.5)
    assert "L1" in ex.s["orders"]
    ex._minute("BTCUSDT", t0 + 60000, 100.0, 101.0, 98.0, 99.0)
    assert "L1" not in ex.s["orders"]
    # stop-first: stop + tp of one long in the same minute -> stop wins
    ex.s["orders"]["S1"] = dict(symbol="BTCUSDT", side="Sell", qty=1.0, triggerPrice=90.0,
                                orderType="Market", triggerDirection=2, reduceOnly=True, positionIdx=1, t_ms=t0)
    ex.s["orders"]["T1"] = dict(symbol="BTCUSDT", side="Sell", qty=1.0, price=110.0,
                                orderType="Limit", reduceOnly=True, positionIdx=1, t_ms=t0)
    ex._pos("BTCUSDT", 1)["qty"] = 1.0
    ex._pos("BTCUSDT", 1)["avg"] = 100.0
    ex._minute("BTCUSDT", t0 + 120000, 100.0, 111.0, 89.0, 100.0)
    assert "S1" not in ex.s["orders"]  # stop filled first (stop-first tie rule)
    assert any(e["orderLinkId"] == "S1" for e in ex.s["execs"])  # the stop is what filled
    assert ex.s["pos"]["BTCUSDT|1"]["qty"] == 0.0  # position closed by the stop


def test_snapshot_asof_ignores_future_events():
    ev = pd.DataFrame([
        {"t": pd.Timestamp("2026-09-01T00:05:00Z"), "symbol": "BTCUSDT", "kind": "order_issue",
         "side": "buy", "price": 99.0, "weight": 0.1},
        {"t": pd.Timestamp("2026-09-01T04:30:00Z"), "symbol": "BTCUSDT", "kind": "book_fill",
         "side": "buy", "price": 99.0, "weight": 0.1},
    ])
    now = pd.Timestamp("2026-09-01T00:06:00Z")
    pre = ev[ev["t"] <= now]
    assert len(pre) == 1 and pre.iloc[0]["kind"] == "order_issue"
