"""oc_k2bybit tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OC = ROOT / "research" / "tournament" / "oc_k2bybit"
KH = ROOT / "research" / "tournament" / "oc_kronoshidden"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


TILT = _load("oc_k2bybit_tilt", OC / "tilt_rule.py")
ENG = _load("oc_k2bybit_eng", OC / "compute_k2bybit_engine.py")


def test_assign_mult_edges_k2():
    A = TILT.assign_mult
    # direction +1 (all five frozen anchors)
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


def test_friction_constants_match_robust_v421():
    # Exact defs from robust_v421.py / PLAN (one knob each, base win_start=5).
    assert ENG.fric_extra("base") == dict(win_start=5)
    assert ENG.fric_extra("S2") == dict(win_start=15, sleeve_start=16)
    assert ENG.fric_extra("S3") == dict(win_start=30, sleeve_start=31)
    assert ENG.fric_extra("S4") == dict(win_start=5, stop_slip=0.5)
    assert ENG.fric_extra("S5") == dict(win_start=5)
    # S1 cost stress constants present in source (patched + restored)
    src = (OC / "compute_k2bybit_engine.py").read_text()
    assert "0.0004" in src and "0.0007 + 0.0005" in src
    assert "S5_START" in src and "bybit_linear_1m_20261004" in src
    # S5 window start fixed by PLAN
    assert ENG.S5_START == pd.Timestamp("2021-11-15", tz="UTC")


def test_k2_truncation_causal_on_frozen_features():
    # Causality: K2 multipliers on a truncated feature table equal the prefix
    # of the full-table multipliers (no future low1 leaks into past bars).
    fits = json.loads((KH / "fits.json").read_text())
    feat = pd.read_parquet(KH / "kronos_features_4shift.parquet",
                           columns=["sym", "shift", "T", "low1"])
    sub = feat[(feat["shift"] == 0) & (feat["sym"] == "BTCUSDT")].sort_values("T")
    sub = sub[(sub["T"] >= "2021-09-24") & (sub["T"] < "2022-09-24")].reset_index(drop=True)
    assert len(sub) > 1000
    f = fits["2021-09-24"]

    def mults(df):
        r = -df["low1"].to_numpy(dtype=float)
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


def test_handchecked_geo_and_gap():
    # Hand-checked: geo monthly mean + K2-REF gap arithmetic used in REPORT.
    Rs = [2.469, 3.478, 6.679, 10.653]
    g = 100 * (float(np.prod([1 + r / 100 for r in Rs])) ** (1 / 4) - 1)
    assert abs(g - 5.772) < 0.002  # oc_kronoshidden K2 dev4
    assert round(5.772 - 5.601, 3) == 0.171  # K2-REF dev4 gap (base)
