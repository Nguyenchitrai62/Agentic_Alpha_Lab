"""Review 2026-10-06 (F1/F2/F5): carry guard + paper IOC interactions. NO network, NO keys.

Each test asserts the CORRECT behaviour; all fail on current code.
F1: carry hedge-retry / timeout-close / delivery-sale markets must pass guard_carry.
F2: _carry_sync must see spot-category fills (category-aware fake like live Bybit).
F5: paper must cancel (not rest) an IOC whose ref price is unknown.
"""
import pandas as pd

from bot import carry


def _now():
    return pd.Timestamp.now(tz="UTC")


def _ms(ts):
    return int(pd.Timestamp(ts).timestamp() * 1000)


def _expiries(now, front_days=3, next_days=90):
    n = _ms(now)
    return {"BTC": [dict(symbol="BTC-FRONT", category="linear", delivery_ms=n + front_days * 86_400_000),
                    dict(symbol="BTCQ", category="linear", delivery_ms=n + next_days * 86_400_000)]}


def _quotes(spot=80000.0, fut=82000.0, sym="BTCQ"):
    return {"BTC": dict(spot_mid=spot, spot_ask=spot, spot_bid=spot,
                        fut_by_sym={sym: dict(bid=fut, ask=fut, mid=fut)})}


def test_carry_hedge_retry_fut_market_passes_guard():
    # F1: single-fill open -> fut Sell Market hedge must be placeable with guard on.
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    want, _ = carry.decide(now, 10000.0, 0.25, cstate, _expiries(now), _quotes())
    spot_link = [p for p in want if p["side"] == "Buy"][0]["orderLinkId"]
    carry.note_exec(cstate, spot_link, float(want[0]["qty"]), 80000.0)
    want2, logs2 = carry.decide(now + pd.Timedelta(minutes=1), 10000.0, 0.25,
                                cstate, _expiries(now), _quotes())
    assert any(r.get("op") == "carry_unhedged" for r in logs2)
    assert len(want2) == 1 and want2[0]["orderType"] == "Market"
    allowed, rejected = carry.guard_carry(
        want2, {}, 10000.0, {"BTCQ": 82000.0, "BTCUSDT": 80000.0})
    assert rejected == [] and len(allowed) == 1


def test_carry_hedge_retry_spot_market_passes_guard():
    # F1 mirror image: fut fills first -> spot Buy Market hedge must pass.
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    want, _ = carry.decide(now, 10000.0, 0.25, cstate, _expiries(now), _quotes())
    fut = [p for p in want if p["side"] == "Sell"][0]
    carry.note_exec(cstate, fut["orderLinkId"], float(fut["qty"]), 82000.0)
    want2, logs2 = carry.decide(now + pd.Timedelta(minutes=1), 10000.0, 0.25,
                                cstate, _expiries(now), _quotes())
    assert any(r.get("op") == "carry_unhedged" for r in logs2)
    assert len(want2) == 1 and want2[0]["orderType"] == "Market"
    allowed, rejected = carry.guard_carry(
        want2, {}, 10000.0, {"BTCQ": 82000.0, "BTCUSDT": 80000.0})
    assert rejected == [] and len(allowed) == 1


def test_carry_delivery_spot_sale_passes_guard():
    # F1: delivery settlement spot Sell Market must pass (fut Buy reduce-only already does).
    sale = [dict(symbol="BTCUSDT", side="Sell", qty="0.03", orderType="Market",
                 orderLinkId="cBTCXrevS", category="spot")]
    allowed, rejected = carry.guard_carry(sale, {}, 10000.0, {"BTCUSDT": 81000.0})
    assert rejected == [] and len(allowed) == 1


class CategoryFakeExchange:
    """Mimics live Bybit: executions are per-category (linear vs spot)."""

    def __init__(self):
        self.linear_execs = []
        self.spot_execs = []
        self.inverse_execs = []

    def executions(self, start_ms, category="linear"):
        # Category-aware like bot/bybit_v5.Bybit.executions(start, category).
        try:
            cat = str(category or "linear")
        except Exception:
            cat = "linear"
        src = self.spot_execs if cat == "spot" else (self.inverse_execs if cat == "inverse" else self.linear_execs)
        return [e for e in src if int(e["execTime"]) >= int(start_ms)]

    def open_orders(self, category="linear"):
        return []


def test_carry_sync_sees_spot_fills():
    # F2: a spot fill must mark spot_filled via _carry_sync; live it never arrives.
    import bot.run as runmod
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    want, _ = carry.decide(now, 10000.0, 0.25, cstate, _expiries(now), _quotes())
    spot = [p for p in want if p["side"] == "Buy"][0]
    t_ms = _ms(now) + 60_000
    ex = CategoryFakeExchange()
    ex.spot_execs.append(dict(execId="spot1", orderLinkId=spot["orderLinkId"],
                              execQty=str(float(spot["qty"])), execPrice="80000",
                              execTime=str(t_ms)))
    r = runmod.Runner.__new__(runmod.Runner)
    r.mode, r.carry_f = "testnet", 0.25
    r.state = {"ledger": {}, "links": {}, "last_exec_ms": t_ms - 120_000,
               "seen_exec": [], "carry": cstate}
    r.ex = ex
    r.logs = []
    r.log = lambda rec: r.logs.append(rec)
    r._carry_sync()
    pos = r.state["carry"]["positions"]["BTC"]
    assert pos.get("spot_filled") is True


def test_paper_ioc_unknown_ref_cancels():
    # F5: IOC with no ref price must be cancelled (None) with nothing resting.
    from bot.paper import PaperExchange
    from pathlib import Path
    import tempfile
    d = Path(tempfile.mkdtemp())

    class Pub:
        def instruments(self, syms):
            return {s: dict(qty_step="0.001", min_qty="0.001",
                            min_notional="5", tick="0.1") for s in syms}

        def public(self, *a, **k):
            return {"list": []}

    ex = PaperExchange(Pub(), d / "ex.json", 10000.0, ["BTCUSDT"])
    assert ex.s.get("last_close", {}) == {}
    res = ex.place(dict(symbol="BTCQ", side="Sell", qty="0.01", orderType="Limit",
                        price="82000", orderLinkId="cBTCqREV",
                        category="linear", positionIdx=2, timeInForce="IOC"))
    assert res is None
    assert "cBTCqREV" not in ex.s["orders"]
