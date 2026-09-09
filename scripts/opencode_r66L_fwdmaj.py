"""Opencode R66-L (v154): forward eval of the STANDING-BEST itself (s0004/majority).

Pre-spec: configs/opencode_v154_fwdmaj.json (written BEFORE this script ran;
driver asserts every frozen value before the one full pass).

Frozen legs: v29 residual-GRU fold-10 3-seed ensemble (combine penalty 0.0,
verbatim v02 plan) + FROZEN fold-10 iso2/iso4/isoall calibrator maps (fit
2025-12-01 vintage, latest labels 2025-11-22, all pre-cutoff, no refit) +
FROZEN v30 policy chain (choose per map + B4 majority vote with iso4 geometry
+ monthly cap 4 + cooldown 5d, grid/prices from research config).
Branches {majority_1x, majority_s0004_1x} (s0004 = 0<=UTC hour<4 pre-frequency
mask; cheap second branch in the SAME single pass). Metrics EXACTLY ONCE.

Local model sources are byte-identical to the v29 training bundle modulo
CRLF (verified pre-run); the parity gate proves the stack reproduces
training code (tol 1e-4), else STOP with no forward pass.

Modes:
  --dry-run : plumbing on FIRST 20 forward bars (signals-only: sealed SHA,
              lattice, sequence parity, checkpoint replay parity, 3-map
              calibrator schema, vote + policy schema).
              No backtest, no metrics, writes nothing.
  full pass : ONE pass over 679 forward decisions (inference timing recorded),
              then 3 ohlc-v2 backtests per branch (normal .0002 / fee .00055 /
              execution FillStress), monthly geometric over forward span,
              then forward-only verdict path per branch (subprocess,
              --forward-only), verdicts embedded into summary without
              recomputing metrics.

Outputs (new dir only): artifacts/research/opencode_v154_fwdmaj/
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

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import SwingStore, choose, grid, prices  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.residual_temporal_value import (  # noqa: E402
    ResidualTemporalValue, residual_predict)
from safetensors.torch import load_file  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v154_fwdmaj.json"
BRANCHES = ("majority_1x", "majority_s0004_1x")
CUTOFF = pd.Timestamp("2026-03-23T00:00:00Z")
STRIDE = 72
N_RESEARCH = 444096
N_FORWARD = 48819
N_DEC = 679
SEEDS = (1729, 1730, 1731)
FOLD_USED = 10
N_FOLDS = 11
PARITY_TOL = 1e-4
BATCH = 32
MAPS = ("isotonic_2", "isotonic_4", "isotonic_all")

FWD = ROOT / "data/processed/opencode_forward_20260323"
FEAT = FWD / "features"
RESEARCH = ROOT / "data/processed/swing_regime_research_v4"
V29 = ROOT / "artifacts/kaggle/v29_download/tcn-training"
CAL_DIR = ROOT / "artifacts/research/opencode_v02_reproduce_v30"


def sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert list(spec["branches"]) == list(BRANCHES), "branches phai la {majority_1x, majority_s0004_1x}"
    assert spec["ensemble"]["checkpoints_used"] == [
        f"artifacts/kaggle/v29_download/tcn-training/seed{s}"
        f"/checkpoints/fold_{FOLD_USED}/model.safetensors" for s in SEEDS]
    assert spec["calibrators"]["fold"] == FOLD_USED
    assert spec["forward_features"]["n_decisions"] == N_DEC
    assert spec["policy_frozen_ref"]["minimum_expected_net_percent"] == 0.3
    assert spec["policy_frozen_ref"]["minimum_fill_score"] == 0.25
    assert spec["fallback_scope"]["iso4_only_partial_used"] is False
    return spec


def verify_checkpoints() -> dict:
    found, missing = [], []
    for seed in SEEDS:
        for fold in range(N_FOLDS):
            q = V29 / f"seed{seed}/checkpoints/fold_{fold}/model.safetensors"
            (found if q.exists() else missing).append(str(q.relative_to(ROOT)))
    pred_found = sum(
        1 for seed in SEEDS for fold in range(N_FOLDS)
        if (V29 / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy").exists())
    audit = {"expected": 33, "found": len(found), "missing": missing,
             "predictions_npy_found": pred_found, "checkpoints_used_for_forward": 3,
             "used": [f"seed{s}/checkpoints/fold_{FOLD_USED}/model.safetensors" for s in SEEDS],
             "unused_recorded": 30}
    print(json.dumps({"verify_v29": audit}), flush=True)
    if missing:
        raise FileNotFoundError(
            f"STOP: thieu {len(missing)}/33 v29 checkpoints, khong thay the model/policy. {missing[:3]}")
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
        if rec["eligible_rows"] != spec["calibrators"]["maps"][short[m]]["eligible_rows"]:
            raise ValueError(f"{m} eligible_rows drift vs prespec")
        xv = np.asarray(rec["x"], dtype=np.float64)
        yv = np.asarray(rec["y"], dtype=np.float64)
        if not bool(np.all(np.diff(xv) >= 0)) or not bool(np.all(np.diff(yv) >= -1e-12)):
            raise ValueError(f"{m} fold-10 iso map not monotone")
        out[m] = {"x": xv, "y": yv, "asof": rec["asof"],
                  "eligible_rows": rec["eligible_rows"],
                  "latest_label_end": rec["latest_label_end"]}
    return out


def make_model(candidates: np.ndarray) -> ResidualTemporalValue:
    return ResidualTemporalValue(candidates, width=48, dropout=0.15)


def load_model(seed: int, candidates: np.ndarray, device: torch.device):
    model = make_model(candidates)
    ckpt = V29 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/model.safetensors"
    model.load_state_dict(load_file(str(ckpt)))
    model.eval()
    return model.to(device)


def parity_check(candidates: np.ndarray, device: torch.device) -> dict:
    out = {}
    for seed in SEEDS:
        rep = np.load(V29 / f"seed{seed}/checkpoints/fold_{FOLD_USED}/replay.npz",
                      allow_pickle=False)
        cloud = np.load(V29 / f"seed{seed}/temporal_neural/fold_{FOLD_USED}/predictions.npy",
                        allow_pickle=False)
        if rep["predictions"].shape != (8, 16, 6) or rep["sequences"].shape != (8, 5, 128, 6):
            raise ValueError(f"seed{seed} replay shape drift")
        if rep["features"].shape != (8, 40):
            raise ValueError(f"seed{seed} replay feat40 shape drift")
        if not np.allclose(rep["predictions"], cloud[:8], rtol=0, atol=0):
            raise ValueError(f"seed{seed} replay != cloud predictions[:8] (artifact relation broken)")
        model = load_model(seed, candidates, device)
        local = residual_predict(model, rep["sequences"], rep["features"], batch_size=BATCH)
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
                    idx: np.ndarray, flat: np.ndarray):
    seqs, feats, closes, a5, a4 = [], [], [], [], []
    for j, k in enumerate(idx):
        ts = pd.Timestamp(decisions["signal_time"].iloc[int(k)])
        w, _, _, feat40, atr5, atr4 = store.sample(ts)
        np.testing.assert_allclose(feat40, flat[int(k), :40], rtol=1e-6, atol=1e-6)
        seqs.append(encode_windows(w))
        feats.append(np.asarray(feat40, dtype=np.float32))
        closes.append(float(candles["close"].iloc[int(
            decisions["bar_index_concat"].iloc[int(k)])]))
        a5.append(float(atr5))
        a4.append(float(atr4))
    seqs = np.stack(seqs).astype(np.float32)
    feats = np.stack(feats).astype(np.float32)
    if seqs.shape[1:] != (5, 128, 6) or not np.isfinite(seqs).all():
        raise ValueError("Bad forward sequences")
    if feats.shape[1:] != (40,) or not np.isfinite(feats).all():
        raise ValueError("Bad forward feat40")
    return seqs, feats, np.asarray(closes), np.asarray(a5), np.asarray(a4)


def dir_of(out) -> int:
    if out.get("action") == "LONG":
        return 1
    if out.get("action") == "SHORT":
        return -1
    return 0


def gen_forward(mask: np.ndarray, iso4_outs: list, decisions: pd.DataFrame, idx: np.ndarray,
                closes: np.ndarray, a5: np.ndarray, a4: np.ndarray, cfg: dict) -> pd.DataFrame:
    """B4 gen_from_mask adapted to the forward lattice (pre-filtered mask +
    IDENTICAL frequency loop; emits iso4 choose() geometry)."""
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


_CLOSE_TIMES = None


def store_close_time(bar: int):
    return _CLOSE_TIMES[bar]


def infer_all(candidates: np.ndarray, seqs: np.ndarray, feats: np.ndarray,
              device: torch.device):
    t0 = time.perf_counter()
    per_seed_s = {}
    outs = []
    for seed in SEEDS:
        s0 = time.perf_counter()
        model = load_model(seed, candidates, device)
        outs.append(residual_predict(model, seqs, feats, batch_size=BATCH))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        per_seed_s[f"seed{seed}"] = time.perf_counter() - s0
    stacked = np.stack(outs).astype(np.float64)
    if stacked.shape != (3, len(seqs), 16, 6) or not np.isfinite(stacked).all():
        raise ValueError(f"Bad stacked predictions {stacked.shape}")
    base, details = combine(stacked, 0.0)
    secs = time.perf_counter() - t0
    timing = {"inference_seconds_total": secs, "per_seed_seconds": per_seed_s,
              "seconds_per_window": secs / max(len(seqs), 1), "device": str(device),
              "batch": BATCH}
    return np.asarray(base, dtype=np.float64), details, timing


def calibrate_all(base: np.ndarray, details: dict, calibs: dict) -> dict:
    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    if score.shape != fill.shape or score.shape[1:] != (16,):
        raise ValueError("Bad ensemble detail shapes")
    fclip = np.clip(fill, 1e-6, 1 - 1e-6)
    outs = {}
    for m in MAPS:
        mapped = np.interp(score.ravel(), calibs[m]["x"], calibs[m]["y"]).reshape(score.shape)
        pred = np.asarray(base, dtype=np.float64).copy()
        pred[..., 0] = mapped / fill
        outs[m] = pred
    return outs


def choose_all(preds: dict, closes: np.ndarray, a5: np.ndarray, a4: np.ndarray,
               cfg: dict):
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
    d2, d4, dall = dirs["isotonic_2"], dirs["isotonic_4"], dirs["isotonic_all"]
    n = len(idx)
    mask_majority = np.array([
        (d4[j] != 0) and ([d2[j], d4[j], dall[j]].count(int(d4[j])) >= 2)
        for j in range(n)], dtype=bool)
    hours = pd.to_datetime(decisions["signal_time"].iloc[idx], utc=True).dt.hour.to_numpy()
    mask_session = (hours >= 0) & (hours < 4)
    masks = {"majority": mask_majority,
             "majority_s0004": mask_majority & mask_session}
    agreement = {
        "n_rows": int(n),
        "nonwait_iso2": int((d2 != 0).sum()),
        "nonwait_iso4": int((d4 != 0).sum()),
        "nonwait_isoall": int((dall != 0).sum()),
        "pass_majority": int(mask_majority.sum()),
        "pass_majority_s0004": int(masks["majority_s0004"].sum()),
        "agree_majority_given_iso4": float(mask_majority.sum() / (d4 != 0).sum())
        if (d4 != 0).sum() else 0.0,
    }
    return masks, agreement


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
    calibs = load_calibrators(spec)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    parity = parity_check(candidates, device)
    global _CLOSE_TIMES
    _CLOSE_TIMES = pd.to_datetime(candles["close_time"], utc=True).reset_index(drop=True)
    store = SwingStore(candles, cfg)
    sub = np.arange(20, dtype=np.int64)
    seqs, feats, closes, a5, a4 = build_sequences(store, candles, decisions, sub, flat)
    base, details, timing = infer_all(candidates, seqs, feats, device)
    preds = calibrate_all(base, details, calibs)
    outs, dirs = choose_all(preds, closes, a5, a4, cfg)
    masks, agreement = vote_masks(dirs, decisions, sub)
    frames = {}
    for branch in BRANCHES:
        key = "majority" if branch == "majority_1x" else "majority_s0004"
        frames[branch] = gen_forward(masks[key], outs["isotonic_4"], decisions,
                                     sub, closes, a5, a4, cfg)
    need = {"bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
            "take_profit_1", "take_profit_2", "holding_bars"}
    for branch, frame in frames.items():
        if len(frame) and not need.issubset(set(frame.columns)):
            raise ValueError(f"{branch} signal schema drift: {sorted(set(frame.columns))}")
        if len(frame) and not set(frame["direction"].unique()).issubset({-1, 1}):
            raise ValueError(f"{branch} direction not in {{-1,1}}")
    print(json.dumps({"dry_run_plumbing": "OK", "n_windows": 20,
                      "forward_rows": "first 20 post-cutoff (no pre-cutoff substitute)",
                      "parity_max_abs_diff": parity, "agreement_row_level": agreement,
                      "n_signals": {b: int(len(f)) for b, f in frames.items()},
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
    calibs = load_calibrators(spec)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    if candidates.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    parity = parity_check(candidates, device)
    global _CLOSE_TIMES
    _CLOSE_TIMES = pd.to_datetime(candles["close_time"], utc=True).reset_index(drop=True)
    store = SwingStore(candles, cfg)
    idx = np.arange(N_DEC, dtype=np.int64)
    seqs, feats, closes, a5, a4 = build_sequences(store, candles, decisions, idx, flat)
    base, details, timing = infer_all(candidates, seqs, feats, device)
    preds = calibrate_all(base, details, calibs)
    outs, dirs = choose_all(preds, closes, a5, a4, cfg)
    masks, agreement = vote_masks(dirs, decisions, idx)

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
    branches, frames = {}, {}
    for branch in BRANCHES:
        key = "majority" if branch == "majority_1x" else "majority_s0004"
        frame = gen_forward(masks[key], outs["isotonic_4"], decisions,
                            idx, closes, a5, a4, cfg)
        frames[branch] = frame
        empty = frame.iloc[0:0].drop(columns=["leverage"], errors="ignore")
        exec_sig = frame.drop(columns=["leverage"], errors="ignore").copy() if len(frame) \
            else empty.copy()
        scen = run_branch(candles, exec_sig, costs, fee_costs, exec1x, years)
        bdir = out / branch
        bdir.mkdir(parents=True)
        frame.to_parquet(bdir / "signals.parquet", index=False)
        bres = {}
        for label in ("normal", "fee_stress", "execution_stress"):
            items = scen[label].pop("_trades")
            rows = [asdict(t) for t in items]
            pd.DataFrame(rows).to_csv(bdir / f"{label}_trades.csv", index=False)
            d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                 for k, v in scen[label].items() if k != "diagnostics"}
            if label == "execution_stress":
                d["diagnostics"] = scen[label].get("diagnostics")
            d["gate"] = flags(d)
            bres[label] = d
        branches[branch] = bres
    np.savez_compressed(out / "forward_predictions.npz",
                        ensemble_base=np.asarray(base, dtype=np.float32),
                        selection_score_percent=np.asarray(
                            details["selection_score_percent"], dtype=np.float32),
                        mean_fill_score=np.asarray(details["mean_fill_score"], dtype=np.float32),
                        **{f"calibrated_{s}": np.asarray(preds[m], dtype=np.float32)
                           for s, m in (("iso2", "isotonic_2"), ("iso4", "isotonic_4"),
                                        ("isoall", "isotonic_all"))})

    def exit_span_of(branch: str):
        if not branches[branch]["normal"]["trades"]:
            return [None, None]
        ex = pd.read_csv(out / branch / "normal_trades.csv", usecols=["exit_time"])
        col = pd.to_datetime(ex["exit_time"], utc=True)
        return [str(col.min()), str(col.max())]

    summary = {
        "experiment": "opencode-r66L-fwdmaj",
        "prespec": "configs/opencode_v154_fwdmaj.json",
        "pass": 1,
        "pass_note": "ONE evaluation pass; no pass-2 has occurred",
        "branches": branches,
        "seal": {"cutoff_exclusive": "2026-03-23T00:00:00+00:00",
                 "state": "PRISTINE per SEAL.json + ledger forward_window rule"},
        "frozen_refs": {
            "checkpoints": ck_audit,
            "calibrators": {s: {"path": f"artifacts/research/opencode_v02_reproduce_v30/{m}/calibrators.json",
                                "fold": FOLD_USED, "asof": calibs[m]["asof"],
                                "eligible_rows": calibs[m]["eligible_rows"],
                                "latest_label_end": calibs[m]["latest_label_end"]}
                            for s, m in (("iso2", "isotonic_2"), ("iso4", "isotonic_4"),
                                         ("isoall", "isotonic_all"))},
            "policy": spec["policy_frozen_ref"],
            "parity_max_abs_diff": parity},
        "clock": {"n_decisions": N_DEC, "stride_bars": STRIDE,
                  "first_signal": str(pd.to_datetime(
                      decisions["signal_time"].iloc[0], utc=True)),
                  "last_signal": str(pd.to_datetime(
                      decisions["signal_time"].iloc[-1], utc=True)),
                  "matches_E_fwfeatures": True},
        "vote_outcome": agreement,
        "signals_composition": {
            b: {"n_signals": int(len(f)),
                "n_long": int((f["direction"] == 1).sum()) if len(f) else 0,
                "n_short": int((f["direction"] == -1).sum()) if len(f) else 0}
            for b, f in frames.items()},
        "span": {"forward_first_open": str(first_open),
                 "forward_last_close": str(last_close),
                 "years": years,
                 "exit_span_normal": {b: exit_span_of(b) for b in BRANCHES}},
        "inference": timing,
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
            "fallback_iso4_only_partial_used": False,
            "evidence": "v29 fold-10 ensemble + frozen fold-10 iso2/iso4/isoall maps + "
                        "B4 majority vote (iso4 geometry) + cap4/cd5 all prespecified "
                        "in v154 before running; dry-run was signals-only on first 20 "
                        "forward bars (no backtest, no metrics, no writes); single full "
                        "pass over 679 forward decisions; sealed SHAs re-verified at "
                        "start; no label/return/pnl columns beyond engine fills"},
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
            **{f"ckpt_fold10_seed{s}": sha(
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
                      "n_signals": {b: int(len(frames[b])) for b in BRANCHES},
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
                    default=Path("artifacts/research/opencode_v154_fwdmaj"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        dry_run()
    else:
        full_pass(args.output)