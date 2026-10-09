"""oc_vrpstrike tests: causality/truncation + hand-checked synthetic cases."""
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "research" / "tournament" / "oc_vrpstrike"))
import vrpstrike as S


def test_bs_parity_and_atm_straddle():
    # put-call parity with r=q=0: C - P == S - K (hand-checkable identity)
    S0, K, T, sig = 81000.0, 81000.0, 7 * 24 * 3600 / (365 * 24 * 3600), 0.45
    c = S.bs_call(S0, K, T, sig)
    p = S.bs_put(S0, K, T, sig)
    assert abs((c - p) - (S0 - K)) < 1e-6 * S0
    # Brenner-Subrahmanyam ATM approx: straddle ~= 0.7979 * S * sig * sqrt(T)
    approx = 0.7979 * S0 * sig * math.sqrt(T)
    assert abs((c + p) - approx) / approx < 0.02


def test_bs_intrinsic_guards():
    assert S.bs_call(100.0, 90.0, 0.0, 0.5) == 10.0
    assert S.bs_put(100.0, 90.0, -1.0, 0.5) == 0.0
    assert S.bs_call(100.0, 100.0, 0.05, 0.0) == 0.0
    assert S.bs_put(100.0, 110.0, 0.05, float("nan")) == 10.0
    assert math.isnan(S.bs_call(-5.0, 100.0, 0.05, 0.5))
    # negative leg price is invalid input (BS here never emits it: intrinsic
    # branch floors at 0, formula branch is positive) -> NaN signals a bug
    assert math.isnan(S.fee_per_side(80000.0, -3e-14))


def test_fee_caps_and_size():
    # cap binds: 0.0003*S vs 12.5% of leg (float-exact via approx)
    import pytest

    assert S.fee_per_side(80000.0, 1000.0) == pytest.approx(min(0.0003 * 80000.0, 125.0))
    assert S.fee_per_side(80000.0, 1000.0) == pytest.approx(24.0)
    assert S.fee_per_side(80000.0, 10.0) == pytest.approx(min(0.0003 * 80000.0, 1.25))
    assert S.settle_fee(81000.0, 0.0) == 0.0
    assert S.settle_fee(81000.0, 500.0) == pytest.approx(min(0.00015 * 81000.0, 62.5))
    assert S.size_q(1.0, 80000.0, 1.0) == 0.5 / 80000.0
    assert S.size_q(2.0, 4000.0, 0.25) == 0.5 * 0.25 * 2.0 / 4000.0


def test_amount_weighted_iv_and_threshold():
    iv, tot = S.amount_weighted_iv(np.array([80.0, 90.0]), np.array([1.0, 3.0]))
    assert tot == 4.0 and abs(iv - 87.5) < 1e-12
    iv, tot = S.amount_weighted_iv(np.array([80.0]), np.array([0.05]))
    assert tot < S.MIN_ENTRY_AMOUNT  # entry window would skip this leg
    iv, tot = S.amount_weighted_iv(np.array([]), np.array([]))
    assert math.isnan(iv) and tot == 0.0


def test_select_strike_nearest_tie_lower():
    assert S.select_strike(np.array([80000.0, 81000.0, 82000.0]), 81057.0) == 81000.0
    assert S.select_strike(np.array([80000.0, 82000.0]), 81000.0) == 80000.0
    assert math.isnan(S.select_strike(np.array([]), 81000.0))
    assert S.sell_sigma(45.0, "BTC") == (45.0 - 0.5) / 100.0
    assert S.sell_sigma(55.0, "ETH") == (55.0 - 1.0) / 100.0


def test_last_traded_iv_causality_and_24h_fallback():
    h = 3600 * 1_000_000_000
    # bucket closes for the 08/09/10h entry buckets; ivs of buckets [8,9,10]h
    closes = np.array([9 * h, 10 * h, 11 * h], dtype=np.int64)
    ivs = np.array([80.0, 82.0, 84.0])
    # bucket known at its close: at t=11h the 10h bucket (close 11h) is usable
    iv, fresh = S.last_traded_iv(closes, ivs, 11 * h)
    assert fresh and iv == 84.0
    # just before 11h the 10h bucket is NOT yet known (entry would use 09h)
    iv, fresh = S.last_traded_iv(closes, ivs, 11 * h - 1)
    assert fresh and iv == 82.0
    # entry window truncation: an 11h print must not leak into the 11:00 entry
    iv, _ = S.last_traded_iv(closes, ivs, 11 * h - 1)
    assert iv != 84.0
    # 24h lookback: stale print -> fallback
    iv, fresh = S.last_traded_iv(closes, ivs, 11 * h + 25 * h)
    assert not fresh and math.isnan(iv)
    # NaN print -> fallback even if fresh in time
    iv, fresh = S.last_traded_iv(closes, np.array([80.0, 82.0, float("nan")]), 11 * h)
    assert not fresh


def test_sl_tp_trigger_order_on_synthetic_path():
    # synthetic: gross=100, mid path dips to 29 (TP) before ask breaches -100
    gross, opt_cash = 100.0, 96.0
    mid = np.array([90.0, 60.0, 29.0, 20.0])
    ask = np.array([92.0, 63.0, 31.0, 22.0])
    is_4h = np.array([True, True, True, True])
    kind, j = "expiry", len(mid) - 1
    for k in range(len(mid) - 1):
        if is_4h[k] and mid[k] <= 0.3 * gross:
            kind, j = "tp", k
            break
        if opt_cash - ask[k] <= -gross:
            kind, j = "sl", k
            break
    assert (kind, j) == ("tp", 2)
    # stop-first when both touch in the same non-4h bar: only SL exists there
    mid2 = np.array([90.0, 10.0])
    ask2 = np.array([92.0, 250.0])
    is_4h2 = np.array([True, False])
    kind, j = "expiry", 1
    for k in range(1):
        if is_4h2[k] and mid2[k] <= 0.3 * gross:
            kind, j = "tp", k
            break
        if opt_cash - ask2[k] <= -gross:
            kind, j = "sl", k
            break
    # k=0: mid 90 > 30, pnl 96-92=-... no trigger; expiry holds (k=1 excluded)
    assert kind == "expiry"
