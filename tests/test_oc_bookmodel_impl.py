"""Tests for oc_bookmodel_impl C1/C2 builders (fast, local, no training on the last year)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
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


C = _load("ocbm_common_t", IMPL / "common_impl.py")


def test_embargo_is_7d_and_ge_horizon():
    assert C.EMBARGO_DAYS == 7
    assert C.EMBARGO_DAYS * 6 >= C.H_MAX  # 7d in 4h bars >= max horizon 42
    for a in list(C.DEV_ANCHORS) + [C.FINAL_ANCHOR]:
        co = C.cutoff_for(a)
        assert co == pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=7)


def test_dev_anchors_are_2021_2024_and_final_scored_once():
    assert tuple(C.DEV_ANCHORS) == ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")
    assert C.FINAL_ANCHOR == "2025-09-24"


def test_train_mask_requires_label_realised_before_cutoff():
    t = pd.date_range("2021-01-01", periods=200, freq="4h", tz="UTC")
    panel = pd.DataFrame({"t": list(t) * 2, "sym": ["BTCUSDT"] * 200 + ["ETHUSDT"] * 200,
                          "y3": 0.1, "y18": 0.1, "y42": 0.1})
    cutoff = t[150]
    m = C.train_mask(panel, cutoff, (3, 18, 42))
    # rows with t+(42+1)*4h >= cutoff must be excluded
    late = panel["t"] + pd.Timedelta(hours=4 * 43) >= cutoff
    assert not (m & late).any()
    assert m.any()


def test_member_format_matches_deployed():
    ref = pd.read_parquet(C.CACHE / "member_A_O1_orders.parquet")
    assert list(ref.columns) == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert ref.index.name == "t"
    W = pd.DataFrame(np.random.randn(10, 5), columns=list(ref.columns),
                     index=pd.date_range("2021-09-24", periods=10, freq="4h", tz="UTC"))
    W.index.name = "t"
    out = C.format_member(W)
    assert list(out.columns) == list(ref.columns)
    assert out.index.name == "t"
    assert str(out.index.dtype) == str(ref.index.dtype)


def test_truncation_causality_on_tv_features():
    stack = C.load_stack()
    _, _, _, _, tvm, _, _ = stack
    v92 = C._load("ocbm_v92_t", C.RD / "v92/v92_pooled_hgb_vt.py")
    b, _, _ = v92.load_asset("BTCUSDT")
    b = b.iloc[2000:2600].reset_index(drop=True)  # small slice, real bars

    def feat(bb):
        return tvm.tv_features(bb)

    res = C.truncation_check(feat, b, n_check=3)
    assert res["pass"], res
    assert res["max_abs_diff"] == 0.0


def test_truncation_causality_on_rank_target_inputs():
    # rank uses only realised y42 at each t; dropping last 3 bars must not change earlier ranks
    t = pd.date_range("2021-01-01", periods=20, freq="4h", tz="UTC")
    rows = []
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        rows.append(pd.DataFrame({"t": t, "sym": s, "y42": np.arange(20, dtype=float)}))
    panel = pd.concat(rows, ignore_index=True)
    c2 = _load("ocbm_c2_t", IMPL / "c2_rank_calibrated.py")
    full = c2.rank_target(panel)
    trunc = c2.rank_target(panel[panel["t"] < t[-3]].copy())
    m = full.set_index(["t", "sym"])["rank42"].unstack()
    m2 = trunc.set_index(["t", "sym"])["rank42"].unstack()
    pd.testing.assert_frame_equal(m.iloc[: len(m2)], m2)


def test_c1_smoke_cli(tmp_path=None):
    out = Path("artifacts/research/engine_real")  # smoke without --out writes nothing
    r = subprocess.run([sys.executable, str(IMPL / "c1_pooled_tvflow.py"), "--smoke"],
                       capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-3000:]
    assert "C1 smoke" in r.stdout


def test_c2_smoke_cli():
    r = subprocess.run([sys.executable, str(IMPL / "c2_rank_calibrated.py"), "--smoke"],
                       capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-3000:]
    assert "C2 smoke" in r.stdout
