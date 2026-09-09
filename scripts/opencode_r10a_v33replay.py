"""Opencode R10-A (R-AUDIT, tiep noi R-diagnostic v34): replay audit + portfolio LOCAL cho v33 action-margin GRU.

Nguon: artifacts/kaggle/v33_actionmargin_download/tcn-training (kernel
nguynchtrai/btc-swing-v33-action-margin-20260906, COMPLETE, [0,0]).
Plan dong bang: configs/swing_v33_action_margin_gru.json.
Pre-spec: configs/opencode_v33d.json (viet TRUOC khi chay).

(1) Audit: nap lai 33 checkpoints (11 folds x 3 seeds), verify summary +
    plan JSON-equality + metadata + weights/prediction sha + indices +
    feature stats + predict_action_margin local (CUDA) vs cloud (rtol/atol 1e-3)
    + combine(mean/mms) + swing_signals parity. Ghi audit.json.
(2) Portfolio: 6 branches (2 ensemble x {1x, 0.5x, dd_guard}) x 3 scenarios
    (normal, fee 0.00055, FillStress(5,5,5,0.00055,False)) + monthly geometric
    theo swing_v15_continuous_folds + diagnostic lens v34. Ghi portfolio.json.

KHONG train/cloud/live. Labels exploratory, causal past-only.
"""
import torch  # noqa: F401  (import truoc pandas: DLL load-order tren Windows host)
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from safetensors.torch import load_file

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.backtest.swing import swing_signals  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402
from agentic_alpha_lab.models.action_margin_value import ActionMarginValue, predict_action_margin  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from train_tcn_kaggle import digest, fold_indices, load_inputs, stable_evaluation_backend, write_json  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v33d.json"
PLAN_PATH = ROOT / "configs/swing_v33_action_margin_gru.json"
SOURCE = ROOT / "artifacts/kaggle/v33_actionmargin_download/tcn-training"
OUT_DIR = ROOT / "artifacts/research/opencode_v33d_replay"
TOPK = 408  # top-decile x 4076 decisions (giong v34)


def qstats(x):
    x = np.asarray(x, dtype=np.float64)
    return {"mean": float(x.mean()), "std": float(x.std()), "min": float(x.min()),
            "p10": float(np.quantile(x, 0.10)), "p50": float(np.quantile(x, 0.50)),
            "p90": float(np.quantile(x, 0.90)), "p95": float(np.quantile(x, 0.95)),
            "p99": float(np.quantile(x, 0.99)), "max": float(x.max())}


def fill_of(pred):
    return 1 / (1 + np.exp(-np.clip(pred[..., 4], -40, 40)))


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


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    spec = json.loads(SPEC_PATH.read_text())
    plan = json.loads(PLAN_PATH.read_text())
    assert plan["model_family"] == "gru_action_margin"
    assert plan["cloud_driver"] == "train_gru_action_margin.py"
    if OUT_DIR.exists():
        raise FileExistsError("Khong ghi de audit cu; dung dir moi")
    summary = json.loads((SOURCE / "summary.json").read_text())
    if summary.get("state") != "complete" or summary.get("worker_exit_codes") != [0, 0] \
            or summary.get("missing_or_failed"):
        raise ValueError("All registered cloud jobs must complete before audit")
    if summary.get("plan") != plan:
        raise ValueError("Export plan differs from registered plan (JSON)")
    parent = json.loads((ROOT / plan["parent_plan"]).read_text())
    sequence, features, labels, decisions, candidates = load_inputs(plan)
    cfg = json.loads((ROOT / plan["dataset"] / "config.json").read_text())
    assert candidates.shape == (16, 6)
    margin_scale = float(plan["loss"]["margin_scale_percent"])
    OUT_DIR.mkdir(parents=True)
    records, forecast_hashes, weight_hashes = [], {}, {}
    local_by_seed, cloud_by_seed, indices = [], [], None
    train_losses, params = {}, None
    device = "cuda"
    if not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; local audit yeu cau GPU")
    for seed in plan["seeds"]:
        local_parts, cloud_parts, index_parts = [], [], []
        for fold in range(len(parent["folds"])):
            target = SOURCE / f"seed{seed}/checkpoints/fold_{fold}"
            meta = json.loads((target / "metadata.json").read_text())
            if meta.get("state") != "complete" or not meta.get("gpu_reload_parity"):
                raise ValueError("Incomplete or parity-failed checkpoint")
            if meta["network"] != plan["network"] or meta["training"] != plan["training"] \
                    or meta["loss"] != plan["loss"] or meta["seed"] != seed or meta["fold"] != fold:
                raise ValueError("Checkpoint experiment mismatch")
            if meta["model_family"] != "gru_action_margin":
                raise ValueError("Checkpoint architecture identity mismatch")
            if meta["dataset_manifest_sha256"] != digest(ROOT / plan["dataset"] / "manifest.json") \
                    or meta["cache_manifest_sha256"] != digest(ROOT / plan["cache"] / "manifest.json"):
                raise ValueError("Checkpoint input identity mismatch")
            if params is None:
                params = meta["parameters"]
            elif params != meta["parameters"]:
                raise ValueError("Parameter count changed across folds")
            hist = meta["training_loss"]
            if len(hist) != plan["training"]["epochs"]:
                raise ValueError("Not fixed-epoch training")
            train_losses[f"{seed}/{fold}"] = hist
            train, test = fold_indices(decisions, parent, plan["training"], fold)
            with np.load(target / "indices.npz", allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved["train"], train)
                np.testing.assert_array_equal(saved["test"], test)
            weights = target / "model.safetensors"
            if digest(weights) != meta["weights_sha256"]:
                raise ValueError("Checkpoint weights changed")
            weight_hashes[weights.relative_to(SOURCE).as_posix()] = digest(weights)
            model = ActionMarginValue(candidates, **plan["network"])
            model.load_state_dict(load_file(str(weights)))
            np.testing.assert_array_equal(model.candidates.numpy(), candidates)
            np.testing.assert_allclose(model.feature_mean.numpy(), features[train].mean(0),
                                       rtol=1e-5, atol=1e-6)
            np.testing.assert_allclose(model.feature_scale.numpy(),
                                       np.maximum(features[train].std(0), 1e-6),
                                       rtol=1e-5, atol=1e-6)
            model.to(device)
            prediction_path = SOURCE / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            if digest(prediction_path) != meta["prediction_sha256"]:
                raise ValueError("Export prediction changed")
            cloud = np.load(prediction_path, allow_pickle=False)
            if cloud.shape != (len(test), 16, 6) or not np.isfinite(cloud).all():
                raise ValueError("Invalid exported prediction shape/values")
            local = predict_action_margin(model, sequence[test], features[test],
                                          batch_size=128, margin_scale_percent=margin_scale)
            if local.shape != cloud.shape or not np.isfinite(local).all():
                raise ValueError("Nonfinite/misaligned replay predictions")
            np.testing.assert_allclose(local, cloud, rtol=1e-3, atol=1e-3)
            error = float(np.max(np.abs(local - cloud)))
            row = {"seed": seed, "fold": fold, "decisions": len(test),
                   "epochs": len(hist), "last_train_loss": float(hist[-1]),
                   "max_error": error}
            records.append(row)
            forecast_hashes[prediction_path.relative_to(SOURCE).as_posix()] = digest(prediction_path)
            local_parts.append(local)
            cloud_parts.append(cloud)
            index_parts.append(test)
            print(json.dumps(row), flush=True)
            write_json(OUT_DIR / "progress.json",
                       {"completed": len(records), "last": row, "state": "auditing"})
            del model
            torch.cuda.empty_cache()
        current = np.concatenate(index_parts)
        if indices is not None:
            np.testing.assert_array_equal(current, indices)
        indices = current
        local_by_seed.append(np.concatenate(local_parts))
        cloud_by_seed.append(np.concatenate(cloud_parts))
    from research_temporal_continuous import partition_indices
    np.testing.assert_array_equal(indices, np.concatenate(partition_indices(decisions, parent)))
    local_all, cloud_all = np.stack(local_by_seed), np.stack(cloud_by_seed)
    signal_rows = {}
    for branch in plan["ensemble_branches"]:
        local, _ = combine(local_all, branch["penalty"])
        cloud, _ = combine(cloud_all, branch["penalty"])
        clock = decisions.iloc[indices].reset_index(drop=True)
        ls = swing_signals(local.astype(np.float32), clock, cfg)
        cs = swing_signals(cloud.astype(np.float32), clock, cfg)
        if len(ls) != len(cs):
            raise ValueError("Local/cloud policy alert count differs")
        if len(ls):
            columns = ["bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
                       "take_profit_1", "take_profit_2", "holding_bars", "leverage"]
            pd.testing.assert_frame_equal(ls[columns].reset_index(drop=True),
                                          cs[columns].reset_index(drop=True), check_exact=True)
        signal_rows[branch["name"]] = len(ls)
    with (SOURCE / "bundle-hashes.json").open("rb") as fh:
        bundle_hash_note = hashlib.file_digest(fh, "sha256").hexdigest()
    result = {"state": "passed", "model_family": "gru_action_margin", "device": device,
              "torch": torch.__version__, "batch_size": 128, "rtol": 0.001, "atol": 0.001,
              "margin_scale_percent": margin_scale,
              "folds": records, "max_replay_error": max(r["max_error"] for r in records),
              "parameters": params, "fixed_epochs": plan["training"]["epochs"],
              "source_summary_sha256": digest(SOURCE / "summary.json"),
              "plan_sha256": digest(PLAN_PATH),
              "plan_json_equal_summary_plan": True,
              "source_identity_note": "byte-sha source check mien tren Windows (CRLF vs LF cua bundle Kaggle; "
                                      "nd JSON dong nhat). Bao dam bang manifest-sha trong metadata + "
                                      "weights/prediction-sha + indices + feature-stats + numeric parity.",
              "bundle_hashes_sha256": bundle_hash_note,
              "dataset_manifest_sha256": digest(ROOT / plan["dataset"] / "manifest.json"),
              "cache_manifest_sha256": digest(ROOT / plan["cache"] / "manifest.json"),
              "prediction_files": forecast_hashes, "weight_files": weight_hashes,
              "identical_policy_signals": signal_rows,
              "all_forecasts_replayed": True, "independent_test": False, "live_approved": False}
    write_json(OUT_DIR / "audit.json", result)
    print(json.dumps({"state": "passed", "max_replay_error": result["max_replay_error"],
                      "signals": signal_rows, "parameters": params}))


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


def sig_info(name, combo, part, cfg, labels_all, indices):
    n = len(part)
    fill = fill_of(combo)
    exp = combo[..., 0] * fill
    best_exp = exp.max(1)
    arg = exp.argmax(1)
    best_fill = fill[np.arange(n), arg]
    policy_net = float(cfg["policy"]["minimum_expected_net_percent"])
    policy_fill = float(cfg["policy"]["minimum_fill_score"])
    pass_net = best_exp >= policy_net
    pass_both = pass_net & (best_fill >= policy_fill)
    signals = swing_signals(combo.astype(np.float32), part, cfg)
    months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
    truth = labels_all[indices]
    order = np.argsort(best_exp, kind="stable")[-TOPK:]
    k = exp[order].argmax(1)
    pe = exp[order, k]
    rn = truth[order, k, 0]
    rf = truth[order, k, 1]
    rp = truth[order, k, 2]
    filled = rf == 1
    net_map = exp
    per = rank_corr_per_decision(net_map, truth[:, :, 0])
    valid = per[~np.isnan(per)]
    return {
        "score_distribution": {f"best_exp_{kk}": vv for kk, vv in qstats(best_exp).items()},
        "threshold_pass": {"pass_net_n": int(pass_net.sum()), "pass_net_rate": float(pass_net.mean()),
                           "pass_both_n": int(pass_both.sum()),
                           "pass_both_rate": float(pass_both.mean())},
        "n_signals": int(len(signals)), "coverage": float(len(signals) / n),
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


def run_portfolio():
    spec = json.loads(SPEC_PATH.read_text())
    plan = json.loads(PLAN_PATH.read_text())
    parent = json.loads((ROOT / plan["parent_plan"]).read_text())
    audit = json.loads((OUT_DIR / "audit.json").read_text())
    if audit.get("state") != "passed" or not audit.get("all_forecasts_replayed"):
        raise ValueError("Replay audit chua PASS: chan portfolio")
    if audit.get("source_summary_sha256") != sha256(SOURCE / "summary.json"):
        raise ValueError("Audit thuoc ve training export khac")
    out_file = OUT_DIR / "portfolio.json"
    if out_file.exists():
        raise FileExistsError("Khong ghi de portfolio cu")
    ds = ROOT / plan["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]
    end = pd.Timestamp(parent["complete_evaluation_until"])
    partitions = []
    for start, stop in parent["folds"]:
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        partitions.append(np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop)
                                          & (decisions.label_end < end)).to_numpy()))
    indices = np.concatenate(partitions)
    forecasts = []
    for fold in range(len(parent["folds"])):
        selected = partitions[fold]
        batch = []
        for seed in plan["seeds"]:
            path = SOURCE / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            pred = np.load(path, allow_pickle=False)
            if pred.shape != (len(selected), 16, 6) or not np.isfinite(pred).all():
                raise ValueError(f"Prediction shape/values mismatch: {path}")
            batch.append(pred)
        forecasts.append(np.stack(batch))
    part = decisions.iloc[indices].reset_index(drop=True)
    stacked = np.concatenate(forecasts, axis=1)
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    gate, branches, diagnostics = spec["gate"], {}, {}
    combos = {}
    for branch in plan["ensemble_branches"]:
        combined, details = combine(stacked, branch["penalty"])
        combos[branch["name"]] = (combined, details)
        diagnostics[branch["name"]] = sig_info(branch["name"], combined, part, cfg,
                                               labels_all, indices)
    for name, (combined, _details) in combos.items():
        signals = swing_signals(combined.astype(np.float32), part, cfg)
        tag = "mean" if name == "mean" else "mean_minus_std"
        if len(signals) != audit["identical_policy_signals"][name]:
            raise ValueError(f"Portfolio signals khac audit parity: {name}")
        bdir1 = OUT_DIR / f"{tag}_1x"
        bdir1.mkdir(parents=True, exist_ok=True)
        base = signals.drop(columns=["leverage"], errors="ignore").copy()
        base.to_parquet(bdir1 / "signals.parquet", index=False)
        exec1x = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                 max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
        res1x, trades1x = run_branch(candles, base, costs, exec1x, years, bdir1)
        bdir05 = OUT_DIR / f"{tag}_0.5x"
        bdir05.mkdir(parents=True, exist_ok=True)
        base.to_parquet(bdir05 / "signals.parquet", index=False)
        exec05 = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                 max_holding_bars=cap, leverage=0.5, max_leverage=0.5)
        res05, _t05 = run_branch(candles, base, costs, exec05, years, bdir05)
        guard = dd_guard_leverage(base, trades1x)
        bdd = OUT_DIR / f"{tag}_dd_guard"
        bdd.mkdir(parents=True, exist_ok=True)
        gsig = base.copy()
        gsig["leverage"] = guard
        gsig.to_parquet(bdd / "signals.parquet", index=False)
        execdd = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                 max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
        resdd, _tdd = run_branch(candles, gsig, costs, execdd, years, bdd)
        months = pd.period_range(part.signal_time.iloc[0].tz_localize(None),
                                 part.signal_time.iloc[-1].tz_localize(None), freq="M")
        for key, res, sig in ((f"{tag}_1x", res1x, base),
                              (f"{tag}_0.5x", res05, base),
                              (f"{tag}_dd_guard", resdd, gsig)):
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
    report = {"experiment": spec["experiment"], "branches": branches,
              "duration_years": years, "gate": gate,
              "standing_best": spec["standing_best"],
              "comparison": "So truc tiep voi standing_best (majority_1x 2.935%/mo DD breach; confirmed_dd_guard 2.79%/mo DD-safe) va gate.",
              "diagnostic_v34_lens": diagnostics,
              "training_notes": {"parameters": audit["parameters"],
                                 "fixed_epochs": audit["fixed_epochs"],
                                 "margin_scale_percent": audit["margin_scale_percent"],
                                 "calibration": "KHONG calibrate (margin tho, khong isotonic) — bias tho duoc do o diagnostic",
                                 "ranking_loss": "KHONG co pairwise/listwise ranking loss (action-margin objective) — rank duoc do o diagnostic"},
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "fixed_0.5x": "ExecutionConfig leverage=0.5 max_leverage=0.5 (exposure trong plan)",
                           "dd_guard": "own-book 1x equity, trigger 10%, lev 0.5/1.0, past-only (tien le v03, giong v28c)",
                           "frequency": "swing_signals: monthly cap + cooldown, giong audit parity"},
              "audit_sha256": sha256(OUT_DIR / "audit.json"),
              "training_summary_sha256": sha256(SOURCE / "summary.json"),
              "independent_test": False, "exploratory": True, "live_approved": False,
              "warning": "Opened development interval only (2023-2026). Drawdown close-sampled; stop/timeout market-like. KHONG live approval."}
    out_file.write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(out_file))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--portfolio", action="store_true")
    a = p.parse_args()
    if a.portfolio:
        run_portfolio()
    else:
        main(a)
