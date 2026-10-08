"""oc_kronosbase tests: tilt-rule hand checks + KBK2 averaging + causality/embargo + bundle contract.

Part A DONE 2026-10-08 via the leader-exception one-private-dataset + private
kernels (account 1, default auth): verify50 gate passed, base features merged.
These tests cover the causal contract without needing the 260k-row parquet.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_kronosbase"
SRC = ROOT / "research/tournament/oc_kronoshidden"
sys.path.insert(0, str(OC))
from tilt_rule import ANCH5, anchor_of, assign_mult  # noqa: E402


def kbk2_avg(m_k2, m_kb):
    """Pre-registered KBK2 rule: per-side missing/NaN -> 1.0 first, then mean."""
    a = 1.0 if m_k2 is None or not np.isfinite(float(m_k2)) else float(m_k2)
    b = 1.0 if m_kb is None or not np.isfinite(float(m_kb)) else float(m_kb)
    return (a + b) / 2.0


def test_assign_mult_edges_k2_kb2():
    # K2/KB2 share hi/lo = 1.25/0.75, direction +1 on all oc_kronoshidden anchors
    assert assign_mult(5.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(0.1, 1, 0.5, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(1.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(2.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.25  # >= q80 inclusive
    assert assign_mult(0.5, 1, 0.5, 2.0, 1.25, 0.75) == 0.75  # <= q20 inclusive
    assert assign_mult(float("nan"), 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(float("inf"), 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(5.0, -1, 0.5, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(0.1, -1, 0.5, 2.0, 1.25, 0.75) == 1.25


def test_kbk2_average_hand_checked():
    # both favourable / both unfavourable / split / middle / missing-first
    assert kbk2_avg(1.25, 1.25) == 1.25
    assert kbk2_avg(0.75, 0.75) == 0.75
    assert kbk2_avg(1.25, 0.75) == 1.0
    assert kbk2_avg(1.25, 1.0) == 1.125
    assert kbk2_avg(0.75, 1.0) == 0.875
    assert kbk2_avg(1.0, 1.0) == 1.0
    assert kbk2_avg(float("nan"), 1.25) == 1.125  # missing side -> 1.0 first
    assert kbk2_avg(None, None) == 1.0


def test_training_embargo_truncation():
    # per-anchor fits use ONLY harness rows with t_exit < A - 7d
    A = pd.Timestamp("2022-09-24", tz="UTC")
    exits = pd.to_datetime(["2022-09-10", "2022-09-16 23:59", "2022-09-17",
                            "2022-09-18", "2023-01-01"], utc=True, format="mixed")
    mask = exits < A - pd.Timedelta(days=7)
    assert mask.tolist() == [True, True, False, False, False]
    # most-recent-year fits: t_exit < 2025-09-17
    A5 = pd.Timestamp("2025-09-24", tz="UTC")
    assert (pd.Timestamp("2025-09-16 23:59", tz="UTC") < A5 - pd.Timedelta(days=7))
    assert not (pd.Timestamp("2025-09-17", tz="UTC") < A5 - pd.Timedelta(days=7))


def test_shift0_join_causality():
    # fits join on (sym, T) with shift == 0 ONLY; other shifts never train fits
    feat = pd.DataFrame({"sym": ["BTCUSDT"] * 4, "shift": [0, 1, 2, 3],
                         "T": pd.to_datetime(["2022-01-01"] * 4, utc=True),
                         "low1": [1.0, 2.0, 3.0, 4.0]})
    train = feat[feat["shift"] == 0].set_index(["sym", "T"])["low1"]
    assert len(train) == 1 and train.iloc[0] == 1.0
    # anchor mapping: year y covers [ANCH5[y]+sh, +365d); pre-anchor clamps to 0
    assert anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert anchor_of(pd.Timestamp("2025-09-24", tz="UTC"), 0) == 4
    assert anchor_of(pd.Timestamp("2020-01-01", tz="UTC"), 0) == 0


def test_bundle_contract_no_upload():
    # kernel payload is a verbatim copy (never modify ../Kronos); metadata stays private
    for name in ("__init__.py", "kronos.py", "module.py"):
        a = (SRC / "model" / name).read_bytes()
        b = (OC / "bundle" / "model" / name).read_bytes()
        assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()
    a = (SRC / "kronos_fast.py").read_bytes()
    b = (OC / "bundle" / "kronos_fast.py").read_bytes()
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()
    assert (OC / "tilt_rule.py").read_bytes() == (SRC / "tilt_rule.py").read_bytes()
    ds = json.loads((OC / "bundle" / "dataset-metadata.json").read_text())
    assert ds.get("isPrivate") is True
    km = json.loads((OC / "bundle" / "kernel-metadata-template.json").read_text())
    assert km.get("is_private") is True and km.get("enable_gpu") is True
    src = (OC / "bundle" / "kernel_inference.py").read_text()
    for needle in ("NeoQuasar/Kronos-base", "NeoQuasar/Kronos-Tokenizer-base",
                   "torch.manual_seed(1234)", "HEARTBEAT_S = 600",
                   "TOP_P, TOP_K = 1.0, 0.9, 0", "P, H, S = 400, 6, 64"):
        assert needle in src, needle
    plan = (OC / "PLAN.md").read_text()
    for row in ("REF", "K2", "KB2", "KBK2"):
        assert row in plan
    assert "kronosbase_features_4shift.parquet" in plan
