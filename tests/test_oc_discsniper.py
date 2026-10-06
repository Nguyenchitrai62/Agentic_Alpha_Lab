"""oc_discsniper causality + hand checks (light, synthetic only)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("research/tournament/oc_discsniper")))
import numpy as np
import pandas as pd

import discsniper as D


def test_p15_hand():
    x = np.array([1.0] * 14 + [2.0] + [0.0] * 5)
    p = D.p15_from_close(x)
    assert np.isnan(p[13])
    assert abs(p[14] - (14 * 1.0 + 2.0) / 15) < 1e-12
    y = np.array([1.0] * 15)
    y[3] = np.nan
    assert np.isnan(D.p15_from_close(y)[14])


def test_z_causal_and_math():
    rng = np.random.RandomState(0)
    p15 = np.concatenate([rng.normal(0, 1, 2000), [-10.0], rng.normal(0, 1, 10)])
    # bar minute i = 2000 -> cur = p15[1999], trailing = p15[i-1441:i-1]
    i = 2000
    z = D.z_from_p15(p15, i)
    tr = p15[i - 1441:i - 1]
    exp = (p15[i - 1] - tr.mean()) / tr.std(ddof=1)
    assert abs(z - exp) < 1e-9
    # changing minutes >= i must not change z
    p15b = p15.copy()
    p15b[i] = 999.0
    p15b[i + 5] = 999.0
    assert D.z_from_p15(p15b, i) == z
    # short history -> NaN
    assert np.isnan(D.z_from_p15(np.ones(100), 50))


def test_z_rolling_equiv():
    rng = np.random.RandomState(1)
    p15 = rng.normal(0, 1, 3000)
    s = pd.Series(p15)
    rm = s.rolling(1440, min_periods=1200).mean().to_numpy()
    rs = s.rolling(1440, min_periods=1200).std(ddof=1).to_numpy()
    for i in (1500, 2000, 2999):
        z1 = D.z_from_p15(p15, i)
        cur, mu, sd = p15[i - 1], rm[i - 2], rs[i - 2]
        z2 = (cur - mu) / sd
        assert abs(z1 - z2) < 1e-9


def test_fill_strict_and_window():
    lim = 100.0
    low = np.full(55, 101.0)
    assert D.find_fill_disc(low, lim) is None
    low2 = np.full(55, 101.0)
    low2[0] = 99.9  # offset 5
    assert D.find_fill_disc(low2, lim) == 0
    low3 = np.full(55, 101.0)
    low3[3] = 100.0  # equal -> STRICT, no fill
    assert D.find_fill_disc(low3, lim) is None
    low4 = np.array([np.nan] * 55)
    assert D.find_fill_disc(low4, lim) is None


def _flat_arrays(px_fill=100.0, sg=0.01):
    n = 240
    Hb = np.full(n, 101.0)
    Lb = np.full(n, 100.5)
    Cb = np.full(n, 100.8)
    Ob = np.full(n, 100.8)
    p15b = np.full(n, -0.01)
    return Hb, Lb, Cb, Ob, p15b


def test_stop_premium_priority_and_causality():
    H, L, C, O, P = _flat_arrays()
    settle = np.zeros(100000, bool)
    # premium trigger at m=10, stop never -> premium exit at 11
    P[10] = 0.01
    ret, x, how = D.outcome_disc(H, L, C, O, P, 5, 100.0, 0.01, 101.0, 1000, 995, settle)
    assert how == "premium" and x == 11
    # stop at m=10 too (close <= sl on a (m+1)%5==0 minute: m=9? (9+1)%5==0)
    C2 = C.copy()
    C2[9] = 90.0  # sl = 96 -> triggers at m=9
    P2 = P.copy()
    P2[9] = 0.01  # same minute tie -> stop wins
    ret, x, how = D.outcome_disc(H, L, C2, O, P2, 5, 100.0, 0.01, 101.0, 1000, 995, settle)
    assert how == "stop"
    # premium at m=8 beats later stop at m=9
    P3 = np.full(240, -0.01)
    P3[8] = 0.01
    ret, x, how = D.outcome_disc(H, L, C2, O, P3, 5, 100.0, 0.01, 101.0, 1000, 995, settle)
    assert how == "premium" and x == 9
    # NaN exit open -> NaN dropped
    O4 = O.copy()
    O4[11] = np.nan
    ret, x, how = D.outcome_disc(H, L, C, O4, P, 5, 100.0, 0.01, 101.0, 1000, 995, settle)
    assert np.isnan(ret)


def test_funding_count():
    m = np.zeros(100, bool)
    m[50] = True
    assert D.funding_count(40, 60, m) == 1
    assert D.funding_count(50, 60, m) == 0  # strictly after fill
    assert D.funding_count(40, 50, m) == 1  # <= exit inclusive


def test_dip_n_hand():
    cmat = np.array([[90.0, 100.0], [90.0, 100.0], [100.0, 100.0], [100.0, 100.0]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = D.dip_n_vector(cmat, oo, ss)
    assert list(n) == [2, 0]
