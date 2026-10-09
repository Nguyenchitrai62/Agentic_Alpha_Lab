"""audit_mvrv tests: causality/truncation + hand-checked synthetic cases."""
import numpy as np
import pandas as pd

from research.tournament.audit_mvrv.signals_mvrv import (
    apply_gate,
    compute_zm,
    control_multiplier,
    m1_multiplier,
    z_at_T,
)


def test_zm_hand_checked():
    # constant ramp 1..5, window trailing: hand check last value
    idx = pd.date_range("2020-01-01", periods=200, freq="D", tz="UTC").floor("D")
    mvrv = pd.Series(np.arange(1, 201, dtype=float), index=idx)
    z = compute_zm(mvrv, win=365, minp=180)
    assert z.iloc[:179].isna().all()
    w = np.arange(1, 201, dtype=float)[-365:]
    expect = (200.0 - w.mean()) / w.std(ddof=1)
    assert abs(z.iloc[-1] - expect) < 1e-9
    # flat series -> std 0 -> NaN
    flat = pd.Series(np.ones(200), index=idx)
    assert compute_zm(flat).isna().all()


def test_zm_window_end_causal():
    # zM(D) must not use days after D: appending a spike later must not change earlier z
    idx = pd.date_range("2020-01-01", periods=400, freq="D", tz="UTC").floor("D")
    rng = np.random.default_rng(0)
    base = pd.Series(1.5 + 0.1 * rng.standard_normal(400), index=idx)
    z0 = compute_zm(base)
    spike = base.copy()
    spike.iloc[-1] += 5.0
    z1 = compute_zm(spike)
    pd.testing.assert_series_equal(z0.iloc[:-1], z1.iloc[:-1])


def test_availability_d_plus_1_02h():
    # day D usable from D+1 02:00 UTC: T before that sees the previous day
    days = pd.date_range("2021-01-01", periods=5, freq="D", tz="UTC")
    zm = pd.Series([0.0, 1.0, 2.5, -1.0, 3.0], index=days)
    T = pd.DatetimeIndex([
        "2021-01-02 01:00",  # before 2021-01-01 avail? avail D=01-01 is 01-02 02:00 -> sees NaN/earlier
        "2021-01-02 02:00",  # exactly avail of D=01-01 -> 0.0
        "2021-01-02 03:00",  # same -> 0.0
        "2021-01-04 01:59",  # before avail of D=01-03 -> sees D=01-02 -> 1.0
        "2021-01-04 02:00",  # avail of D=01-03 -> 2.5
    ], tz="UTC")
    z = z_at_T(T, zm)
    assert np.isnan(z.iloc[0])
    assert z.iloc[1] == 0.0 and z.iloc[2] == 0.0
    assert z.iloc[3] == 1.0 and z.iloc[4] == 2.5


def test_truncation_future_csv_rows_unchanged():
    # removing future CSV rows must leave z(T) for earlier T unchanged
    idx = pd.date_range("2019-01-01", periods=800, freq="D", tz="UTC").floor("D")
    rng = np.random.default_rng(1)
    mvrv = pd.Series(1.6 + 0.3 * rng.standard_normal(800), index=idx)
    z_full = compute_zm(mvrv)
    z_tr = compute_zm(mvrv.iloc[:700])
    T = pd.DatetimeIndex(["2020-06-01 04:00", "2020-12-01 00:00"], tz="UTC")
    a = z_at_T(T, z_full)
    b = z_at_T(T, z_tr)
    pd.testing.assert_series_equal(a, b)


def test_crosscheck_lit_position_signal_identical():
    # Post-replication cross-check (allowed only AFTER replication.json was saved):
    # independent z(T) must equal oc_lit_position's H8 signal to the digit.
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "lit_sig", root / "research/tournament/oc_lit_position/signals.py")
    lit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lit)
    from research.tournament.audit_mvrv.signals_mvrv import (
        compute_zm,
        load_mvrv_daily,
        z_at_T,
    )
    T = pd.date_range("2021-09-24", "2026-09-23", freq="4h", tz="UTC")
    d = lit.load_mvrv_daily()
    zl = lit.h8_asof_z(d, T)
    mv = load_mvrv_daily()
    za = z_at_T(T, compute_zm(mv)).to_numpy()
    m = np.isfinite(zl) & np.isfinite(za)
    assert int(m.sum()) > 10000
    assert float(np.abs(zl[m] - za[m]).max()) == 0.0
    assert int((zl > 2.0).sum()) == 750 == int((za > 2.0).sum())


def test_m1_gate_and_cutoff():
    T = pd.date_range("2021-09-23 20:00", periods=6, freq="4h", tz="UTC")
    zT = pd.Series([-1.0, 2.5, 2.0, 2.01, np.nan, 5.0], index=T)
    m = m1_multiplier(zT)
    assert m.tolist() == [1.0, 0.5, 1.0, 0.5, 1.0, 0.5]  # strict > 2.0
    sb = pd.DataFrame({"BTCUSDT": [1.0, 1.0, -1.0, 1.0, 1.0, 1.0],
                       "ETHUSDT": [0.0, 2.0, 2.0, -3.0, 0.5, 0.5]}, index=T)
    g = apply_gate(sb, m)
    # row 0 before cutoff -> never gated even though... (z=-1 anyway); force mult 0.5 there
    m2 = pd.Series(0.5, index=T)
    g2 = apply_gate(sb, m2)
    assert g2.loc[T[0], "BTCUSDT"] == 1.0  # pre-2021-09-24 untouched
    assert g2.loc[T[1], "BTCUSDT"] == 0.5 and g2.loc[T[1], "ETHUSDT"] == 1.0
    assert g2.loc[T[2], "BTCUSDT"] == -1.0  # shorts unchanged
    ctrl, means = control_multiplier(sb, m2)
    assert means["2021-09-24"] <= 1.0
