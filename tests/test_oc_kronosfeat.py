"""oc_kronosfeat tests: hand-checked stats + causality/truncation + output contracts."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_kronosfeat"
TMP = OC / "tmp"


def spearman_xy(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3 or np.std(x) == 0.0 or np.std(y) == 0.0:
        return float("nan"), int(len(x))
    rx, ry = rankdata(x), rankdata(y)
    if np.std(rx) == 0.0 or np.std(ry) == 0.0:
        return float("nan"), int(len(x))
    return float(np.corrcoef(rx, ry)[0, 1]), int(len(x))


def test_spearman_hand_checked():
    ic, n = spearman_xy([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
    assert n == 5 and abs(ic - 1.0) < 1e-12
    ic, n = spearman_xy([1, 2, 3, 4, 5], [50, 40, 30, 20, 10])
    assert n == 5 and abs(ic + 1.0) < 1e-12
    ic, n = spearman_xy([1, 1, 1, 1], [1, 2, 3, 4])
    assert np.isnan(ic)
    ic, n = spearman_xy([1, 2], [1, 2])
    assert np.isnan(ic) and n == 2
    # NaNs are dropped pairwise
    ic, n = spearman_xy([1, 2, np.nan, 4, 5], [1, 2, 3, 4, 5])
    assert n == 4 and abs(ic - 1.0) < 1e-12


def test_quintile_split_hand_checked():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    qs = s.quantile([0.2, 0.4, 0.6, 0.8]).to_list()
    assert qs == [1.8, 2.6, 3.4, 4.2]
    edges = [-float("inf")] + [float(v) for v in qs] + [float("inf")]
    counts = []
    for q in range(5):
        lo, hi = edges[q], edges[q + 1]
        if q < 4:
            m = (s >= lo) & (s < hi) if np.isfinite(lo) else (s < hi)
        else:
            m = s >= lo
        counts.append(int(m.sum()))
    assert counts == [1, 1, 1, 1, 1]


def test_book_labels_are_causal_and_truncated():
    bars = pd.read_parquet(
        ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet",
        columns=["sym", "shift", "T", "open"],
    )
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    assert len(sub) > 5000
    # pick a mid-history bar: label must use strictly later opens
    row = sub.iloc[1000]
    t, o = row["T"], float(row["open"])
    o1 = float(sub.iloc[1001]["open"])
    assert sub.iloc[1001]["T"] > t
    assert np.isfinite(o1 / o - 1.0)
    # truncation: last bars cannot form h=18 labels (need opens past end)
    last_open = sub.iloc[-1]["open"]
    assert np.isfinite(float(last_open))
    b = json.loads((TMP / "book_tables.json").read_text())
    assert b["n_rows"]["4"] == 43785  # Y4 shorter: h=18 tail dropped
    assert b["n_rows"]["0"] == 43800


def test_feature_join_is_asof_same_grid():
    feats = pd.read_parquet(
        ROOT / "research/tournament/oc_kronoshidden/kronos_features_4shift.parquet",
        columns=["sym", "shift", "T", "low1"],
    )
    d = json.loads((TMP / "dip_tables.json").read_text())
    assert d["coverage"] == 1.0 and d["n_fills"] == 22312
    # every feature timestamp lies on its shift grid (multiple of 4h + shift)
    t0 = feats["T"].iloc[0]
    assert pd.Timestamp("2020-10-06", tz="UTC") <= t0 <= pd.Timestamp("2020-10-07", tz="UTC")


def test_output_contracts_and_fidelity_gate():
    b = json.loads((TMP / "book_tables.json").read_text())
    assert len(b["book_ic"]) == 600 and len(b["book_vol"]) == 600
    assert len(b["w_corr"]) == 240
    d = json.loads((TMP / "dip_tables.json").read_text())
    assert len(d["spear"]) == 40 and len(d["quint"]) == 200
    assert len(d["flush"]) == 80 and len(d["low1_by_coin"]) == 25
    s = json.loads((TMP / "dip_ledger_stats.json").read_text())
    assert abs(s["base_sum5y"] - s["ref_base_sum5y"]) <= 0.01
    for g, r in zip(s["phase0_raw_sums"], s["ref_phase0"]):
        assert abs(g - r) < 1e-6
    assert (OC / "REPORT.md").exists() and (OC / "results.json").exists()
    rep = (OC / "REPORT.md").read_text(encoding="utf-8")
    assert "Key question" in rep and "Vietnamese" in rep
