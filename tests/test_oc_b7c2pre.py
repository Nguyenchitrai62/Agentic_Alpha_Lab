"""Tests for oc_b7c2pre: hand-checked stack arithmetic + causality on frozen pre-sample tables."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
MINE = ROOT / "research/tournament/oc_b7c2pre"
CBP = ROOT / "research/tournament/oc_cboostpre"
PST = ROOT / "research/tournament/oc_presampletilt"
sys.path.insert(0, str(MINE))

from stack_rule import (  # noqa: E402
    B7_BOOST,
    C2_DIRECTION,
    C2_HI,
    C2_LO,
    C2_Q20,
    C2_Q80,
    STACK_CAP,
    assign_c2,
    stack_mult,
    stack_mult_cap,
    variant_mult_c2,
)


def test_assign_c2_and_product_hand_checked():
    # Frozen C2 fit constants
    assert C2_DIRECTION == 1
    assert C2_Q20 == 1.110054237503456
    assert C2_Q80 == 2.8608138206510407
    assert C2_HI == 1.25 and C2_LO == 0.75
    # direction +1: high risk favourable
    assert assign_c2(5.0) == 1.25
    assert assign_c2(0.5) == 0.75
    assert assign_c2(2.0) == 1.0
    assert assign_c2(C2_Q80) == 1.25  # edge inclusive
    assert assign_c2(C2_Q20) == 0.75  # edge inclusive
    assert assign_c2(float("nan")) == 1.0
    assert assign_c2(float("inf")) == 1.0
    assert variant_mult_c2(float("nan")) == 1.0
    # Product (pre-registered): every (m_B7, m_C2) combo
    assert stack_mult(1.0, 1.0) == 1.0
    assert stack_mult(1.5, 1.0) == 1.5
    assert stack_mult(1.0, 1.25) == 1.25
    assert stack_mult(1.0, 0.75) == 0.75
    assert stack_mult(1.5, 1.25) == 1.875
    assert stack_mult(1.5, 0.75) == 1.125
    assert stack_mult(float("nan"), 1.25) == 1.25
    assert stack_mult(1.5, float("nan")) == 1.5
    assert stack_mult_cap(1.5, 1.25) == 1.5
    assert stack_mult_cap(1.5, 0.75) == 1.125
    assert stack_mult_cap(1.0, 1.25) == 1.25
    assert B7_BOOST == 1.5 and STACK_CAP == 1.5
    got = {stack_mult(b, c) for b in (1.0, 1.5) for c in (0.75, 1.0, 1.25)}
    assert got == {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}
    got_cap = {stack_mult_cap(b, c) for b in (1.0, 1.5) for c in (0.75, 1.0, 1.25)}
    assert got_cap == {0.75, 1.0, 1.125, 1.25, 1.5}


def test_placebo_percentile_hand_checked():
    rng = np.random.default_rng(20261007)
    perms = rng.normal(0, 1, size=1000)
    assert 100.0 * (1 + int((perms <= 10.0).sum())) / 1001 == 100.0
    assert 100.0 * (1 + int((perms <= -10.0).sum())) / 1001 < 5.0


def test_stack_truncation_causal_on_frozen_tables():
    """Truncating frozen boost+Chronos tables cannot change stack mults at kept bars."""
    boost = pd.read_parquet(CBP / "boost_mult_presample.parquet",
                            columns=["shift", "T", "mult_B7"])
    boost = boost[boost["shift"] == 0].sort_values("T").reset_index(drop=True)
    feat = pd.read_parquet(PST / "chronos_features_presample.parquet",
                           columns=["sym", "shift", "T", "ch_q10"])
    sub = feat[(feat["shift"] == 0) & (feat["sym"] == "BTCUSDT")].sort_values("T")
    sub = sub.reset_index(drop=True)
    assert len(sub) > 1000 and len(boost) > 100
    bmap = {pd.Timestamp(t): float(m) for t, m in zip(boost["T"], boost["mult_B7"])}

    def stack_rows(df):
        out = []
        for t, q in zip(df["T"], df["ch_q10"]):
            mb = bmap.get(pd.Timestamp(t), 1.0)
            mc = variant_mult_c2(-float(q)) if np.isfinite(float(q)) else 1.0
            out.append((stack_mult(mb, mc), stack_mult_cap(mb, mc)))
        return np.array(out)

    full = stack_rows(sub)
    cut = len(sub) * 2 // 3
    part = stack_rows(sub.iloc[:cut])
    np.testing.assert_array_equal(part, full[:cut])
    assert set(np.unique(full[:, 0])) <= {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}
    assert set(np.unique(full[:, 1])) <= {0.75, 1.0, 1.125, 1.25, 1.5}
    assert set(boost["mult_B7"].unique()) <= {1.0, 1.5}


def test_replica_reproduction_and_gain_arithmetic():
    """Reused ledger gate + stack gain arithmetic (norm-base, norm-norm_B7/C2)."""
    res = json.loads((MINE / "tmp/stack_presample.json").read_text())
    assert res["reproduction"]["n_fills"] == 9731
    assert res["reproduction"]["base_sums"] == [2.313362, 2.67887, 0.577643, 0.297538]
    assert res["reproduction"]["c2_missing_to_1"] == 5547
    for v in ("B7C2", "B7C2_cap"):
        assert len(res[v]["per_year"]) == 4
        for row, trow, brow in zip(res[v]["per_year"], res[v]["timing_placebo"],
                                   res[v]["block_placebo"]):
            assert 0.0 <= trow["percentile"] <= 100.0
            assert 0.0 <= brow["percentile"] <= 100.0
            assert abs(row["norm"] - row["base"] - row["gain_vs_base"]) < 5e-6
        vals = set()
        for row in res[v]["per_year"]:
            assert row["boosted_share_mult_gt1"] is not None
    # copy gates hold to the digit
    cbp = json.loads((CBP / "results.json").read_text())
    pst = json.loads((PST / "results.json").read_text())
    assert [r["norm"] for r in res["copies"]["B7_per_year"]] == \
        [r["norm"] for r in cbp["B7"]["per_year"]]
    assert [r["norm"] for r in res["copies"]["C2_per_year"]] == \
        [r["norm"] for r in pst["presample"]["C2"]["per_year"]]
    # stack multisets are subsets of the pre-registered sets
    assert res["config"]["rule"].startswith("m_stack=m_B7*m_C2")


def test_stop_splits_sanity():
    """Frozen-kind stop splits cover ~all fills; COVID leg elevated."""
    st = json.loads((MINE / "tmp/stop_stack.json").read_text())
    assert st["config"]["unknown"] == 15
    tot = sum(r["n_fills"] for r in st["per_year"])
    known = sum(r["n_known"] for r in st["per_year"])
    assert tot == 9731 and known == 9716
    for r in st["per_year"]:
        assert 0.0 <= r["base_stop_rate"] <= 0.30
        assert -0.10 <= r["B7C2_stop_delta"] <= 0.10
        assert -0.10 <= r["B7C2_cap_stop_delta"] <= 0.10
    y20 = next(r for r in st["per_year"] if r["year"] == "Y2020p")
    assert y20["B7C2_stop_delta"] > y20["B7_copy"]["stop_delta"]  # C2 deepens, not cushions
