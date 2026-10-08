"""Tests for scripts/d1_shadow.py (no network, no model - D1 is model-free)."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("d1_shadow", ROOT / "scripts/d1_shadow.py")
ds = importlib.util.module_from_spec(SPEC)
sys.modules["d1_shadow"] = ds
SPEC.loader.exec_module(ds)


def h1_fixture(start="2026-01-01", hours=900):
    t = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(hours) / 20.0)
    df = pd.DataFrame({"open_time": t, "open": close, "high": close + 0.2,
                       "low": close - 0.2, "close": close, "volume": 1.0,
                       "quote_volume": close * 1.0,
                       "close_time": t + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
                       "closed": True})
    return df


def test_share_of_hand_checked_synthetic():
    assert ds.share_of([-0.01] * 36) == 1.0  # all-down -> 1
    assert ds.share_of([0.01] * 36) == 0.0  # all-up -> 0
    assert abs(ds.share_of([0.01, -0.01] * 18) - 0.5) < 1e-12  # symmetric -> 0.5
    assert not np.isfinite(ds.share_of([0.0] * 36))  # zero-vol -> NaN
    assert not np.isfinite(ds.share_of([]))  # empty -> NaN
    assert not np.isfinite(ds.share_of([0.01, np.nan] + [0.01] * 34))  # non-finite -> NaN


def test_compute_d1_window_exactness_and_causality():
    # 37 closes -> 36 returns; hand-check against the research formula
    closes = 100.0 * np.exp(np.linspace(0.0, 0.05, 37))  # steady drift up
    ctx = pd.DataFrame({"close": closes})
    risk, C0 = ds.compute_d1(ctx)
    r = np.diff(np.log(closes))
    exp = float(np.sum(np.minimum(r, 0.0) ** 2) / np.sum(r * r))
    assert abs(risk - exp) < 1e-12 and C0 == closes[-1]
    # truncation: recomputing from data cut at T gives the identical value
    h1 = h1_fixture(hours=900)
    T = h1["open_time"].iloc[800].floor("4h")
    s = int(T.hour) % 4
    b1 = ds.build_shift_bars(h1, s)
    r1, _ = ds.compute_d1(ds.select_context(b1, T))
    h1_future = h1.copy()
    m = h1_future["open_time"] >= pd.Timestamp(T)
    h1_future.loc[m, ["open", "high", "low", "close"]] *= 10.0
    b2 = ds.build_shift_bars(h1_future, s)
    r2, _ = ds.compute_d1(ds.select_context(b2, T))
    assert r1 == r2 and np.isfinite(r1)


def test_context_requires_37_complete_bars():
    h1 = h1_fixture(hours=900)
    T = h1["open_time"].iloc[800].floor("4h")
    s = int(T.hour) % 4
    bars = ds.build_shift_bars(h1, s)
    assert len(ds.select_context(bars, T)) == 37
    assert len(ds.select_context(bars, bars["T"].iloc[10])) == 0  # too early -> empty
    risk, C0 = ds.compute_d1(ds.select_context(bars, bars["T"].iloc[10]))
    assert not np.isfinite(risk)
    # unclosed hours never create a bar beyond the last closed 4h block
    h1b = h1_fixture(hours=900)
    h1b.loc[h1b.index[-5:], "closed"] = False
    bb = ds.build_shift_bars(h1b, 0)
    assert pd.Timestamp(bb["T"].max()) <= h1b[h1b["closed"]]["open_time"].max()


def test_d1_multiplier_hand_checked_and_matches_fit():
    fits = json.loads((ROOT / "research/tournament/bot_d1shadow/fit_2026.json").read_text())
    f = fits["2026-09-24"]
    assert f["direction"] == 1
    assert abs(f["q20"] - 0.2902893279268819) < 1e-12
    assert abs(f["q80"] - 0.7411885300667425) < 1e-12
    assert ds.FROZEN["direction"] == 1
    assert abs(ds.FROZEN["q20"] - f["q20"]) < 1e-12
    assert abs(ds.FROZEN["q80"] - f["q80"]) < 1e-12
    assert ds.WIN_D1 == 36 and ds.NEED_BARS == 37
    # favourable outer quintile (risk >= q80) x1.25
    assert ds.assign_d1(0.9, f["direction"], f["q20"], f["q80"]) == 1.25
    # unfavourable outer quintile (risk <= q20) x0.75
    assert ds.assign_d1(0.1, f["direction"], f["q20"], f["q80"]) == 0.75
    # middle -> 1, NaN -> 1
    assert ds.assign_d1(0.5, f["direction"], f["q20"], f["q80"]) == 1.0
    assert ds.assign_d1(float("nan"), f["direction"], f["q20"], f["q80"]) == 1.0
    # flipped direction mirrors the rule
    assert ds.assign_d1(0.9, -1, f["q20"], f["q80"]) == 0.75
    assert ds.assign_d1(0.1, -1, f["q20"], f["q80"]) == 1.25


def test_prospective_labelling_and_targets():
    T = pd.Timestamp("2026-10-07T08:00:00Z")
    assert ds.is_prospective(T + pd.Timedelta(minutes=29), T) is True
    assert ds.is_prospective(T + pd.Timedelta(minutes=31), T) is False
    tg = ds.targets_for_window(pd.Timestamp("2026-10-07T10:35:00Z"), 1)
    assert tg == [(2, pd.Timestamp("2026-10-07T10:00:00Z"))]
    tg3 = ds.targets_for_window(pd.Timestamp("2026-10-07T10:35:00Z"), 3)
    assert [s for s, _ in tg3] == [0, 1, 2]
    assert tg3[-1][1] == pd.Timestamp("2026-10-07T10:00:00Z")


def test_idempotence_key_and_source_window_pin():
    assert ds.model_sha().startswith("model-free:D1")
    import inspect
    assert "WIN_D1" in inspect.getsource(ds.check_source_def)
    keys = {(r["sym"], r["shift"], pd.Timestamp(r["T"]).isoformat()) for r in
            [{"sym": "BTCUSDT", "shift": 0, "T": pd.Timestamp("2026-10-07T08:00:00Z")}]}
    new = [r for r in [{"sym": "BTCUSDT", "shift": 0, "T": pd.Timestamp("2026-10-07T08:00:00Z")},
                       {"sym": "ETHUSDT", "shift": 0, "T": pd.Timestamp("2026-10-07T08:00:00Z")}]
           if (r["sym"], r["shift"], pd.Timestamp(r["T"]).isoformat()) not in keys]
    assert [r["sym"] for r in new] == ["ETHUSDT"]
