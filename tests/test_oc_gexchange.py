"""oc_gexchange tests: causality/truncation + hand-checked synthetic cases."""
import math

import numpy as np
import pandas as pd

from research.tournament.oc_gex.gex_lib import last_hour_before
from research.tournament.oc_gexchange.gexchange_lib import (
    assign_bucket,
    build_changes,
    idx_24h_before,
    raw_d,
    trailing_sigma,
    z_of_d,
    z_series,
)


def test_z_hand_total_and_bucket_edges():
    # d = -8 - (-2) = -6; sigma = 3 -> z = -2 -> LOW bucket.
    assert raw_d(-8.0, -2.0) == -6.0
    assert z_of_d(-6.0, 3.0) == -2.0
    assert assign_bucket(-2.0) == 0
    assert assign_bucket(0.5) == 1
    assert assign_bucket(1.5) == 2
    # edges: -1 and +1 belong to MID (fixed: LOW is z < -1 strictly).
    assert assign_bucket(-1.0) == 1
    assert assign_bucket(1.0) == 1
    assert assign_bucket(float("nan")) == -1
    # bad sigma -> NaN (no div-by-zero).
    assert math.isnan(z_of_d(1.0, 0.0))
    assert math.isnan(z_of_d(1.0, float("nan")))
    assert math.isnan(raw_d(float("nan"), 1.0))


def test_trailing_sigma_hand_value_and_excludes_current():
    # constant changes -> std 0; varying changes hand-check vs numpy.
    c = np.array([1.0, 2.0, 3.0, 4.0, 100.0])
    sig = trailing_sigma(c, win=4, minp=2)
    # sigma[4] uses c[0:4] only (excludes current c[4]=100).
    expect = float(np.std([1.0, 2.0, 3.0, 4.0], ddof=1))
    assert abs(sig[4] - expect) < 1e-12
    # sigma[0] has no predecessors -> NaN; sigma[1] has 1 value < minp=2 -> NaN.
    assert math.isnan(sig[0])
    assert math.isnan(sig[1])
    # changing the current value must not change its own sigma.
    c2 = c.copy()
    c2[4] = -999.0
    sig2 = trailing_sigma(c2, win=4, minp=2)
    assert sig2[4] == sig[4]


def test_causality_idx_and_join_margin():
    he = (pd.date_range("2021-04-01", periods=50, freq="h", tz="UTC")).values.astype(
        "datetime64[ns]").astype(np.int64)
    # regular grid: j(h) = h - 24.
    assert idx_24h_before(he, 30) == 6
    assert idx_24h_before(he, 24) == 0
    assert idx_24h_before(he, 10) == -1  # no 24 h-earlier hour yet
    # join margin: bar open exactly on an hour end uses the previous hour.
    bt = int(pd.Timestamp("2021-04-02 03:00", tz="UTC").value)
    assert last_hour_before(he, bt) == int(
        np.searchsorted(he, bt - 60_000_000_000, side="right") - 1)
    # a fill in the first 5 min after close still maps to an hour before the bar.
    assert last_hour_before(he, bt + 4 * 60_000_000_000) <= int(
        np.searchsorted(he, bt, side="right") - 1) + 1


def test_truncation_build_changes_needs_both_ends():
    he = (pd.date_range("2021-04-01", periods=30, freq="h", tz="UTC")).values.astype(
        "datetime64[ns]").astype(np.int64)
    g = np.arange(30, dtype=float)
    g[5] = np.nan  # missing level poisons c[5] and c[29]? c[29]=g[29]-g[5] -> NaN.
    c = build_changes(g, he)
    assert math.isnan(c[5])
    assert math.isnan(c[29])
    assert c[28] == g[28] - g[4]
    # z_series threads d/sigma consistently on a noisy ramp
    # (a perfect ramp has constant d -> sigma 0 -> z NaN by design).
    n2 = 2500  # sigma needs >=720 valid predecessors (pre-registered minimum)
    gg = np.linspace(0.0, 10.0, n2) + 0.5 * np.sin(np.arange(n2))
    he2 = (pd.date_range("2021-04-01", periods=n2, freq="h", tz="UTC")).values.astype(
        "datetime64[ns]").astype(np.int64)
    d, sig, z = z_series(gg, he2)
    assert np.all(np.isfinite(d[24:100]))
    assert abs(d[50] - (gg[50] - gg[26])) < 1e-12
    assert math.isnan(z[100])  # only ~76 predecessors < 720 minimum
    assert np.isfinite(z[2000])
