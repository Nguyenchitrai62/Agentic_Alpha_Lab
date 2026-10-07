"""Tests for oc_premexpo (causality, tilt/control/placebo math, results consistency)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_premexpo"
CACHE = ROOT / "artifacts/research/engine_real"
USDT = ROOT / "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet"
CB = ROOT / "data/raw/coinbase_20260925/BTC-USD_1h.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
NS = 1_000_000_000

sys.path.insert(0, str(HERE))
import compute_premexpo as S


def _panel() -> pd.DataFrame:
    p = pd.read_parquet(HERE / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


def _res() -> dict:
    return json.loads((HERE / "results.json").read_text())


def test_books_match_formula():
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    books = 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2
    p = _panel()
    piv = p.pivot_table(index="T", columns="sym", values="w_base").sort_index()
    # w_base differs from raw books only on bear longs (x0.5); raw books are
    # recoverable where bear is False or weight <= 0. Check common grid overlap.
    assert len(piv) > 10000
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).fillna(False).reindex(piv.index).fillna(False).to_numpy(bool)
    raw = books.reindex(piv.index)[SYMS].to_numpy(float)
    wb = piv[SYMS].to_numpy(float)
    pos_bear = (raw > 0) & bear[:, None]
    np.testing.assert_allclose(wb[pos_bear], 0.5 * raw[pos_bear], rtol=0, atol=1e-12)
    np.testing.assert_allclose(wb[~pos_bear], raw[~pos_bear], rtol=0, atol=1e-12)


def test_both_z_causal():
    p = _panel()
    usdt = S.load_usdt()
    cb = S.load_cbpremium()
    grid = p["T"].drop_duplicates().sort_values().to_numpy()
    rng = np.random.default_rng(71)
    sample = rng.choice(np.arange(700, len(grid)), size=5, replace=False)
    for i in sorted(sample):
        T = pd.Timestamp(grid[i]).tz_convert("UTC")
        for df, col, key in ((usdt, "usdt_z90", "z_usdt"), (cb, "cbprem_z90", "z_cb")):
            trunc = df[df["end"] <= T - pd.Timedelta(seconds=1)]
            expect = float(trunc[col].iloc[-1]) if len(trunc) else np.nan
            got = float(p[p["T"] == T].iloc[0][key])
            if np.isnan(expect):
                assert np.isnan(got)
            else:
                assert np.isclose(got, expect, equal_nan=True), f"{key} mismatch at {T}"


def test_tilt_and_combined_math():
    p = _panel()
    for key, zk in (("mult_usdt", "z_usdt"), ("mult_cb", "z_cb")):
        z = p[zk].to_numpy(float)
        m = p[key].to_numpy(float)
        assert np.all(m[np.isfinite(z) & (z > 1.0)] == 1.15)
        assert np.all(m[np.isfinite(z) & (z < -1.0)] == 0.85)
        assert np.all(m[~np.isfinite(z) | ((z >= -1.0) & (z <= 1.0))] == 1.0)
    np.testing.assert_allclose(
        p["mult_comb"].to_numpy(float),
        (p["mult_usdt"].to_numpy(float) + p["mult_cb"].to_numpy(float)) / 2.0,
        rtol=0, atol=1e-12)
    # Combined levels are exactly the five expected averages.
    assert set(np.round(p["mult_comb"].unique(), 6)) <= {0.85, 0.925, 1.0, 1.075, 1.15}


def test_control_ratios_match_panel():
    p = _panel()
    res = _res()
    bounds = ANCHORS + [LAST_BOUND]
    for sname, mkey in (("usdt", "mult_usdt"), ("cb", "mult_cb"), ("combined", "mult_comb")):
        for k, y in enumerate(res["signals"][sname]["years"]):
            m = (p["T"] >= bounds[k]) & (p["T"] < bounds[k + 1])
            sub = p[m & (p["w_base"] > 0)]
            gb = float((sub["w_base"]).sum())
            gr = float((sub["w_base"] * sub[mkey]).sum())
            assert round(gb, 6) == y["long_gross_w_base"]
            assert round(gr, 6) == y["long_gross_w_rule"]
            cm = gr / gb if gb != 0 else 1.0
            assert round(cm, 6) == y["control_mult"] == y["avg_long_mult"]
            # gain stored from full precision; rounded legs double-round, so allow 2e-6.
            assert abs(float(y["long_pnl_rule"] - y["long_pnl_control"]) - y["gain_vs_control"]) < 2e-6


def test_placebo_preserves_rows():
    """Block shuffle preserves length + total row counts per mult level.

    Adjacent equal-valued run pairs merge on rebuild, so the run list itself
    can shrink by merges (documented); row counts per level stay exact.
    """
    p = _panel()
    grid = p["T"].drop_duplicates().sort_values()
    bounds = ANCHORS + [LAST_BOUND]
    for mkey in ("mult_usdt", "mult_cb", "mult_comb"):
        full = p.pivot_table(index="T", columns="sym", values=mkey).sort_index()[SYMS[0]].to_numpy(float)
        assert len(full) == 10955
        for seed in (S.FULL_SEED_BASE, S.FULL_SEED_BASE + 1):
            sh = S.shuffle_runs(full, seed)
            assert len(sh) == len(full)
            for v in (0.85, 1.0, 1.15, 0.925, 1.075):
                assert int(np.sum(full == v)) == int(np.sum(sh == v))
        # Yearly slice: same invariants inside year 2.
        k = 2
        m = ((grid >= bounds[k]) & (grid < bounds[k + 1])).to_numpy()
        seg = full[m]
        sh = S.shuffle_runs(seg, S.YEAR_SEED_BASE + 7)
        assert len(sh) == len(seg)
        for v in (0.85, 1.0, 1.15, 0.925, 1.075):
            assert int(np.sum(seg == v)) == int(np.sum(sh == v))


def test_synthetic_control_and_gain():
    w_base = np.array([[1.0, 0.0], [0.0, 2.0], [-1.0, 1.0]])
    r1 = np.array([[0.01, 0.02], [0.03, -0.01], [0.05, 0.02]])
    mult = np.array([1.15, 0.85, 1.0])
    yid = np.array([0, 0, 0])
    ry, _ = S.path_long_pnls(w_base, r1, mult, 0.0002, yid, n_years=1)
    # Hand check longs: weights [1.15, 0, 0/1.7, -/1.0] with own chain.
    w = np.where(w_base > 0, w_base * mult[:, None], w_base)
    cost = 0.0002 * np.abs(w - np.vstack([np.zeros((1, 2)), w[:-1]]))
    expect = float(np.sum((w * r1 - cost)[w_base > 0]))
    assert ry[0] == expect
    # Exposure-weighted control mult over the 3 long cells.
    gb = 1.0 + 2.0 + 1.0
    gr = 1.15 + 1.7 + 1.0
    cm = gr / gb
    cy, _ = S.path_long_pnls(w_base, r1, np.full(3, cm), 0.0002, yid, n_years=1)
    assert cy[0] != ry[0]  # timing differs from flat exposure


def test_results_verdicts_and_correlation():
    res = _res()
    assert res["meta"]["n_placebo"] == 500
    assert res["correlation_z_vs_z"]["full"] == round(float(np.corrcoef(
        _panel().drop_duplicates("T").sort_values("T")["z_usdt"].to_numpy(float),
        _panel().drop_duplicates("T").sort_values("T")["z_cb"].to_numpy(float))[0, 1]), 6)
    for sname, exp in (("usdt", "ALPHA"), ("cb", "EXPOSURE"), ("combined", "ALPHA")):
        t = res["signals"][sname]["total"]
        npos = sum(1 for y in res["signals"][sname]["years"] if y["gain_positive"])
        assert t["years_gain_positive"] == f"{npos}/5"
        want = "ALPHA" if (npos >= 4 and t["placebo_pct_5y"] >= 95.0) else "EXPOSURE"
        assert t["verdict"] == want == exp
        assert abs(t["long_pnl_rule"] - t["long_pnl_control"] - t["gain_vs_control"]) < 2e-6


def test_grid_bounds():
    p = _panel()
    assert (p["T"] < CUTOFF).all()
    grid = p["T"].drop_duplicates().sort_values()
    assert len(grid) == 10955
    bounds = ANCHORS + [LAST_BOUND]
    total = sum(int(((grid >= bounds[k]) & (grid < bounds[k + 1])).sum()) for k in range(5))
    assert total == len(grid)
    assert set(p["sym"].unique()) == set(SYMS)
