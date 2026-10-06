"""Tests for oc_coinbear (research/tournament/oc_coinbear). Lightweight checks on results.json + causality of regimes/filters."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_coinbear"
RES = HERE / "results.json"
PANEL = HERE / "panel.parquet"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_coinbear_compute", HERE / "compute_coinbear.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_coinbear/compute_coinbear.py first"
    assert PANEL.exists(), "panel.parquet missing"
    r = _load()
    for k in ("meta", "years", "window_W2", "full_path", "loyo", "decision"):
        assert k in r, k
    assert len(r["years"]) == 5
    for row in r["years"]:
        for k in ("n_bars", "share_btc_bear", "share_newly_halved",
                  "book_pnl_base", "book_pnl_rule", "long_pnl_base",
                  "long_pnl_rule", "worst_week_base", "worst_week_rule",
                  "maxDD_base", "maxDD_rule", "dd_not_worse", "pnl_ge95"):
            assert k in row, (row.get("year"), k)
    assert r["meta"]["n_bars"] == 10955
    assert r["meta"]["n_panel"] == 54775
    assert r["window_W2"]["window"] == "2023-04-17..2023-06-15"
    assert r["window_W2"]["n_bars"] == 354


def test_year_partition_covers_grid():
    r = _load()
    ns = [row["n_bars"] for row in r["years"]]
    assert sum(ns) == r["meta"]["n_bars"] == 10955, ns
    assert ns[2] == 2196  # leap-year partition 2023-09-24..2024-09-24
    assert (ns[0], ns[1], ns[3], ns[4]) == (2190, 2190, 2190, 2189)
    panel = pd.read_parquet(PANEL)
    assert len(panel) == 54775
    assert (pd.to_datetime(panel["T"], utc=True) < CUTOFF).all()


def test_turnover_cost():
    panel = pd.read_parquet(PANEL)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    for cost_col, w_col in (("cost_base", "w_base"), ("cost_rule", "w_rule")):
        assert (panel[cost_col].to_numpy(float) >= 0).all()
        tot_cost = float(panel[cost_col].sum())
        # recompute turnover with the path's OWN prev (first prev = 0)
        to = 0.0
        for s in SYMS:
            w = panel.loc[panel["sym"] == s].sort_values("T")[w_col].to_numpy(float)
            to += float(np.abs(w - np.concatenate([[0.0], w[:-1]])).sum())
        assert abs(tot_cost - MAKER * to) < 1e-9, (cost_col, tot_cost, to)


def test_decision_matches_counts():
    r = _load()
    ys = r["years"]
    n_dd = sum(1 for y in ys if y["maxDD_rule"] <= y["maxDD_base"] + 1e-12)
    n_p = 0
    for y in ys:
        b, q = y["book_pnl_base"], y["book_pnl_rule"]
        n_p += int(q >= 0.95 * b if b >= 0 else q >= 1.05 * b)
    assert r["decision"]["dd_not_worse_count"] == f"{n_dd}/5"
    assert r["decision"]["pnl_ge95_count"] == f"{n_p}/5"
    assert r["decision"]["promising"] == (n_dd >= 4 and n_p >= 4)
    assert r["decision"]["promising"] is False
    assert [y["dd_not_worse"] for y in ys] == [
        y["maxDD_rule"] <= y["maxDD_base"] + 1e-12 for y in ys]


def test_filter_math_handchecked():
    mod = _mod()
    idx = pd.date_range("2023-01-01", periods=4, freq="4h", tz="UTC")
    books = pd.DataFrame([[0.10, -0.10, 0.0, 0.04, -0.04]] * 4, index=idx, columns=SYMS)
    # bears: row0 BTC bear only; row1 ETH own-bear only; row2 both; row3 neither
    bears = {}
    for s in SYMS:
        bears[s] = pd.Series(False, index=idx)
    bears["BTCUSDT"] = pd.Series([True, False, True, False], index=idx)
    bears["ETHUSDT"] = pd.Series([False, True, True, False], index=idx)
    base, rule, newly = mod.apply_filters(books, bears)
    # row0 BTC bear: ALL longs halved in both (SOL 0.04 -> 0.02)
    assert base.iloc[0]["BNBUSDT"] == 0.05
    assert rule.iloc[0]["SOLUSDT"] == 0.02
    assert base.iloc[0]["SOLUSDT"] == 0.02
    assert base.iloc[0]["BTCUSDT"] == -0.10  # shorts unchanged
    assert base.iloc[0]["ETHUSDT"] == 0.0  # flat unchanged
    # row1 own-bear only (ETH): base unchanged, rule halves ETH long rows only
    eth_col = "ETHUSDT"
    # books row1 ETH entry is 0.0 (flat) -> unchanged; use BNB? BNB own bear is False
    # so rebuild a targeted frame for the own-bear-only case:
    b2 = pd.DataFrame([[0.08, 0.06, 0.06, 0.06, 0.06]] * 2,
                      index=idx[:2], columns=SYMS)
    bears2 = {s: pd.Series(False, index=idx[:2]) for s in SYMS}
    bears2["ETHUSDT"] = pd.Series([True, False], index=idx[:2])
    base2, rule2, newly2 = mod.apply_filters(b2, bears2)
    pd.testing.assert_frame_equal(base2.iloc[[0]], b2.iloc[[0]], check_dtype=False)
    assert rule2.iloc[0][eth_col] == 0.03  # own-bear long halved in RULE only
    assert rule2.iloc[0]["BNBUSDT"] == 0.08  # non-bear coin untouched
    assert newly2.iloc[0][eth_col] is True or newly2.iloc[0][eth_col] == True
    assert not newly2.iloc[0]["BNBUSDT"]
    # row2 both: halved in both; row3 neither: unchanged
    assert rule.iloc[2]["BNBUSDT"] == 0.05 and base.iloc[2]["BNBUSDT"] == 0.05
    pd.testing.assert_frame_equal(base.iloc[3:], books.iloc[3:], check_dtype=False)
    pd.testing.assert_frame_equal(rule.iloc[3:], books.iloc[3:], check_dtype=False)
    # BTC rows identical in BASE and RULE by construction
    pd.testing.assert_series_equal(base["BTCUSDT"], rule["BTCUSDT"], check_dtype=False)


def test_regimes_causal_on_truncation():
    mod = _mod()
    rng = np.random.default_rng(7)
    n = 1500
    idx = pd.date_range("2022-01-01", periods=n + 1, freq="4h", tz="UTC")
    opens = pd.DataFrame(
        {s: 100.0 * np.cumprod(1 + 0.004 * rng.standard_normal(n + 1)) for s in SYMS},
        index=idx,
    )
    grid = idx[:-1]
    bears = mod.build_bears(opens, grid)
    cut = grid[1000]
    opens_tr = opens[opens.index <= cut]
    grid_tr = grid[grid <= cut]
    bears_t = mod.build_bears(opens_tr, grid_tr)
    for s in SYMS:
        pd.testing.assert_series_equal(
            bears[s].reindex(grid_tr), bears_t[s], check_dtype=False
        )


def test_books_match_oc_bookic():
    mod = _mod()
    spec = importlib.util.spec_from_file_location(
        "oc_bookic_compute",
        HERE.parents[2] / "research" / "tournament" / "oc_bookic" / "compute_bookic.py",
    )
    bmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bmod)
    a = mod.research_books_d2()
    b = bmod.research_books_d2()
    common = a.index.intersection(b.index)
    assert len(common) > 10000
    pd.testing.assert_frame_equal(a.reindex(common), b.reindex(common), check_dtype=False)


def test_T_and_bounds():
    r = _load()
    assert pd.Timestamp(r["meta"]["grid_end"], tz="UTC") < CUTOFF
    assert pd.Timestamp(r["meta"]["grid_start"], tz="UTC") >= pd.Timestamp("2021-09-24", tz="UTC")
    panel = pd.read_parquet(PANEL)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    assert panel["pnl_base"].notna().all() and panel["pnl_rule"].notna().all()
    # RULE longs are never above BASE longs; shorts/flat bit-identical
    assert ((panel["w_rule"] <= panel["w"] + 1e-12) | (panel["w"] <= 0)).all()
    neg = panel["w"] < 0
    np.testing.assert_allclose(
        panel.loc[neg, "w_rule"].to_numpy(float),
        panel.loc[neg, "w_base"].to_numpy(float),
        rtol=1e-12,
    )
