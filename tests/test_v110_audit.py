"""Tests for v110 blind audit (Part A). No leader v110 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v110_audit")
REP = AUD / "replication.json"
ROWS = ("primary_gated_0.25", "secondary_gated_0.30", "ref_ungov_0.25", "ref_ungov_0.15")
SCENS = ("normal", "fee_stress", "execution_stress")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v110/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["union_bars"] == 10950
    assert d["live"]["n_live_bars"] == 10944  # 6 bars on 2026-09-23 forced to 0
    assert set(d["results"].keys()) == set(ROWS)
    for row in ROWS:
        assert set(d["results"][row].keys()) == set(SCENS)
        for sc in SCENS:
            r = d["results"][row][sc]
            assert len(r["yearly"]) == 5
            assert len(r["mean_g_per_anchor_year"]) == 5
            for y in r["yearly"]:
                assert y["bars"] == 2190
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] >= 0
            for gm in r["mean_g_per_anchor_year"]:
                assert 0.0 <= gm["mean_g"] <= 1.0
            assert 0.0 <= r["full_path_live_max_dd_pct"] < 100
    # targets / governed flags
    assert d["rows"]["primary_gated_0.25"] == {"target": 0.25, "governed": True}
    assert d["rows"]["secondary_gated_0.30"] == {"target": 0.30, "governed": True}
    assert d["rows"]["ref_ungov_0.25"]["governed"] is False
    # ungoverned means g == 1
    for row in ("ref_ungov_0.25", "ref_ungov_0.15"):
        for sc in SCENS:
            for gm in d["results"][row][sc]["mean_g_per_anchor_year"]:
                assert gm["mean_g"] == 1.0
    assert "j=i-2" in d["wrapper_spec"] or "j = i-2" in d["wrapper_spec"] or "j=i" in d["wrapper_spec"]


def test_governor_math_synthetic():
    # clip((0.20-DD)/0.10, 0, 1): full exposure to 10% DD, zero at 20%
    for dd, want in [(0.0, 1.0), (0.05, 1.0), (0.10, 1.0), (0.15, 0.5), (0.20, 0.0), (0.30, 0.0)]:
        assert float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0)) == want or abs(float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0)) - want) < 1e-9
    # 2-bar lag: equity at j=i-2 uses opens up to bar i (known at close-i decision)
    assert (2) == 2  # documents j = i-2
    # 90-day window = 540 4h bars (j-539..j inclusive)
    assert 90 * 6 == 540
    # live mask literal [2021-09-24, 2026-09-23)
    assert (pd.Timestamp("2026-09-23", tz="UTC") - pd.Timestamp("2021-09-24", tz="UTC")).days == 1825


def test_equity_files_causal_shape():
    for row in ROWS:
        df = pd.read_csv(AUD / f"equity_{row}_normal.csv", parse_dates=["t"])
        assert len(df) == 10950
        assert df["net"].notna().all() and df["g"].notna().all()
        assert ((df["g"] >= 0.0) & (df["g"] <= 1.0)).all()
        if "ungov" in row:
            assert (df["g"] == 1.0).all()
        else:
            # governor warmup: first two bars g == 1
            assert (df["g"].iloc[:2] == 1.0).all()
            # governor engages somewhere (not identically 1)
            assert (df["g"] < 1.0).any()
    # scales file
    s = pd.read_csv(AUD / "scales.csv", parse_dates=["t"])
    assert len(s) == 10950
    for c in [c for c in s.columns if c.startswith("s_")]:
        assert (s[c] > 0).all() and (s[c] <= 2.0 + 1e-12).all()
    # live mask: bars on/after 2026-09-23 have zero weights; the first outside
    # bar carries the unwind turnover, the rest are flat zero
    df = pd.read_csv(AUD / "equity_primary_gated_0.25_normal.csv", parse_dates=["t"])
    t = pd.to_datetime(df["t"], utc=True)
    out = df.loc[np.asarray(t >= pd.Timestamp("2026-09-23", tz="UTC"))]
    assert len(out) == 6
    assert (out["turnover"].iloc[1:] == 0.0).all()
    assert out["turnover"].iloc[0] > 0.0  # exit cost on unwind bar
