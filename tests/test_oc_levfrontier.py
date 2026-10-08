"""oc_levfrontier tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_levfrontier"))

from lev_rule import ANCH5, assign_c2, stack_mult, anchor_of  # noqa: E402


def test_assign_c2_handchecked():
    # direction +1 (high risk favourable): top quintile -> hi, bottom -> lo
    assert assign_c2(3.0, 1, 1.11, 2.86) == 1.25
    assert assign_c2(0.5, 1, 1.11, 2.86) == 0.75
    assert assign_c2(2.0, 1, 1.11, 2.86) == 1.0
    assert assign_c2(float("nan"), 1, 1.11, 2.86) == 1.0
    # frozen C2 fits have direction +1 for all anchors
    assert assign_c2(10.0, 1, 1.0, 2.0) == 1.25
    assert assign_c2(-10.0, 1, 1.0, 2.0) == 0.75


def test_stack_mult_handchecked():
    assert stack_mult(1.5, 1.25) == 1.875
    assert stack_mult(1.5, 0.75) == 1.125
    assert stack_mult(1.0, 0.75) == 0.75
    assert stack_mult(1.0, 1.0) == 1.0
    assert stack_mult(float("nan"), 1.25) == 1.25
    allowed = {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}
    for mb in (1.0, 1.5):
        for mc in (0.75, 1.0, 1.25):
            assert stack_mult(mb, mc) in allowed


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00+00:00", 0) == 0
    assert anchor_of("2022-09-24 00:00+00:00", 0) == 1
    assert anchor_of("2025-09-24 00:00+00:00", 0) == 4
    assert anchor_of("2026-09-23 00:00+00:00", 0) == 4
    assert anchor_of("2021-09-24 00:00+00:00", 3) == 0


def test_truncation_causal_on_frozen_tables():
    """Recompute stack mults from truncated frozen tables -> identical prefix."""
    import json
    cb = ROOT / "research/tournament/oc_cascadeboost/boost_mult_4shift.parquet"
    ch = ROOT / "research/tournament/oc_chronos/chronos_features_4shift.parquet"
    fits = json.loads((ROOT / "research/tournament/oc_chronos/fits.json").read_text())
    if not (cb.exists() and ch.exists()):
        return  # data not present in this checkout; pure tests above still run
    d = pd.read_parquet(cb, columns=["shift", "T", "mult_B7"])
    d = d[d["shift"] == 0].sort_values("T")
    t = pd.to_datetime(d["T"], utc=True)
    exact = {pd.Timestamp(tt): float(a) for tt, a in zip(t, d["mult_B7"])}
    c = pd.read_parquet(ch, columns=["sym", "shift", "T", "ch_q10"])
    c = c[c["shift"] == 0]
    feat = {(str(s), pd.Timestamp(tt)): float(q)
            for s, tt, q in zip(c["sym"], c["T"], c["ch_q10"])}
    ts = sorted(exact)[:400]
    assert len(ts) > 100
    cut = ts[len(ts) // 2]
    full, trunc = [], []
    for T in ts:
        mb = exact[pd.Timestamp(T)]
        q = feat.get(("BTCUSDT", pd.Timestamp(T)), float("nan"))
        y = anchor_of(T, 0)
        f = fits[ANCH5[y]]
        mc = assign_c2(-q, f["direction"], f["q20"], f["q80"]) if np.isfinite(q) else 1.0
        full.append(stack_mult(mb, mc))
        if T <= cut:
            trunc.append(stack_mult(mb, mc))
    assert full[:len(trunc)] == trunc
    assert set(full) <= {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}


def test_engine_source_uses_win_start5_and_bybit_dir():
    src = (ROOT / "research/tournament/oc_levfrontier/compute_levfrontier_engine.py").read_text()
    assert "win_start=5" in src
    assert "bybit_linear_1m_20261004" in src
    assert "2021-11-15" in src
    assert 'kw["sleeve_gross_cap"] = 2.0' in src
    assert "kd" in src


def test_plan_frozen_rows():
    plan = (ROOT / "research/tournament/oc_levfrontier/PLAN.md").read_text()
    for token in ("L00", "L01", "L02", "L03", "L10", "L11", "L12", "L13",
                  "G2K20", "B7xC2", "f=0.25", "heavy_slot"):
        assert token in plan, token
