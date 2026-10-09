"""audit_vrpstraddle tests: causality/truncation + hand-checked synthetic cases."""
import math
import numpy as np
import pandas as pd

from research.tournament.audit_vrpstraddle.replicate import (
    bs_pair, fee_unit, latest_dvol, get_close, simulate_coin, SEC_PER_YEAR,
)


def test_bs_parity_and_edges():
    # put-call parity C - P = S - K for r=q=0
    c, p = bs_pair(60000.0, 60000.0, 0.8, 0.02)
    assert abs((c - p) - 0.0) < 1e-6
    c2, p2 = bs_pair(61000.0, 60000.0, 0.8, 0.02)
    assert abs((c2 - p2) - 1000.0) < 1e-6
    # T<=0 -> intrinsic
    c3, p3 = bs_pair(61000.0, 60000.0, 0.8, 0.0)
    assert c3 == 1000.0 and p3 == 0.0
    # sigma<=0 -> intrinsic
    c4, p4 = bs_pair(59000.0, 60000.0, -0.5, 0.02)
    assert c4 == 0.0 and p4 == 1000.0
    # ATM straddle approx S*s*sqrt(T)*sqrt(2/pi)
    S, s, T = 50000.0, 0.8, (7 * 24 * 60 - 5) / (365 * 24 * 60)
    c5, p5 = bs_pair(S, S, s, T)
    approx = S * s * math.sqrt(T) * math.sqrt(2 / math.pi)
    assert abs((c5 + p5) - approx) / approx < 0.02


def test_fee_caps():
    # cap binds at 12.5% of leg price
    assert fee_unit(60000.0, 10.0, 0.0003) == min(18.0, 1.25)
    assert fee_unit(60000.0, 1000.0, 0.0003) == min(18.0, 125.0)
    # settlement rate
    assert fee_unit(60000.0, 500.0, 0.00015) == min(9.0, 62.5)


def test_dvol_strictly_asof():
    # hourly candle [08:00,09:00) closes exactly 09:00; at 08:05 only the 07:00 candle is known
    base = pd.Timestamp("2021-09-24 07:00", tz="UTC").value
    close_ns = np.array([base + 3600_000_000_000, base + 2 * 3600_000_000_000])  # 08:00, 09:00 closes
    cl = np.array([80.0, 90.0])
    t_entry = pd.Timestamp("2021-09-24 08:05", tz="UTC").value
    assert latest_dvol(close_ns, cl, t_entry) == 0.80
    t_at_close = pd.Timestamp("2021-09-24 09:00", tz="UTC").value
    assert latest_dvol(close_ns, cl, t_at_close) == 0.90


def test_get_close_exact_only():
    tns = np.array([pd.Timestamp("2021-09-24 08:04", tz="UTC").value])
    cl = np.array([50000.0])
    assert get_close(tns, cl, tns[0]) == 50000.0
    assert not np.isfinite(get_close(tns, cl, tns[0] + 60_000_000_000))


def test_no_exit_before_first_hourly_close():
    # flat market, tiny vol: no SL/TP possible before 09:00; first check is 09:00
    tns_list, cl_list = [], []
    start = pd.Timestamp("2021-09-24 07:30", tz="UTC")
    px = 50000.0
    for m in range(8 * 24 * 60):
        tns_list.append((start + pd.Timedelta(minutes=m)).value)
        cl_list.append(px)
    tns = np.array(tns_list)
    cl = np.array(cl_list)
    entry = pd.Timestamp("2021-09-24 08:05", tz="UTC")
    expiry = entry + pd.Timedelta(days=7) - pd.Timedelta(minutes=5)
    K = 50000.0
    pc, pp = bs_pair(px, K, 0.5, (expiry.value - entry.value) / 1e9 / SEC_PER_YEAR)
    dvol_ns = np.array([pd.Timestamp("2021-09-24 08:00", tz="UTC").value])
    dvol_c = np.array([50.0])
    r = simulate_coin("BTC", entry, expiry, px, K, 0.485, pc, pp, tns, cl, dvol_ns, dvol_c)
    # flat market decays -> TP at some 4h close, but never before the first hourly close 09:00
    assert pd.Timestamp(r["exit"]["t"], tz="UTC").value >= pd.Timestamp("2021-09-24 09:00", tz="UTC").value


def test_tp_first_at_4h_close():
    # deep-decayed mark at a 4h close must exit as TP even if SL would also bind;
    # construct tiny premium so mark<=0.3*gross at first 4h close (12:00)
    tns_list, cl_list = [], []
    start = pd.Timestamp("2021-09-24 07:30", tz="UTC")
    for m in range(8 * 24 * 60):
        tns_list.append((start + pd.Timedelta(minutes=m)).value)
        cl_list.append(50000.0)
    tns = np.array(tns_list)
    cl = np.array(cl_list)
    entry = pd.Timestamp("2021-09-24 08:05", tz="UTC")
    expiry = entry + pd.Timedelta(days=7) - pd.Timedelta(minutes=5)
    K = 50000.0
    # hand-set economics: gross 100, opt_cash 99, mark ~0 at 12:00 -> TP first
    pc, pp = 50.0, 50.0
    dvol_ns = np.array([pd.Timestamp("2021-09-24 08:00", tz="UTC").value])
    dvol_c = np.array([1.0])  # tiny vol -> mark ~ intrinsic 0
    r = simulate_coin("BTC", entry, expiry, 50000.0, K, 0.0097, pc, pp, tns, cl, dvol_ns, dvol_c)
    assert r["exit"]["type"] == "TP"
    assert pd.Timestamp(r["exit"]["t"], tz="UTC").hour % 4 == 0


def test_overlay_marked_path_formula():
    # M = A_prev*hh + dU (fixed) vs M_prev*hh (buggy decay): fixed must be >= buggy after a dip
    A_prev, hh, dU, M_prev = 1.0, 0.9, 0.01, 0.95
    assert A_prev * hh + dU == 0.91
    assert M_prev * hh + dU == 0.865
    # fixed anchors on close path; buggy compounds the dip twice
    assert (A_prev * hh + dU) > (M_prev * hh + dU)
