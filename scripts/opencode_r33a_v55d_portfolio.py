"""Opencode R-AUDIT (round33 heartbeat worker): portfolio LOCAL cho v55c rankonly SSM.

Nguon: artifacts/kaggle/v55c_rankonly_download/rankonly-training (kernel
nguynchtrai/opencode-trackb-rankonly-v55c, COMPLETE, exit [0,0], missing []).
Plan dong bang: configs/opencode_v80_v55c.json (seeds 1729/1730/1731,
11 quarterly folds, RankOnlySSM 597409 params + ListNet-only + FIXED 16ep
+ rank-margin gate p70, KHONG value/aux/coverage-hinge, KHONG fallback).

Replay audit DA PASS truoc do (artifacts/research/opencode_v55d_replay/audit.json:
33/33 predictions (n,16) RAW rank logits finite, max replay error 2.86e-6,
plan-SHA + 29-file bundle byte_match, local 127 = cloud 127 signals).

Script nay CHI chay portfolio (pre-spec theo plan):
  ensemble mean 3 seeds logits -> gate margin > threshold_en(fold)
  (mean-3-seeds p70 tu audit.json, khong fallback, WAIT else) ->
  candidate = top1 argmax (first-max deterministic); KHONG du bao fill ->
  geometry + frequency loop giong swing_signals (monthly cap 4 + cooldown 5d
  tu dataset cfg) -> 2 branches (rankonly_en_1x, rankonly_en_dd_guard)
  x 3 scenarios (normal fee 0.0002, fee_stress 0.00055,
  execution_stress FillStress(5,5,5,0.00055,False)) + monthly geometric theo
  configs/swing_v15_continuous_folds.json + diagnostic lens
  (pass-rate vs 30%, rank-correlation, coverage).
  Dung du bao CLOUD (da verify parity + SHA).
  Ghi artifacts/research/opencode_v55d_replay/portfolio.json.

KHONG train/cloud/live. Labels exploratory, causal past-only.
"""
import torch  # noqa: F401  (import truoc pandas: DLL load-order tren Windows host)
import hashlib
import json
import sys
from collections import Counter
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
from opencode_r17b_rankonly_model import rank_logits_to_signals, rank_top1_margin_np  # noqa: E402
from train_tcn_kaggle import write_json  # noqa: E402

SPEC_NOTE = "pre-spec = configs/opencode_v80_v55c.json (branches_eval, mapping_rank_to_signal p70)"
PLAN_PATH = ROOT / "configs/opencode_v80_v55c.json"
PARENT_PATH = ROOT / "configs/swing_v15_continuous_folds.json"
SOURCE = ROOT / "artifacts/kaggle/v55c_rankonly_download/rankonly-training"
OUT_DIR = ROOT / "artifacts/research/opencode_v55d_replay"
SEEDS = [1729, 1730, 1731]
TOPK = 408  # top-decile x 4076 decisions (giong v34/v38b)


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


def v55c_policy_signals(ensemble, part, cfg, fold_of, thresholds):
    """Tin hieu theo mapping chuan v55 (khong che).

    ensemble: (n,16) mean-3-seeds RAW rank logits. Moi fold-test: giu
    decisions co margin > threshold_en(fold) (p70 past-only, KHONG fallback).
    Candidate: top1 argmax (first-max deterministic). Geometry (prices) +
    frequency loop (monthly cap + cooldown) giong swing_signals.
    """
    logits = np.asarray(ensemble, dtype=np.float64)
    top1, margins = rank_top1_margin_np(logits)
    n = len(part)
    if len(fold_of) != n:
        raise ValueError("fold index mismatch")
    chosen = np.full(n, -1, dtype=np.int64)
    picks_by_fold = {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        thr = float(thresholds[str(f)])
        pick = idx[margins[idx] > thr]
        chosen[pick] = top1[pick]
        picks_by_fold[str(f)] = int(len(pick))
    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    if cand_grid.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    policy, signals = cfg["policy"], []
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    for i, row in enumerate(part.itertuples()):
        k = int(chosen[i])
        if k < 0:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp,
                        "fold_test": int(fold_of[i]),
                        "action": "LONG" if cand_grid[k, 0] == 1 else "SHORT",
                        "direction": int(cand_grid[k, 0]), "candidate_id": k,
                        **prices(float(row.close), float(row.atr5), float(row.atr4),
                                 cand_grid[k], cfg),
                        "rank_margin_logit": float(margins[i]),
                        "rank_threshold_logit": float(thresholds[str(int(fold_of[i]))]),
                        "calibrated": False, "entry_expiry_bars": cfg["entry_expiry_bars"],
                        "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    cols = ["bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
            "take_profit_1", "take_profit_2", "holding_bars"]
    frame = pd.DataFrame(signals)
    if len(frame) and not set(cols).issubset(frame.columns):
        raise ValueError("Unexpected signal schema")
    info = {"picks_pre_frequency": int((chosen >= 0).sum()),
            "pick_rate_pre_frequency": float((chosen >= 0).mean()),
            "picks_by_fold": picks_by_fold, "n_signals": len(frame)}
    return frame, info, chosen, margins, top1


DD_TRIGGER, DD_GUARD_LEV = 0.1, 0.5
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def dd_guard_leverage(signals, trades):
    """0.5 khi equity 1x own-book dang >10% duoi trailing peak (past-only), else 1.0."""
    equity_at = sorted((pd.Timestamp(t.exit_time), t.equity_after) for t in trades)
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signals["signal_time"]):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak, level = float(curve.cummax().iloc[-1]), float(curve.iloc[-1])
        out.append(DD_GUARD_LEV if level / peak < 1.0 - DD_TRIGGER else 1.0)
    return np.array(out)


def run_branch(candles, signals, costs, execution, years, bdir):
    from dataclasses import asdict
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
                      "annual_geometric_net": ratio ** (1 / years) - 1,
                      "monthly_geometric_net": ratio ** (1 / (12 * years)) - 1}
        rows = [asdict(t) for t in items]
        dest = bdir / f"{label}_trades.csv"
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(dest, index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(dest, index=False)
    out["execution_stress"]["diagnostics"] = diag
    return out, trades


def diagnostic_lens(ensemble, part, cfg, labels_all, indices, fold_of, thresholds):
    logits = np.asarray(ensemble, dtype=np.float64)
    top1, margins = rank_top1_margin_np(logits)
    signals, info, chosen, _, _ = v55c_policy_signals(ensemble, part, cfg, fold_of, thresholds)
    months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
    truth = labels_all[indices]
    order = np.argsort(margins, kind="stable")[-TOPK:]
    k = top1[order]
    mg = margins[order]
    rn = truth[order, k, 0]
    rf = truth[order, k, 1]
    rp = truth[order, k, 2]
    filled = rf == 1
    per = rank_corr_per_decision(logits, truth[:, :, 0])
    valid = per[~np.isnan(per)]
    per_fold = {}
    for f in sorted(set(fold_of.tolist())):
        v = per[fold_of == f]
        v = v[~np.isnan(v)]
        per_fold[str(f)] = {"n": int(len(v)),
                            "rank_corr_mean": float(v.mean()) if len(v) else None}
    return {
        "margin_distribution": {f"margin_{kk}": vv for kk, vv in qstats(margins).items()},
        "pass_rate_vs_30pct": {
            "picked_pre_frequency": info["picks_pre_frequency"],
            "pick_rate_pre_frequency": info["pick_rate_pre_frequency"],
            "expected_rate": 0.30, "picks_by_fold": info["picks_by_fold"]},
        "n_signals": int(len(signals)), "coverage": float(len(signals) / len(part)),
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
        "topmargin_decile": {"n": int(TOPK), "margin_mean_logit": float(mg.mean()),
                             "obs_net_mean_pct": float(rn.mean()),
                             "obs_fill_rate": float(rf.mean()),
                             "obs_pos_given_fill": float(rp[filled].mean()) if filled.any() else None,
                             "units_warning": "margin la logit ordinal, realized net la %: "
                             "so trung binh khong cung don vi, chi rank_corr la so sanh hop le"},
        "rank_overall": {"n": int(len(part)), "n_valid": int(len(valid)),
                         "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                         "rank_corr_std": float(valid.std()) if len(valid) else None},
        "rank_by_fold": per_fold,
    }


def main():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "rankonly_ssm_v55"
    assert plan["branches_eval"] == ["rankonly_en_1x", "rankonly_en_dd_guard"]
    parent = json.loads(PARENT_PATH.read_text(encoding="utf-8"))
    audit = json.loads((OUT_DIR / "audit.json").read_text(encoding="utf-8"))
    if audit.get("state") != "passed" or not audit.get("all_forecasts_replayed"):
        raise ValueError("Replay audit chua PASS: chan portfolio")
    if audit.get("source_summary_sha256") != sha256(SOURCE / "summary.json"):
        raise ValueError("Audit thuoc ve training export khac")
    out_file = OUT_DIR / "portfolio.json"
    if out_file.exists():
        raise FileExistsError("Khong ghi de portfolio cu")
    thresholds = audit["thresholds_ensemble_mean"]
    ds = ROOT / plan["dataset"]
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]
    end = pd.Timestamp(parent["complete_evaluation_until"])
    partitions, fold_of_parts = [], []
    for f, (start, stop) in enumerate(parent["folds"]):
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        idx = np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop)
                              & (decisions.label_end < end)).to_numpy())
        partitions.append(idx)
        fold_of_parts.append(np.full(len(idx), f, dtype=np.int64))
    indices = np.concatenate(partitions)
    fold_of = np.concatenate(fold_of_parts)
    forecasts = []
    for fold in range(len(parent["folds"])):
        selected = partitions[fold]
        batch = []
        for seed in SEEDS:
            path = SOURCE / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            pred = np.load(path, allow_pickle=False)
            if pred.shape != (len(selected), 16) or not np.isfinite(pred).all():
                raise ValueError(f"Prediction shape/values mismatch: {path}")
            batch.append(pred)
        forecasts.append(np.stack(batch))
    part = decisions.iloc[indices].reset_index(drop=True)
    stacked = np.concatenate(forecasts, axis=1)  # (3 seeds, n, 16)
    ensemble = stacked.mean(axis=0)
    signals, pinfo, _, _, _ = v55c_policy_signals(ensemble, part, cfg, fold_of, thresholds)
    if len(signals) != audit["policy"]["cloud_signals"]:
        raise ValueError(f"Portfolio signals khac audit parity: {len(signals)} vs "
                         f"{audit['policy']['cloud_signals']}")
    if pinfo["picks_pre_frequency"] != audit["policy"]["picked_pre_frequency"]:
        raise ValueError("Pre-frequency picks khac audit")
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    gate = {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30,
            "scenarios": ["normal", "fee_stress", "execution_stress"]}
    diagnostics = {"rankonly_en": diagnostic_lens(ensemble, part, cfg, labels_all,
                                                  indices, fold_of, thresholds)}
    branches = {}
    bdir1 = OUT_DIR / "rankonly_en_1x"
    bdir1.mkdir(parents=True, exist_ok=True)
    base = signals.drop(columns=["leverage"], errors="ignore").copy()
    base.to_parquet(bdir1 / "signals.parquet", index=False)
    exec1x = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    res1x, trades1x = run_branch(candles, base, costs, exec1x, years, bdir1)
    guard = dd_guard_leverage(base, trades1x)
    bdd = OUT_DIR / "rankonly_en_dd_guard"
    bdd.mkdir(parents=True, exist_ok=True)
    gsig = base.copy()
    gsig["leverage"] = guard
    gsig.to_parquet(bdd / "signals.parquet", index=False)
    execdd = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                             max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
    resdd, _tdd = run_branch(candles, gsig, costs, execdd, years, bdd)
    months = pd.period_range(part.signal_time.iloc[0].tz_localize(None),
                             part.signal_time.iloc[-1].tz_localize(None), freq="M")
    for key, res, sig in (("rankonly_en_1x", res1x, base),
                          ("rankonly_en_dd_guard", resdd, gsig)):
        counts = sig.signal_time.dt.strftime("%Y-%m").value_counts() if len(sig) else {}
        branches[key] = {
            "scenarios": res,
            "n_signals": int(len(sig)),
            "n_decisions": int(len(part)),
            "coverage": float(len(sig) / len(part)),
            "signals_by_month": {str(m): int(counts.get(str(m), 0)) for m in months},
            "passes_gate_all_scenarios": bool(all(
                res[s]["monthly_geometric_net"] >= gate["monthly_min"]
                and res[s]["max_drawdown"] >= -gate["dd_max"]
                and res[s]["trades"] >= gate["fills_min"]
                for s in gate["scenarios"])),
            "dd_safe_all_scenarios": bool(all(
                res[s]["max_drawdown"] >= -gate["dd_max"] for s in gate["scenarios"])),
        }
        print(json.dumps({"branch": key, "gate": branches[key]["passes_gate_all_scenarios"],
                          "metrics": {s: {kk: res[s][kk] for kk in
                                          ("total_return", "max_drawdown", "trades",
                                           "monthly_geometric_net", "gross_pnl", "fees",
                                           "funding", "profit_factor", "win_rate")}
                                      for s in gate["scenarios"]}}), flush=True)
    report = {"experiment": "opencode-r26b-rankonly-selective-ssm-v55c-audit",
              "prespec_note": SPEC_NOTE,
              "policy_spec": {"ensemble": "mean_3seeds RAW rank logits (giong audit parity)",
                              "gate": "margin > threshold_en(fold)=mean-3-seeds p70 "
                              "(pre-spec plan, KHONG fallback, WAIT else)",
                              "candidate": "top1 argmax (first-max deterministic); "
                              "KHONG du bao fill (rank-only disclosure)",
                              "geometry_frequency": "cfg prices + monthly-cap/cooldown loop "
                              "(giong swing_signals)",
                              "selection_detail": pinfo},
              "branches": branches,
              "duration_years": years,
              "gate": gate,
              "standing_best": {"majority_1x": "2.935%/mo (DD breach)",
                                "confirmed_dd_guard": "2.79/2.67/2.06 DD-safe all scenarios"},
              "multitask_anchor_v38": {"rank": "+0.066 (tot nhat trong cac model fresh, ~v29); "
                                       "monthly 1.1-1.5%, DD breach 6/6",
                                       "key_question": "ranking-alone (v55c) vs "
                                       "ranking-in-multitask (v38): xem rank_overall"},
              "diagnostic_lens": diagnostics,
              "training_notes": {"parameters": audit["parameters"],
                                 "fixed_epochs": audit["fixed_epochs"],
                                 "train_loss_first_mean": audit["train_loss_first_mean"],
                                 "train_loss_last_mean": audit["train_loss_last_mean"],
                                 "val_loss_last_mean": audit["val_loss_last_mean"],
                                 "max_replay_error": audit["max_replay_error"],
                                 "calibration": "KHONG isotonic (khong co absolute score); "
                                 "nguong la validation-percentile tren rank-margin (ordinal)",
                                 "ranking_loss": "ListNet duy nhat (bo value/aux/coverage-hinge): "
                                 "rank duoc do o diagnostic_lens",
                                 "coverage": "qua relative gate (p70 bao ~30% test qua gate "
                                 "neu phan phoi on dinh)"},
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": "own-book 1x equity, trigger 10%, lev 0.5/1.0, "
                           "past-only (giong v28c/v33d/v35b/v38b)",
                           "monthly_geometric": "tu configs/swing_v15_continuous_folds.json",
                           "frequency": "monthly cap 4 + cooldown 5d, giong swing_signals"},
              "audit_sha256": sha256(OUT_DIR / "audit.json"),
              "training_summary_sha256": sha256(SOURCE / "summary.json"),
              "plan_sha256": sha256(PLAN_PATH),
              "independent_test": False, "exploratory": True, "live_approved": False,
              "warning": "Opened development interval only (2023-2026). Drawdown close-sampled; "
                         "stop/timeout market-like. KHONG live approval."}
    out_file.write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(out_file))


if __name__ == "__main__":
    main()
