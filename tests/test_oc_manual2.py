"""Lightweight checks for oc_manual2 (no market data, no simulation)."""
import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "oc_manual2", ROOT / "research/diagnostics/oc_manual2/oc_manual2.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_rows_fixed():
    assert MOD.ROWS == ["M5_humanBF", "M5_humanBF_top2", "M5_humanBF_btceth"]
    assert MOD.PIPES == {"M5": "v367"}
    assert list(MOD.ANCH5) == ["2021-09-24", "2022-09-24", "2023-09-24",
                               "2024-09-24", "2025-09-24"]
    assert MOD.CHOSEN_MULT == 1.5


def test_bear_halves_longs_only_and_is_causal():
    idx = pd.date_range("2022-01-01", periods=1300, freq="4h", tz="UTC")
    btc = pd.Series(100.0, index=idx)
    btc.iloc[1200:] = 50.0
    books = pd.DataFrame({"BTCUSDT": 1.0, "ETHUSDT": -2.0}, index=idx)
    out = MOD.bear_books(books, btc)
    assert float(out["BTCUSDT"].iloc[1199]) == 1.0
    assert float(out["BTCUSDT"].iloc[1299]) == 0.5
    assert (out["ETHUSDT"] == -2.0).all()
    out2 = MOD.bear_books(books.iloc[:1250], btc.iloc[:1250])
    assert out2["BTCUSDT"].iloc[1249] == out["BTCUSDT"].iloc[1249]


def test_pick_top2_and_ties():
    assert set(MOD.pick_top2([1.0, 1.0, 1.0, 1.0, 1.0])) == {0, 1}
    assert set(MOD.pick_top2([1.0, 5.0, 5.0, 2.0, 0.0])) == {1, 2}
    # tie for second place -> lower index wins
    assert set(MOD.pick_top2([9.0, 2.0, 2.0, 2.0, 0.0])) == {0, 1}


def test_coin_scores_sum_mapped_rungs_with_default():
    import datetime
    T = pd.Timestamp("2022-01-01", tz="UTC")
    cols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    lsz = {(T, "ETHUSDT", 1): 2.0, (T, "ETHUSDT", 3): 0.5,
           (T, "SOLUSDT", 1): 1.0}  # missing keys -> 1.0
    s = MOD.coin_scores(lsz, T, cols, (1, 3))
    assert s[1] == 2.5
    assert s[2] == 2.0  # 1.0 + default 1.0
    assert s[0] == 2.0  # default + default
    assert set(MOD.pick_top2(s)) == {1, 0} or set(MOD.pick_top2(s)) == {1, 2}


def test_sleeve_mult_night_and_chosen():
    assert MOD.sleeve_mult(True, {0, 1}, 0) == 0.0
    assert MOD.sleeve_mult(True, {0, 1}, 2) == 0.0
    assert MOD.sleeve_mult(False, {0, 1}, 0) == 1.5
    assert MOD.sleeve_mult(False, {0, 1}, 2) == 0.0


def test_summary_math():
    allres = {s: {"M5_humanBF": [dict(net=0.12, dd=5.0, nb=10, wb=6, nr=10, wr=7)] * 5}
              for s in range(4)}
    m = MOD.summary(allres, "M5_humanBF", [0, 1, 2, 3, 4])
    import numpy as np
    assert m["R"] == round(float(100 * ((1.12 ** 5) ** (1 / 60) - 1)), 3)
    assert m["book_win"] == 0.6
    assert m["win_all"] == round((24 + 28) / 80, 4)
    assert m["DD"] == 5.0 and m["DD_max"] == 5.0
