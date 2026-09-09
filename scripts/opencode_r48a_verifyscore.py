"""A2-ARCH v133 VERIFY: doc lap tinh lai neo diagnostic v127 (analysis only).

Tu frozen predictions v38/v96 + labels examples.npz, bang code TU VIET
(KHONG import driver R opencode_r47a_v96scorediag, KHONG import combine):
  (a) rank-correlation tong the v38/v96 (per-decision Spearman, dinh nghia v100),
  (b) top-decile realized means 3 nhom v38-only/v96-only/overlap,
  (c) entropy trung binh tau=1.0%%.
Pre-spec: configs/opencode_v133_verifyscore.json (script RAISE neu thieu).
Ghi artifacts/research/opencode_v133_verifyscore/ (moi, khong ghi de).
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRESPEC = ROOT / "configs/opencode_v133_verifyscore.json"
OUT_DEFAULT = ROOT / "artifacts/research/opencode_v133_verifyscore"

SEED_LIST = [1729, 1730, 1731]
N_FOLD = 11
TOPK = 408


def _sha(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def _sigmoid_clip(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(z, dtype=np.float64), -40.0, 40.0)))


def _fold_partitions(decisions: pd.DataFrame, plan: dict):
    cutoff = pd.Timestamp(plan["complete_evaluation_until"])
    blocks = []
    for start, stop in plan["folds"]:
        keep = (
            (decisions["signal_time"] >= pd.Timestamp(start))
            & (decisions["signal_time"] < pd.Timestamp(stop))
            & (decisions["label_end"] < cutoff)
        ).to_numpy()
        blocks.append(np.flatnonzero(keep))
    return blocks


def _ensemble_mean_net(source: Path, blocks, tag: str) -> np.ndarray:
    """E[n,16] = mean_seed(ch0 * sigmoid(ch4)); tu viet, khong dung combine."""
    per_seed_mats = []
    for seed in SEED_LIST:
        fold_mats = []
        for f in range(N_FOLD):
            fp = source / f"seed{seed}/temporal_neural/fold_{f}/predictions.npy"
            cube = np.load(fp, allow_pickle=False)
            want = len(blocks[f])
            if cube.shape != (want, 16, 6) or not np.isfinite(cube).all():
                raise ValueError(f"{tag} sai shape/gia tri: {fp} {cube.shape}")
            fold_mats.append(cube)
        joined = np.concatenate(fold_mats, axis=0)  # (n,16,6)
        per_seed_mats.append(joined)
    stack = np.stack(per_seed_mats, axis=0)  # (3,n,16,6)
    net_per_seed = stack[..., 0] * _sigmoid_clip(stack[..., 4])
    return np.asarray(net_per_seed.mean(axis=0), dtype=np.float64)


def _per_decision_rankcorr(pred: np.ndarray, truth_ch0: np.ndarray) -> np.ndarray:
    """Spearman per-decision (dinh nghia v100): Pearson tren average-rank.

    rank = pandas rank(axis=1) mac dinh method='average', ascending=True;
    tru mean hang; den>0 moi hop le; overall = mean tren hop le.
    """
    pr = pd.DataFrame(np.asarray(pred, dtype=np.float64)).rank(axis=1).to_numpy(dtype=np.float64)
    tr = pd.DataFrame(np.asarray(truth_ch0, dtype=np.float64)).rank(axis=1).to_numpy(dtype=np.float64)
    pr -= pr.mean(axis=1, keepdims=True)
    tr -= tr.mean(axis=1, keepdims=True)
    denom = np.sqrt((pr * pr).sum(axis=1) * (tr * tr).sum(axis=1))
    ok = denom > 0
    out = np.full((pred.shape[0],), np.nan, dtype=np.float64)
    out[ok] = (pr * tr).sum(axis=1)[ok] / denom[ok]
    return out


def _entropy_rows(mat: np.ndarray, tau: float):
    z = np.asarray(mat, dtype=np.float64) / tau
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    p = e / e.sum(axis=1, keepdims=True)
    h = -(p * np.log(np.clip(p, 1e-300, 1.0))).sum(axis=1)
    return (
        np.asarray(h, dtype=np.float64),
        np.asarray(p.max(axis=1), dtype=np.float64),
        np.asarray(np.exp(h), dtype=np.float64),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    if not PRESPEC.exists():
        raise FileNotFoundError(f"Thieu pre-spec: {PRESPEC} (khong tinh khi chua pre-spec)")
    spec = json.loads(PRESPEC.read_text(encoding="utf-8"))
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de ket qua cu; dung dir moi")

    src38 = ROOT / str(spec["inputs"]["v38_source"]).split(" (")[0]
    src96 = ROOT / str(spec["inputs"]["v96_source"]).split(" (")[0]
    if not src38.is_dir():
        raise FileNotFoundError(f"v38 download vang mat: {src38} -> STOP")
    if not src96.is_dir():
        raise FileNotFoundError(f"v96 download vang mat: {src96} -> STOP")

    ds = ROOT / str(spec["inputs"]["dataset"]).split(" (")[0]
    plan = json.loads((ROOT / str(spec["inputs"]["parent_plan"]).split(" (")[0]).read_text(encoding="utf-8"))
    decisions = pd.read_parquet(ds / "decisions.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as zf:
        labels_full = zf["labels"]

    blocks = _fold_partitions(decisions, plan)
    order = np.concatenate(blocks)
    n = int(len(order))
    if n != int(spec["inputs"]["n_decisions"]):
        raise ValueError(f"n_decisions={n}, ky vong {spec['inputs']['n_decisions']}")
    # thu tu clock: fold0..fold10 phai tang dan theo signal_time
    st = decisions.iloc[order].reset_index(drop=True)["signal_time"]
    if not bool((st.diff().dropna() >= pd.Timedelta(0)).all()):
        raise ValueError("clock order broken")
    truth = labels_full[order]  # (n,16,3)
    t0 = np.asarray(truth[:, :, 0], dtype=np.float64)

    mat38 = _ensemble_mean_net(src38, blocks, "v38")
    mat96 = _ensemble_mean_net(src96, blocks, "v96")
    s38 = mat38.max(axis=1)
    s96 = mat96.max(axis=1)
    best38 = mat38.argmax(axis=1)  # first-max
    best96 = mat96.argmax(axis=1)

    # ---- (a) rank ----
    r38 = _per_decision_rankcorr(mat38, t0)
    r96 = _per_decision_rankcorr(mat96, t0)
    v38 = r38[~np.isnan(r38)]
    v96 = r96[~np.isnan(r96)]
    a38_mean, a96_mean = float(v38.mean()), float(v96.mean())
    a38_std, a96_std = float(v38.std()), float(v96.std())
    a38_n, a96_n = int(len(v38)), int(len(v96))

    # ---- (b) top-decile rieng per model ----
    o38 = np.argsort(-np.asarray(s38, dtype=np.float64), kind="stable")[:TOPK]
    o96 = np.argsort(-np.asarray(s96, dtype=np.float64), kind="stable")[:TOPK]
    k38 = np.asarray(best38)[o38]
    k96 = np.asarray(best96)[o96]
    rn38 = truth[o38, k38, 0]
    rn96 = truth[o96, k96, 0]
    set38, set96 = set(o38.tolist()), set(o96.tolist())
    common = np.array(sorted(set38 & set96), dtype=np.int64)
    solo38 = np.array(sorted(set38 - set96), dtype=np.int64)
    solo96 = np.array(sorted(set96 - set38), dtype=np.int64)

    def _gmean(idx: np.ndarray, best: np.ndarray) -> float | None:
        if len(idx) == 0:
            return None
        kk = np.asarray(best)[idx]
        return float(np.asarray(truth[idx, kk, 0], dtype=np.float64).mean())

    m_solo38 = _gmean(solo38, best38)
    m_solo96 = _gmean(solo96, best96)
    m_common = _gmean(common, best38)

    # ---- (c) entropy tau=1.0 ----
    tau = float(spec["metrics"]["c_entropy"]["tau_percent"])
    h38, p38, e38 = _entropy_rows(mat38, tau)
    h96, p96, e96 = _entropy_rows(mat96, tau)
    H38, H96 = float(h38.mean()), float(h96.mean())
    dH = float((h96 - h38).mean())

    # ---- PASS ----
    tol_r = float(spec["metrics"]["a_rank"]["tol_rank"])
    tol_m = float(spec["metrics"]["b_topdecile"]["tol_mean"])
    tol_h = float(spec["metrics"]["c_entropy"]["tol_mean"])
    anc = spec["metrics"]
    d_r38 = abs(a38_mean - float(anc["a_rank"]["v38_anchor_mean"]))
    d_r96 = abs(a96_mean - float(anc["a_rank"]["v96_anchor_mean"]))
    d_b38 = abs(m_solo38 - float(anc["b_topdecile"]["anchor_v38_only_mean"]))
    d_b96 = abs(m_solo96 - float(anc["b_topdecile"]["anchor_v96_only_mean"]))
    d_ov = abs(m_common - float(anc["b_topdecile"]["anchor_overlap_mean_v38cand"]))
    d_H38 = abs(H38 - float(anc["c_entropy"]["anchor_H38_mean"]))
    d_H96 = abs(H96 - float(anc["c_entropy"]["anchor_H96_mean"]))
    pass_rank = bool(d_r38 <= tol_r and d_r96 <= tol_r)
    pass_n = bool(a38_n == 4075 and a96_n == 4075)
    pass_counts = bool(len(common) == 147 and len(solo38) == 261 and len(solo96) == 261)
    pass_means = bool(d_b38 <= tol_m and d_b96 <= tol_m and d_ov <= tol_m)
    pass_ent = bool(d_H38 <= tol_h and d_H96 <= tol_h)
    overall = bool(pass_rank and pass_n and pass_counts and pass_means and pass_ent)

    out.mkdir(parents=True)
    pd.DataFrame([
        {"model": "v38", "rank_corr_mean": a38_mean, "rank_corr_std": a38_std,
         "n_valid": a38_n, "anchor_mean": float(anc["a_rank"]["v38_anchor_mean"]), "abs_delta": d_r38},
        {"model": "v96", "rank_corr_mean": a96_mean, "rank_corr_std": a96_std,
         "n_valid": a96_n, "anchor_mean": float(anc["a_rank"]["v96_anchor_mean"]), "abs_delta": d_r96},
    ]).to_csv(out / "rank_recompute.csv", index=False)
    pd.DataFrame([
        {"group": "v38_top408", "n": int(len(o38)), "obs_net_mean": float(rn38.mean()),
         "anchor": float(anc["b_topdecile"]["anchor_v38_obs_net_mean"])},
        {"group": "v96_top408", "n": int(len(o96)), "obs_net_mean": float(rn96.mean()),
         "anchor": float(anc["b_topdecile"]["anchor_v96_obs_net_mean"])},
        {"group": "overlap", "n": int(len(common)), "obs_net_mean": m_common,
         "anchor": float(anc["b_topdecile"]["anchor_overlap_mean_v38cand"])},
        {"group": "v38_only", "n": int(len(solo38)), "obs_net_mean": m_solo38,
         "anchor": float(anc["b_topdecile"]["anchor_v38_only_mean"])},
        {"group": "v96_only", "n": int(len(solo96)), "obs_net_mean": m_solo96,
         "anchor": float(anc["b_topdecile"]["anchor_v96_only_mean"])},
    ]).to_csv(out / "topdecile_groups.csv", index=False)
    pd.DataFrame([
        {"model": "v38", "H_mean": H38, "pmax_mean": float(p38.mean()), "effN_mean": float(e38.mean()),
         "anchor_H": float(anc["c_entropy"]["anchor_H38_mean"]), "abs_delta_H": d_H38},
        {"model": "v96", "H_mean": H96, "pmax_mean": float(p96.mean()), "effN_mean": float(e96.mean()),
         "anchor_H": float(anc["c_entropy"]["anchor_H96_mean"]), "abs_delta_H": d_H96},
        {"model": "delta_H96_minus_H38", "H_mean": dH, "pmax_mean": float((p96 - p38).mean()),
         "effN_mean": float((e96 - e38).mean()),
         "anchor_H": float(anc["c_entropy"]["anchor_delta_H96_minus_H38"]), "abs_delta_H": abs(dH - float(anc["c_entropy"]["anchor_delta_H96_minus_H38"]))},
    ]).to_csv(out / "entropy_compare.csv", index=False)

    summary = {
        "experiment": "opencode-v133-verifyscore",
        "prespec": str(PRESPEC),
        "spearman_definition": spec["spearman_definition"],
        "ensemble_independent": spec["ensemble_independent"],
        "inputs": {"v38_source": str(src38), "v96_source": str(src96),
                   "dataset": str(ds), "n_decisions": n,
                   "fold_lens": [int(len(b)) for b in blocks]},
        "recomputed": {
            "v38_rank_corr_mean": a38_mean, "v38_rank_corr_std": a38_std, "v38_n_valid": a38_n,
            "v96_rank_corr_mean": a96_mean, "v96_rank_corr_std": a96_std, "v96_n_valid": a96_n,
            "v38_score_cut": float(np.asarray(s38)[o38].min()),
            "v96_score_cut": float(np.asarray(s96)[o96].min()),
            "v38_obs_net_mean": float(rn38.mean()), "v96_obs_net_mean": float(rn96.mean()),
            "overlap_n": int(len(common)), "overlap_obs_net_mean_v38cand": m_common,
            "v38_only_n": int(len(solo38)), "v38_only_obs_net_mean": m_solo38,
            "v96_only_n": int(len(solo96)), "v96_only_obs_net_mean": m_solo96,
            "H38_mean": H38, "H96_mean": H96, "delta_H96_minus_H38": dH,
            "pmax38_mean": float(p38.mean()), "pmax96_mean": float(p96.mean()),
        },
        "deltas_vs_R": {"d_r38": d_r38, "d_r96": d_r96, "d_v38only": d_b38,
                        "d_v96only": d_b96, "d_overlap": d_ov, "d_H38": d_H38, "d_H96": d_H96},
        "pass": {"rank_tol_1e6": pass_rank, "n_valid_exact": pass_n, "counts_exact": pass_counts,
                 "group_means_tol_1e4": pass_means, "entropy_tol_1e4": pass_ent, "overall": overall},
        "verdict": "PASS - khop R trong dung sai" if overall else "MISMATCH - can dieu tra",
        "causality": spec["causality"],
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"state": "done", "overall_pass": overall,
                      "d_r38": d_r38, "d_r96": d_r96, "d_v38only": d_b38,
                      "d_v96only": d_b96, "d_overlap": d_ov,
                      "d_H38": d_H38, "d_H96": d_H96}, ensure_ascii=False))


if __name__ == "__main__":
    main()
