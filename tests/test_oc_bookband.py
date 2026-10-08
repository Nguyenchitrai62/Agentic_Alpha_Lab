"""oc_bookband tests: causality/truncation + hand-checked synthetic band cases."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent / "research/tournament/oc_bookband"
sys.path.insert(0, str(HERE))
import bookband as bb


def _synth(n=600, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="4h", tz="UTC")
    T = pd.DataFrame(rng.normal(0, 0.1, size=(n, 5)), index=idx, columns=bb.SYMS)
    return T


def test_typical_is_strictly_causal():
    T = _synth()
    typ = bb.trailing_typical(T)
    # typ[t] must not use T[t]: perturb T[t] and check typ[t] unchanged
    T2 = T.copy()
    T2.iloc[300] *= 100.0
    typ2 = bb.trailing_typical(T2)
    assert typ.iloc[300].equals(typ2.iloc[300]), "typ[t] leaked T[t]"
    # but typ[t+1] must see it
    assert not typ.iloc[301].equals(typ2.iloc[301])
    # truncation: trailing window bounded by 540 bars
    assert typ.iloc[0].isna().all(), "no history -> NaN (band inactive)"
    assert typ.iloc[bb.MIN_PERIODS].notna().all()


def test_band_hand_checked():
    idx = pd.date_range("2022-01-01", periods=200, freq="4h", tz="UTC")
    T = pd.DataFrame(0.0, index=idx, columns=bb.SYMS)
    T["BTCUSDT"] = 0.20  # constant target 0.20
    typ = bb.trailing_typical(T)
    # at t=150 typical ~= 0.20; small wiggle +0.01 (5% of typical) suppressed under NB10
    T2 = T.copy()
    T2.iloc[150, T2.columns.get_loc("BTCUSDT")] = 0.21
    F10 = bb.apply_band(T2, bb.trailing_typical(T2), 0.10)
    assert F10.iloc[150]["BTCUSDT"] == 0.20, "5% wiggle must be suppressed by NB10"
    # big move +0.05 (25%) executes under NB10
    T3 = T.copy()
    T3.iloc[150, T3.columns.get_loc("BTCUSDT")] = 0.25
    F10b = bb.apply_band(T3, bb.trailing_typical(T3), 0.10)
    assert F10b.iloc[150]["BTCUSDT"] == 0.25, "25% move must execute under NB10"
    # same 5% wiggle executes under... no: still suppressed under NB25
    assert bb.apply_band(T2, bb.trailing_typical(T2), 0.25).iloc[150]["BTCUSDT"] == 0.20
    # direction flip always executes even if tiny: prev +0.20 -> cur -0.01
    T4 = T.copy()
    T4.iloc[150, T4.columns.get_loc("BTCUSDT")] = -0.01
    Ff = bb.apply_band(T4, bb.trailing_typical(T4), 0.25)
    assert Ff.iloc[150]["BTCUSDT"] == -0.01, "sign flip must always execute"
    # memory: suppression persists (F stays at executed level, not T[t-1])
    T5 = T.copy()
    T5.iloc[150, T5.columns.get_loc("BTCUSDT")] = 0.21  # suppressed
    T5.iloc[151, T5.columns.get_loc("BTCUSDT")] = 0.22  # delta vs F=0.20 is 0.02 = band edge
    F5 = bb.apply_band(T5, bb.trailing_typical(T5), 0.10)
    assert F5.iloc[150]["BTCUSDT"] == 0.20
    # |0.22-0.20|=0.02 <= 0.10*0.20=0.02 -> suppressed (boundary inclusive)
    assert F5.iloc[151]["BTCUSDT"] == 0.20


def test_turnover_proxy_hand_checked():
    idx = pd.date_range("2022-01-01", periods=4, freq="4h", tz="UTC")
    T = pd.DataFrame(0.0, index=idx, columns=bb.SYMS)
    T["BTCUSDT"] = [0.0, 0.10, 0.10, -0.10]
    typ = pd.DataFrame(0.10, index=idx, columns=bb.SYMS)
    typ.iloc[0] = np.nan  # inactive at first bar
    fwd = pd.DataFrame(0.01, index=idx, columns=bb.SYMS)
    out = bb.turnover_frame(T, typ, fwd, p_list=(0.10,), fee_rate=0.0002)
    # turnover = 0.10 + 0 + 0.20 = 0.30
    assert out["turnover_total"] == round(0.30, 6)
    assert out["fee_total"] == round(0.30 * 0.0002, 6)
