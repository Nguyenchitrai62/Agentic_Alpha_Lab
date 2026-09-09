"""Opencode R-DIAGNOSTIC (round40): TRUE val-fit calibrate-first on v41 predictions.

Pre-spec: configs/opencode_v112_v41valfit.json (viet TRUOC khi chay).
Frozen inputs: artifacts/kaggle/v41_acc2_download/valuescale-training (33 test
  predictions + 33 val predictions = 11 folds x 3 seeds, map-v8 RAW TRADEABLE
  percent (n,16,6), VERIFY presence else STOP),
  data/processed/swing_regime_research_v4/{decisions.parquet,examples.npz,
  candles.parquet,config.json}.
Method (causal, frozen constants): per-fold IsotonicRegression fit on VAL
  predictions/labels ONLY (never test; record per-fold; warmup rule pre-spec),
  applied to test predictions; then standard gate (v41 policy floor unchanged:
  en_best > 0.0 + coverage fallback top-8/fold, record bindings). Differs from
  nested-val-proxy attempts: TRUE held-out val per fold.
Branches (1x): v41-identity (control, phai khop R-audit rank_en_1x normal
  +39.0%/-33.4%/75 trong 1e-9 + exact hoac STOP),
  v41-valfit-calibrated (gate/candidate tren calibrated).
Scenarios: normal + fee 0.00055 + FillStress(5,5,5,.00055,False).
Monthly geometric theo configs/swing_v15_continuous_folds.json.
Decisions/labels: data/processed/swing_regime_research_v4/.
Record: bias before->after, rank before->after (assert order preservation
  up-to-ties), coverage before->after.
Local only, khong live, khong overwrite.
"""

import torch  # noqa: F401 (torch truoc pandas: DLL load-order Windows host)
import argparse
import json
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.swing import grid, prices  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from opencode_r30m_v41_model import deterministic_best_index  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v112_v41valfit.json"
EXPECTED_BRANCHES = ["v41-identity", "v41-valfit-calibrated"]
TOPK = 408
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def qstats(x):
    x = np.asarray(x, dtype=np.float64)
    return {"mean": float(x.mean()), "std": float(x.std()), "min": float(x.min()),
            "p10": float(np.quantile(x, 0.10)), "p50": float(np.quantile(x, 0.50)),
            "p90": float(np.quantile(x, 0.90)), "p95": float(np.quantile(x, 0.95)),
            "p99": float(np.quantile(x, 0.99)), "max": float(x.max())}


def rank_corr_per_decision(net, tgt):
    a = pd.DataFrame(net).rank(axis=1).to_numpy()
    b = pd.DataFrame(tgt).rank(axis=1).to_numpy()
    a -= a.mean(1, keepdims=True)
    b -= b.mean(1, keepdims=True)
    den = np.sqrt((a * a).sum(1) * (b * b).sum(1))
    valid = den > 0
    out = np.full(net.shape[0], np.nan)
    out[valid] = (a * b).sum(1)[valid] / den[valid]
    return out


def build_v41_signals(exp_mat, fill_logits, cand_grid, fold_of, part, cfg):
    """VERBATIM v91b policy: gate en_best>0 + fallback top-8/fold-test.

    exp_mat: (n,16) expected tradeable percent (RAW hoac calibrated).
    fill_logits: (n,16) ensemble fill logits (goc, khong calibrate).
    candidate: deterministic_best_index eps=1e-6 fill-desc holding-asc.
    Frequency: monthly cap 4 + cooldown 5d (giong swing_signals).
    Tra ve (signals frame, info dict, selected set, en_best).
    """
    exp_mat = np.asarray(exp_mat, dtype=np.float64)
    fill_logits = np.asarray(fill_logits, dtype=np.float64)
    n = len(part)
    if exp_mat.shape != (n, 16) or fill_logits.shape != (n, 16):
        raise ValueError("expected/fill shape mismatch")
    if len(fold_of) != n:
        raise ValueError("fold index mismatch")
    en_best = exp_mat.max(1)
    selected = set()
    gate_hits, fallback_adds = {}, {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        gate = idx[en_best[idx] > 0.0]
        gate_hits[str(f)] = int(len(gate))
        if len(gate) >= 8:
            selected.update(gate.tolist())
            fallback_adds[str(f)] = 0
        else:
            top = idx[np.argsort(-en_best[idx], kind="stable")[:min(8, len(idx))]]
            selected.update(gate.tolist())
            selected.update(top.tolist())
            fallback_adds[str(f)] = int(len(set(top.tolist()) - set(gate.tolist())))
    policy = cfg["policy"]
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    signals = []
    for i, row in enumerate(part.itertuples()):
        if i not in selected:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        k = deterministic_best_index(exp_mat[i], fill_logits[i], cand_grid, eps=1e-6)
        sig = prices(float(row.close), float(row.atr5), float(row.atr4),
                     cand_grid[k], cfg)
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp,
                        "fold_test": int(fold_of[i]),
                        "action": "LONG" if cand_grid[k, 0] == 1 else "SHORT",
                        "direction": int(cand_grid[k, 0]), "candidate_id": k,
                        "entry_limit": float(sig["entry_limit"]),
                        "stop_loss": float(sig["stop_loss"]),
                        "take_profit_1": float(sig["take_profit_1"]),
                        "take_profit_2": float(sig["take_profit_2"]),
                        "holding_bars": int(sig["holding_bars"]),
                        "expected_net_percent": float(exp_mat[i, k]),
                        "en_best": float(en_best[i]),
                        "ohlc_fill_score": float(1 / (1 + np.exp(-np.clip(float(fill_logits[i, k]), -40, 40)))),
                        "calibrated": False,
                        "entry_expiry_bars": int(cfg["entry_expiry_bars"]),
                        "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    frame = pd.DataFrame(signals)
    info = {"gate_hits_by_fold": gate_hits, "fallback_adds_by_fold": fallback_adds,
            "n_selected": len(selected), "n_signals": len(frame),
            "policy_margin": 0.0, "policy_n_min": 8}
    return frame, info, selected, en_best


def dd_guard_leverage(signals, trades):
    equity_at = sorted((pd.Timestamp(t.exit_time), t.equity_after) for t in trades)
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signals["signal_time"], utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak, level = float(curve.cummax().iloc[-1]), float(curve.iloc[-1])
        out.append(0.5 if level / peak < 0.9 else 1.0)
    return np.array(out, dtype=float)


def run_branch(candles, signals, costs, execution, years):
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    stress, st, diag = run_stress(candles, signals, 100, costs, execution,
                                  FillStress(5, 5, 5, 0.00055, False))
    out = {}
    for label, res, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                              ("execution_stress", stress, st)):
        ratio = res.final_equity / 100
        out[label] = {**asdict(res),
                      "annual_geometric_net": float(ratio ** (1 / years) - 1),
                      "monthly_geometric_net": float(ratio ** (1 / (12 * years)) - 1)}
        rows = [asdict(t) for t in items]
        out[label]["_trades_rows"] = rows
    out["execution_stress"]["diagnostics"] = diag
    return out, trades


def sig_info(exp_mat, part, cfg, labels_sub, signals, tag):
    exp_mat = np.asarray(exp_mat, dtype=np.float64)
    best_exp = exp_mat.max(1)
    months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
    truth = np.asarray(labels_sub, dtype=np.float64)
    order = np.argsort(best_exp, kind="stable")[-TOPK:]
    k = exp_mat[order].argmax(1)
    pe = exp_mat[order, k]
    rn = truth[order, k, 0]
    rf = truth[order, k, 1]
    rp = truth[order, k, 2]
    filled = rf == 1
    per = rank_corr_per_decision(exp_mat, truth[:, :, 0])
    valid = per[~np.isnan(per)]
    return {
        "score_distribution": {f"best_exp_{kk}": vv for kk, vv in qstats(best_exp).items()},
        "n_signals": int(len(signals)),
        "coverage": float(len(signals) / len(part)) if len(part) else 0.0,
        "directions": {str(kk): int(vv) for kk, vv in signals.direction.value_counts().items()}
        if len(signals) and "direction" in signals else {},
        "candidates": {str(kk): int(vv) for kk, vv in signals.candidate_id.value_counts().items()}
        if len(signals) and "candidate_id" in signals else {},
        "holdings": {str(kk): int(vv) for kk, vv in signals.holding_bars.value_counts().items()}
        if len(signals) and "holding_bars" in signals else {},
        "active_months": int(len(months)),
        "first_signal": str(signals.signal_time.min()) if len(signals) else None,
        "last_signal": str(signals.signal_time.max()) if len(signals) else None,
        "by_month": {str(kk): int(vv) for kk, vv in months.items()} if len(signals) else {},
        "topdecile": {"n": int(TOPK), "pred_exp_mean": float(pe.mean()),
                      "obs_net_mean": float(rn.mean()), "obs_fill_rate": float(rf.mean()),
                      "obs_pos_given_fill": float(rp[filled].mean()) if filled.any() else None,
                      "bias_pred_minus_obs": float(pe.mean() - rn.mean())},
        "rank_overall": {"n": int(len(part)), "n_valid": int(len(valid)),
                         "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                         "rank_corr_std": float(valid.std()) if len(valid) else None},
        "tag": tag,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    a = p.parse_args()
    spec = json.loads(Path(a.config).read_text(encoding="utf-8"))
    assert list(spec["branches"]) == EXPECTED_BRANCHES, "branches phai pre-spec dung 2 nhanh v112"
    assert spec["calibration"]["min_eligible_decisions"] == 50, "warmup rule pre-spec 50"
    assert spec["scenarios"] == ["normal", "fee_stress", "execution_stress"], "scenarios pre-spec"
    assert spec["base"]["seeds"] == [1729, 1730, 1731], "seeds pre-spec"
    if a.output.exists():
        raise FileExistsError("Khong ghi de lich su; chon output dir moi")
    base = spec["base"]
    plan = json.loads((ROOT / base["plan"]).read_text(encoding="utf-8"))
    assert plan.get("model_family") == "valuescale_selective_ssm_v41", "plan phai la v41"
    parent = json.loads((ROOT / base["parent_plan"]).read_text(encoding="utf-8"))
    ds = ROOT / base["dataset"]
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    # VERIFY v41 download presence: 33 test + 33 val (else STOP)
    source = ROOT / base["source"]
    test_paths, val_paths = [], []
    for seed in base["seeds"]:
        for fold in range(len(parent["folds"])):
            test_paths.append(source / base["predictions_pattern"].format(seed=seed, fold=fold))
            val_paths.append(source / base["val_predictions_pattern"].format(seed=seed, fold=fold))
    missing_test = [str(q) for q in test_paths if not q.exists()]
    missing_val = [str(q) for q in val_paths if not q.exists()]
    print(json.dumps({"verify_v41": {"expected_test": 33, "found_test": 33 - len(missing_test),
                                     "expected_val": 33, "found_val": 33 - len(missing_val),
                                     "missing_test": missing_test[:3], "missing_val": missing_val[:3]}}), flush=True)
    if missing_test or missing_val:
        print(json.dumps({"STOP_missing_v41_download": {"missing_test": len(missing_test),
                                                         "missing_val": len(missing_val)}}), flush=True)
        raise FileNotFoundError(f"Thieu test {len(missing_test)}/33 hoac val {len(missing_val)}/33; STOP, khong tu re-download.")
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels_all = z["labels"]
    assert labels_all.shape[1] == 16 and labels_all.shape[2] == 3, "labels shape"
    end = pd.Timestamp(parent["complete_evaluation_until"])
    partitions = []
    for s, e in parent["folds"]:
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        partitions.append(np.flatnonzero(((decisions.signal_time >= s) & (decisions.signal_time < e)
                                          & (decisions.label_end < end)).to_numpy()))
    indices = np.concatenate(partitions)
    assert len(indices) == 4076, f"decision count changed: {len(indices)}"
    part = decisions.iloc[indices].reset_index(drop=True)
    fold_of = np.concatenate([np.full(len(sel), f, dtype=np.int64) for f, sel in enumerate(partitions)])
    assert len(fold_of) == len(part)
    labsub = labels_all[indices]
    # Stack TEST forecasts VERBATIM audit (raw float32 stack -> combine mean)
    forecasts = []
    for fold in range(len(parent["folds"])):
        batch = []
        for seed in base["seeds"]:
            q = source / base["predictions_pattern"].format(seed=seed, fold=fold)
            arr = np.load(q, allow_pickle=False)
            if arr.shape != (len(partitions[fold]), 16, 6) or not np.isfinite(arr).all():
                raise ValueError(f"Invalid test prediction {q}: {arr.shape}")
            batch.append(arr)
        forecasts.append(np.stack(batch))
    stacked = np.concatenate(forecasts, axis=1)  # (3 seeds, n, 16, 6) float32
    ensemble, _ = combine(stacked, 0.0)
    ensemble = np.asarray(ensemble, dtype=np.float64)  # (4076,16,6)
    assert ensemble.shape == (4076, 16, 6)
    fill_logits = np.asarray(ensemble[..., 4], dtype=np.float64)
    fill = 1 / (1 + np.exp(-np.clip(fill_logits, -40, 40)))
    exp_raw = np.asarray(ensemble[..., 0] * fill, dtype=np.float64)
    assert exp_raw.shape == (4076, 16)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    assert cap == 2016, "holding cap"
    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    assert cand_grid.shape == (16, 6)
    # ---- TRUE val-fit per-fold isotonic VAL-ONLY ----
    n = len(part)
    cal = np.zeros_like(exp_raw)
    calib_records = []
    fold_offsets = []
    off = 0
    for fold in range(len(parent["folds"])):
        fold_offsets.append(off)
        sel_len = len(partitions[fold])
        cur = slice(off, off + sel_len)
        # val ensemble per fold
        vbatch = []
        for seed in base["seeds"]:
            q = source / base["val_predictions_pattern"].format(seed=seed, fold=fold)
            arr = np.load(q, allow_pickle=False)
            if arr.shape[1:] != (16, 6) or not np.isfinite(arr).all():
                raise ValueError(f"Invalid val prediction {q}: {arr.shape}")
            vbatch.append(arr)
        # verify val indices identical across seeds (causal past-only by construction)
        vidx_ref = None
        for seed in base["seeds"]:
            q = source / base["indices_pattern"].format(seed=seed, fold=fold)
            with np.load(q, allow_pickle=False) as ix:
                v = np.asarray(ix["validation"])
                if vidx_ref is None:
                    vidx_ref = v
                elif not np.array_equal(vidx_ref, v):
                    raise ValueError(f"Val indices differ across seeds fold {fold}")
        with np.load(source / base["indices_pattern"].format(seed=base["seeds"][0], fold=fold),
                     allow_pickle=False) as ix:
            vidx = np.asarray(ix["validation"])
            tidx = np.asarray(ix["test"])
        # past-only proof: max val signal_time < min test signal_time (per fold)
        v_times = decisions.iloc[vidx]["signal_time"]
        # test rows in global part order for this fold:
        t_global = np.flatnonzero(fold_of == fold)
        t_times = part.iloc[t_global]["signal_time"]
        past_only = bool(v_times.max() < t_times.min())
        if not past_only:
            raise ValueError(f"fold {fold} val NOT past-only vs test")
        vstack = np.stack(vbatch)  # (3, n_val, 16, 6)
        vens, _ = combine(vstack, 0.0)
        vens = np.asarray(vens, dtype=np.float64)
        vfill = 1 / (1 + np.exp(-np.clip(np.asarray(vens[..., 4], dtype=np.float64), -40, 40)))
        vexp = np.asarray(vens[..., 0] * vfill, dtype=np.float64)
        vlab = np.asarray(labels_all[vidx][..., 0], dtype=np.float64)
        X = vexp.ravel()
        y = vlab.ravel()
        n_val = int(len(vidx))
        warmup = None
        if n_val < int(spec["calibration"]["min_eligible_decisions"]):
            warmup = "WAIT"
        if not (np.isfinite(X).all() and np.isfinite(y).all()):
            raise ValueError(f"fold {fold} nonfinite val fit inputs")
        if len(np.unique(X)) < 2:
            warmup = "WAIT"
        if warmup is not None:
            cal[cur] = exp_raw[cur]  # warmup: dung RAW (record ro)
            calib_records.append({"fold": fold, "warmup": "WAIT",
                                  "eligible_rows": n_val,
                                  "val_signal_max": str(v_times.max()),
                                  "test_signal_min": str(t_times.min()),
                                  "past_only": past_only,
                                  "t_best_note": "warmup: no fit, use raw"})
        else:
            model = IsotonicRegression(out_of_bounds="clip").fit(X, y)
            mapped = model.predict(np.asarray(exp_raw[cur], dtype=np.float64).ravel())
            cal[cur] = mapped.reshape(exp_raw[cur].shape)
            xv = np.asarray(model.X_thresholds_, dtype=np.float64)
            yv = np.asarray(model.y_thresholds_, dtype=np.float64)
            assert bool(np.all(np.diff(xv) >= 0)), f"fold {fold} iso x not sorted"
            assert bool(np.all(np.diff(yv) >= -1e-12)), f"fold {fold} iso y not monotone"
            calib_records.append({"fold": fold, "warmup": None,
                                  "eligible_rows": n_val,
                                  "val_signal_max": str(v_times.max()),
                                  "test_signal_min": str(t_times.min()),
                                  "past_only": past_only,
                                  "iso_x_len": int(len(xv)), "iso_y_len": int(len(yv)),
                                  "x_min": float(xv.min()), "x_max": float(xv.max()),
                                  "y_min": float(yv.min()), "y_max": float(yv.max()),
                                  "x": [float(v) for v in xv],
                                  "y": [float(v) for v in yv]})
        off += sel_len
    # within-fold order-preservation assert (raw_a < raw_b => mapped_a <= mapped_b)
    for fold in range(len(parent["folds"])):
        if calib_records[fold].get("warmup") is not None:
            continue
        start = fold_offsets[fold]
        cur = slice(start, start + len(partitions[fold]))
        raw_f = exp_raw[cur].ravel()
        map_f = cal[cur].ravel()
        rng = np.random.default_rng(0)
        m = min(20000, raw_f.size * 2)
        ii = rng.integers(0, raw_f.size, size=m)
        jj = rng.integers(0, raw_f.size, size=m)
        viol = int(((raw_f[ii] < raw_f[jj] - 1e-12) & (map_f[ii] > map_f[jj] + 1e-9)).sum())
        assert viol == 0, f"fold {fold} isotonic order violated: {viol}"
    per_raw = rank_corr_per_decision(exp_raw, labsub[..., 0])
    per_cal = rank_corr_per_decision(cal, labsub[..., 0])
    both = ~(np.isnan(per_raw) | np.isnan(per_cal))
    max_rank_drift = float(np.max(np.abs(per_raw[both] - per_cal[both]))) if both.any() else 0.0
    mean_rank_drift = float(np.mean(np.abs(per_raw[both] - per_cal[both]))) if both.any() else 0.0
    mean_raw = float(np.nanmean(per_raw)) if (~np.isnan(per_raw)).any() else None
    mean_cal = float(np.nanmean(per_cal)) if (~np.isnan(per_cal)).any() else None
    print(json.dumps({"order_assert": {"viol_order": 0, "assert": "pass (monotone up-to-ties)",
                                       "max_rank_drift": max_rank_drift,
                                       "mean_abs_rank_drift": mean_rank_drift,
                                       "rank_mean_raw": mean_raw, "rank_mean_cal": mean_cal,
                                       "n_both_valid": int(both.sum())}}), flush=True)
    # Fallback top-8/fold on CALIBRATED (tru warmup): ranking trong fold khong dung label
    fallback_idx = set()
    fallback_by_fold = {}
    for fold in range(len(parent["folds"])):
        if calib_records[fold].get("warmup") is not None:
            fallback_by_fold[str(fold)] = []
            continue
        start = fold_offsets[fold]
        best = cal[start:start + len(partitions[fold])].max(1)
        order = np.argsort(best, kind="stable")[::-1]
        picked = [int(start + j) for j in order[:min(8, len(partitions[fold]))]]
        for q in picked:
            fallback_idx.add(q)
        fallback_by_fold[str(fold)] = picked
    print(json.dumps({"calibration": {"folds": len(calib_records),
                                      "warmup_folds": [r["fold"] for r in calib_records if r.get("warmup")],
                                      "fallback_total": len(fallback_idx)}}), flush=True)
    # ---- Signals ----
    sig_identity, info_identity, _, en_best_raw = build_v41_signals(exp_raw, fill_logits, cand_grid, fold_of, part, cfg)
    # calibrated signals: gate tren calibrated (fallback da tinh nhung build_v41_signals tu xu ly fallback theo calibrated best)
    sig_cal_raw, info_cal, _, en_best_cal = build_v41_signals(cal, fill_logits, cand_grid, fold_of, part, cfg)
    sig_cal = sig_cal_raw.copy()
    if len(sig_cal):
        sig_cal["calibrated"] = True
    branch_signals = {"v41-identity": sig_identity,
                      "v41-valfit-calibrated": sig_cal}
    for name, s in branch_signals.items():
        print(json.dumps({"branch_signals": name, "n_signals": int(len(s)),
                          "coverage": float(len(s) / len(part)) if len(part) else 0.0}), flush=True)
    # ---- CONTROL CHECK (STOP neu lech) ----
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    ref = spec["control_reference"]
    base_sig = sig_identity.drop(columns=["leverage"], errors="ignore").copy()
    # identity signals already have no leverage col; run normal
    res_c, tr_c = run_backtest(candles, base_sig, 100, costs, exec1x)
    rep_long = int(sum(1 for t in tr_c if t.direction == 1))
    rep_short = int(sum(1 for t in tr_c if t.direction == -1))
    rep_mo = float((res_c.final_equity / 100) ** (1 / (12 * years)) - 1)
    match = bool(abs(res_c.total_return - float(ref["total_return"])) < 1e-9
                 and abs(res_c.max_drawdown - float(ref["max_drawdown"])) < 1e-9
                 and abs(rep_mo - float(ref["monthly_geometric_net"])) < 1e-9
                 and res_c.trades == int(ref["trades"])
                 and rep_long == int(ref["long_trades"])
                 and rep_short == int(ref["short_trades"])
                 and len(sig_identity) == int(ref["n_signals"]))
    print(json.dumps({"control_check": {
        "reproduced": {"total_return": res_c.total_return, "max_drawdown": res_c.max_drawdown,
                       "monthly_geometric_net": rep_mo,
                       "trades": res_c.trades, "long": rep_long, "short": rep_short,
                       "n_signals": int(len(sig_identity))},
        "reference": ref, "match": match}}), flush=True)
    if not match:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_c), "reference": ref,
             "n_signals": int(len(sig_identity))}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; v41-identity != R-audit rank_en_1x +39.0%/-33.4%/75", flush=True)
        sys.exit(1)
    # ---- Backtest tat ca branches x 3 scenarios ----
    gate = spec["gate"]
    results, diagnostics = {}, {}

    def gate_flags(d):
        try:
            m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f_ok = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m_ok = dd_ok = f_ok = False
        return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
                "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}

    empty_template = base_sig.iloc[0:0].copy()
    for branch in EXPECTED_BRANCHES:
        sig = branch_signals[branch]
        bdir = a.output / branch
        bdir.mkdir()
        sig_out = sig.copy()
        if "leverage" not in sig_out.columns and len(sig_out):
            sig_out["leverage"] = 1.0
        sig_out.to_parquet(bdir / "signals.parquet", index=False)
        np.savez_compressed(bdir / "predictions.npz",
                            ensemble_mean_raw=ensemble.astype(np.float32),
                            expected_raw=exp_raw.astype(np.float64),
                            expected_calibrated=cal.astype(np.float64),
                            fill_logits=fill_logits.astype(np.float64),
                            decision_indices=indices)
        (bdir / "calibrators.json").write_text(json.dumps(
            {"records": calib_records, "fallback_by_fold": fallback_by_fold,
             "fallback_total": len(fallback_idx),
             "note": "TRUE val-fit per-fold VAL-ONLY isotonic (out_of_bounds=clip) on ensemble unconditional percent; thresholds NONE (gate 0.0 unchanged); fallback ranking trong fold khong dung label; fill logits giu nguyen cho tie-break; warmup rule <50/nonfinite/unique<2 -> use raw"},
            indent=2, default=str))
        exec_sig = sig.drop(columns=["leverage"], errors="ignore").copy() if len(sig) else empty_template.copy()
        scen, trades = run_branch(candles, exec_sig, costs, exec1x, years)
        branch_metrics = {}
        for label in ("normal", "fee_stress", "execution_stress"):
            rows = scen[label].pop("_trades_rows")
            d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v) for k, v in scen[label].items() if k != "diagnostics"}
            if label == "execution_stress":
                d["diagnostics"] = scen[label].get("diagnostics")
            d["gate"] = gate_flags(d)
            branch_metrics[label] = d
            dest = bdir / f"{label}_trades.csv"
            if rows:
                pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(dest, index=False)
            else:
                pd.DataFrame(columns=TRADE_COLUMNS).to_csv(dest, index=False)
            (bdir / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
        results[branch + "_1x"] = branch_metrics
        if branch == "v41-identity":
            diagnostics[branch + "_1x"] = sig_info(exp_raw, part, cfg, labsub, sig, "raw")
            diagnostics[branch + "_1x"]["gate_thresholds"] = {
                "type": "v41_policy_floor_raw_gt_0", "fallback": "top8_per_fold", "policy_info": info_identity}
        else:
            diagnostics[branch + "_1x"] = sig_info(cal, part, cfg, labsub, sig, "valfit-calibrated")
            diagnostics[branch + "_1x"]["gate_thresholds"] = {
                "type": "v41_policy_floor_calibrated_gt_0_unchanged",
                "fallback": "top8_per_fold_on_calibrated", "policy_info": info_cal}
        print(json.dumps({"branch": branch + "_1x", "signals": int(len(sig)),
                          "metrics": {s: {k: branch_metrics[s][k] for k in
                                          ("total_return", "max_drawdown", "trades",
                                           "monthly_geometric_net", "gross_pnl", "fees",
                                           "funding", "profit_factor", "win_rate")}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": {s: branch_metrics[s]["gate"] for s in
                                   ("normal", "fee_stress", "execution_stress")}}, default=str), flush=True)
    # ---- dd_guard conditional tren calibrated (neu re) ----
    dd_info = {"ran": False, "reason": ""}
    try:
        best = "v41-valfit-calibrated_1x"
        best_sig_name = "v41-valfit-calibrated"
        best_sig = branch_signals[best_sig_name]
        if len(best_sig) == 0:
            dd_info = {"ran": False, "reason": "calibrated co 0 signals; skip dd_guard", "best": best}
        else:
            bdir_best = a.output / best_sig_name
            exec_sig_best = best_sig.drop(columns=["leverage"], errors="ignore").copy()
            _, trades_best = run_backtest(candles, exec_sig_best, 100, costs, exec1x)
            guard = dd_guard_leverage(best_sig, trades_best)
            gsig = best_sig.copy()
            gsig["leverage"] = guard
            execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                                     max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
            scen_dd, _ = run_branch(candles, gsig, costs, execdd, years)
            bdir_dd = a.output / (best_sig_name + "_dd_guard")
            bdir_dd.mkdir()
            gsig.to_parquet(bdir_dd / "signals.parquet", index=False)
            np.savez_compressed(bdir_dd / "predictions.npz",
                                expected_calibrated=np.load(bdir_best / "predictions.npz")["expected_calibrated"],
                                decision_indices=indices)
            (bdir_dd / "calibrators.json").write_text((bdir_best / "calibrators.json").read_text(encoding="utf-8"))
            dd_metrics = {}
            for label in ("normal", "fee_stress", "execution_stress"):
                rows = scen_dd[label].pop("_trades_rows")
                d = {k: v for k, v in scen_dd[label].items() if k != "diagnostics"}
                if label == "execution_stress":
                    d["diagnostics"] = scen_dd[label].get("diagnostics")
                d["gate"] = gate_flags(d)
                dd_metrics[label] = d
                pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
                    bdir_dd / f"{label}_trades.csv", index=False)
                (bdir_dd / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
            results[best + "_dd_guard"] = dd_metrics
            diagnostics[best + "_dd_guard"] = deepcopy(diagnostics[best])
            diagnostics[best + "_dd_guard"]["dd_guard"] = {
                "reference": f"{best} own-book 1x (trigger 10%, lev 0.5/1.0, past-only)",
                "n_guarded": int((guard == 0.5).sum()), "guard_fraction": float((guard == 0.5).mean())}
            dd_info = {"ran": True, "best": best, "branch": best + "_dd_guard",
                       "n_guarded": int((guard == 0.5).sum()),
                       "guard_fraction": float((guard == 0.5).mean())}
            print(json.dumps({"dd_guard": dd_info}), flush=True)
    except Exception as e:  # noqa: BLE001
        dd_info = {"ran": False, "reason": f"skip dd_guard (khong re/loi): {type(e).__name__}: {e}"}
        print(json.dumps({"dd_guard_skipped": dd_info}), flush=True)
    # ---- bias/rank/coverage deltas ----
    deltas = {}
    try:
        b0 = diagnostics["v41-identity_1x"]["topdecile"]
        r0 = diagnostics["v41-identity_1x"]["rank_overall"]
        c0 = diagnostics["v41-identity_1x"]["coverage"]
        n0 = diagnostics["v41-identity_1x"]["n_signals"]
        b1 = diagnostics["v41-valfit-calibrated_1x"]["topdecile"]
        r1 = diagnostics["v41-valfit-calibrated_1x"]["rank_overall"]
        c1 = diagnostics["v41-valfit-calibrated_1x"]["coverage"]
        deltas["v41-valfit-calibrated_1x"] = {
            "bias_before_pct": float(b0["bias_pred_minus_obs"]),
            "bias_after_pct": float(b1["bias_pred_minus_obs"]),
            "bias_delta_pct": float(b1["bias_pred_minus_obs"] - b0["bias_pred_minus_obs"]),
            "pred_mean_before_pct": float(b0["pred_exp_mean"]),
            "pred_mean_after_pct": float(b1["pred_exp_mean"]),
            "obs_mean_before_pct": float(b0["obs_net_mean"]),
            "obs_mean_after_pct": float(b1["obs_net_mean"]),
            "rank_before": float(r0["rank_corr_mean"]) if r0["rank_corr_mean"] is not None else None,
            "rank_after": float(r1["rank_corr_mean"]) if r1["rank_corr_mean"] is not None else None,
            "rank_delta": (float(r1["rank_corr_mean"] - r0["rank_corr_mean"])
                           if (r0["rank_corr_mean"] is not None and r1["rank_corr_mean"] is not None) else None),
            "coverage_before": float(c0), "coverage_after": float(c1),
            "coverage_delta": float(c1 - c0),
            "n_signals_before": int(n0),
            "n_signals_after": int(diagnostics["v41-valfit-calibrated_1x"]["n_signals"])}
    except Exception as e:  # noqa: BLE001
        deltas = {"error": f"{type(e).__name__}: {e}"}
    # ---- summary.json ----
    input_files = [base["decisions"], base["labels"], base["candles"], base["dataset_config"],
                   base["parent_plan"], base["plan"], base["r_audit_read_only"],
                   base["r_portfolio_read_only"],
                   "configs/opencode_v112_v41valfit.json",
                   "scripts/opencode_r40a_v41valfit.py",
                   "src/agentic_alpha_lab/models/ensemble_value.py",
                   "scripts/opencode_r30m_v41_model.py"]
    report = {"experiment": spec["experiment"], "family": spec["family"],
              "hypothesis": spec["hypothesis"], "branches": results,
              "diagnostic_v34_lens": diagnostics,
              "bias_rank_coverage_deltas": deltas,
              "order_preservation": {"max_rank_drift": max_rank_drift,
                                     "mean_abs_rank_drift": mean_rank_drift,
                                     "rank_mean_raw": mean_raw, "rank_mean_cal": mean_cal,
                                     "assert": "pass (monotone up-to-ties, viol==0; rank drift recorded, per-fold maps + warmup expected)"},
              "calibration_records": calib_records,
              "fallback_by_fold": fallback_by_fold,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_c.total_return,
                                               "max_drawdown": res_c.max_drawdown,
                                               "monthly_geometric_net": rep_mo,
                                               "trades": res_c.trades,
                                               "long_trades": rep_long, "short_trades": rep_short,
                                               "n_signals": int(len(sig_identity))},
                                "match": True},
              "dd_guard_conditional": dd_info,
              "duration_years": years, "gate": gate,
              "formulas": {"monthly_geometric_net": spec["monthly_formula"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": spec["dd_guard_conditional"]["formula"]},
              "config": spec, "independent_test": False, "exploratory": True,
              "live_approved": False,
              "causality": "past-only closed-candle; TRUE val-fit per-fold VAL-ONLY (val past-only vs test, embargo 8d by construction, verified per fold); thresholds NONE (gate 0.0 unchanged v41); fallback ranking trong fold khong dung label; fill tu nen ke tiep",
              "warning": ("Opened development interval 2023-2026 only. Labels exploratory. "
                          "Drawdown trade-candle-close sampled, not true mark/intrabar. "
                          "Stop/timeout market-like o scenario fee. Khong live approval."),
              "input_sha256": {q: sha256(ROOT / q) for q in input_files},
              "output_note": "moi file duoi output dir la moi; khong ghi de lich su"}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    import hashlib

    def fsha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    out_hashes = {}
    for q in sorted(a.output.rglob("*")):
        if q.is_file():
            if q.name == "summary.json":
                continue
            out_hashes[q.relative_to(a.output).as_posix()] = fsha(q)
    rep2 = json.loads((a.output / "summary.json").read_text(encoding="utf-8"))
    rep2["output_sha256"] = out_hashes
    (a.output / "summary.json").write_text(json.dumps(rep2, indent=2, default=str), encoding="utf-8")
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
