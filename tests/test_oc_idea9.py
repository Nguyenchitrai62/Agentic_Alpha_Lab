"""Tests for oc_idea9 (research/tournament/oc_idea9). Schema, partition, causality."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_idea9"
RES = OC / "results.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_idea9_compute", OC / "compute_idea9.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_idea9/compute_idea9.py first"
    r = _load()
    for k in ("definitions", "symbols", "anchor_years", "n_bars", "spx",
              "variants", "decision", "scale_summary"):
        assert k in r, k
    assert set(r["variants"]) == {"base_60d", "tilt_gap075"}
    assert r["n_bars"] == 10955
    for name, v in r["variants"].items():
        assert len(v["per_year"]) == 5, name
        for row in v["per_year"]:
            for k in ("n_bars", "ret", "dd", "sharpe", "worst_day", "fire_rate"):
                assert k in row, (name, row)
    assert r["spx"]["rows"] == 2696
    assert r["spx"]["first"] == "2016-01-04" and r["spx"]["last"] == "2026-09-23"


def test_year_partition_covers_grid():
    r = _load()
    ns = [row["n_bars"] for row in r["variants"]["base_60d"]["per_year"]]
    assert ns == [2190, 2190, 2196, 2190, 2189], ns
    assert sum(ns) == r["n_bars"]
    ns2 = [row["n_bars"] for row in r["variants"]["tilt_gap075"]["per_year"]]
    assert ns2 == ns


def test_base_matches_oc_bookvol():
    """BASE must reproduce the oc_bookvol V0 row (same books, same math)."""
    r = _load()
    want_ret = [0.304858, 0.64167, 0.967846, 1.15555, 0.817877]
    want_dd = [0.228127, 0.105103, 0.153012, 0.104646, 0.135891]
    rows = r["variants"]["base_60d"]["per_year"]
    for row, wr, wd in zip(rows, want_ret, want_dd):
        assert abs(row["ret"] - wr) < 1e-6, row
        assert abs(row["dd"] - wd) < 1e-6, row


def test_turnover_cost_nonnegative():
    r = _load()
    for name, v in r["variants"].items():
        assert v["total_turnover"] >= 0, name
        assert v["total_cost"] >= 0, name
        assert abs(v["total_cost"] - 0.0005 * v["total_turnover"]) < 5e-4, name


def test_decision_matches_counts():
    r = _load()
    d = r["decision"]
    n_dd = sum(1 for x in d["dDD"] if x is not None and x > 0)
    assert d["dd_pos"] == f"{n_dd}/5"
    assert d["loyo_dd"] == f"{sum(d['loyo_detail'])}/5"
    assert d["tail_pos"] == f"{sum(d['tail_ok'])}/5"
    expect = n_dd >= 4 and sum(d["loyo_detail"]) >= 4 and sum(d["tail_ok"]) >= 4
    assert d["promising"] == expect
    assert d["promising"] is True
    assert d["dd_pos"] == "4/5" and d["loyo_dd"] == "4/5" and d["tail_pos"] == "4/5"


def test_spx_manifest_and_bounds():
    mf = json.loads((ROOT / "data/raw/newinfo_idea9/manifest.json").read_text())
    assert "url" in mf and mf["symbol"] == "^GSPC"
    for f, meta in mf["files"].items():
        p = ROOT / "data/raw/newinfo_idea9" / f
        assert p.exists(), f
        assert hashlib.sha256(p.read_bytes()).hexdigest() == meta["sha256"], f
    assert mf["last"] < "2026-09-24"


def test_close_utc_handchecks():
    mod = _mod()
    assert mod.close_utc_for(dt.date(2022, 1, 26)) == pd.Timestamp("2022-01-26 21:00", tz="UTC")  # EST
    assert mod.close_utc_for(dt.date(2022, 6, 15)) == pd.Timestamp("2022-06-15 20:00", tz="UTC")  # EDT
    assert mod.close_utc_for(dt.date(2024, 1, 11)) == pd.Timestamp("2024-01-11 21:00", tz="UTC")  # EST
    assert mod.close_utc_for(dt.date(2024, 6, 12)) == pd.Timestamp("2024-06-12 20:00", tz="UTC")  # EDT


def test_threshold_prefit_window():
    mod = _mod()
    daily = mod.load_spx()
    q = mod.thresholds(daily)
    assert set(q) == {str(a.date()) for a in ANCHORS}
    a0 = ANCHORS[0]
    g = daily.loc[daily["close_utc"] < a0 - pd.Timedelta(days=7), "gap"].dropna()
    assert abs(q[str(a0.date())] - float(g.quantile(0.25))) < 1e-12
    assert (daily.loc[daily["close_utc"] < a0 - pd.Timedelta(days=7), "day"] >= dt.date(2016, 1, 1)).all()
    assert len(g) > 1300  # ~5.6y of sessions before year 1


def test_gap_causal_strictly_before_T():
    """gap(T) uses only SPX rows with close_utc < T; T at a close instant is excluded."""
    mod = _mod()
    daily = mod.load_spx()
    grid = pd.DatetimeIndex([pd.Timestamp("2022-01-27 21:00", tz="UTC"),
                             pd.Timestamp("2022-01-27 22:00", tz="UTC")])
    gap = mod.gaps_for_T(grid, daily)
    # close_utc(2022-01-27) = 21:00 EST; T=21:00 excludes it -> D = 2022-01-26
    row26 = daily.loc[daily["day"] == dt.date(2022, 1, 26)].iloc[0]
    row27 = daily.loc[daily["day"] == dt.date(2022, 1, 27)].iloc[0]
    assert abs(gap.iloc[0] - row26["gap"]) < 1e-12
    # T=22:00 is after the 21:00 EST close -> D = 2022-01-27
    assert abs(gap.iloc[1] - row27["gap"]) < 1e-12
    # dropping every SPX row on/after max(T) leaves gaps unchanged
    trunc = daily[daily["close_utc"] < grid.max()].copy()
    gap2 = mod.gaps_for_T(grid, trunc)
    pd.testing.assert_series_equal(gap, gap2, check_names=False)
    # synthetic 4h grid: truncation of later SPX rows never moves earlier gaps
    grid2 = pd.date_range("2021-10-01", periods=200, freq="4h", tz="UTC")
    full = mod.gaps_for_T(grid2, daily)
    trunc2 = daily[daily["day"] < dt.date(2021, 11, 1)].copy()
    early = grid2[grid2 < pd.Timestamp("2021-11-01", tz="UTC")]
    pd.testing.assert_series_equal(full.loc[early], mod.gaps_for_T(early, trunc2),
                                   check_names=False)


def test_scales_causal_on_truncation():
    mod = _mod()
    rng = np.random.default_rng(7)
    idx = pd.date_range("2023-01-01", periods=501, freq="4h", tz="UTC")
    opens = pd.DataFrame({s: 100.0 * np.cumprod(1 + 0.005 * rng.standard_normal(501))
                          for s in SYMS}, index=idx)
    books = pd.DataFrame(rng.standard_normal((501, len(SYMS))) * 0.05,
                         index=idx, columns=SYMS)
    fwd1 = (opens.shift(-1) / opens - 1.0).iloc[:-1]
    books = books.iloc[:-1]
    dial = pd.Series(np.where(rng.random(len(books)) < 0.25, 0.75, 1.0), index=books.index)
    full, _ = mod.compute_scales(books, fwd1, dial)
    for cut in (300, 420):
        part, _ = mod.compute_scales(books.iloc[: cut + 1], fwd1.iloc[: cut + 1],
                                     dial.iloc[: cut + 1])
        for name in full:
            pd.testing.assert_frame_equal(full[name].iloc[: cut + 1], part[name],
                                          check_dtype=False)
