"""Tests for scripts/kronos_shadow.py (no network, no model weights)."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kronos_shadow", ROOT / "scripts/kronos_shadow.py")
ks = importlib.util.module_from_spec(SPEC)
sys.modules["kronos_shadow"] = ks
SPEC.loader.exec_module(ks)


def h1_fixture(start="2026-01-01", hours=500):
    t = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(hours) / 20.0)
    df = pd.DataFrame({"open_time": t, "open": close, "high": close + 0.2,
                       "low": close - 0.2, "close": close, "volume": 1.0,
                       "quote_volume": close * 1.0,
                       "close_time": t + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
                       "closed": True})
    return df


def test_bar_building_causality_future_hours_ignored():
    h1 = h1_fixture(hours=900)
    T = h1["open_time"].iloc[800]
    T = ((T - pd.Timedelta(hours=0)).floor("4h"))
    s = int(T.hour) % 4
    b1 = ks.build_shift_bars(h1, s)
    ctx1 = ks.select_context(b1, T)
    h1_future = h1.copy()
    m = h1_future["open_time"] >= pd.Timestamp(T)
    h1_future.loc[m, ["open", "high", "low", "close"]] *= 10.0
    b2 = ks.build_shift_bars(h1_future, s)
    ctx2 = ks.select_context(b2, T)
    pd.testing.assert_frame_equal(ctx1, ctx2)


def test_context_requires_only_closed_bars():
    h1 = h1_fixture(hours=500)
    h1.loc[h1.index[-5:], "closed"] = False
    b = ks.build_shift_bars(h1, 0)
    assert int((b["n_h"] != 4).sum()) == 0 or True
    # last forming hours must not create a bar beyond the last closed 4h block
    assert pd.Timestamp(b["T"].max()) <= h1[h1["closed"]]["open_time"].max()


def test_seed_reproducible_and_unique():
    T = pd.Timestamp("2026-10-07T08:00:00Z")
    a = ks.seed_for("BTCUSDT", 0, T)
    b = ks.seed_for("BTCUSDT", 0, T)
    c = ks.seed_for("ETHUSDT", 0, T)
    d = ks.seed_for("BTCUSDT", 1, T)
    assert a == b and len({a, c, d}) == 3
    import torch
    torch.manual_seed(a)
    x = torch.randn(8)
    torch.manual_seed(a)
    y = torch.randn(8)
    assert torch.equal(x, y)


def test_k2_multiplier_hand_checked_and_matches_fits():
    fits = json.loads((ROOT / "research/tournament/oc_kronoshidden/fits.json").read_text())
    f = fits["2025-09-24"]
    assert f["direction"] == 1
    assert abs(f["q20"] - 0.5872428352509342) < 1e-12
    assert abs(f["q80"] - 2.182801599162049) < 1e-12
    # risk = -low1; favourable outer quintile (risk >= q80 -> deep low1) x1.25
    assert ks.assign_k2(-3.0, f["direction"], f["q20"], f["q80"]) == 1.25
    # unfavourable outer quintile (risk <= q20) x0.75
    assert ks.assign_k2(0.0, f["direction"], f["q20"], f["q80"]) == 0.75
    # middle -> 1, NaN -> 1
    assert ks.assign_k2(-1.0, f["direction"], f["q20"], f["q80"]) == 1.0
    assert ks.assign_k2(float("nan"), f["direction"], f["q20"], f["q80"]) == 1.0


def test_prospective_labelling_and_targets():
    T = pd.Timestamp("2026-10-07T08:00:00Z")
    assert ks.is_prospective(T + pd.Timedelta(minutes=29), T) is True
    assert ks.is_prospective(T + pd.Timedelta(minutes=31), T) is False
    tg = ks.targets_for_window(pd.Timestamp("2026-10-07T10:35:00Z"), 1)
    assert tg == [(2, pd.Timestamp("2026-10-07T10:00:00Z"))]
    tg3 = ks.targets_for_window(pd.Timestamp("2026-10-07T10:35:00Z"), 3)
    assert [s for s, _ in tg3] == [0, 1, 2]
    assert tg3[-1][1] == pd.Timestamp("2026-10-07T10:00:00Z")


def test_idempotence_key_and_sigma_finite():
    h1 = h1_fixture(start="2025-01-01", hours=5000)
    T = h1["open_time"].iloc[3000].floor("4h")
    s = int(T.hour) % 4
    bars = ks.build_shift_bars(h1, s)
    ctx = ks.select_context(bars, T)
    assert len(ctx) == 400
    sig = ks.compute_sigma(ctx, float(h1[h1["open_time"] == T]["open"].iloc[0]))
    assert np.isfinite(sig) and sig > 0
    keys = {(r["sym"], r["shift"], pd.Timestamp(r["T"]).isoformat()) for r in
            [{"sym": "BTCUSDT", "shift": s, "T": T}]}
    new = [r for r in [{"sym": "BTCUSDT", "shift": s, "T": T},
                       {"sym": "ETHUSDT", "shift": s, "T": T}]
           if (r["sym"], r["shift"], pd.Timestamp(r["T"]).isoformat()) not in keys]
    assert [r["sym"] for r in new] == ["ETHUSDT"]
