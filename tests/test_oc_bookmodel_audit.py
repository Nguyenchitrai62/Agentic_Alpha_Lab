"""Blind pre-run audit tests for oc_bookmodel_impl C1/C2 (no Kaggle, no edits of audited code).

Scope: assignment docs/opencode/OPENCODE_W_oc_bookmodel_audit.md.
These tests pin the audit properties WITHOUT training on the last year and
without computing forward returns for dates >= 2025-09-24:
- truncation causality on 3 dev anchors (TV indicators + order-level whale flow)
- label-window asserts (horizons 3/18/42 realised before anchor-7d; C2 rank mask)
- quarterly cutoffs respect the same embargo
- alt universe fixed Dec-2020 (no survivorship additions)
- kpack bundles carry no data/credentials and match the audited sources
- 2025-09-24 is not used by any training/selection code path
- KNOWN BUG (FAIL F1): C2's feature list currently CONTAINS the rank42 label
  (common_impl.feature_list only excludes y*-prefixed columns). The test below
  pins the buggy behaviour so the failure is explicit; after the fix, flip it
  to assert "rank42" not in feats.
"""
from __future__ import annotations

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


C = _load("ocbm_audit_common", IMPL / "common_impl.py")
C2 = _load("ocbm_audit_c2", IMPL / "c2_rank_calibrated.py")

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
    import filecmp
    for cand, files in (("kpack_C1", ("c1_pooled_tvflow.py", "common_impl.py")),
                        ("kpack_C2", ("c2_rank_calibrated.py", "common_impl.py"))):
        kd = IMPL / cand
        for f in files:
            assert filecmp.cmp(IMPL / f, kd / f, shallow=False), (cand, f)
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
    for mod, entry in (("c1_pooled_tvflow.py", "member_C1_"), ("c2_rank_calibrated.py", "member_C2_")):
        src = (IMPL / mod).read_text()
        assert "C.DEV_ANCHORS" in src
        # full writer loops dev anchors only; the only FINAL_ANCHOR training
        # reference is the dead `pass` loop in C1 (no fit call inside it)
        assert src.count("FINAL_ANCHOR") <= 2, (mod, src.count("FINAL_ANCHOR"))


def test_c2_rank42_currently_leaks_into_features():
    """FAIL F1 pin: feature_list INCLUDES the rank42 label (must be fixed pre-Kaggle).

    common_impl.py:251-256 excludes only y*-prefixed columns, so the C2 label
    rank42 (c2_rank_calibrated.py:79) is returned as a training feature and the
    HGB ranker (c2_rank_calibrated.py:149) trains on its own target.
    After the fix, change this test to assert "rank42" not in feats.
    """
    panel = pd.DataFrame({c: [1.0] for c in
                          ["y", "t", "open", "sym", "bar", "y42", "rank42", "ret42"]})
    feats = C.feature_list(panel)
    assert "rank42" not in feats  # BUG present -> audit FAIL F1
    assert "y42" not in feats and "y" not in feats
