"""Tests for round75 track B streaming parity. RESEARCH ONLY, frozen policy.

Covers: bit-identical parity vs the frozen batch reference, prefix invariance,
restart/resume exactly-once, duplicate/out-of-order/missing/stale bar handling,
deterministic alert IDs, and causal HTF/guard/choose audits. No tuning, no
live paths, no cloud.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import opencode_r75_streaming as S  # noqa: E402
import opencode_r75_parity as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
K_PREFIX = 2000


@pytest.fixture(scope="module")
def bundle():
    policy = S.load_policy(ROOT / "configs/opencode_r75_policy.json")
    candles, decisions, part, didx, preds, ds_cfg = S.load_inputs(policy)
    _, control_exits = S.batch_control_reference(policy, candles, ds_cfg)
    batch_ref = pd.read_parquet(ROOT / policy["reference_signals"]["path"])
    return {"policy": policy, "candles": candles, "part": part,
            "preds": preds, "ds_cfg": ds_cfg, "control_exits": control_exits,
            "batch_ref": batch_ref}


@pytest.fixture(scope="module")
def full_stream(bundle):
    signals, replay = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"])
    return signals, replay


def test_policy_bundle_frozen(bundle):
    p = bundle["policy"]
    assert p["policy_id"] == "opencode_r75_confirmed_dd_guard"
    assert p["frozen"] is True
    for key, tagged in p["source_shas"].items():
        expect, rel = tagged.split(":", 1)
        assert S.sha256_file(ROOT / rel) == expect, f"source changed: {rel}"


def test_reference_parity_bit_identical(bundle, full_stream):
    signals, _ = full_stream
    rep = P.compare_signal_frames(bundle["batch_ref"], signals)
    assert rep["n_stream"] == rep["n_batch"] == 94
    assert rep["all_bit_exact"] is True, rep["max_abs_diff"]


def test_control_regeneration_parity(bundle):
    ctrl_batch = pd.read_parquet(
        ROOT / "artifacts/research/opencode_v15_mapensemble/iso4_only_1x/signals.parquet")
    ctrl_stream, _ = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"], vote=S.VOTE_ISO4_ONLY)
    rep = P.compare_signal_frames(ctrl_batch, ctrl_stream)
    assert rep["all_bit_exact"] is True, rep["max_abs_diff"]


def test_prefix_invariance(bundle, full_stream):
    signals, _ = full_stream
    pre, _ = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"], end_row=K_PREFIX)
    head = signals.iloc[:len(pre)].reset_index(drop=True)
    pre = pre.reset_index(drop=True)
    assert (head["bar_index"].to_numpy() == pre["bar_index"].to_numpy()).all()
    assert (head["direction"].to_numpy() == pre["direction"].to_numpy()).all()
    assert (head["leverage"].to_numpy() == pre["leverage"].to_numpy()).all()


def test_restart_resume_bit_identical(bundle, full_stream, tmp_path):
    signals, _ = full_stream
    _, replay = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"], end_row=K_PREFIX)
    snap_path = tmp_path / "r75_state.json"
    replay.save_state(snap_path)
    snap = json.loads(snap_path.read_text())
    resumed_signals, _ = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"], restore_from=snap)
    assert (resumed_signals["bar_index"].to_numpy()
            == signals["bar_index"].to_numpy()).all()
    assert (resumed_signals["leverage"].to_numpy()
            == signals["leverage"].to_numpy()).all()
    assert len(resumed_signals) == len(signals)


def test_state_restore_refuses_mismatch(bundle, tmp_path):
    _, replay = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"], end_row=10)
    snap_path = tmp_path / "r75_state.json"
    replay.save_state(snap_path)
    snap = json.loads(snap_path.read_text())
    bad = dict(snap, n_bars=snap["n_bars"] + 1)
    fresh = S.R75StreamReplay(bundle["policy"], bundle["candles"], bundle["part"],
                              bundle["preds"], bundle["ds_cfg"],
                              bundle["control_exits"])
    with pytest.raises(ValueError):
        fresh.restore_state(bad)
    bad2 = dict(snap, policy_id="something-else")
    with pytest.raises(ValueError):
        fresh.restore_state(bad2)


def _fresh(bundle):
    return S.R75StreamReplay(bundle["policy"], bundle["candles"], bundle["part"],
                             bundle["preds"], bundle["ds_cfg"],
                             bundle["control_exits"])


def test_duplicate_out_of_order_stale_refused(bundle):
    r = _fresh(bundle)
    r.on_decision(0)
    with pytest.raises((ValueError, AssertionError)):
        r.on_decision(0)  # duplicate replay of the same row
    # out-of-order/stale at BAR level: rows fed in an order whose bars go back
    swapped = bundle["part"].iloc[[5, 3]].reset_index(drop=True)
    r2 = S.R75StreamReplay(bundle["policy"], bundle["candles"], swapped,
                           {m: bundle["preds"][m][[5, 3]] for m in bundle["preds"]},
                           bundle["ds_cfg"], bundle["control_exits"])
    r2.on_decision(0)
    with pytest.raises(ValueError):
        r2.on_decision(1)  # bar goes backwards -> stale/out-of-order refused


def test_sequential_gap_refused_not_silently_skipped(bundle):
    r = _fresh(bundle)
    with pytest.raises(AssertionError):
        r.on_decision(5)  # gap: rows 0..4 missing -> fail-closed, never skip


def test_unclosed_bar_refused(bundle):
    tampered = bundle["candles"].copy()
    b0 = int(bundle["part"].iloc[0]["bar_index"])
    tampered.at[tampered.index[b0], "close_time"] = \
        pd.Timestamp("2030-01-01T00:00:00+00:00")
    r = S.R75StreamReplay(bundle["policy"], tampered, bundle["part"],
                          bundle["preds"], bundle["ds_cfg"],
                          bundle["control_exits"])
    with pytest.raises(ValueError):
        r.on_decision(0)


def test_alert_ids_deterministic(bundle):
    _, r1 = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"], end_row=500)
    _, r2 = S.run_stream(
        bundle["policy"], bundle["candles"], bundle["part"], bundle["preds"],
        bundle["ds_cfg"], bundle["control_exits"], end_row=500)
    ids1 = [a["alert_id"] for a in r1.alerts]
    ids2 = [a["alert_id"] for a in r2.alerts]
    assert ids1 == ids2
    assert len(set(ids1)) == len(ids1)  # unique
    assert all(i.startswith("r75-") and len(i) == 20 for i in ids1)


def test_exactly_once_output(bundle, full_stream, tmp_path):
    _, replay = full_stream
    out = tmp_path / "signals.parquet"
    replay.write_signals(out)
    assert len(pd.read_parquet(out)) == len(replay.signals_frame())
    with pytest.raises(FileExistsError):
        replay.write_signals(out)  # never silently overwrite/duplicate
    frame = replay.signals_frame()
    assert frame["bar_index"].is_unique


def test_causal_htf_alignment(bundle, full_stream):
    signals, _ = full_stream
    rep = P.audit_decision_alignment(bundle["candles"], bundle["part"], signals)
    assert rep["verdict"] is True, rep


def test_guard_cutoff_and_choose_invariance(bundle):
    g = P.audit_guard_cutoff(bundle["part"], bundle["preds"], bundle["ds_cfg"],
                             bundle["candles"], bundle["control_exits"],
                             bundle["policy"])
    assert g["cutoff_invariant"] is True
    c = P.audit_choose_row_invariance(bundle["part"], bundle["preds"],
                                      bundle["ds_cfg"])
    assert c["no_window_inspection"] is True, c
