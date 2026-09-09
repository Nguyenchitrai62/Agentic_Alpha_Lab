"""R-DIAGNOSTIC v100: TAI SAO multitask GIUP ranking? (analysis only, no training).

So sanh frozen predictions tren cung 4076 decisions:
  - v38 multitask (value 2.0 + pairwise-ranking 0.5 + aux + coverage-hinge):
    artifacts/kaggle/v38_rankloss_download/rankloss-training (33 x (n,16,6) map-v8)
  - v55c rank-only ListNet (bo value/aux/coverage-hinge, cung encoder ~0.6M):
    artifacts/kaggle/v55c_rankonly_download/rankonly-training (33 x (n,16) logits)

Pre-spec: configs/opencode_v100_scorediag.json (metrics + splits) — script RAISE
neu config thieu (khong tinh khi chua pre-spec). Chi doc + thong ke mo ta +
splits past-only; KHONG fit, KHONG train, KHONG cloud, KHONG live.
Ghi artifacts/research/opencode_v100_scorediag/ (moi, khong ghi de).
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

CONFIG_PATH = ROOT / "configs/opencode_v100_scorediag.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v100_scorediag"


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


def load_v38(source, parts):
    per_seed = []
    for seed in SEEDS:
        folds = []
        for fold in range(N_FOLDS):
            path = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            arr = np.load(path, allow_pickle=False)
            if arr.shape != (len(parts[fold]), 16, 6) or not np.isfinite(arr).all():
                raise ValueError(f"v38 shape/values mismatch: {path} {arr.shape}")
            folds.append(arr)
        per_seed.append(np.concatenate(folds, axis=0))
    stacked = np.stack(per_seed)  # (3, n, 16, 6)
    ensemble, details = combine(stacked, 0.0)  # VERBATIM v38b parity
    _ = ensemble
    return np.asarray(details["mean_expected_net_percent"], dtype=np.float64)


def load_v55c(source, parts):
    per_seed = []
    for seed in SEEDS:
        folds = []
        for fold in range(N_FOLDS):
            path = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            arr = np.load(path, allow_pickle=False)
            if arr.shape != (len(parts[fold]), 16) or not np.isfinite(arr).all():
                raise ValueError(f"v55c shape/values mismatch: {path} {arr.shape}")
            folds.append(arr)
        per_seed.append(np.concatenate(folds, axis=0))
    return np.stack(per_seed).mean(axis=0).astype(np.float64)  # (n,16) VERBATIM v55d parity


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -40, 40)))


def margins_of(logits):
    top1 = np.asarray(logits).argmax(axis=1)  # first-max deterministic
    order = np.argsort(-np.asarray(logits, dtype=np.float64), axis=1, kind="stable")
    second = order[:, 1]
    mg = logits[np.arange(len(logits)), top1] - logits[np.arange(len(logits)), second]
    return top1.astype(np.int64), np.asarray(mg, dtype=np.float64)


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

    v38_src = ROOT / spec["inputs"]["v38_source"].split(" (")[0]
    v55c_src = ROOT / spec["inputs"]["v55c_source"].split(" (")[0]
    if not v38_src.is_dir():
        raise FileNotFoundError(f"v38 download vang mat: {v38_src} (fallback: v38b_replay artifacts)")
    if not v55c_src.is_dir():
        raise FileNotFoundError(f"v55c download vang mat: {v55c_src}")

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

    E38 = load_v38(v38_src, parts)      # (4076,16) expected net %
    L55 = load_v55c(v55c_src, parts)    # (4076,16) rank logits
    s38 = E38.max(axis=1)
    top1_38 = E38.argmax(axis=1)  # first-max
    top1_55, m55 = margins_of(L55)

    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    assert cand_grid.shape == (16, 6)
    side_of = np.where(cand_grid[:, 0] == 1, 1, -1)
    side38 = side_of[top1_38]
    side55 = side_of[top1_55]

    # ---- (a) smoothness / Lipschitz proxy ----
    z38 = (s38 - s38.mean()) / s38.std()
    z55 = (m55 - m55.mean()) / m55.std()
    d38, d55 = np.diff(s38), np.diff(m55)
    dz38, dz55 = np.diff(z38), np.diff(z55)
    within = np.ones(len(d38), dtype=bool)
    bounds = np.cumsum(fold_lens)[:-1] - 1  # gap index i = giua decision i va i+1
    within[bounds] = False
    smooth_rows = [
        {"model": "v38_multitask", "scale": "raw", **gap_stats(d38)},
        {"model": "v55c_rankonly", "scale": "raw", **gap_stats(d55)},
        {"model": "v38_multitask", "scale": "standardized", **gap_stats(dz38)},
        {"model": "v55c_rankonly", "scale": "standardized", **gap_stats(dz55)},
        {"model": "v38_multitask", "scale": "raw_within_fold", **gap_stats(d38[within])},
        {"model": "v55c_rankonly", "scale": "raw_within_fold", **gap_stats(d55[within])},
        {"model": "v38_multitask", "scale": "standardized_within_fold", **gap_stats(dz38[within])},
        {"model": "v55c_rankonly", "scale": "standardized_within_fold", **gap_stats(dz55[within])},
    ]
    pd.DataFrame(smooth_rows).to_csv(out / "smoothness.csv", index=False)
    sfold_rows = []
    for f in range(N_FOLDS):
        idx = np.flatnonzero(fold_of == f)
        g38 = np.abs(np.diff(s38[idx])).mean()
        g55 = np.abs(np.diff(m55[idx])).mean()
        gz38 = np.abs(np.diff(z38[idx])).mean()
        gz55 = np.abs(np.diff(z55[idx])).mean()
        sfold_rows.append({
            "fold": f, "fold_start": str(pd.Timestamp(parent["folds"][f][0]).date()),
            "n": int(len(idx)),
            "v38_mean_abs_raw": float(g38), "v55c_mean_abs_raw": float(g55),
            "v38_mean_abs_std": float(gz38), "v55c_mean_abs_std": float(gz55),
            "ratio_v55c_over_v38_std": float(gz55 / gz38) if gz38 > 0 else None,
        })
    pd.DataFrame(sfold_rows).to_csv(out / "smoothness_by_fold.csv", index=False)

    # ---- (b) rank agreement ----
    rfold_rows = []
    for f in range(N_FOLDS):
        idx = np.flatnonzero(fold_of == f)
        rfold_rows.append({
            "fold": f, "fold_start": str(pd.Timestamp(parent["folds"][f][0]).date()),
            "n": int(len(idx)),
            "decision_spearman_s38_m55": spearman(s38[idx], m55[idx]),
        })
    overall_spear = spearman(s38, m55)
    rfold_rows.append({"fold": "overall", "fold_start": "", "n": int(n),
                       "decision_spearman_s38_m55": overall_spear})
    # within-decision candidate agreement
    per_dec = np.array([spearman(E38[i], L55[i]) for i in range(n)])
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
    per55 = rank_corr_per_decision(L55, truth[:, :, 0])
    anchor = {
        "v38_rank_corr_mean": float(per38[~np.isnan(per38)].mean()),
        "v38_rank_corr_std": float(per38[~np.isnan(per38)].std()),
        "v38_n_valid": int((~np.isnan(per38)).sum()),
        "v55c_rank_corr_mean": float(per55[~np.isnan(per55)].mean()),
        "v55c_rank_corr_std": float(per55[~np.isnan(per55)].std()),
        "v55c_n_valid": int((~np.isnan(per55)).sum()),
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
    pct55 = np.asarray(pd.Series(m55).rank(method="average").to_numpy() / n)
    D = np.abs(pct38 - pct55)
    p80 = float(np.quantile(D, 0.80))
    highD = D >= p80
    top1_agree = top1_38 == top1_55
    side_agree = side38 == side55
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
                               ("side_v55c", np.where(side55 == 1, "LONG", "SHORT")),
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

    row38, set38 = topdec(s38, top1_38, "v38_multitask")
    row55, set55 = topdec(m55, top1_55, "v55c_rankonly")
    inter = set38 & set55
    only38 = np.array(sorted(set38 - set55))
    only55 = np.array(sorted(set55 - set38))
    both = np.array(sorted(inter))

    def realized(idx, top1):
        k = np.asarray(top1)[idx]
        rn = truth[idx, k, 0]
        rf = truth[idx, k, 1]
        return float(rn.mean()) if len(idx) else None, float(rf.mean()) if len(idx) else None

    m_both38, f_both = realized(both, top1_38)
    m_o38, f_o38 = realized(only38, top1_38)
    m_o55, f_o55 = realized(only55, top1_55)
    top_rows = [row38, row55, {
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
        "model": "v55c_only", "n": int(len(only55)),
        "score_cut": None, "fill_rate": f_o55, "pos_given_fill": None,
        "p_net_positive": None, "obs_net_mean": m_o55,
        "obs_net_filled_mean": None,
    }]
    pd.DataFrame(top_rows).to_csv(out / "topdecile.csv", index=False)

    summary = {
        "experiment": "opencode-v100-scorediag",
        "prespec": str(CONFIG_PATH),
        "causality": spec["causality"],
        "inputs": {"v38_source": str(v38_src), "v55c_source": str(v55c_src),
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
        "topdecile": {"v38": row38, "v55c": row55,
                      "overlap_n": int(len(both)),
                      "overlap_obs_net_mean_v38cand": m_both38,
                      "v38_only_obs_net_mean": m_o38, "v55c_only_obs_net_mean": m_o55},
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
                      "decision_spearman": round(overall_spear, 4)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
