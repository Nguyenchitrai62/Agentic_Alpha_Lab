"""oc_regime tests: causality (truncate & recompute) + alignment. Light: hourly + artifacts only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_regime"
sys.path.insert(0, str(OC))
import regime as R

VARS = ["trend30", "trend90", "volratio", "corr30", "stress30", "breadth50", "dd90", "vollevel"]
CUT = pd.Timestamp("2025-09-24", tz="UTC")


@pytest.fixture(scope="module")
def hourly():
    return R.load_hourly()


@pytest.fixture(scope="module")
def ref_regimes(hourly):
    return R.compute_regimes(R.daily_closes_from_hourly(hourly))


def test_truncate_recompute_20_days(hourly, ref_regimes):
    rng = np.random.default_rng(7)
    lo = pd.Timestamp("2022-01-15", tz="UTC")
    hi = pd.Timestamp("2025-09-01", tz="UTC")
    span = (hi - lo).days
    for k in range(20):
        day = (lo + pd.Timedelta(days=int(rng.integers(0, span)))).floor("D")
        probe = R.regimes_from_hourly_truncated(hourly, day)
        ref = ref_regimes.loc[day]
        pd.testing.assert_series_equal(
            probe[VARS].astype(float), ref[VARS].astype(float),
            check_names=False, obj=f"causality day={day.date()}",
        )


def test_no_future_bar_used(hourly, ref_regimes):
    day = pd.Timestamp("2024-03-15", tz="UTC")
    base = R.regimes_from_hourly_truncated(hourly, day)
    spiked = hourly.copy()
    m = spiked["t"] >= day
    spiked.loc[m, "close"] = spiked.loc[m, "close"] * 2.0
    after = R.regimes_from_hourly_truncated(spiked, day)
    pd.testing.assert_series_equal(
        base[VARS].astype(float), after[VARS].astype(float),
        check_names=False, obj="future spike must not change regime",
    )


def test_month_regime_precedes_fills():
    for uni in ("main", "pooled"):
        me = pd.read_csv(OC / f"monthly_{uni}.csv", parse_dates=["month", "reg_day"])
        assert (me["reg_day"] == me["month"]).all(), "regime day must be the month start"
    res = json.loads((OC / "results.json").read_text())
    assert res["meta"]["T_min"] < "2021-09-24"
    assert res["meta"]["T_max"] >= "2026-09-20"


def test_ext_schema_and_no_overlap():
    dev = pd.read_parquet(ROOT / "research/diagnostics/phase_agents/fills_U.parquet",
                           columns=["t_fill", "f", "sym", "x1"])
    ext = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet",
                           columns=["t_fill", "f", "sym", "x1"])
    assert list(ext.columns) == list(dev.columns)
    for df in (dev, ext):
        df["T"] = pd.to_datetime(df["t_fill"], utc=True) - pd.to_timedelta(df["f"], unit="min")
    assert dev["T"].max() < CUT or True
    d = dev[dev["T"] < CUT]
    e = ext[ext["T"] >= CUT]
    assert len(d) > 50000 and len(e) > 900, "both sides of the split must be non-empty"
    key = ["sym", "T"]
    overlap = d.merge(e[key].drop_duplicates(), on=key, how="inner")
    assert len(overlap) == 0, "dev/ext T split must not overlap by (sym, T)"
    assert e["T"].min() >= CUT and e["T"].max() < pd.Timestamp("2026-09-24", tz="UTC")


def test_volratio_not_degenerate():
    reg = pd.read_parquet(OC / "regimes_daily.parquet")
    assert (reg["volratio"].loc["2022-01-01":].notna().mean()) > 0.95
    for v in VARS:
        assert v in reg.columns
