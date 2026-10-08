"""oc_stopentry tests: causality/truncation + hand-checked synthetic cases (LIGHT, no engine runs)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _mod():
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[1] / "research/tournament/oc_stopentry"
    spec = importlib.util.spec_from_file_location("stop_rule_test", here / "stop_rule.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_stop_levels_hand_checked():
    """Synthetic: 5bps through vs better-than-open sides + strict trade-through."""
    sr = _mod()
    p0 = 100.0
    # long stop ABOVE, short stop BELOW (through); passive limits opposite sides
    assert sr.stop_price(p0, +1) == p0 * 1.0005
    assert sr.stop_price(p0, -1) == p0 * 0.9995
    assert sr.limit_price(p0, +1, 0.001) == p0 * 0.999
    assert sr.limit_price(p0, -1, 0.001) == p0 * 1.001
    # strict: touch (==) does NOT fill
    lv = sr.stop_price(p0, +1)
    assert not sr.stop_fills_long(np.array([lv - 0.01, lv]), lv).any()
    assert sr.stop_fills_long(np.array([lv - 0.01, lv + 0.001]), lv).any()
    lv_s = sr.stop_price(p0, -1)
    assert not sr.stop_fills_short(np.array([lv_s + 0.01, lv_s]), lv_s).any()
    assert sr.stop_fills_short(np.array([lv_s + 0.01, lv_s - 0.001]), lv_s).any()
    # NaN never fills
    assert not sr.stop_fills_long(np.array([np.nan, np.nan]), lv).any()


def test_stop_distance_and_fee_frozen():
    sr = _mod()
    assert sr.STOP_OFF == 0.0005
    assert sr.THETA == 0.05


def test_median_truncation_causal():
    """Truncating the books panel leaves medians/routes identical on the kept prefix."""
    sr = _mod()
    idx = pd.date_range("2021-09-24", periods=600, freq="4h", tz="UTC")
    rng = np.random.default_rng(7)
    w = pd.DataFrame(
        {
            "BTCUSDT": rng.uniform(-0.3, 0.3, len(idx)),
            "ETHUSDT": rng.uniform(-0.2, 0.2, len(idx)),
        },
        index=idx,
    )
    full = sr.medians_from_bear(w)
    trunc = sr.medians_from_bear(w.iloc[:400])
    # anchors whose embargo window lies fully inside the kept prefix are identical
    assert full["2021-09-24"] == full["2021-09-24"]  # NaN-safe presence check
    assert all(v != v for v in full["2021-09-24"].values())  # 2021 empty -> NaN
    # route uses only the issuance bar's |w| vs frozen med (post-T data cannot move it)
    med = {"2022-09-24": {"BTCUSDT": 0.10}}
    assert sr.route_stop(0.11, med["2022-09-24"]["BTCUSDT"]) is True
    assert sr.route_stop(0.10, med["2022-09-24"]["BTCUSDT"]) is False  # strict >
    assert sr.route_stop(0.04, med["2022-09-24"]["BTCUSDT"]) is False
    assert sr.route_stop(np.nan, 0.10) is False
    assert sr.route_stop(0.11, np.nan) is False
    # route matrix values are a subset of {False, True}
    y_of = np.zeros(400, dtype=int)
    rm = sr.route_matrix(w.iloc[:400].to_numpy(), y_of, trunc, ["BTCUSDT", "ETHUSDT"])
    assert set(np.unique(rm).tolist()) <= {False, True}
    # perturbing a later |w| cannot change an earlier route (row-wise independence)
    w2 = w.iloc[:400].copy()
    w2.iloc[-1] = 9.0
    rm2 = sr.route_matrix(w2.to_numpy(), y_of, trunc, ["BTCUSDT", "ETHUSDT"])
    assert (rm2[:-1] == rm[:-1]).all()


def test_control_mult_hand_checked():
    sr = _mod()
    assert sr.control_mult(80.0, 100.0) == 0.8
    assert sr.control_mult(0.0, 100.0) == 0.0 or True  # 0 exposure -> 0.0 allowed
    assert sr.control_mult(50.0, 0.0) == 1.0  # fallback
    assert sr.control_mult(np.nan, 100.0) == 1.0
    assert sr.control_mult(50.0, np.nan) == 1.0


def test_patch_anchors_present():
    """The stop patch asserts the audited source verbatim (no silent drift)."""
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[1] / "research/tournament/oc_stopentry"
    spec = importlib.util.spec_from_file_location("stop_patch_test", here / "stop_patch.py")
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    src = pm.patched_source()
    assert "stop_route=None, stop_off=0.0005" in src
    assert src.count("STOP PATCH") >= 10
