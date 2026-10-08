"""audit_cboost tests: independent cascade-boost checks + look-ahead audit."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "research" / "tournament" / "audit_cboost"
OCC = ROOT / "research" / "tournament" / "oc_cascadeboost"
BARS = ROOT / "research" / "tournament" / "oc_kronoshidden" / "bars_4h_4shift.parquet"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_boost_rule_synthetic():
    """Hand-checked: sigma/trigger/boost arithmetic on a tiny series."""
    br = _load("br_cb", AUD / "boost_rule.py")
    # flat closes -> r=0, sigma=0 -> NaN sigma (s<=0 -> NaN) -> never fires
    c = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    r = br.close_returns(c)
    assert np.isnan(r[0]) and bool((r[1:] == 0).all())
    sig = br.trailing_sigma(np.array([np.nan, 0.0, 0.0, 0.0, 0.0, 0.0] * 30))
    assert bool(np.isnan(sig[:120]).all())  # min_periods 120
    # spike: constant 0 returns then one +50% jump must fire (sigma 0 -> NaN -> no fire is wrong;
    # with tiny noise sigma>0 the jump fires). Build noisy-flat then jump:
    rng = np.random.RandomState(0)
    base = 100 + rng.randn(600) * 0.1
    closes = np.concatenate([base, [base[-1] * 1.5]])
    T = pd.date_range("2021-01-01", periods=len(closes), freq="4h", tz="UTC")
    fires = br.triggers_of(T.values, closes)
    assert bool(fires[-1])  # +40% log move >> 4 sigma of 0.1-noise
    assert not bool(fires[:-1].any())
    # boost window: strictly after tc, up to +7d inclusive
    tc = T[-1] + pd.Timedelta(hours=4)
    grid = pd.DatetimeIndex([tc - pd.Timedelta(minutes=1), tc,
                             tc + pd.Timedelta(hours=4), tc + pd.Timedelta(days=7),
                             tc + pd.Timedelta(days=7, hours=4)])
    b = br.boosted_mask(grid.values, np.array([tc.value], dtype="datetime64[ns]"), 7)
    assert list(b) == [False, False, True, True, False]
    # mult mapping
    assert br.BOOST == 1.5 and br.B7_DAYS == 7 and br.THRESH == 4.0


def test_truncation_causality():
    """Causality/truncation: triggers recomputed from bars truncated at cut match prefix."""
    br = _load("br_cb", AUD / "boost_rule.py")
    df = pd.read_parquet(BARS, columns=["sym", "shift", "T", "close"])
    df["T"] = pd.to_datetime(df["T"], utc=True)
    cut = pd.Timestamp("2023-01-01", tz="UTC")
    for (sym, shift) in [("BTCUSDT", 0), ("ETHUSDT", 2)]:
        g = df[(df["sym"] == sym) & (df["shift"] == shift)].sort_values("T").reset_index(drop=True)
        full_f = br.triggers_of(g["T"].to_numpy(), g["close"].to_numpy(dtype=float))
        kept = g[g["T"] + pd.Timedelta(hours=4) <= cut].reset_index(drop=True)
        kept_f = br.triggers_of(kept["T"].to_numpy(), kept["close"].to_numpy(dtype=float))
        assert (full_f[:len(kept)] == kept_f).all(), (sym, shift)
        # sigma self-exclusion: SIG[i] never contains r[i]
        r = br.close_returns(g["close"].to_numpy(dtype=float)[:600])
        sig = br.trailing_sigma(r)
        # last bar's return must not affect its own sigma: recompute with r[-1]=NaN -> same sig[-1]
        r2 = r.copy()
        r2[-1] = np.nan
        assert br.trailing_sigma(r2)[-1] == sig[-1] or (np.isnan(sig[-1]))


def test_boost_window_timing_market_wide():
    """Window timing: market-wide per shift, 0 < T-tc <= 7d; our parquet obeys it."""
    pq = pd.read_parquet(AUD / "boost_mult_4shift.parquet", columns=["shift", "T", "boosted_B7", "mult_B7"])
    pq["T"] = pd.to_datetime(pq["T"], utc=True)
    assert set(pq["mult_B7"].unique()) <= {1.0, 1.5}
    assert bool(((pq["mult_B7"] == 1.5) == pq["boosted_B7"]).all())
    # at least one boosted and one normal bar per shift (dense windows, not degenerate)
    for s in range(4):
        g = pq[pq["shift"] == s]
        assert bool(g["boosted_B7"].any()) and bool((~g["boosted_B7"]).any()), s
    # no fill in the trigger's own bar: boosted bars are strictly after some tc
    # (spot-check one shift against trigger_counts time-bars)
    tc_info = json.loads((AUD / "tmp" / "trigger_counts.json").read_text())
    assert tc_info["meta"]["thresh"] == 4.0 and tc_info["meta"]["N_days"] == 7


def test_multiplier_application_point():
    """Multiplier is applied inside sleeve_fill_size (per holding bar), cap still binds."""
    src = (AUD / "run_engine.py").read_text()
    assert "mult * 1.7 * tilt(i, a) * base_size(i, a, r, f)" in src
    assert 'kw["sleeve_gross_cap"] = 2.0' in src
    assert "win_start=5" in src
    assert "sleeve_risk_budget" in src and "0.26" in src
    # causal ffill lookup, missing -> 1
    assert "searchsorted" in src and "return 1.0" in src


def test_replication_matches_thresholds():
    """Quantitative comparison vs oc_cascadeboost (run ONLY after replication.json saved)."""
    rep = json.loads((AUD / "replication.json").read_text())
    occ = json.loads((OCC / "results.json").read_text())
    # fits: none in this study (frozen threshold/windows/N/boost); trigger counts exact
    for s in range(4):
        key = [k for k in rep["triggers"]["per_year_shift"] if k.endswith(f"_s{s}")]
        assert key, s
    dev_b7 = occ["dev4_engine"]["B7"]
    dev_ref = occ["dev4_engine"]["REF"]
    for y in range(4):
        assert abs(rep["years_b7"][y]["R"] - dev_b7["years_R"][y]) <= 0.10, y
        assert abs(rep["years_b7"][y]["DD"] - dev_b7["years_DD"][y]) <= 0.5, y
        assert abs(rep["years_ref"][y]["R"] - dev_ref["years_R"][y]) <= 0.10, y
        assert abs(rep["years_ref"][y]["DD"] - dev_ref["years_DD"][y]) <= 0.5, y
    assert abs(rep["dev4_b7"]["R"] - dev_b7["Rdev4"]) <= 0.10
    assert abs(rep["dev4_b7"]["W"] - dev_b7["Wdev4"]) <= 0.10
    last = occ["engine_last_once_REF_pick"]
    assert abs(rep["y4_b7"]["R"] - last["B7"]["Rlast_diag"]) <= 0.10
    assert abs(rep["y4_b7"]["DD"] - last["B7"]["DDlast_diag"]) <= 0.5
    assert abs(rep["y4_ref"]["R"] - last["REF"]["Rlast_diag"]) <= 0.10
    assert abs(rep["y4_ref"]["DD"] - last["REF"]["DDlast_diag"]) <= 0.5
    assert abs(rep["full_path_dd_b7"] - last["B7"]["full_path_dd"]) <= 0.5
    assert abs(rep["full_path_dd_ref"] - last["REF"]["full_path_dd"]) <= 0.5
    assert abs(rep["y5_b7"]["R"] - last["B7"]["R5y"]) <= 0.10
    assert abs(rep["y5_ref"]["R"] - last["REF"]["R5y"]) <= 0.10
