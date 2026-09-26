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

    def grab(idx, net, eq, eq_min, g, stats):
        captured.update(net=net.copy(), stats=dict(stats), eq_min=eq_min.copy())
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
