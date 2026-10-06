"""bot_carry tests (no network, no keys). Uses tests/mock_bybit_v5.py for exchange I/O."""
import json
import time

import pandas as pd

from bot import carry
from bot import mirror
from scripts import carry_paper
from tests.mock_bybit_v5 import MockBybitV5

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
        "ETHUSDT": dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01")}


def _now():
    return pd.Timestamp.now(tz="UTC")


def _ms(ts):
    return int(pd.Timestamp(ts).timestamp() * 1000)


def _expiries(now, front_days=3, next_days=90, coin="BTC", sym_front="BTC-FRONT", sym_next="BTC-NEXTQ"):
    n = _ms(now)
    return {coin: [dict(symbol=sym_front, category="linear", delivery_ms=n + front_days * 86_400_000),
                   dict(symbol=sym_next, category="linear", delivery_ms=n + next_days * 86_400_000)]}


def _quotes(spot=80000.0, fut=82000.0, sym="BTC-NEXTQ"):
    return {"BTC": dict(spot_mid=spot, spot_ask=spot, spot_bid=spot,
                        fut_by_sym={sym: dict(bid=fut, ask=fut, mid=fut)})}


def test_frozen_rule_imports():
    assert carry.RULE_PARAMS is carry_paper.RULE_PARAMS
    assert carry.is_quarterly_delivery is carry_paper.is_quarterly_delivery
    assert carry.RULE_PARAMS["basis_threshold"] == 0.04
    assert carry.RULE_PARAMS["roll_days"] == 7


def test_entry_two_legs_prefix_c_sizing():
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    want, logs = carry.decide(now, 10000.0, 0.25, cstate,
                              _expiries(now), _quotes())
    assert len(want) == 2
    links = sorted(p["orderLinkId"] for p in want)
    assert all(str(x).startswith("c") for x in links)
    by_side = {p["side"]: p for p in want}
    spot, fut = by_side["Buy"], by_side["Sell"]
    assert spot["category"] == "spot" and spot["timeInForce"] == "IOC"
    assert spot["orderType"] == "Limit" and float(spot["price"]) == 80000.0
    assert fut["category"] == "linear" and fut["timeInForce"] == "IOC"
    assert fut.get("positionIdx") == 2
    # each leg notional = f x equity; equal coin quantity
    assert abs(float(spot["qty"]) - 0.25 * 10000.0 / 80000.0) < 1e-9
    assert abs(float(fut["qty"]) - float(spot["qty"])) < 1e-12
    assert any(r.get("op") == "carry_entry" for r in logs)
    assert "BTC" in cstate["positions"]


def test_skip_when_basis_below_threshold():
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    want, logs = carry.decide(now, 10000.0, 0.25, cstate,
                              _expiries(now), _quotes(spot=80000.0, fut=80100.0))
    assert want == []
    assert any(r.get("op") == "carry_skip" for r in logs)
    assert cstate["positions"] == {}


def test_partial_hedge_retry_then_timeout_close():
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    want, _ = carry.decide(now, 10000.0, 0.25, cstate, _expiries(now), _quotes())
    spot_link = [p for p in want if p["side"] == "Buy"][0]["orderLinkId"]
    # only the spot leg fills
    rec = carry.note_exec(cstate, spot_link, float(want[0]["qty"]), 80000.0)
    assert rec and rec["leg"] == "spot"
    pos = cstate["positions"]["BTC"]
    assert pos["spot_filled"] and not pos["fut_filled"]
    # next cycle: retry missing fut at market, log carry_unhedged
    want2, logs2 = carry.decide(now + pd.Timedelta(minutes=1), 10000.0, 0.25,
                                cstate, _expiries(now), _quotes())
    assert len(want2) == 1 and want2[0]["side"] == "Sell" and want2[0]["orderType"] == "Market"
    assert any(r.get("op") == "carry_unhedged" for r in logs2)
    assert pos["unhedged_cycles"] == 1
    # two more unhedged cycles -> close the filled leg
    carry.decide(now + pd.Timedelta(minutes=2), 10000.0, 0.25, cstate, _expiries(now), _quotes())
    want4, logs4 = carry.decide(now + pd.Timedelta(minutes=3), 10000.0, 0.25,
                                cstate, _expiries(now), _quotes())
    assert any(r.get("op") == "carry_close" for r in logs4)
    assert want4 and want4[0]["orderType"] == "Market"


def test_delivery_settlement_spot_sale_and_pnl():
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    want, _ = carry.decide(now, 10000.0, 0.25, cstate, _expiries(now), _quotes())
    for p in want:
        leg = "spot" if p["side"] == "Buy" else "fut"
        carry.note_exec(cstate, p["orderLinkId"], float(p["qty"]), float(p["price"]))
    assert cstate["positions"]["BTC"]["spot_filled"] and cstate["positions"]["BTC"]["fut_filled"]
    dlv = cstate["positions"]["BTC"]["delivery_ms"]
    t_del = pd.Timestamp(dlv + 60_000, unit="ms", tz="UTC")
    want2, logs2 = carry.decide(t_del, 10000.0, 0.25, cstate, _expiries(now), _quotes(spot=81000.0))
    assert any(p["side"] == "Sell" and p["category"] == "spot" and p["orderType"] == "Market" for p in want2)
    assert any(r.get("op") == "carry_settle" for r in logs2)
    sale = [p for p in want2 if p.get("category") == "spot"][0]
    rec = carry.note_exec(cstate, sale["orderLinkId"], float(sale["qty"]), 81000.0)
    assert rec and rec["op"] == "carry_settled"
    assert "BTC" not in cstate["positions"]
    assert cstate["history"] and "realised_pnl" in cstate["history"][0]


def test_guard_carry_cap_and_risk_guard_passthrough():
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    # f=0.5 on 10k: short notional ~5125 > 0.3x -> blocked at decide (carry_cap log)
    want, logs = carry.decide(now, 10000.0, 0.5, cstate, _expiries(now), _quotes())
    assert want == [] and any(r.get("op") == "carry_cap" for r in logs)
    # direct guard: oversize short rejected with carry_cap even when allowlisted
    big = [dict(symbol="BTC-NEXTQ", side="Sell", qty="0.0625", orderType="Limit",
                price="82000", orderLinkId="cBTCbigF", category="linear", positionIdx=2)]
    allowed, rej = carry.guard_carry(big, {}, 10000.0, {"BTC-NEXTQ": 82000.0})
    assert allowed == [] and rej and rej[0]["reason"] == "carry_cap"
    # normal-size short passes the guard
    ok = [dict(symbol="BTC-NEXTQ", side="Sell", qty="0.03", orderType="Limit",
               price="82000", orderLinkId="cBTCokF", category="linear", positionIdx=2)]
    allowed2, rej2 = carry.guard_carry(ok, {}, 10000.0, {"BTC-NEXTQ": 82000.0})
    assert len(allowed2) == 1 and rej2 == []


def _runner(monkeypatch, tmp_path, plan, mock, tag="c", **kw):
    import bot.run as runmod
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "dummy")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "dummy")
    monkeypatch.setattr(runmod, "ROOT", tmp_path)
    mock.install_session(monkeypatch)
    plan_f = tmp_path / f"plan_{tag}.json"
    plan_f.write_text(json.dumps(plan, default=str))
    r = runmod.Runner("testnet", plan_f, None, tag=tag, **kw)
    r._kline_cache_dir_override = str(tmp_path / f"kcache_{tag}")
    return r


def _empty_plan():
    now = _now()
    return {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}], "coins": {}}


def test_runner_entry_via_mock_and_paper_fills(monkeypatch, tmp_path):
    now = _now()
    mock = MockBybitV5(prices={"BTCUSDT": 79900.0}, equity=10000.0,
                       inst=dict(mock_bybit_inst()))
    r = _runner(monkeypatch, tmp_path, _empty_plan(), mock, tag="ce", carry_f=0.25)
    n = _ms(now)
    r._carry_contracts_override = {"BTC": [
        dict(symbol="BTC-FRONT", category="linear", delivery_ms=n + 3 * 86_400_000),
        dict(symbol="BTCQ", category="linear", delivery_ms=n + 90 * 86_400_000)]}
    r._carry_quotes_override = {"BTC": dict(spot_mid=80000.0, spot_ask=80000.0, spot_bid=80000.0,
                                            fut_by_sym={"BTCQ": dict(bid=82000.0, ask=82000.0, mid=82000.0)})}
    # dated symbol needs an instrument in the mock for rounding/placement
    r.inst["BTCQ"] = dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")
    r.cycle()
    clinks = [k for k in mock.orders if str(k).startswith("c")]
    assert len(clinks) == 2
    sides = sorted(o["side"] for o in (mock.orders[k] for k in clinks))
    assert sides == ["Buy", "Sell"]
    ops = [json.loads(x) for x in (r.dir / "actions.jsonl").read_text().splitlines()]
    assert any(x.get("op") == "carry_entry" for x in ops)


def mock_bybit_inst():
    from tests.mock_bybit_v5 import DEFAULT_INST
    d = dict(DEFAULT_INST)
    d["BTCQ"] = dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")
    return d


def test_flag_off_no_change(monkeypatch, tmp_path):
    mock = MockBybitV5(prices={"BTCUSDT": 79900.0}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, _empty_plan(), mock, tag="co")
    assert float(getattr(r, "carry_f", 0.0) or 0.0) == 0.0
    acts = r.cycle()
    assert "carry" not in r.state
    assert not [k for k in r.state.get("links", {}) if str(k).startswith("c")]
    ops = [json.loads(x) for x in (r.dir / "actions.jsonl").read_text().splitlines()] if (r.dir / "actions.jsonl").exists() else []
    assert not [x for x in ops if str(x.get("op", "")).startswith("carry")]
    assert acts is not None


def test_generic_cancel_ignores_carry_links():
    import bot.run as runmod
    have = {"cBTChrvw7S": dict(symbol="BTCUSDT", price=85363.1, qty=0.014),
            "cBTChrvw7F": dict(symbol="BTCUSDT-25DEC26", price=86274.4, qty=0.014),
            "b0BTCxyzE": dict(symbol="BTCUSDT", price=80000.0, qty=0.01)}
    raw = mirror.diff({}, have)
    assert any(a.get("op") == "cancel" and a.get("link") == "cBTChrvw7S" for a in raw)
    filt = runmod._have_without_carry(have)
    assert "cBTChrvw7S" not in filt and "cBTChrvw7F" not in filt
    assert "b0BTCxyzE" in filt
    kept = runmod._acts_without_carry_cancel(
        raw + [dict(op="amend", link="cBTChrvw7S", symbol="BTCUSDT", price=1.0)])
    assert not [a for a in kept if str(a.get("link", "")).startswith("c")]
    assert any(a.get("link") == "b0BTCxyzE" for a in kept)


def test_ioc_paper_fill_both_legs():
    from bot.paper import PaperExchange

    class Pub:
        def instruments(self, syms):
            return {s: INST["BTCUSDT"] for s in syms}

        def public(self, *a, **k):
            return {"list": []}

    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    ex = PaperExchange(Pub(), d / "ex.json", 10000.0, ["BTCUSDT"])
    t0 = int(_ms(_now()) // 60000 * 60000)
    ex.s["last_ms"] = {"BTCUSDT": t0, "BTCQ": t0}
    ex.s["last_close"] = {"BTCUSDT": 79999.0, "BTCQ": 82001.0}
    r1 = ex.place(dict(symbol="BTCUSDT", side="Buy", qty="0.01", orderType="Limit",
                       price="80000", orderLinkId="cBTCiS", category="spot",
                       timeInForce="IOC"))
    r2 = ex.place(dict(symbol="BTCQ", side="Sell", qty="0.01", orderType="Limit",
                       price="82000", orderLinkId="cBTCiF", category="linear",
                       positionIdx=2, timeInForce="IOC"))
    assert r1 and r2  # crossing IOCs fill at placement
    assert not [k for k in ex.s["orders"] if str(k).startswith("cBTCi")]
    assert abs(ex.s["spot"]["BTCUSDT"]["qty"] - 0.01) < 1e-9
    assert abs(ex.s["pos"]["BTCQ|2"]["qty"] - 0.01) < 1e-9
    assert {"cBTCiS", "cBTCiF"} <= {e["orderLinkId"] for e in ex.s["execs"]}


def test_ioc_paper_cancel_when_no_cross():
    from bot.paper import PaperExchange

    class Pub:
        def instruments(self, syms):
            return {s: INST["BTCUSDT"] for s in syms}

        def public(self, *a, **k):
            return {"list": []}

    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    ex = PaperExchange(Pub(), d / "ex.json", 10000.0, ["BTCUSDT"])
    t0 = int(_ms(_now()) // 60000 * 60000)
    ex.s["last_ms"] = {"BTCUSDT": t0, "BTCQ": t0}
    ex.s["last_close"] = {"BTCUSDT": 79999.0, "BTCQ": 82001.0}
    assert ex.place(dict(symbol="BTCUSDT", side="Buy", qty="0.01", orderType="Limit",
                         price="79000", orderLinkId="cBTCnS", category="spot",
                         timeInForce="IOC")) is None
    assert ex.place(dict(symbol="BTCQ", side="Sell", qty="0.01", orderType="Limit",
                         price="83000", orderLinkId="cBTCnF", category="linear",
                         positionIdx=2, timeInForce="IOC")) is None
    assert not [k for k in ex.s["orders"] if str(k).startswith("cBTCn")]
    assert {e["orderLinkId"] for e in ex.s["execs"]}.isdisjoint({"cBTCnS", "cBTCnF"})


def test_neither_filled_retry_then_abandon():
    now = _now()
    cstate = {"positions": {}, "entered": [], "history": []}
    exp, quo = _expiries(now), _quotes()
    want, _ = carry.decide(now, 10000.0, 0.25, cstate, exp, quo)
    assert len(want) == 2
    first_links = {p["orderLinkId"] for p in want}
    # cycle 2: neither leg filled -> fresh pair, attempt 2
    want2, logs2 = carry.decide(now + pd.Timedelta(minutes=1), 10000.0, 0.25,
                                cstate, exp, quo)
    assert len(want2) == 2
    assert {p["orderLinkId"] for p in want2} != first_links
    assert any(r.get("op") == "carry_entry" and r.get("retry") for r in logs2)
    assert cstate["positions"]["BTC"]["attempts"] == 2
    # cycle 3: still nothing filled -> attempt 3
    want3, _ = carry.decide(now + pd.Timedelta(minutes=2), 10000.0, 0.25,
                            cstate, exp, quo)
    assert len(want3) == 2
    assert cstate["positions"]["BTC"]["attempts"] == 3
    # cycle 4: 3 attempts used -> carry_abandon, position cleared for next roll
    want4, logs4 = carry.decide(now + pd.Timedelta(minutes=3), 10000.0, 0.25,
                                cstate, exp, quo)
    assert want4 == []
    assert any(r.get("op") == "carry_abandon" for r in logs4)
    assert "BTC" not in cstate["positions"]
    # next roll: re-evaluated, a fresh entry is possible
    want5, logs5 = carry.decide(now + pd.Timedelta(minutes=4), 10000.0, 0.25,
                                cstate, exp, quo)
    assert len(want5) == 2
    assert any(r.get("op") == "carry_entry" for r in logs5)


def test_skip_dedupe_per_coin_hour():
    now = _now().floor("h")
    cstate = {"positions": {}, "entered": [], "history": []}
    exp = _expiries(now)
    quo = _quotes(spot=80000.0, fut=80100.0)
    _, logs1 = carry.decide(now, 10000.0, 0.25, cstate, exp, quo)
    _, logs2 = carry.decide(now + pd.Timedelta(minutes=5), 10000.0, 0.25,
                            cstate, exp, quo)
    skips = [r for r in logs1 + logs2 if r.get("op") == "carry_skip"]
    assert len(skips) == 1
    _, logs3 = carry.decide(now + pd.Timedelta(hours=1, minutes=1), 10000.0, 0.25,
                            cstate, _expiries(now), quo)
    assert any(r.get("op") == "carry_skip" for r in logs3)


def test_paper_spot_and_dated_trade_through():
    from bot.paper import PaperExchange

    class Pub:
        def instruments(self, syms):
            return {s: INST["BTCUSDT"] for s in syms}

        def public(self, *a, **k):
            return {"list": []}

    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    ex = PaperExchange(Pub(), d / "ex.json", 10000.0, ["BTCUSDT"])
    t0 = int(_ms(_now()) // 60000 * 60000)
    ex.s["last_ms"] = {"BTCUSDT": t0, "BTCQ": t0}
    ex.s["last_close"] = {"BTCUSDT": 80000.0, "BTCQ": 82000.0}
    ex.place(dict(symbol="BTCUSDT", side="Buy", qty="0.01", orderType="Limit",
                  price="80000", orderLinkId="cBTCtS", category="spot"))
    ex.place(dict(symbol="BTCQ", side="Sell", qty="0.01", orderType="Limit",
                  price="82000", orderLinkId="cBTCtF", category="linear", positionIdx=2))
    # strict trade-through on the next minute fills both at their limits
    ex._minute("BTCUSDT", t0 + 60_000, 80000, 80100, 79900, 80050)
    ex._minute("BTCQ", t0 + 60_000, 82000, 82100, 81900, 82050)
    assert not [k for k in ex.s["orders"] if str(k).startswith("cBTCt")]
    assert abs(ex.s["spot"]["BTCUSDT"]["qty"] - 0.01) < 1e-9
    assert abs(ex.s["pos"]["BTCQ|2"]["qty"] - 0.01) < 1e-9
    exec_links = {e["orderLinkId"] for e in ex.s["execs"]}
    assert {"cBTCtS", "cBTCtF"} <= exec_links
