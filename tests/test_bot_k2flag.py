"""bot_k2flag: optional Kronos K2 dip-size tilt (default OFF, paper/mock only).

Covers the assignment: flag absent -> bit-identical orders; flag set with
1.25 / 0.75 / missing rows -> entry qty scaled before budget/gross-cap/lot
rounding; caps still bind; lot minimum respected (dust skip); parquet
missing -> 1.0; backfill mode ignored; one k2_mult log per (coin, phase, bar).
No network, no keys (fake HTTP session to tests/mock_bybit_v5.py).
"""
import json

import pandas as pd
import pytest

import bot.run as runmod
from bot.run import _k2_bar_of_dip, _k2_mult_for, _k2_norm_sym
from tests.mock_bybit_v5 import MockBybitV5


def _now():
    return pd.Timestamp.now(tz="UTC")


def _dip_row(phase=0, rung=2.5, lv=78000.0, frac=0.08, frm=None, until=None):
    now = _now()
    a0 = frm if frm is not None else (now - pd.Timedelta(minutes=60))
    a1 = until if until is not None else (now + pd.Timedelta(hours=3))
    return {"rung": rung, "phase": phase, "buy_limit": lv, "tp": lv * 1.01,
            "stop": lv * 0.96, "backstop": lv * 0.92, "size_frac": frac,
            "active_from": str(a0), "active_until": str(a1)}


def _plan(dips_by_coin):
    now = _now()
    phases = [{"phase": 0, "capital": 0.25}, {"phase": 1, "capital": 0.25}]
    coins = {}
    for coin, dips in dips_by_coin.items():
        px = 85000.0 if coin == "BTCUSDT" else (3500.0 if coin == "ETHUSDT" else 2.0)
        coins[coin] = {"price": px, "subs": [], "dips": dips}
    return {"generated_at": str(now), "phases": phases, "coins": coins}


def _runner(monkeypatch, tmp_path, plan, mock, tag="k", **kw):
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "dummy")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "dummy")
    monkeypatch.setattr(runmod, "ROOT", tmp_path)
    mock.install_session(monkeypatch)
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


def _dip_orders(mock):
    return {k: v for k, v in mock.orders.items()
            if k.endswith("E") and v.get("side") == "Buy" and v.get("timeInForce") == "PostOnly"}


def _norm_orders(orders):
    """Orders without placement-time noise (t_ms differs across cycles)."""
    out = {}
    for k, v in orders.items():
        vv = dict(v)
        vv.pop("t_ms", None)
        out[k] = vv
    return out


def _write_parquet(path, rows):
    df = pd.DataFrame(rows)
    df.to_parquet(path, index=False)
    return path


# ---- hand-checked synthetic: pure helpers -----------------------------------

def test_k2_helpers_synthetic():
    assert _k2_norm_sym("BTC") == "BTCUSDT"
    assert _k2_norm_sym("BTCUSDT") == "BTCUSDT"
    assert _k2_norm_sym("btc") == "BTCUSDT"
    d = {"active_from": "2026-10-07T12:16:00+00:00"}
    assert str(_k2_bar_of_dip(d)) == "2026-10-07 12:00:00+00:00"
    assert _k2_bar_of_dip({}) is None
    bar = pd.Timestamp("2026-10-07T12:00:00Z")
    key = lambda m, mo: {("BTCUSDT", 0, int(bar.value)): (m, mo)}
    assert _k2_mult_for("BTC", 0, bar, key(1.25, "prospective"))[0] == 1.25
    assert _k2_mult_for("BTCUSDT", 0, bar, key(0.75, "late"))[0] == 0.75
    assert _k2_mult_for("BTC", 0, bar, key(1.25, "backfill"))[0] == 1.0
    assert _k2_mult_for("BTC", 0, bar, key(1.25, "prospective"))[1] == "prospective"
    assert _k2_mult_for("ETH", 0, bar, key(1.25, "prospective"))[0] == 1.0  # missing row
    assert _k2_mult_for("BTC", 0, None, key(1.25, "prospective"))[0] == 1.0


def test_k2_truncation_backfill_and_nan_are_1():
    bar = pd.Timestamp("2026-10-07T12:00:00Z")
    m = {("BTCUSDT", 0, int(bar.value)): (float("nan"), "prospective"),
         ("ETHUSDT", 0, int(bar.value)): (1.25, "backfill"),
         ("SOLUSDT", 0, int(bar.value)): (0.0, "prospective")}
    assert _k2_mult_for("BTC", 0, bar, m)[0] == 1.0
    assert _k2_mult_for("ETH", 0, bar, m)[0] == 1.0
    assert _k2_mult_for("SOL", 0, bar, m)[0] == 1.0


# ---- flag absent -> identical orders ----------------------------------------

def test_flag_absent_identical(monkeypatch, tmp_path):
    plan = _plan({"BTCUSDT": [_dip_row(phase=0, rung=2.5, lv=78000.0, frac=0.08)]})
    m1 = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    r1 = _runner(monkeypatch, tmp_path, plan, m1, tag="kabs1")
    r1.cycle()
    o1 = dict(m1.orders)
    m2 = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    r2 = _runner(monkeypatch, tmp_path, plan, m2, tag="kabs2", k2_tilt=None)
    r2.cycle()
    assert _norm_orders(m2.orders) == _norm_orders(o1)
    assert len(_dip_orders(m1)) == 1
    assert not [x for x in _ops(r1) if x.get("op") in ("k2_mult", "k2_missing")]
    assert not [x for x in _ops(r2) if x.get("op") in ("k2_mult", "k2_missing")]


# ---- 1.25 / 0.75 / missing rows --------------------------------------------

def test_scale_125_075_missing(monkeypatch, tmp_path):
    d0 = _dip_row(phase=0, rung=2.5, lv=78000.0, frac=0.08)
    d1 = _dip_row(phase=1, rung=2.5, lv=77000.0, frac=0.08)
    d2 = _dip_row(phase=0, rung=2.5, lv=3000.0, frac=0.08)
    plan = _plan({"BTCUSDT": [d0, d1], "ETHUSDT": [d2]})
    b0 = _k2_bar_of_dip(d0)
    b1 = _k2_bar_of_dip(d1)
    pq = tmp_path / "k2.parquet"
    _write_parquet(pq, [
        {"sym": "BTCUSDT", "shift": 0, "T": b0, "k2_mult": 1.25, "mode": "prospective"},
        {"sym": "BTCUSDT", "shift": 1, "T": b1, "k2_mult": 0.75, "mode": "late"},
    ])
    m0 = MockBybitV5(prices={"BTCUSDT": 85000.0, "ETHUSDT": 3500.0}, equity=10000.0)
    rb = _runner(monkeypatch, tmp_path, plan, m0, tag="kbase")
    rb.cycle()
    base = _dip_orders(m0)
    assert len(base) == 3
    m1 = MockBybitV5(prices={"BTCUSDT": 85000.0, "ETHUSDT": 3500.0}, equity=10000.0)
    rk = _runner(monkeypatch, tmp_path, plan, m1, tag="ktilt", k2_tilt=str(pq))
    rk.cycle()
    tilted = _dip_orders(m1)
    assert len(tilted) == 3
    # match links to base by (symbol, price): same rung layout, qty scaled
    for link, o in base.items():
        t = tilted.get(link)
        assert t is not None, link
        assert t["price"] == o["price"]  # price untouched
    # per-link expected scaled qty (floor to lot, same as to_exchange;
    # recomputed from raw frac*equity/price to avoid double-floor drift)
    from bot.bybit_v5 import round_step as rs
    raw_of = {}
    for coin, cc in plan["coins"].items():
        for dd in cc["dips"]:
            raw_of[(coin, float(dd["buy_limit"]))] = float(dd["size_frac"]) * 10000.0 / float(dd["buy_limit"])
    exp = {}
    for link, o in base.items():
        px = float(o["price"])
        raw = raw_of.get((o["symbol"], px), float(o["qty"]))
        if o["symbol"] == "BTCUSDT" and px == 78000.0:
            exp[link] = rs(raw * 1.25, "0.001")
        elif o["symbol"] == "BTCUSDT" and px == 77000.0:
            exp[link] = rs(raw * 0.75, "0.001")
        else:
            exp[link] = o["qty"]  # ETH missing row -> 1.0
    for link, want_q in exp.items():
        assert tilted[link]["qty"] == want_q, (link, tilted[link]["qty"], want_q)
    ops = _ops(rk)
    k2ops = [x for x in ops if x.get("op") == "k2_mult"]
    assert k2ops
    by_key = {(x.get("coin"), x.get("phase"), x.get("bar")): x for x in k2ops}
    assert len(by_key) == 3  # once per (coin, phase, bar)
    mults = sorted(float(x.get("mult")) for x in k2ops)
    assert mults == [0.75, 1.0, 1.25]
    # book path untouched: no book entries in this plan, and second cycle logs no dup k2
    n0 = len(k2ops)
    rk.cycle()
    k2ops2 = [x for x in _ops(rk) if x.get("op") == "k2_mult"]
    assert len(k2ops2) == n0  # once per bar, not once per cycle


def test_backfill_mode_ignored(monkeypatch, tmp_path):
    d = _dip_row(phase=0, rung=2.5, lv=78000.0, frac=0.08)
    plan = _plan({"BTCUSDT": [d]})
    bar = _k2_bar_of_dip(d)
    pq = tmp_path / "k2b.parquet"
    _write_parquet(pq, [{"sym": "BTCUSDT", "shift": 0, "T": bar, "k2_mult": 1.25, "mode": "backfill"}])
    m0 = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    _runner(monkeypatch, tmp_path, plan, m0, tag="kbf0").cycle()
    m1 = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    _runner(monkeypatch, tmp_path, plan, m1, tag="kbf1", k2_tilt=str(pq)).cycle()
    assert _norm_orders(m1.orders) == _norm_orders(m0.orders)


# ---- caps still bind --------------------------------------------------------

def test_gross_cap_still_binds(monkeypatch, tmp_path):
    d = _dip_row(phase=0, rung=2.5, lv=80000.0, frac=0.045)  # notional 450
    plan = _plan({"BTCUSDT": [d]})
    bar = _k2_bar_of_dip(d)
    pq = tmp_path / "k2c.parquet"
    _write_parquet(pq, [{"sym": "BTCUSDT", "shift": 0, "T": bar, "k2_mult": 1.25, "mode": "prospective"}])
    room = 0.2 * 10000 * 0.25  # 500
    m1 = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    _runner(monkeypatch, tmp_path, plan, m1, tag="kcap1", k2_tilt=str(pq), dip_gross_cap=0.2).cycle()
    dips = list(_dip_orders(m1).values())
    assert len(dips) == 1
    notion = float(dips[0]["qty"]) * float(dips[0]["price"])
    assert notion <= room + 1e-6
    assert notion > 450.0  # scaled up ...
    assert notion <= 500.0 + 1e-6  # ... but capped at room


# ---- lot minimum respected ---------------------------------------------------

def test_lot_minimum_skips_scaled_dust(monkeypatch, tmp_path):
    # XRP lot 1 / min_notional 5, lv 2.0, equity 10000, qty floors to lots:
    # frac 0.00065 -> qty 3.25 -> lot 3 (notional 6, ok); x0.75 -> 2.4375
    # -> lot 2 (notional 4 < 5 -> skipped like any other dust).
    d = _dip_row(phase=0, rung=2.5, lv=2.0, frac=0.00065)
    d["tp"] = 2.02
    d["stop"] = 1.92
    d["backstop"] = 1.84
    plan = _plan({"XRPUSDT": [d]})
    bar = _k2_bar_of_dip(d)
    pq = tmp_path / "k2d.parquet"
    _write_parquet(pq, [{"sym": "XRPUSDT", "shift": 0, "T": bar, "k2_mult": 0.75, "mode": "prospective"}])
    m0 = MockBybitV5(prices={"XRPUSDT": 2.2}, equity=10000.0)
    _runner(monkeypatch, tmp_path, plan, m0, tag="kdust0").cycle()
    assert len(_dip_orders(m0)) == 1
    m1 = MockBybitV5(prices={"XRPUSDT": 2.2}, equity=10000.0)
    r1 = _runner(monkeypatch, tmp_path, plan, m1, tag="kdust1", k2_tilt=str(pq))
    r1.cycle()
    assert len(_dip_orders(m1)) == 0  # scaled below minimum -> skipped as dust
    ops = _ops(r1)
    assert [x for x in ops if x.get("op") in ("skipped_below_minimum", "dust_skip")]


# ---- parquet missing -> 1.0 ----------------------------------------------------

def test_parquet_missing_is_10(monkeypatch, tmp_path):
    plan = _plan({"BTCUSDT": [_dip_row(phase=0, rung=2.5, lv=78000.0, frac=0.08)]})
    m0 = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    _runner(monkeypatch, tmp_path, plan, m0, tag="kmiss0").cycle()
    m1 = MockBybitV5(prices={"BTCUSDT": 85000.0}, equity=10000.0)
    r1 = _runner(monkeypatch, tmp_path, plan, m1, tag="kmiss1",
                 k2_tilt=str(tmp_path / "no_such.parquet"))
    r1.cycle()
    assert _norm_orders(m1.orders) == _norm_orders(m0.orders)
    ops = _ops(r1)
    assert [x for x in ops if x.get("op") == "k2_missing"]
    assert [x for x in ops if x.get("op") == "place"]
