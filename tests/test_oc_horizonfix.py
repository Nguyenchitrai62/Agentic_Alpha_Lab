"""oc_horizonfix tests: synthetic inflation proof + hand-checked + truncation/causality.

Light: synthetic data only, no disk reads.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_horizonfix.py -q
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

BARH = pd.Timedelta(hours=4)


def make_opens(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.01, size=n)
    o = 100.0 * np.cumprod(1 + r)
    idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    return pd.Series(o, index=idx)


def sigma_of(opens):
    r1 = opens / opens.shift(1) - 1.0
    return r1.rolling(360, min_periods=120).std(ddof=1)


def y_at(opens, sig, base_times, h):
    oT = opens.reindex(base_times).to_numpy()
    oH = opens.reindex(base_times + h * BARH).to_numpy()
    sg = sig.reindex(base_times).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        y = (oH / oT - 1.0) / sg
    bad = (~np.isfinite(sg)) | (sg <= 0) | (~np.isfinite(oT)) | (~np.isfinite(oH))
    y[bad] = np.nan
    return y


def spear(x, y):
    m = np.isfinite(np.asarray(x, float)) & np.isfinite(np.asarray(y, float))
    assert int(m.sum()) >= 3
    return float(spearmanr(np.asarray(x, float)[m], np.asarray(y, float)[m]).statistic)


def test_old_yardstick_inflates_and_new_does_not():
    """Feature = current bar's own move (close[T]/open[T]-1, known at close[T]).

    With exact 4h sampling close[T] == open[T+1], this feature EQUALS the old
    h=1 numerator open[T+1]/open[T]-1 (the leak: bar T's own move is already
    known to features that include close[T]). Old IC must be ~+1; corrected
    IC (forward base T+4h) must be ~0. Index note: an open-to-open feature
    open[T]/open[T-1]-1 would NOT inflate (it is last bar's move); the leak
    is specifically via close[T] ~= open[T+1].
    """
    opens = make_opens()
    sig = sigma_of(opens)
    T = opens.index[:-2]
    oT = opens.reindex(T).to_numpy()
    oT1 = opens.reindex(T + BARH).to_numpy()
    f = oT1 / oT - 1.0  # current bar's return, known at close[T]
    y_old = y_at(opens, sig, T, 1)
    y_new = y_at(opens, sig, T + BARH, 1)
    y_new = pd.Series(y_new, index=T).to_numpy()
    assert spear(f, y_old) > 0.5  # pre-registered: strongly positive (~1.0)
    assert abs(spear(f, y_new)) < 0.1  # pre-registered: leak gone


def test_corrected_yardstick_detects_real_forward_skill():
    """Genuinely predictive feature (next bar's move) scores ~+1 corrected."""
    opens = make_opens()
    sig = sigma_of(opens)
    T = opens.index[:-2]
    tT = T + BARH
    oTT = opens.reindex(tT).to_numpy()
    oTT1 = opens.reindex(tT + BARH).to_numpy()
    g = oTT1 / oTT - 1.0  # next-bar move at availability: real 1-bar skill
    y_new = y_at(opens, sig, tT, 1)
    assert spear(g, y_new) > 0.5  # not a null machine


def test_handchecked_tiny_series():
    """Hand-computed old vs corrected on 6 opens (no sigma normalisation)."""
    idx = pd.date_range("2021-01-01", periods=6, freq="4h", tz="UTC")
    o = np.array([100.0, 101.0, 100.0, 102.0, 104.0, 103.0])
    opens = pd.Series(o, index=idx)
    # old h=1 at T=idx[1]: 100/101-1
    assert abs((o[2] / o[1] - 1) - (-0.009900990099009901)) < 1e-12
    # corrected base T+4h=idx[2], h=1: 102/100-1 = +0.02
    assert abs((o[3] / o[2] - 1) - 0.02) < 1e-12
    # old h=2 at idx[1]: o[3]/o[1]-1
    assert abs((o[3] / o[1] - 1) - (102.0 / 101.0 - 1)) < 1e-12
    # corrected h=2 at idx[1] (base idx[2]): o[4]/o[2]-1 = 0.04
    assert abs((o[4] / o[2] - 1) - 0.04) < 1e-12
    # function agrees
    sig = pd.Series(np.ones(6), index=idx)  # unit sigma isolates numerator
    assert abs(y_at(opens, sig, idx[1:2], 1)[0] - (o[2] / o[1] - 1)) < 1e-12
    assert abs(y_at(opens, sig, idx[1:2] + BARH, 1)[0] - 0.02) < 1e-12


def test_truncation_and_causality():
    """Tail bars with no future open are NaN; far-future opens don't leak back."""
    opens = make_opens(n=500)
    sig = sigma_of(opens)
    T = opens.index
    y_old = pd.Series(y_at(opens, sig, T, 42), index=T)
    y_new = pd.Series(y_at(opens, sig, T + BARH, 42), index=T)
    # last bar has no forward open -> NaN under both yardsticks
    assert bool(y_old.iloc[-1] != y_old.iloc[-1])  # NaN
    assert bool(y_new.iloc[-1] != y_new.iloc[-1])
    # edge shift: corrected drops the last valid old row (base+42 out of
    # range) and gains one row at the sigma warm-up boundary; find them
    # programmatically instead of hardcoding rolling-window edges.
    valid_old = np.where(y_old.notna().to_numpy())[0]
    valid_new = np.where(y_new.notna().to_numpy())[0]
    assert len(valid_old) > 0 and len(valid_new) > 0
    assert valid_new[0] == valid_old[0] - 1  # warm-up edge gained
    assert valid_new[-1] == valid_old[-1] - 1  # tail edge dropped
    # causality: perturbing opens AFTER t_trade+h leaves row T unchanged
    t0 = T[200]
    base = y_at(opens, sig, pd.DatetimeIndex([t0]), 6)
    opens2 = opens.copy()
    opens2.iloc[400] *= 1.5  # far future, beyond any window of row 200
    sig2 = sigma_of(opens2)
    base2 = y_at(opens2, sig2, pd.DatetimeIndex([t0]), 6)
    assert abs(float(base[0]) - float(base2[0])) < 1e-12
    # sigma warm-up: first bars NaN (min_periods=120)
    assert bool(sig.iloc[0] != sig.iloc[0])
    assert bool(np.isfinite(sig.iloc[-1]))
