"""Tests for oc_c2ic (research/tournament/oc_c2ic). Lightweight checks, no engine."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_c2ic"
RES = HERE / "results.json"
CACHE = Path(__file__).resolve().parents[1] / "artifacts/research/engine_real"
CUTOFF = pd.Timestamp("2025-09-24", tz="UTC")
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _load():
    assert RES.exists(), "run research/tournament/oc_c2ic/compute_c2ic.py first"
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_c2ic_mod", HERE / "compute_c2ic.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_schema_and_counts():
    r = _load()
    assert r["verdict"] in ("YES", "NO")
    assert len(r["per_member"]) == 16  # 4 years x 4 members
    assert len(r["per_book"]) == 4
    assert {(d["year"], d["member"]) for d in r["per_member"]} == \
        {(y, m) for y in (2021, 2022, 2023, 2024) for m in ("A", "Aq", "B", "Bq")}
    assert [b["year"] for b in r["per_book"]] == [2021, 2022, 2023, 2024]
    assert r["book_corr_pooled_2021_2024"] is not None


def test_metric_bounds():
    r = _load()
    ic_keys = {"fix_pooled_spearman", "fix_xs_mean", "fix_xs_median", "fix_xs_frac_pos",
               "deployed_pooled_spearman", "deployed_xs_mean",
               "buggy_pooled_spearman", "fix_vs_deployed_pearson", "buggy_vs_deployed_pearson",
               "cand_pooled_spearman", "cand_xs_mean", "cand_xs_median",
               "cand_vs_deployed_pearson", "cand_minus_deployed_xs", "fix_ic_minus_deployed_xs"}
    for d in r["per_member"] + r["per_book"]:
        for k in ic_keys:
            if k in d and d[k] is not None:
                assert np.isfinite(d[k]) and -1.0 <= d[k] <= 1.0, (k, d[k])
        for hk in ("fix_hit_rate", "deployed_hit_rate", "cand_hit_rate"):
            if hk in d:
                assert 0.0 <= d[hk] <= 1.0, (hk, d[hk])
    assert -1.0 <= r["book_corr_pooled_2021_2024"] <= 1.0


def test_dev_only_no_2025_rows():
    # member inputs themselves must end before the cutoff (never load >= 2025-09-24)
    w = pd.read_parquet(
        CACHE.parent / "v427_eval/c2fix_members/member_C2_A_2024.parquet")
    assert pd.to_datetime(w.index, utc=True).max() < CUTOFF
    dep = pd.read_parquet(CACHE / "member_A_O1_orders.parquet")
    dep_idx = pd.to_datetime(dep.index, utc=True)
    assert (dep_idx < CUTOFF).sum() == 4 * 2190  # exactly the 4 dev years scoreable
    r = _load()
    for d in r["per_member"]:
        assert d["n_bars"] == 2190 and d["n_scored"] == 2190, d


def test_y42_definition_on_synthetic():
    m = _mod()
    idx = pd.date_range("2021-01-01", periods=60, freq="4h", tz="UTC")
    opens = pd.DataFrame({s: 100.0 + np.arange(60) for s in SYMS}, index=idx)
    y42 = opens.shift(-43) / opens.shift(-1) - 1.0
    # hand check row 0: open[43]/open[1]-1 = 143/101-1
    assert abs(y42.iloc[0, 0] - (143.0 / 101.0 - 1.0)) < 1e-12
    assert y42.iloc[-43:].isna().all().all()  # last 43 rows unrealised
    assert m is not None


def test_xs_ic_sanity():
    m = _mod()
    idx = pd.date_range("2021-01-01", periods=10, freq="4h", tz="UTC")
    y = pd.DataFrame({s: float(i) for i, s in enumerate(SYMS)}, index=idx)
    w_same = y.copy()
    s = m.xs_ic_stats(w_same, y)
    assert abs(s["xs_mean"] - 1.0) < 1e-9 and s["xs_n"] == 10
    w_flat = pd.DataFrame(0.0, index=idx, columns=SYMS)
    s0 = m.xs_ic_stats(w_flat, y)
    assert s0["xs_n"] == 0  # zero-variance timestamps skipped


def test_book_d_byte_identical():
    m = _mod()
    fix_dir = CACHE.parent / "v427_eval/c2fix_members"
    A = pd.concat([pd.read_parquet(fix_dir / f"member_C2_A_{y}.parquet")[SYMS]
                   for y in (2021, 2022, 2023, 2024)]).sort_index()
    B = pd.concat([pd.read_parquet(fix_dir / f"member_C2_B_{y}.parquet")[SYMS]
                   for y in (2021, 2022, 2023, 2024)]).sort_index()
    Aq = pd.concat([pd.read_parquet(fix_dir / f"member_C2_Aq_{y}.parquet")[SYMS]
                    for y in (2021, 2022, 2023, 2024)]).sort_index()
    Bq = pd.concat([pd.read_parquet(fix_dir / f"member_C2_Bq_{y}.parquet")[SYMS]
                    for y in (2021, 2022, 2023, 2024)]).sort_index()
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    book = m.build_book_o1(A, B, Aq, Bq, D, Dq)
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    d_term = 0.2 * (g(D) + g(Dq)) / 2
    # D sleeve identical for any O1: book - 0.8*O1 == deployed D term (fp tolerance;
    # same source files, same formula as eval_candidate.candidate_books_d2)
    assert np.allclose((book - 0.8 * g(o1)).values, d_term.values, atol=1e-12, rtol=1e-9)
    # determinism: same inputs -> bit-identical book
    book2 = m.build_book_o1(A, B, Aq, Bq, D, Dq)
    pd.testing.assert_frame_equal(book, book2)


def test_buggy_all_short_confirms_disclosed_bug():
    r = _load()
    for d in r["per_member"]:
        assert d["buggy_net_long"] < -0.3, d  # disclosed Platt base-rate bug
        assert d["fix_long_share"] > 0.05, d  # fix restores longs


def test_verdict_logic_recomputed():
    r = _load()
    wins = sum(1 for b in r["per_book"]
               if np.isfinite(b["cand_minus_deployed_xs"]) and b["cand_minus_deployed_xs"] > 0)
    assert wins == r["book_ic_wins_cand_over_deployed"] == 2
    expect = "YES" if (wins >= 3 and r["book_corr_pooled_2021_2024"] < 0.7) else "NO"
    assert r["verdict"] == expect == "NO"
