"""Tests for v117 blind audit (Part A). No leader v117 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v117_audit")
REP = AUD / "replication.json"
KEYS = ("k12_primary_t15", "k42_primary_t15", "k6_reference_primary_t15")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v117/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(KEYS) <= set(d.keys())
    for key in KEYS:
        assert set(d[key].keys()) == {"normal", "fee_stress", "execution_stress"}
        for sc in ("normal", "fee_stress", "execution_stress"):
            r = d[key][sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] >= 0 and y["mean_g"] == 1.0
            assert 0.0 <= r["full_path_dd"] < 100
    assert d["meta"]["union_bars"] == 10950
    assert d["meta"]["n_live_bars"] == 10944
    assert d["meta"]["target"] == 0.15
    assert d["meta"]["governed"] is False


def test_k6_reference_matches_v115_primary():
    import json as _json

    d = _rep()
    v115 = _json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v115_audit/replication.json").read_text())
    for sc in ("normal", "fee_stress", "execution_stress"):
        for yb, yv in zip(d["k6_reference_primary_t15"][sc]["yearly"], v115["primary_t15"][sc]["yearly"]):
            assert yb["net_pct"] == yv["net_pct"]
            assert yb["max_drawdown_percent"] == yv["max_drawdown_percent"]
            assert yb["fills"] == yv["fills"]
        for fld in ("monthly_pct", "worst_year_dd", "full_path_dd"):
            assert d["k6_reference_primary_t15"][sc][fld] == v115["primary_t15"][sc][fld]


def test_slow_rebalance_changes_results():
    d = _rep()
    # slower rebalance must change results vs k=6 reference (different books/scales/s path)
    for sc in ("normal", "fee_stress", "execution_stress"):
        n6 = [y["net_pct"] for y in d["k6_reference_primary_t15"][sc]["yearly"]]
        n12 = [y["net_pct"] for y in d["k12_primary_t15"][sc]["yearly"]]
        n42 = [y["net_pct"] for y in d["k42_primary_t15"][sc]["yearly"]]
        assert n12 != n6
        assert n42 != n6
        assert n42 != n12
        # fills stay in a plausible replay range
        for key in KEYS:
            tot = sum(y["fills"] for y in d[key][sc]["yearly"])
            assert 8000 <= tot <= 12000


def test_books_scales_causal_shape():
    for k in (12, 42, 6):
        b = pd.read_csv(AUD / f"books_k{k}.csv", index_col=0, parse_dates=True)
        assert len(b) == 10950
        assert list(b.columns) == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        assert b.notna().all().all()
    s = pd.read_csv(AUD / "scales.csv", parse_dates=["t"])
    assert len(s) == 10950
    for c in ("s_k12_t15", "s_k42_t15", "s_k6_t15"):
        assert (s[c] > 0).all() and (s[c] <= 2.0 + 1e-12).all()
    # combined books include continuous per-book vol scales, so they move every bar;
    # check the k-variants are distinct but share shape/finiteness
    b6 = pd.read_csv(AUD / "books_k6.csv", index_col=0, parse_dates=True)
    b12 = pd.read_csv(AUD / "books_k12.csv", index_col=0, parse_dates=True)
    b42 = pd.read_csv(AUD / "books_k42.csv", index_col=0, parse_dates=True)
    assert not b12.equals(b6)
    assert not b42.equals(b6)
    assert not b42.equals(b12)
