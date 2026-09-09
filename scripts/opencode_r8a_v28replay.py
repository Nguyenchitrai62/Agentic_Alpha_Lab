"""Opencode R8-A (R-AUDIT): replay audit LOCAL cho v28 BigModel (KHONG train/cloud/live).

Nap lai 33 checkpoints tu artifacts/kaggle/v28_bigmodel_download/bigmodel-training:
 - verify summary (complete, worker_exit_codes [0,0], missing_or_failed rong)
 - plan dong nhat configs/opencode_v28_bigmodel.json (sha256)
 - verify epoch-selection record tung fold-seed (nested past-only, earliest rule)
 - verify train/test indices, weights sha, prediction sha, feature stats
 - predict_big local (CUDA) vs cloud predictions.npy (rtol/atol 1e-3)
 - combine (mean penalty 0.0 / mean_minus_std penalty 1.0) + swing_signals
   (choose + frequency loop) parity: local vs cloud phai identical
Ghi artifacts/research/opencode_v28c_replay/audit.json. Labels exploratory.
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
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import earliest_best_epoch, nested_split  # noqa: E402
from opencode_r6m_bigmodel_features import N_FLAT, build_flat  # noqa: E402
from opencode_r6m_bigmodel_model import BigTemporalMultitask, predict_big  # noqa: E402
from train_tcn_kaggle import stable_evaluation_backend, write_json  # noqa: E402

ENSEMBLE = (("mean", 0.0), ("mean_minus_std", 1.0))
SOURCE = ROOT / "artifacts/kaggle/v28_bigmodel_download/bigmodel-training"
PLAN_PATH = ROOT / "configs/opencode_v28_bigmodel.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v28c_replay"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fold_indices(decisions, parent, plan, fold):
    start, stop = map(pd.Timestamp, parent["folds"][fold])
    train = np.flatnonzero(((decisions.signal_time >= start - pd.Timedelta(days=plan["folds"]["trailing_window_days"])) &
                            (decisions.label_end < start - pd.Timedelta(days=plan["folds"]["embargo_days"]))).to_numpy())
    test = np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop) &
                           (decisions.label_end < pd.Timestamp(parent["complete_evaluation_until"]))).to_numpy())
    if len(train) < plan["folds"]["minimum_train_decisions"] or not len(test) or np.intersect1d(train, test).size:
        raise ValueError("Invalid chronological fold")
    return train, test


def verify_epoch_selection(plan, decisions, parent, seed, fold, meta):
    spec = plan["epoch_selection"]
    target = SOURCE / f"seed{seed}/selection/fold_{fold}"
    record = json.loads((target / "selection.json").read_text())
    if meta.get("epoch_selection") != spec or record["selection_spec"] != spec:
        raise ValueError("Selection specification changed")
    if meta.get("selection_record_sha256") != digest(target / "selection.json"):
        raise ValueError("Selection record changed")
    if record["seed"] != seed or record["fold"] != fold:
        raise ValueError("Selection model identity mismatch")
    best = earliest_best_epoch(record["validation_losses"], spec["minimum_improvement"])
    if best != record["selected_epoch"] or not 1 <= len(record["validation_losses"]) <= plan["training"]["epochs"]:
        raise ValueError("Epoch selection does not follow registered rule")
    train, val, clock = nested_split(decisions, parent["folds"][fold][0],
        **{k: spec[k] for k in ("window_days", "validation_days", "embargo_days", "minimum_train", "minimum_validation")})
    if record["clock"] != clock:
        raise ValueError("Selection chronology mismatch")
    with np.load(target / "indices.npz", allow_pickle=False) as ix:
        np.testing.assert_array_equal(ix["train"], train)
        np.testing.assert_array_equal(ix["validation"], val)
    if digest(target / "selected.safetensors") != record["selection_weights_sha256"]:
        raise ValueError("Inner selected checkpoint changed")
    return dict(plan["training"], epochs=best)


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(PLAN_PATH.read_text())
    assert plan["model_family"] == "bigmodel_tcn_multitask"
    if OUT_DIR.exists():
        raise FileExistsError("Khong ghi de audit cu; dung dir moi")
    summary = json.loads((SOURCE / "summary.json").read_text())
    if summary.get("state") != "complete" or summary.get("worker_exit_codes") != [0, 0] or summary.get("missing_or_failed"):
        raise ValueError("All registered cloud jobs must complete before audit")
    if summary.get("plan") != plan:
        raise ValueError("Export plan differs from registered plan")
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text())
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    cfg = json.loads((ds / "config.json").read_text())
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert sequence.shape == (len(decisions), 5, 128, 6) and flat.shape == (len(decisions), N_FLAT)
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)
    ds_manifest = digest(ds / "manifest.json")
    cache_manifest = digest(cache / "manifest.json")
    OUT_DIR.mkdir(parents=True)
    records, forecast_hashes, weight_hashes, selection_hashes = [], {}, {}, {}
    local_by_seed, cloud_by_seed, indices = [], [], None
    device = "cuda"
    if not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; local audit yeu cau GPU nhu A1")
    for seed in plan["seeds"]:
        local_parts, cloud_parts, index_parts = [], [], []
        for fold in range(len(parent["folds"])):
            target = SOURCE / f"seed{seed}/checkpoints/fold_{fold}"
            meta = json.loads((target / "metadata.json").read_text())
            if meta.get("state") != "complete" or not meta.get("gpu_reload_parity"):
                raise ValueError("Incomplete or parity-failed checkpoint")
            expected_training = verify_epoch_selection(plan, decisions, parent, seed, fold, meta)
            for name in ("selection.json", "indices.npz", "selected.safetensors"):
                p = SOURCE / f"seed{seed}/selection/fold_{fold}" / name
                selection_hashes[p.relative_to(SOURCE).as_posix()] = digest(p)
            if meta["network"] != plan["architecture"]["network"] or meta["training"] != expected_training \
                    or meta["seed"] != seed or meta["fold"] != fold:
                raise ValueError("Checkpoint experiment mismatch")
            # v28 driver khong luu dataset/cache manifest sha trong metadata
            # (khac A1); dinh danh input duoc bao dam qua selection record +
            # weights/prediction sha + train/test indices + feature stats duoi day.
            if meta["model_family"] != "bigmodel_tcn_multitask":
                raise ValueError("Checkpoint architecture identity mismatch")
            if meta.get("parameters") != plan["params_target"]["measured_parameters"]:
                raise ValueError("Checkpoint parameter count mismatch")
            train, test = fold_indices(decisions, parent, plan, fold)
            with np.load(target / "indices.npz", allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved["train"], train)
                np.testing.assert_array_equal(saved["test"], test)
            weights = target / "model.safetensors"
            if digest(weights) != meta["weights_sha256"]:
                raise ValueError("Checkpoint weights changed")
            weight_hashes[weights.relative_to(SOURCE).as_posix()] = digest(weights)
            model = BigTemporalMultitask(candidates, **plan["architecture"]["network"], n_flat=N_FLAT)
            model.load_state_dict(load_file(str(weights)))
            np.testing.assert_array_equal(model.candidates.numpy(), candidates)
            np.testing.assert_allclose(model.feature_mean.numpy(), flat[train].mean(0), rtol=1e-5, atol=1e-6)
            np.testing.assert_allclose(model.feature_scale.numpy(), np.maximum(flat[train].std(0), 1e-6), rtol=1e-5, atol=1e-6)
            model.to(device)
            prediction_path = SOURCE / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            if digest(prediction_path) != meta["prediction_sha256"]:
                raise ValueError("Export prediction changed")
            cloud = np.load(prediction_path, allow_pickle=False)
            if cloud.shape != (len(test), 16, 6) or not np.isfinite(cloud).all():
                raise ValueError("Invalid exported prediction shape/values")
            local = predict_big(model, sequence[test], flat[test], batch_size=32)
            if local.shape != cloud.shape or not np.isfinite(local).all():
                raise ValueError("Nonfinite/misaligned replay predictions")
            np.testing.assert_allclose(local, cloud, rtol=1e-3, atol=1e-3)
            error = float(np.max(np.abs(local - cloud)))
            row = {"seed": seed, "fold": fold, "decisions": len(test),
                   "selected_epoch": expected_training["epochs"], "max_error": error}
            records.append(row)
            forecast_hashes[prediction_path.relative_to(SOURCE).as_posix()] = digest(prediction_path)
            local_parts.append(local)
            cloud_parts.append(cloud)
            index_parts.append(test)
            print(json.dumps(row), flush=True)
            write_json(OUT_DIR / "progress.json", {"completed": len(records), "last": row, "state": "auditing"})
            del model
            torch.cuda.empty_cache()
        current = np.concatenate(index_parts)
        if indices is not None:
            np.testing.assert_array_equal(current, indices)
        indices = current
        local_by_seed.append(np.concatenate(local_parts))
        cloud_by_seed.append(np.concatenate(cloud_parts))
    # continuous partition: gap-free, khop folds
    end = pd.Timestamp(parent["complete_evaluation_until"])
    parts = []
    for start, stop in parent["folds"]:
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        parts.append(np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop)
                                     & (decisions.label_end < end)).to_numpy()))
    np.testing.assert_array_equal(indices, np.concatenate(parts))
    local_all, cloud_all = np.stack(local_by_seed), np.stack(cloud_by_seed)
    signal_rows = {}
    for name, penalty in ENSEMBLE:
        local, _ = combine(local_all, penalty)
        cloud, _ = combine(cloud_all, penalty)
        clock = decisions.iloc[indices].reset_index(drop=True)
        ls, cs = swing_signals(local, clock, cfg), swing_signals(cloud, clock, cfg)
        if len(ls) != len(cs):
            raise ValueError("Local/cloud policy alert count differs")
        if len(ls):
            columns = ["bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
                       "take_profit_1", "take_profit_2", "holding_bars", "leverage"]
            pd.testing.assert_frame_equal(ls[columns].reset_index(drop=True),
                                          cs[columns].reset_index(drop=True), check_exact=True)
        signal_rows[name] = len(ls)
    result = {"state": "passed", "model_family": "bigmodel_tcn_multitask", "device": device,
              "torch": torch.__version__, "batch_size": 32, "rtol": 0.001, "atol": 0.001,
              "folds": records, "max_replay_error": max(r["max_error"] for r in records),
              "source_summary_sha256": digest(SOURCE / "summary.json"),
              "plan_sha256": digest(PLAN_PATH), "dataset_manifest_sha256": ds_manifest,
              "cache_manifest_sha256": cache_manifest,
              "prediction_files": forecast_hashes, "weight_files": weight_hashes,
              "identical_policy_signals": signal_rows, "selection_files": selection_hashes,
              "all_forecasts_replayed": True, "independent_test": False, "live_approved": False}
    write_json(OUT_DIR / "audit.json", result)
    print(json.dumps({"state": "passed", "max_replay_error": result["max_replay_error"],
                      "signals": signal_rows}))


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


def run_portfolio():
    spec = json.loads((ROOT / "configs/opencode_v28c.json").read_text())
    plan = json.loads(PLAN_PATH.read_text())
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text())
    audit = json.loads((OUT_DIR / "audit.json").read_text())
    if audit.get("state") != "passed" or not audit.get("all_forecasts_replayed"):
        raise ValueError("Replay audit chua PASS: chan portfolio")
    if audit.get("source_summary_sha256") != sha256(SOURCE / "summary.json"):
        raise ValueError("Audit thuoc ve training export khac")
    out_file = OUT_DIR / "portfolio.json"
    if out_file.exists():
        raise FileExistsError("Khong ghi de portfolio cu")
    ds = ROOT / spec["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
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
    gate, branches = spec["gate"], {}
    for name, penalty in ENSEMBLE:
        combined, _ = combine(stacked, penalty)
        signals = swing_signals(combined, part, cfg)
        if len(signals) != audit["identical_policy_signals"][name]:
            raise ValueError(f"Portfolio signals khac audit parity: {name}")
        b1 = OUT_DIR / f"{name}_1x"
        b1.mkdir(parents=True, exist_ok=True)
        base = signals.drop(columns=["leverage"], errors="ignore").copy()
        base.to_parquet(b1 / "signals.parquet", index=False)
        exec1x = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                 max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
        res1x, trades1x = run_branch(candles, base, costs, exec1x, years, b1)
        guard = dd_guard_leverage(base, trades1x)
        bdd = OUT_DIR / f"{name}_dd_guard"
        bdd.mkdir(parents=True, exist_ok=True)
        gsig = base.copy()
        gsig["leverage"] = guard
        gsig.to_parquet(bdd / "signals.parquet", index=False)
        execdd = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                 max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
        resdd, _ = run_branch(candles, gsig, costs, execdd, years, bdd)
        months = pd.period_range(part.signal_time.iloc[0].tz_localize(None),
                                 part.signal_time.iloc[-1].tz_localize(None), freq="M")
        for key, res, sig in ((f"{name}_1x", res1x, base),
                              (f"{name}_dd_guard", resdd, gsig)):
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
                              "metrics": {s: {k: res[s][k] for k in
                                              ("total_return", "max_drawdown", "trades",
                                               "monthly_geometric_net", "gross_pnl", "fees",
                                               "funding", "profit_factor", "win_rate")}
                                          for s in gate["scenarios"]}}), flush=True)
    report = {"experiment": spec["experiment"], "branches": branches,
              "duration_years": years, "gate": gate,
              "standing_best": spec["standing_best"],
              "comparison": "So truc tiep voi standing_best (majority_1x 2.935%/mo DD breach; confirmed_dd_guard 2.79%/mo DD-safe) va gate.",
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": "own-book 1x equity, trigger 10%, lev 0.5/1.0, past-only (tien le v03)",
                           "frequency": "swing_signals: monthly cap + cooldown, giong audit parity"},
              "audit_sha256": sha256(OUT_DIR / "audit.json"),
              "training_summary_sha256": sha256(SOURCE / "summary.json"),
              "independent_test": False, "exploratory": True, "live_approved": False,
              "warning": "Opened development interval only (2023-2026). Drawdown close-sampled; stop/timeout market-like. KHONG live approval."}
    out_file.write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(out_file))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force-fresh", action="store_true")
    p.add_argument("--portfolio", action="store_true")
    a = p.parse_args()
    if a.force_fresh:
        import shutil
        shutil.rmtree(OUT_DIR, ignore_errors=True)
    if a.portfolio:
        run_portfolio()
    else:
        main(a)
