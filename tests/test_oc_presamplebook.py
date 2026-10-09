"""oc_presamplebook tests: label math (hand-checked), clip/turnover book math,
block-bootstrap shape, train/test embargo truncation on real artefacts, and
TV-feature append-causality (future bars must not change past rows)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_presamplebook"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PB = _load("oc_presamplebook_mod", OC / "presamplebook.py")
MT = _load("oc_presamplebook_metrics", OC / "metrics.py")


def _const_trend(n=120, g=0.001, start=100.0):
    """Constant log step g: closes/opens = start*exp(g*i); vol42 == 0."""
    t = pd.date_range("2019-01-01", periods=n, freq="4h", tz="UTC")
    px = start * np.exp(g * np.arange(n))
    return pd.DataFrame({"open_time": t, "open": px, "high": px * 1.001,
                         "low": px * 0.999, "close": px,
                         "volume": np.full(n, 10.0)})


def test_label_constant_trend_clips():
    # fwd[i] = 42g (same sign as g), vol42 == 0 -> +/-inf -> clipped to +/-4.
    seg = PB.add_label(_const_trend(g=0.001))
    assert seg["label"].iloc[:42].isna().all()  # vol warm-up + forward edge
    assert seg["label"].iloc[42] == pytest.approx(4.0)
    seg_dn = PB.add_label(_const_trend(g=-0.001))
    assert seg_dn["label"].iloc[42] == pytest.approx(-4.0)
    # hand-check one interior forward return: row 50 uses o[51], o[93]
    o = seg["open"].to_numpy()
    expect = np.log(o[50 + 43] / o[50 + 1])
    assert expect == pytest.approx(42 * 0.001, rel=1e-9)
    assert np.isfinite(expect) and seg["label"].iloc[50] == pytest.approx(4.0)


def test_label_uses_next_open_not_close():
    # Break open != close: label must follow OPENS o[i+1], o[i+43].
    n = 120
    t = pd.date_range("2019-01-01", periods=n, freq="4h", tz="UTC")
    o = 100.0 + np.arange(n)  # linear opens
    c = o * 1.05  # closes differ -> vol from closes, direction from opens
    seg = pd.DataFrame({"open_time": t, "open": o, "high": o + 1,
                        "low": o - 1, "close": c,
                        "volume": np.full(n, 5.0)})
    out = PB.add_label(seg)
    i = 60
    fwd = np.log(o[i + 43] / o[i + 1])
    r1 = pd.Series(np.log(c)).diff()
    vol = r1.rolling(42).std().iloc[i]
    assert out["label"].iloc[i] == pytest.approx(
        float(np.clip(fwd / (vol * np.sqrt(42)), -4, 4)))


def test_diag_book_hand_checked():
    # 2 coins x 3 bars, s = 2.0; values worked out by hand in PLAN terms.
    t = pd.date_range("2020-01-01", periods=3, freq="4h", tz="UTC")
    df = pd.DataFrame({
        "open_time": list(t) * 2,
        "sym": ["A"] * 3 + ["B"] * 3,
        "pred": [1.0, 2.0, -4.0, 0.0, -2.0, 2.0],
        "r_next": [0.01, 0.02, -0.01, 0.03, -0.01, 0.02],
    })
    got = MT.diag_book(df, 2.0)
    a = [0.5 * 0.01 - 0.0002 * 0.5, 1.0 * 0.02 - 0.0002 * 0.5,
         -1.0 * -0.01 - 0.0002 * 2.0]
    b = [0.0 * 0.03 - 0.0, -1.0 * -0.01 - 0.0002 * 1.0,
         1.0 * 0.02 - 0.0002 * 2.0]
    per = [(x + y) / 2 for x, y in zip(a, b)]
    eq = (1 + per[0]) * (1 + per[1]) * (1 + per[2])
    assert got["end_equity"] == pytest.approx(eq, rel=1e-4)  # stored rounded to 4dp
    assert got["n_bars"] == 3 and got["n_coin_bars"] == 6
    assert got["turnover_units"] == pytest.approx(0.5 + 0.5 + 2.0 + 0 + 1.0 + 2.0)
    ndays = 0.5
    assert got["monthly_pct"] == pytest.approx(
        100 * (eq ** (30.4375 / ndays) - 1), rel=1e-4)  # stored rounded to 3dp


def test_block_ci_shape_and_bounds():
    rng = np.random.default_rng(0)
    n = 300
    t = pd.date_range("2021-01-01", periods=n // 2, freq="4h", tz="UTC")
    df = pd.DataFrame({"open_time": np.repeat(t, 2),
                       "pred": rng.normal(size=n),
                       "label": rng.normal(size=n)})
    pt, lo, hi, nb = MT.block_ci(df, n_boot=200, seed=0)
    assert nb == 4  # 150 distinct bars -> ceil(150/42)
    for v in (pt, lo, hi):
        assert -1.0 <= v <= 1.0
    assert lo <= hi


def test_real_artefacts_truncation_and_embargo():
    # Every saved test row lies in [A, A+365d) with a realised label; the
    # 2020-03-01 leg is truncated by the 2020-09-30 store end; no test row
    # may have been fittable (train cut = A - 7d - 43*4h < A - 7d).
    for a in PB.ANCHORS:
        A = pd.Timestamp(a, tz="UTC")
        E = A + pd.Timedelta(days=365)
        df = pd.read_csv(OC / f"preds_{a}.csv", parse_dates=["open_time"])
        ts = pd.to_datetime(df["open_time"], utc=True)
        assert (ts >= A).all() and (ts < E).all()
        assert df["label"].notna().all() and df["pred"].notna().all()
        cut = A - pd.Timedelta(days=7) - 43 * pd.Timedelta(hours=4)
        assert cut < A - pd.Timedelta(days=7)
        if a == "2020-03-01":
            assert ts.max() < pd.Timestamp("2020-09-24", tz="UTC")
            assert len(df) < 8760  # truncated year


def test_tv_features_append_causality():
    # Appending future bars must not change already-known feature rows.
    tvm = PB.load_tv()
    n = 400
    t = pd.date_range("2019-01-01", periods=n, freq="4h", tz="UTC")
    rng = np.random.default_rng(1)
    c = 8000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    b = pd.DataFrame({"open_time": t, "open": c, "high": c * 1.005,
                      "low": c * 0.995, "close": c,
                      "volume": np.abs(rng.normal(10, 2, n))})
    x_short = tvm.tv_features(b.iloc[:300]).reset_index(drop=True)
    x_full = tvm.tv_features(b).reset_index(drop=True).iloc[:300]
    pd.testing.assert_frame_equal(x_short, x_full, check_exact=False,
                                  rtol=1e-12, atol=1e-12)
