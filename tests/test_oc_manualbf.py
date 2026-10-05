"""Lightweight checks for oc_manualbf (no market data, no simulation)."""
import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "oc_manualbf", ROOT / "research/diagnostics/oc_manualbf/oc_manualbf.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_rows_fixed():
    assert MOD.ROWS == ["M4_base", "M4_human", "M4_humanBF",
                        "M5_base", "M5_human", "M5_humanBF"]
    assert MOD.PIPES == {"M4": "v362", "M5": "v367"}
    assert list(MOD.ANCH5) == ["2021-09-24", "2022-09-24", "2023-09-24",
                               "2024-09-24", "2025-09-24"]


def test_bear_halves_longs_only_and_is_causal():
    idx = pd.date_range("2022-01-01", periods=1300, freq="4h", tz="UTC")
    # flat at 100 for 1200 bars, then drop to 50: rows after the drop are bear
    btc = pd.Series(100.0, index=idx)
    btc.iloc[1200:] = 50.0
    books = pd.DataFrame({"BTCUSDT": 1.0, "ETHUSDT": -2.0}, index=idx)
    out = MOD.bear_books(books, btc)
    # warm-up / flat region: no bear -> unchanged
    assert float(out["BTCUSDT"].iloc[1199]) == 1.0
    # after a sustained drop below the 1200-bar mean: longs halved
    assert float(out["BTCUSDT"].iloc[1299]) == 0.5
    # shorts unchanged everywhere
    assert (out["ETHUSDT"] == -2.0).all()
    # causality: row t never depends on opens after t (truncate -> same prefix)
    out2 = MOD.bear_books(books.iloc[:1250], btc.iloc[:1250])
    assert out2["BTCUSDT"].iloc[1249] == out["BTCUSDT"].iloc[1249]


def test_bear_needs_sustained_history():
    idx = pd.date_range("2022-01-01", periods=700, freq="4h", tz="UTC")
    btc = pd.Series(100.0, index=idx)
    books = pd.DataFrame({"BTCUSDT": 1.0}, index=idx)
    out = MOD.bear_books(books, btc)
    assert (out["BTCUSDT"] == 1.0).all()  # flat market is never bear


def test_summary_math():
    allres = {s: {"M4_human": [dict(net=0.12, dd=5.0, nb=10, wb=6, nr=10, wr=7)] * 5}
              for s in range(4)}
    m = MOD.summary(allres, "M4_human", [0, 1, 2, 3, 4])
    import numpy as np
    assert m["R"] == round(float(100 * ((1.12 ** 5) ** (1 / 60) - 1)), 3)
    assert m["book_win"] == 0.6
    assert m["win_all"] == round((24 + 28) / 80, 4)
    assert m["DD"] == 5.0 and m["DD_max"] == 5.0
