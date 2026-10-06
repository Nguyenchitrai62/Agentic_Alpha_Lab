"""Tests for oc_bullshort (research/tournament/oc_bullshort). Lightweight checks on results.json + causality of filters/scales."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_bullshort"
RES = HERE / "results.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_bullshort_compute", HERE / "compute_bullshort.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic(n=500, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n + 1, freq="4h", tz="UTC")
    opens = pd.DataFrame({s: 100.0 * np.cumprod(1 + 0.005 * rng.standard_normal(n + 1)) for s in SYMS}, index=idx)
    books = pd.DataFrame(rng.standard_normal((n + 1, len(SYMS))) * 0.05,
                         index=idx, columns=SYMS)
    fwd1 = opens.shift(-1) / opens - 1.0
    books, fwd1 = books.iloc[:-1], fwd1.iloc[:-1]
    return books, fwd1, opens


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_bullshort/compute_bullshort.py first"
    r = _load()
    for k in ("variants", "decision", "definitions", "anchor_years", "n_bars"):
        assert k in r, k
    assert set(r["variants"]) == {"B0_bearLong05", "B1_bullShort05", "B2_bullShort00"}
    assert set(r["decision"]) == {"B1_bullShort05", "B2_bullShort00"}
    for name, v in r["variants"].items():
        assert len(v["per_year"]) == 5, name
        for row in v["per_year"]:
            for k in ("n_bars", "ret", "dd", "sharpe", "pnl_long", "pnl_short"):
                assert k in row, (name, row)
    assert r["n_bars"] == 10955


def test_year_partition_covers_grid():
    r = _load()
    per = r["variants"]["B0_bearLong05"]["per_year"]
    ns = [row["n_bars"] for row in per]
    assert sum(ns) == r["n_bars"], ns
    assert ns[2] == 2196  # leap-year partition 2023-09-24..2024-09-24
    assert ns[0] == 2190 and ns[1] == 2190 and ns[3] == 2190 and ns[4] == 2189


def test_turnover_cost_nonnegative():
    r = _load()
    for name, v in r["variants"].items():
        assert v["total_turnover"] >= 0, name
        assert v["total_cost"] >= 0, name
        assert abs(v["total_cost"] - 0.0005 * v["total_turnover"]) < 5e-4, name


def test_decision_matches_counts():
    r = _load()
    for name, d in r["decision"].items():
        n_ret = sum(1 for x in d["dRet"] if x is not None and x > 0)
        n_dd = sum(1 for x in d["dDD"] if x is not None and x > 0)
        assert d["ret_pos"] == f"{n_ret}/5", name
        assert d["dd_pos"] == f"{n_dd}/5", name
        expect = n_ret >= 4 and n_dd >= 4 and int(d["loyo_ret"][0]) >= 4 and int(d["loyo_dd"][0]) >= 4
        assert d["promising"] == expect, name
    assert all(not r["decision"][k]["promising"] for k in r["decision"])


def test_filter_math_handchecked():
    mod = _mod()
    idx = pd.date_range("2023-01-01", periods=4, freq="4h", tz="UTC")
    books = pd.DataFrame([[0.10, -0.10, 0.0, 0.04, -0.04]] * 4, index=idx, columns=SYMS)
    bear = pd.Series([True, False, False, False], index=idx)
    bull = pd.Series([False, True, False, False], index=idx)
    out = mod.apply_filters(books, bear, bull)
    # row0 bear: longs halved, shorts unchanged
    assert out["B0_bearLong05"].iloc[0]["BNBUSDT"] == 0.05
    assert out["B0_bearLong05"].iloc[0]["BTCUSDT"] == -0.10
    # row1 bull: B1 shorts halved, B2 shorts zero, longs unchanged
    assert out["B1_bullShort05"].iloc[1]["BTCUSDT"] == -0.05
    assert out["B2_bullShort00"].iloc[1]["BTCUSDT"] == 0.0
    assert out["B1_bullShort05"].iloc[1]["BNBUSDT"] == 0.10
    # rows 2-3 neutral: unchanged
    pd.testing.assert_frame_equal(out["B0_bearLong05"].iloc[2:], books.iloc[2:], check_dtype=False)
    pd.testing.assert_frame_equal(out["B1_bullShort05"].iloc[3:], out["B0_bearLong05"].iloc[3:], check_dtype=False)


def test_regimes_causal_on_truncation():
    mod = _mod()
    _, _, opens = _synthetic(n=1500)
    grid = opens.index[:-1]
    bear_full, bull_full = mod.build_regimes(opens, grid)
    cut = grid[1000]
    opens_tr = opens[opens.index <= cut + pd.Timedelta(hours=8)]
    grid_tr = grid[grid <= cut]
    bear_tr, bull_tr = mod.build_regimes(opens_tr, grid_tr)
    pd.testing.assert_series_equal(bear_full.reindex(grid_tr), bear_tr, check_dtype=False)
    pd.testing.assert_series_equal(bull_full.reindex(grid_tr), bull_tr, check_dtype=False)


def test_scales_causal_on_truncation():
    mod = _mod()
    books, fwd1, opens = _synthetic()
    grid = books.index
    bear, bull = mod.build_regimes(opens.reindex(grid.union([grid[-1] + pd.Timedelta(hours=4)])), grid)
    filt = mod.apply_filters(books, bear, bull)
    full, _ = mod.compute_scales(filt, fwd1)
    for cut in (300, 420):
        filt_p = {k: v.iloc[: cut + 1] for k, v in filt.items()}
        part, _ = mod.compute_scales(filt_p, fwd1.iloc[: cut + 1])
        for name in full:
            pd.testing.assert_frame_equal(full[name].iloc[: cut + 1], part[name], check_dtype=False)
