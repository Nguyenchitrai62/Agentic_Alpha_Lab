"""Tests for oc_lsratio (IDEAS5 §7 top-trader LS-ratio contrarian gate).

Covers: hand-checked synthetic gate cases + causality/truncation (asof excludes
the contemporaneous print; pre-anchor embargo windows).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_lsratio"))

from lsratio_rule import anchor_of, asof_ratio, gate_long, gate_short


def test_handchecked_gates():
    # frozen thresholds p90=2.5, p10=1.2
    assert gate_long(2.50001, 2.5) is True
    assert gate_long(2.5, 2.5) is False  # strictly greater
    assert gate_long(2.4, 2.5) is False
    assert gate_short(1.19999, 1.2) is True
    assert gate_short(1.2, 1.2) is False  # strictly less
    assert gate_short(1.3, 1.2) is False
    # NaN / non-positive never gate
    assert gate_long(float("nan"), 2.5) is False
    assert gate_short(float("nan"), 1.2) is False
    assert gate_long(-1.0, 2.5) is False
    assert gate_short(1.0, float("nan")) is False
    # L2 symmetry: middle value gates neither side
    assert gate_long(1.8, 2.5) is False and gate_short(1.8, 1.2) is False


def test_asof_causality_truncation():
    # 5-min prints at 00:00, 00:05, 00:10; query T=04:00 with 5-min lag -> q=03:55
    mt = np.array([
        pd.Timestamp("2021-01-01 03:50", tz="UTC").value,
        pd.Timestamp("2021-01-01 03:55", tz="UTC").value,
        pd.Timestamp("2021-01-01 04:00", tz="UTC").value,  # contemporaneous: excluded
        pd.Timestamp("2021-01-01 04:05", tz="UTC").value,  # future: excluded
    ])
    mv = np.array([1.0, 2.0, 99.0, 100.0])
    q = np.array([pd.Timestamp("2021-01-01 04:00", tz="UTC").value - 5 * 60 * 10**9])
    out = asof_ratio(mt, mv, q)
    assert float(out[0]) == 2.0  # 03:55 print, NOT the 04:00 print
    # query before any print -> NaN (never gate, no imputation)
    q0 = np.array([pd.Timestamp("2020-01-01", tz="UTC").value])
    assert bool(np.isnan(asof_ratio(mt, mv, q0)[0])) is True
    # non-positive / non-finite prints -> NaN (gate-off, never imputed)
    out2 = asof_ratio(np.array([10, 20, 30]), np.array([1.5, -2.0, np.inf]),
                      np.array([15, 20, 25]))
    assert float(out2[0]) == 1.5  # last print <= 15 is 10 -> 1.5
    assert bool(np.isnan(out2[1])) is True  # print at 20 is -2.0 -> NaN
    assert bool(np.isnan(out2[2])) is True  # last print <= 25 is 20 -> NaN


def test_anchor_and_embargo_windows():
    # anchor mapping on the standard grid
    assert anchor_of("2021-09-24") == 0
    assert anchor_of("2022-09-23 20:00+00:00") == 0
    assert anchor_of("2022-09-24") == 1
    assert anchor_of("2025-09-24") == 4
    # embargo: norm window for anchor A ends 7d before A (PLAN.md [A-372d, A-7d))
    A = pd.Timestamp("2022-09-24", tz="UTC")
    lo = A - pd.Timedelta(days=372)
    hi = A - pd.Timedelta(days=7)
    assert lo == pd.Timestamp("2021-09-17", tz="UTC")
    assert hi == pd.Timestamp("2022-09-17", tz="UTC")
    # a bar inside the embargo week must NOT belong to the norm pool
    t_emb = pd.Timestamp("2022-09-20 00:00", tz="UTC")
    assert bool(lo <= t_emb < hi) is False
    t_in = pd.Timestamp("2022-09-16 00:00", tz="UTC")
    assert bool(lo <= t_in < hi) is True


def test_real_norms_match_embargoed_window():
    """Stored p90/p10 equal the embargoed-window quantiles (no test-year leak)."""
    tmp = ROOT / "research/tournament/oc_lsratio/tmp"
    panel_p = tmp / "lsratio_panel.parquet"
    norms_p = tmp / "norms.json"
    if not (panel_p.exists() and norms_p.exists()):
        import pytest
        pytest.skip("compute_lsratio.py has not run yet")
    import json
    panel = pd.read_parquet(panel_p, columns=["T", "LS_BTCUSDT"])
    norms = json.loads(norms_p.read_text())
    T = pd.to_datetime(panel["T"], utc=True)
    ls = panel["LS_BTCUSDT"].to_numpy(dtype=float)
    A = pd.Timestamp("2023-09-24", tz="UTC")
    lo, hi = A - pd.Timedelta(days=372), A - pd.Timedelta(days=7)
    w = ls[((T >= lo) & (T < hi)).to_numpy()]
    w = w[np.isfinite(w) & (w > 0)]
    assert len(w) >= 1000
    exp90, exp10 = float(np.percentile(w, 90.0)), float(np.percentile(w, 10.0))
    got = norms["BTCUSDT"]["2023-09-24"]
    assert got["p90"] == exp90 and got["p10"] == exp10
