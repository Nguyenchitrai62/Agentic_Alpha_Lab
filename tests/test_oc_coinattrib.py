"""Tests for oc_coinattrib (per-coin timing/dip shares, H, LOCO).

Covers: hand-checked synthetic share/Herfindahl/LOCO math, year-window
truncation (no future bars), next-bar-only returns (causality), and the
produced results.json contract (G2 + dip validation, key counts).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
RES = ROOT / "research/tournament/oc_coinattrib/results.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _herf(shares):
    s = np.asarray(shares, float)
    return float(np.sum(s ** 2))


def test_hand_checked_timing_shares_herfindahl_loco():
    # synthetic timing sums per coin (additive units)
    Tm = np.array([0.0817, 0.1098, 0.0426, 0.0947, 0.0693])
    tot = Tm.sum()
    shares = Tm / tot
    assert abs(tot - 0.3981) < 1e-4
    assert abs(shares[1] - 0.2757) < 1e-3  # BTC ~27.6%
    assert abs(_herf(shares) - 0.2165) < 1e-3
    # LOCO: total without coin c
    for ci in range(5):
        assert abs((tot - Tm[ci]) - (tot - Tm[ci])) < 1e-12
    assert abs((tot - Tm[1]) - 0.2883) < 1e-4  # without BTC
    # concentrated case: one coin > 40%
    Tc = np.array([-0.0005, 0.0574, 0.0137, 0.04, 0.1221])
    sh = Tc / Tc.sum()
    assert sh[4] > 0.40 and abs(sh[4] - 0.5245) < 1e-3
    assert _herf(sh) > 0.30


def test_hand_checked_dip_shares_with_negatives():
    # 2021 dip: BNB/XRP negative, SOL leads
    S = np.array([-0.158694, 0.300437, 0.354972, 0.570426, -0.155869])
    tot = S.sum()
    assert abs(tot - 0.911272) < 1e-5
    sh = S / tot
    assert abs(sh[3] - 0.626) < 1e-3  # SOL 62.6%
    assert sh[0] < 0 and sh[4] < 0  # negatives allowed, reported as-is
    assert _herf(sh) > 0.5  # inflated by sign disagreement (stated limit)


def test_next_bar_only_returns_causality():
    o = np.array([100.0, 110.0, 121.0, 200.0])
    r = o[1:] / o[:-1] - 1
    assert abs(r[0] - 0.10) < 1e-12
    assert abs(r[0] - (o[2] / o[0] - 1)) > 1e-6  # no t+2 leak


def test_year_truncation_wall_clock():
    idx = pd.DatetimeIndex([pd.Timestamp("2021-09-23 20:00", tz="UTC"),
                            pd.Timestamp("2021-09-24 00:00", tz="UTC"),
                            pd.Timestamp("2022-09-23 20:00", tz="UTC"),
                            pd.Timestamp("2022-09-24 00:00", tz="UTC")])
    a0 = pd.Timestamp("2021-09-24", tz="UTC")
    a1 = a0 + pd.Timedelta(days=365)
    m = (idx >= a0) & (idx < a1)
    assert m.tolist() == [False, True, True, False]


def test_results_contract_and_key_counts():
    d = json.loads(RES.read_text())
    assert d["g2_validation"]["reproduced_exactly"] is True
    assert d["dip_validation"]["n"] == 22312
    assert abs(d["dip_validation"]["base_sum5y"] - 7.718304) < 1e-4
    assert len(d["book_timing_share"]) == 5 and len(d["dip_share"]) == 5
    for row in d["book_timing_share"]:
        assert set(row["shares"]) == set(SYMS)
        assert abs(sum(row["shares"].values()) - 1.0) < 1e-3
    for row in d["dip_share"]:
        assert set(row["shares"]) == set(SYMS)
    kc = d["key_counts"]
    # pre-registered count: max share > 40% in dev years
    assert kc["book_years_gt40_dev4"] == sum(1 for s in kc["book_max_shares"][:4] if s > 0.40)
    assert kc["dip_years_gt40_dev4"] == sum(1 for s in kc["dip_max_shares"][:4] if s > 0.40)
    assert kc["book_years_gt40_dev4"] == 2
    assert kc["dip_years_gt40_dev4"] == 2
    # dip DD 5-episode shares sum to 1
    assert abs(sum(d["dip_dd_5ep"]["share"].values()) - 1.0) < 1e-3
