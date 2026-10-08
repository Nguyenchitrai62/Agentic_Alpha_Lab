"""oc_b7c2 tests: hand-checked stack arithmetic + causality/truncation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OC = ROOT / "research" / "tournament" / "oc_b7c2"
CB = ROOT / "research" / "tournament" / "oc_cascadeboost"
CH = ROOT / "research" / "tournament" / "oc_chronos"

sys.path.insert(0, str(OC))
from stack_rule import (  # noqa: E402
    ANCH5,
    B7_BOOST,
    C2_HI,
    C2_LO,
    STACK_CAP,
    anchor_of,
    assign_c2,
    stack_mult,
    stack_mult_cap,
)


def test_assign_c2_edges_and_stack_product_hand_checked():
    # C2 leg (direction +1, all five frozen Chronos anchors)
    assert assign_c2(5.0, 1, 0.5, 2.0) == 1.25
    assert assign_c2(0.1, 1, 0.5, 2.0) == 0.75
    assert assign_c2(1.0, 1, 0.5, 2.0) == 1.0
    assert assign_c2(2.0, 1, 0.5, 2.0) == 1.25  # edge inclusive
    assert assign_c2(0.5, 1, 0.5, 2.0) == 0.75  # edge inclusive
    assert assign_c2(float("nan"), 1, 0.5, 2.0) == 1.0
    assert assign_c2(float("inf"), 1, 0.5, 2.0) == 1.0
    assert assign_c2(5.0, -1, 0.5, 2.0) == 0.75
    assert assign_c2(0.1, -1, 0.5, 2.0) == 1.25
    assert C2_HI == 1.25 and C2_LO == 0.75
    # Stack product (pre-registered): every (m_B7, m_C2) combo
    assert stack_mult(1.0, 1.0) == 1.0
    assert stack_mult(1.5, 1.0) == 1.5
    assert stack_mult(1.0, 1.25) == 1.25
    assert stack_mult(1.0, 0.75) == 0.75
    assert stack_mult(1.5, 1.25) == 1.875
    assert stack_mult(1.5, 0.75) == 1.125
    assert stack_mult(float("nan"), 1.25) == 1.25  # missing leg -> 1.0
    assert stack_mult(1.5, float("nan")) == 1.5
    # Capped stack: min(product, 1.5)
    assert stack_mult_cap(1.5, 1.25) == 1.5
    assert stack_mult_cap(1.5, 0.75) == 1.125
    assert stack_mult_cap(1.0, 1.25) == 1.25
    assert stack_mult_cap(1.0, 1.0) == 1.0
    assert STACK_CAP == 1.5 and B7_BOOST == 1.5
    # Stack multiset is exactly the pre-registered set
    got = {stack_mult(b, c) for b in (1.0, 1.5) for c in (0.75, 1.0, 1.25)}
    assert got == {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}
    got_cap = {stack_mult_cap(b, c) for b in (1.0, 1.5) for c in (0.75, 1.0, 1.25)}
    assert got_cap == {0.75, 1.0, 1.125, 1.25, 1.5}
    # Year grid
    assert anchor_of("2021-09-24 00:00", 0) == 0
    assert anchor_of("2024-09-24 00:00", 0) == 3
    assert anchor_of("2024-09-24 03:00", 3) == 3
    assert anchor_of("2025-09-24 00:00", 0) == 4
    assert ANCH5[0] == "2021-09-24" and ANCH5[4] == "2025-09-24"


def test_stack_truncation_causal_on_frozen_tables():
    """Stack mults from truncated frozen tables equal the kept prefix.

    Uses the frozen boost parquet (B7 leg) + Chronos features (C2 leg) for
    BTCUSDT shift 0 in anchor year 2021: truncating the tables cannot change
    stack multipliers at kept (sym, T) — no future data leaks into past bars.
    """
    fits = json.loads((CH / "fits.json").read_text())
    f = fits["2021-09-24"]
    boost = pd.read_parquet(CB / "boost_mult_4shift.parquet",
                            columns=["shift", "T", "mult_B7"])
    boost = boost[boost["shift"] == 0].sort_values("T").reset_index(drop=True)
    feat = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                           columns=["sym", "shift", "T", "ch_q10"])
    sub = feat[(feat["shift"] == 0) & (feat["sym"] == "BTCUSDT")].sort_values("T")
    sub = sub[(sub["T"] >= "2021-09-24") & (sub["T"] < "2022-09-24")].reset_index(drop=True)
    assert len(sub) > 1000 and len(boost) > 1000
    bmap = {pd.Timestamp(t): float(m) for t, m in zip(boost["T"], boost["mult_B7"])}

    def stack_rows(df):
        out = []
        for t, q in zip(df["T"], df["ch_q10"]):
            mb = bmap.get(pd.Timestamp(t), 1.0)
            mc = assign_c2(-float(q), f["direction"], f["q20"], f["q80"]) \
                if np.isfinite(float(q)) else 1.0
            out.append((stack_mult(mb, mc), stack_mult_cap(mb, mc)))
        return np.array(out)

    full = stack_rows(sub)
    cut = len(sub) * 2 // 3
    part = stack_rows(sub.iloc[:cut])
    np.testing.assert_array_equal(part, full[:cut])
    # multisets are the pre-registered ones (or subsets on one coin-year)
    assert set(np.unique(full[:, 0])) <= {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}
    assert set(np.unique(full[:, 1])) <= {0.75, 1.0, 1.125, 1.25, 1.5}
    # boost leg is binary, C2 leg is ternary
    assert set(boost["mult_B7"].unique()) <= {1.0, 1.5}


def test_handchecked_geo_and_engine_constants():
    # Hand-checked: geo monthly mean arithmetic used in REPORT tables.
    Rs = [2.955, 3.264, 8.537, 12.486]  # oc_cascadeboost B7 dev4
    g = 100 * (float(np.prod([1 + r / 100 for r in Rs])) ** (1 / 4) - 1)
    assert abs(g - 6.738) < 0.002
    assert round(6.738 - 5.601, 3) == 1.137  # B7-REF dev4 gap (base)
    # Engine files pin the frozen mechanism (gross cap + win_start + stack lookup).
    src = (OC / "run_engine.py").read_text()
    assert "sleeve_gross_cap" in src and "2.0" in src
    assert "win_start=5" in src
    assert "gate costs inside the engine" in src
    assert "maker 0.0002" in src and "taker 0.00055" in src
    assert "boost_mult_4shift" in src and "chronos_features_4shift" in src
    s5 = (OC / "compute_s5_engine.py").read_text()
    assert "bybit_linear_1m_20261004" in s5 and "2021-11-15" in s5
    assert "B7C2_cap" in src and "stack_mult_cap" in src
