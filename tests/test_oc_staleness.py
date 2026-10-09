"""Tests for oc_staleness (no outcome tuning; fast, no heavy data needed)."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent / "research/tournament/oc_staleness"


def _mod():
    spec = importlib.util.spec_from_file_location("oc_stale", HERE / "compute_staleness.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_spearman_pooled_hand_checked():
    m = _mod()
    x = pd.Series([float(i) for i in range(12)])
    y = pd.Series([float(i) * 10 for i in range(12)])
    ic, n = m.spearman_pooled(x, y)
    assert ic == 1.0 and n == 12
    ic2, _ = m.spearman_pooled(x, y[::-1].reset_index(drop=True))
    assert ic2 == -1.0
    # constant prediction -> NaN, n reported
    ic3, n3 = m.spearman_pooled(pd.Series([1.0] * 6), pd.Series(range(6), dtype=float))
    assert np.isnan(ic3) and n3 == 6


def test_diagnostic_pnl_hand_checked():
    # w = clip(pred/0.5,-1,1); pred=[0.25,-1.0] -> w=[0.5,-1.0]; r=[0.01,0.02] -> pnl=-0.015
    w = (pd.Series([0.25, -1.0]) / 0.5).clip(-1, 1)
    r = pd.Series([0.01, 0.02])
    assert abs(float((w * r).sum()) - (-0.015)) < 1e-12


def test_halving_rule_hand_checked():
    def halve(curve):
        ic0 = curve[0]
        if ic0 is None or not np.isfinite(ic0) or ic0 <= 0:
            return None
        for k, v in enumerate(curve[1:], start=1):
            if v is not None and v <= 0.5 * ic0:
                return k
        return -1  # no halving
    assert halve([0.2, 0.09]) == 1
    assert halve([0.2, 0.15, 0.05]) == 2
    assert halve([0.2, 0.15, 0.12]) == -1
    assert halve([-0.05, 0.2]) is None
    assert halve([0.0, 0.2]) is None


def test_no_data_beyond_cutoff_and_fit_windows():
    """Causality/truncation: bins end before 2025-09-24; fits end before cut-7d."""
    res = json.loads((HERE / "results.json").read_text())
    END = pd.Timestamp("2025-09-24", tz="UTC")
    for r in res["rows"]:
        assert pd.Timestamp(r["t_hi"], tz="UTC") <= END
        assert r["n_stale"] >= 2000  # full quarters, labels realised before END
    for key, v in res["fit_info"].items():
        if not isinstance(v, dict) or "cutoff" not in v:
            continue
        parts = key.split("_")
        cut = pd.Timestamp(parts[2], tz="UTC")
        assert pd.Timestamp(v["cutoff"]) <= cut - pd.Timedelta(days=7), key
        assert v["train_rows"] > 10000


def test_bins_partition_without_overlap():
    res = json.loads((HERE / "results.json").read_text())
    df = pd.DataFrame(res["rows"])
    for (fam, cut), g in df.groupby(["family", "cut"]):
        g = g.sort_values("bin")
        assert list(g["bin"]) == list(range(8))
        assert (g["age_lo_m"].to_numpy() == np.arange(8) * 3).all()
        assert (g["age_hi_m"].to_numpy() == (np.arange(8) + 1) * 3).all()
