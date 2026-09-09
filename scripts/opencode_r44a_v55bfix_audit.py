"""Opencode R-AUDIT (round44 heartbeat worker): replay audit + portfolio LOCAL
cho v55bfix rankonly-SSM scale-cap (kernel trainguyenchi/opencode-trackb-rankonly-v55bfix,
account-2 failover, COMPLETE poll 18, exit [0,0], missing []).

Plan dong bang: configs/opencode_v111_v55bfix_acc2.json (B viet; seeds 1729/1730/1731,
11 quarterly folds, RankOnlySSM 597409 params + ListNet-only + FIXED 16ep
+ rank-margin gate p70 tren CAPPED margins + tanh cap 3.0 + allowlist fix
macro_micro_value.py; KHONG value/aux/coverage-hinge, KHONG fallback).
Ban bundled trong dataset (source/configs/opencode_v111_v55bfix.json) giong
het phan chuc nang, chi khac metadata slugs/queue (failover acc1->acc2, co ghi nhan).

(1) Audit: nap lai 33 checkpoints, verify summary + plan JSON (functional-equal,
metadata-slugs recorded) + bundle-hashes (byte-sha; text chuan hoa CRLF) +
metadata (state/parity/weights-sha/prediction-sha/model_family/params) +
FIXED-16 record (training == plan training, 16 losses, validation past-only qua
nested_split) + train/test indices + feature stats (flat[train]) +
predict_capped local (GTX1650 inference) vs cloud (rtol/atol 1e-3) +
policy signals parity (local vs cloud, capped ensemble + mean thresholds).
Ghi artifacts/research/opencode_v111b_replay/audit.json.
(2) Portfolio (pre-spec theo plan): ensemble mean 3 seeds CAPPED logits ->
gate margin > threshold_en(fold) (mean-3-seeds p70, khong fallback, WAIT else) ->
candidate = top1 argmax (first-max deterministic); KHONG du bao fill ->
geometry + frequency loop giong swing_signals (monthly cap 4 + cooldown 5d
tu dataset cfg) -> 2 branches (rankonly_en_1x, rankonly_en_dd_guard)
x 3 scenarios (normal fee 0.0002, fee_stress 0.00055,
execution_stress FillStress(5,5,5,0.00055,False)) + monthly geometric theo
configs/swing_v15_continuous_folds.json + diagnostic lens
(pass-rate vs 30%, rank-correlation, coverage, cap bind-frac).
Dung du bao CLOUD (da verify parity + SHA).
Ghi artifacts/research/opencode_v111b_replay/portfolio.json.

KHONG train/cloud/live. Labels exploratory, causal past-only.
"""
import torch  # noqa: F401  (import truoc pandas: DLL load-order tren Windows host)
import hashlib
import json
from collections import Counter
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
from agentic_alpha_lab.data.swing import grid, prices  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import nested_split  # noqa: E402
from opencode_r17b_rankonly_model import predict_rank, rank_top1_margin_np  # noqa: E402
from opencode_r21b_v55b_model import LOGIT_CAP, cap_rank_logits_np  # noqa: E402
from opencode_r21b_v55b_features import N_FLAT, build_flat  # noqa: E402
import opencode_r21b_v55b_train as v55train  # noqa: E402
from train_tcn_kaggle import write_json  # noqa: E402

SPEC_NOTE = "pre-spec = configs/opencode_v111_v55bfix_acc2.json (branches_eval, mapping_rank_to_signal p70, cap tanh 3.0)"
PLAN_PATH = ROOT / "configs/opencode_v111_v55bfix_acc2.json"
BUNDLED_PLAN = "source/configs/opencode_v111_v55bfix.json"
PARENT_PATH = ROOT / "configs/swing_v15_continuous_folds.json"
SOURCE = ROOT / "artifacts/kaggle/v55bfix_acc2_download/v55b-training"
OUT_DIR = ROOT / "artifacts/research/opencode_v111b_replay"
SEEDS = [1729, 1730, 1731]
FIXED_EPOCHS = 16
TOPK = 408
TEXT_SUFFIXES = (".py", ".json")
META_ONLY_KEYS = ("cloud", "owner_slug_suggestion", "queue", "failover_record")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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


def verify_fixed_epochs(plan, decisions, parent, seed, fold, meta):
    spec = plan["epoch_selection"]
    if not str(spec.get("mode", "")).startswith("FIXED"):
        raise ValueError("Plan epoch mode changed (expected FIXED)")
    if not str(meta.get("epoch_mode", "")).startswith("FIXED"):
        raise ValueError("Checkpoint epoch mode changed (expected FIXED)")
    if meta.get("training") != plan["training"]:
        raise ValueError("Checkpoint training config differs from plan")
    if len(meta.get("training_loss", [])) != FIXED_EPOCHS:
        raise ValueError("Checkpoint did not train FIXED 16 epochs")
    if len(meta.get("val_loss_by_epoch", [])) != FIXED_EPOCHS:
        raise ValueError("Checkpoint epoch histories incomplete")
    keys = ("window_days", "validation_days", "embargo_days", "minimum_train", "minimum_validation")
    _train, val, clock = nested_split(decisions, parent["folds"][fold][0],
                                      **{k: spec[k] for k in keys})
    if meta.get("validation_clock") != clock:
        raise ValueError("Validation chronology mismatch")
    if int(meta.get("validation_decisions", -1)) != len(val):
        raise ValueError("Validation count mismatch")
    target = SOURCE / f"seed{seed}/checkpoints/fold_{fold}"
    with np.load(target / "indices.npz", allow_pickle=False) as ix:
        np.testing.assert_array_equal(ix["validation"], val)
    return {"validation_count": len(val)}


def policy_signals(ensemble, part, cfg, fold_of, thresholds):
    """Chinh sach chuan v55b: capped-margin > threshold_en(fold), else WAIT."""
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


def diagnostic_lens(ensemble, part, cfg, labels_all, indices, fold_of, thresholds, bind_frac):
    logits = np.asarray(ensemble, dtype=np.float64)
    top1, margins = rank_top1_margin_np(logits)
    signals, info, chosen, _, _ = policy_signals(ensemble, part, cfg, fold_of, thresholds)
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
        "cap_bind_frac_test": bind_frac,
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
    torch.set_num_threads(2)
    v55train.stable_backend()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "rankonly_ssm_v55b"
    assert plan["branches_eval"] == ["rankonly_en_1x", "rankonly_en_dd_guard"]
    assert plan["seeds"] == SEEDS
    assert int(plan["training"]["epochs"]) == FIXED_EPOCHS
    assert float(plan["training"]["scale_cap_logit"]) == LOGIT_CAP
    if OUT_DIR.exists():
        raise FileExistsError("Khong ghi de audit cu; dung dir moi")
    parent = json.loads(PARENT_PATH.read_text(encoding="utf-8"))
    summary = json.loads((SOURCE / "summary.json").read_text(encoding="utf-8"))
    if summary.get("state") != "complete" or summary.get("worker_exit_codes") != [0, 0] \
            or summary.get("missing_or_failed"):
        raise ValueError("All registered cloud jobs must complete before audit")
    bundled = json.loads((SOURCE / BUNDLED_PLAN).read_text(encoding="utf-8"))
    if summary.get("plan") != bundled:
        raise ValueError("Export plan differs from bundled plan (JSON)")
    func_equal = all(bundled.get(k) == plan.get(k) for k in bundled if k not in META_ONLY_KEYS)
    meta_diffs = [k for k in bundled if k in plan and bundled[k] != plan[k]]
    if not func_equal:
        raise ValueError("Functional plan sections differ from registered acc2 plan")
    bundle = json.loads((SOURCE / "bundle-hashes.json").read_text(encoding="utf-8"))
    bundle_check = {}
    for name, expected in bundle.items():
        local = ROOT / name
        blob = local.read_bytes()
        sha = hashlib.sha256(blob).hexdigest()
        if sha != expected:
            if local.suffix in TEXT_SUFFIXES and \
                    hashlib.sha256(blob.replace(b"\r\n", b"\n")).hexdigest() == expected:
                bundle_check[name] = "match_after_crlf_normalization"
            else:
                raise ValueError(f"Bundle identity mismatch: {name}")
        else:
            bundle_check[name] = "byte_match"
    ds = ROOT / plan["dataset"]
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    cache = ROOT / plan["cache"]
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert sequence.shape == (len(decisions), 5, 128, 6) and flat.shape == (len(decisions), N_FLAT)
    assert np.isfinite(sequence).all() and np.isfinite(flat).all()
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)
    with np.load(ds / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]
    for col in ("bar_index", "signal_time", "close", "atr5", "atr4"):
        if col not in decisions.columns:
            raise ValueError(f"decisions thieu cot {col}")
    OUT_DIR.mkdir(parents=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    records, forecast_hashes, weight_hashes, index_hashes = [], {}, {}, {}
    thresholds_by_seed = {str(s): {} for s in SEEDS}
    local_by_seed, cloud_by_seed, indices, fold_of_list = [], [], None, []
    raw_bind, params = [], None
    for seed in SEEDS:
        local_parts, cloud_parts, index_parts, fold_parts = [], [], [], []
        for fold in range(len(parent["folds"])):
            target = SOURCE / f"seed{seed}/checkpoints/fold_{fold}"
            meta = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
            if meta.get("state") != "complete" or not meta.get("gpu_reload_parity"):
                raise ValueError("Incomplete or parity-failed checkpoint")
            if meta.get("model_family") != "rankonly_ssm_v55b":
                raise ValueError("Checkpoint architecture identity mismatch")
            if meta["seed"] != seed or meta["fold"] != fold:
                raise ValueError("Checkpoint identity mismatch")
            if params is None:
                params = meta["parameters"]
            elif params != meta["parameters"]:
                raise ValueError("Parameter count changed across folds")
            if params != 597409:
                raise ValueError("Parameter count differs from plan (597409)")
            if meta.get("rank_gate", {}).get("percentile") != 70:
                raise ValueError("Gate percentile mismatch (expected p70)")
            if meta.get("rank_gate", {}).get("threshold_basis") != "CAPPED val margins (past-only)":
                raise ValueError("Threshold basis mismatch (expected CAPPED val margins)")
            verify_fixed_epochs(plan, decisions, parent, seed, fold, meta)
            index_hashes[(target / "indices.npz").relative_to(SOURCE).as_posix()] = \
                digest(target / "indices.npz")
            train, test = v55train.fold_indices(decisions, parent, plan, fold)
            with np.load(target / "indices.npz", allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved["train"], train)
                np.testing.assert_array_equal(saved["test"], test)
            weights = target / "model.safetensors"
            if digest(weights) != meta["weights_sha256"]:
                raise ValueError("Checkpoint weights changed")
            weight_hashes[weights.relative_to(SOURCE).as_posix()] = digest(weights)
            model = v55train.make_model(plan, candidates)
            model.load_state_dict(load_file(str(weights)))
            np.testing.assert_array_equal(model.candidates.numpy(), candidates)
            np.testing.assert_allclose(model.feature_mean.numpy(), flat[train].mean(0),
                                       rtol=1e-5, atol=1e-6)
            np.testing.assert_allclose(model.feature_scale.numpy(),
                                       np.maximum(flat[train].std(0), 1e-6),
                                       rtol=1e-5, atol=1e-6)
            model.to(device)
            prediction_path = SOURCE / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            if digest(prediction_path) != meta["prediction_sha256"]:
                raise ValueError("Export prediction changed")
            cloud = np.load(prediction_path, allow_pickle=False)
            if cloud.shape != (len(test), 16) or not np.isfinite(cloud).all():
                raise ValueError("Invalid exported prediction shape/values")
            if not (np.abs(cloud) <= LOGIT_CAP + 1e-6).all():
                raise ValueError("Export violates cap bound |logit|<=3.0")
            raw = predict_rank(model, sequence[test], flat[test], batch_size=32)
            if raw.shape != cloud.shape or not np.isfinite(raw).all():
                raise ValueError("Nonfinite/misaligned replay predictions")
            raw_bind.append(float((np.abs(raw) > LOGIT_CAP).mean()))
            local = cap_rank_logits_np(raw, LOGIT_CAP)
            np.testing.assert_allclose(local, cloud, rtol=1e-3, atol=1e-3)
            error = float(np.max(np.abs(local - cloud)))
            thresholds_by_seed[str(seed)][str(fold)] = float(
                meta["rank_gate"]["threshold_logit"])
            row = {"seed": seed, "fold": fold, "decisions": len(test),
                   "epochs_trained": len(meta["training_loss"]),
                   "train_loss_first": float(meta["training_loss"][0]),
                   "train_loss_last": float(meta["training_loss"][-1]),
                   "val_loss_last": float(meta["val_loss_by_epoch"][-1]),
                   "threshold_logit": float(meta["rank_gate"]["threshold_logit"]),
                   "test_pick_rate": float(meta["test_gate_preview"]["pick_rate"]),
                   "test_n_picked": int(meta["test_gate_preview"]["n_picked"]),
                   "gpu_reload_max_error": float(meta.get("gpu_reload_max_error", -1)),
                   "cap_bind_frac": raw_bind[-1],
                   "max_error": error}
            records.append(row)
            forecast_hashes[prediction_path.relative_to(SOURCE).as_posix()] = digest(prediction_path)
            local_parts.append(local)
            cloud_parts.append(cloud)
            index_parts.append(test)
            fold_parts.append(np.full(len(test), fold, dtype=np.int64))
            print(json.dumps(row), flush=True)
            write_json(OUT_DIR / "progress.json",
                       {"completed": len(records), "last": row, "state": "auditing"})
            del model
            if device == "cuda":
                torch.cuda.empty_cache()
        current = np.concatenate(index_parts)
        if indices is not None:
            np.testing.assert_array_equal(current, indices)
        indices = current
        fold_of_list.append(np.concatenate(fold_parts))
        local_by_seed.append(np.concatenate(local_parts))
        cloud_by_seed.append(np.concatenate(cloud_parts))
    for f in fold_of_list[1:]:
        np.testing.assert_array_equal(f, fold_of_list[0])
    fold_of = fold_of_list[0]
    end = pd.Timestamp(parent["complete_evaluation_until"])
    parts = []
    for start, stop in parent["folds"]:
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        parts.append(np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop)
                                     & (decisions.label_end < end)).to_numpy()))
    np.testing.assert_array_equal(indices, np.concatenate(parts))
    thresholds_en = {str(f): float(np.mean([thresholds_by_seed[str(s)][str(f)]
                                            for s in SEEDS]))
                     for f in range(len(parent["folds"]))}
    local_all, cloud_all = np.stack(local_by_seed), np.stack(cloud_by_seed)
    local_en, cloud_en = local_all.mean(0), cloud_all.mean(0)
    clock = decisions.iloc[indices].reset_index(drop=True)
    ls, linfo, _, _, _ = policy_signals(local_en.astype(np.float64), clock, cfg, fold_of,
                                        thresholds_en)
    cs, cinfo, _, _, _ = policy_signals(cloud_en.astype(np.float64), clock, cfg, fold_of,
                                        thresholds_en)
    if len(ls) != len(cs):
        raise ValueError(f"Local/cloud policy signal count differs: {len(ls)} vs {len(cs)}")
    if len(ls):
        policy_cols = ["bar_index", "signal_time", "direction", "candidate_id", "fold_test",
                       "entry_limit", "stop_loss", "take_profit_1", "take_profit_2", "holding_bars"]
        pd.testing.assert_frame_equal(ls[policy_cols].reset_index(drop=True),
                                      cs[policy_cols].reset_index(drop=True), check_exact=True)
    result = {"state": "passed", "model_family": "rankonly_ssm_v55b",
              "device": device, "torch": torch.__version__, "batch_size": 32,
              "rtol": 0.001, "atol": 0.001, "seeds": SEEDS,
              "folds": records, "max_replay_error": max(r["max_error"] for r in records),
              "parameters": params, "fixed_epochs": FIXED_EPOCHS,
              "train_loss_first_mean": float(np.mean([r["train_loss_first"] for r in records])),
              "train_loss_last_mean": float(np.mean([r["train_loss_last"] for r in records])),
              "val_loss_last_mean": float(np.mean([r["val_loss_last"] for r in records])),
              "cap_bind_frac_mean": float(np.mean(raw_bind)),
              "cap_bind_frac_max": float(np.max(raw_bind)),
              "thresholds_by_seed": thresholds_by_seed,
              "thresholds_ensemble_mean": thresholds_en,
              "source_summary_sha256": digest(SOURCE / "summary.json"),
              "plan_sha256": digest(PLAN_PATH),
              "bundled_plan_sha256": digest(SOURCE / BUNDLED_PLAN),
              "plan_json_equal_summary_plan": True,
              "plan_functional_equal_acc2_plan": func_equal,
              "plan_metadata_diffs_recorded": meta_diffs,
              "bundle_identity": bundle_check,
              "bundle_files": len(bundle_check),
              "prediction_files": forecast_hashes, "weight_files": weight_hashes,
              "index_files": index_hashes,
              "n_predictions": len(forecast_hashes),
              "prediction_shape": "(n_test,16) CAPPED rank logits (|logit|<=3.0)",
              "policy": {"ensemble": "mean_3seeds CAPPED logits",
                         "gate": "capped-margin > threshold_en(fold)=mean-3-seeds p70 "
                         "(pre-spec plan, no fallback, WAIT else)",
                         "candidate": "top1 argmax (first-max deterministic); "
                         "no fill prediction (rank-only disclosure)",
                         "geometry_frequency": "dataset cfg prices + monthly-cap/cooldown loop "
                         "(giong swing_signals)",
                         "local_signals": len(ls), "cloud_signals": len(cs),
                         "identical_policy_signals": True,
                         "picked_pre_frequency": cinfo["picks_pre_frequency"],
                         "pick_rate_pre_frequency": cinfo["pick_rate_pre_frequency"],
                         "picks_by_fold": cinfo["picks_by_fold"]},
              "all_forecasts_replayed": True, "independent_test": False, "live_approved": False,
              "prespec_note": SPEC_NOTE}
    write_json(OUT_DIR / "audit.json", result)
    print(json.dumps({"state": "passed", "max_replay_error": result["max_replay_error"],
                      "signals": len(cs), "parameters": params}))
    # ---- Portfolio (pre-spec, dung du bao CLOUD da verify) ----
    out_file = OUT_DIR / "portfolio.json"
    if out_file.exists():
        raise FileExistsError("Khong ghi de portfolio cu")
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    gate = {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30,
            "scenarios": ["normal", "fee_stress", "execution_stress"]}
    diagnostics = {"rankonly_en": diagnostic_lens(cloud_en, clock, cfg, labels_all,
                                                  indices, fold_of, thresholds_en,
                                                  float(np.mean(raw_bind)))}
    branches = {}
    bdir1 = OUT_DIR / "rankonly_en_1x"
    bdir1.mkdir(parents=True, exist_ok=True)
    base = cs.drop(columns=["leverage"], errors="ignore").copy()
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
    months = pd.period_range(clock.signal_time.iloc[0].tz_localize(None),
                             clock.signal_time.iloc[-1].tz_localize(None), freq="M")
    for key, res, sig in (("rankonly_en_1x", res1x, base),
                          ("rankonly_en_dd_guard", resdd, gsig)):
        counts = sig.signal_time.dt.strftime("%Y-%m").value_counts() if len(sig) else {}
        branches[key] = {
            "scenarios": res,
            "n_signals": int(len(sig)),
            "n_decisions": int(len(clock)),
            "coverage": float(len(sig) / len(clock)),
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
    report = {"experiment": "opencode-r44a-rankonly-scalecap-v55bfix-audit-acc2",
              "prespec_note": SPEC_NOTE,
              "kernel": "trainguyenchi/opencode-trackb-rankonly-v55bfix (account-2 failover)",
              "policy_spec": {"ensemble": "mean_3seeds CAPPED rank logits (parity-verified)",
                              "gate": "capped-margin > threshold_en(fold)=mean-3-seeds p70 "
                              "(pre-spec plan, KHONG fallback, WAIT else)",
                              "candidate": "top1 argmax (first-max deterministic); "
                              "KHONG du bao fill (rank-only disclosure)",
                              "geometry_frequency": "cfg prices + monthly-cap/cooldown loop "
                              "(giong swing_signals)",
                              "selection_detail": cinfo},
              "branches": branches,
              "duration_years": years,
              "gate": gate,
              "standing_best": {"majority_1x": "2.935%/mo (DD breach)",
                                "confirmed_dd_guard": "2.79/2.67/2.06 DD-safe all scenarios"},
              "rank_anchors": {"v38_multitask": "+0.066 (tot nhat fresh, ~v29)",
                               "v55c_rankonly": "+0.022, monthly am, DD breach",
                               "key_question": "ranking-alone WITH allowlist fix (v55bfix) "
                               "vs v55c: xem diagnostic_lens.rank_overall"},
              "diagnostic_lens": diagnostics,
              "training_notes": {"parameters": params,
                                 "fixed_epochs": FIXED_EPOCHS,
                                 "train_loss_first_mean": result["train_loss_first_mean"],
                                 "train_loss_last_mean": result["train_loss_last_mean"],
                                 "val_loss_last_mean": result["val_loss_last_mean"],
                                 "max_replay_error": result["max_replay_error"],
                                 "cap_bind_frac_mean": result["cap_bind_frac_mean"],
                                 "calibration": "KHONG isotonic (khong co absolute score); "
                                 "nguong la validation-percentile tren CAPPED rank-margin (ordinal)",
                                 "ranking_loss": "ListNet duy nhat tren capped logits "
                                 "(bo value/aux/coverage-hinge): rank do o diagnostic_lens",
                                 "coverage": "qua relative gate (p70 bao ~30% test qua gate "
                                 "neu phan phoi on dinh)"},
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": "own-book 1x equity, trigger 10%, lev 0.5/1.0, "
                           "past-only (giong v28c/v33d/v35b/v38b/v55d)",
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
