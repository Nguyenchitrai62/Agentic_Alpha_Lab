"""R-DIAGNOSTIC (R-v28audit tiep noi): TAI SAO BigModel 2.8M FAIL du replay PASS.

Chi doc + phan tich local, KHONG train, KHONG cloud, KHONG live.
Khong dung future de "sua" gi, chi do (causal, past-only, labels exploratory).
So sanh predictions nowrap:
  - v28: artifacts/kaggle/v28_bigmodel_download/bigmodel-training (33 predictions.npy)
  - v29: artifacts/kaggle/v29_download/tcn-training (33 predictions.npy)
  - v30: artifacts/research/opencode_v02_reproduce_v30/isotonic_4/predictions.npz
Ghi artifacts/research/opencode_v34_diagnostic/ (moi, khong ghi de).
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from agentic_alpha_lab.backtest.swing import swing_signals  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402

SEEDS = [1729, 1730, 1731]
V28_SRC = ROOT / "artifacts/kaggle/v28_bigmodel_download/bigmodel-training"
V29_SRC = ROOT / "artifacts/kaggle/v29_download/tcn-training"
V30_PRED = ROOT / "artifacts/research/opencode_v02_reproduce_v30/isotonic_4/predictions.npz"
DS = ROOT / "data/processed/swing_regime_research_v4"
PARENT_PLAN = ROOT / "configs/swing_v15_continuous_folds.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v34_diagnostic"

BUCKET_EDGES = [-np.inf, -0.5, 0.0, 0.3, 1.0, 2.0, np.inf]
TOPK = 408  # 10% x 4076 decisions (argsort exact, tranh tie cua isotonic)


def sha256(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def partition_indices(decisions, parent):
    end = pd.Timestamp(parent["complete_evaluation_until"])
    parts, previous = [], None
    for start, stop in parent["folds"]:
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        if start >= stop or (previous is not None and start != previous):
            raise ValueError("Continuous plan has a gap or overlap")
        previous = stop
        mask = (
            (decisions.signal_time >= start)
            & (decisions.signal_time < stop)
            & (decisions.label_end < end)
        ).to_numpy()
        parts.append(np.flatnonzero(mask))
    if previous != end:
        raise ValueError("Final fold does not match evaluation cutoff")
    return parts


def load_ensemble(source):
    per_seed = []
    for seed in SEEDS:
        folds = []
        for fold in range(11):
            path = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            folds.append(np.load(path, allow_pickle=False))
        per_seed.append(np.concatenate(folds, axis=0))
    stacked = np.stack(per_seed)
    if stacked.shape[0] != 3 or stacked.shape[2] != 16 or stacked.shape[3] != 6:
        raise ValueError(f"Unexpected ensemble shape: {stacked.shape}")
    if not np.isfinite(stacked).all():
        raise ValueError("Nonfinite ensemble predictions")
    return stacked


def fill_of(pred):
    return 1 / (1 + np.exp(-np.clip(pred[..., 4], -40, 40)))


def expected_of(pred):
    return pred[..., 0] * fill_of(pred)


def qstats(x):
    x = np.asarray(x, dtype=np.float64)
    return {
        "mean": float(x.mean()),
        "std": float(x.std()),
        "min": float(x.min()),
        "p10": float(np.quantile(x, 0.10)),
        "p50": float(np.quantile(x, 0.50)),
        "p90": float(np.quantile(x, 0.90)),
        "p95": float(np.quantile(x, 0.95)),
        "p99": float(np.quantile(x, 0.99)),
        "max": float(x.max()),
    }


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de diagnostic cu; dung dir moi")
    out.mkdir(parents=True)

    parent = json.loads(PARENT_PLAN.read_text())
    cfg = json.loads((DS / "config.json").read_text())
    decisions = pd.read_parquet(DS / "decisions.parquet")
    with np.load(DS / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]
    policy_net = float(cfg["policy"]["minimum_expected_net_percent"])
    policy_fill = float(cfg["policy"]["minimum_fill_score"])

    parts = partition_indices(decisions, parent)
    fold_lens = [len(p) for p in parts]
    indices = np.concatenate(parts)
    part = decisions.iloc[indices].reset_index(drop=True)
    truth = labels_all[indices]  # (4076, 16, 3): net, fill, pos
    n = len(part)
    assert n == 4076, n

    v28_raw = load_ensemble(V28_SRC)
    v29_raw = load_ensemble(V29_SRC)
    assert v28_raw.shape[1] == n and v29_raw.shape[1] == n
    for seed_stack, tag in ((v28_raw, "v28"), (v29_raw, "v29")):
        off = 0
        for fold, sel in enumerate(parts):
            chunk = seed_stack[:, off : off + len(sel)]
            if chunk.shape[1] != len(sel):
                raise ValueError(f"{tag} fold {fold} length mismatch")
            off += len(sel)

    c28, d28 = combine(v28_raw, 0.0)
    c28m, d28m = combine(v28_raw, 1.0)
    c29, d29 = combine(v29_raw, 0.0)
    c29m, d29m = combine(v29_raw, 1.0)
    with np.load(V30_PRED, allow_pickle=False) as z:
        c30 = z["prediction"].astype(np.float64)
        v30_idx = z["decision_indices"]
    np.testing.assert_array_equal(v30_idx, indices)

    models = {
        "v28_mean": (c28, d28["selection_score_percent"]),
        "v28_mms": (c28m, d28m["selection_score_percent"]),
        "v29_mean": (c29, d29["selection_score_percent"]),
        "v29_mms": (c29m, d29m["selection_score_percent"]),
        "v30_iso4": (c30, None),
    }

    # (1) Phan phoi score / selection_score + pass policy + coverage sau frequency cap.
    dist_rows, pass_rows, sig_info = [], [], {}
    for name, (combo, sel) in models.items():
        fill = fill_of(combo)
        exp = combo[..., 0] * fill
        best_exp = exp.max(1)
        arg = exp.argmax(1)
        best_fill = fill[np.arange(n), arg]
        best_cond = combo[np.arange(n), arg, 0]
        score = sel.max(1) if sel is not None else best_exp
        row = {"model": name, **{f"best_exp_{k}": v for k, v in qstats(best_exp).items()},
               **{f"score_{k}": v for k, v in qstats(score).items()}}
        row["best_fill_mean"] = float(best_fill.mean())
        row["best_fill_min"] = float(best_fill.min())
        pass_net = best_exp >= policy_net
        pass_both = pass_net & (best_fill >= policy_fill)
        row["pass_net_rate"] = float(pass_net.mean())
        row["pass_both_rate"] = float(pass_both.mean())
        row["pass_both_n"] = int(pass_both.sum())
        dist_rows.append(row)
        pass_rows.append({"model": name, "pass_net_n": int(pass_net.sum()),
                          "pass_net_rate": float(pass_net.mean()),
                          "pass_both_n": int(pass_both.sum()),
                          "pass_both_rate": float(pass_both.mean())})
        signals = swing_signals(combo.astype(np.float32), part, cfg)
        months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
        sig_info[name] = {
            "n_signals": int(len(signals)),
            "coverage": float(len(signals) / n),
            "directions": {str(k): int(v) for k, v in signals.direction.value_counts().items()} if len(signals) and "direction" in signals else {},
            "candidates": {str(k): int(v) for k, v in signals.candidate_id.value_counts().items()} if len(signals) and "candidate_id" in signals else {},
            "holdings": {str(k): int(v) for k, v in signals.holding_bars.value_counts().items()} if len(signals) and "holding_bars" in signals else {},
            "active_months": int(len(months)),
            "first_signal": str(signals.signal_time.min()) if len(signals) else None,
            "last_signal": str(signals.signal_time.max()) if len(signals) else None,
            "by_month": {str(k): int(v) for k, v in months.items()} if len(signals) else {},
        }
        (out / f"signals_{name}.csv").write_text(
            signals.to_csv(index=False) if len(signals) else "empty\n", encoding="utf-8")

    pd.DataFrame(dist_rows).to_csv(out / "score_distribution.csv", index=False)
    pd.DataFrame(pass_rows).to_csv(out / "threshold_pass.csv", index=False)

    # (2) Calibration tho: buckets co dinh (candidate-level) + top-decile picked.
    bucket_rows, top_rows = [], []
    for name, (combo, sel) in models.items():
        fill = fill_of(combo)
        exp = combo[..., 0] * fill
        for lo, hi in zip(BUCKET_EDGES[:-1], BUCKET_EDGES[1:]):
            mask = (exp >= lo) & (exp < hi)
            if mask.any():
                bucket_rows.append({
                    "model": name, "lower": None if not np.isfinite(lo) else float(lo),
                    "upper": None if not np.isfinite(hi) else float(hi),
                    "candidate_obs": int(mask.sum()),
                    "predicted_net": float(exp[mask].mean()),
                    "observed_net": float(truth[..., 0][mask].mean()),
                    "observed_fill": float(truth[..., 1][mask].mean()),
                })
        score = sel.max(1) if sel is not None else exp.max(1)
        order = np.argsort(score, kind="stable")[-TOPK:]
        k = exp[order].argmax(1)
        pe = exp[order, k]
        pf = fill[order, k]
        pc = combo[order, k, 0]
        rn = truth[order, k, 0]
        rf = truth[order, k, 1]
        rp = truth[order, k, 2]
        filled = rf == 1
        top_rows.append({
            "model": name, "n": int(TOPK),
            "score_cut": float(score[order].min()),
            "pred_exp_mean": float(pe.mean()),
            "pred_cond_mean": float(pc.mean()),
            "pred_fill_mean": float(pf.mean()),
            "obs_fill_rate": float(rf.mean()),
            "obs_pos_given_fill": float(rp[filled].mean()) if filled.any() else None,
            "obs_net_mean": float(rn.mean()),
            "obs_net_filled_mean": float(rn[filled].mean()) if filled.any() else None,
            "bias_pred_minus_obs": float(pe.mean() - rn.mean()),
        })
    pd.DataFrame(bucket_rows).to_csv(out / "calibration_buckets.csv", index=False)
    pd.DataFrame(top_rows).to_csv(out / "topdecile.csv", index=False)

    # (3) Rank quality: within-decision action-rank correlation theo fold.
    net_map = {"v28_mean": d28["mean_expected_net_percent"],
               "v29_mean": d29["mean_expected_net_percent"],
               "v30_iso4": c30[..., 0] * fill_of(c30)}
    rank_rows = []
    off = 0
    for fi, sel in enumerate(parts):
        sl = slice(off, off + len(sel))
        off += len(sel)
        fold_start = str(pd.Timestamp(parent["folds"][fi][0]).date())
        for mname, netm in net_map.items():
            per = rank_corr_per_decision(netm[sl], truth[sl, :, 0])
            valid = per[~np.isnan(per)]
            rank_rows.append({"model": mname, "fold": fi, "fold_start": fold_start,
                              "n": int(len(sel)), "n_valid": int(len(valid)),
                              "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                              "rank_corr_std": float(valid.std()) if len(valid) else None})
    for mname, netm in net_map.items():
        per = rank_corr_per_decision(netm, truth[:, :, 0])
        valid = per[~np.isnan(per)]
        rank_rows.append({"model": mname, "fold": "overall", "fold_start": "",
                          "n": int(n), "n_valid": int(len(valid)),
                          "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                          "rank_corr_std": float(valid.std()) if len(valid) else None})
    pd.DataFrame(rank_rows).to_csv(out / "rank_by_fold.csv", index=False)

    # (4) Coverage theo thoi gian: theo fold + theo thang (+ gia BTC median).
    dec_ym = pd.to_datetime(part.signal_time).dt.strftime("%Y-%m")
    price_med = part.assign(ym=dec_ym.values).groupby("ym")["close"].median()
    cov_fold_rows, cov_month_rows = [], []
    for name in models:
        sig_csv = out / f"signals_{name}.csv"
        try:
            sig = pd.read_csv(sig_csv, parse_dates=["signal_time"])
            if "empty" in sig.columns and len(sig) == 0:
                sig = sig.iloc[0:0]
        except Exception:
            sig = pd.DataFrame()
        if len(sig) and "signal_time" in sig:
            sig["signal_time"] = pd.to_datetime(sig["signal_time"], utc=True)
            folds_of = []
            for ts in sig["signal_time"]:
                f = next((i for i, (s, e) in enumerate(parent["folds"])
                          if pd.Timestamp(s) <= ts < pd.Timestamp(e)), -1)
                folds_of.append(f)
            sig = sig.assign(fold=folds_of)
            by_fold = sig.groupby("fold").size()
            for fi, sel in enumerate(parts):
                cov_fold_rows.append({"model": name, "fold": fi,
                                      "fold_start": str(pd.Timestamp(parent["folds"][fi][0]).date()),
                                      "n_decisions": int(len(sel)),
                                      "n_signals": int(by_fold.get(fi, 0)),
                                      "coverage": float(by_fold.get(fi, 0) / len(sel))})
            by_month = sig.signal_time.dt.strftime("%Y-%m").value_counts()
            for ym in sorted(set(list(by_month.index) + list(price_med.index))):
                cov_month_rows.append({"model": name, "month": str(ym),
                                       "n_signals": int(by_month.get(ym, 0)),
                                       "btc_close_median": float(price_med.get(ym, float("nan")))})
        else:
            for fi, sel in enumerate(parts):
                cov_fold_rows.append({"model": name, "fold": fi,
                                      "fold_start": str(pd.Timestamp(parent["folds"][fi][0]).date()),
                                      "n_decisions": int(len(sel)), "n_signals": 0, "coverage": 0.0})
    pd.DataFrame(cov_fold_rows).to_csv(out / "coverage_by_fold.csv", index=False)
    pd.DataFrame(cov_month_rows).to_csv(out / "coverage_by_month.csv", index=False)

    # Epoch selection v28 (bang chung undertrain): doc metadata read-only.
    from collections import Counter
    ep = Counter()
    for meta_path in sorted((V28_SRC / "seed1729").parent.glob("seed*/checkpoints/fold_*/metadata.json")):
        meta = json.loads(Path(meta_path).read_text())
        ep[int(meta["training"]["epochs"])] += 1
    epoch_dist = {str(k): int(v) for k, v in sorted(ep.items())}

    proposals = [
        "Loss + epoch: them pairwise/listwise ranking loss tren value head (kieu v29 ranking_weight ~0.5, temperature ~1.0%), nang trong so value-objective so voi aux heads (direction/quantile/excursion), train fixed 16 epochs thay vi early-stop patience-3/min_improvement-1e-4 (v28 dung o epoch 1-3 o 29/33 folds) — fit tren train/val past-only, khong tune tren test.",
        "Coverage floor + calibration truoc policy: giu policy gate (0.3%/0.25) nhung calibrate causal (isotonic past-only nhu v30) TRUOC choose, chon nguong tu phan vi validation (vi du top-decile) thay vi so tuyet doi, dat coverage floor (vi du toi thieu ~2 signals/thang hoac fallback WAIT co kiem soat) de tranh collapse ve 3 candidates/1 regime nhu v28.",
        "Kien truc/data: giu candidate-prior + residual head (kieu v29) thay vi multitask from-scratch 5 heads doc lap; prior on dinh giu rank (~0.07), residual hoc thu tu; giu disagreement lam sizing/dd_guard chu khong lam selection penalty (mms giet coverage 9.6%->2.6% ma khong cuu rank). Features du (price+deriv+flow+funding+macro) — van de la objective, khong phai thieu feature.",
    ]

    summary = {
        "experiment": "opencode-r9a-diagnostic-v28fail",
        "causality": "past-only, closed-candle, fill tu nen ke tiep; labels exploratory; khong dung future de sua gi, chi do",
        "inputs": {
            "v28_source": str(V28_SRC), "v29_source": str(V29_SRC),
            "v30_predictions": str(V30_PRED), "dataset": str(DS),
            "parent_plan": str(PARENT_PLAN),
        },
        "policy": {"minimum_expected_net_percent": policy_net, "minimum_fill_score": policy_fill,
                   "n_decisions": n, "top_decile_k": TOPK},
        "score_distribution": dist_rows,
        "threshold_pass": pass_rows,
        "signals": sig_info,
        "topdecile": top_rows,
        "rank_overall": [r for r in rank_rows if r["fold"] == "overall"],
        "v28_selected_epochs": epoch_dist,
        "v28_params": 2798731,
        "v29_params": 40707,
        "proposals": proposals,
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report_lines = [
        "# Diagnostic v28 BigModel FAIL (R-DIAGNOSTIC, local-only)",
        "",
        "Xem summary.json + cac CSV trong thu muc nay. Labels exploratory, causal past-only.",
        "",
        "## 1. Phan phoi score / pass policy",
        "",
    ]
    for r in pass_rows:
        s = sig_info[r["model"]]
        report_lines.append(
            f"- {r['model']}: pass gate {r['pass_both_n']}/{n} ({r['pass_both_rate']*100:.2f}%), "
            f"signals {s['n_signals']} (coverage {s['coverage']*100:.3f}%), "
            f"huong {s['directions']}, candidates {s['candidates']}")
    report_lines += ["", "## 2. Calibration top-decile", ""]
    for r in top_rows:
        report_lines.append(
            f"- {r['model']}: pred {r['pred_exp_mean']:.3f}% vs obs {r['obs_net_mean']:.3f}% "
            f"(bias {r['bias_pred_minus_obs']:+.3f}), fill {r['obs_fill_rate']:.2f}, "
            f"P(net>0|fill) {r['obs_pos_given_fill']:.3f}")
    report_lines += ["", "## 3. Rank theo fold (overall)", ""]
    for r in summary["rank_overall"]:
        report_lines.append(f"- {r['model']}: {r['rank_corr_mean']:.4f} (n_valid {r['n_valid']})")
    report_lines += ["", "## 4. Coverage theo thoi gian", ""]
    for name, s in sig_info.items():
        report_lines.append(
            f"- {name}: {s['n_signals']} signals / {s['active_months']} thang, "
            f"{s['first_signal']} -> {s['last_signal']}")
    report_lines += ["", "## Ket luan + 3 de xuat", "",
                     "v28 FAIL vi underfit + sai objective (multitask proxy, khong ranking loss, "
                     "early-stop o epoch 1-3) -> scores compressed duoi gate, coverage sup do, "
                     "rank ~0.02, chi pick 3 long-7d candidates trong 1 regime.",
                     ""]
    for i, p in enumerate(proposals, 1):
        report_lines.append(f"{i}. {p}")
    (out / "BAO_CAO.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    digests = {}
    for f in sorted(out.iterdir()):
        if f.is_file():
            digests[f.name] = sha256(f)
    summary["output_sha256"] = digests
    summary["input_sha256"] = {
        "v30_predictions": sha256(V30_PRED),
        "dataset_config": sha256(DS / "config.json"),
        "parent_plan": sha256(PARENT_PLAN),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"state": "done", "out": str(out),
                      "signals": {k: v["n_signals"] for k, v in sig_info.items()},
                      "rank_overall": {r["model"]: round(r["rank_corr_mean"], 4) for r in summary["rank_overall"]}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
