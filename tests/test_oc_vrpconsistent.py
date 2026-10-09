"""oc_vrpconsistent tests: causality + hand-checked synthetic cases."""
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "research/tournament/oc_vrpconsistent"))
import vrp as V
import run_consistent as RC


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def test_bs_matches_hand_calc_and_parity():
    S, K, T, s = 100.0, 100.0, 0.25, 0.60
    sqt = s * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * s * s * T) / sqt
    d2 = d1 - sqt
    assert abs(V.bs_call(S, K, T, s) - (S * ncdf(d1) - K * ncdf(d2))) < 1e-9
    assert abs(V.bs_put(S, K, T, s) - (K * ncdf(-d2) - S * ncdf(-d1))) < 1e-9
    assert abs((V.bs_call(S, K, T, s) - V.bs_put(S, K, T, s)) - (S - K)) < 1e-9
    assert V.bs_call(110.0, 100.0, 0.0, s) == 10.0
    assert V.bs_put(90.0, 100.0, 0.0, s) == 10.0
    assert V.strike_round(67430.0, 1000.0) == 67000.0
    assert V.size_q(2.0, 50000.0, 0.25) == 0.5 * 0.25 * 2.0 / 50000.0


def test_px_floor_fixes_dust_negative_leg():
    # hand-checked corner from the R080 run: deep-OTM ETH put at tiny T prices
    # dust-negative in raw BS; the runner must floor it (else fee NaNs).
    raw = V.bs_put(2099.44, 1850.0, 0.0007990867579908676, 0.8 * 0.649 * 1.05)
    assert raw < 0.0 and raw > -1e-9, raw
    assert RC._px(raw) == 0.0
    assert np.isfinite(V.fee_per_side(2099.44, RC._px(raw)))
    # positive legs untouched
    assert RC._px(12.5) == 12.5


def test_r_scaling_is_consistent_and_monotone():
    # sale 0.97r / TP 1.0r / SL 1.05r must stay ordered and shrink with r
    S, K, T, dv = 60000.0, 60000.0, (7 * 24 * 60 - 5) / (365 * 24 * 60), 60.0
    for r in (1.00, 0.87, 0.80):
        sell = V.bs_straddle(S, K, T, 0.97 * r * dv / 100.0)
        mark = V.bs_straddle(S, K, T, 1.00 * r * dv / 100.0)
        sl = V.bs_straddle(S, K, T, 1.05 * r * dv / 100.0)
        assert sell < mark < sl, (r, sell, mark, sl)
    prems = [V.bs_straddle(S, K, T, 0.97 * r * dv / 100.0) for r in (1.00, 0.87, 0.80)]
    assert prems[0] > prems[1] > prems[2]
    # R100 identity: r=1.0 sigmas equal the original V2 sigmas exactly
    assert 0.97 * 1.0 * dv / 100.0 == 0.97 * dv / 100.0
    assert 1.05 * 1.0 * dv / 100.0 == 1.05 * dv / 100.0


def test_truncation_causality_dvol_known_and_px_at():
    """dvol_known uses the candle close <= t; px_at never peeks forward."""
    ms = np.array([0, 3600_000, 7200_000], dtype=np.int64) * 1_000_000
    cl = np.array([50.0, 51.0, 52.0])
    assert not np.isfinite(RC.dvol_known(ms, cl, 3600_000_000_000 - 1))
    assert RC.dvol_known(ms, cl, 3600_000_000_000) == 50.0
    assert RC.dvol_known(ms, cl, 2 * 3600_000_000_000 - 1) == 50.0
    assert RC.dvol_known(ms, cl, 2 * 3600_000_000_000) == 51.0
    ts = np.array([0, 60_000_000_000, 120_000_000_000], dtype=np.int64)
    px = np.array([100.0, 101.0, 102.0])
    assert RC.px_at(ts, px, 60_000_000_000) == (101.0, True)
    assert RC.px_at(ts, px, 90_000_000_000)[0] == 101.0
    assert RC.px_at(ts, px, 60_000_000_000 - 1)[0] == 100.0


def test_r100_reproduces_v2_dev4_overlay():
    res = json.loads((HERE.parent / "research/tournament/oc_vrpconsistent/results.json").read_text())
    assert res["dev"]["overlay"]["R100_f0.25"]["dev4_mean"] == 6.566
    assert res["dev"]["overlay"]["R100_f0.25"]["dev4_worst"] == 4.365
    assert res["dev"]["overlay"]["R100_f0.25"]["dev4_DD"] == 16.10
    assert res["meta"]["G2_dev4_mean"] == 5.601
    # gap method reproduces C4 for r=1.0
    c4 = json.loads((HERE.parent / "research/tournament/oc_vrprobust/tmp/C4.json").read_text())
    g100 = res["gap"]["R100"]
    assert g100["worst_minute"] == c4["worst_minute"]
    for k in ("g_-10%", "g_-15%", "g_+10%", "g_+15%"):
        assert g100[k] == c4[k], (k, g100[k], c4[k])
    # verdict arithmetic: R087 beats G2 mean+worst within DD bar, R080 fails 0.3pp
    r087 = res["dev"]["overlay"]["R087_f0.25"]
    r080 = res["dev"]["overlay"]["R080_f0.25"]
    assert round(r087["dev4_mean"] - 5.601, 3) == 0.139
    assert r087["dev4_DD"] <= 16.91 + 0.5
    assert round(5.601 - r080["dev4_mean"], 3) > 0.3
