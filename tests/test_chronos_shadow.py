"""Tests for scripts/chronos_shadow.py (no network, no GPU/model weights)."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chronos_shadow", ROOT / "scripts/chronos_shadow.py")
cs = importlib.util.module_from_spec(SPEC)
sys.modules["chronos_shadow"] = cs
SPEC.loader.exec_module(cs)


def h1_fixture(start="2026-01-01", hours=5000):
    t = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(hours) / 20.0)
    df = pd.DataFrame({"open_time": t, "open": close, "high": close + 0.2,
                       "low": close - 0.2, "close": close, "volume": 1.0,
                       "quote_volume": close * 1.0,
                       "close_time": t + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
                       "closed": True})
    return df


def test_bar_builder_causality_future_hours_ignored():
    h1 = h1_fixture(hours=5000)
    T = h1["open_time"].iloc[4000]
    T = ((T - pd.Timedelta(hours=0)).floor("4h"))
    s = int(T.hour) % 4
    b1 = cs.build_shift_bars(h1, s)
    ctx1 = cs.select_context(b1, T)
    assert len(ctx1) == 512
    h1_future = h1.copy()
    m = h1_future["open_time"] >= pd.Timestamp(T)
    h1_future.loc[m, ["open", "high", "low", "close"]] *= 10.0
    b2 = cs.build_shift_bars(h1_future, s)
    ctx2 = cs.select_context(b2, T)
    pd.testing.assert_frame_equal(ctx1, ctx2)


def test_context_requires_only_closed_bars_and_512():
    h1 = h1_fixture(hours=5000)
    h1.loc[h1.index[-5:], "closed"] = False
    b = cs.build_shift_bars(h1, 0)
    assert pd.Timestamp(b["T"].max()) <= h1[h1["closed"]]["open_time"].max()
    # insufficient history -> empty
    T_early = b["T"].iloc[10]
    assert len(cs.select_context(b, T_early)) == 0
    # deep history -> exactly 512 complete bars
    T = h1[h1["closed"]]["open_time"].iloc[4000].floor("4h")
    s = int(T.hour) % 4
    bars = cs.build_shift_bars(h1, s)
    assert len(cs.select_context(bars, T)) == 512


def test_sigma_hand_checked_synthetic():
    # constant opens -> zero variance -> sigma 0
    ctx = pd.DataFrame({"open": np.full(512, 100.0)})
    assert cs.compute_sigma(ctx, 100.0) == 0.0
    # hand-checked: two-point log-diff series against pandas rolling std
    opens = np.linspace(100.0, 110.0, 512)
    open_T = 110.5
    got = cs.compute_sigma(pd.DataFrame({"open": opens}), open_T)
    lo = np.log(np.r_[opens, [open_T]])
    exp = float(pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()[-1])
    assert abs(got - exp) < 1e-12 and np.isfinite(got) and got > 0
    # research parity: sigma uses log-OPEN diffs (not closes)
    ctx2 = pd.DataFrame({"open": opens, "close": opens * 2.0})
    assert cs.compute_sigma(ctx2, open_T) == got


def test_c2_multiplier_hand_checked_and_matches_fit():
    fits = json.loads((ROOT / "research/tournament/bot_c2shadow/fit_2026.json").read_text())
    f = fits["2026-09-24"]
    assert f["direction"] == 1
    assert abs(f["q20"] - 1.0765874389863197) < 1e-12
    assert abs(f["q80"] - 2.5955569463614445) < 1e-12
    # frozen constants in the script match the file
    assert cs.FROZEN["direction"] == 1
    assert abs(cs.FROZEN["q20"] - f["q20"]) < 1e-12
    assert abs(cs.FROZEN["q80"] - f["q80"]) < 1e-12
    # risk = -ch_q10; favourable outer quintile (risk >= q80) x1.25
    assert cs.assign_c2(3.0, f["direction"], f["q20"], f["q80"]) == 1.25
    # unfavourable outer quintile (risk <= q20) x0.75
    assert cs.assign_c2(0.0, f["direction"], f["q20"], f["q80"]) == 0.75
    # middle -> 1, NaN -> 1
    assert cs.assign_c2(1.5, f["direction"], f["q20"], f["q80"]) == 1.0
    assert cs.assign_c2(float("nan"), f["direction"], f["q20"], f["q80"]) == 1.0
    # flipped direction mirrors the rule
    assert cs.assign_c2(3.0, -1, f["q20"], f["q80"]) == 0.75
    assert cs.assign_c2(0.0, -1, f["q20"], f["q80"]) == 1.25


def test_prospective_labelling_and_targets():
    T = pd.Timestamp("2026-10-07T08:00:00Z")
    assert cs.is_prospective(T + pd.Timedelta(minutes=29), T) is True
    assert cs.is_prospective(T + pd.Timedelta(minutes=31), T) is False
    tg = cs.targets_for_window(pd.Timestamp("2026-10-07T10:35:00Z"), 1)
    assert tg == [(2, pd.Timestamp("2026-10-07T10:00:00Z"))]
    tg3 = cs.targets_for_window(pd.Timestamp("2026-10-07T10:35:00Z"), 3)
    assert [s for s, _ in tg3] == [0, 1, 2]
    assert tg3[-1][1] == pd.Timestamp("2026-10-07T10:00:00Z")


def test_idempotence_key_and_model_pin():
    assert cs.MODEL == "amazon/chronos-bolt-small"
    assert cs.MODEL_REVISION == "772f3d25d38aec6d914c8949dab4462e2d46f5d8"
    assert cs.MODEL_REVISION in cs.model_sha()
    import inspect
    assert "revision=MODEL_REVISION" in inspect.getsource(cs.load_chronos)
    h1 = h1_fixture(start="2025-01-01", hours=5000)
    T = h1["open_time"].iloc[3000].floor("4h")
    s = int(T.hour) % 4
    bars = cs.build_shift_bars(h1, s)
    ctx = cs.select_context(bars, T)
    assert len(ctx) == 512
    sig = cs.compute_sigma(ctx, float(h1[h1["open_time"] == T]["open"].iloc[0]))
    assert np.isfinite(sig) and sig > 0
    keys = {(r["sym"], r["shift"], pd.Timestamp(r["T"]).isoformat()) for r in
            [{"sym": "BTCUSDT", "shift": s, "T": T}]}
    new = [r for r in [{"sym": "BTCUSDT", "shift": s, "T": T},
                       {"sym": "ETHUSDT", "shift": s, "T": T}]
           if (r["sym"], r["shift"], pd.Timestamp(r["T"]).isoformat()) not in keys]
    assert [r["sym"] for r in new] == ["ETHUSDT"]
