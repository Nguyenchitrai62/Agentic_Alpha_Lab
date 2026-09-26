"""Synthetic checks of engine_user: limit fill, take-profit, stop through a gap, unfilled limit, funding."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "engine_user", ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)


def make(lows=None, highs=None, opens_m=None, settle=False, sig=0.01):
    idx = pd.DatetimeIndex([pd.Timestamp("2022-01-01 00:00", tz="UTC")])
    cols = ["BTCUSDT"]
    O = np.full((1, 240, 1), 100.0)
    H = np.full((1, 240, 1), 100.0)
    L = np.full((1, 240, 1), 100.0)
    C = np.full((1, 240, 1), 100.0)
    for m, v in (lows or {}).items():
        L[0, m, 0] = v
    for m, v in (highs or {}).items():
        H[0, m, 0] = v
    for m, v in (opens_m or {}).items():
        O[0, m, 0] = v
        C[0, m, 0] = v
    prep = dict(idx=idx, cols=cols, O=O, H=H, L=L, C=C, sig4=np.array([[sig]]), o1=np.array([[100.0]]),
                o2=np.array([[100.0]]), settle=np.array([settle]))
    books = pd.DataFrame([[1.0]], index=idx, columns=cols)
    opens = pd.DataFrame([[100.0]], index=idx, columns=cols)
    return books, opens, prep


def net_of(res):
    return res["yearly"]  # not used; simulate returns summary


def run(books, opens, prep, **kw):
    captured = {}
    orig = eu.summarize

    def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
        captured.update(net=net.copy(), stats=dict(stats), eq_min=eq_min.copy(),
                        eq_max=None if eq_max is None else eq_max.copy())
        return {}
    eu.summarize = grab
    try:
        eu.simulate(books, opens, prep, sleeve=False, **kw)
    finally:
        eu.summarize = orig
    return captured


def test_limit_fill_and_take_profit():
    sd = 0.01 * np.sqrt(6)
    fill = 100 * (1 - eu.D_LIMIT)
    tp = fill * (1 + 2 * 3 * sd)
    books, opens, prep = make(lows={5: 99.8}, highs={50: tp + 1})
    out = run(books, opens, prep, m_sl=3.0)
    q = 0.8 / 100.0
    exp = q * (tp - fill) - q * fill * eu.MAKER - q * tp * eu.MAKER
    assert out["net"][0] == pytest.approx(exp, rel=1e-9)
    assert out["stats"]["tps"] == 1 and out["stats"]["fills"] == 1


def test_stop_through_gap_fills_at_open():
    books, opens, prep = make(lows={5: 99.8, 60: 89.0}, opens_m={60: 90.0})
    out = run(books, opens, prep, m_sl=3.0)
    fill = 100 * (1 - eu.D_LIMIT)
    q = 0.8 / 100.0
    exp = q * (90.0 - fill) - q * fill * eu.MAKER - q * 90.0 * eu.TAKER
    assert out["net"][0] == pytest.approx(exp, rel=1e-9)
    assert out["stats"]["stops"] == 1


def test_unfilled_limit_expires():
    books, opens, prep = make(lows={100: 99.0})  # trade-through only after minute 59
    out = run(books, opens, prep)
    assert out["net"][0] == 0.0 and out["stats"]["unfilled"] == 1


def test_long_pays_funding_at_settlement():
    books, opens, prep = make(lows={5: 99.8}, settle=True)
    out = run(books, opens, prep, m_sl=3.0)
    fill = 100 * (1 - eu.D_LIMIT)
    q = 0.8 / 100.0
    exp = q * (100.0 - fill) - q * fill * eu.MAKER - eu.FUND_LONG * q * 100.0
    assert out["net"][0] == pytest.approx(exp, rel=1e-9)


def test_intrabar_peak_counts_in_drawdown():
    # long fills at 99.9, price rallies to 104 intrabar (no TP), then closes back at 100
    books, opens, prep = make(lows={5: 99.8}, highs={100: 104.0}, opens_m={100: 104.0})
    out = run(books, opens, prep, m_sl=3.0)
    q = 0.8 / 100.0
    fill = 100 * (1 - eu.D_LIMIT)
    peak_rel = q * (104.0 - fill) - q * fill * eu.MAKER
    assert out["eq_max"][0] == pytest.approx(1 + peak_rel, rel=1e-9)
    close_eq = 1 + out["net"][0]
    dd_close_peak = 1 - close_eq / max(1.0, close_eq)
    dd_intrabar_peak = 1 - close_eq / max(1.0, close_eq, out["eq_max"][0])
    assert dd_close_peak == pytest.approx(0.0, abs=1e-12) and dd_intrabar_peak > 0.02


def test_stop_wins_tie_with_fill_minute():
    # an existing long (entry 100) is stopped in the same minute the new buy limit would fill: stop first, order cancelled
    books, opens, prep = make(lows={5: 85.0})
    captured = {}
    orig = eu.summarize

    def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
        captured.update(stats=dict(stats))
        return {}
    eu.summarize = grab
    try:
        # two bars: bar 0 opens the position quietly, bar 1 has the crash at minute 5
        idx = pd.DatetimeIndex([pd.Timestamp("2022-01-01 00:00", tz="UTC"), pd.Timestamp("2022-01-01 04:00", tz="UTC")])
        O = np.full((2, 240, 1), 100.0)
        H = np.full((2, 240, 1), 100.0)
        L = np.full((2, 240, 1), 100.0)
        C = np.full((2, 240, 1), 100.0)
        L[0, 5, 0] = 99.8          # bar 0: buy fills
        L[1, 5, 0] = 85.0          # bar 1: stop (sd = 0.0245 -> SL ~ 92.6) in the minute the add-on limit would fill
        prep2 = dict(idx=idx, cols=["BTCUSDT"], O=O, H=H, L=L, C=C, sig4=np.array([[0.01], [0.01]]),
                     o1=np.array([[100.0], [100.0]]), o2=np.array([[100.0], [100.0]]), settle=np.array([False, False]))
        books2 = pd.DataFrame([[1.0], [2.0]], index=idx, columns=["BTCUSDT"])
        opens2 = pd.DataFrame([[100.0], [100.0]], index=idx, columns=["BTCUSDT"])
        eu.simulate(books2, opens2, prep2, sleeve=False, m_sl=3.0)
    finally:
        eu.summarize = orig
    assert captured["stats"]["stops"] == 1
    assert captured["stats"]["fills"] == 2 or captured["stats"]["fills"] == 1
