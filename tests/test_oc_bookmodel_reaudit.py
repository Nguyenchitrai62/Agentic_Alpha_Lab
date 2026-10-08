"""Blind re-audit tests for oc_bookmodel_impl C1/C2 after the REPORT.md fixes.

Re-audit of docs/opencode/OPENCODE_W_oc_bookmodel_reaudit.md: verify each
previous finding (F1/W1/W2/N1) is fixed and re-check checks (1)-(7)
independently, WITHOUT training on the last year and without computing forward
returns for dates >= 2025-09-24.
"""
from __future__ import annotations

import filecmp
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / "research/tournament/oc_bookmodel_impl"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("ocbm_reaudit_common", IMPL / "common_impl.py")
C2 = _load("ocbm_reaudit_c2", IMPL / "c2_rank_calibrated.py")

ANCHORS_3 = ("2021-09-24", "2022-09-24", "2023-09-24")


def _btc_bars():
    stack = C.load_stack()
    v92 = stack[0]
    b, _, _ = v92.load_asset("BTCUSDT")
    return stack, b


def test_tv_truncation_three_anchors():
    stack, b = _btc_bars()
    tvm = stack[4]
    ot = pd.DatetimeIndex(b["open_time"])
    for a in ANCHORS_3:
        anchor = pd.Timestamp(a, tz="UTC")
        idx = int((ot >= anchor).argmax())
        bb = b.iloc[max(0, idx - 500): idx + 100].reset_index(drop=True)
        res = C.truncation_check(lambda x: tvm.tv_features(x), bb, n_check=3)
        assert res["pass"] and res["max_abs_diff"] == 0.0, (a, res)


def test_orderflow_truncation_three_anchors():
    stack, b = _btc_bars()
    flo_o = stack[6]
    assert str(flo_o.D) == str(Path("data/raw/aggflow_20260928_orders")), flo_o.D
    ot = pd.DatetimeIndex(b["open_time"])
    for a in ANCHORS_3:
        anchor = pd.Timestamp(a, tz="UTC")
        idx = int((ot >= anchor).argmax())
        t = ot[max(0, idx - 500): idx + 100]
        full = flo_o.flow_features("BTCUSDT", t)
        trunc = flo_o.flow_features("BTCUSDT", t[:-3])
        a1 = full.iloc[: len(trunc)].to_numpy(float)
        b1 = trunc.to_numpy(float)
        both = np.isnan(a1) & np.isnan(b1)
        d = np.abs(a1 - b1)
        d[both] = 0.0
        d[np.isnan(d)] = np.inf
        assert float(np.max(d)) == 0.0, a


def test_label_window_c1_horizons_all_anchors():
    t = pd.date_range("2021-01-01", periods=400, freq="4h", tz="UTC")
    panel = pd.DataFrame({
        "t": list(t) * 2,
        "sym": ["BTCUSDT"] * 400 + ["ETHUSDT"] * 400,
        "y3": 0.1, "y18": 0.1, "y42": 0.1,
    })
    for a in C.DEV_ANCHORS:
        cutoff = C.cutoff_for(a)
        assert cutoff == pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=7)
        m = C.train_mask(panel, cutoff, C.H_C1)
        assert m.any()
        late = panel["t"] + pd.Timedelta(hours=4 * (42 + 1)) >= cutoff
        assert not (m & late).any(), a
        early = panel["t"] + pd.Timedelta(hours=4 * (3 + 1)) >= cutoff
        assert not (m & early).any(), a


def test_label_window_c2_rank_mask():
    t = pd.date_range("2021-01-01", periods=200, freq="4h", tz="UTC")
    rows = []
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        rows.append(pd.DataFrame({"t": t, "sym": s, "y42": 0.1}))
    panel = pd.concat(rows, ignore_index=True)
    panel = C2.rank_target(panel)
    assert panel["rank42"].notna().all()
    cutoff = C.cutoff_for("2022-09-24")
    base = (panel["t"] < cutoff) & panel["y42"].notna() & panel["rank42"].notna()
    base &= panel["t"] + pd.Timedelta(hours=4 * (42 + 1)) < cutoff
    assert base.any()
    late = panel["t"] + pd.Timedelta(hours=4 * 43) >= cutoff
    assert not (base & late).any()


def test_quarterly_cutoffs_match_embargo():
    for a in C.DEV_ANCHORS:
        starts = C.quarter_starts(a)
        assert len(starts) == 4
        assert starts[0] == pd.Timestamp(a, tz="UTC")
        for q0 in starts:
            assert q0 - pd.Timedelta(days=C.EMBARGO_DAYS) == q0 - pd.Timedelta(days=7)
        end = C.quarter_end(a)
        assert end == pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365)


def test_alt_universe_fixed_dec2020():
    uni = C.alt_universe()
    assert len(uni) == 72, len(uni)
    for major in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        assert major not in uni
    v = pd.read_csv(ROOT / "data/raw/um_universe_20260930/volume_2020_12.csv")
    assert set(uni) <= set(v.symbol)


def test_kpack_bundles_clean_and_in_sync():
    for cand, files in (("kpack_C1", ("c1_pooled_tvflow.py", "common_impl.py")),
                        ("kpack_C2", ("c2_rank_calibrated.py", "common_impl.py"))):
        kd = IMPL / cand
        for f in files:
            # normalized-text sync: the kpack copies were written with CRLF
            # line endings (bulk copy 2026-10-06 14:03) while the sources are
            # LF, so byte-exact filecmp false-fails; any logic change still
            # fails this comparison. See ops_snapshottests/REPORT.md.
            a = (IMPL / f).read_text(encoding="utf-8").splitlines()
            b = (kd / f).read_text(encoding="utf-8").splitlines()
            assert a == b, (cand, f)
        names = {p.name for p in kd.iterdir()}
        assert not any(n.endswith((".parquet", ".csv", ".pkl", ".npz")) for n in names), names
        blob = "\n".join((kd / f).read_text() for f in kd.iterdir() if f.is_file())
        for needle in ("api_key", "API_KEY", "secret", "SECRET", "BEGIN PRIVATE", "kaggle.json"):
            assert needle not in blob, needle
        meta = json.loads((kd / "kernel-metadata.json.template").read_text())
        assert meta["is_private"] is True and meta["enable_gpu"] is False
        assert meta["enable_internet"] is False


def test_final_year_not_in_training_paths():
    assert tuple(C.DEV_ANCHORS) == ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")
    assert C.FINAL_ANCHOR == "2025-09-24"
    for mod in ("c1_pooled_tvflow.py", "c2_rank_calibrated.py"):
        src = (IMPL / mod).read_text()
        assert "C.DEV_ANCHORS" in src
        assert "FINAL_ANCHOR" not in src, mod


def test_f1_fixed_rank42_pred_excluded_from_features():
    """F1 re-audit: rank42/pred must NOT be features (old pin asserted the bug)."""
    panel = pd.DataFrame({
        "ret42": [0.1, 0.2], "tv_st_dir": [1.0, -1.0],
        "fl_big_imb6": [0.3, -0.3], "xs_ret42": [0.0, 0.1],
        "tbr_6": [0.01, -0.01], "asset": [0, 1],
        "y": [0.1, 0.2], "y3": [0.1, 0.2], "y18": [0.1, 0.2],
        "y42": [0.1, 0.2], "rank42": [0.5, -0.5], "pred": [0.3, -0.3],
        "future_leak": [9.0, 9.0], "t": pd.date_range("2021-01-01", periods=2, tz="UTC"),
        "open": [1.0, 1.0], "sym": ["BTCUSDT"] * 2, "bar": [0, 1],
    })
    feats = C.feature_list(panel)
    for leaked in ("y", "y3", "y18", "y42", "rank42", "pred", "future_leak",
                   "t", "open", "sym", "bar"):
        assert leaked not in feats, leaked
    for kept in ("ret42", "tv_st_dir", "fl_big_imb6", "xs_ret42", "tbr_6", "asset"):
        assert kept in feats, kept
    assert "rank42" not in C.FEATURE_ALLOWLIST and "pred" not in C.FEATURE_ALLOWLIST
    feats_b = C.feature_list(panel, exclude_flow_for_B=True)
    assert "fl_big_imb6" not in feats_b and "ret42" in feats_b


def test_w1w2_fixed_time_last_calibration_no_sampling_denylist():
    """W1/W2 re-audit: time-ordered calibration split, no random sampling, denylist."""
    assert hasattr(C2, "split_fit_cal")
    src = (IMPL / "c2_rank_calibrated.py").read_text()
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert ".sample(n=" not in code and "tr.sample(" not in code
    t = pd.date_range("2020-01-01", periods=500, freq="4h", tz="UTC")
    rng = np.random.RandomState(0)
    order = rng.permutation(len(t))
    tr = pd.DataFrame({"t": t[order], "v": rng.randn(len(t))})
    fit, cal = C2.split_fit_cal(tr)
    assert len(fit) == 400 and len(cal) == 100
    assert fit["t"].max() <= cal["t"].min()
    assert set(cal["t"]) == set(sorted(t)[-100:])
    fit2, cal2 = C2.split_fit_cal(tr)
    pd.testing.assert_frame_equal(fit.reset_index(drop=True), fit2.reset_index(drop=True))
    pd.testing.assert_frame_equal(cal.reset_index(drop=True), cal2.reset_index(drop=True))
    assert "rank42" in C.LABEL_DENY_EXACT and "pred" in C.LABEL_DENY_EXACT
    assert not [c for c in C.FEATURE_ALLOWLIST if C._is_denied(c)]
