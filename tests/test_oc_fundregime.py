"""oc_fundregime tests: funding as-of causality, cutoff causality, counts, no-1m, book wiring."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_fundregime"
sys.path.insert(0, str(OC))
import analyze_fundregime as A

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)


@pytest.fixture(scope="module")
def fund():
    return A.load_funding()


@pytest.fixture(scope="module")
def res():
    return json.loads((OC / "results.json").read_text())


def test_funding_files_span(fund):
    assert set(fund) == set(SYMS)
    for s, d in fund.items():
        assert {"calc_time", "funding_interval_hours", "last_funding_rate"} <= set(d.columns)
        assert d["calc_time"].min() <= pd.Timestamp("2020-10-01", tz="UTC")
        assert d["calc_time"].max() >= pd.Timestamp("2026-08-31", tz="UTC")
        # settlements are the regular 00/08/16 UTC grid except SOL Nov-2022 (2h crisis interval)
        hrs = pd.to_datetime(d["calc_time"], utc=True).dt.hour
        assert set(hrs.unique()) <= {0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22}


def test_funding_strictly_before_T(fund):
    """Truncating every coin panel to calc_time < T leaves F(T) unchanged (5 sampled T)."""
    books = A.research_books_d2()
    queries = pd.DatetimeIndex(sorted(set(books.index[::997]) | set(books.index[-5:])))
    ref = A.funding_feature(fund, queries)
    for T in queries[:: max(1, len(queries) // 5)][:5]:
        trunc = {s: d[d["calc_time"] < T].reset_index(drop=True) for s, d in fund.items()}
        for s, d in trunc.items():
            assert (pd.to_datetime(d["calc_time"], utc=True) < T).all(), f"{s} leaks at {T}"
        got = A.funding_feature(trunc, pd.DatetimeIndex([T])).iloc[0]
        want = ref.loc[T]
        if np.isnan(want):
            assert np.isnan(got), f"NaN mismatch at {T}"
        else:
            assert got == pytest.approx(want), f"F changed at {T}"


def test_dip_cutoffs_match_and_causal(fund, res):
    """Year-1 dip cut-offs equal quantiles of the previous-rows-only pool."""
    fills = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    fills["T"] = fills["t_fill"] - pd.to_timedelta(fills["f"], unit="m")
    m = fills["sym"].isin(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]) & fills["x1"].isin([2.5, 3.0, 3.5, 4.0, 5.0])
    d = fills[m].copy()
    assert len(d) == 6876
    d["F"] = A.funding_feature(fund, pd.DatetimeIndex(d["T"])).to_numpy()
    tr = d[(d["T"] < ANCHORS[0]) & d["F"].notna()]
    assert len(tr) >= 100
    assert tr["T"].max() < ANCHORS[0]
    q33, q67 = tr["F"].quantile(1 / 3), tr["F"].quantile(2 / 3)
    y1 = res["dips"]["yearly"][0]
    assert y1["cut_q33_bps"] == pytest.approx(q33 * 1e4)
    assert y1["cut_q67_bps"] == pytest.approx(q67 * 1e4)
    # LOYO fold held-out 2023-24 must exclude that year from training
    h = 2
    held = (d["T"] >= ANCHORS[h]) & (d["T"] < ANCHORS[h] + YEAR)
    assert held.sum() == 1330
    trm = pd.Series(False, index=d.index)
    for k in range(5):
        if k != h:
            trm |= (d["T"] >= ANCHORS[k]) & (d["T"] < ANCHORS[k] + YEAR)
    assert not (trm & held).any()


def test_book_cutoffs_match_and_causal(fund, res):
    """Year-1 book cut-offs equal quantiles of previous 4h clock times only."""
    books = A.research_books_d2()
    Fbar = A.funding_feature(fund, books.index)
    clock_pre = pd.date_range(pd.Timestamp("2020-09-21", tz="UTC"), ANCHORS[0], freq="4h")
    clock_pre = clock_pre[clock_pre < ANCHORS[0]]
    Fpre = A.funding_feature(fund, clock_pre)
    train = Fpre[Fpre.notna()]
    assert len(train) >= 100
    q33, q67 = float(train.quantile(1 / 3)), float(train.quantile(2 / 3))
    y1 = res["books"]["yearly"][0]
    assert y1["cut_q33_bps"] == pytest.approx(q33 * 1e4)
    assert y1["cut_q67_bps"] == pytest.approx(q67 * 1e4)
    assert y1["n_train_times"] == len(train) + int(((books.index < ANCHORS[0]) & Fbar.notna()).sum())


def test_counts_and_grid(res):
    assert res["meta"]["dip_T"][2] == 6876
    assert [r["n"] for r in res["dips"]["yearly"]] == [990, 1045, 1330, 989, 1144]
    assert res["meta"]["grid"][2] == 10955
    assert [r["n_bars"] for r in res["books"]["yearly"]] == [2190, 2190, 2190, 2190, 2189]


def test_no_1m_data():
    src = (OC / "analyze_fundregime.py").read_text()
    for token in ("premium_1m", "intraday", "_1m.parquet", "kline"):
        assert token not in src, f"1m token in script: {token}"


def test_books_cell_matches_formula():
    """One d2 cell recomputed by hand from the member files (oc_bookic math)."""
    C = ROOT / "artifacts/research/engine_real"
    cols = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    A_ = pd.read_parquet(C / "member_A_O1_orders.parquet")[cols]
    Aq = pd.read_parquet(C / "member_Aq_O1_orders.parquet")[cols]
    B = pd.read_parquet(C / "member_B_tv.parquet")[cols]
    Bq = pd.read_parquet(C / "member_Bq_tv.parquet")[cols]
    D = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0)[cols]
    Dq = pd.read_parquet(C / "members_quarterly_D.parquet")[cols]
    got = A.research_books_d2()
    t, s = got.index[1000], "ETHUSDT"
    o1 = 0.5 * (A_.loc[t, s] + B.loc[t, s]) / 2 + 0.5 * (Aq.loc[t, s] + Bq.loc[t, s]) / 2
    want = 0.8 * o1 + 0.2 * (D.loc[t, s] + Dq.loc[t, s]) / 2
    assert got.loc[t, s] == pytest.approx(want)
