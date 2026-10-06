"""oc_ethbtc tests: causality (truncate & recompute) + alignment + aggregation.

Light: 4h opens + fills_U_ext + results.json only, one process.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_ethbtc.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_ethbtc"
sys.path.insert(0, str(OC))
import regimes_ethbtc as R

VARS = ["ethbtc30", "ethbtc90", "dom30"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)


def test_regime_causal_truncate():
    opens = R.load_opens()
    ref = R.compute_regimes(opens)
    rng = np.random.default_rng(7)
    valid = ref.dropna().index
    for k in range(10):
        t = valid[int(rng.integers(0, len(valid)))]
        probe = R.regimes_truncated(opens, t)
        pd.testing.assert_series_equal(
            probe.loc[t, VARS].astype(float),
            ref.loc[t, VARS].astype(float),
            check_names=False, obj=f"causality t={t}",
        )


def test_no_future_open_used():
    opens = R.load_opens()
    t = pd.Timestamp("2024-03-15 00:00:00", tz="UTC")
    base = R.regimes_truncated(opens, t).loc[t, VARS]
    spiked = opens.copy()
    spiked.loc[spiked.index > t] *= 2.0
    after = R.compute_regimes(spiked).loc[t, VARS]
    pd.testing.assert_series_equal(
        base.astype(float), after.astype(float),
        check_names=False, obj="future opens must not change regime at t",
    )


def test_fill_regime_precedes_fill():
    opens = R.load_opens()
    regimes = R.compute_regimes(opens)
    fills = pd.read_parquet(
        ROOT / "research/tournament/ext/fills_U_ext.parquet", columns=["t_fill", "f"]
    )
    T = pd.to_datetime(fills["t_fill"], utc=True) - pd.to_timedelta(
        fills["f"].astype(float), unit="min"
    )
    asg = R.assign_to_fills(T, regimes)
    assert asg["grid_t"].notna().all()
    assert (asg["grid_t"] <= T).all(), "regime grid_t must precede fill T"
    grid = regimes.index.sort_values()
    nxt = grid[grid.searchsorted(pd.DatetimeIndex(pd.to_datetime(T, utc=True)), side="right")]
    assert ((pd.DatetimeIndex(pd.to_datetime(T, utc=True)) < nxt)).all()


def test_cutoffs_strictly_before_anchor():
    res = json.loads((OC / "results.json").read_text())
    assert res["meta"]["T_max"] < "2026-09-24"
    # previous-history sizes grow monotonically across anchors
    for rows, key in ((res["dip_per_year"], "hist_n"), (res["book_per_year"], "hist_bars")):
        for v in VARS:
            hs = [r[key] for r in rows if r["var"] == v]
            assert hs == sorted(hs) and hs[0] > 0, (v, hs)


def test_aggregation_and_schema():
    res = json.loads((OC / "results.json").read_text())
    assert len(res["dip_per_year"]) == 15 and len(res["book_per_year"]) == 15
    for r in res["dip_per_year"] + res["book_per_year"]:
        assert r["n_lo"] + r["n_mid"] + r["n_hi"] == r["n"], r
        h = r["hilo_bps"]
        exp = 0 if (h is None or (isinstance(h, float) and (np.isnan(h) or h == 0))) \
            else (1 if h > 0 else -1)
        assert r["sign"] == exp, r
        if np.isfinite(r["mean_lo_bps"]) and np.isfinite(r["mean_hi_bps"]):
            assert abs((r["mean_hi_bps"] - r["mean_lo_bps"]) - r["hilo_bps"]) < 0.06, r
    for r in res["book_per_year"]:
        # mean per-bar x n must recover the stored tercile sums (rounding tol)
        for side in ("lo", "mid", "hi"):
            n = r[f"n_{side}"]
            if n and np.isfinite(r[f"mean_{side}_bps"]):
                assert abs(r[f"mean_{side}_bps"] / 1e4 * n - r[f"sum_{side}"]) < 1e-3, r
    for part in ("dip", "book"):
        for v in VARS:
            g = res["gates"][part][v]
            assert g["promising"] == (g["consistent_4of5"] and g["loo_holds"] >= 4), (part, v)
    assert res["gates"]["book"]["dom30"]["promising"] is True
    assert sum(1 for v in VARS for p in ("dip", "book")
               if res["gates"][p][v]["promising"]) == 1
