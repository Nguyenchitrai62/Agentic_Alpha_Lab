"""Tests for oc_presampletilt (frozen 2021 rule on pre-sample years)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_presampletilt"
sys.path.insert(0, str(HERE))
from tilt_rule import FROZEN_2021, assign_mult, variant_mult  # noqa: E402


def test_assign_mult_handchecked():
    f = FROZEN_2021["V_RV6"]
    assert assign_mult(f["q80"], 1, f["q20"], f["q80"]) == 1.25
    assert assign_mult(f["q20"], 1, f["q20"], f["q80"]) == 0.75
    assert assign_mult((f["q20"] + f["q80"]) / 2, 1, f["q20"], f["q80"]) == 1.0
    assert assign_mult(float("nan"), 1, f["q20"], f["q80"]) == 1.0
    assert assign_mult(float("inf"), 1, f["q20"], f["q80"]) == 1.0
    # direction -1 mirrors (synthetic, not used; rule supports it)
    assert assign_mult(f["q80"], -1, f["q20"], f["q80"]) == 0.75
    assert assign_mult(f["q20"], -1, f["q20"], f["q80"]) == 1.25
    # all three frozen dirs are +1
    for v in ("V_RV6", "V_GARCH", "C2"):
        assert FROZEN_2021[v]["direction"] == 1
        assert variant_mult(FROZEN_2021[v]["q80"] + 1.0, v) == 1.25
        assert variant_mult(float("nan"), v) == 1.0


def test_frozen_2021_matches_source_fits():
    vv = json.loads((ROOT / "research/tournament/oc_voltilt/fits.json").read_text())
    cc = json.loads((ROOT / "research/tournament/oc_chronos/fits.json").read_text())
    for v in ("V_RV6", "V_GARCH"):
        src = vv[v]["2021-09-24"]
        for k in ("direction", "q20", "q80"):
            assert FROZEN_2021[v][k] == src[k]
    for k in ("direction", "q20", "q80"):
        assert FROZEN_2021["C2"][k] == cc["2021-09-24"][k]


def test_vol_truncation_causality():
    """Features recomputed from bars truncated at a cut date are identical on the
    kept prefix with FROZEN GARCH params (causality: no future bar leaks)."""
    bars = pd.read_parquet(HERE / "bars_4h_presample.parquet")
    vol = pd.read_parquet(HERE / "vol_features_presample.parquet")
    b = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    cut = pd.Timestamp("2019-06-01", tz="UTC")
    b_tr = b[b["T"] < cut].reset_index(drop=True)
    O = b_tr["open"].to_numpy(dtype=float)
    C = b_tr["close"].to_numpy(dtype=float)
    lo = np.log(np.clip(O, 1e-12, None))
    sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
    lc = np.log(np.clip(C, 1e-12, None))
    r = np.empty_like(lc)
    r[0] = np.nan
    r[1:] = lc[1:] - lc[:-1]
    rv6 = pd.Series(r).rolling(6).std().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        risk = rv6 / sig
    risk[~(np.isfinite(rv6) & np.isfinite(sig) & (sig > 0))] = np.nan
    T = b_tr["T"].to_numpy()
    keep = np.isfinite(sig)
    ref = vol[(vol["sym"] == "BTCUSDT") & (vol["shift"] == 0)].sort_values("T")
    ref = ref[ref["T"] < cut].reset_index(drop=True)
    got = pd.DataFrame({"T": T[keep], "risk_RV6": risk[keep]}).sort_values("T").reset_index(drop=True)
    merged = ref.merge(got, on="T", suffixes=("_ref", "_got"))
    assert len(merged) == len(ref) == len(got)
    assert np.allclose(merged["risk_RV6_ref"].to_numpy(dtype=float),
                       merged["risk_RV6_got"].to_numpy(dtype=float),
                       rtol=1e-12, atol=1e-15, equal_nan=True)


def test_ledger_interval_truncation():
    """Ledger fills sit on bars with open inside their own year interval."""
    bt = np.load(HERE / "tmp/bt_presample.npy", allow_pickle=True)
    led = dict(np.load(HERE / "tmp/ledger_presample.npz"))
    bounds = {
        0: (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
        1: (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
        2: (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
        3: (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
    }
    for y, (S, E) in bounds.items():
        m = led["year"] == y
        assert m.any()
        for t in pd.DatetimeIndex([pd.Timestamp(x) for x in bt[m]]):
            assert S <= t < E


def test_placebo_percentile_handchecked():
    """Percentile formula on a synthetic case: actual above all perms -> 100."""
    rng = np.random.default_rng(20261007)
    actual = 10.0
    perms = rng.normal(0, 1, size=1000)
    pct = 100.0 * (1 + int((perms <= actual).sum())) / 1001
    assert pct == 100.0
    actual2 = -10.0
    pct2 = 100.0 * (1 + int((perms <= actual2).sum())) / 1001
    assert pct2 < 5.0
