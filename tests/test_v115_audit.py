"""Tests for v115 blind audit (Part A). No leader v115 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v115_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v115/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(("primary_t15", "secondary_t25_governed", "hidden_year_1m_execution_strict")) <= set(d.keys())
    for key in ("primary_t15", "secondary_t25_governed"):
        assert set(d[key].keys()) == {"normal", "fee_stress", "execution_stress"}
        for sc in ("normal", "fee_stress", "execution_stress"):
            r = d[key][sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] >= 0 and 0.0 <= y["mean_g"] <= 1.0
            assert 0.0 <= r["full_path_dd"] < 100
    # ungoverned primary mean_g == 1
    for sc in ("normal", "fee_stress", "execution_stress"):
        for y in d["primary_t15"][sc]["yearly"]:
            assert y["mean_g"] == 1.0
    # governed secondary engages (not identically 1)
    assert any(y["mean_g"] < 1.0 for y in d["secondary_t25_governed"]["normal"]["yearly"])
    h = d["hidden_year_1m_execution_strict"]
    assert np.isfinite(h["net_pct"]) and 0.0 <= h["maker_fill_rate"] <= 1.0
    assert d["meta"]["union_bars"] == 10950
    assert d["meta"]["n_live_bars"] == 10944
    assert "j=i-2" in d["meta"]["wrapper_spec"]


def test_governor_and_calendar_math():
    for dd, want in [(0.0, 1.0), (0.10, 1.0), (0.15, 0.5), (0.20, 0.0)]:
        assert abs(float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0)) - want) < 1e-9
    assert 90 * 6 == 540
    assert (pd.Timestamp("2026-09-23", tz="UTC") - pd.Timestamp("2021-09-24", tz="UTC")).days == 1825


def test_books_scales_causal_shape():
    b = pd.read_csv(AUD / "books.csv", index_col=0, parse_dates=True)
    assert len(b) == 10950
    assert list(b.columns) == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert b.notna().all().all()
    s = pd.read_csv(AUD / "scales.csv", parse_dates=["t"])
    assert len(s) == 10950
    for c in ("s_primary_t15", "s_secondary_t25", "s_hidden_t15"):
        assert (s[c] > 0).all() and (s[c] <= 2.0 + 1e-12).all()
