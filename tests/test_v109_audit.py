"""Tests for v109 blind audit (Part A). No leader v109 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v109_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v109/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["union_bars"] == 10950
    assert d["n_taus"] == 1825
    assert len(d["gate_means_per_anchor_year"]) == 5
    for g in d["gate_means_per_anchor_year"]:
        for k in ("m_lo", "m94", "m103"):
            assert 0.0 <= g[k] <= 1.5, (k, g[k])
        assert g["n_bars"] == 2190
        assert g["n_taus"] in (365, 366)
    for sec in ("primary_ungated_yearly", "primary_gated_yearly",
                "secondary_v92_ungated_yearly", "secondary_v92_gated_yearly"):
        assert set(d[sec].keys()) == {"normal", "fee_stress", "execution_stress"}
        for sc, yearly in d[sec].items():
            assert len(yearly) == 5
            for y in yearly:
                assert y["bars"] == 2190
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] >= 0
    assert "t+(h+1)*4h <= tau" in d["gate_spec"]
    assert "UNGATED" in d["wrapper_spec"]


def test_gate_math_synthetic():
    # clip rule
    for ic, want in [(-0.05, 0.0), (0.0, 0.0), (0.05, 0.5), (0.10, 1.0), (0.20, 1.5), (0.30, 1.5)]:
        assert float(np.clip(ic / 0.10, 0.0, 1.5)) == want
    # label-realization window: t+(h+1)*4h <= tau excludes unreleased labels
    tau = pd.Timestamp("2022-01-01", tz="UTC")
    h = 42
    t_ok = tau - pd.Timedelta(hours=4 * (h + 1))
    t_bad = t_ok + pd.Timedelta(hours=4)
    assert t_ok + pd.Timedelta(hours=4 * (h + 1)) <= tau
    assert not (t_bad + pd.Timedelta(hours=4 * (h + 1)) <= tau)
    # 60-day left edge inclusive
    assert (tau - pd.Timedelta(days=60)) >= (tau - pd.Timedelta(days=60))
    # min-rows fallback
    assert 199 < 200  # documents GATE_MIN_ROWS=200 -> m=1


def test_gates_files_causal_shape():
    g = pd.read_csv(AUD / "gates.csv", parse_dates=["t"])
    assert len(g) == 10950
    for c in ("m_lo", "m94", "m103"):
        assert ((g[c] >= 0.0) & (g[c] <= 1.5)).all()
        assert g[c].notna().all()
    # gates are daily-ffilled: each block of 6 bars shares the same value
    for c in ("m_lo", "m94", "m103"):
        v = g[c].to_numpy()
        assert (v.reshape(-1, 6)[:, 0][:, None] == v.reshape(-1, 6)).all()
    # tau files
    for key in ("lo", "b94", "b103"):
        df = pd.read_csv(AUD / f"gates_tau_{key}.csv", parse_dates=["tau"])
        assert len(df) == 1825
        assert ((df["m"] >= 0.0) & (df["m"] <= 1.5)).all()
        # early taus have <200 rows -> m == 1
        assert (df.iloc[:3]["m"] == 1.0).all()
        assert (df.iloc[:3]["n_rows"] < 200).all()


def test_equity_files_cover_five_years():
    for name in ("equity_primary_ungated_normal.csv", "equity_primary_gated_normal.csv",
                 "equity_secondary_v92_gated_normal.csv"):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert len(df) == 10950
        assert df["net"].notna().all()
