"""Synthetic checks of engine_user's execution-realism stress hooks (system audit 2026-10-03).

sleeve_fill_minute_stop, fill_through_bps, stop_slip, timeout_exit_minute and funding_rates must all be default-neutral and
act as documented on hand-made 1m paths.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "engine_user_stress", ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)

SIG = 0.01
LV = 100 * (1 - 3.0 * SIG)          # dip rung 3 sigma below the 100 open = 97
SL = LV * (1 - 2.0 * SIG)           # rung stop m_sleeve_sl = 2 -> 95.06
TP = LV * (1 + 1.0 * SIG)           # rung take-profit 1 sigma -> 97.97
FEES = eu.MAKER + eu.TAKER
TRADE = dict(theta=0.05, k_off=0.25, min_off=0.001, n_valid=2, win_start=5)
BOOK_LIMIT = 100 * (1 - 0.25 * SIG)  # 99.75


def make(nbars=3, books_val=0.0, minutes=None, settle0=False):
    """Flat 100 path; minutes = {(bar, minute or (start, stop)): {"O"/"H"/"L"/"C": value}} overrides."""
    idx = pd.date_range("2022-01-01", periods=nbars, freq="4h", tz="UTC")
    cols = ["BTCUSDT"]
    X = {k: np.full((nbars, 240, 1), 100.0) for k in "OHLC"}
    for (b, m), d in (minutes or {}).items():
        for k, v in d.items():
            X[k][b, slice(*m) if isinstance(m, tuple) else m, 0] = v
    o1 = np.full((nbars, 1), 100.0)
    o2 = np.array([X["O"][min(b + 1, nbars - 1), 0, 0] for b in range(nbars)]).reshape(-1, 1)
    settle = np.zeros(nbars, bool)
    settle[0] = settle0
    prep = dict(idx=idx, cols=cols, O=X["O"], H=X["H"], L=X["L"], C=X["C"], sig4=np.full((nbars, 1), SIG), o1=o1, o2=o2,
                settle=settle)
    books = pd.DataFrame(np.full((nbars, 1), books_val), index=idx, columns=cols)
    opens = pd.DataFrame(o1, index=idx, columns=cols)
    return books, opens, prep


def run(books, opens, prep, **kw):
    events, cap = [], {}
    orig = eu.summarize

    def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(net=net.copy(), stats=dict(stats))
        return {}
    eu.summarize = grab
    try:
        eu.simulate(books, opens, prep, events=events, **kw)
    finally:
        eu.summarize = orig
    cap["events"] = events
    return cap


SLEEVE = dict(sleeve=True, rungs=(3.0,), m_sleeve_sl=2.0, sleeve_start=16)
BOOK = dict(sleeve=False, m_sl=4.0, trade=TRADE, win_start=5)


def rung_exit(cap):
    ex = [e for e in cap["events"] if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")]
    assert len(ex) == 1
    return ex[0]


def held_after_fill():
    """Rung fills at minute 20, then the bar trades at 97.5 (between stop and TP) -> timeout at the next open."""
    return {(0, (20, 240)): dict(O=97.5, H=97.5, L=97.5, C=97.5)}


def test_defaults_are_neutral():
    m = held_after_fill()
    m[(0, 20)] = dict(L=95.0)
    m[(0, 30)] = dict(O=96.0, L=94.0)
    b, o, p = make(minutes=m)
    a = run(b, o, p, **SLEEVE)
    c = run(b, o, p, **SLEEVE, sleeve_fill_minute_stop=False, fill_through_bps=0.0, stop_slip=0.0, timeout_exit_minute=0,
            funding_rates=None)
    assert a["events"] == c["events"] and np.array_equal(a["net"], c["net"]) and a["stats"] == c["stats"]
    bb, ob, pb = make(books_val=1.0, minutes={(0, 10): dict(L=99.7), (0, 50): dict(O=95.0, L=85.0)})
    a = run(bb, ob, pb, **BOOK)
    c = run(bb, ob, pb, **BOOK, fill_through_bps=0.0, stop_slip=0.0)
    assert a["events"] == c["events"] and np.array_equal(a["net"], c["net"])


def test_fill_minute_stop():
    m = held_after_fill()
    m[(0, 20)] = dict(L=95.0)  # the bid fills and the stop is touched in the same minute
    b, o, p = make(minutes=m)
    d = rung_exit(run(b, o, p, **SLEEVE))
    assert d["kind"] == "rung_timeout"  # default: exits only from the minute after the fill
    cap = run(b, o, p, **SLEEVE, sleeve_fill_minute_stop=True)
    e = rung_exit(cap)
    assert e["kind"] == "rung_sl" and e["t"] == p["idx"][0] + pd.Timedelta(hours=4, minutes=20)
    assert e["ret"] == pytest.approx(SL / LV - 1 - FEES)
    assert cap["stats"]["fill_minute_stops"] == 1
    # a fill minute whose low stays above the stop is unaffected
    m[(0, 20)] = dict(L=96.0)
    b, o, p = make(minutes=m)
    assert rung_exit(run(b, o, p, **SLEEVE, sleeve_fill_minute_stop=True))["kind"] == "rung_timeout"


def test_fill_through_dip_bid_and_tp():
    m = held_after_fill()
    m[(0, 20)] = dict(L=96.99)  # through the 97 bid by ~1 bp only
    b, o, p = make(minutes=m)
    assert len(run(b, o, p, **SLEEVE)["events"]) == 2
    assert run(b, o, p, **SLEEVE, fill_through_bps=2.0)["events"] == []
    m[(0, 20)] = dict(L=96.9)
    m[(0, 30)] = dict(H=TP * 1.0001)  # TP traded through by 1 bp
    b, o, p = make(minutes=m)
    assert rung_exit(run(b, o, p, **SLEEVE))["kind"] == "rung_tp"
    e = rung_exit(run(b, o, p, **SLEEVE, fill_through_bps=2.0))
    assert e["kind"] == "rung_timeout"
    fill = run(b, o, p, **SLEEVE, fill_through_bps=2.0)["events"][0]
    assert fill["price"] == pytest.approx(LV)  # the fill price stays the limit


def test_fill_through_book_entry():
    b, o, p = make(books_val=1.0, minutes={(0, 10): dict(L=BOOK_LIMIT - 0.01)})  # ~1 bp through the 99.75 limit
    assert any(e["kind"] == "book_fill" for e in run(b, o, p, **BOOK)["events"])
    assert not any(e["kind"] == "book_fill" for e in run(b, o, p, **BOOK, fill_through_bps=2.0)["events"])


def test_stop_slip_rung_and_book():
    m = held_after_fill()
    m[(0, 20)] = dict(L=96.9)
    m[(0, 30)] = dict(O=96.0, L=94.0)  # stop 95.06 touched, minute low 94
    b, o, p = make(minutes=m)
    assert rung_exit(run(b, o, p, **SLEEVE))["ret"] == pytest.approx(SL / LV - 1 - FEES)
    e = rung_exit(run(b, o, p, **SLEEVE, stop_slip=0.5))
    assert e["ret"] == pytest.approx((SL - 0.5 * (SL - 94.0)) / LV - 1 - FEES)
    b, o, p = make(books_val=1.0, minutes={(0, 10): dict(L=99.7), (0, 50): dict(O=95.0, L=85.0)})
    sl = BOOK_LIMIT * (1 - 4.0 * SIG * np.sqrt(6))
    st = [e for e in run(b, o, p, **BOOK)["events"] if e["kind"] == "book_stop"]
    assert st and st[0]["price"] == pytest.approx(sl)
    st = [e for e in run(b, o, p, **BOOK, stop_slip=1.0)["events"] if e["kind"] == "book_stop"]
    assert st and st[0]["price"] == pytest.approx(85.0)


def test_timeout_exit_minute_and_funding():
    m = held_after_fill()
    m[(0, 20)] = dict(L=96.9)
    m[(1, 10)] = dict(O=101.0)  # the next bar's minute-10 open
    b, o, p = make(minutes=m, settle0=True)
    base = rung_exit(run(b, o, p, **SLEEVE))
    assert base["ret"] == pytest.approx(100.0 / LV - 1 - FEES - eu.FUND_LONG)
    late = rung_exit(run(b, o, p, **SLEEVE, timeout_exit_minute=10))
    assert late["ret"] == pytest.approx(101.0 / LV - 1 - FEES - eu.FUND_LONG)
    assert late["t"] == p["idx"][0] + pd.Timedelta(hours=4, minutes=250)
    # actual signed funding: a negative rate settled at the end of bar 0 is received by the long rung; a settlement at the
    # bar start belongs to the previous bar
    fr = pd.DataFrame({"BTCUSDT": [0.05, -0.0003]}, index=[p["idx"][0] + pd.Timedelta(hours=4), p["idx"][0] + pd.Timedelta(hours=8)])
    f = rung_exit(run(b, o, p, **SLEEVE, funding_rates=fr))
    assert f["ret"] == pytest.approx(100.0 / LV - 1 - FEES + 0.0003)


def test_funding_rates_book_short_receives():
    # a short book position held through a settlement receives a positive rate
    b, o, p = make(nbars=3, books_val=-1.0, minutes={(0, 10): dict(H=100.3)})
    fr = pd.DataFrame({"BTCUSDT": [0.001]}, index=[p["idx"][0] + pd.Timedelta(hours=8)])
    flat = run(b, o, p, **BOOK)
    real = run(b, o, p, **BOOK, funding_rates=fr)
    assert flat["stats"]["funding"] == 0.0  # adverse rule: shorts pay / receive nothing
    assert real["stats"]["funding"] < 0.0 and real["net"][0] > flat["net"][0]
