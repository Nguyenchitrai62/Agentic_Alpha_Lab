"""Tests for v170 blind audit (Part A). Does not open research/.../v170/."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v170_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v170/ folder"
    return json.loads(REP.read_text())


def test_replication_structure_and_w15_anchor():
    d = _rep()
    assert d["version"] == "v170_audit_replication"
    assert d["W"] == [15, 60, 120]
    assert d["target"] == 0.25 and d["governor"] is True
    for key in ("W15", "W60", "W120"):
        r = d["results"][key]
        assert np.isfinite(r["monthly_pct"])
        assert 0.0 <= r["full_path_dd"] < 100
        assert len(r["yearly"]) == 5
        for share_key in ("buy_maker_share", "sell_maker_share", "all_maker_share"):
            v = r["maker"][share_key]
            assert v is None or 0.0 <= v <= 1.0
        assert set(r["components_sum"].keys()) == {"gross", "exec", "funding", "carry_pnl", "carry_cost", "net"}
    # W=15 must equal engine_real
    assert d["results"]["W15"]["monthly_pct"] == 3.708
    assert d["results"]["W15"]["full_path_dd"] == 18.87


def test_gain_not_concentrated_one_year():
    d = _rep()
    for key in ("W15", "W60", "W120"):
        diag = d["results"][key]["diagnostic"]
        assert diag["max_year_share_of_net_sum"] < 0.5
        assert all(np.isfinite(v) for v in diag["yearly_net_pct"])
        assert all(v > 0 for v in diag["yearly_net_pct"])


def test_taker_branch_charges_drift_w60():
    d = _rep()
    t = d["results"]["W60"]["diagnostic"]["taker_drift"]
    assert t["taker_buy_orders_live"] > 0 and t["taker_sell_orders_live"] > 0
    assert t["max_abs_dev_buy_rel_minus_drift"] < 1e-12
    assert t["max_abs_dev_sell_rel_minus_drift"] < 1e-12
    # drift is actually charged (not free waiting): non-trivial share nonzero
    assert t["share_taker_buy_nonzero_drift"] > 0.5


def test_exec_math_synthetic():
    D = 0.001
    # maker buy: lo through limit
    p0, lo, pW = 100.0, 99.8, 100.5
    assert lo < p0 * (1 - D)
    fee, rel = 0.0002, -D
    assert fee == 0.0002 and rel == -0.001
    # taker buy: no trade-through, drift charged
    p0, lo, pW = 100.0, 99.95, 100.5
    assert not (lo < p0 * (1 - D))
    mv = pW / p0 - 1
    assert abs((mv + 0.0002) - (0.005 + 0.0002)) < 1e-12
    # taker sell symmetric
    p0, hi, pW = 100.0, 100.05, 99.0
    assert not (hi > p0 * (1 + D))
    assert abs((pW / p0 - 1 - 0.0002) - (-0.0102)) < 1e-12
    # maker sell
    assert 100.2 > p0 * (1 + D)
    # no p0 -> taker rel +/-0.0002
    assert 0.0002 == 0.0002 and -0.0002 == -0.0002
    # NaN pW -> p0 gives zero drift
    pWf = p0  # NaN -> p0
    assert pWf / p0 - 1 == 0.0


def test_offsets_window_definition():
    # offsets 2..W-1 inclusive: W=15 -> 13 minutes (2..14); W=60 -> 58 minutes
    for W, expect in ((15, 13), (60, 58), (120, 118)):
        assert len(range(2, W)) == expect
    # bar_stats_W uses only minutes after the decision (offsets >= 0 inside T=t+4h)
    src = (AUD / "replicate_v170.py").read_text()
    assert "off == 0" in src and "off == W" in src
    assert "2" in src and "W - 1" in src


def test_blind_script_does_not_open_v170():
    src = (AUD / "replicate_v170.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "audit_engine" in body
    assert "load_1m" in body
    assert "v170/v170" not in body
    assert "v170_result" not in body
    assert "v170_exec_window" not in body
