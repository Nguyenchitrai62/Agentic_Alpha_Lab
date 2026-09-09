"""Opencode R30 R-DIAGNOSTIC: outlier-robust (winsorized) calibrate-first on v40.

Pre-spec: configs/opencode_v90_v40wincal.json (viet TRUOC khi chay).
Frozen inputs: artifacts/kaggle/v40_capatpolicy_download/capatpolicy-training
  (33 test predictions + 33 val predictions = 66 files, VERIFY presence else STOP),
  data/processed/swing_regime_research_v4/{decisions.parquet,examples.npz,candles.parquet,config.json}.
Method: WINSORIZE val labels at +-1.0 (percent-points) then causal isotonic
  fit on winsorized-val-only (per-fold, past-only, embargo 8d,
  IsotonicRegression out_of_bounds=clip), applied to test; gate = same v40
  policy floor (en_best>0.0 + fallback top-8/fold-test, deterministic tie-break
  eps=1e-6 fill-desc holding-asc among fill>=0.25).
Branches (1x): v40-identity (control, must reproduce R-audit rank_en_1x normal
  +0.66%/-40.87%/89 or STOP), v40-winsor-calibrated (same gate on calibrated).
Scenarios: normal + fee 0.00055 + FillStress(5,5,5,.00055,False).
Monthly geometric per configs/swing_v15_continuous_folds.json.
Labels exploratory, causal past-only (val-only fit, no test peek; winsor cap
from val distribution only), local only, no live.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.swing import grid, prices  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v90_v40wincal.json"
EXPECTED_BRANCHES = ["v40-identity", "v40-winsor-calibrated"]
POLICY_MARGIN = 0.0
POLICY_N_MIN = 8
TIE_EPS = 1e-6
WINSOR_CAP = 1.0
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


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(np.asarray(x, dtype=np.float64), -40, 40)))


def deterministic_best_index(expected_row, fill_row, candidates, eps=TIE_EPS):
    exp = np.asarray(expected_row, dtype=np.float64).reshape(-1)
    fil = np.asarray(fill_row, dtype=np.float64).reshape(-1)
    cand = np.asarray(candidates)
    if exp.shape[0] != 16 or fil.shape[0] != 16 or cand.shape != (16, 6):
        raise ValueError("Tie-break expects (16,) expected/fill + (16,6) candidates")
    if not (np.isfinite(exp).all() and np.isfinite(fil).all()):
        raise ValueError("Nonfinite tie-break inputs")
    if not float(eps) == 1e-6:
        raise ValueError("v40 tie_break_eps must be 1e-6")
    m = float(np.max(exp))
    tied = np.flatnonzero((m - exp) < float(eps))
    if len(tied) == 1:
        return int(tied[0])
    fmax = float(np.max(fil[tied]))
    tied_f = tied[(fil[tied] >= fmax - 1e-9)]
    if len(tied_f) == 1:
        return int(tied_f[0])
    holdings = cand[tied_f, 5].astype(np.float64)
    hmin = float(np.min(holdings))
    tied_h = tied_f[holdings <= hmin + 1e-12]
    return int(np.min(tied_h))


def v40_policy_signals(ensemble, part, cfg, fold_of):
    """Ban sao policy floor v40 audit (deterministic tie-break).

    ensemble: (n,16,6) map-v8 mean 3 seeds (capped or calibrated).
    en_best = max_k ch0*fill. Per fold-test: gate en_best > 0.0; if <8 then
    top-8 by en_best. Candidate: deterministic_best_index among fill>=0.25
    (ineligible masked to -inf before tie-break). Geometry + frequency
    (monthly cap 4 + cooldown 5d) from dataset cfg.
    """
    pred = np.asarray(ensemble, dtype=np.float64)
    fill = sigmoid(pred[..., 4])
    expected = pred[..., 0] * fill
    en_best = expected.max(1)
    n = len(part)
    if len(fold_of) != n:
        raise ValueError("fold index mismatch")
    selected = set()
    gate_hits, fallback_adds = {}, {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        gate = idx[en_best[idx] > POLICY_MARGIN]
        gate_hits[str(f)] = int(len(gate))
        if len(gate) >= POLICY_N_MIN:
            selected.update(gate.tolist())
            fallback_adds[str(f)] = 0
        else:
            top = idx[np.argsort(-en_best[idx], kind="stable")[:min(POLICY_N_MIN, len(idx))]]
            selected.update(gate.tolist())
            selected.update(top.tolist())
            fallback_adds[str(f)] = int(len(set(top.tolist()) - set(gate.tolist())))
    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    if cand_grid.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    policy, signals = cfg["policy"], []
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    n_wait_ineligible = 0
    for i, row in enumerate(part.itertuples()):
        if i not in selected:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        elig = np.flatnonzero(fill[i] >= policy["minimum_fill_score"])
        if not len(elig):
            n_wait_ineligible += 1
            continue
        exp_masked = np.full(16, -np.inf)
        exp_masked[elig] = expected[i, elig]
        k = deterministic_best_index(exp_masked, fill[i], cand_grid, eps=TIE_EPS)
        if k not in elig:
            k = int(elig[np.argmax(expected[i, elig])])
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp,
                        "fold_test": int(fold_of[i]),
                        "direction": int(cand_grid[k, 0]), "candidate_id": k,
                        **prices(float(row.close), float(row.atr5), float(row.atr4),
                                 cand_grid[k], cfg),
                        "expected_net_percent": float(expected[i, k]),
                        "en_best": float(en_best[i]),
                        "ohlc_fill_score": float(fill[i, k]),
                        "calibrated": False, "entry_expiry_bars": cfg["entry_expiry_bars"],
                        "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    frame = pd.DataFrame(signals)
    info = {"gate_hits_by_fold": gate_hits, "fallback_adds_by_fold": fallback_adds,
            "n_selected": len(selected), "n_signals": len(frame),
            "n_wait_no_fill_eligible": n_wait_ineligible,
            "policy_margin": POLICY_MARGIN, "policy_n_min": POLICY_N_MIN,
            "tie_break_eps": TIE_EPS}
    return frame, info


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


def sig_info(pred_for_rank, part, cfg, labels_sub, signals):
    n = len(part)
    exp = np.asarray(pred_for_rank, dtype=np.float64)
    best_exp = exp.max(1)
    pass_net = best_exp > POLICY_MARGIN
    months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
    truth = np.asarray(labels_sub, dtype=np.float64)
    order = np.argsort(best_exp, kind="stable")[-TOPK:]
    k = exp[order].argmax(1)
    pe = exp[order, k]
    rn = truth[order, k, 0]
    rf = truth[order, k, 1]
    rp = truth[order, k, 2]
    filled = rf == 1
    per = rank_corr_per_decision(exp, truth[:, :, 0])
    valid = per[~np.isnan(per)]
    return {
        "score_distribution": {f"best_exp_{kk}": vv for kk, vv in qstats(best_exp).items()},
        "threshold_pass_policy0": {"pass_net_n": int(pass_net.sum()),
                                   "pass_net_rate": float(pass_net.mean())},
        "n_signals": int(len(signals)), "coverage": float(len(signals) / n) if n else 0.0,
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
        "rank_overall": {"n": int(n), "n_valid": int(len(valid)),
                         "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                         "rank_corr_std": float(valid.std()) if len(valid) else None},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    a = p.parse_args()
    spec = json.loads(Path(a.config).read_text())
    assert list(spec["branches"]) == EXPECTED_BRANCHES, "branches phai pre-spec dung 2 nhanh v90"
    assert spec["calibration"]["embargo_days"] == 8, "embargo phai 8d"
    assert spec["scenarios"] == ["normal", "fee_stress", "execution_stress"], "scenarios pre-spec"
    assert spec["base"]["seeds"] == [1729, 1730, 1731], "seeds pre-spec"
    assert float(spec["winsor"]["cap"]) == WINSOR_CAP == 1.0, "winsor cap phai +-1.0"
    assert POLICY_MARGIN == 0.0 and POLICY_N_MIN == 8 and TIE_EPS == 1e-6, "policy floor pre-spec"
    if a.output.exists():
        raise FileExistsError("Khong ghi de lich su; chon output dir moi")
    base = spec["base"]
    plan = json.loads((ROOT / base["plan"]).read_text())
    parent = json.loads((ROOT / base["parent_plan"]).read_text())
    assert plan.get("model_family") == "capatpolicy_selective_ssm_v40", "plan phai la v40"
    ds = ROOT / base["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    # VERIFY v40 download presence: 33 test + 33 val = 66 files, else STOP
    source = ROOT / base["source"]
    test_paths, val_paths = [], []
    for seed in base["seeds"]:
        for fold in range(len(parent["folds"])):
            test_paths.append(source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy")
            val_paths.append(source / f"seed{seed}/temporal_neural/fold_{fold}/val_predictions.npy")
    missing_test = [str(q) for q in test_paths if not q.exists()]
    missing_val = [str(q) for q in val_paths if not q.exists()]
    print(json.dumps({"verify_v40": {"expected_test": 33, "found_test": 33 - len(missing_test),
                                     "expected_val": 33, "found_val": 33 - len(missing_val),
                                     "missing_test": missing_test[:3], "missing_val": missing_val[:3]}}), flush=True)
    if missing_test or missing_val:
        raise FileNotFoundError(f"Thieu v40 predictions (test {len(missing_test)}/33, val {len(missing_val)}/33); STOP. Vi du test: {missing_test[:3]} val: {missing_val[:3]}")
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
    # ---- STEP 1: compute pooled-val label distribution BEFORE choosing (val-only, no test peek) ----
    pooled_val = set()
    for seed in base["seeds"]:
        for fold in range(len(parent["folds"])):
            chk = source / f"seed{seed}/checkpoints/fold_{fold}/indices.npz"
            if not chk.exists():
                raise FileNotFoundError(f"Thieu indices.npz {chk}; STOP (can de xac dinh val-only)")
            arr = np.load(str(chk), allow_pickle=False)
            pooled_val.update(arr["validation"].tolist())
    pooled_val = np.array(sorted(pooled_val))
    val_lab0 = labels_all[pooled_val][:, :, 0].ravel()
    dist = {"n_rows": int(len(pooled_val)), "n_labels": int(val_lab0.size),
            "qstats": {"mean": float(val_lab0.mean()), "std": float(val_lab0.std()),
                       "min": float(val_lab0.min()), "p1": float(np.quantile(val_lab0, 0.01)),
                       "p5": float(np.quantile(val_lab0, 0.05)), "p10": float(np.quantile(val_lab0, 0.10)),
                       "p25": float(np.quantile(val_lab0, 0.25)), "p50": float(np.quantile(val_lab0, 0.50)),
                       "p75": float(np.quantile(val_lab0, 0.75)), "p90": float(np.quantile(val_lab0, 0.90)),
                       "p95": float(np.quantile(val_lab0, 0.95)), "p99": float(np.quantile(val_lab0, 0.99)),
                       "max": float(val_lab0.max())},
            "frac_abs_gt_1": float((np.abs(val_lab0) > 1.0).mean()),
            "frac_abs_gt_3": float((np.abs(val_lab0) > 3.0).mean()),
            "pct_le_minus1": float((val_lab0 <= -1.0).mean() * 100),
            "pct_le_plus1": float((val_lab0 <= 1.0).mean() * 100),
            "frac_in_minus1_plus1": float(((val_lab0 >= -1.0) & (val_lab0 <= 1.0)).mean())}
    dist_hash = hashlib.sha256(json.dumps(dist, sort_keys=True).encode()).hexdigest()
    print(json.dumps({"winsor_step1_distribution": dist, "distribution_sha256": dist_hash}), flush=True)
    # verify vs pre-spec (val-only, computed BEFORE config freeze)
    prespec_dist = spec["winsor"]["step1_distribution_before_choosing"]
    prespec_hash = prespec_dist.get("distribution_sha256")
    dist_match = (dist_hash == prespec_hash)
    print(json.dumps({"winsor_step1_verify": {"recomputed_hash": dist_hash, "prespec_hash": prespec_hash,
                                              "match": dist_match, "note": "val-only, no test peek; mismatch (float) logged not fatal"}}), flush=True)
    # ---- STEP 2: freeze cap AFTER distribution ----
    cap = float(spec["winsor"]["cap"])
    assert cap == 1.0, "winsor cap must be 1.0 (percent-points)"
    cap_hash = hashlib.sha256(json.dumps({"cap": cap}, sort_keys=True).encode()).hexdigest()
    print(json.dumps({"winsor_step2_freeze_cap": {"cap": cap, "cap_sha256": cap_hash,
                                                  "prespec_cap_sha256": spec["winsor"]["step2_freeze_cap"].get("cap_sha256"),
                                                  "order": "step1 (distribution) BEFORE step2 (freeze cap)"}}), flush=True)
    # Stack test forecasts (3,4076,16,6)
    forecasts = []
    for fold in range(len(parent["folds"])):
        batch = []
        for seed in base["seeds"]:
            q = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            arr = np.load(q, allow_pickle=False)
            if arr.shape != (len(partitions[fold]), 16, 6) or not np.isfinite(arr).all():
                raise ValueError(f"Invalid prediction {q}: {arr.shape}")
            batch.append(arr)
        forecasts.append(np.stack(batch))
    stacked = np.concatenate(forecasts, axis=1)
    assert stacked.shape == (3, 4076, 16, 6), f"stacked shape {stacked.shape}"
    combined, details = combine(stacked, 0.0)
    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    assert score.shape == (4076, 16) and fill.shape == (4076, 16)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap_bars = int(max(cfg["holding_days"]) * 288)
    assert cap_bars == 2016, "holding cap"
    # ---- Causal winsor-isotonic per fold on winsorized-val-only ----
    n = len(part)
    is_val_part = np.array([g in set(pooled_val.tolist()) for g in indices])
    mapped_all = np.zeros_like(score)
    calib_records = []
    fold_offsets = []
    off = 0
    for fold, sel in enumerate(partitions):
        fold_offsets.append(off)
        cur = slice(off, off + len(sel))
        asof = pd.Timestamp(parent["folds"][fold][0])
        left = pd.Timestamp(parent["folds"][0][0])
        cutoff = asof - pd.Timedelta(days=8)
        mask_all = ((part.signal_time >= left) & (part.signal_time < asof) & (part.label_end < cutoff)).to_numpy()
        mask = mask_all & is_val_part
        cur_scores = score[cur]
        if mask.sum() < 50:
            mapped_all[cur] = np.zeros_like(cur_scores)
            calib_records.append({"fold": fold, "asof": str(asof), "lookback_start": str(left),
                                  "warmup": "WAIT", "eligible_rows_all": int(mask_all.sum()),
                                  "eligible_rows_val_only": int(mask.sum()),
                                  "eligible_match": bool(mask_all.sum() == mask.sum()),
                                  "winsor_cap": cap, "t_note": "warmup: no gate, fallback WAIT"})
        else:
            x = np.asarray(score[mask].ravel(), dtype=np.float64)
            y_raw = np.asarray(labsub[mask, :, 0].ravel(), dtype=np.float64)
            y = np.clip(y_raw, -cap, cap)
            if not np.isfinite(x).all() or not np.isfinite(y).all():
                raise ValueError("Nonfinite winsor-calibration inputs")
            model = IsotonicRegression(out_of_bounds="clip").fit(x, y)
            mapped = model.predict(np.asarray(cur_scores.ravel())).reshape(cur_scores.shape)
            mapped_all[cur] = mapped
            xv = np.asarray(model.X_thresholds_, dtype=np.float64)
            yv = np.asarray(model.y_thresholds_, dtype=np.float64)
            assert bool(np.all(np.diff(xv) >= 0)), f"fold {fold} iso x not sorted"
            assert bool(np.all(np.diff(yv) >= -1e-12)), f"fold {fold} iso y not monotone"
            assert float(np.min(yv)) >= -cap - 1e-9 and float(np.max(yv)) <= cap + 1e-9, f"fold {fold} iso Y exceeds winsor cap"
            calib_records.append({"fold": fold, "asof": str(asof), "lookback_start": str(left),
                                  "warmup": None, "eligible_rows_all": int(mask_all.sum()),
                                  "eligible_rows_val_only": int(mask.sum()),
                                  "eligible_match": bool(mask_all.sum() == mask.sum()),
                                  "latest_label_end": str(part.loc[mask, "label_end"].max()),
                                  "winsor_cap": cap,
                                  "winsor_frac_clipped_in_fit": float((np.abs(y_raw) > cap).mean()),
                                  "iso_x_len": len(xv), "iso_y_len": len(yv),
                                  "x_min": float(np.min(xv)), "x_max": float(np.max(xv)),
                                  "y_min": float(np.min(yv)), "y_max": float(np.max(yv)),
                                  "x": [float(v) for v in xv], "y": [float(v) for v in yv]})
        off += len(sel)
    # order-preservation assert per non-warmup fold (sampled pairs)
    for fold, sel in enumerate(partitions):
        if calib_records[fold].get("warmup") is not None:
            continue
        start = fold_offsets[fold]
        cur = slice(start, start + len(sel))
        raw_f = score[cur].ravel()
        map_f = mapped_all[cur].ravel()
        rng = np.random.default_rng(0)
        ii = rng.integers(0, raw_f.size, size=min(20000, raw_f.size * 2))
        jj = rng.integers(0, raw_f.size, size=min(20000, raw_f.size * 2))
        viol = ((raw_f[ii] < raw_f[jj] - 1e-12) & (map_f[ii] > map_f[jj] + 1e-9)).sum()
        assert viol == 0, f"fold {fold} isotonic order violated: {viol}"
    per_raw = rank_corr_per_decision(score, labsub[..., 0])
    per_map = rank_corr_per_decision(mapped_all, labsub[..., 0])
    both = ~(np.isnan(per_raw) | np.isnan(per_map))
    max_rank_drift = float(np.max(np.abs(per_raw[both] - per_map[both]))) if both.any() else 0.0
    mean_rank_drift = float(np.mean(np.abs(per_raw[both] - per_map[both]))) if both.any() else 0.0
    mean_raw = float(np.nanmean(per_raw)) if (~np.isnan(per_raw)).any() else None
    mean_map = float(np.nanmean(per_map)) if (~np.isnan(per_map)).any() else None
    print(json.dumps({"order_assert": {"viol_order": 0, "assert": "pass (monotone up-to-ties)",
                                       "max_rank_drift": max_rank_drift,
                                       "mean_abs_rank_drift": mean_rank_drift,
                                       "rank_mean_raw": mean_raw, "rank_mean_map": mean_map,
                                       "n_both_valid": int(both.sum())}}), flush=True)
    # Fallback top-8/fold on calibrated (excl warmup), ranking in fold uses no labels
    fallback_idx = set()
    fallback_by_fold = {}
    for fold, sel in enumerate(partitions):
        if calib_records[fold].get("warmup") is not None:
            fallback_by_fold[str(fold)] = []
            continue
        start = fold_offsets[fold]
        best = mapped_all[start:start + len(sel)].max(1)
        best_fill = fill[start:start + len(sel)].max(1)
        order = np.argsort(best, kind="stable")[::-1]
        picked = []
        for j in order:
            if best_fill[j] >= float(cfg["policy"]["minimum_fill_score"]):
                picked.append(int(start + j))
            if len(picked) >= 8:
                break
        for q in picked:
            fallback_idx.add(q)
        fallback_by_fold[str(fold)] = picked
    print(json.dumps({"calibration": {"folds": len(calib_records),
                                      "warmup_folds": [r["fold"] for r in calib_records if r.get("warmup")],
                                      "y_minmax": [(r.get("y_min"), r.get("y_max")) for r in calib_records if not r.get("warmup")],
                                      "fallback_total": len(fallback_idx)}}), flush=True)
    # ---- Build predictions ----
    identity_pred = combined.copy()
    iso_pred = combined.copy()
    for fold, sel in enumerate(partitions):
        start = fold_offsets[fold]
        cur = slice(start, start + len(sel))
        if calib_records[fold].get("warmup") is not None:
            iso_pred[cur, ..., 0] = np.float32(-1.0)
        else:
            iso_pred[cur, ..., 0] = (mapped_all[cur] / fill[cur]).astype(np.float32)
    # ---- Signals (same v40 floor on both; calibrated uses mapped) ----
    sig_identity, info_identity = v40_policy_signals(identity_pred.astype(np.float64), part, cfg, fold_of)
    # calibrated signals via same policy function on iso_pred
    sig_cal, info_cal = v40_policy_signals(iso_pred.astype(np.float64), part, cfg, fold_of)
    # mark calibrated flag
    if len(sig_cal):
        sig_cal = sig_cal.copy()
        sig_cal["calibrated"] = True
    branch_signals = {"v40-identity": (sig_identity, identity_pred, score, info_identity),
                      "v40-winsor-calibrated": (sig_cal, iso_pred, mapped_all, info_cal)}
    for name, (s, _, _, _) in branch_signals.items():
        print(json.dumps({"branch_signals": name, "n_signals": int(len(s)),
                          "coverage": float(len(s) / len(part)) if len(part) else 0.0}), flush=True)
    # ---- CONTROL CHECK (STOP if mismatch) ----
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap_bars, leverage=1.0, max_leverage=1.0)
    ref = spec["control_reference"]
    base_sig = sig_identity.drop(columns=["leverage"], errors="ignore").copy() if "leverage" in sig_identity.columns else sig_identity.copy()
    # v40 identity signals have leverage col? ensure engine 1x (drop leverage, use exec1x)
    res_c, tr_c = run_backtest(candles, base_sig, 100, costs, exec1x)
    match = bool(abs(res_c.total_return - float(ref["total_return"])) < 1e-9
                 and abs(res_c.max_drawdown - float(ref["max_drawdown"])) < 1e-9
                 and res_c.trades == int(ref["trades"])
                 and len(sig_identity) == int(ref["n_signals"]))
    print(json.dumps({"control_check": {
        "reproduced": {"total_return": res_c.total_return, "max_drawdown": res_c.max_drawdown,
                       "trades": res_c.trades, "n_signals": int(len(sig_identity))},
        "reference": ref, "match": match}}), flush=True)
    if not match:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_c), "reference": ref,
             "n_signals": int(len(sig_identity))}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; v40-identity != R-audit rank_en_1x +0.66%/-40.87%/89", flush=True)
        sys.exit(1)
    # ---- Backtest all branches x 3 scenarios ----
    gate = spec["gate"]

    def gate_flags(d):
        try:
            m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f_ok = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m_ok = dd_ok = f_ok = False
        return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
                "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}

    empty_template = sig_identity.iloc[0:0].drop(columns=["leverage"], errors="ignore") if len(sig_identity) else pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
    results, diagnostics = {}, {}

    def _clean(d):
        return {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v) for k, v in d.items() if k != "diagnostics"}

    for branch in EXPECTED_BRANCHES:
        sig, pred_arr, rank_mat, _info = branch_signals[branch]
        bdir = a.output / branch
        bdir.mkdir()
        sig_out = sig.copy()
        if "leverage" not in sig_out.columns and len(sig_out):
            sig_out["leverage"] = 1.0
        sig_out.to_parquet(bdir / "signals.parquet", index=False)
        np.savez_compressed(bdir / "predictions.npz", prediction=np.asarray(pred_arr, dtype=np.float32),
                            decision_indices=indices, mapped_unconditional=mapped_all)
        (bdir / "calibrators.json").write_text(json.dumps(
            {"records": calib_records, "fallback_by_fold": fallback_by_fold if "calibrated" in branch else _info,
             "fallback_total": len(fallback_idx) if "calibrated" in branch else 0,
             "policy_info": _info,
             "winsor": {"cap": cap, "distribution_sha256": dist_hash, "cap_sha256": cap_hash},
             "note": "past-only val-only (embargo 8d); fallback ranking in fold uses no labels"},
            indent=2, default=str))
        exec_sig = sig.drop(columns=["leverage"], errors="ignore").copy() if len(sig) else empty_template.copy()
        scen, trades = run_branch(candles, exec_sig, costs, exec1x, years)
        branch_metrics = {}
        for label in ("normal", "fee_stress", "execution_stress"):
            rows = scen[label].pop("_trades_rows")
            d = _clean(scen[label])
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
        diagnostics[branch + "_1x"] = sig_info(rank_mat, part, cfg, labsub, sig)
        diagnostics[branch + "_1x"]["gate_thresholds"] = {
            "type": "v40_policy_0p0_top8",
            "fallback": "plan_top8",
            "policy_info": _info}
        print(json.dumps({"branch": branch + "_1x", "signals": int(len(sig)),
                          "metrics": {s: {k: branch_metrics[s][k] for k in
                                          ("total_return", "max_drawdown", "trades",
                                           "monthly_geometric_net", "gross_pnl", "fees",
                                           "funding", "profit_factor", "win_rate")}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": {s: branch_metrics[s]["gate"] for s in
                                   ("normal", "fee_stress", "execution_stress")}}, default=str), flush=True)
    # ---- dd_guard conditional on calibrated only (if cheap) ----
    dd_info = {"ran": False, "reason": ""}
    try:
        best = "v40-winsor-calibrated_1x"
        best_sig = branch_signals["v40-winsor-calibrated"][0]
        if len(best_sig) == 0:
            dd_info = {"ran": False, "reason": "calibrated has 0 signals; skip dd_guard", "best": best}
        else:
            bdir_best = a.output / "v40-winsor-calibrated"
            exec_sig_best = best_sig.drop(columns=["leverage"], errors="ignore").copy()
            _, trades_best = run_backtest(candles, exec_sig_best, 100, costs, exec1x)
            guard = dd_guard_leverage(best_sig, trades_best)
            gsig = best_sig.copy()
            gsig["leverage"] = guard
            execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                                     max_holding_bars=cap_bars, leverage=0.5, max_leverage=1.0)
            scen_dd, _ = run_branch(candles, gsig, costs, execdd, years)
            bdir_dd = a.output / "v40-winsor-calibrated_dd_guard"
            bdir_dd.mkdir()
            gsig.to_parquet(bdir_dd / "signals.parquet", index=False)
            np.savez_compressed(bdir_dd / "predictions.npz",
                                prediction=np.load(bdir_best / "predictions.npz")["prediction"],
                                decision_indices=indices)
            (bdir_dd / "calibrators.json").write_text((bdir_best / "calibrators.json").read_text())
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
        b0 = diagnostics["v40-identity_1x"]["topdecile"]
        r0 = diagnostics["v40-identity_1x"]["rank_overall"]
        c0 = diagnostics["v40-identity_1x"]["coverage"]
        b1 = diagnostics["v40-winsor-calibrated_1x"]["topdecile"]
        r1 = diagnostics["v40-winsor-calibrated_1x"]["rank_overall"]
        c1 = diagnostics["v40-winsor-calibrated_1x"]["coverage"]
        deltas["v40-winsor-calibrated_1x"] = {
            "bias_before": float(b0["bias_pred_minus_obs"]),
            "bias_after": float(b1["bias_pred_minus_obs"]),
            "bias_delta": float(b1["bias_pred_minus_obs"] - b0["bias_pred_minus_obs"]),
            "pred_exp_mean_before": float(b0["pred_exp_mean"]),
            "pred_exp_mean_after": float(b1["pred_exp_mean"]),
            "obs_net_mean_ref": float(b0["obs_net_mean"]),
            "rank_before": float(r0["rank_corr_mean"]) if r0["rank_corr_mean"] is not None else None,
            "rank_after": float(r1["rank_corr_mean"]) if r1["rank_corr_mean"] is not None else None,
            "rank_delta": (float(r1["rank_corr_mean"] - r0["rank_corr_mean"])
                           if (r0["rank_corr_mean"] is not None and r1["rank_corr_mean"] is not None) else None),
            "coverage_before": float(c0), "coverage_after": float(c1),
            "coverage_delta": float(c1 - c0),
            "n_signals_before": int(diagnostics["v40-identity_1x"]["n_signals"]),
            "n_signals_after": int(diagnostics["v40-winsor-calibrated_1x"]["n_signals"])}
    except Exception as e:  # noqa: BLE001
        deltas = {"error": f"{type(e).__name__}: {e}"}
    # ---- summary.json ----
    input_files = [base["decisions"], base["labels"], base["candles"], base["dataset_config"],
                   base["parent_plan"], base["plan"], "configs/opencode_v90_v40wincal.json",
                   "scripts/opencode_r30a_v40wincal.py"]
    report = {"experiment": spec["experiment"], "family": spec["family"],
              "hypothesis": spec["hypothesis"], "branches": results,
              "diagnostic_v34_lens": diagnostics,
              "bias_rank_coverage_deltas": deltas,
              "order_preservation": {"max_rank_drift": max_rank_drift,
                                     "mean_abs_rank_drift": mean_rank_drift,
                                     "rank_mean_raw": mean_raw, "rank_mean_map": mean_map,
                                     "assert": "pass (monotone up-to-ties, viol==0; rank drift recorded, ties expected)"},
              "winsor_justification": {"step1_distribution": dist, "distribution_sha256": dist_hash,
                                       "step2_cap": cap, "cap_sha256": cap_hash,
                                       "prespec_distribution_sha256": prespec_hash,
                                       "distribution_match_prespec": dist_match,
                                       "order": "step1 distribution (val-only, no test) BEFORE step2 freeze cap",
                                       "why_pm1": spec["winsor"]["step1_distribution_before_choosing"]["justification"]},
              "calibration_records": calib_records,
              "fallback_by_fold": fallback_by_fold,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_c.total_return,
                                               "max_drawdown": res_c.max_drawdown,
                                               "trades": res_c.trades,
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
              "causality": "past-only closed-candle; winsor cap from pooled-val distribution only (4316 rows, no test); isotonic maps fit on eligible val-only history only (embargo 8d, current fold excluded); fallback ranking in fold uses no labels; fill from next candle",
              "warning": ("Opened development interval 2023-2026 only. Labels exploratory. "
                          "Drawdown trade-candle-close sampled, not true mark/intrabar. "
                          "Stop/timeout market-like at scenario fee. No live approval."),
              "input_sha256": {q: sha256(ROOT / q) for q in input_files},
              "output_note": "moi file duoi output dir la moi; khong ghi de lich su"}

    def fsha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    out_hashes = {}
    for q in sorted(a.output.rglob("*")):
        if q.is_file():
            if q.name == "summary.json":
                continue
            out_hashes[q.relative_to(a.output).as_posix()] = fsha(q)
    rep2 = json.loads((a.output / "summary.json").read_text())
    rep2["output_sha256"] = out_hashes
    (a.output / "summary.json").write_text(json.dumps(rep2, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
