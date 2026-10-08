"""oc_c2frontier tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OC = ROOT / "research" / "tournament" / "oc_c2frontier"
CH = ROOT / "research" / "tournament" / "oc_chronos"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


TILT = _load("oc_c2frontier_tilt", OC / "tilt_rule.py")
ENG = _load("oc_c2frontier_eng", OC / "compute_frontier_engine.py")


def test_assign_mult_edges_c2():
    A = TILT.assign_mult
    # direction +1 (all five frozen Chronos anchors)
    assert A(5.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.25
    assert A(0.1, 1, 0.5, 2.0, 1.25, 0.75) == 0.75
    assert A(1.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    # exact edges inclusive
    assert A(2.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.25
    assert A(0.5, 1, 0.5, 2.0, 1.25, 0.75) == 0.75
    # missing -> 1.0 (no lookahead fill-in)
    assert A(float("nan"), 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    assert A(float("inf"), 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    # flipped direction sanity
    assert A(5.0, -1, 0.5, 2.0, 1.25, 0.75) == 0.75
    assert A(0.1, -1, 0.5, 2.0, 1.25, 0.75) == 1.25


def test_row_configs_match_plan():
    # Frozen PLAN configs: kd/G/tilt per row; F fixed 2.5; win_start 5; S5 start fixed.
    assert ENG.CONFIGS["D13BF"] == dict(kd=1.3, G=None, tilt=False)
    assert ENG.CONFIGS["D13BF_C2"] == dict(kd=1.3, G=None, tilt=True)
    assert ENG.CONFIGS["G2K20_C2"] == dict(kd=2.0, G=2.0, tilt=True)
    assert ENG.F_FLUSH == 2.5
    assert ENG.S5_START == pd.Timestamp("2021-11-15", tz="UTC")
    assert set(ENG.JOBS) == {"D13BF_base", "D13BF_C2_base", "G2K20_C2_base",
                             "D13BF_S5", "D13BF_C2_S5"}
    src = (OC / "compute_frontier_engine.py").read_text()
    assert "ch_q10" in src and "chronos_features_4shift" in src
    assert "bybit_linear_1m_20261004" in src
    assert "win_start=5" in src
    # C2 multipliers frozen from oc_chronos
    assert "1.25, 0.75" in src


def test_c2_truncation_causal_on_frozen_features():
    # Causality: C2 multipliers on a truncated feature table equal the prefix
    # of the full-table multipliers (no future ch_q10 leaks into past bars).
    fits = json.loads((CH / "fits.json").read_text())
    feat = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                           columns=["sym", "shift", "T", "ch_q10"])
    sub = feat[(feat["shift"] == 0) & (feat["sym"] == "BTCUSDT")].sort_values("T")
    sub = sub[(sub["T"] >= "2021-09-24") & (sub["T"] < "2022-09-24")].reset_index(drop=True)
    assert len(sub) > 1000
    f = fits["2021-09-24"]

    def mults(df):
        r = -df["ch_q10"].to_numpy(dtype=float)
        return np.array([TILT.assign_mult(v, f["direction"], f["q20"], f["q80"], 1.25, 0.75)
                         for v in r])

    full = mults(sub)
    cut = len(sub) * 2 // 3
    part = mults(sub.iloc[:cut])
    assert set(np.unique(full)) <= {0.75, 1.0, 1.25}
    np.testing.assert_array_equal(part, full[:cut])
    # year grid: truncate at an anchor boundary leaves year-0 prefix unchanged
    assert TILT.anchor_of("2021-09-24 00:00", 0) == 0
    assert TILT.anchor_of("2025-09-24 00:00", 0) == 4


def test_handchecked_geo_and_d13bf_gate():
    # Hand-checked: geo monthly mean arithmetic used in REPORT.
    Rs = [2.485, 3.286, 4.975, 9.526]
    g = 100 * (float(np.prod([1 + r / 100 for r in Rs])) ** (1 / 4) - 1)
    assert abs(g - 5.033) < 0.002  # v424 D13BF dev4 mean (hand-checked)
    # exact v424 D13BF dev4 rows reproduce the known 5y when combined with Y4 4.723
    Rs5 = [2.485, 3.286, 4.975, 9.526, 4.723]
    g5 = 100 * (float(np.prod([1 + r / 100 for r in Rs5])) ** (1 / 5) - 1)
    assert abs(g5 - 4.971) < 0.002  # v424 D13BF 5y gate value
