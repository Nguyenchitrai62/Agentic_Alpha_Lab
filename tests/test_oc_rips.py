"""oc_rips tests: regime truncation causality + fill/exit logic on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_rips"
sys.path.insert(0, str(OC))
import backtest as B
import regimes as RG

MK, TK = 0.0002, 0.00055


def _synth_daily(n=500, seed=11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    px = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, size=(n, 5)), axis=0))
    return pd.DataFrame(px, index=days, columns=RG.SYMS)


def test_regime_truncation_20_days():
    daily = _synth_daily()
    full = RG.build_regimes(daily)
    rng = np.random.default_rng(7)
    days = full.index[400:490]
    pick = rng.choice(len(days), size=20, replace=False)
    for j in pick:
        day = days[j]
        probe = RG.regimes_truncated(daily, day)
        ref = full.loc[day]
        pd.testing.assert_series_equal(
            probe[["trend90", "below200", "volratio", "breadth50"]].astype(float),
            ref[["trend90", "below200", "volratio", "breadth50"]].astype(float),
            check_names=False, obj=f"causality day={day.date()}",
        )


def test_daily_close_uses_only_past_minutes():
    mins = pd.date_range("2022-03-01", periods=3 * 1440, freq="1min", tz="UTC")
    df = pd.DataFrame({"open_time": mins, "close": 100.0})
    df.loc[df["open_time"] >= pd.Timestamp("2022-03-03", tz="UTC"), "close"] = 500.0
    d = RG.daily_closes_from_minutes(df)
    assert d.loc[pd.Timestamp("2022-03-01", tz="UTC")] == 100.0
    assert d.loc[pd.Timestamp("2022-03-02", tz="UTC")] == 100.0
    assert d.loc[pd.Timestamp("2022-03-03", tz="UTC")] == 500.0


def _flat_path(n=300, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    C = np.full(n, o)
    return O, H, Lw, C


def test_fill_tp_short():
    O, H, Lw, C = _flat_path()
    L, s, f, b0 = 101.0, 0.01, 20, 0
    tp = L * (1 - s)
    Lw[25] = tp - 0.01  # strict trade-through
    H[25] = L  # no backstop
    x, px, how = B.resolve_exit(O, H, Lw, C, f, L, s, b0, -1)
    assert how == "tp" and x == 25 and px == tp
    assert abs(B.net_short(L, px, how) - ((L - tp) / L - 2 * MK)) < 1e-12


def test_stop_backstop_and_stop_first():
    O, H, Lw, C = _flat_path()
    L, s, f, b0 = 101.0, 0.01, 20, 0
    bs = L * (1 + 8 * s)
    tp = L * (1 - s)
    H[25] = bs + 0.05   # backstop touch
    Lw[25] = tp - 0.01  # TP also touched same minute -> stop wins
    x, px, how = B.resolve_exit(O, H, Lw, C, f, L, s, b0, -1)
    assert how == "stop" and x == 25 and px == max(bs, O[25])
    # block-close stop: calm minutes, then block-end close above SC
    O2, H2, Lw2, C2 = _flat_path()
    sc = L * (1 + 4 * s)
    C2[25] = sc + 0.05  # f+5 block end
    O2[26] = 102.0
    x, px, how = B.resolve_exit(O2, H2, Lw2, C2, f, L, s, b0, -1)
    assert how == "stop" and x == 26 and px == 102.0


def test_timeout_short():
    O, H, Lw, C = _flat_path()
    L, s, f, b0 = 101.0, 0.01, 20, 0
    O[240] = 100.5
    x, px, how = B.resolve_exit(O, H, Lw, C, f, L, s, b0, -1)
    assert how == "time" and x == 240 and px == 100.5
    assert abs(B.net_short(L, px, how) - ((L - px) / L - MK - TK)) < 1e-12
