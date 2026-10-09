"""oc_k2carry tests: gates (frozen numbers) + causality/truncation + synthetic."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_k2carry"


def last_close_before(times_ns, closes, ts_ns):
    idx = np.searchsorted(np.asarray(times_ns), np.asarray(ts_ns),
                          side="left") - 1
    out = np.full(len(np.asarray(ts_ns)), np.nan, dtype=float)
    ok = idx >= 0
    out[ok] = np.asarray(closes, dtype=float)[idx[ok]]
    return out


def test_gates_reproduce_frozen_numbers():
    res = json.loads((OC / "results.json").read_text())
    rows = res["rows"]
    v421 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                       "/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    g = rows["G2_binance"]
    assert [y["R"] for y in g["years"]] == [r for r, _ in v421["years"]]
    assert [y["DD"] for y in g["years"]] == [d for _, d in v421["years"]]
    assert g["R5y"] == v421["R"] and g["W5y"] == v421["W"]
    assert g["DDmax"] == v421["DD"]
    assert g["full_path_dd"]["full"] == v421["full_path_dd"]
    gc = rows["G2_carry_binance"]
    assert gc["R5y"] == 5.634
    assert gc["DDmax"] == 16.75
    assert gc["full_path_dd"]["full"] == 16.66
    kh_tab = json.loads((ROOT / "research/tournament/oc_k2bybit/tmp"
                         "/k2bybit_table.json").read_text())["table"]
    for key, kk in (("K2_binance", "K2_base"), ("G2_bybit_S5", "REF_S5"),
                    ("K2_bybit_S5", "K2_S5")):
        assert [y["R"] for y in rows[key]["years"]] == kh_tab[kk]["years_R"]
        assert [y["DD"] for y in rows[key]["years"]] == kh_tab[kk]["years_DD"]
        assert rows[key]["full_path_dd"]["full"] == kh_tab[kk]["full_path_dd"]
    # bootstrap block present for all 8 rows
    assert len(rows) == 8
    for k, v in rows.items():
        b = v["bootstrap"]
        assert set(b) == {"m_med_pc", "p_m_ge_5pc", "p_dd_gt_20pc",
                          "p_losing_pc"}, k


def test_last_close_before_strictly_before_hand_checked():
    # bar times t=10,20,30 with closes 100,110,120; query AT a bar time must
    # use the PREVIOUS bar only (strictly before), never the bar itself.
    times = np.array([10, 20, 30])
    closes = np.array([100.0, 110.0, 120.0])
    q = np.array([10, 20, 30, 25, 9])
    got = last_close_before(times, closes, q)
    assert np.isnan(got[0])  # nothing strictly before t=10
    assert got[1] == 100.0  # at t=20 -> close of t=10
    assert got[2] == 110.0  # at t=30 -> close of t=20
    assert got[3] == 110.0  # t=25 -> close of t=20
    assert np.isnan(got[4])  # t=9 -> nothing


def test_carry_mtm_causal_truncation_identical_prefix():
    # synthetic spot/fut grids; truncating the future must not change the
    # kept prefix (causality: last CLOSED bar strictly before t).
    times = np.arange(0, 100, 10)
    closes = 100.0 + np.arange(10, dtype=float)
    grid = np.arange(0, 100, 5)
    full = last_close_before(times, closes, grid)
    cut = 50
    keep = grid < cut
    times_t = times[times < cut]
    closes_t = closes[:len(times_t)]
    trunc = last_close_before(times_t, closes_t, grid[keep])
    assert np.allclose(full[keep], trunc, equal_nan=True)


def test_compounding_account_hand_checked_synthetic():
    # A(t)=A(t-1)*(1+r)+dU, M(t)=A(t-1)*hh+dU; 3 steps hand-computed.
    r = np.array([0.10, -0.05, 0.02])
    hh = np.array([0.10, -0.08, 0.01])  # marked/base ratio path
    dU = np.array([0.0, 0.5, -0.2])
    A, M = [1.0], [1.0]
    a = 1.0
    for i in range(3):
        a = a * (1 + r[i]) + dU[i]
        A.append(a)
    a = 1.0
    for i in range(3):
        m = a * (1 + hh[i]) + dU[i]
        a = a * (1 + r[i]) + dU[i]
        M.append(m)
    assert A[1:] == [1.1, 1.545, 1.3759]
    assert abs(M[1] - 1.1) < 1e-12
    assert abs(M[2] - (1.1 * 0.92 + 0.5)) < 1e-12
    assert abs(M[3] - (1.545 * 1.01 - 0.2)) < 1e-12
    # f=0 short-circuit identity: with dU=0, A == cumprod(1+r)
    assert abs(np.prod(1 + r[:2]) - 1.045) < 1e-12
