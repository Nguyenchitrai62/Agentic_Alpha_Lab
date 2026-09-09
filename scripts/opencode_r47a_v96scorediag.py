"""R-DIAGNOSTIC v127: TAI SAO attention FAIL ranking? (analysis only, no training).

So sanh frozen predictions tren cung 4076 decisions:
  - v38 multitask SSM ~0.6M (value 2.0 + pairwise-ranking 0.5 + aux + coverage-hinge):
    artifacts/kaggle/v38_rankloss_download/rankloss-training (33 x (n,16,6) map-v8)
  - v96 Transformer 8.77M (frame-x5 d320/h8 + cross-x2, ListNet-listwise PRIMARY 2.0
    tren value head TRADEABLE + value-scale-at-origin + select-raw):
    artifacts/kaggle/v96_transformer_download/transformer-training (33 x (n,16,6) map-v8)

Pre-spec: configs/opencode_v127_v96scorediag.json (metrics a-e + splits) — script RAISE
neu config thieu (khong tinh khi chua pre-spec). CUNG method family nhu v100
(smoothness gaps + Spearman + top-decile + past-only splits) + them entropy/
concentration attention-specific. Chi doc + thong ke mo ta + splits past-only;
KHONG fit, KHONG train, KHONG cloud, KHONG live.
Ghi artifacts/research/opencode_v127_v96scorediag/ (moi, khong ghi de).
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
N_FOLDS = 11
TOPK = 408
TAU_PCT = 1.0  # softmax temperature, percent (VERBATIM ListNet tau v96 + v55 style)
LOG16 = float(np.log(16))

CONFIG_PATH = ROOT / "configs/opencode_v127_v96scorediag.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v127_v96scorediag"


def sha256(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def partitions(decisions, parent):
    end = pd.Timestamp(parent["complete_evaluation_until"])
    parts = []
    for start, stop in parent["folds"]:
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        mask = (
            (decisions.signal_time >= start)
            & (decisions.signal_time < stop)
            & (decisions.label_end < end)
        ).to_numpy()
        parts.append(np.flatnonzero(mask))
    return parts


def load_mapv8(source, parts, tag):
    per_seed = []
    for seed in SEEDS:
        folds = []
        for fold in range(N_FOLDS):
            path = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            arr = np.load(path, allow_pickle=False)
            if arr.shape != (len(parts[fold]), 16, 6) or not np.isfinite(arr).all():
                raise ValueError(f"{tag} shape/values mismatch: {path} {arr.shape}")
            folds.append(arr)
        per_seed.append(np.concatenate(folds, axis=0))
    stacked = np.stack(per_seed)  # (3, n, 16, 6)
    ensemble, details = combine(stacked, 0.0)  # VERBATIM v38b/v96b parity
    _ = ensemble
    return np.asarray(details["mean_expected_net_percent"], dtype=np.float64)


def spearman(x, y):
    rx = pd.Series(np.asarray(x, dtype=np.float64)).rank(method="average")
    ry = pd.Series(np.asarray(y, dtype=np.float64)).rank(method="average")
    if float(rx.std(ddof=0)) == 0.0 or float(ry.std(ddof=0)) == 0.0:
        return float("nan")
    return float(rx.corr(ry, method="pearson"))


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


def gap_stats(d):
    d = np.asarray(d, dtype=np.float64)
    return {
        "n_gaps": int(len(d)),
        "mean_abs": float(np.abs(d).mean()),
        "median_abs": float(np.median(np.abs(d))),
        "std_abs": float(np.abs(d).std()),
        "max_abs": float(np.abs(d).max()),
    }


def per_decision_concentration(E, tau=TAU_PCT):
    z = np.asarray(E, dtype=np.float64) / tau
    z -= z.max(axis=1, keepdims=True)
    exp = np.exp(z)
    p = exp / exp.sum(axis=1, keepdims=True)
    logp = np.log(np.clip(p, 1e-300, 1.0))
    H = -(p * logp).sum(axis=1)
    return {
        "H": np.asarray(H, dtype=np.float64),
        "pmax": np.asarray(p.max(axis=1), dtype=np.float64),
        "effN": np.asarray(np.exp(H), dtype=np.float64),
        "cand_std": np.asarray(E.std(axis=1, dtype=np.float64), dtype=np.float64),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Thieu pre-spec config: {CONFIG_PATH} (khong tinh khi chua pre-spec)")
    spec = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de diagnostic cu; dung dir moi")
    out.mkdir(parents=True)

    v96_src = ROOT / spec["inputs"]["v96_source"].split(" (")[0]
    v38_src = ROOT / spec["inputs"]["v38_source"].split(" (")[0]
    if not v96_src.is_dir():
        raise FileNotFoundError(f"v96 download vang mat: {v96_src}")
    if not v38_src.is_dir():
        raise FileNotFoundError(f"v38 download vang mat: {v38_src}")

    ds = ROOT / spec["inputs"]["dataset"].split(" (")[0]
    parent = json.loads((ROOT / spec["inputs"]["parent_plan"].split(" (")[0]).read_text(encoding="utf-8"))
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    decisions_all = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]

    parts = partitions(decisions_all, parent)
    fold_lens = [len(p) for p in parts]
    indices = np.concatenate(parts)
    n = len(indices)
    assert n == int(spec["ensemble"]["n_decisions"]) == 4076, (n, fold_lens)
    part = decisions_all.iloc[indices].reset_index(drop=True)
    # Clock order check: partitions fold0..fold10 chronological == signal_time sorted
    assert bool((part.signal_time.diff().dropna() >= pd.Timedelta(0)).all()), "clock order broken"
    truth = labels_all[indices]  # (4076,16,3)
    fold_of = np.concatenate([np.full(len(p), f, dtype=np.int64) for f, p in enumerate(parts)])

    E38 = load_mapv8(v38_src, parts, "v38")  # (4076,16) % unconditional net
    E96 = load_mapv8(v96_src, parts, "v96")  # (4076,16) % TRADEABLE
    s38 = E38.max(axis=1)
    s96 = E96.max(axis=1)
    top1_38 = E38.argmax(axis=1)  # first-max
    top1_96 = E96.argmax(axis=1)  # first-max

    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    assert cand_grid.shape == (16, 6)
    side_of = np.where(cand_grid[:, 0] == 1, 1, -1)
    side38 = side_of[top1_38]
    side96 = side_of[top1_96]

    # ---- (a) smoothness ----
    z38 = (s38 - s38.mean()) / s38.std()
    z96 = (s96 - s96.mean()) / s96.std()
    d38, d96 = np.diff(s38), np.diff(s96)
    dz38, dz96 = np.diff(z38), np.diff(z96)
    within = np.ones(len(d38), dtype=bool)
    bounds = np.cumsum(fold_lens)[:-1] - 1  # gap index i = giua decision i va i+1
    within[bounds] = False
    smooth_rows = [
        {"model": "v38_SSM", "scale": "raw", **gap_stats(d38)},
        {"model": "v96_Transformer", "scale": "raw", **gap_stats(d96)},
        {"model": "v38_SSM", "scale": "standardized", **gap_stats(dz38)},
        {"model": "v96_Transformer", "scale": "standardized", **gap_stats(dz96)},
        {"model": "v38_SSM", "scale": "raw_within_fold", **gap_stats(d38[within])},
        {"model": "v96_Transformer", "scale": "raw_within_fold", **gap_stats(d96[within])},
        {"model": "v38_SSM", "scale": "standardized_within_fold", **gap_stats(dz38[within])},
        {"model": "v96_Transformer", "scale": "standardized_within_fold", **gap_stats(dz96[within])},
    ]
    pd.DataFrame(smooth_rows).to_csv(out / "smoothness.csv", index=False)
    sfold_rows = []
    for f in range(N_FOLDS):
        idx = np.flatnonzero(fold_of == f)
        g38 = np.abs(np.diff(s38[idx])).mean()
        g96 = np.abs(np.diff(s96[idx])).mean()
        gz38 = np.abs(np.diff(z38[idx])).mean()
        gz96 = np.abs(np.diff(z96[idx])).mean()
        sfold_rows.append({
            "fold": f, "fold_start": str(pd.Timestamp(parent["folds"][f][0]).date()),
            "n": int(len(idx)),
            "v38_mean_abs_raw": float(g38), "v96_mean_abs_raw": float(g96),
            "v38_mean_abs_std": float(gz38), "v96_mean_abs_std": float(gz96),
            "ratio_v96_over_v38_std": float(gz96 / gz38) if gz38 > 0 else None,
        })
    pd.DataFrame(sfold_rows).to_csv(out / "smoothness_by_fold.csv", index=False)

    # ---- (b) rank agreement ----
    rfold_rows = []
    for f in range(N_FOLDS):
        idx = np.flatnonzero(fold_of == f)
        rfold_rows.append({
            "fold": f, "fold_start": str(pd.Timestamp(parent["folds"][f][0]).date()),
            "n": int(len(idx)),
            "decision_spearman_s38_s96": spearman(s38[idx], s96[idx]),
        })
    overall_spear = spearman(s38, s96)
    rfold_rows.append({"fold": "overall", "fold_start": "", "n": int(n),
                       "decision_spearman_s38_s96": overall_spear})
    # within-decision candidate agreement
    per_dec = np.array([spearman(E38[i], E96[i]) for i in range(n)])
    valid_dec = per_dec[~np.isnan(per_dec)]
    for row in rfold_rows:
        f = row["fold"]
        v = per_dec[fold_of == f] if f != "overall" else per_dec
        v = v[~np.isnan(v)]
        row["candidate_spearman_mean"] = float(v.mean()) if len(v) else None
        row["candidate_spearman_median"] = float(np.median(v)) if len(v) else None
        row["candidate_spearman_std"] = float(v.std()) if len(v) else None
        row["candidate_n_valid"] = int(len(v))
    pd.DataFrame(rfold_rows).to_csv(out / "rank_by_fold.csv", index=False)
    # anchor recompute vs truth
    per38 = rank_corr_per_decision(E38, truth[:, :, 0])
    per96 = rank_corr_per_decision(E96, truth[:, :, 0])
    anchor = {
        "v38_rank_corr_mean": float(per38[~np.isnan(per38)].mean()),
        "v38_rank_corr_std": float(per38[~np.isnan(per38)].std()),
        "v38_n_valid": int((~np.isnan(per38)).sum()),
        "v96_rank_corr_mean": float(per96[~np.isnan(per96)].mean()),
        "v96_rank_corr_std": float(per96[~np.isnan(per96)].std()),
        "v96_n_valid": int((~np.isnan(per96)).sum()),
    }

    # ---- past-only descriptors (no fitting) ----
    closes = candles["close"].to_numpy(dtype=np.float64)
    bi = part["bar_index"].to_numpy(dtype=np.int64)
    assert bool(((bi - 8640 >= 0) & (bi < len(closes))).all()), "bar_index window out of range"
    logc = np.log(closes)
    win = 30 * 288
    vols = np.empty(n)
    for i, b in enumerate(bi):
        rets = np.diff(logc[b - win:b])  # strictly before signal_time
        vols[i] = float(np.std(rets) * np.sqrt(365.2425 * 288)) if len(rets) >= 100 else np.nan
    assert bool(np.isfinite(vols).all()), "vol window failed"
    ret24 = closes[bi] / closes[bi - 288] - 1.0
    hours = pd.to_datetime(part["signal_time"]).dt.tz_convert("UTC").dt.hour.to_numpy()
    sess_names = ["s0004", "s0408", "s0812", "s1216", "s1620", "s2024"]
    sess = np.array(sess_names)[np.clip(hours // 4, 0, 5)]
    dow = pd.to_datetime(part["signal_time"]).dt.tz_convert("UTC").dt.dayofweek.to_numpy()
    weekend = np.where(dow >= 5, "weekend", "weekday")
    vol_band = np.where(vols < 0.30, "low", np.where(vols <= 0.60, "mid", "high"))
    trend = np.where(ret24 > 0.0025, "up", np.where(ret24 < -0.0025, "down", "flat"))

    # ---- (c) disagreement pockets ----
    pct38 = pd.Series(s38).rank(method="average").to_numpy() / n
    pct96 = np.asarray(pd.Series(s96).rank(method="average").to_numpy() / n)
    D = np.abs(pct38 - pct96)
    p80 = float(np.quantile(D, 0.80))
    highD = D >= p80
    top1_agree = top1_38 == top1_96
    side_agree = side38 == side96
    buckets = []
    for split_name, labels in (("utc_session", sess), ("weekend", weekend),
                               ("vol_ann_30d", vol_band), ("trend_24h_sign", trend)):
        for key in sorted(set(labels.tolist())):
            m = labels == key
            buckets.append({
                "split": split_name, "bucket": key, "n": int(m.sum()),
                "mean_D": float(D[m].mean()),
                "share_highD": float(highD[m].mean()),
                "top1_agree_rate": float(top1_agree[m].mean()),
                "side_agree_rate": float(side_agree[m].mean()),
            })
    for split_name, labels in (("side_v38", np.where(side38 == 1, "LONG", "SHORT")),
                               ("side_v96", np.where(side96 == 1, "LONG", "SHORT")),
                               ("side_agree", np.where(side_agree, "agree", "disagree")),
                               ("top1_agree", np.where(top1_agree, "agree", "disagree"))):
        for key in sorted(set(labels.tolist())):
            m = labels == key
            buckets.append({
                "split": split_name, "bucket": key, "n": int(m.sum()),
                "mean_D": float(D[m].mean()),
                "share_highD": float(highD[m].mean()),
                "top1_agree_rate": float(top1_agree[m].mean()),
                "side_agree_rate": float(side_agree[m].mean()),
            })
    buckets.append({"split": "overall", "bucket": "all", "n": int(n),
                    "mean_D": float(D.mean()), "share_highD": float(highD.mean()),
                    "top1_agree_rate": float(top1_agree.mean()),
                    "side_agree_rate": float(side_agree.mean())})
    pd.DataFrame(buckets).to_csv(out / "disagreement_by_bucket.csv", index=False)

    # ---- (d) top-decile ----
    def topdec(score, top1, tag):
        order = np.argsort(-np.asarray(score, dtype=np.float64), kind="stable")[:TOPK]
        k = np.asarray(top1)[order]
        rn = truth[order, k, 0]
        rf = truth[order, k, 1]
        rp = truth[order, k, 2]
        filled = rf == 1
        return {
            "model": tag, "n": int(TOPK),
            "score_cut": float(np.asarray(score)[order].min()),
            "fill_rate": float(rf.mean()),
            "pos_given_fill": float(rp[filled].mean()) if filled.any() else None,
            "p_net_positive": float((rn > 0).mean()),
            "obs_net_mean": float(rn.mean()),
            "obs_net_filled_mean": float(rn[filled].mean()) if filled.any() else None,
        }, set(order.tolist())

    row38, set38 = topdec(s38, top1_38, "v38_SSM")
    row96, set96 = topdec(s96, top1_96, "v96_Transformer")
    inter = set38 & set96
    only38 = np.array(sorted(set38 - set96))
    only96 = np.array(sorted(set96 - set38))
    both = np.array(sorted(inter))

    def realized(idx, top1):
        k = np.asarray(top1)[idx]
        rn = truth[idx, k, 0]
        rf = truth[idx, k, 1]
        return float(rn.mean()) if len(idx) else None, float(rf.mean()) if len(idx) else None

    m_both38, f_both = realized(both, top1_38)
    m_o38, f_o38 = realized(only38, top1_38)
    m_o96, f_o96 = realized(only96, top1_96)
    top_rows = [row38, row96, {
        "model": "overlap_n", "n": int(len(both)),
        "score_cut": None, "fill_rate": f_both, "pos_given_fill": None,
        "p_net_positive": None, "obs_net_mean": m_both38,
        "obs_net_filled_mean": None,
    }, {
        "model": "v38_only", "n": int(len(only38)),
        "score_cut": None, "fill_rate": f_o38, "pos_given_fill": None,
        "p_net_positive": None, "obs_net_mean": m_o38,
        "obs_net_filled_mean": None,
    }, {
        "model": "v96_only", "n": int(len(only96)),
        "score_cut": None, "fill_rate": f_o96, "pos_given_fill": None,
        "p_net_positive": None, "obs_net_mean": m_o96,
        "obs_net_filled_mean": None,
    }]
    pd.DataFrame(top_rows).to_csv(out / "topdecile.csv", index=False)

    # ---- (e) entropy / concentration (attention-specific) ----
    c38 = per_decision_concentration(E38)
    c96 = per_decision_concentration(E96)
    ent = pd.DataFrame({
        "decision_idx": np.arange(n), "fold": fold_of,
        "s38": s38, "s96": s96,
        "H38": c38["H"], "H96": c96["H"],
        "pmax38": c38["pmax"], "pmax96": c96["pmax"],
        "effN38": c38["effN"], "effN96": c96["effN"],
        "cand_std38": c38["cand_std"], "cand_std96": c96["cand_std"],
    })
    ent.to_csv(out / "entropy.csv", index=False)
    efold_rows = []
    for f in range(N_FOLDS):
        m = fold_of == f
        efold_rows.append({
            "fold": f, "fold_start": str(pd.Timestamp(parent["folds"][f][0]).date()),
            "n": int(m.sum()),
            "H38_mean": float(c38["H"][m].mean()), "H96_mean": float(c96["H"][m].mean()),
            "pmax38_mean": float(c38["pmax"][m].mean()), "pmax96_mean": float(c96["pmax"][m].mean()),
            "effN38_mean": float(c38["effN"][m].mean()), "effN96_mean": float(c96["effN"][m].mean()),
            "cand_std38_mean": float(c38["cand_std"][m].mean()),
            "cand_std96_mean": float(c96["cand_std"][m].mean()),
        })
    efold_rows.append({
        "fold": "overall", "fold_start": "", "n": int(n),
        "H38_mean": float(c38["H"].mean()), "H96_mean": float(c96["H"].mean()),
        "pmax38_mean": float(c38["pmax"].mean()), "pmax96_mean": float(c96["pmax"].mean()),
        "effN38_mean": float(c38["effN"].mean()), "effN96_mean": float(c96["effN"].mean()),
        "cand_std38_mean": float(c38["cand_std"].mean()),
        "cand_std96_mean": float(c96["cand_std"].mean()),
    })
    pd.DataFrame(efold_rows).to_csv(out / "entropy_by_fold.csv", index=False)
    entropy_overall = {
        "tau_percent": TAU_PCT, "log16_nats": LOG16,
        "H38": {"mean": float(c38["H"].mean()), "median": float(np.median(c38["H"])),
                "std": float(c38["H"].std())},
        "H96": {"mean": float(c96["H"].mean()), "median": float(np.median(c96["H"])),
                "std": float(c96["H"].std())},
        "pmax38": {"mean": float(c38["pmax"].mean()), "median": float(np.median(c38["pmax"]))},
        "pmax96": {"mean": float(c96["pmax"].mean()), "median": float(np.median(c96["pmax"]))},
        "effN38_mean": float(c38["effN"].mean()), "effN96_mean": float(c96["effN"].mean()),
        "cand_std38": {"mean": float(c38["cand_std"].mean())},
        "cand_std96": {"mean": float(c96["cand_std"].mean())},
        "delta_H96_minus_H38_mean": float((c96["H"] - c38["H"]).mean()),
        "delta_pmax96_minus_pmax38_mean": float((c96["pmax"] - c38["pmax"]).mean()),
        "s38_across_std": float(s38.std()), "s96_across_std": float(s96.std()),
        "s38_across_mean": float(s38.mean()), "s96_across_mean": float(s96.mean()),
    }

    summary = {
        "experiment": "opencode-v127-v96scorediag",
        "prespec": str(CONFIG_PATH),
        "causality": spec["causality"],
        "inputs": {"v96_source": str(v96_src), "v38_source": str(v38_src),
                   "dataset": str(ds), "n_decisions": int(n), "fold_lens": fold_lens},
        "anchor_expected": spec["inputs"]["rank_anchors"],
        "anchor_recomputed": anchor,
        "smoothness_overall": {r["model"] + "|" + r["scale"]: {
            "mean_abs": r["mean_abs"], "median_abs": r["median_abs"],
            "std_abs": r["std_abs"], "max_abs": r["max_abs"]} for r in smooth_rows},
        "decision_spearman_overall": overall_spear,
        "candidate_spearman_overall": {
            "mean": float(valid_dec.mean()), "median": float(np.median(valid_dec)),
            "std": float(valid_dec.std()), "n_valid": int(len(valid_dec))},
        "disagreement_overall": {"mean_D": float(D.mean()), "p80_D": p80,
                                 "top1_agree_rate": float(top1_agree.mean()),
                                 "side_agree_rate": float(side_agree.mean())},
        "topdecile": {"v38": row38, "v96": row96,
                      "overlap_n": int(len(both)),
                      "overlap_obs_net_mean_v38cand": m_both38,
                      "v38_only_obs_net_mean": m_o38, "v96_only_obs_net_mean": m_o96},
        "entropy_overall": entropy_overall,
        "mechanism": None,
        "design_implication": None,
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    digests = {f.name: sha256(f) for f in sorted(out.iterdir()) if f.is_file()}
    summary["output_sha256"] = digests
    summary["input_sha256"] = {
        "config": sha256(CONFIG_PATH),
        "dataset_config": sha256(ds / "config.json"),
        "parent_plan": sha256(ROOT / spec["inputs"]["parent_plan"].split(" (")[0]),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(json.dumps({"state": "done", "out": str(out), "n": n,
                      "anchor_recomputed": anchor,
                      "decision_spearman": round(overall_spear, 4),
                      "entropy": {k: round(v, 4) if isinstance(v, float) else v
                                  for k, v in entropy_overall.items()
                                  if isinstance(v, float)}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
