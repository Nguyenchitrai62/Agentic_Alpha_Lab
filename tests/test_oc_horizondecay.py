"""oc_horizondecay tests: causality/truncation + hand-checked synthetic cases."""

import numpy as np
import pandas as pd

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_horizondecay"))

import decay_rule as dr
from build_horizondecay import relabel_y


def test_weights_renormalised_and_frozen():
    w1 = dr.decay_weights("HD1")
    w2 = dr.decay_weights("HD2")
    assert set(w1) == {1, 2, 6, 18} and set(w2) == {1, 2, 6, 18}
    assert abs(sum(w1.values()) - 1.0) < 1e-12
    assert abs(sum(w2.values()) - 1.0) < 1e-12
    # hand-checked frozen fractions: HD1 18/31, 9/31, 3/31, 1/31
    assert abs(w1[1] - 18 / 31) < 1e-9
    assert abs(w1[2] - 9 / 31) < 1e-9
    assert abs(w1[6] - 3 / 31) < 1e-9
    assert abs(w1[18] - 1 / 31) < 1e-9
    # HD1 decays faster than HD2: more weight on h=1, less on h=18
    assert w1[1] > w2[1] and w1[18] < w2[18]
    # monotonic decay in h for both variants
    assert w1[1] > w1[2] > w1[6] > w1[18]
    assert w2[1] > w2[2] > w2[6] > w2[18]


def test_blend_synthetic_hand_checked():
    idx = pd.date_range("2021-09-24", periods=4, freq="4h", tz="UTC")
    cols = ["BTCUSDT", "ETHUSDT"]
    per = {h: pd.DataFrame(float(h), index=idx, columns=cols) for h in (1, 2, 6, 18)}
    b1 = dr.blend_members(per, "HD1")
    # hand-check: 18/31*1 + 9/31*2 + 3/31*6 + 1/31*18 = (18+18+18+18)/31 = 72/31
    assert abs(float(b1.iloc[0, 0]) - 72 / 31) < 1e-9
    b2 = dr.blend_members(per, "HD2")
    w2 = dr.decay_weights("HD2")
    expect = sum(w2[h] * h for h in (1, 2, 6, 18))
    assert abs(float(b2.iloc[0, 0]) - expect) < 1e-9


def test_relabel_y_formula_and_truncation():
    # 12 bars, constant vol, linearly rising opens: hand-check h=1 label at row 0
    n = 12
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    o = 100.0 * (1.001 ** np.arange(n))
    panel = pd.DataFrame({"t": list(t) * 1, "sym": "BTCUSDT",
                          "open": o, "vol42": np.full(n, 0.01)})
    panel["y"] = np.nan
    out = relabel_y(panel, 1)
    # y[0] = log(o[2]/o[1]) / (0.01*sqrt(1)) = log(1.001)/0.01
    expect = float(np.log(o[2] / o[1]) / 0.01)
    assert abs(float(out.loc[0, "y"]) - expect) < 1e-12
    # tail rows without realised forward are NaN: last 1+h rows (t+1+h beyond end)
    assert bool(pd.isna(out.loc[n - 1, "y"]))
    assert bool(pd.isna(out.loc[n - 2, "y"]))
    # truncation invariance: dropping the last bar does not change earlier labels
    # (labels use only rows <= t+1+h, never future beyond the realised forward)
    short = panel.iloc[: n - 1].copy()
    out_s = relabel_y(short, 1)
    assert abs(float(out_s.loc[0, "y"]) - expect) < 1e-12


def test_bear_and_exposure_scale_causal():
    idx = pd.date_range("2021-09-24", periods=8, freq="4h", tz="UTC")
    ref = pd.DataFrame(1.0, index=idx, columns=["BTCUSDT"])
    var = pd.DataFrame(2.0, index=idx, columns=["BTCUSDT"])
    anchors = [pd.Timestamp("2021-09-24", tz="UTC")]
    s = dr.exposure_scale(ref, var, idx, anchors)
    assert abs(list(s.values())[0] - 2.0) < 1e-12
    cc = dr.apply_exposure_control(ref, s, anchors)
    assert abs(float(cc.iloc[0, 0]) - 2.0) < 1e-12
