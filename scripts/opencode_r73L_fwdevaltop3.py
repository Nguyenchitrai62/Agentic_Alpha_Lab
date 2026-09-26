"""Opencode R73-L (v159): forward eval of the 3 most deployable-shaped books.

Pre-spec: configs/opencode_v159_fwdevaltop3.json (written BEFORE this script ran;
driver asserts every frozen value before the one full pass).

Candidate 1 L3combo_dd_guard_tp075: v38-identity-fwd (fold-10 3-seed ensemble
RAW + v38_policy_signals verbatim, NO calibrator) + v33-identity-fwd (fold-10
3-seed mms ensemble RAW + imported swing_signals verbatim) + majority-fwd
(v29 fold-10 3-seed ensemble + frozen iso2/iso4/isoall maps + B4 majority vote,
verbatim r66) -> L1 union dedup (bar_index,direction) priority v38>v33>majority
(verbatim v72) -> s0004 filter 0<=UTC hour<4 (verbatim v73) -> tp075_1x-fwd
reference run (guard input only) -> dd_guard (trigger 0.1, lev 0.5, own-book
tp075 ref, verbatim v75) + tp1 0.75. Metrics EXACTLY ONCE (3 scenarios).

Candidate 2 confirmed_dd_guard: v29 forward (same inference as above, reused
arrays, no re-inference) + frozen iso4/isoall maps -> confirmed vote
(d4!=0 AND dall==d4, iso4 geometry, verbatim v15) + frequency loop ->
iso4_only_1x-fwd reference run (v15 convention guard ref, guard input only) ->
dd_guard at confirmed signal times + exec 0.25/1.0 tp1 0.5. Metrics EXACTLY ONCE.

Candidate 3 band2confirmed_1x: candidate-2 pre-guard confirmed_1x-fwd signals +
fund_7d as-of join on SEALED forward funding (strict past, min_periods 21,
NaN->drop recorded) -> keep fund_7d>=5e-05 (verbatim D1/v49, no upper bound) ->
1x tp1 0.5. Metrics EXACTLY ONCE. BLOCKED iff candidate 2 blocked.

Modes:
  --dry-run : plumbing on FIRST 20 forward bars (signals-only: sealed SHA,
              lattice, sequence parity, 3x checkpoint replay parity, policy
              schema, vote masks, union schema, funding-join schema).
              No backtest, no metrics, writes nothing.
  full pass : ONE pass over 679 forward decisions (inference timing recorded),
              guard-reference runs (mechanical, metrics discarded except
              counts), then 3 ohlc-v2 backtests per candidate (normal .0002 /
              fee .00055 / execution FillStress), monthly geometric over
              forward span, then forward-only verdict per candidate
              (subprocess, --forward-only), verdicts embedded into summary
              without recomputing metrics.

Outputs (new dir only): artifacts/research/opencode_v159_fwdevaltop3/
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
BUNDLE_SCRIPTS = (ROOT / "artifacts/kaggle/v38_rankloss_download/rankloss-training/source/scripts")
sys.path.insert(0, str(BUNDLE_SCRIPTS))

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.backtest.swing import swing_signals  # noqa: E402 (verbatim v42 v33-identity)
from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import SwingStore, choose, grid, prices  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.action_margin_value import (  # noqa: E402
    ActionMarginValue, predict_action_margin)
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.residual_temporal_value import (  # noqa: E402
    ResidualTemporalValue, residual_predict)
from opencode_r9m_nextarch_model import SelectiveSSMTemporal, predict_ssm  # noqa: E402 (exact v38 training code)
from safetensors.torch import load_file  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v159_fwdevaltop3.json"
BRANCHES = ("L3combo_dd_guard_tp075", "confirmed_dd_guard", "band2confirmed_1x")
CUTOFF = pd.Timestamp("2026-03-23T00:00:00Z")
STRIDE = 72
N_RESEARCH = 444096
N_FORWARD = 48819
N_DEC = 679
SEEDS = (1729, 1730, 1731)
FOLD_USED = 10
N_FOLDS = 11
PARITY_TOL = 1e-4
B33 = 128
B38 = 32
B29 = 32
MARGIN_SCALE = 1.0
POLICY_MARGIN_V38 = 0.0
POLICY_N_MIN_V38 = 8
FUND_MIN = 5e-05
FUND_MIN_PERIODS = 21
MAPS = ("isotonic_2", "isotonic_4", "isotonic_all")

FWD = ROOT / "data/processed/opencode_forward_20260323"
FEAT = FWD / "features"
RESEARCH = ROOT / "data/processed/swing_regime_research_v4"
V38 = ROOT / "artifacts/kaggle/v38_rankloss_download/rankloss-training"
V33 = ROOT / "artifacts/kaggle/v33_actionmargin_download/tcn-training"
V29 = ROOT / "artifacts/kaggle/v29_download/tcn-training"
CAL_DIR = ROOT / "artifacts/research/opencode_v02_reproduce_v30"

_TF32_STATE = None


def v33_backends_on():
    """r50 proven setting for the v33 section only; restored after."""
    global _TF32_STATE
    _TF32_STATE = (torch.backends.mha.is_fastpath_enabled()
                   if hasattr(torch.backends.mha, "is_fastpath_enabled") else None,
                   torch.backends.cuda.matmul.allow_tf32,
                   torch.backends.cudnn.allow_tf32)
    torch.backends.mha.set_fastpath_enabled(False)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def v33_backends_off():
    global _TF32_STATE
    if _TF32_STATE is None:
        return
    fast, mm, dnn = _TF32_STATE
    if fast is not None:
        torch.backends.mha.set_fastpath_enabled(fast)
    torch.backends.cuda.matmul.allow_tf32 = mm
    torch.backends.cudnn.allow_tf32 = dnn
    _TF32_STATE = None


def sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert list(spec["branches"]) == list(BRANCHES), "3 candidates pre-spec"
    assert spec["forward_features"]["n_decisions"] == N_DEC
    assert spec["funding_band2"]["threshold_fund_7d_min"] == FUND_MIN
    assert spec["checkpoints"]["parity_tol"] == PARITY_TOL
    assert spec["checkpoints"]["margin_scale_percent_v33"] == MARGIN_SCALE
    assert spec["dependency_order"][1].startswith("candidate 1")
    return spec


def verify_checkpoints() -> dict:
    audit = {}
    for name, base in (("v38", V38), ("v33", V33), ("v29", V29)):
        found, missing = [], []
        for seed in SEEDS:
            for fold in range(N_FOLDS):
                q = base / f"seed{seed}/checkpoints/fold_{fold}/model.safetensors"
                (found if q.exists() else missing).append(str(q.relative_to(ROOT)))
        pred_found = sum(
            1 for seed in SEEDS for fold in range(N_FOLDS)
            if (base / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy").exists())
        rep_found = sum(
            1 for seed in SEEDS
            if (base / f"seed{seed}/checkpoints/fold_{FOLD_USED}/replay.npz").exists())
        audit[name] = {"expected": 33, "found": len(found), "missing": missing,
                       "predictions_npy_found": pred_found, "replay_npz_fold10": rep_found,
                       "checkpoints_used_for_forward": 3,
                       "used": [f"seed{s}/checkpoints/fold_{FOLD_USED}/model.safetensors"
                                for s in SEEDS], "unused_recorded": 30}
        print(json.dumps({f"verify_{name}": audit[name]}), flush=True)
    missing_any = [m for a in audit.values() for m in a["missing"]]
    if missing_any:
        raise FileNotFoundError(
            f"STOP: thieu checkpoints, khong thay the model/policy. {missing_any[:3]}")
    return audit


def load_concat(spec: dict):
    fz = json.loads((FWD / "manifest.json").read_text(encoding="utf-8"))
    for key, name in (("candles", "candles.parquet"), ("funding", "funding.parquet"),
                      ("macro", "macro.parquet")):
        if sha(FWD / name) != fz[key]["sha256"]:
            raise ValueError(f"Sealed hash mismatch: {name}")
        if sha(FWD / name) != spec["forward_window"]["sealed_sha256"][name]:
            raise ValueError(f"Sealed hash != prespec: {name}")
    fw = pd.read_parquet(FWD / "candles.parquet")
    if len(fw) != N_FORWARD != fz["candles"]["rows"]:
        raise ValueError("Forward candle row mismatch")
    sums = {}
    for line in (FEAT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1]] = parts[0]
    for name, want in (("features.npz", spec["forward_features"]["sha"]["features.npz"]),
                       ("decisions_forward.parquet",
                        spec["forward_features"]["sha"]["decisions_forward.parquet"])):
        if sha(FEAT / name) != want or sums.get(name) != want:
            raise ValueError(f"E-fwfeatures SHA mismatch: {name}")
    decisions = pd.read_parquet(FEAT / "decisions_forward.parquet")
    if len(decisions) != N_DEC:
        raise ValueError(f"Forward decisions != {N_DEC}")
    rs_meta = json.loads((RESEARCH / "manifest.json").read_text(encoding="utf-8"))
    if sha(RESEARCH / "candles.parquet") != rs_meta["files"]["candles.parquet"]:
        raise ValueError("Research candles changed")
    rs = pd.read_parquet(RESEARCH / "candles.parquet")
    if len(rs) != N_RESEARCH:
        raise ValueError("Research candle row mismatch")
    keep = [c for c in rs.columns if c in fw.columns]
    candles = pd.concat([rs[keep], fw[keep]], ignore_index=True)
    candles = validate_source(candles)
    if len(candles) != N_RESEARCH + N_FORWARD:
        raise ValueError("Concat candle length mismatch")
    grid_idx = np.arange(N_RESEARCH, len(candles), STRIDE, dtype=np.int64)[:N_DEC]
    if len(grid_idx) != N_DEC:
        raise ValueError("Forward lattice != 679")
    if (grid_idx != decisions["bar_index_concat"].to_numpy()).any():
        raise ValueError("Lattice != E-fwfeatures clock")
    sig_times = pd.DatetimeIndex(pd.to_datetime(
        candles["close_time"].iloc[grid_idx])).tz_convert("UTC")
    if (sig_times != pd.DatetimeIndex(
            pd.to_datetime(decisions["signal_time"], utc=True))).any():
        raise ValueError("Signal times != E-fwfeatures clock")
    return candles, decisions, grid_idx


def load_flat() -> np.ndarray:
    with np.load(FEAT / "features.npz", allow_pickle=False) as z:
        flat = z["features"].astype(np.float64)
    if flat.shape != (N_DEC, 133):
        raise ValueError(f"Flat shape {flat.shape} != (679,133)")
    if not np.isfinite(flat).all():
        raise ValueError("Nonfinite forward flat features")
    return flat


def load_calibrators(spec: dict) -> dict:
    out = {}
    short = {"isotonic_2": "iso2", "isotonic_4": "iso4", "isotonic_all": "isoall"}
    for m in MAPS:
        doc = json.loads((CAL_DIR / m / "calibrators.json").read_text(encoding="utf-8"))
        recs = [r for r in doc if r["fold"] == FOLD_USED]
        if len(recs) != 1:
            raise ValueError(f"{m} fold-10 calibrator record missing/ambiguous")
        rec = recs[0]
        if rec.get("warmup") is not None or not rec.get("x") or not rec.get("y"):
            raise ValueError(f"{m} fold-10 calibrator not a fitted map")
        if pd.Timestamp(rec["asof"], tz="UTC") >= CUTOFF:
            raise ValueError(f"{m} calibrator asof not pre-cutoff")
        if pd.Timestamp(rec["latest_label_end"], tz="UTC") >= CUTOFF:
            raise ValueError(f"{m} calibrator fitted on post-cutoff labels")
        if rec["eligible_rows"] != spec["calibrators_v29_vote"]["eligible_rows"][short[m]]:
            raise ValueError(f"{m} eligible_rows drift vs prespec")
        xv = np.asarray(rec["x"], dtype=np.float64)
        yv = np.asarray(rec["y"], dtype=np.float64)
        if not bool(np.all(np.diff(xv) >= 0)) or not bool(np.all(np.diff(yv) >= -1e-12)):
            raise ValueError(f"{m} fold-10 iso map not monotone")
        out[m] = {"x": xv, "y": yv, "asof": rec["asof"],
                  "eligible_rows": rec["eligible_rows"],
                  "latest_label_end": rec["latest_label_end"]}
    return out


# ---------- model constructors (verbatim per-family proven code) ----------

def make_v38(candidates: np.ndarray) -> SelectiveSSMTemporal:
    return SelectiveSSMTemporal(candidates, n_flat=133, frame_dim=64,
                                frame_state=16, frame_layers=2,
                                cross_state=16, dropout=0.1)


def make_v33(candidates: np.ndarray) -> ActionMarginValue:
    return ActionMarginValue(candidates, width=48, dropout=0.15)


def make_v29(candidates: np.ndarray) -> ResidualTemporalValue:
    return ResidualTemporalValue(candidates, width=48, dropout=0.15)


def parity_v38(candidates: np.ndarray, device: torch.device) -> dict:
    out = {}
    for seed in SEEDS:
        rep = np.load(V38 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/replay.npz",
                      allow_pickle=False)
        cloud = np.load(V38 / f"seed{seed}/temporal_neural/fold_{FOLD_USED}/predictions.npy",
                        allow_pickle=False)
        if rep["predictions"].shape != (8, 16, 6) or rep["sequences"].shape != (8, 5, 128, 6):
            raise ValueError(f"v38 seed{seed} replay shape drift")
        if not np.allclose(rep["predictions"], cloud[:8], rtol=0, atol=0):
            raise ValueError(f"v38 seed{seed} replay != cloud predictions[:8]")
        model = make_v38(candidates)
        model.load_state_dict(load_file(str(
            V38 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors")))
        model.eval()
        local = predict_ssm(model.to(device), rep["sequences"], rep["features"],
                            batch_size=B38)
        err = float(np.max(np.abs(local - rep["predictions"].astype(np.float64))))
        out[f"seed{seed}"] = err
        print(json.dumps({"parity_v38": {"seed": seed, "max_abs_diff": err,
                                         "tol": PARITY_TOL, "pass": err <= PARITY_TOL}}),
              flush=True)
        if err > PARITY_TOL:
            raise ValueError(f"STOP: v38 seed{seed} local != cloud ({err} > {PARITY_TOL})")
        del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return out


def parity_v33(candidates: np.ndarray, device: torch.device) -> dict:
    out = {}
    for seed in SEEDS:
        rep = np.load(V33 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/replay.npz",
                      allow_pickle=False)
        cloud = np.load(V33 / f"seed{seed}/temporal_neural/fold_{FOLD_USED}/predictions.npy",
                        allow_pickle=False)
        if rep["predictions"].shape != (8, 16, 6) or rep["sequences"].shape != (8, 5, 128, 6):
            raise ValueError(f"v33 seed{seed} replay shape drift")
        if rep["features"].shape != (8, 40):
            raise ValueError(f"v33 seed{seed} replay features != (8,40)")
        if not np.allclose(rep["predictions"], cloud[:8], rtol=0, atol=0):
            raise ValueError(f"v33 seed{seed} replay != cloud predictions[:8]")
        model = make_v33(candidates)
        model.load_state_dict(load_file(str(
            V33 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors")))
        model.eval()
        local = predict_action_margin(
            model.to(device), rep["sequences"], rep["features"],
            batch_size=B33, margin_scale_percent=MARGIN_SCALE)
        err = float(np.max(np.abs(local.astype(np.float64)
                                  - rep["predictions"].astype(np.float64))))
        out[f"seed{seed}"] = err
        print(json.dumps({"parity_v33": {"seed": seed, "max_abs_diff": err,
                                         "tol": PARITY_TOL, "pass": err <= PARITY_TOL}}),
              flush=True)
        if err > PARITY_TOL:
            raise ValueError(f"STOP: v33 seed{seed} local != cloud ({err} > {PARITY_TOL})")
        del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return out


def parity_v29(candidates: np.ndarray, device: torch.device) -> dict:
    out = {}
    for seed in SEEDS:
        rep = np.load(V29 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/replay.npz",
                      allow_pickle=False)
        cloud = np.load(V29 / f"seed{seed}/temporal_neural/fold_{FOLD_USED}/predictions.npy",
                        allow_pickle=False)
        if rep["predictions"].shape != (8, 16, 6) or rep["sequences"].shape != (8, 5, 128, 6):
            raise ValueError(f"v29 seed{seed} replay shape drift")
        if rep["features"].shape != (8, 40):
            raise ValueError(f"v29 seed{seed} replay feat40 shape drift")
        if not np.allclose(rep["predictions"], cloud[:8], rtol=0, atol=0):
            raise ValueError(f"v29 seed{seed} replay != cloud predictions[:8]")
        model = make_v29(candidates)
        model.load_state_dict(load_file(str(
            V29 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors")))
        model.eval()
        local = residual_predict(model.to(device), rep["sequences"], rep["features"],
                                 batch_size=B29)
        err = float(np.max(np.abs(local - rep["predictions"].astype(np.float64))))
        out[f"seed{seed}"] = err
        print(json.dumps({"parity_v29": {"seed": seed, "max_abs_diff": err,
                                         "tol": PARITY_TOL, "pass": err <= PARITY_TOL}}),
              flush=True)
        if err > PARITY_TOL:
            raise ValueError(f"STOP: v29 seed{seed} local != cloud ({err} > {PARITY_TOL})")
        del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return out


def build_sequences(store: SwingStore, candles: pd.DataFrame, decisions: pd.DataFrame,
                    idx: np.ndarray, flat: np.ndarray):
    seqs, feats, closes, a5, a4 = [], [], [], [], []
    for j, k in enumerate(idx):
        kk = int(k)
        ts = pd.Timestamp(decisions["signal_time"].iloc[kk])
        w, _, _, feat40, atr5, atr4 = store.sample(ts)
        np.testing.assert_allclose(feat40, flat[kk, :40], rtol=1e-6, atol=1e-6)
        seqs.append(encode_windows(w))
        feats.append(np.asarray(feat40, dtype=np.float32))
        closes.append(float(candles["close"].iloc[int(
            decisions["bar_index_concat"].iloc[kk])]))
        a5.append(float(atr5))
        a4.append(float(atr4))
    seqs = np.stack(seqs).astype(np.float32)
    feats = np.stack(feats).astype(np.float32)
    if seqs.shape[1:] != (5, 128, 6) or not np.isfinite(seqs).all():
        raise ValueError("Bad forward sequences")
    if feats.shape[1:] != (40,) or not np.isfinite(feats).all():
        raise ValueError("Bad forward feat40")
    return seqs, feats, np.asarray(closes), np.asarray(a5), np.asarray(a4)


def infer_v38(candidates, seqs, flat, device):
    t0 = time.perf_counter()
    per_seed_s, outs = {}, []
    for seed in SEEDS:
        s0 = time.perf_counter()
        model = make_v38(candidates)
        model.load_state_dict(load_file(str(
            V38 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors")))
        model.eval()
        outs.append(predict_ssm(model.to(device), seqs, flat.astype(np.float32),
                                batch_size=B38))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        per_seed_s[f"seed{seed}"] = time.perf_counter() - s0
    stacked = np.stack(outs).astype(np.float64)
    if stacked.shape != (3, len(seqs), 16, 6) or not np.isfinite(stacked).all():
        raise ValueError(f"Bad v38 stacked {stacked.shape}")
    ensemble, details = combine(stacked, 0.0)
    secs = time.perf_counter() - t0
    timing = {"inference_seconds_total": secs, "per_seed_seconds": per_seed_s,
              "seconds_per_window": secs / max(len(seqs), 1), "device": str(device),
              "batch": B38, "combine_penalty": 0.0}
    return np.asarray(ensemble, dtype=np.float64), details, timing


def infer_v33(candidates, seqs, feat40, device):
    t0 = time.perf_counter()
    per_seed_s, outs = {}, []
    for seed in SEEDS:
        s0 = time.perf_counter()
        model = make_v33(candidates)
        model.load_state_dict(load_file(str(
            V33 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors")))
        model.eval()
        outs.append(predict_action_margin(
            model.to(device), seqs, feat40.astype(np.float32),
            batch_size=B33, margin_scale_percent=MARGIN_SCALE))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        per_seed_s[f"seed{seed}"] = time.perf_counter() - s0
    stacked = np.stack(outs).astype(np.float64)
    if stacked.shape != (3, len(seqs), 16, 6) or not np.isfinite(stacked).all():
        raise ValueError(f"Bad v33 stacked {stacked.shape}")
    ensemble, details = combine(stacked, 1.0)
    secs = time.perf_counter() - t0
    timing = {"inference_seconds_total": secs, "per_seed_seconds": per_seed_s,
              "seconds_per_window": secs / max(len(seqs), 1), "device": str(device),
              "batch": B33, "combine_penalty": 1.0}
    return np.asarray(ensemble, dtype=np.float64), details, timing


def infer_v29(candidates, seqs, feats, device):
    t0 = time.perf_counter()
    per_seed_s, outs = {}, []
    for seed in SEEDS:
        s0 = time.perf_counter()
        model = make_v29(candidates)
        model.load_state_dict(load_file(str(
            V29 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors")))
        model.eval()
        outs.append(residual_predict(model.to(device), seqs, feats, batch_size=B29))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        per_seed_s[f"seed{seed}"] = time.perf_counter() - s0
    stacked = np.stack(outs).astype(np.float64)
    if stacked.shape != (3, len(seqs), 16, 6) or not np.isfinite(stacked).all():
        raise ValueError(f"Bad v29 stacked {stacked.shape}")
    base, details = combine(stacked, 0.0)
    secs = time.perf_counter() - t0
    timing = {"inference_seconds_total": secs, "per_seed_seconds": per_seed_s,
              "seconds_per_window": secs / max(len(seqs), 1), "device": str(device),
              "batch": B29, "combine_penalty": 0.0}
    return np.asarray(base, dtype=np.float64), details, timing


# ---------- policies (verbatim proven functions) ----------

def v38_policy_signals(raw_pred: np.ndarray, decisions: pd.DataFrame, idx: np.ndarray,
                       closes: np.ndarray, a5: np.ndarray, a4: np.ndarray,
                       cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Ban sao VERBATIM v38_policy_signals (r49 driver); identity = RAW ensemble."""
    pred = np.asarray(raw_pred, dtype=np.float64)
    fill = 1 / (1 + np.exp(-np.clip(pred[..., 4], -40, 40)))
    expected = pred[..., 0] * fill
    en_best = expected.max(1)
    gate = np.flatnonzero(en_best > POLICY_MARGIN_V38)
    info = {"gate_hits": int(len(gate)), "n_forward": int(len(idx))}
    if len(gate) >= POLICY_N_MIN_V38:
        selected = set(gate.tolist())
        info["fallback_adds"] = 0
    else:
        top = np.argsort(-en_best, kind="stable")[:min(POLICY_N_MIN_V38, len(idx))]
        selected = set(gate.tolist()) | set(top.tolist())
        info["fallback_adds"] = int(len(set(top.tolist()) - set(gate.tolist())))
    info["n_selected"] = len(selected)
    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    if cand_grid.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    policy, signals = cfg["policy"], []
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    n_wait_ineligible = 0
    order = np.argsort([pd.Timestamp(decisions["signal_time"].iloc[int(k)]).value
                        for k in idx], kind="stable")
    for j in order:
        if int(j) not in selected:
            continue
        k = int(idx[int(j)])
        timestamp = pd.Timestamp(decisions["signal_time"].iloc[k])
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        elig = np.flatnonzero(fill[int(j)] >= policy["minimum_fill_score"])
        if not len(elig):
            n_wait_ineligible += 1
            continue
        kk = int(elig[np.argmax(expected[int(j), elig])])
        bar = int(decisions["bar_index_concat"].iloc[k])
        if pd.to_datetime(store_close_time(bar), utc=True) != timestamp:
            raise ValueError("Signal not at closed-candle time (causality)")
        signals.append({"bar_index": bar, "signal_time": timestamp, "fold_test": -1,
                        "direction": int(cand_grid[kk, 0]), "candidate_id": kk,
                        **prices(float(closes[int(j)]), float(a5[int(j)]),
                                 float(a4[int(j)]), cand_grid[kk], cfg),
                        "expected_net_percent": float(expected[int(j), kk]),
                        "en_best": float(en_best[int(j)]),
                        "ohlc_fill_score": float(fill[int(j), kk]),
                        "calibrated": False, "entry_expiry_bars": cfg["entry_expiry_bars"],
                        "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    frame = pd.DataFrame(signals)
    info.update({"n_signals": len(frame), "n_wait_no_fill_eligible": n_wait_ineligible,
                 "policy_margin": POLICY_MARGIN_V38, "policy_n_min": POLICY_N_MIN_V38,
                 "monthly_cap": policy["maximum_signals_per_month"],
                 "cooldown_days": policy["cooldown_days"]})
    return frame, info


_CLOSE_TIMES = None


def store_close_time(bar: int):
    return _CLOSE_TIMES[bar]


def dir_of(out) -> int:
    if out.get("action") == "LONG":
        return 1
    if out.get("action") == "SHORT":
        return -1
    return 0


def calibrate_all(base: np.ndarray, details: dict, calibs: dict) -> dict:
    """Ban sao VERBATIM r66 calibrate_all (frozen iso maps, no refit)."""
    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    if score.shape != fill.shape or score.shape[1:] != (16,):
        raise ValueError("Bad ensemble detail shapes")
    outs = {}
    for m in MAPS:
        mapped = np.interp(score.ravel(), calibs[m]["x"], calibs[m]["y"]).reshape(score.shape)
        pred = np.asarray(base, dtype=np.float64).copy()
        pred[..., 0] = mapped / fill
        outs[m] = pred
    return outs


def choose_all(preds: dict, closes: np.ndarray, a5: np.ndarray, a4: np.ndarray,
               cfg: dict):
    """Ban sao VERBATIM r66 choose_all."""
    outs, dirs = {}, {}
    for m in MAPS:
        arr = preds[m]
        olist, dlist = [], []
        for j in range(arr.shape[0]):
            o = choose(arr[j], float(closes[j]), float(a5[j]), float(a4[j]), cfg)
            olist.append(None if o.get("action") == "WAIT" else o)
            dlist.append(dir_of(o))
        outs[m] = olist
        dirs[m] = np.asarray(dlist, dtype=int)
    return outs, dirs


def vote_masks(dirs: dict, decisions: pd.DataFrame, idx: np.ndarray) -> dict:
    """r66 vote_masks + confirmed + iso4_only (verbatim v15 mask defs)."""
    d2, d4, dall = dirs["isotonic_2"], dirs["isotonic_4"], dirs["isotonic_all"]
    n = len(idx)
    mask_iso4_only = (d4 != 0)
    mask_majority = np.array([
        (d4[j] != 0) and ([d2[j], d4[j], dall[j]].count(int(d4[j])) >= 2)
        for j in range(n)], dtype=bool)
    mask_confirmed = (d4 != 0) & (dall == d4)
    hours = pd.to_datetime(decisions["signal_time"].iloc[idx], utc=True).dt.hour.to_numpy()
    mask_session = (hours >= 0) & (hours < 4)
    masks = {"iso4_only": mask_iso4_only, "majority": mask_majority,
             "confirmed": mask_confirmed,
             "majority_s0004_diag": mask_majority & mask_session}
    agreement = {
        "n_rows": int(n),
        "nonwait_iso2": int((d2 != 0).sum()),
        "nonwait_iso4": int((d4 != 0).sum()),
        "nonwait_isoall": int((dall != 0).sum()),
        "pass_iso4_only": int(mask_iso4_only.sum()),
        "pass_majority": int(mask_majority.sum()),
        "pass_confirmed": int(mask_confirmed.sum()),
        "agree_majority_given_iso4": float(mask_majority.sum() / (d4 != 0).sum())
        if (d4 != 0).sum() else 0.0,
        "agree_confirmed_given_iso4": float(mask_confirmed.sum() / (d4 != 0).sum())
        if (d4 != 0).sum() else 0.0,
    }
    return masks, agreement


def gen_forward(mask: np.ndarray, iso4_outs: list, decisions: pd.DataFrame, idx: np.ndarray,
                closes: np.ndarray, a5: np.ndarray, a4: np.ndarray, cfg: dict) -> pd.DataFrame:
    """Ban sao VERBATIM r66 gen_forward (B4 gen_from_mask, forward lattice)."""
    policy = cfg["policy"]
    signals, monthly = [], Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    order = np.argsort([pd.Timestamp(decisions["signal_time"].iloc[int(k)]).value
                        for k in idx], kind="stable")
    for pos in order:
        j = int(pos)
        if not bool(mask[j]):
            continue
        out = iso4_outs[j]
        if out is None or out.get("action") == "WAIT":
            continue
        k = int(idx[j])
        timestamp = pd.Timestamp(decisions["signal_time"].iloc[k])
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        bar = int(decisions["bar_index_concat"].iloc[k])
        if pd.to_datetime(store_close_time(bar), utc=True) != timestamp:
            raise ValueError("Signal not at closed-candle time (causality)")
        sig = dict(out)
        sig.pop("action", None)
        signals.append({"bar_index": bar, "signal_time": timestamp, **sig})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    if signals:
        return pd.DataFrame(signals)
    return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


def union_pool(frames: dict) -> tuple[pd.DataFrame, dict]:
    """L1 union VERBATIM v72: dedup (bar_index,direction), priority v38>v33>majority."""
    order = ["v38_identity", "v33_identity", "majority"]
    tag = {"v38_identity": "src_v38_identity", "v33_identity": "src_v33_identity",
           "majority": "src_majority_1x"}
    seen, rows, conflicts, geo_diffs = {}, [], 0, 0
    geo_cols = ["entry_limit", "stop_loss", "take_profit_1", "take_profit_2",
                "holding_bars"]
    for key in order:
        fr = frames[key]
        for _, row in fr.iterrows():
            kk = (int(row["bar_index"]), int(row["direction"]))
            if kk in seen:
                conflicts += 1
                prev = seen[kk]
                try:
                    same = all(abs(float(prev[c]) - float(row[c])) < 1e-9 for c in geo_cols)
                except (KeyError, TypeError, ValueError):
                    same = False
                if not same:
                    geo_diffs += 1
                prev["sources"] = sorted(set(prev["sources"]) | {key})
                prev["n_sources"] = len(prev["sources"])
                prev[tag[key]] = True
                continue
            rec = {c: row[c] for c in fr.columns if c != "action"}
            rec["sources"] = [key]
            rec["n_sources"] = 1
            for t in tag.values():
                rec[t] = (t == tag[key])
            seen[kk] = rec
    rows = list(seen.values())
    pool = pd.DataFrame(rows)
    if len(pool):
        pool["signal_time"] = pd.to_datetime(pool["signal_time"], utc=True)
        pool = pool.sort_values("signal_time").reset_index(drop=True)
    info = {"n_pool": int(len(pool)),
            "n_per_source": {k: int(len(frames[k])) for k in order},
            "n_dedup_conflicts": int(conflicts), "n_geometry_diffs": int(geo_diffs)}
    return pool, info


def s0004_filter(pool: pd.DataFrame) -> pd.DataFrame:
    """L2 s0004 VERBATIM v73: keep iff 0 <= UTC hour(signal_time) < 4."""
    if not len(pool):
        return pool.copy()
    hours = pd.to_datetime(pool["signal_time"], utc=True).dt.hour.to_numpy()
    return pool[((hours >= 0) & (hours < 4))].copy().reset_index(drop=True)


def dd_guard_leverage(signal_times, ref_trades, trigger: float = 0.1,
                      lev: float = 0.5) -> np.ndarray:
    """Guard VERBATIM v15/v42/v75 drivers (trigger/lev params; ref = sampled equity)."""
    equity_at = sorted((pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades)
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signal_times, utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak, level = float(curve.cummax().iloc[-1]), float(curve.iloc[-1])
        out.append(lev if level / peak < 1.0 - trigger else 1.0)
    return np.array(out, dtype=float)


def fund_7d_asof(signal_times) -> np.ndarray:
    """fund_7d VERBATIM D1 v23 dinh_nghia: mean trailing 21 fundingRate, strict
    past (funding_time < signal_time), min_periods=21; NaN -> dropped downstream."""
    fwd = pd.read_parquet(FWD / "funding.parquet").sort_values("funding_time")
    ft = pd.to_datetime(fwd["funding_time"], utc=True).astype("int64").to_numpy()
    fr = fwd["fundingRate"].to_numpy(dtype=np.float64)
    out = np.full(len(signal_times), np.nan)
    for i, ts in enumerate(pd.to_datetime(signal_times, utc=True)):
        n = int(np.searchsorted(ft, pd.Timestamp(ts).value, side="left"))
        if n >= FUND_MIN_PERIODS:
            out[i] = float(fr[n - FUND_MIN_PERIODS:n].mean())
    return out


def run_branch(candles: pd.DataFrame, signals: pd.DataFrame, costs: CostModel,
               fee_costs: CostModel, exec_cfg: ExecutionConfig, years: float):
    fee_only = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    assert abs(fee_only.fee_rate_per_fill - fee_costs.fee_rate_per_fill) < 1e-12, \
        "fee stress .00055 pre-spec"
    normal, trades = run_backtest(candles, signals, 100, costs, exec_cfg)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, exec_cfg)
    stress, st, diag = run_stress(candles, signals, 100, costs, exec_cfg,
                                  FillStress(5, 5, 5, 0.00055, False))
    out = {}
    for label, res, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                              ("execution_stress", stress, st)):
        ratio = res.final_equity / 100
        out[label] = {**asdict(res),
                      "annual_geometric_net": float(ratio ** (1 / years) - 1),
                      "monthly_geometric_net": float(ratio ** (1 / (12 * years)) - 1)}
        out[label]["_trades"] = items
    out["execution_stress"]["diagnostics"] = diag
    return out


def run_ref_1x(candles, signals, costs, exec_cfg):
    """Mechanical guard-reference run (normal only); returns normal trades."""
    exec_sig = signals.drop(columns=["leverage"], errors="ignore").copy() \
        if len(signals) else signals.iloc[0:0].drop(columns=["leverage"], errors="ignore").copy()
    _, trades = run_backtest(candles, exec_sig, 100, costs, exec_cfg)
    return trades


def check_schema(frame: pd.DataFrame, name: str) -> dict:
    need = {"bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
            "take_profit_1", "take_profit_2", "holding_bars"}
    if len(frame) and not need.issubset(set(frame.columns)):
        raise ValueError(f"{name} signal schema drift: {sorted(set(frame.columns))}")
    if len(frame) and not set(frame["direction"].unique()).issubset({-1, 1}):
        raise ValueError(f"{name} direction not in {{-1,1}}")
    return {"n_signals": int(len(frame)),
            "n_long": int((frame["direction"] == 1).sum()) if len(frame) else 0,
            "n_short": int((frame["direction"] == -1).sum()) if len(frame) else 0}


def dry_run() -> None:
    spec = load_spec()
    ck = verify_checkpoints()
    assert all(a["replay_npz_fold10"] == 3 for a in ck.values()), "replay 3/3 per family"
    candles, decisions, grid_idx = load_concat(spec)
    flat = load_flat()
    cfg = json.loads((RESEARCH / "config.json").read_text(encoding="utf-8"))
    assert cfg["policy"]["minimum_expected_net_percent"] == 0.3
    assert cfg["policy"]["minimum_fill_score"] == 0.25
    calibs = load_calibrators(spec)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    par38 = parity_v38(candidates, device)
    v33_backends_on()
    try:
        par33 = parity_v33(candidates, device)
    finally:
        v33_backends_off()
    par29 = parity_v29(candidates, device)
    global _CLOSE_TIMES
    _CLOSE_TIMES = pd.to_datetime(candles["close_time"], utc=True).reset_index(drop=True)
    store = SwingStore(candles, cfg)
    sub = np.arange(20, dtype=np.int64)
    seqs, feats, closes, a5, a4 = build_sequences(store, candles, decisions, sub, flat)
    ens38, _, t38 = infer_v38(candidates, seqs, flat[sub], device)
    v33_backends_on()
    try:
        ens33, _, t33 = infer_v33(candidates, seqs, feats, device)
    finally:
        v33_backends_off()
    ens29, det29, t29 = infer_v29(candidates, seqs, feats, device)
    f38, i38 = v38_policy_signals(ens38, decisions, sub, closes, a5, a4, cfg)
    like = pd.DataFrame({"signal_time": pd.to_datetime(
        decisions["signal_time"].iloc[sub], utc=True).to_numpy(),
        "bar_index": decisions["bar_index_concat"].iloc[sub].to_numpy(),
        "close": closes, "atr5": a5, "atr4": a4})
    f33 = swing_signals(ens33.astype(np.float32), like, cfg)
    preds = calibrate_all(ens29, det29, calibs)
    outs, dirs = choose_all(preds, closes, a5, a4, cfg)
    masks, agreement = vote_masks(dirs, decisions, sub)
    fmaj = gen_forward(masks["majority"], outs["isotonic_4"], decisions, sub,
                       closes, a5, a4, cfg)
    fcon = gen_forward(masks["confirmed"], outs["isotonic_4"], decisions, sub,
                       closes, a5, a4, cfg)
    fiso = gen_forward(masks["iso4_only"], outs["isotonic_4"], decisions, sub,
                       closes, a5, a4, cfg)
    pool, uinfo = union_pool({"v38_identity": f38, "v33_identity": f33,
                              "majority": fmaj})
    s4 = s0004_filter(pool)
    f7 = fund_7d_asof(fcon["signal_time"]) if len(fcon) else np.array([])
    for name, fr in (("v38_identity", f38), ("v33_identity", f33),
                     ("majority", fmaj), ("confirmed", fcon), ("iso4_only", fiso),
                     ("pool", pool), ("s0004", s4)):
        check_schema(fr, name)
    print(json.dumps({"dry_run_plumbing": "OK", "n_windows": 20,
                      "forward_rows": "first 20 post-cutoff (no pre-cutoff substitute)",
                      "parity": {"v38": par38, "v33": par33, "v29": par29},
                      "policy": {"v38_identity": i38, "agreement_row_level": agreement,
                                 "union": uinfo, "n_s0004_of_pool": int(len(s4)),
                                 "n_confirmed_band2_warm": int((f7 >= FUND_MIN).sum())
                                 if len(f7) else 0,
                                 "n_confirmed_nan_fund": int(np.isnan(f7).sum())
                                 if len(f7) else 0},
                      "infer_timing": {"v38": t38, "v33": t33, "v29": t29},
                      "pre_cutoff_only": False, "writes": "none",
                      "metrics": "none (signals-only, no backtest)"}, default=str))


def full_pass(out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"Khong ghi de: {out} da ton tai")
    spec = load_spec()
    ck_audit = verify_checkpoints()
    candles, decisions, grid_idx = load_concat(spec)
    flat = load_flat()
    cfg = json.loads((RESEARCH / "config.json").read_text(encoding="utf-8"))
    calibs = load_calibrators(spec)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    if candidates.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    par38 = parity_v38(candidates, device)
    v33_backends_on()
    try:
        par33 = parity_v33(candidates, device)
    finally:
        v33_backends_off()
    par29 = parity_v29(candidates, device)
    global _CLOSE_TIMES
    _CLOSE_TIMES = pd.to_datetime(candles["close_time"], utc=True).reset_index(drop=True)
    store = SwingStore(candles, cfg)
    idx = np.arange(N_DEC, dtype=np.int64)
    seqs, feats, closes, a5, a4 = build_sequences(store, candles, decisions, idx, flat)

    # ---- inference, one pass per family ----
    ens38, det38, t38 = infer_v38(candidates, seqs, flat, device)
    v33_backends_on()
    try:
        ens33, det33, t33 = infer_v33(candidates, seqs, feats, device)
    finally:
        v33_backends_off()
    ens29, det29, t29 = infer_v29(candidates, seqs, feats, device)

    # ---- candidate 1 legs (identity-level) ----
    f38, i38 = v38_policy_signals(ens38, decisions, idx, closes, a5, a4, cfg)
    like = pd.DataFrame({"signal_time": pd.to_datetime(
        decisions["signal_time"].iloc[idx], utc=True).to_numpy(),
        "bar_index": decisions["bar_index_concat"].iloc[idx].to_numpy(),
        "close": closes, "atr5": a5, "atr4": a4})
    f33 = swing_signals(ens33.astype(np.float32), like, cfg)
    preds = calibrate_all(ens29, det29, calibs)
    outs, dirs = choose_all(preds, closes, a5, a4, cfg)
    masks, agreement = vote_masks(dirs, decisions, idx)
    fmaj = gen_forward(masks["majority"], outs["isotonic_4"], decisions, idx,
                       closes, a5, a4, cfg)
    fcon = gen_forward(masks["confirmed"], outs["isotonic_4"], decisions, idx,
                       closes, a5, a4, cfg)
    fiso = gen_forward(masks["iso4_only"], outs["isotonic_4"], decisions, idx,
                       closes, a5, a4, cfg)
    for name, fr in (("v38_identity", f38), ("v33_identity", f33),
                     ("majority", fmaj), ("confirmed", fcon), ("iso4_only", fiso)):
        check_schema(fr, name)
    pool, uinfo = union_pool({"v38_identity": f38, "v33_identity": f33,
                              "majority": fmaj})
    check_schema(pool, "pool")
    s4 = s0004_filter(pool)
    check_schema(s4, "s0004")

    # ---- common backtest setup ----
    fw_candles = pd.read_parquet(FWD / "candles.parquet")
    first_open = pd.to_datetime(fw_candles["open_time"], utc=True).min()
    last_close = pd.to_datetime(fw_candles["close_time"], utc=True).max()
    years = (last_close - first_open).total_seconds() / (365.2425 * 86400)
    costs = CostModel(**cfg["costs"])
    fee_costs = CostModel(**spec["backtest"]["costs_fee_stress"])
    cap = int(max(cfg["holding_days"]) * 288)
    assert cap == 2016, "holding cap"
    exec_1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                              max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    exec_tp075_1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                                    max_holding_bars=cap, tp1_fraction=0.75,
                                    leverage=1.0, max_leverage=1.0)
    exec_dd_tp075 = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                                    max_holding_bars=cap, tp1_fraction=0.75,
                                    leverage=0.25, max_leverage=1.0)
    exec_dd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                              max_holding_bars=cap, leverage=0.25, max_leverage=1.0)
    gate = json.loads((ROOT / "configs/opencode_gatecheck.json").read_text(
        encoding="utf-8"))["gate"]

    def flags(d):
        try:
            m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f_ok = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m_ok = dd_ok = f_ok = False
        return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
                "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}

    out.mkdir(parents=True)
    branches, comp = {}, {}

    # ---- candidate 1: L3combo_dd_guard_tp075 ----
    ref_tp075_trades = run_ref_1x(candles, s4, costs, exec_tp075_1x)
    lev1 = dd_guard_leverage(pd.to_datetime(s4["signal_time"], utc=True),
                             ref_tp075_trades) if len(s4) else np.array([], dtype=float)
    sig1 = s4.copy()
    sig1["leverage"] = lev1
    scen1 = run_branch(candles, sig1, costs, fee_costs, exec_dd_tp075, years)
    comp["L3combo_dd_guard_tp075"] = {
        "n_v38_identity": int(len(f38)), "n_v33_identity": int(len(f33)),
        "n_majority": int(len(fmaj)), "union": uinfo,
        "n_s0004": int(len(s4)), "n_tp075_ref_trades": int(len(ref_tp075_trades)),
        "guard_frac_half": float((lev1 == 0.5).mean()) if len(lev1) else 0.0,
        "policy_v38": i38, "agreement": agreement}

    # ---- candidate 2: confirmed_dd_guard (v15 convention: iso4_only ref) ----
    ref_iso_trades = run_ref_1x(candles, fiso, costs, exec_1x)
    lev2 = dd_guard_leverage(pd.to_datetime(fcon["signal_time"], utc=True),
                             ref_iso_trades) if len(fcon) else np.array([], dtype=float)
    sig2 = fcon.copy()
    sig2["leverage"] = lev2
    scen2 = run_branch(candles, sig2, costs, fee_costs, exec_dd, years)
    comp["confirmed_dd_guard"] = {
        "n_confirmed_1x": int(len(fcon)), "n_iso4_only": int(len(fiso)),
        "n_iso4_ref_trades": int(len(ref_iso_trades)),
        "guard_frac_half": float((lev2 == 0.5).mean()) if len(lev2) else 0.0,
        "agreement": agreement}

    # ---- candidate 3: band2confirmed_1x (depends on candidate-2 signals) ----
    f7 = fund_7d_asof(fcon["signal_time"]) if len(fcon) else np.array([])
    n_nan = int(np.isnan(f7).sum()) if len(f7) else 0
    keep = (f7 >= FUND_MIN) if len(f7) else np.array([], dtype=bool)
    sig3 = fcon[keep].copy().reset_index(drop=True) if len(fcon) else fcon.copy()
    sig3 = sig3.drop(columns=["leverage", "fund_7d"], errors="ignore")
    f7kept = f7[keep] if len(f7) else np.array([])
    scen3 = run_branch(candles, sig3, costs, fee_costs, exec_1x, years)
    comp["band2confirmed_1x"] = {
        "n_confirmed_in": int(len(fcon)), "n_band2_kept": int(len(sig3)),
        "n_nan_fund_dropped": n_nan,
        "fund_kept_min": float(f7kept.min()) if len(f7kept) else None,
        "fund_kept_max": float(f7kept.max()) if len(f7kept) else None}

    sigs = {"L3combo_dd_guard_tp075": sig1, "confirmed_dd_guard": sig2,
            "band2confirmed_1x": sig3}
    scens = {"L3combo_dd_guard_tp075": scen1, "confirmed_dd_guard": scen2,
             "band2confirmed_1x": scen3}
    for branch in BRANCHES:
        check_schema(sigs[branch].drop(columns=["leverage"], errors="ignore"), branch)
        bdir = out / branch
        bdir.mkdir(parents=True)
        sigs[branch].to_parquet(bdir / "signals.parquet", index=False)
        bres = {}
        for label in ("normal", "fee_stress", "execution_stress"):
            items = scens[branch][label].pop("_trades")
            rows = [asdict(t) for t in items]
            pd.DataFrame(rows).to_csv(bdir / f"{label}_trades.csv", index=False)
            d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                 for k, v in scens[branch][label].items() if k != "diagnostics"}
            if label == "execution_stress":
                d["diagnostics"] = scens[branch][label].get("diagnostics")
            d["gate"] = flags(d)
            bres[label] = d
        branches[branch] = bres
    np.savez_compressed(out / "forward_predictions.npz",
                        v38_ensemble=np.asarray(ens38, dtype=np.float32),
                        v33_ensemble=np.asarray(ens33, dtype=np.float32),
                        v29_base=np.asarray(ens29, dtype=np.float32),
                        v29_sel=np.asarray(det29["selection_score_percent"], dtype=np.float32),
                        v29_fill=np.asarray(det29["mean_fill_score"], dtype=np.float32))

    def exit_span_of(branch: str):
        if not branches[branch]["normal"]["trades"]:
            return [None, None]
        ex = pd.read_csv(out / branch / "normal_trades.csv", usecols=["exit_time"])
        col = pd.to_datetime(ex["exit_time"], utc=True)
        return [str(col.min()), str(col.max())]

    summary = {
        "experiment": "opencode-r73L-fwdevaltop3",
        "prespec": "configs/opencode_v159_fwdevaltop3.json",
        "pass": 1,
        "pass_note": "ONE evaluation pass per candidate; no pass-2 has occurred",
        "branches": branches,
        "seal": {"cutoff_exclusive": "2026-03-23T00:00:00+00:00",
                 "state": "PRISTINE per SEAL.json + ledger forward_window rule"},
        "frozen_refs": {
            "checkpoints": ck_audit,
            "calibrators_v29_vote": {
                s: {"path": f"artifacts/research/opencode_v02_reproduce_v30/{m}/calibrators.json",
                    "fold": FOLD_USED, "asof": calibs[m]["asof"],
                    "eligible_rows": calibs[m]["eligible_rows"],
                    "latest_label_end": calibs[m]["latest_label_end"]}
                for s, m in (("iso2", "isotonic_2"), ("iso4", "isotonic_4"),
                             ("isoall", "isotonic_all"))},
            "parity": {"v38": par38, "v33": par33, "v29": par29}},
        "clock": {"n_decisions": N_DEC, "stride_bars": STRIDE,
                  "first_signal": str(pd.to_datetime(
                      decisions["signal_time"].iloc[0], utc=True)),
                  "last_signal": str(pd.to_datetime(
                      decisions["signal_time"].iloc[-1], utc=True)),
                  "matches_E_fwfeatures": True},
        "signals_composition": comp,
        "span": {"forward_first_open": str(first_open),
                 "forward_last_close": str(last_close),
                 "years": years,
                 "exit_span_normal": {b: exit_span_of(b) for b in BRANCHES}},
        "inference": {"v38": t38, "v33": t33, "v29": t29},
        "machine_verdict": {},
        "seal_affirmation": {
            "frozen_policy": True,
            "metrics_computed_once": True,
            "no_tuning": True,
            "no_threshold_selection_on_forward": True,
            "no_labels_outcomes_beyond_scoring": True,
            "no_plots": True,
            "no_training_or_fitting": True,
            "sealed_files_unmodified": True,
            "guard_reference_runs_are_policy_inputs": True,
            "evidence": "v38/v33-identity RAW policies + v29 frozen iso maps + "
                        "B4 votes + L1 union + s0004 + band2 + dd_guard rules all "
                        "prespecified in v159 before running; dry-run was "
                        "signals-only on first 20 forward bars (no backtest, no "
                        "metrics, no writes); single full pass over 679 forward "
                        "decisions; sealed SHAs re-verified at start"},
        "input_sha256": {
            "sealed_candles": sha(FWD / "candles.parquet"),
            "sealed_funding": sha(FWD / "funding.parquet"),
            "sealed_macro": sha(FWD / "macro.parquet"),
            "decisions_forward": sha(FEAT / "decisions_forward.parquet"),
            "features": sha(FEAT / "features.npz"),
            "research_candles_warmup": sha(RESEARCH / "candles.parquet"),
            "research_config": sha(RESEARCH / "config.json"),
            **{f"calibrators_{s}": sha(CAL_DIR / m / "calibrators.json")
               for s, m in (("iso2", "isotonic_2"), ("iso4", "isotonic_4"),
                            ("isoall", "isotonic_all"))},
            "prespec": sha(SPEC_PATH),
            **{f"ckpt_v38_fold10_seed{s}": sha(
                V38 / f"seed{s}/checkpoints/fold_{FOLD_USED}/model.safetensors")
                for s in SEEDS},
            **{f"ckpt_v33_fold10_seed{s}": sha(
                V33 / f"seed{s}/checkpoints/fold_{FOLD_USED}/model.safetensors")
                for s in SEEDS},
            **{f"ckpt_v29_fold10_seed{s}": sha(
                V29 / f"seed{s}/checkpoints/fold_{FOLD_USED}/model.safetensors")
                for s in SEEDS}},
    }
    (out / "config.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    (out / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"),
                                          encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False,
                                                 default=str), encoding="utf-8")
    for branch in BRANCHES:
        vfile = out / f"verdict_forward_only_{branch}.json"
        cmd = [sys.executable, "scripts/opencode_forward_test.py", "--forward-only",
               "--forward-summary", str(out / "summary.json"),
               "--forward-trades", str(out / branch / "normal_trades.csv"),
               "--branch", branch, "--out", str(vfile)]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        print(proc.stdout, flush=True)
        if proc.returncode != 0:
            print(proc.stderr, flush=True)
            raise RuntimeError(f"forward-only verdict failed rc={proc.returncode} branch={branch}")
        verdict = json.loads(vfile.read_text(encoding="utf-8"))
        summary["machine_verdict"][branch] = {
            "mode": verdict.get("mode"), "decision": verdict.get("decision"),
            "decision_line": verdict.get("decision_line"),
            "decision_reasons": verdict.get("decision_reasons"),
            "forward": {k: verdict.get("forward", {}).get(k) for k in
                        ("status", "in_sample_baseline", "span", "forward_normal_monthly",
                         "margins_pass", "months_pass", "forward_decision", "forward_reasons")},
            "verdict_embedded_after": True,
            "metrics_recomputed": False}
        (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False,
                                                     default=str), encoding="utf-8")
    sums = [f"{sha(p)}  {p.relative_to(out).as_posix()}" for p in
            [*(b / f for b in (out / br for br in BRANCHES)
               for f in ("signals.parquet", "normal_trades.csv", "fee_stress_trades.csv",
                         "execution_stress_trades.csv")),
             out / "forward_predictions.npz", out / "summary.json",
             *[out / f"verdict_forward_only_{br}.json" for br in BRANCHES],
             out / "config.json", out / "driver_source.py"]]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps({"one_pass_complete": True, "branches": list(BRANCHES),
                      "per_branch_normal": {
                          b: {k: branches[b]["normal"][k] for k in
                              ("total_return", "monthly_geometric_net",
                               "max_drawdown", "trades", "profit_factor",
                               "win_rate")} for b in BRANCHES},
                      "machine_verdict": {b: summary["machine_verdict"][b]["decision"]
                                          for b in BRANCHES},
                      "out": str(out)}, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=Path("artifacts/research/opencode_v159_fwdevaltop3"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        dry_run()
    else:
        full_pass(args.output)
