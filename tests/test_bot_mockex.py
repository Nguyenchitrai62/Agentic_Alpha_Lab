"""Mock-exchange end-to-end tests for the order-mirror bot (no network, no keys).

The real ``bot.bybit_v5.Bybit`` client talks to ``tests/mock_bybit_v5.py`` by
monkeypatching its HTTP calls (signed + public). Every test drives
``bot.run.Runner`` in ``testnet`` mode over a scripted 1m price path with a
plan-file fixture shaped like ``trade_plan_v376.json``.
"""
import json
import time

import pandas as pd

from tests.mock_bybit_v5 import MockBybitV5

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def _now():
    return pd.Timestamp.now(tz="UTC")


def _book_plan(price=80000.0, weight=0.02, sl=70000.0, tp=95000.0, issued_ago_min=10):
    now = _now()
    return {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"BTCUSDT": {"price": price,
                                  "subs": [{"phase": 0, "state": "pending",
                                            "order": {"kind": "open", "side": "BUY", "price": price,
                                                      "weight": weight,
                                                      "issued": str(now - pd.Timedelta(minutes=issued_ago_min)),
                                                      "valid_until": str(now + pd.Timedelta(hours=4)),
                                                      "sl_if_filled": sl, "tp_if_filled": tp}}],
                                  "dips": []}}}


def _dip_row(lv=78000.0, rung=2.5, frac=0.05, frm=None, until=None):
    now = _now()
    a0 = frm or (now - pd.Timedelta(minutes=60))
    a1 = until or (now + pd.Timedelta(hours=3))
    return {"rung": rung, "phase": 0, "buy_limit": lv, "tp": lv * 1.01,
            "stop": lv * 0.96, "backstop": lv * 0.92, "size_frac": frac,
            "active_from": str(a0), "active_until": str(a1)}


def _runner(monkeypatch, tmp_path, plan, mock, tag="t", **kw):
    import bot.run as runmod
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "dummy")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "dummy")
    monkeypatch.setattr(runmod, "ROOT", tmp_path)
    mock.install_session(monkeypatch)  # real Bybit client -> fake HTTP (signing/retry intact)
    plan_f = tmp_path / f"plan_{tag}.json"
    plan_f.write_text(json.dumps(plan, default=str))
    r = runmod.Runner("testnet", plan_f, None, tag=tag, **kw)
    r._kline_cache_dir_override = str(tmp_path / f"kcache_{tag}")
    return r


def _ops(r):
    f = r.dir / "actions.jsonl"
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()]


def test_1_book_entry_rests_fills_then_protected(monkeypatch, tmp_path):
    mock = MockBybitV5(prices={"BTCUSDT": 81000.0}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, _book_plan(), mock, tag="t1")
    r.cycle()
    entries = {k: o for k, o in mock.orders.items() if o.get("orderType") == "Limit" and not o.get("reduceOnly")}
    assert len(entries) == 1
    (link, pay), = entries.items()
    assert pay["timeInForce"] == "PostOnly" and link.endswith("E")
    t = int(time.time() * 1000) + 60_000
    assert mock.process_bar("BTCUSDT", 81000, 81100, 79900, 80500, t) == [link]
    r.cycle()
    assert len(r.state["ledger"]) == 1
    tp = [o for o in mock.orders.values() if o.get("reduceOnly") and o.get("orderType") == "Limit"]
    st = [o for o in mock.orders.values() if o.get("triggerPrice")]
    assert tp and st and st[0]["orderType"] == "Market" and st[0]["reduceOnly"] is True
    poss = r.ex.get("/v5/position/list", category="linear", settleCoin="USDT")
    assert any(p["positionIdx"] == 1 and float(p["size"]) > 0 for p in poss["list"])
    assert r.ex.get("/v5/execution/list", category="linear", startTime=0, limit=100)["list"]


def test_2_crossing_entry_rejects_retries_never_market(monkeypatch, tmp_path):
    mock = MockBybitV5(prices={"BTCUSDT": 79000.0}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, _book_plan(), mock, tag="t2")
    r.cycle()
    r.cycle()
    ops = _ops(r)
    assert [x for x in ops if x.get("op") == "postonly_reject"]
    assert r.state["links"] == {} and not mock.orders
    assert not [c for c in mock.calls if c[0] == "post" and c[1] == "/v5/order/create"
                and c[2].get("orderType") == "Market"]
    assert any(x.get("op") == "postonly_reject" and "110079" in str(x.get("note", "")) for x in ops)


def test_3_dips_gross_cap_and_guard_blocks_oversize_not_stops(monkeypatch, tmp_path):
    mock = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    now = _now()
    plan = {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"BTCUSDT": {"price": 85000.0,
                                  "subs": [{"phase": 0, "state": "pending",
                                            "order": {"kind": "open", "side": "BUY", "price": 80000.0,
                                                      "weight": 2.0, "issued": str(now - pd.Timedelta(minutes=10)),
                                                      "valid_until": str(now + pd.Timedelta(hours=4)),
                                                      "sl_if_filled": 70000.0, "tp_if_filled": 95000.0}},
                                           {"phase": 0, "state": "position",
                                            "position": {"side": "LONG", "sl": 70000.0, "tp": 95000.0}}],
                                  "dips": [_dip_row(lv=78000.0, rung=2.5, frac=0.15),
                                           _dip_row(lv=77000.0, rung=3.0, frac=0.15),
                                           _dip_row(lv=76000.0, rung=4.0, frac=0.15)]}}}
    r = _runner(monkeypatch, tmp_path, plan, mock, tag="t3", dip_gross_cap=0.2)
    r.state["ledger"] = {"seed1": dict(kind="book", phase=0, symbol="BTCUSDT", side=1,
                                       qty=0.01, entry=80000.0, sl=70000.0, tp=95000.0,
                                       opened=str(now - pd.Timedelta(hours=1)))}
    r.cycle()
    ops = _ops(r)
    assert [x for x in ops if x.get("op") == "risk_reject"]
    assert not [k for k in mock.orders if k.startswith("b0BTC")]
    stops = [o for k, o in mock.orders.items() if k == "seed1S"]
    assert stops  # reduce-only protection still goes through
    dips = [o for o in mock.orders.values() if o.get("timeInForce") == "PostOnly" and o.get("side") == "Buy"]
    assert dips
    room = 0.2 * 10000 * 0.25
    assert all(float(o["qty"]) * float(o["price"]) <= room + 1e-6 for o in dips)
    assert sum(float(o["qty"]) * float(o["price"]) for o in dips) <= 2 * room + 1e-6


def test_4_restart_mid_position_no_duplicates(monkeypatch, tmp_path):
    import bot.run as runmod
    mock = MockBybitV5(prices={"BTCUSDT": 81000.0}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, _book_plan(), mock, tag="t4")
    r.cycle()
    links_dbg = list(mock.orders)
    assert len(links_dbg) == 1, links_dbg
    link = links_dbg[0]
    t = int(time.time() * 1000) + 60_000
    mock.process_bar("BTCUSDT", 81000, 81100, 79900, 80500, t)
    r.cycle()
    n_orders, ledger = dict(mock.orders), dict(r.state["ledger"])
    assert ledger and any(k.endswith("T") for k in n_orders) and any(k.endswith("S") for k in n_orders)
    r2 = runmod.Runner("testnet", r.plan_path, None, tag="t4")
    r2._kline_cache_dir_override = str(tmp_path / "kcache_t4")
    acts = r2.cycle()
    assert r2.state["ledger"] == ledger
    assert not [a for a in acts if a.get("op") == "place" and getattr(a.get("order"), "kind", "") == "entry"]
    assert any(k.endswith("T") for k in mock.orders) and any(k.endswith("S") for k in mock.orders)


def test_5_partial_fill_then_expiry_cancel(monkeypatch, tmp_path):
    mock = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    now = _now()
    plan = {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"BTCUSDT": {"subs": [], "dips": [_dip_row()]}}}
    r = _runner(monkeypatch, tmp_path, plan, mock, tag="t5")
    r.cycle()
    elinks = [k for k in mock.orders if k.endswith("E")]
    assert len(elinks) == 1, list(mock.orders)
    link = elinks[0]
    full = float(mock.orders[link]["qty"])
    t = int(time.time() * 1000) + 60_000
    mock.manual_fill(link, full / 2, 78000.0, t)
    r.cycle()
    pids = list(r.state["ledger"])
    assert len(pids) == 1
    pid = pids[0]
    assert abs(r.state["ledger"][pid]["qty"] - full / 2) < 1e-9
    assert link in mock.orders  # remainder still resting
    assert abs(float(mock.orders[link]["qty"]) - full / 2) < 1e-9
    expired = {"generated_at": str(_now()), "phases": [{"phase": 0, "capital": 0.25}],
               "coins": {"BTCUSDT": {"subs": [], "dips": [_dip_row(
                   frm=_now() - pd.Timedelta(hours=6), until=_now() - pd.Timedelta(hours=2))]}}}
    r.plan_path.write_text(json.dumps(expired, default=str))
    r.cycle()
    assert link not in mock.orders  # expired remainder cancelled


def test_6_10006_burst_backoff_no_crash(monkeypatch, tmp_path):
    import bot.bybit_v5 as bv
    mock = MockBybitV5(prices={"BTCUSDT": 81000.0}, equity=10000.0)
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(bv.time, "sleep", lambda s: sleeps.append(s))
    r = _runner(monkeypatch, tmp_path, _book_plan(), mock, tag="t6")
    mock.fail_public = 2
    assert r.cycle() is not None and sleeps  # backoff happened, no crash
    mock.fail_public = 100
    assert r.cycle() is not None  # sustained burst still does not crash
