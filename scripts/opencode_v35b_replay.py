"""Opencode R-AUDIT (standing auditor): replay audit + portfolio LOCAL cho v35 Selective-SSM.

Nguon: artifacts/kaggle/v35_nextarch_download/nextarch-training (kernel
nguynchtrai/opencode-trackm-nextarch-v35, COMPLETE, exit [0,0]).
Plan dong bang: configs/opencode_v35_nextarch.json (seeds 1729/1730/1731,
11 quarterly folds, SelectiveSSMTemporal 600k + coverage-floor hinge).

(1) Audit: nap lai 33 checkpoints, verify summary + plan JSON-equality +
    bundle-hashes (byte-sha; file text chuan hoa CRLF) + metadata
    (state/parity/weights-sha/prediction-sha) + epoch-selection record
    (nested past-only, earliest FULL-loss rule) + train/test indices +
    feature stats (flat[train]) + predict_ssm local (CUDA) vs cloud
    (rtol/atol 1e-3) + v35-policy signals parity (local vs cloud).
    Ghi artifacts/research/opencode_v35b_replay/audit.json.
(2) Portfolio (pre-spec theo plan): ensemble mean 3 seeds (ssm_en) ->
    policy floor DANG KY trong plan (gate en_best > 0 + fallback top-8
    moi fold-test) -> candidate = argmax expected trong fill>=0.25 ->
    geometry + frequency loop giong swing_signals (monthly cap + cooldown
    tu dataset cfg) -> 2 branches (ssm_en_1x, ssm_en_dd_guard) x 3 scenarios
    (normal, fee 0.00055, FillStress(5,5,5,0.00055,False)) + monthly geometric
    theo configs/swing_v15_continuous_folds.json + diagnostic lens v34.
    Ghi portfolio.json. Dung du bao CLOUD (da verify parity).

KHONG train/cloud/live. Labels exploratory, causal past-only.
"""
import torch  # noqa: F401  (import truoc pandas: DLL load-order tren Windows host)
import argparse
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
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import earliest_best_epoch, nested_split  # noqa: E402
from opencode_r9m_nextarch_features import N_FLAT, build_flat  # noqa: E402
from opencode_r9m_nextarch_model import POLICY_MARGIN, POLICY_N_MIN, predict_ssm  # noqa: E402
import opencode_r9m_nextarch_train as v35train  # noqa: E402
from train_tcn_kaggle import write_json  # noqa: E402

SPEC_NOTE = "pre-spec = configs/opencode_v35_nextarch.json (branches_eval, policy_mechanism)"
PLAN_PATH = ROOT / "configs/opencode_v35_nextarch.json"
PARENT_PATH = ROOT / "configs/swing_v15_continuous_folds.json"
SOURCE = ROOT / "artifacts/kaggle/v35_nextarch_download/nextarch-training"
OUT_DIR = ROOT / "artifacts/research/opencode_v35b_replay"
SEEDS = [1729, 1730, 1731]
TOPK = 408  # top-decile x 4076 decisions (giong v34)
TEXT_SUFFIXES = (".py", ".json")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -40, 40)))


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


def verify_epoch_selection(plan, decisions, parent, seed, fold, meta):
    spec = plan["epoch_selection"]
    target = SOURCE / f"seed{seed}/selection/fold_{fold}"
    record = json.loads((target / "selection.json").read_text(encoding="utf-8"))
    if meta.get("epoch_selection") != spec or record["selection_spec"] != spec:
        raise ValueError("Selection specification changed")
    if meta.get("selection_record_sha256") != digest(target / "selection.json"):
        raise ValueError("Selection record changed")
    if record["seed"] != seed or record["fold"] != fold:
        raise ValueError("Selection model identity mismatch")
    best = earliest_best_epoch(record["validation_losses"], spec["minimum_improvement"])
    if best != record["selected_epoch"] or not 1 <= len(record["validation_losses"]) <= plan["training"]["epochs"]:
        raise ValueError("Epoch selection does not follow registered rule")
    keys = ("window_days", "validation_days", "embargo_days", "minimum_train", "minimum_validation")
    train, val, clock = nested_split(decisions, parent["folds"][fold][0],
                                     **{k: spec[k] for k in keys})
    if record["clock"] != clock:
        raise ValueError("Selection chronology mismatch")
    with np.load(target / "indices.npz", allow_pickle=False) as ix:
        np.testing.assert_array_equal(ix["train"], train)
        np.testing.assert_array_equal(ix["validation"], val)
    if digest(target / "selected.safetensors") != record["selection_weights_sha256"]:
        raise ValueError("Inner selected checkpoint changed")
    return best, record


def v35_policy_signals(ensemble, part, cfg, fold_of):
    """Tin hieu theo policy floor DANG KY trong plan (khong che).

    ensemble: (n,16,6) map-v8 mean 3 seeds. en_best = max_k ch0*fill.
    Moi fold-test: gate en_best > 0; neu < 8 thi bu top-8 theo en_best.
    Candidate: argmax expected trong fill>=0.25 (fallback: global argmax).
    Geometry (prices) + frequency loop (monthly cap + cooldown) giong
    swing_signals tu dataset cfg.
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
        k = int(elig[np.argmax(expected[i, elig])])
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp,
                        "fold_test": int(fold_of[i]),
                        "action": "LONG" if cand_grid[k, 0] == 1 else "SHORT",
                        "direction": int(cand_grid[k, 0]), "candidate_id": k,
                        **prices(float(row.close), float(row.atr5), float(row.atr4),
                                 cand_grid[k], cfg),
                        "expected_net_percent": float(expected[i, k]),
                        "en_best": float(en_best[i]),
                        "conditional_net_quantiles_percent": pred[i, k, 1:4].tolist(),
                        "ohlc_fill_score": float(fill[i, k]),
                        "conditional_win_score": float(sigmoid(pred[i, k, 5])),
                        "calibrated": False, "entry_expiry_bars": cfg["entry_expiry_bars"],
                        "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    cols = ["bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
            "take_profit_1", "take_profit_2", "holding_bars"]
    frame = pd.DataFrame(signals)
    if len(frame) and not set(cols).issubset(frame.columns):
        raise ValueError("Unexpected signal schema")
    info = {"gate_hits_by_fold": gate_hits, "fallback_adds_by_fold": fallback_adds,
            "n_selected": len(selected), "n_signals": len(frame),
            "n_wait_no_fill_eligible": n_wait_ineligible,
            "policy_margin": POLICY_MARGIN, "policy_n_min": POLICY_N_MIN}
    return frame, info


def load_plan_inputs(plan):
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert sequence.shape == (len(decisions), 5, 128, 6) and flat.shape == (len(decisions), N_FLAT)
    assert np.isfinite(sequence).all() and np.isfinite(flat).all()
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)
    return decisions, candles, cfg, sequence, flat, candidates


def main(a):
    torch.set_num_threads(2)
    v35train.stable_backend()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "nextarch_selective_ssm_v35"
    assert plan["seeds"] == SEEDS
    if OUT_DIR.exists():
        raise FileExistsError("Khong ghi de audit cu; dung dir moi")
    summary = json.loads((SOURCE / "summary.json").read_text(encoding="utf-8"))
    if summary.get("state") != "complete" or summary.get("worker_exit_codes") != [0, 0] \
            or summary.get("missing_or_failed"):
        raise ValueError("All registered cloud jobs must complete before audit")
    if summary.get("plan") != plan:
        raise ValueError("Export plan differs from registered plan (JSON)")
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
    parent = json.loads(PARENT_PATH.read_text(encoding="utf-8"))
    decisions, _candles, cfg, sequence, flat, candidates = load_plan_inputs(plan)
    for col in ("bar_index", "signal_time", "close", "atr5", "atr4"):
        if col not in decisions.columns:
            raise ValueError(f"decisions thieu cot {col}")
    OUT_DIR.mkdir(parents=True)
    device = "cuda"
    if not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; local audit yeu cau GPU")
    records, forecast_hashes, weight_hashes, selection_hashes = [], {}, {}, {}
    local_by_seed, cloud_by_seed, indices, fold_of_list = [], [], None, []
    params, val_mean_pos_last = None, []
    for seed in SEEDS:
        local_parts, cloud_parts, index_parts, fold_parts = [], [], [], []
        for fold in range(len(parent["folds"])):
            target = SOURCE / f"seed{seed}/checkpoints/fold_{fold}"
            meta = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
            if meta.get("state") != "complete" or not meta.get("gpu_reload_parity"):
                raise ValueError("Incomplete or parity-failed checkpoint")
            if meta.get("model_family") != "nextarch_selective_ssm_v35":
                raise ValueError("Checkpoint architecture identity mismatch")
            if meta["seed"] != seed or meta["fold"] != fold:
                raise ValueError("Checkpoint identity mismatch")
            if params is None:
                params = meta["parameters"]
            elif params != meta["parameters"]:
                raise ValueError("Parameter count changed across folds")
            cov = meta.get("coverage", {})
            if float(cov.get("lambda", -1)) != float(plan["training"]["coverage_lambda"]) or \
                    float(cov.get("floor_pos", -1)) != float(plan["training"]["coverage_floor_pos"]):
                raise ValueError("Coverage-floor mismatch")
            best, record = verify_epoch_selection(plan, decisions, parent, seed, fold, meta)
            for name in ("selection.json", "indices.npz", "selected.safetensors"):
                p = SOURCE / f"seed{seed}/selection/fold_{fold}" / name
                selection_hashes[p.relative_to(SOURCE).as_posix()] = digest(p)
            val_mean_pos_last.append(float(record["coverage"]["val_mean_pos_by_epoch"][best - 1])
                                     if record["coverage"].get("val_mean_pos_by_epoch") else None)
            expected_training = dict(plan["training"], epochs=best)
            if meta["training"] != expected_training:
                raise ValueError("Checkpoint refit-epoch mismatch")
            train, test = v35train.fold_indices(decisions, parent, plan, fold)
            with np.load(target / "indices.npz", allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved["train"], train)
                np.testing.assert_array_equal(saved["test"], test)
            weights = target / "model.safetensors"
            if digest(weights) != meta["weights_sha256"]:
                raise ValueError("Checkpoint weights changed")
            weight_hashes[weights.relative_to(SOURCE).as_posix()] = digest(weights)
            model = v35train.make_model(plan, candidates)
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
            if cloud.shape != (len(test), 16, 6) or not np.isfinite(cloud).all():
                raise ValueError("Invalid exported prediction shape/values")
            local = predict_ssm(model, sequence[test], flat[test], batch_size=32)
            if local.shape != cloud.shape or not np.isfinite(local).all():
                raise ValueError("Nonfinite/misaligned replay predictions")
            np.testing.assert_allclose(local, cloud, rtol=1e-3, atol=1e-3)
            error = float(np.max(np.abs(local - cloud)))
            row = {"seed": seed, "fold": fold, "decisions": len(test),
                    "selected_epoch": best, "train_mean_pos_last": float(cov["train_mean_pos_by_epoch"][-1]),
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
    local_all, cloud_all = np.stack(local_by_seed), np.stack(cloud_by_seed)
    local_en, _ = combine(local_all, 0.0)
    cloud_en, _ = combine(cloud_all, 0.0)
    clock = decisions.iloc[indices].reset_index(drop=True)
    # fold_of duoc ghep theo thu tu fold0..fold10 == thu tu clock
    ls, linfo = v35_policy_signals(local_en.astype(np.float64), clock, cfg, fold_of)
    cs, cinfo = v35_policy_signals(cloud_en.astype(np.float64), clock, cfg, fold_of)
    if len(ls) != len(cs):
        raise ValueError(f"Local/cloud policy signal count differs: {len(ls)} vs {len(cs)}")
    if len(ls):
        # So exact chi cac cot nguyen / khong phu thuoc predictions (geometry tu close/atr/grid).
        # Cac cot float tu predictions (expected_net_percent, en_best...) duoc bao boi numeric parity 1e-3.
        policy_cols = ["bar_index", "signal_time", "direction", "candidate_id", "fold_test",
                       "entry_limit", "stop_loss", "take_profit_1", "take_profit_2", "holding_bars"]
        pd.testing.assert_frame_equal(ls[policy_cols].reset_index(drop=True),
                                      cs[policy_cols].reset_index(drop=True), check_exact=True)
    result = {"state": "passed", "model_family": "nextarch_selective_ssm_v35",
              "device": device, "torch": torch.__version__, "batch_size": 32,
              "rtol": 0.001, "atol": 0.001, "seeds": SEEDS,
              "folds": records, "max_replay_error": max(r["max_error"] for r in records),
              "parameters": params,
              "selected_epoch_distribution": {str(k): int(v) for k, v in
                                              Counter(r["selected_epoch"] for r in records).items()},
              "val_mean_pos_last_mean": float(np.mean([v for v in val_mean_pos_last if v is not None])),
              "source_summary_sha256": digest(SOURCE / "summary.json"),
              "plan_sha256": digest(PLAN_PATH),
              "plan_json_equal_summary_plan": True,
              "bundle_identity": bundle_check,
              "prediction_files": forecast_hashes, "weight_files": weight_hashes,
              "selection_files": selection_hashes,
              "policy": {"ensemble": "mean_3seeds (combine penalty 0.0)",
                         "gate": "en_best > 0.0 + fallback top-8/fold-test (pre-spec plan)",
                         "candidate": "argmax expected s.t. fill>=0.25",
                         "geometry_frequency": "dataset cfg prices + monthly-cap/cooldown loop (giong swing_signals)",
                         "local_signals": len(ls), "cloud_signals": len(cs),
                         "identical_policy_signals": True,
                         "gate_hits_by_fold": cinfo["gate_hits_by_fold"],
                         "fallback_adds_by_fold": cinfo["fallback_adds_by_fold"],
                         "n_wait_no_fill_eligible": cinfo["n_wait_no_fill_eligible"]},
              "all_forecasts_replayed": True, "independent_test": False, "live_approved": False,
              "prespec_note": SPEC_NOTE}
    write_json(OUT_DIR / "audit.json", result)
    print(json.dumps({"state": "passed", "max_replay_error": result["max_replay_error"],
                      "signals": len(cs), "parameters": params}))


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


def diagnostic_lens(ensemble, part, cfg, labels_all, indices, fold_of):
    pred = np.asarray(ensemble, dtype=np.float64)
    fill = sigmoid(pred[..., 4])
    exp = pred[..., 0] * fill
    n = len(part)
    best_exp = exp.max(1)
    arg = exp.argmax(1)
    best_fill = fill[np.arange(n), arg]
    policy_net = float(cfg["policy"]["minimum_expected_net_percent"])
    policy_fill = float(cfg["policy"]["minimum_fill_score"])
    pass_net = best_exp >= policy_net
    pass_both = pass_net & (best_fill >= policy_fill)
    signals, info = v35_policy_signals(ensemble, part, cfg, fold_of)
    months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
    truth = labels_all[indices]
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
        "threshold_pass_cfg_gates": {
            "pass_net_n": int(pass_net.sum()), "pass_net_rate": float(pass_net.mean()),
            "pass_both_n": int(pass_both.sum()), "pass_both_rate": float(pass_both.mean())},
        "policy_floor_gate": {"gate_en_gt_0_n": int((best_exp > 0).sum()),
                              "gate_en_gt_0_rate": float((best_exp > 0).mean()),
                              "gate_hits_by_fold": info["gate_hits_by_fold"],
                              "fallback_adds_by_fold": info["fallback_adds_by_fold"]},
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
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    parent = json.loads(PARENT_PATH.read_text(encoding="utf-8"))
    audit = json.loads((OUT_DIR / "audit.json").read_text(encoding="utf-8"))
    if audit.get("state") != "passed" or not audit.get("all_forecasts_replayed"):
        raise ValueError("Replay audit chua PASS: chan portfolio")
    if audit.get("source_summary_sha256") != sha256(SOURCE / "summary.json"):
        raise ValueError("Audit thuoc ve training export khac")
    out_file = OUT_DIR / "portfolio.json"
    if out_file.exists():
        raise FileExistsError("Khong ghi de portfolio cu")
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
            if pred.shape != (len(selected), 16, 6) or not np.isfinite(pred).all():
                raise ValueError(f"Prediction shape/values mismatch: {path}")
            batch.append(pred)
        forecasts.append(np.stack(batch))
    part = decisions.iloc[indices].reset_index(drop=True)
    stacked = np.concatenate(forecasts, axis=1)
    ensemble, _details = combine(stacked, 0.0)
    signals, pinfo = v35_policy_signals(ensemble.astype(np.float64), part, cfg, fold_of)
    if len(signals) != audit["policy"]["cloud_signals"]:
        raise ValueError("Portfolio signals khac audit parity")
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    gate = {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30,
            "scenarios": ["normal", "fee_stress", "execution_stress"]}
    diagnostics = {"ssm_en": diagnostic_lens(ensemble.astype(np.float64), part, cfg,
                                             labels_all, indices, fold_of)}
    branches = {}
    bdir1 = OUT_DIR / "ssm_en_1x"
    bdir1.mkdir(parents=True, exist_ok=True)
    base = signals.drop(columns=["leverage"], errors="ignore").copy()
    base.to_parquet(bdir1 / "signals.parquet", index=False)
    exec1x = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    res1x, trades1x = run_branch(candles, base, costs, exec1x, years, bdir1)
    guard = dd_guard_leverage(base, trades1x)
    bdd = OUT_DIR / "ssm_en_dd_guard"
    bdd.mkdir(parents=True, exist_ok=True)
    gsig = base.copy()
    gsig["leverage"] = guard
    gsig.to_parquet(bdd / "signals.parquet", index=False)
    execdd = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                             max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
    resdd, _tdd = run_branch(candles, gsig, costs, execdd, years, bdd)
    months = pd.period_range(part.signal_time.iloc[0].tz_localize(None),
                             part.signal_time.iloc[-1].tz_localize(None), freq="M")
    for key, res, sig in (("ssm_en_1x", res1x, base),
                          ("ssm_en_dd_guard", resdd, gsig)):
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
    report = {"experiment": "opencode-r9m-nextarch-selective-ssm-v35-audit",
              "prespec_note": SPEC_NOTE,
              "policy_spec": {"ensemble": "mean_3seeds (combine penalty 0.0, giong audit parity)",
                              "gate": "en_best = max_k ch0*fill > 0.0 + fallback top-8/fold-test (plan policy_mechanism)",
                              "candidate": "argmax expected s.t. fill>=0.25 (cfg fill gate giu, net gate 0.0 theo plan)",
                              "geometry_frequency": "cfg prices + monthly-cap/cooldown loop (giong swing_signals)",
                              "selection_detail": pinfo},
              "branches": branches,
              "duration_years": years,
              "gate": gate,
              "standing_best": {"majority_1x": "2.935%/mo (DD breach)",
                                "confirmed_dd_guard": "2.79/2.67/2.06 DD-safe all scenarios"},
              "comparison": "So truc tiep voi standing_best va gate.",
              "diagnostic_v34_lens": diagnostics,
              "training_notes": {"parameters": audit["parameters"],
                                 "selected_epoch_distribution": audit["selected_epoch_distribution"],
                                 "val_mean_pos_last_mean": audit["val_mean_pos_last_mean"],
                                 "calibration": "KHONG calibrate (scores tho) — bias tho duoc do o diagnostic",
                                 "ranking_loss": "KHONG co pairwise/listwise ranking loss — rank duoc do o diagnostic",
                                 "coverage_hinge": "lambda 3.0 floor 5e-4 trong loss; policy floor en_best>0 + top-8"},
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": "own-book 1x equity, trigger 10%, lev 0.5/1.0, past-only (giong v28c/v33d)",
                           "monthly_geometric": "tu configs/swing_v15_continuous_folds.json",
                           "frequency": "monthly cap + cooldown, giong swing_signals"},
              "audit_sha256": sha256(OUT_DIR / "audit.json"),
              "training_summary_sha256": sha256(SOURCE / "summary.json"),
              "plan_sha256": sha256(PLAN_PATH),
              "independent_test": False, "exploratory": True, "live_approved": False,
              "warning": "Opened development interval only (2023-2026). Drawdown close-sampled; "
                         "stop/timeout market-like. KHONG live approval."}
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
