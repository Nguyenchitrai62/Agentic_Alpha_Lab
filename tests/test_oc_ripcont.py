"""oc_ripcont tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.tournament.oc_ripcont import backtest as B


def _ns(day: str, hm: str, n: int):
    t0 = pd.Timestamp(f"{day} {hm}", tz="UTC")
    return (t0 + pd.to_timedelta(np.arange(n), unit="m")).values.astype("datetime64[ns]").astype(np.int64)


def test_sigma_truncation_and_log():
    rng = np.random.Generator(np.random.PCG64(11))
    opens = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 500)))
    full = B.sigma_from_bar_opens_log(opens)
    trunc = B.sigma_from_bar_opens_log(opens[:300])
    assert np.isfinite(full[299]) and np.isfinite(trunc[299])
    assert full[299] == trunc[299]  # uses only opens <= O[299]
    assert np.all(np.isnan(full[:120]))  # min_periods 120
    # hand check: constant 1% log returns -> std 0
    o = 100 * np.exp(0.01 * np.arange(200))
    s = B.sigma_from_bar_opens_log(o)
    assert abs(s[199]) < 1e-12
    # hand check: alternating +-1% -> std of +-0.01 ~ 0.01005 (ddof=1, 360 window uses last 199 here... use 150 pts)
    o2 = [100.0]
    for i in range(1, 150):
        o2.append(o2[-1] * np.exp(0.01 if i % 2 else -0.01))
    s2 = B.sigma_from_bar_opens_log(np.array(o2))
    assert s2[149] > 0.009 and s2[149] < 0.011


def _one_bar_setup(day="2022-01-01", hm="01:00", O0=100.0, s=0.01, k=2.0):
    n = 241
    idx_ns = _ns(day, hm, n)
    O = np.full(n, np.nan)
    H = np.full(n, np.nan)
    Lw = np.full(n, np.nan)
    C = np.full(n, np.nan)
    O[:] = O0
    C[:] = O0
    H[:] = O0
    Lw[:] = O0 * 1.05  # above any test L -> no accidental pullback fills
    O[240] = O0 + 0.5  # timeout open
    return idx_ns, O, H, Lw, C


def test_trigger_pullback_tp_exact():
    s, k, O0 = 0.01, 2.0, 100.0
    idx_ns, O, H, Lw, C = _one_bar_setup(s=O0)
    trig = O0 * np.exp(k * s)
    L = O0 * np.exp((k - 1.0) * s)
    tp = L * np.exp(0.75 * s)
    sl = L * np.exp(-1.0 * s)
    H[10] = trig + 0.1  # trigger m=10
    Lw[12] = L - 0.01  # fill f=12
    H[15] = tp + 0.5  # TP
    Lw[15] = sl + 0.5  # above SL
    C[15] = tp
    evs = B.simulate_clock(idx_ns, O, H, Lw, C, np.array([0]), np.array(["t"]), np.array([s]), k)
    assert len(evs) == 1
    e = evs[0]
    assert e["fill_idx"] == 12 and e["how"] == "tp"
    assert abs(e["level"] - L) < 1e-9 and abs(e["exit_px"] - tp) < 1e-9
    assert e["n_fund"] == 0  # 01:xx, no settlement crossed
    assert abs(e["net"] - ((tp - L) / L - 0.0002 - 0.0002)) < 1e-12


def test_stop_first_same_minute():
    s, k, O0 = 0.01, 2.0, 100.0
    idx_ns, O, H, Lw, C = _one_bar_setup()
    trig = O0 * np.exp(k * s)
    L = O0 * np.exp((k - 1.0) * s)
    tp = L * np.exp(0.75 * s)
    sl = L * np.exp(-1.0 * s)
    H[10] = trig + 0.1
    Lw[12] = L - 0.01
    H[15] = tp + 1.0  # both touched
    Lw[15] = sl - 0.5
    evs = B.simulate_clock(idx_ns, O, H, Lw, C, np.array([0]), np.array(["t"]), np.array([s]), k)
    assert len(evs) == 1 and evs[0]["how"] == "stop"
    assert abs(evs[0]["exit_px"] - sl) < 1e-9


def test_timeout_with_funding():
    # bar 07:00 -> 11:00 crosses the 08:00 settlement
    s, k, O0 = 0.01, 2.0, 100.0
    idx_ns, O, H, Lw, C = _one_bar_setup(day="2022-01-01", hm="07:00")
    trig = O0 * np.exp(k * s)
    L = O0 * np.exp((k - 1.0) * s)
    H[10] = trig + 0.1
    Lw[12] = L - 0.01
    # never touch TP/SL: keep band tight around L
    tp = L * np.exp(0.75 * s)
    sl = L * np.exp(-1.0 * s)
    H[13:240] = (L + tp) / 2
    Lw[13:240] = (L + sl) / 2
    C[13:240] = L
    evs = B.simulate_clock(idx_ns, O, H, Lw, C, np.array([0]), np.array(["t"]), np.array([s]), k)
    assert len(evs) == 1 and evs[0]["how"] == "time"
    assert evs[0]["exit_idx"] == 240
    assert evs[0]["n_fund"] == 1  # 08:00 crossed between 07:12 and 11:00
    assert abs(evs[0]["net"] - ((O[240] - L) / L - 0.0002 - 0.00055 - 0.0001)) < 1e-12


def test_no_fill_first5min_or_no_pullback():
    s, k, O0 = 0.01, 2.0, 100.0
    # rip only at offset 3 -> ignored (window starts at 5)
    idx_ns, O, H, Lw, C = _one_bar_setup()
    trig = O0 * np.exp(k * s)
    H[3] = trig + 1.0
    evs = B.simulate_clock(idx_ns, O, H, Lw, C, np.array([0]), np.array(["t"]), np.array([s]), k)
    assert evs == []
    # trigger but never pulls back to L -> no fill
    idx_ns, O, H, Lw, C = _one_bar_setup()
    H[10] = trig + 0.1
    Lw[11:200] = O0 * np.exp((k - 1.0) * s) + 0.5  # always above L
    H[11:200] = trig + 0.5
    evs = B.simulate_clock(idx_ns, O, H, Lw, C, np.array([0]), np.array(["t"]), np.array([s]), k)
    assert evs == []
