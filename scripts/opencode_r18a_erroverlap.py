"""R-DIAGNOSTIC round18a (v56 erroverlap): ERROR OVERLAP across model families.

Read-only analysis, no training/fitting. Pre-spec: configs/opencode_v56_erroverlap.json
(one correctness definition top1_sign, applied identically to all families).
Universe: same 4076 decisions as v34. Labels exploratory, past-only splits only.
New outputs only under artifacts/research/opencode_v56_erroverlap/ (fail if exists).
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
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.data.swing import grid  # noqa: E402

SEEDS = [1729, 1730, 1731]
CFG_PATH = ROOT / "configs/opencode_v56_erroverlap.json"
DS = ROOT / "data/processed/swing_regime_research_v4"
PARENT_PLAN = ROOT / "configs/swing_v15_continuous_folds.json"
V30_PRED = ROOT / "artifacts/research/opencode_v02_reproduce_v30/isotonic_4/predictions.npz"
OUT_DIR = ROOT / "artifacts/research/opencode_v56_erroverlap"
SRC = {
    "v28": ROOT / "artifacts/kaggle/v28_bigmodel_download/bigmodel-training",
    "v29": ROOT / "artifacts/kaggle/v29_download/tcn-training",
    "v33": ROOT / "artifacts/kaggle/v33_actionmargin_download/tcn-training",
}
FAMS = ["v28", "v29", "v33", "v30"]


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


def load_ensemble(source, n):
    per_seed = []
    for seed in SEEDS:
        folds = []
        for fold in range(11):
            path = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            folds.append(np.load(path, allow_pickle=False))
        per_seed.append(np.concatenate(folds, axis=0))
    stacked = np.stack(per_seed)
    if stacked.shape[0] != 3 or stacked.shape[1] != n or stacked.shape[2] != 16 or stacked.shape[3] != 6:
        raise ValueError(f"Unexpected ensemble shape: {stacked.shape}")
    if not np.isfinite(stacked).all():
        raise ValueError("Nonfinite ensemble predictions")
    return stacked


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


def phi_of(a, b):
    # a,b binary arrays; phi coefficient of correct indicators
    n11 = int(((a == 1) & (b == 1)).sum())
    n10 = int(((a == 1) & (b == 0)).sum())
    n01 = int(((a == 0) & (b == 1)).sum())
    n00 = int(((a == 0) & (b == 0)).sum())
    den = np.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return (n11 * n00 - n10 * n01) / den if den > 0 else float("nan"), (n11, n10, n01, n00)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de; dung dir moi")
    out.mkdir(parents=True)

    cfg = json.loads(CFG_PATH.read_text())
    parent = json.loads(PARENT_PLAN.read_text())
    ds_cfg = json.loads((DS / "config.json").read_text())
    decisions = pd.read_parquet(DS / "decisions.parquet")
    decisions["signal_time"] = pd.to_datetime(decisions["signal_time"], utc=True)
    decisions["label_end"] = pd.to_datetime(decisions["label_end"], utc=True)
    with np.load(DS / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]
    _ = ds_cfg

    parts = partition_indices(decisions, parent)
    indices = np.concatenate(parts)
    part = decisions.iloc[indices].reset_index(drop=True)
    truth = labels_all[indices].astype(np.float64)  # (N,16,3)
    n = len(part)
    assert n == 4076, n
    assert np.isfinite(truth).all(), "truth has nonfinite"

    cand_grid = np.asarray(grid(json.loads((DS / "config.json").read_text())))
    side_of = np.where(cand_grid[:, 0] == 1, "long", "short")  # k<8 long

    # --- predictions: identical top1 rule per family ---
    pred_exp, topk, nets_for_rank = {}, {}, {}
    for fam, src in SRC.items():
        raw = load_ensemble(src, n)
        combo, det = combine(raw, 0.0)
        exp = combo[..., 0].astype(np.float64) * fill_of(combo)
        pred_exp[fam] = exp
        topk[fam] = exp.argmax(1)
        nets_for_rank[fam] = det["mean_expected_net_percent"].astype(np.float64)
    with np.load(V30_PRED, allow_pickle=False) as z:
        c30 = z["prediction"].astype(np.float64)
        v30_idx = z["decision_indices"]
    np.testing.assert_array_equal(v30_idx, indices)
    exp30 = c30[..., 0] * fill_of(c30)
    pred_exp["v30"] = exp30
    topk["v30"] = exp30.argmax(1)
    nets_for_rank["v30"] = exp30  # calibrated score doubles as rank signal
    v30_abstain = (c30[..., 0] == 0).all(axis=1)
    v30_valid = ~v30_abstain

    # --- correctness / errors / fills (ONE definition, identical) ---
    correct, filled = {}, {}
    for fam in FAMS:
        k = topk[fam]
        correct[fam] = (truth[np.arange(n), k, 0] > 0).astype(int)
        filled[fam] = (truth[np.arange(n), k, 1] == 1).astype(int)
    error = {fam: 1 - correct[fam] for fam in FAMS}

    # --- per-model accuracy ---
    acc_rows = []
    for fam in FAMS:
        c = correct[fam]
        f = filled[fam]
        acc_rows.append({
            "model": fam, "n": n, "acc": float(c.mean()),
            "n_correct": int(c.sum()), "n_error": int((1 - c).sum()),
            "fill_rate_own_top": float(f.mean()),
            "acc_given_own_filled": float(c[f == 1].mean()) if (f == 1).any() else None,
            "n_own_filled": int((f == 1).sum()),
        })
    pd.DataFrame(acc_rows).to_csv(out / "per_model_accuracy.csv", index=False)

    # --- (a) pairwise error overlap ---
    ov_rows = []
    for i, fa in enumerate(FAMS):
        for fb in FAMS[i + 1:]:
            ea, eb = error[fa] == 1, error[fb] == 1
            inter = int((ea & eb).sum())
            union = int((ea | eb).sum())
            jacc = inter / union if union else float("nan")
            agr = float(((correct[fa] == correct[fb])).mean())
            phi, (n11, n10, n01, n00) = phi_of(correct[fa], correct[fb])
            ov_rows.append({"A": fa, "B": fb, "n": n,
                            "errA": int(ea.sum()), "errB": int(eb.sum()),
                            "both_wrong": inter, "either_wrong": union,
                            "jaccard_error": jacc, "agreement": agr,
                            "phi_correct": float(phi) if np.isfinite(phi) else None,
                            "n11": n11, "n10": n10, "n01": n01, "n00": n00})
    pd.DataFrame(ov_rows).to_csv(out / "overlap_matrix.csv", index=False)

    # --- (b) conditional accuracy, full directed matrix ---
    cond_rows = []
    for fa in FAMS:
        wmask = error[fa] == 1
        nw = int(wmask.sum())
        for fb in FAMS:
            if fa == fb:
                continue
            marg = float(correct[fb].mean())
            p_cond = float(correct[fb][wmask].mean()) if nw else None
            se = float(np.sqrt(p_cond * (1 - p_cond) / nw)) if nw and p_cond is not None else None
            z = float((p_cond - marg) / se) if se else None
            cond_rows.append({"A_wrong": fa, "B": fb, "n_Awrong": nw,
                              "B_marginal": marg, "B_given_Awrong": p_cond,
                              "lift": (p_cond - marg) if p_cond is not None else None,
                              "se": se, "z": z})
    pd.DataFrame(cond_rows).to_csv(out / "conditional_accuracy.csv", index=False)

    # --- (c) oracle bound ---
    union_correct = np.zeros(n, dtype=int)
    for fam in FAMS:
        union_correct |= correct[fam]
    best_single = max(float(correct[f].mean()) for f in FAMS)
    oracle = float(union_correct.mean())
    # fills-gated oracle
    any_filled = np.zeros(n, dtype=bool)
    any_corr_filled = np.zeros(n, dtype=bool)
    for fam in FAMS:
        any_filled |= (filled[fam] == 1)
        any_corr_filled |= ((correct[fam] == 1) & (filled[fam] == 1))
    oracle_gated = float(any_corr_filled[any_filled].mean()) if any_filled.any() else None
    oracle_rows = [{"scope": "full", "n": n, "oracle": oracle,
                    "best_single": best_single, "oracle_minus_best": oracle - best_single,
                    "n_oracle_correct": int(union_correct.sum())},
                   {"scope": "fills_gated_any", "n": int(any_filled.sum()),
                    "oracle": oracle_gated, "best_single": None,
                    "oracle_minus_best": None, "n_oracle_correct": int(any_corr_filled.sum())}]
    pd.DataFrame(oracle_rows).to_csv(out / "oracle.csv", index=False)

    # --- (d) fills-gated pairwise (common-filled subsets) ---
    gated_rows = []
    for i, fa in enumerate(FAMS):
        for fb in FAMS[i + 1:]:
            s = ((filled[fa] == 1) & (filled[fb] == 1))
            ns = int(s.sum())
            if ns == 0:
                gated_rows.append({"A": fa, "B": fb, "n_common_filled": 0,
                                   "jaccard_error": None, "agreement": None,
                                   "B_given_Awrong": None, "A_given_Bwrong": None})
                continue
            ea, eb = error[fa][s] == 1, error[fb][s] == 1
            inter = int((ea & eb).sum())
            union = int((ea | eb).sum())
            gated_rows.append({
                "A": fa, "B": fb, "n_common_filled": ns,
                "jaccard_error": inter / union if union else float("nan"),
                "agreement": float((correct[fa][s] == correct[fb][s]).mean()),
                "B_given_Awrong": float(correct[fb][s][ea].mean()) if ea.any() else None,
                "A_given_Bwrong": float(correct[fa][s][eb].mean()) if eb.any() else None,
                "accA": float(correct[fa][s].mean()), "accB": float(correct[fb][s].mean()),
                "oracle_pair": float(((correct[fa][s] == 1) | (correct[fb][s] == 1)).mean())})
    pd.DataFrame(gated_rows).to_csv(out / "fills_gated_pairs.csv", index=False)

    # --- v30-valid sensitivity (3708 rows) ---
    sens_rows = []
    sv = v30_valid
    for fam in FAMS:
        sens_rows.append({"model": fam, "scope": "v30_valid", "n": int(sv.sum()),
                          "acc": float(correct[fam][sv].mean())})
    uo = np.zeros(n, dtype=int)
    for fam in FAMS:
        uo |= correct[fam]
    sens_rows.append({"model": "ORACLE4", "scope": "v30_valid", "n": int(sv.sum()),
                      "acc": float(uo[sv].mean())})
    pd.DataFrame(sens_rows).to_csv(out / "sensitivity_v30valid.csv", index=False)

    # --- pockets (past-only split variables; thresholds past-only fit) ---
    sig_time = pd.to_datetime(part["signal_time"], utc=True)
    atr_ratio = (part["atr4"].to_numpy(dtype=float) / part["close"].to_numpy(dtype=float))
    pre2025 = (sig_time < pd.Timestamp("2025-01-01", tz="UTC")).to_numpy()
    vol_cut = float(np.median(atr_ratio[pre2025]))
    conf30 = pred_exp["v30"][np.arange(n), topk["v30"]]
    conf_cut = float(np.median(conf30[pre2025 & v30_valid]))
    pockets = {}
    pockets["side_long"] = (np.array([side_of[k] for k in topk["v30"]]) == "long")
    pockets["side_short"] = ~pockets["side_long"]
    for h in (0, 6, 12, 18):
        pockets[f"session_{h:02d}h"] = (sig_time.dt.hour.to_numpy() == h)
    pockets["vol_high"] = atr_ratio >= vol_cut
    pockets["vol_low"] = ~pockets["vol_high"]
    pockets["era_2023_2024"] = (sig_time.dt.year.to_numpy() <= 2024)
    pockets["era_2025_2026"] = ~pockets["era_2023_2024"]
    allk = np.stack([topk[f] for f in FAMS])
    pockets["agree_all"] = (allk == allk[0]).all(axis=0)
    pockets["disagree_any"] = ~pockets["agree_all"]
    pockets["v30_agrees_any"] = ((topk["v30"] == topk["v28"]) | (topk["v30"] == topk["v29"]) | (topk["v30"] == topk["v33"]))
    pockets["v30_alone"] = ~pockets["v30_agrees_any"]
    pockets["conf_high"] = conf30 >= conf_cut
    pockets["conf_low"] = ~pockets["conf_high"]

    v30w = (error["v30"] == 1)
    pocket_rows, flags = [], []
    for pname, pmask in pockets.items():
        pmask = np.asarray(pmask, dtype=bool)
        np_ = int(pmask.sum())
        prow = {"pocket": pname, "n": np_, "frac": float(np_ / n),
                "v30_acc": float(correct["v30"][pmask].mean()) if np_ else None,
                "n_v30wrong": int((pmask & v30w).sum())}
        uo_p = uo[pmask].mean() if np_ else None
        prow["oracle"] = float(uo_p) if uo_p is not None else None
        for fb in ("v29", "v33", "v28"):
            marg = float(correct[fb].mean())
            sub = pmask & v30w
            ns = int(sub.sum())
            pc = float(correct[fb][sub].mean()) if ns else None
            if ns and pc is not None:
                se = float(np.sqrt(pc * (1 - pc) / ns))
                z = float((pc - marg) / se) if se > 0 else 0.0
                lift = float(pc - marg)
            else:
                se, z, lift = None, None, None
            prow[f"{fb}_given_v30wrong"] = pc
            prow[f"{fb}_lift"] = lift
            prow[f"{fb}_z"] = z
            if (pc is not None and lift is not None and z is not None
                    and lift >= 0.05 and ns >= 100 and z >= 2.0 and np_ >= 200):
                flags.append({"pocket": pname, "model": fb, "n_pocket": np_,
                              "n_v30wrong": ns, "cond_acc": pc,
                              "marginal": marg, "lift": lift, "z": z})
        pocket_rows.append(prow)
    pd.DataFrame(pocket_rows).to_csv(out / "pockets.csv", index=False)

    # --- rank context (read-only, same fn as v34) ---
    rank_rows = []
    for fam in FAMS:
        per = rank_corr_per_decision(nets_for_rank[fam], truth[:, :, 0])
        valid = per[~np.isnan(per)]
        rank_rows.append({"model": fam, "n": n, "n_valid": int(len(valid)),
                          "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                          "rank_corr_std": float(valid.std()) if len(valid) else None})
    pd.DataFrame(rank_rows).to_csv(out / "rank_context.csv", index=False)

    n_oracle_only_v30wrong = int(((uo == 1) & (error["v30"] == 1)).sum())
    summary = {
        "experiment": "opencode-v56-erroverlap",
        "config": "configs/opencode_v56_erroverlap.json",
        "causality": "read-only, no fitting; labels exploratory; pockets past-only",
        "definition": cfg["correctness_definition"],
        "n": n,
        "v30_abstain_n": int(v30_abstain.sum()),
        "vol_cut_atr4_over_close_prefit2025": vol_cut,
        "conf_cut_v30_prefit2025": conf_cut,
        "per_model": acc_rows,
        "pairwise": ov_rows,
        "conditional": cond_rows,
        "oracle": oracle_rows,
        "fills_gated_pairs": gated_rows,
        "sensitivity_v30valid": sens_rows,
        "pockets": pocket_rows,
        "pocket_flags": flags,
        "rank_context": rank_rows,
        "n_oracle_correct_where_v30_wrong": n_oracle_only_v30wrong,
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Error-overlap diagnostic v56 (R-DIAGNOSTIC, local-only)",
             "",
             "Definition (pre-specified, identical): top1_sign — correct iff realized net of model's argmax-exp pick > 0.",
             "",
             "## Per-model accuracy (N=4076)"]
    for r in acc_rows:
        lines.append(f"- {r['model']}: acc {r['acc']*100:.2f}% ({r['n_correct']}/{r['n']}), "
                     f"own-fill {r['fill_rate_own_top']*100:.1f}%, acc|filled {r['acc_given_own_filled']*100:.2f}%")
    lines += ["", "## Pairwise error overlap (Jaccard of error sets)"]
    for r in ov_rows:
        lines.append(f"- {r['A']} x {r['B']}: Jaccard {r['jaccard_error']:.3f} "
                     f"(both-wrong {r['both_wrong']}, either-wrong {r['either_wrong']}), agreement {r['agreement']*100:.1f}%")
    lines += ["", "## Conditional: P(B right | v30 wrong) vs marginal"]
    for r in cond_rows:
        if r["A_wrong"] == "v30":
            lines.append(f"- {r['B']} | v30 wrong: {r['B_given_Awrong']*100:.2f}% vs marginal {r['B_marginal']*100:.2f}% "
                         f"(lift {r['lift']*100:+.2f}pp, z {r['z']:+.2f}, n {r['n_Awrong']})")
    lines += ["", "## Oracle bound",
              f"- full: {oracle*100:.2f}% vs best-single {best_single*100:.2f}% (gap {oracle-best_single:+.2f}pp, n {int(union_correct.sum())})",
              f"- fills-gated: {oracle_gated*100:.2f}% on {int(any_filled.sum())} any-filled decisions" if oracle_gated else "- fills-gated: n/a",
              f"- oracle-correct where v30 wrong: {n_oracle_only_v30wrong}",
              "", "## Pockets",
              f"- {len(flags)} flagged pockets (lift>=5pp, n_v30wrong>=100, z>=2, pocket>=200)"]
    for f in flags:
        lines.append(f"  - {f['model']} in {f['pocket']}: cond {f['cond_acc']*100:.1f}% vs marg {f['marginal']*100:.1f}% "
                     f"(lift {f['lift']*100:+.1f}pp, z {f['z']:+.1f}, n {f['n_v30wrong']}/{f['n_pocket']})")
    lines += ["", "Labels exploratory; no live approval."]
    (out / "BAO_CAO.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    digests = {}
    for f in sorted(out.iterdir()):
        if f.is_file() and f.name != "summary.json":
            digests[f.name] = sha256(f)
    summary["output_sha256"] = digests
    summary["input_sha256"] = {
        "config": sha256(CFG_PATH),
        "v30_predictions": sha256(V30_PRED),
        "dataset_config": sha256(DS / "config.json"),
        "parent_plan": sha256(PARENT_PLAN),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"state": "done", "out": str(out),
                      "oracle": round(oracle, 4), "best_single": round(best_single, 4),
                      "flags": len(flags)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
