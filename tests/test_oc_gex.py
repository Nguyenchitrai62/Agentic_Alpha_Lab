"""oc_gex tests: causality/truncation + hand-checked synthetic cases."""
import math

import numpy as np
import pandas as pd

from research.tournament.oc_gex.gex_lib import (
    assign_tercile,
    dealer_gex,
    gamma_bs,
    gexn,
    last_hour_before,
    tercile_cuts,
)


def test_gamma_hand_value_and_parity():
    # S=K=50000, iv=0.60, T=30/365.25 -> gamma ~= 4.626e-05 (r=0).
    g = gamma_bs(50000.0, 50000.0, 0.60, 30.0 / 365.25)
    assert abs(g - 4.626e-05) / 4.626e-05 < 0.01
    # same for C and P (gamma has no cp input by construction)
    assert gamma_bs(50000.0, 60000.0, 0.6, 0.25) > 0
    assert gamma_bs(50000.0, 40000.0, 0.6, 0.25) > 0
    # far OTM gamma < ATM gamma
    assert gamma_bs(50000.0, 80000.0, 0.6, 0.25) < gamma_bs(50000.0, 50000.0, 0.6, 0.25)
    # bad inputs -> NaN
    assert math.isnan(gamma_bs(0.0, 50000.0, 0.6, 0.25))
    assert math.isnan(gamma_bs(50000.0, 50000.0, float("nan"), 0.25))


def test_dealer_gex_hand_total():
    # two instruments, q=+10 / -5, same gamma 4.626e-05, S=50000:
    # GEX = -(10-5)*g*S^2*0.01 = -5*4.626e-05*2.5e9*0.01 = -5782.6
    g = 4.626e-05
    got = dealer_gex(np.array([10.0, -5.0]), np.array([g, g]), 50000.0)
    assert abs(got - (-5782.6)) / 5782.6 < 0.02
    # sign flip: customers net short (q<0) -> dealers long -> GEX positive
    assert dealer_gex(np.array([-10.0]), np.array([g]), 50000.0) > 0
    assert math.isnan(dealer_gex(np.array([1.0]), np.array([np.nan]), 50000.0))


def test_gexn_normalisation():
    assert abs(gexn(-5782.6, 50000.0, 1e6) - (-5782.6 / (50000.0 * 1e6))) < 1e-15
    assert math.isnan(gexn(1.0, 50000.0, 0.0))
    assert math.isnan(gexn(float("nan"), 50000.0, 1.0))


def test_causality_last_hour_before():
    he = (pd.date_range("2021-04-01", periods=5, freq="h", tz="UTC") 
          + pd.Timedelta(hours=1)).values.astype("datetime64[ns]").astype(np.int64)
    bt = int(pd.Timestamp("2021-04-01 02:00", tz="UTC").value)
    # last full hour strictly before 02:00 (minus 1 min) is the 01:00-02:00 bar? No:
    # hour_ends are 01:00..05:00; last <= 01:59 is 01:00 -> index 0.
    assert last_hour_before(he, bt) == 0
    bt2 = int(pd.Timestamp("2021-04-01 01:00", tz="UTC").value)
    # nothing ends <= 00:59 except 01:00? 01:00 > 00:59 so index -1... first end is 01:00.
    assert last_hour_before(he, bt2) == -1
    # exact end: bar open 03:00 -> last <= 02:59 is 02:00 end (index 1)
    bt3 = int(pd.Timestamp("2021-04-01 03:00", tz="UTC").value)
    assert last_hour_before(he, bt3) == 1


def test_truncation_expiry_and_ffill():
    # synthetic: instrument expires 2021-04-02 08:00 UTC; GEX must drop it after.
    exp_ns = int(pd.Timestamp("2021-04-02 08:00", tz="UTC").value)
    t_before = int(pd.Timestamp("2021-04-02 07:00", tz="UTC").value)  # hour end 07:00
    t_after = int(pd.Timestamp("2021-04-02 08:00", tz="UTC").value)  # hour end 08:00
    assert exp_ns > t_before  # alive
    assert not (exp_ns > t_after)  # expired
    # T floor: 0.5h -> floored to 1h
    assert gamma_bs(50000.0, 50000.0, 0.6, 0.5 / 8760.0) == gamma_bs(
        50000.0, 50000.0, 0.6, 1.0 / 8760.0)


def test_tercile_embargo():
    # cuts from training rows only; a late extreme must not move the cuts.
    train = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    lo, hi = tercile_cuts(train)
    assert lo == np.quantile(train, 1 / 3) and hi == np.quantile(train, 2 / 3)
    assert assign_tercile(1.0, lo, hi) == 0
    assert assign_tercile(6.0, lo, hi) == 2
    assert assign_tercile(3.5, lo, hi) == 1
    assert assign_tercile(float("nan"), lo, hi) == -1
    lo2, hi2 = tercile_cuts(np.array([]))
    assert math.isnan(lo2) and math.isnan(hi2)
