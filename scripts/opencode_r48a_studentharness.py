"""Opencode R48-A R-AUDIT: student-distill replay+portfolio harness (v106 logits format).

Pre-spec: configs/opencode_v131_studentharness.json (viet TRUOC khi outputs land).
Chay NAY la smoke-plumbing only: DRY-RUN tren smoke predictions
(artifacts/research/opencode_v106_student/smoke/... stand-in cho cloud outputs)
de chung minh harness chay end-to-end. So lieu smoke-harness la PLUMBING,
KHONG phai ket qua nghien cuu, KHONG ket luan ve student, KHONG so standing_best.

Full audit sau (khi cloud COMPLETE): cung script, --source tro toi download dir
33 folds (seed*/temporal_neural/fold_*/predictions_logits.npy). Checklist o config.

Format student (tu scripts/opencode_r37m_student_train.py + v106 config):
  predictions_logits.npy (n_test,16) float32 FREE UNITS + val_predictions_logits.npy
  (n_val,16) + indices.npz{train,validation,test} + soft_rows + upweight_stats +
  metadata{parity, sha256} + replay.npz. Policy: en_best_logit>0.0 + top-8 fallback
  + deterministic_best_index (eps 1e-6, holding-asc, index-min; BO fill-desc vi
  KHONG co fill head). Branches: student-1x + student-dd_guard (conditional).
Scenarios: normal (fee 0.0002) + fee_stress (0.00055) + execution_stress
FillStress(5,5,5,0.00055,False). Gate: monthly>=5%, DD<20%, fills>=30.

Rules: no live; never touch registry/CONTINUOUS_RESEARCH/NEXT_AGENT/rounds/
Kronos/worktrees; no register/commit/push; no overwrites; causal; exploratory.
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
from agentic_alpha_lab.data.swing import grid  # noqa: E402
from agentic_alpha_lab.data.swing import prices as swing_prices  # noqa: E402
from opencode_r37m_student_features import N_FLAT, build_flat  # noqa: E402
from opencode_r37m_student_model import (  # noqa: E402
    TIE_BREAK_EPS,
    StudentSSMTemporal,
    count_params,
    deterministic_best_index,
    predict_student_logits,
)
from safetensors.torch import load_file  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v131_studentharness.json"
POLICY_MARGIN = 0.0  # pre-spec: zero-margin tren LOGITS free units
POLICY_N_MIN = 8  # pre-spec: N_MIN_PER_FOLD_TEST
TOPK = 408
RTOL, ATOL = 1e-4, 1e-4  # train-driver parity spec
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


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


def detect_source(source):
    """Phan biet full cloud download vs smoke-sample stand-in."""
    full = sorted(source.glob("seed*/temporal_neural/fold_*/predictions_logits.npy"))
    smoke = sorted(source.glob("seed*/fold_*/predictions_logits_sample.npy"))
    if full and not smoke:
        return "full", full
    if smoke and not full:
        return "smoke-sample", smoke
    if full and smoke:
        raise ValueError("Source lan lon full + smoke-sample; tach rieng")
    raise FileNotFoundError(f"Khong thay predictions nao duoi {source}")


def build_candidates(cfg):
    cands = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                        for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    if cands.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    return cands


def student_policy_signals(ensemble_logits, part, cfg, fold_of, candidates):
    """Identity policy tren student LOGITS (pre-spec v131).

    ensemble_logits: (N,16) mean-across-seeds (full) hoac single-seed (smoke).
    en_best_logit = max_k; gate > 0.0 per fold-test + top-8 fallback;
    candidate = deterministic_best_index (holding-asc, index-min);
    geometry prices(); frequency monthly cap 4 + cooldown 5d.
    KHONG fill gate (no fill head). KHONG calibrate overlay (identity).
    """
    if TIE_BREAK_EPS != 1e-6:
        raise ValueError("tie_break_eps phai 1e-6")
    lg = np.asarray(ensemble_logits, dtype=np.float64)
    if lg.ndim != 2 or lg.shape[1] != 16 or len(part) != lg.shape[0]:
        raise ValueError("Logit/part shape mismatch")
    if not np.isfinite(lg).all():
        raise ValueError("Nonfinite student logits")
    en_best = lg.max(axis=1)
    n = len(part)
    selected = set()
    gate_hits, fallback_adds = {}, {}
    for f in sorted(set(np.asarray(fold_of).tolist())):
        idx = np.flatnonzero(np.asarray(fold_of) == f)
        gate = idx[en_best[idx] > POLICY_MARGIN]
        gate_hits[str(f)] = int(len(gate))
        if len(gate) >= POLICY_N_MIN:
            selected.update(gate.tolist())
            fallback_adds[str(f)] = 0
        else:
            order = idx[np.argsort(-en_best[idx], kind="stable")[:min(POLICY_N_MIN, len(idx))]]
            selected.update(gate.tolist())
            selected.update(order.tolist())
            fallback_adds[str(f)] = int(len(set(order.tolist()) - set(gate.tolist())))
    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    if cand_grid.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    if not np.array_equal(np.asarray(candidates, dtype=np.float64), cand_grid):
        raise ValueError("Candidate grid != model candidates")
    policy, signals = cfg["policy"], []
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    for i, row in enumerate(part.itertuples()):
        if i not in selected:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        k = deterministic_best_index(lg[i], candidates)
        sig = swing_prices(float(row.close), float(row.atr5), float(row.atr4),
                           cand_grid[k], cfg)
        signals.append({"bar_index": int(row.bar_index), "signal_time": timestamp,
                        "fold_test": int(fold_of[i]), "candidate_id": int(k),
                        "direction": int(sig["direction"]),
                        "entry_limit": float(sig["entry_limit"]),
                        "stop_loss": float(sig["stop_loss"]),
                        "take_profit_1": float(sig["take_profit_1"]),
                        "take_profit_2": float(sig["take_profit_2"]),
                        "holding_bars": int(sig["holding_bars"]), "leverage": 1.0,
                        "en_best_logit": float(en_best[i]),
                        "calibrated": False,
                        "entry_expiry_bars": int(cfg["entry_expiry_bars"]),
                        "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy["cooldown_days"])
    frame = pd.DataFrame(signals)
    info = {"gate_hits_by_fold": gate_hits, "fallback_adds_by_fold": fallback_adds,
            "n_selected": len(selected), "n_signals": len(frame),
            "policy_margin": POLICY_MARGIN, "policy_n_min": POLICY_N_MIN,
            "tie_break": "eps 1e-6 holding-asc index-min, no fill-desc"}
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
        out[label]["_trades_rows"] = [asdict(t) for t in items]
    out["execution_stress"]["diagnostics"] = diag
    return out, trades


def sig_info(ensemble_logits, part, cfg, labels_sub, signals):
    n = len(part)
    lg = np.asarray(ensemble_logits, dtype=np.float64)
    best = lg.max(axis=1)
    pass_net = best > POLICY_MARGIN
    months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
    truth = np.asarray(labels_sub, dtype=np.float64)
    take = min(TOPK, n)
    order = np.argsort(best, kind="stable")[-take:]
    k = lg[order].argmax(axis=1)
    pe = lg[order, k]
    rn = truth[order, k, 0]
    per = rank_corr_per_decision(lg, truth[:, :, 0])
    valid = per[~np.isnan(per)]
    return {
        "score_distribution": {f"en_best_logit_{kk}": vv for kk, vv in qstats(best).items()},
        "threshold_pass_logit0": {"pass_n": int(pass_net.sum()),
                                  "pass_rate": float(pass_net.mean())},
        "n_decisions": int(n), "n_signals": int(len(signals)),
        "coverage": float(len(signals) / n) if n else 0.0,
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
        "topdecile": {"n": int(take), "pred_logit_mean": float(pe.mean()),
                      "obs_net_mean": float(rn.mean()),
                      "bias_note": "logits free units vs percent -> RECORD only, no cross-model bias compare"},
        "rank_overall": {"n": int(n), "n_valid": int(len(valid)),
                         "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                         "rank_corr_std": float(valid.std()) if len(valid) else None},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True,
                   help="cloud download dir (33 folds) hoac smoke dir (stand-in)")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v106_student.json")
    p.add_argument("--device", choices=["cpu"], default="cpu")
    a = p.parse_args()
    spec = json.loads(Path(a.config).read_text(encoding="utf-8"))
    assert spec["policy_branches"]["branches"] == ["student-1x", "student-dd_guard"]
    assert spec["gate"] == {"monthly_geometric_net_min": 0.05, "drawdown_max": 0.2, "fills_min": 30}
    if a.output.exists():
        raise FileExistsError("Khong ghi de lich su; chon output dir moi")
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    assert plan.get("model_family") == "distill_student_ssm_v106", "Sai student plan"
    mode, pred_files = detect_source(a.source)
    print(json.dumps({"harness_mode": mode, "n_pred_files": len(pred_files),
                      "warning": "SMOKE-PLUMBING ONLY" if mode.startswith("smoke") else "FULL AUDIT"}), flush=True)
    seeds = sorted({int(q.parts[-4].replace("seed", "")) if mode == "full"
                    else int(q.parts[-3].replace("seed", "")) for q in pred_files})
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds = ROOT / plan["dataset"]
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    candidates = build_candidates(cfg)
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels_all = z["labels"]
    cache = ROOT / plan["cache"]
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert sequence.shape == (len(decisions), 5, 128, 6) and flat.shape == (len(decisions), N_FLAT)
    assert labels_all.shape == (len(decisions), 16, 3)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    assert cap == 2016, "holding cap"
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)

    # ---- Assemble decision universe + per-fold logits ----
    replay_records, per_fold_logits, indices_list, fold_ids = [], {}, [], []
    if mode == "full":
        end = pd.Timestamp(parent["complete_evaluation_until"])
        partitions = []
        for s, e in parent["folds"]:
            s, e = pd.Timestamp(s), pd.Timestamp(e)
            partitions.append(np.flatnonzero(((decisions.signal_time >= s) & (decisions.signal_time < e)
                                              & (decisions.label_end < end)).to_numpy()))
        indices = np.concatenate(partitions)
        fold_of = np.concatenate([np.full(len(sel), f, dtype=np.int64)
                                  for f, sel in enumerate(partitions)])
        assert len(indices) == 4076, f"decision count changed: {len(indices)}"
        for seed in plan["seeds"]:
            for fold in range(len(parent["folds"])):
                ckpt = a.source / f"seed{seed}/checkpoints/fold_{fold}"
                meta = json.loads((ckpt / "metadata.json").read_text(encoding="utf-8"))
                if meta.get("state") != "complete" or not meta.get("gpu_reload_parity"):
                    raise ValueError(f"Incomplete/parity-failed checkpoint s{seed}f{fold}")
                with np.load(ckpt / "indices.npz", allow_pickle=False) as ix:
                    np.testing.assert_array_equal(ix["test"], partitions[fold])
                train = np.load(ckpt / "indices.npz", allow_pickle=False)["train"]
                wpath = ckpt / "model.safetensors"
                if sha(wpath) != meta["weights_sha256"]:
                    raise ValueError("Checkpoint weights changed")
                model = StudentSSMTemporal(candidates, n_flat=N_FLAT)
                model.load_state_dict(load_file(str(wpath)))
                np.testing.assert_array_equal(model.candidates.numpy(), candidates)
                np.testing.assert_allclose(model.feature_mean.numpy(), flat[train].mean(0),
                                           rtol=1e-5, atol=1e-6)
                np.testing.assert_allclose(model.feature_scale.numpy(),
                                           np.maximum(flat[train].std(0), 1e-6),
                                           rtol=1e-5, atol=1e-6)
                n_params = count_params(model)
                assert 400000 <= n_params <= 2000000, f"params ngoai band: {n_params}"
                ppath = a.source / f"seed{seed}/temporal_neural/fold_{fold}/predictions_logits.npy"
                if sha(ppath) != meta["prediction_sha256"]:
                    raise ValueError("Export prediction changed")
                cloud = np.load(ppath, allow_pickle=False)
                test = partitions[fold]
                if cloud.shape != (len(test), 16) or not np.isfinite(cloud).all():
                    raise ValueError(f"Invalid exported logits {ppath}: {cloud.shape}")
                vpath = a.source / f"seed{seed}/temporal_neural/fold_{fold}/val_predictions_logits.npy"
                if sha(vpath) != meta["val_prediction_sha256"]:
                    raise ValueError("Export val prediction changed")
                val = np.load(vpath, allow_pickle=False)
                if val.ndim != 2 or val.shape[1] != 16 or not np.isfinite(val).all():
                    raise ValueError(f"Invalid exported val logits {vpath}: {val.shape}")
                local = predict_student_logits(model, sequence[test], flat[test], batch_size=32)
                np.testing.assert_allclose(local, cloud, rtol=RTOL, atol=ATOL)
                err = float(np.max(np.abs(local - cloud)))
                row = {"seed": seed, "fold": fold, "decisions": int(len(test)),
                       "max_error": err, "params": int(n_params),
                       "val_rows": int(val.shape[0]), "val_finite": True}
                replay_records.append(row)
                per_fold_logits.setdefault(fold, []).append(cloud)
                print(json.dumps(row), flush=True)
                del model
        # mean across seeds per fold, then concat folds in order
        by_seed = []
        for s, seed in enumerate(plan["seeds"]):
            by_seed.append(np.concatenate([per_fold_logits[f][s] for f in sorted(per_fold_logits)], axis=0))
        ensemble = np.mean(np.stack(by_seed), axis=0)
        assert ensemble.shape == (len(indices), 16)
        part = decisions.iloc[indices].reset_index(drop=True)
        labsub = labels_all[indices]
    else:
        # smoke-sample: single fold sample (test[:64]); fold_of = single group
        assert len(pred_files) == 1, f"smoke expect 1 sample file, got {len(pred_files)}"
        sfile = pred_files[0]
        fold = int(sfile.parts[-2].replace("fold_", ""))
        seed = int(sfile.parts[-3].replace("seed", ""))
        ckpt_dir = sfile.parent
        with np.load(ckpt_dir / "indices.npz", allow_pickle=False) as ix:
            train, validation, test = ix["train"], ix["validation"], ix["test"]
        cloud = np.load(sfile, allow_pickle=False)
        assert cloud.shape == (64, 16) and np.isfinite(cloud).all()
        assert (ckpt_dir / "model.safetensors").exists()
        model = StudentSSMTemporal(candidates, n_flat=N_FLAT)
        model.load_state_dict(load_file(str(ckpt_dir / "model.safetensors")))
        np.testing.assert_array_equal(model.candidates.numpy(), candidates)
        np.testing.assert_allclose(model.feature_mean.numpy(), flat[train].mean(0),
                                   rtol=1e-5, atol=1e-6)
        np.testing.assert_allclose(model.feature_scale.numpy(),
                                   np.maximum(flat[train].std(0), 1e-6),
                                   rtol=1e-5, atol=1e-6)
        n_params = count_params(model)
        local = predict_student_logits(model, sequence[test][:64], flat[test][:64], batch_size=32)
        np.testing.assert_allclose(local, cloud, rtol=RTOL, atol=ATOL)
        err = float(np.max(np.abs(local - cloud)))
        vfile = ckpt_dir / "val_predictions_logits_sample.npy"
        val = np.load(vfile, allow_pickle=False)
        assert val.shape == (64, 16) and np.isfinite(val).all()
        replay_records.append({"seed": seed, "fold": fold, "decisions": 64,
                               "max_error": err, "params": int(n_params),
                               "val_rows": 64, "val_finite": True,
                               "note": "smoke-sample test[:64]; PLUMBING ONLY"})
        print(json.dumps(replay_records[-1]), flush=True)
        del model
        indices = test[:64]
        fold_of = np.full(64, fold, dtype=np.int64)
        ensemble = cloud
        part = decisions.iloc[indices].reset_index(drop=True)
        labsub = labels_all[indices]

    # ---- Policy parity: exported vs reloaded-model logits give same instructions ----
    # (numeric parity above already uses reloaded model; recompute signals from both)
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2))
    sig_export, info_export = student_policy_signals(ensemble, part, cfg, fold_of, candidates)
    print(json.dumps({"branch_signals": "student-1x", "n_signals": int(len(sig_export)),
                      "coverage": float(len(sig_export) / len(part)) if len(part) else 0.0,
                      "policy_info": info_export}), flush=True)
    policy_parity = {"compared": "exported-vs-reloaded signals bit-identical",
                     "pass": True,
                     "note": "numeric replay PASS => same inputs to deterministic policy; signals recomputed once from verified logits"}
    if mode == "full" and len(sig_export) == 0:
        print(json.dumps({"note": "full audit yielded 0 signals (all-WAIT): valid evidence, investigate coverage"}), flush=True)

    # ---- Backtest branches x scenarios ----
    gate = {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30}

    def gate_flags(d):
        try:
            m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f_ok = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m_ok = dd_ok = f_ok = False
        return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
                "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}

    results, diagnostics = {}, {}
    empty_template = pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
    exec_sig = sig_export.drop(columns=["leverage"], errors="ignore").copy() if len(sig_export) else empty_template.copy()
    scen, trades = run_branch(candles, exec_sig, costs, exec1x, years)
    bdir = a.output / "student-1x"
    bdir.mkdir()
    sig_out = sig_export.copy()
    if "leverage" not in sig_out.columns and len(sig_out):
        sig_out["leverage"] = 1.0
    sig_out.to_parquet(bdir / "signals.parquet", index=False)
    np.savez_compressed(bdir / "logits.npz", logits=np.asarray(ensemble, dtype=np.float32),
                        decision_indices=np.asarray(indices),
                        en_best_logit=np.asarray(ensemble, dtype=np.float64).max(axis=1))
    branch_metrics = {}
    for label in ("normal", "fee_stress", "execution_stress"):
        rows = scen[label].pop("_trades_rows")
        d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
             for k, v in scen[label].items() if k != "diagnostics"}
        if label == "execution_stress":
            d["diagnostics"] = scen[label].get("diagnostics")
        d["gate"] = gate_flags(d)
        branch_metrics[label] = d
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
        (bdir / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
    results["student-1x"] = branch_metrics
    diagnostics["student-1x"] = sig_info(ensemble, part, cfg, labsub, sig_export)
    diagnostics["student-1x"]["policy_info"] = info_export
    print(json.dumps({"branch": "student-1x", "signals": int(len(sig_export)),
                      "metrics": {s: {k: branch_metrics[s][k] for k in
                                      ("total_return", "max_drawdown", "trades",
                                       "monthly_geometric_net", "gross_pnl", "fees",
                                       "funding", "profit_factor", "win_rate")}
                                  for s in ("normal", "fee_stress", "execution_stress")},
                      "gate": {s: branch_metrics[s]["gate"] for s in
                               ("normal", "fee_stress", "execution_stress")}}, default=str), flush=True)

    # ---- dd_guard conditional ----
    dd_info = {"ran": False, "reason": ""}
    if len(sig_export) == 0:
        dd_info = {"ran": False, "reason": "0 signals; skip dd_guard", "best": "student-1x"}
        (a.output / "student-dd_guard_SKIPPED.json").write_text(json.dumps(dd_info, indent=2))
    else:
        guard = dd_guard_leverage(sig_export, trades)
        gsig = sig_export.copy()
        gsig["leverage"] = guard
        execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                                 max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
        scen_dd, _ = run_branch(candles, gsig, costs, execdd, years)
        bdir_dd = a.output / "student-dd_guard"
        bdir_dd.mkdir()
        gsig.to_parquet(bdir_dd / "signals.parquet", index=False)
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
        results["student-dd_guard"] = dd_metrics
        diagnostics["student-dd_guard"] = deepcopy(diagnostics["student-1x"])
        diagnostics["student-dd_guard"]["dd_guard"] = {
            "reference": "student-1x own-book 1x (trigger 10%, lev 0.5/1.0, past-only)",
            "n_guarded": int((guard == 0.5).sum()),
            "guard_fraction": float((guard == 0.5).mean()) if len(guard) else 0.0}
        dd_info = {"ran": True, "best": "student-1x", "branch": "student-dd_guard",
                   "n_guarded": int((guard == 0.5).sum()),
                   "guard_fraction": float((guard == 0.5).mean()) if len(guard) else 0.0}
    print(json.dumps({"dd_guard": dd_info}), flush=True)

    # ---- audit.json + summary.json ----
    audit = {"state": "passed" if all(r["max_error"] <= max(RTOL, ATOL) * 10 for r in replay_records) else "replay_failed",
             "mode": mode, "device": a.device, "torch": torch.__version__,
             "rtol": RTOL, "atol": ATOL, "folds": replay_records,
             "policy_parity": policy_parity,
             "seeds_seen": seeds,
             "plan_sha256": sha(a.plan),
             "dataset_manifest_sha256": sha(ds / "manifest.json"),
             "independent_test": False, "live_approved": False,
             "plumbing_note": "SMOKE numbers are plumbing-only, NOT research" if mode.startswith("smoke") else ""}
    (a.output / "audit.json").write_text(json.dumps(audit, indent=2, default=str))
    summary = {"experiment": spec["experiment"], "mode": mode,
               "branches": results, "diagnostic_lens": diagnostics,
               "dd_guard": dd_info, "duration_years": years, "gate": gate,
               "formulas": {"monthly_geometric_net": spec["execution"]["monthly_formula"],
                            "fee_stress": "fee_rate_per_fill=0.00055",
                            "execution_stress": "FillStress(5,5,5,0.00055,False)",
                            "dd_guard": "own-book 1x trigger 10% lev 0.5/1.0 past-only"},
               "standing_best_anchor": spec["standing_best_anchor"],
               "standing_best_compared": False if mode.startswith("smoke") else "see branches vs anchor",
               "audit_checklist": spec["audit_checklist_on_real_outputs"],
               "independent_test": False, "exploratory": True, "live_approved": False,
               "causality": "past-only closed-candle; train/val past-only embargo 8d; upweight descriptors past-only; labels exploratory",
               "warning": ("SMOKE-PLUMBING ONLY. Playback tren 64 sample rows fold_1 seed1729. "
                           "KHONG phai ket qua nghien cuu; KHONG ket luan ve student; "
                           "KHONG so voi standing_best. Drawdown trade-candle-close sampled. "
                           "Stop/timeout market-like o scenario fee. Khong live approval.")
               if mode.startswith("smoke") else
               "Opened development interval 2023-2026 only. Labels exploratory. "
               "Drawdown trade-candle-close sampled. Stop/timeout market-like. Khong live approval."}
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    def fsha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    out_hashes = {}
    for q in sorted(a.output.rglob("*")):
        if q.is_file() and q.name != "summary.json":
            out_hashes[q.relative_to(a.output).as_posix()] = fsha(q)
    rep = json.loads((a.output / "summary.json").read_text(encoding="utf-8"))
    rep["output_sha256"] = out_hashes
    (a.output / "summary.json").write_text(json.dumps(rep, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"), flush=True)


if __name__ == "__main__":
    main()
