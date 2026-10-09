"""Tests for oc_kronosbookvol (pre-registered; light, no engine run)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
MOD = HERE.parent / "research/tournament/oc_kronosbookvol/compute_kronosbookvol.py"


def _load():
    spec = importlib.util.spec_from_file_location("kbv_test", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


kbv = _load()
T0 = pd.Timestamp("2022-01-01", tz="UTC")


def _syn_frames():
    Ts = pd.date_range(T0, periods=6, freq="4h", tz="UTC")
    out = {}
    for s in range(4):
        for sym in kbv.MAJORS:
            out[(s, sym)] = pd.DataFrame({
                "T": Ts,
                "vol1": np.array([0.5, 0.6, 0.7, 0.8, 0.9, 1.0]) + 0.01 * s,
                "rng1": np.array([1.5, 1.6, 1.7, 1.8, 1.9, 2.0]),
            })
    ctrl = {}
    for s in range(4):
        for sym in kbv.MAJORS:
            ctrl[(s, sym)] = pd.DataFrame({
                "T": Ts,
                "ratio42": np.array([0.9, 1.0, 1.1, 1.2, 1.3, 1.4]),
            })
    return out, ctrl


def test_clip_mult_handchecked():
    assert kbv.clip_mult(0.6, 0.6) == 1.0
    assert kbv.clip_mult(0.6, 0.3) == 1.4  # 2.0 clipped to HI
    assert kbv.clip_mult(0.6, 1.2) == 0.6  # 0.5 clipped to LO
    assert kbv.clip_mult(0.8, 1.0) == 0.8  # interior, hand-checked 0.8/1.0
    for bad in (float("nan"), 0.0, -1.0, float("inf")):
        assert kbv.clip_mult(0.6, bad) == 1.0
        assert kbv.clip_mult(bad, 0.6) == 1.0
    assert kbv.clip_mult(0.6, 1e-13) == 1.0  # below EPS


def test_feature_at_backward():
    Ts = pd.date_range(T0, periods=3, freq="4h", tz="UTC")
    fr = pd.DataFrame({"T": Ts, "vol1": [10.0, 20.0, 30.0]})
    d = {"k": fr}
    assert kbv.feature_at(d, "k", Ts[1]) == 20.0  # exact match
    assert kbv.feature_at(d, "k", Ts[1] + pd.Timedelta(hours=2)) == 20.0  # between bars
    assert kbv.feature_at(d, "k", Ts[2] + pd.Timedelta(days=30)) == 30.0  # ffill tail
    assert np.isnan(kbv.feature_at(d, "k", Ts[0] - pd.Timedelta(seconds=1)))  # before start


def test_phase_shift_isolation_and_truncation():
    """Phase s sees only shift-s rows with T <= bar open (causality)."""
    kronos, ctrl = _syn_frames()
    med = {("KV1", kbv.ANCH5[0], 0, "BTCUSDT"): 0.6}
    idx = pd.DatetimeIndex([T0 + pd.Timedelta(hours=4 * i) for i in range(6)], tz="UTC")
    before = [kbv.mult_for("BTCUSDT", t, 0, "KV1", kronos, ctrl, med) for t in idx]
    # perturb another shift's features (even to NaN/inf): shift-0 mults unchanged
    kronos[(1, "BTCUSDT")].loc[:, "vol1"] = np.inf
    after = [kbv.mult_for("BTCUSDT", t, 0, "KV1", kronos, ctrl, med) for t in idx]
    assert before == after
    # truncate shift-0 frame at T0+8h: mults at bars <= cut unchanged (causal)
    cut = T0 + pd.Timedelta(hours=8)
    trunc = {k: (v[v["T"] <= cut].reset_index(drop=True) if k == (0, "BTCUSDT") else v)
             for k, v in kronos.items()}
    trunc_after = [kbv.mult_for("BTCUSDT", t, 0, "KV1", trunc, ctrl, med)
                   for t in idx[idx <= cut]]
    assert before[: len(trunc_after)] == trunc_after
    # hand-check one value: median 0.6 / f(T0)=0.5 -> 1.2; /f(T0+4h)=0.6 -> 1.0
    assert before[0] == 1.2 and before[1] == 1.0


def test_anchor_embargo_and_median():
    kronos, ctrl = _syn_frames()
    # anchor 2022-09-24, cutoff 2022-09-17: all synthetic rows (Jan 2022) are training
    med = kbv.training_medians(kronos, ctrl)
    v = kronos[(0, "BTCUSDT")]["vol1"].to_numpy()
    assert med[("KV1", "2022-09-24", 0, "BTCUSDT")] == float(np.median(v))
    # a row inside the embargo (T >= cutoff) must not move the median
    late = pd.DataFrame({"T": [pd.Timestamp("2022-09-20", tz="UTC")],
                         "vol1": [999.0], "rng1": [999.0]})
    kronos2 = dict(kronos)
    kronos2[(0, "BTCUSDT")] = pd.concat([kronos[(0, "BTCUSDT")], late], ignore_index=True)
    med2 = kbv.training_medians(kronos2, ctrl)
    assert med2[("KV1", "2022-09-24", 0, "BTCUSDT")] == med[("KV1", "2022-09-24", 0, "BTCUSDT")]


def test_book_scaling_both_sides():
    """Scaled books = base * m elementwise: sign preserved, both legs scaled."""
    base = pd.DataFrame({"BTCUSDT": [0.5, -0.25, 0.0], "ETHUSDT": [-1.0, 0.75, 0.1]})
    m = pd.DataFrame({"BTCUSDT": [1.4, 0.6, 1.0], "ETHUSDT": [0.6, 1.4, 1.0]})
    scaled = base * m
    assert scaled.loc[0, "BTCUSDT"] == 0.7  # long x 1.4
    assert scaled.loc[1, "BTCUSDT"] == -0.15  # short x 0.6 (shorts also scaled)
    assert scaled.loc[2, "BTCUSDT"] == 0.0
    assert (np.sign(scaled.to_numpy()) == np.sign(base.to_numpy())).all()


def test_build_mult_frame_matches_mult_for():
    """Vectorized engine path agrees with the proven single-point path."""
    kronos, ctrl = _syn_frames()
    Ts = kronos[(0, "BTCUSDT")]["T"]
    med = {("KV1", kbv.ANCH5[0], 0, s): 0.6 for s in kbv.MAJORS}
    idx = pd.DatetimeIndex(Ts, tz="UTC")
    frame = kbv.build_mult_frame(idx, ["BTCUSDT", "ETHUSDT"], 0, "KV1", kronos, ctrl, med)
    for t in idx:
        for sym in ("BTCUSDT", "ETHUSDT"):
            med_sym = {("KV1", kbv.ANCH5[0], 0, sym): 0.6}
            want = kbv.mult_for(sym, t, 0, "KV1", kronos, ctrl,
                                {**med, ("KV1", kbv.ANCH5[0], 0, sym): 0.6})
            assert frame.loc[t, sym] == want, (t, sym)


def test_real_kronos_groups_complete():
    df = pd.read_parquet(kbv.KRONOS_PATH, columns=["sym", "shift"])
    groups = df.groupby(["shift", "sym"]).size()
    assert len(groups) == 20
    assert set(df["sym"].unique()) == set(kbv.MAJORS)
