"""Opencode R49-L (v135): FIRST real forward eval - v38-isoall calibrated leg on sealed window.

Pre-spec: configs/opencode_v135_fwdeval38.json (written BEFORE this script ran;
driver asserts every frozen value before the one full pass).

Frozen leg: fold-10 (last walk-forward fold) 3-seed ensemble (combine penalty 0.0,
verbatim v59 audit) + FROZEN fold-10 isoall calibrator map (fit <=2025-11-22,
pre-cutoff, no refit) + FROZEN v38 policy (gate en_best_cal>0.0 + top-8 fallback,
monthly cap 4 + cooldown 5d, geometry grid/prices from research config).
Branches {1x} only. Metrics EXACTLY ONCE.

Modes:
  --dry-run : plumbing on FIRST 20 forward bars (signals-only: sealed SHA,
              lattice, sequence parity, checkpoint replay parity, policy schema).
              No backtest, no metrics, writes nothing.
  full pass : ONE pass over 679 forward decisions (inference timing recorded),
              then 3 ohlc-v2 backtests (normal .0002 / fee .00055 /
              execution FillStress), monthly geometric over forward span,
              then forward-only verdict path (subprocess, --forward-only),
              verdict embedded into summary without recomputing metrics.

Outputs (new dir only): artifacts/research/opencode_v135_fwdeval38/
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
from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import SwingStore, grid, prices  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from opencode_r9m_nextarch_model import SelectiveSSMTemporal, predict_ssm  # noqa: E402 (exact training code)
from safetensors.torch import load_file  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v135_fwdeval38.json"
BRANCH = "v38_isoall_fwd_1x"
CUTOFF = pd.Timestamp("2026-03-23T00:00:00Z")
STRIDE = 72
N_RESEARCH = 444096
N_FORWARD = 48819
N_DEC = 679
SEEDS = (1729, 1730, 1731)
FOLD_USED = 10
N_FOLDS = 11
POLICY_MARGIN = 0.0
POLICY_N_MIN = 8
PARITY_TOL = 1e-4
BATCH = 32

FWD = ROOT / "data/processed/opencode_forward_20260323"
FEAT = FWD / "features"
RESEARCH = ROOT / "data/processed/swing_regime_research_v4"
V38 = ROOT / "artifacts/kaggle/v38_rankloss_download/rankloss-training"
CALIBRATORS = ROOT / "artifacts/research/opencode_v59_v38cal/v38-isoall/calibrators.json"


def sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["branches"] == [BRANCH], "branches phai la {1x} only"
    assert spec["ensemble"]["checkpoints_used"] == [
        f"artifacts/kaggle/v38_rankloss_download/rankloss-training/seed{s}"
        f"/checkpoints/fold_{FOLD_USED}/model.safetensors" for s in SEEDS]
    assert spec["calibrator"]["fold"] == FOLD_USED
    assert spec["forward_features"]["n_decisions"] == N_DEC
    assert POLICY_MARGIN == 0.0 and POLICY_N_MIN == 8, "policy floor pre-spec"
    return spec


def verify_checkpoints() -> dict:
    found, missing = [], []
    for seed in SEEDS:
        for fold in range(N_FOLDS):
            q = V38 / f"seed{seed}/checkpoints/fold_{fold}/model.safetensors"
            (found if q.exists() else missing).append(str(q.relative_to(ROOT)))
    pred_found = sum(
        1 for seed in SEEDS for fold in range(N_FOLDS)
        if (V38 / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy").exists())
    audit = {"expected": 33, "found": len(found), "missing": missing,
             "predictions_npy_found": pred_found, "checkpoints_used_for_forward": 3,
             "used": [f"seed{s}/checkpoints/fold_{FOLD_USED}/model.safetensors" for s in SEEDS],
             "unused_recorded": 30}
    print(json.dumps({"verify_v38": audit}), flush=True)
    if missing:
        raise FileNotFoundError(
            f"STOP: thieu {len(missing)}/33 v38 checkpoints, khong thay the model/policy. {missing[:3]}")
    return audit


def load_concat(spec: dict):
    fz = json.loads((FWD / "manifest.json").read_text(encoding="utf-8"))
    for key, name in (("candles", "candles.parquet"), ("funding", "funding.parquet"),
                      ("macro", "macro.parquet")):
        if sha(FWD / name) != fz[key]["sha256"]:
            raise ValueError(f"Sealed hash mismatch: {name}")
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


def load_calibrator() -> dict:
    doc = json.loads(CALIBRATORS.read_text(encoding="utf-8"))
    recs = [r for r in doc["records"] if r["fold"] == FOLD_USED]
    if len(recs) != 1:
        raise ValueError("Fold-10 calibrator record missing/ambiguous")
    rec = recs[0]
    if rec.get("warmup") is not None or not rec.get("x") or not rec.get("y"):
        raise ValueError("Fold-10 calibrator not a fitted map")
    if pd.Timestamp(rec["asof"], tz="UTC") >= CUTOFF:
        raise ValueError("Calibrator asof not pre-cutoff")
    if pd.Timestamp(rec["latest_label_end"], tz="UTC") >= CUTOFF:
        raise ValueError("Calibrator fitted on post-cutoff labels")
    xv = np.asarray(rec["x"], dtype=np.float64)
    yv = np.asarray(rec["y"], dtype=np.float64)
    if not bool(np.all(np.diff(xv) >= 0)) or not bool(np.all(np.diff(yv) >= -1e-12)):
        raise ValueError("Fold-10 iso map not monotone")
    return {"x": xv, "y": yv, "asof": rec["asof"],
            "eligible_rows": rec["eligible_rows"],
            "latest_label_end": rec["latest_label_end"]}


def make_model(candidates: np.ndarray) -> SelectiveSSMTemporal:
    return SelectiveSSMTemporal(candidates, n_flat=133, frame_dim=64,
                                frame_state=16, frame_layers=2,
                                cross_state=16, dropout=0.1)


def load_model(seed: int, candidates: np.ndarray, device: torch.device):
    model = make_model(candidates)
    ckpt = V38 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors"
    model.load_state_dict(load_file(str(ckpt)))
    model.eval()
    return model.to(device)


def parity_check(candidates: np.ndarray, device: torch.device) -> dict:
    out = {}
    for seed in SEEDS:
        rep = np.load(V38 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/replay.npz",
                      allow_pickle=False)
        cloud = np.load(V38 / f"seed{seed}/temporal_neural/fold_{FOLD_USED}/predictions.npy",
                        allow_pickle=False)
        if rep["predictions"].shape != (8, 16, 6) or rep["sequences"].shape != (8, 5, 128, 6):
            raise ValueError(f"seed{seed} replay shape drift")
        if not np.allclose(rep["predictions"], cloud[:8], rtol=0, atol=0):
            raise ValueError(f"seed{seed} replay != cloud predictions[:8] (artifact relation broken)")
        model = load_model(seed, candidates, device)
        local = predict_ssm(model, rep["sequences"], rep["features"], batch_size=BATCH)
        err = float(np.max(np.abs(local - rep["predictions"].astype(np.float64))))
        out[f"seed{seed}"] = err
        print(json.dumps({"parity": {"seed": seed, "max_abs_diff": err,
                                     "tol": PARITY_TOL, "pass": err <= PARITY_TOL}}), flush=True)
        if err > PARITY_TOL:
            raise ValueError(f"STOP: seed{seed} local inference != cloud ({err} > {PARITY_TOL})")
        del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return out


def build_sequences(store: SwingStore, candles: pd.DataFrame, decisions: pd.DataFrame,
                    idx: np.ndarray, flat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    seqs, closes, a5, a4 = [], [], [], []
    for j, k in enumerate(idx):
        ts = pd.Timestamp(decisions["signal_time"].iloc[k])
        w, _, _, feat40, atr5, atr4 = store.sample(ts)
        np.testing.assert_allclose(feat40, flat[k, :40], rtol=1e-6, atol=1e-6)
        seqs.append(encode_windows(w))
        closes.append(float(candles["close"].iloc[int(
            decisions["bar_index_concat"].iloc[k])]))
        a5.append(float(atr5))
        a4.append(float(atr4))
    seqs = np.stack(seqs).astype(np.float32)
    if seqs.shape[1:] != (5, 128, 6) or not np.isfinite(seqs).all():
        raise ValueError("Bad forward sequences")
    return seqs, np.asarray(closes), np.asarray(a5), np.asarray(a4)


def v38_policy_signals(iso_pred: np.ndarray, decisions: pd.DataFrame, idx: np.ndarray,
                       closes: np.ndarray, a5: np.ndarray, a4: np.ndarray,
                       cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Ban sao VERBATIM v38_policy_signals (v59 driver), single forward group."""
    pred = np.asarray(iso_pred, dtype=np.float64)
    fill = 1 / (1 + np.exp(-np.clip(pred[..., 4], -40, 40)))
    expected = pred[..., 0] * fill
    en_best = expected.max(1)
    gate = np.flatnonzero(en_best > POLICY_MARGIN)
    info = {"gate_hits": int(len(gate)), "n_forward": int(len(idx))}
    if len(gate) >= POLICY_N_MIN:
        selected = set(gate.tolist())
        info["fallback_adds"] = 0
    else:
        top = np.argsort(-en_best, kind="stable")[:min(POLICY_N_MIN, len(idx))]
        selected = set(gate.tolist()) | set(top.tolist())
        info["fallback_adds"] = int(len(set(top.tolist()) - set(gate.tolist())))
    info["n_selected"] = len(selected)
    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    if cand_grid.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    policy, signals = cfg["policy"], []
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    n_wait_ineligible = 0
    order = np.argsort([pd.Timestamp(decisions["signal_time"].iloc[k]).value for k in idx],
                       kind="stable")
    for j in order:
        if int(j) not in selected:
            continue
        k = int(idx[j])
        timestamp = pd.Timestamp(decisions["signal_time"].iloc[k])
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        elig = np.flatnonzero(fill[j] >= policy["minimum_fill_score"])
        if not len(elig):
            n_wait_ineligible += 1
            continue
        kk = int(elig[np.argmax(expected[j, elig])])
        bar = int(decisions["bar_index_concat"].iloc[k])
        if pd.to_datetime(store_close_time(bar), utc=True) != timestamp:
            raise ValueError("Signal not at closed-candle time (causality)")
        signals.append({"bar_index": bar, "signal_time": timestamp, "fold_test": -1,
                        "direction": int(cand_grid[kk, 0]), "candidate_id": kk,
                        **prices(float(closes[j]), float(a5[j]), float(a4[j]),
                                 cand_grid[kk], cfg),
                        "expected_net_percent": float(expected[j, kk]),
                        "en_best": float(en_best[j]),
                        "ohlc_fill_score": float(fill[j, kk]),
                        "calibrated": True, "entry_expiry_bars": cfg["entry_expiry_bars"],
                        "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    frame = pd.DataFrame(signals)
    info.update({"n_signals": len(frame), "n_wait_no_fill_eligible": n_wait_ineligible,
                 "policy_margin": POLICY_MARGIN, "policy_n_min": POLICY_N_MIN,
                 "monthly_cap": policy["maximum_signals_per_month"],
                 "cooldown_days": policy["cooldown_days"]})
    return frame, info


_CLOSE_TIMES = None


def store_close_time(bar: int):
    return _CLOSE_TIMES[bar]


def infer_all(candidates: np.ndarray, seqs: np.ndarray, flat: np.ndarray,
              device: torch.device) -> tuple[np.ndarray, dict, float]:
    t0 = time.perf_counter()
    per_seed_s = {}
    outs = []
    for seed in SEEDS:
        s0 = time.perf_counter()
        model = load_model(seed, candidates, device)
        outs.append(predict_ssm(model, seqs, flat.astype(np.float32), batch_size=BATCH))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        per_seed_s[f"seed{seed}"] = time.perf_counter() - s0
    stacked = np.stack(outs).astype(np.float64)
    if stacked.shape != (3, len(seqs), 16, 6) or not np.isfinite(stacked).all():
        raise ValueError(f"Bad stacked predictions {stacked.shape}")
    ensemble, details = combine(stacked, 0.0)
    secs = time.perf_counter() - t0
    timing = {"inference_seconds_total": secs, "per_seed_seconds": per_seed_s,
              "seconds_per_window": secs / max(len(seqs), 1), "device": str(device),
              "batch": BATCH}
    return np.asarray(ensemble, dtype=np.float64), details, timing


def calibrate(details: dict, calib: dict) -> tuple[np.ndarray, np.ndarray]:
    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    if score.shape != fill.shape or score.shape[1] != 16:
        raise ValueError("Bad ensemble detail shapes")
    mapped = np.interp(score.ravel(), calib["x"], calib["y"]).reshape(score.shape)
    return mapped, fill


def run_branch(candles: pd.DataFrame, signals: pd.DataFrame, costs: CostModel,
               fee_costs: CostModel, exec1x: ExecutionConfig, years: float):
    fee_only = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    assert abs(fee_only.fee_rate_per_fill - fee_costs.fee_rate_per_fill) < 1e-12, \
        "fee stress .00055 pre-spec"
    normal, trades = run_backtest(candles, signals, 100, costs, exec1x)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, exec1x)
    stress, st, diag = run_stress(candles, signals, 100, costs, exec1x,
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


def dry_run() -> None:
    spec = load_spec()
    verify_checkpoints()
    candles, decisions, grid_idx = load_concat(spec)
    flat = load_flat()
    cfg = json.loads((RESEARCH / "config.json").read_text(encoding="utf-8"))
    calib = load_calibrator()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    parity = parity_check(candidates, device)
    global _CLOSE_TIMES
    _CLOSE_TIMES = pd.to_datetime(candles["close_time"], utc=True).reset_index(drop=True)
    store = SwingStore(candles, cfg)
    sub = np.arange(20, dtype=np.int64)
    seqs, closes, a5, a4 = build_sequences(store, candles, decisions, sub, flat)
    ensemble, details, timing = infer_all(candidates, seqs, flat[sub], device)
    mapped, fill = calibrate(details, calib)
    iso_pred = np.zeros((len(sub), 16, 6), dtype=np.float64)
    iso_pred[..., 0] = mapped / fill
    iso_pred[..., 4] = np.log(np.clip(fill, 1e-6, 1 - 1e-6) / (1 - np.clip(fill, 1e-6, 1 - 1e-6)))
    signals, info = v38_policy_signals(iso_pred, decisions, sub, closes, a5, a4, cfg)
    need = {"bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
            "take_profit_1", "take_profit_2", "holding_bars"}
    if not need.issubset(set(signals.columns)) and len(signals):
        raise ValueError(f"signal schema drift: {sorted(set(signals.columns))}")
    if len(signals) and not set(signals["direction"].unique()).issubset({-1, 1}):
        raise ValueError("direction not in {-1,1}")
    print(json.dumps({"dry_run_plumbing": "OK", "n_windows": 20,
                      "forward_rows": "first 20 post-cutoff (no pre-cutoff substitute)",
                      "parity_max_abs_diff": parity, "policy_info": info,
                      "infer_timing": timing, "pre_cutoff_only": False,
                      "writes": "none",
                      "metrics": "none (signals-only, no backtest)"}, default=str))


def full_pass(out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"Khong ghi de: {out} da ton tai")
    spec = load_spec()
    ck_audit = verify_checkpoints()
    candles, decisions, grid_idx = load_concat(spec)
    flat = load_flat()
    cfg = json.loads((RESEARCH / "config.json").read_text(encoding="utf-8"))
    calib = load_calibrator()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    if candidates.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    parity = parity_check(candidates, device)
    global _CLOSE_TIMES
    _CLOSE_TIMES = pd.to_datetime(candles["close_time"], utc=True).reset_index(drop=True)
    store = SwingStore(candles, cfg)
    idx = np.arange(N_DEC, dtype=np.int64)
    seqs, closes, a5, a4 = build_sequences(store, candles, decisions, idx, flat)
    ensemble, details, timing = infer_all(candidates, seqs, flat, device)
    mapped, fill = calibrate(details, calib)
    iso_pred = np.zeros((N_DEC, 16, 6), dtype=np.float64)
    iso_pred[..., 0] = mapped / fill
    fclip = np.clip(fill, 1e-6, 1 - 1e-6)
    iso_pred[..., 4] = np.log(fclip / (1 - fclip))
    signals, info = v38_policy_signals(iso_pred, decisions, idx, closes, a5, a4, cfg)

    fw_candles = pd.read_parquet(FWD / "candles.parquet")
    first_open = pd.to_datetime(fw_candles["open_time"], utc=True).min()
    last_close = pd.to_datetime(fw_candles["close_time"], utc=True).max()
    years = (last_close - first_open).total_seconds() / (365.2425 * 86400)

    costs = CostModel(**cfg["costs"])
    fee_costs = CostModel(**spec["backtest"]["costs_fee_stress"])
    cap = int(max(cfg["holding_days"]) * 288)
    assert cap == 2016 == spec["backtest"]["execution"]["max_holding_bars"], "holding cap"
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    empty = signals.iloc[0:0].drop(columns=["leverage"], errors="ignore")
    exec_sig = signals.drop(columns=["leverage"], errors="ignore").copy() if len(signals) \
        else empty.copy()
    scen = run_branch(candles, exec_sig, costs, fee_costs, exec1x, years)

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

    bdir = out / BRANCH
    bdir.mkdir(parents=True)
    signals.to_parquet(bdir / "signals.parquet", index=False)
    branches = {}
    for label in ("normal", "fee_stress", "execution_stress"):
        items = scen[label].pop("_trades")
        rows = [asdict(t) for t in items]
        pd.DataFrame(rows).to_csv(bdir / f"{label}_trades.csv", index=False)
        d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
             for k, v in scen[label].items() if k != "diagnostics"}
        if label == "execution_stress":
            d["diagnostics"] = scen[label].get("diagnostics")
        d["gate"] = flags(d)
        branches[label] = d
    np.savez_compressed(bdir / "forward_predictions.npz",
                        ensemble_combined=np.asarray(ensemble, dtype=np.float32),
                        selection_score_percent=np.asarray(
                            details["selection_score_percent"], dtype=np.float32),
                        mean_fill_score=np.asarray(details["mean_fill_score"], dtype=np.float32),
                        mapped_calibrated=np.asarray(mapped, dtype=np.float32))

    n_ex = pd.read_csv(bdir / "normal_trades.csv", usecols=["exit_time"]) \
        if branches["normal"]["trades"] else None
    exit_span = [str(pd.to_datetime(n_ex["exit_time"], utc=True).min()),
                 str(pd.to_datetime(n_ex["exit_time"], utc=True).max())] \
        if n_ex is not None else [None, None]
    summary = {
        "experiment": "opencode-r49L-fwdeval38",
        "prespec": "configs/opencode_v135_fwdeval38.json",
        "pass": 1,
        "pass_note": "ONE evaluation pass; no pass-2 has occurred",
        "branch": BRANCH,
        "branches": {BRANCH: branches},
        "seal": {"cutoff_exclusive": "2026-03-23T00:00:00+00:00",
                 "state": "PRISTINE per SEAL.json + ledger forward_window rule"},
        "frozen_refs": {
            "checkpoints": ck_audit,
            "calibrator": {"path": "artifacts/research/opencode_v59_v38cal/v38-isoall/calibrators.json",
                           "fold": FOLD_USED, "asof": calib["asof"],
                           "eligible_rows": calib["eligible_rows"],
                           "latest_label_end": calib["latest_label_end"]},
            "policy": spec["policy_frozen_ref"],
            "parity_max_abs_diff": parity},
        "clock": {"n_decisions": N_DEC, "stride_bars": STRIDE,
                  "first_signal": str(pd.to_datetime(
                      decisions["signal_time"].iloc[0], utc=True)),
                  "last_signal": str(pd.to_datetime(
                      decisions["signal_time"].iloc[-1], utc=True)),
                  "matches_E_fwfeatures": True},
        "policy_outcome": info,
        "signals_composition": {
            "n_signals": int(len(signals)),
            "n_long": int((signals["direction"] == 1).sum()) if len(signals) else 0,
            "n_short": int((signals["direction"] == -1).sum()) if len(signals) else 0},
        "span": {"forward_first_open": str(first_open),
                 "forward_last_close": str(last_close),
                 "years": years, "exit_span_normal": exit_span,
                 "n_calendar_months_exit_span":
                     int(len(pd.period_range(exit_span[0][:7], exit_span[1][:7], freq="M")))
                     if exit_span[0] else 0},
        "inference": timing,
        "machine_verdict": None,
        "seal_affirmation": {
            "frozen_policy": True,
            "metrics_computed_once": True,
            "no_tuning": True,
            "no_threshold_selection_on_forward": True,
            "no_labels_outcomes_beyond_scoring": True,
            "no_plots": True,
            "no_training_or_fitting": True,
            "sealed_files_unmodified": True,
            "evidence": "fold-10 ensemble + fold-10 iso map + v38 policy all prespecified "
                        "in v135 before running; dry-run was signals-only on first 20 "
                        "forward bars (no backtest, no metrics, no writes); single full "
                        "pass; sealed SHAs re-verified at start; no label/return/pnl "
                        "columns beyond engine fills"},
        "input_sha256": {
            "sealed_candles": sha(FWD / "candles.parquet"),
            "sealed_funding": sha(FWD / "funding.parquet"),
            "sealed_macro": sha(FWD / "macro.parquet"),
            "decisions_forward": sha(FEAT / "decisions_forward.parquet"),
            "features": sha(FEAT / "features.npz"),
            "research_candles_warmup": sha(RESEARCH / "candles.parquet"),
            "research_config": sha(RESEARCH / "config.json"),
            "calibrators": sha(CALIBRATORS),
            "prespec": sha(SPEC_PATH),
            **{f"ckpt_fold10_seed{s}": sha(
                V38 / f"seed{s}/checkpoints/fold_{FOLD_USED}/model.safetensors")
                for s in SEEDS}},
    }
    (out / "config.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    (out / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"),
                                          encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False,
                                                 default=str), encoding="utf-8")
    cmd = [sys.executable, "scripts/opencode_forward_test.py", "--forward-only",
           "--forward-summary", str(out / "summary.json"),
           "--forward-trades", str(bdir / "normal_trades.csv"),
           "--branch", BRANCH, "--out", str(out / "verdict_forward_only.json")]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    print(proc.stdout, flush=True)
    if proc.returncode != 0:
        print(proc.stderr, flush=True)
        raise RuntimeError(f"forward-only verdict failed rc={proc.returncode}")
    verdict = json.loads((out / "verdict_forward_only.json").read_text(encoding="utf-8"))
    summary["machine_verdict"] = {
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
            (bdir / "signals.parquet", bdir / "normal_trades.csv",
             bdir / "fee_stress_trades.csv", bdir / "execution_stress_trades.csv",
             bdir / "forward_predictions.npz", out / "summary.json",
             out / "verdict_forward_only.json", out / "config.json",
             out / "driver_source.py")]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    mo = branches["normal"]["monthly_geometric_net"]
    print(json.dumps({"one_pass_complete": True, "branch": BRANCH,
                      "n_signals": len(signals),
                      "normal": {k: branches["normal"][k] for k in
                                 ("total_return", "monthly_geometric_net",
                                  "max_drawdown", "trades", "profit_factor",
                                  "win_rate")},
                      "fee_stress_monthly": branches["fee_stress"]["monthly_geometric_net"],
                      "exec_monthly": branches["execution_stress"]["monthly_geometric_net"],
                      "exec_trades": branches["execution_stress"]["trades"],
                      "machine_verdict": summary["machine_verdict"]["decision"],
                      "out": str(out)}, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=Path("artifacts/research/opencode_v135_fwdeval38"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        dry_run()
    else:
        full_pass(args.output)
