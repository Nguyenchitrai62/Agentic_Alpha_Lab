"""R-DIAGNOSTIC v101: distillation targets tu v38-ensemble (targets only, NO training).

(1) Ensemble-mean 33 v38 prediction blocks (same combine as audit v38b).
(2) PER-FOLD temperature scaling fit tren validation-qua-khu ONLY
    (folds < f; fold 0 fallback tau=1.0; NLL vs oracle argmax ch0) — causal, no test peek.
(3) Ghi soft-targets (n,16) float32 + per-fold tau + teacher-vs-hard diagnostic.
(4) Student-training spec nam trong config (KHONG thuc thi o day).

Pre-spec: configs/opencode_v101_distill.json — script RAISE neu thieu config.
Ghi artifacts/research/opencode_v101_distill/ (moi, khong ghi de). KHONG student.
"""
import torch  # noqa: F401  (import truoc pandas: DLL load-order tren Windows host)
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

SEEDS = [1729, 1730, 1731]
N_FOLDS = 11

CONFIG_PATH = ROOT / "configs/opencode_v101_distill.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v101_distill"


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


def stable_softmax(logits):
    z = np.asarray(logits, dtype=np.float64)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll_vs_oracle(E, oracle, tau):
    p = stable_softmax(E / tau)
    return float(-np.log(np.clip(p[np.arange(len(E)), oracle], 1e-12, 1.0)).mean())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Thieu pre-spec config: {CONFIG_PATH} (khong tinh khi chua pre-spec)")
    spec = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de distill cu; dung dir moi")
    out.mkdir(parents=True)

    v38_src = ROOT / spec["inputs"]["v38_source"].split(" (")[0]
    if not v38_src.is_dir():
        raise FileNotFoundError(f"v38 download vang mat: {v38_src}")
    policy_ref = ROOT / spec["inputs"]["v38b_policy_ref"].split(" (")[0]
    if not policy_ref.is_file():
        raise FileNotFoundError(f"v38b policy ref vang mat: {policy_ref}")
    ds = ROOT / spec["inputs"]["labels"].split(" (")[0]
    ds = ds.parent  # thu muc dataset
    parent = json.loads((ROOT / spec["inputs"]["parent_plan"].split(" (")[0]).read_text(encoding="utf-8"))
    decisions_all = pd.read_parquet(ds / "decisions.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]
    assert labels_all.shape == (len(decisions_all), 16, 3) and np.isfinite(labels_all).all()

    parts = partitions(decisions_all, parent)
    fold_lens = [len(p) for p in parts]
    indices = np.concatenate(parts)
    n = len(indices)
    assert n == int(spec["ensemble"]["n_decisions"]) == 4076, (n, fold_lens)
    assert bool((decisions_all.iloc[indices].reset_index(drop=True)
                 .signal_time.diff().dropna() >= pd.Timedelta(0)).all()), "clock order broken"
    truth = labels_all[indices].astype(np.float64)  # (4076,16,3)
    fold_of = np.concatenate([np.full(len(p), f, dtype=np.int64) for f, p in enumerate(parts)])

    E38 = load_v38(v38_src, parts)  # (4076,16) expected net %
    oracle = truth[:, :, 0].argmax(axis=1)  # first-max deterministic
    teacher_top1 = E38.argmax(axis=1)  # first-max deterministic

    # ---- (2) per-fold temperature fit tren qua-khu ONLY ----
    grid = [float(t) for t in spec["temperature"]["grid"]]
    fallback_tau = 1.0
    tau_per_fold, tau_rows = [], []
    for f in range(N_FOLDS):
        past = np.flatnonzero(fold_of < f)
        if len(past) == 0:
            tau, fb, nlls, conf, acc = fallback_tau, True, None, None, None
        else:
            nlls = {str(t): nll_vs_oracle(E38[past], oracle[past], t) for t in grid}
            tau = min(grid, key=lambda t: (nlls[str(t)], grid.index(t)))  # first-min
            fb = False
            p = stable_softmax(E38[past] / tau)
            conf = float(p.max(axis=1).mean())
            acc = float((E38[past].argmax(axis=1) == oracle[past]).mean())
        tau_per_fold.append(float(tau))
        tau_rows.append({"fold": int(f), "tau": float(tau), "n_val": int(len(past)),
                         "fallback": bool(fb), "nll_per_tau": nlls,
                         "top1_conf_mean_val": conf, "top1_accuracy_val": acc,
                         "cal_gap_val": (abs(conf - acc) if conf is not None else None)})
    tau_per_row = np.array([tau_per_fold[f] for f in fold_of], dtype=np.float64)

    # ---- (3a) soft targets ----
    soft = stable_softmax(E38 / tau_per_row[:, None])
    assert bool(np.isfinite(soft).all())
    np.testing.assert_allclose(soft.sum(axis=1), np.ones(n), rtol=0, atol=1e-5)
    np.savez_compressed(out / "soft_targets.npz",
                        soft_targets=soft.astype(np.float32),
                        teacher_expected_net=E38.astype(np.float32),
                        fold_of=fold_of.astype(np.int64),
                        indices=indices.astype(np.int64),
                        tau_per_row=tau_per_row,
                        oracle_top1=oracle.astype(np.int64))

    # ---- (3b) teacher-vs-hard diagnostic (mo ta, exploratory) ----
    chance = 1.0 / 16.0
    diag_rows = []
    for f in list(range(N_FOLDS)) + ["overall"]:
        idx = np.flatnonzero(fold_of == f) if f != "overall" else np.arange(n)
        tt = teacher_top1[idx]
        rn_t = truth[idx, tt, 0]
        rf_t = truth[idx, tt, 1]
        rp_t = truth[idx, tt, 2]
        filled = rf_t == 1
        agree = tt == oracle[idx]
        uni = truth[idx, :, 0].mean(axis=1)
        p = stable_softmax(E38[idx] / np.array([tau_per_fold[ff] for ff in fold_of[idx]])[:, None])
        diag_rows.append({
            "fold": f, "n": int(len(idx)),
            "agree_rate": float(agree.mean()), "chance": chance,
            "teacher_realized_mean": float(rn_t.mean()),
            "oracle_realized_mean": float(truth[idx, oracle[idx], 0].mean()),
            "uniform_realized_mean": float(uni.mean()),
            "teacher_minus_uniform": float(rn_t.mean() - uni.mean()),
            "p_net_positive_teacher": float((rn_t > 0).mean()),
            "fill_rate_teacher": float(rf_t.mean()),
            "pos_given_fill_teacher": (float(rp_t[filled].mean()) if filled.any() else None),
            "top1_conf_mean": float(p.max(axis=1).mean()),
            "top1_accuracy": float(agree.mean()),
            "cal_gap": float(abs(p.max(axis=1).mean() - agree.mean())),
        })
    loses = [r["fold"] for r in diag_rows if r["fold"] != "overall"
             and (r["teacher_minus_uniform"] < 0 or r["agree_rate"] < chance)]
    (out / "teacher_diagnostic.json").write_text(json.dumps(
        {"definitions": spec["teacher_diagnostic"]["definitions"],
         "per_fold": diag_rows, "loses_where": loses,
         "honest_note": ("Teacher thua uniform-baseline hoac duoi chance tai folds: "
                         + (str(loses) if loses else "KHONG co — teacher thang moi fold"))},
        indent=2, ensure_ascii=False), encoding="utf-8")

    (out / "taus.json").write_text(json.dumps(
        {"objective": spec["temperature"]["objective"],
         "why_past_folds": spec["temperature"]["why_past_folds"],
         "grid": grid, "fallback_tau": fallback_tau,
         "fallback_rule": "fold 0 khong co qua khu -> tau=1.0, khong peek",
         "per_fold": tau_rows, "tau_per_fold": tau_per_fold},
        indent=2, ensure_ascii=False), encoding="utf-8")

    overall = [r for r in diag_rows if r["fold"] == "overall"][0]
    summary = {
        "experiment": "opencode-v101-distill",
        "prespec": str(CONFIG_PATH),
        "causality": spec["causality"],
        "inputs": {"v38_source": str(v38_src), "v38b_policy_ref": str(policy_ref),
                   "dataset": str(ds), "n_decisions": int(n), "fold_lens": fold_lens},
        "mechanism": spec["mechanism_recap"],
        "taus": tau_per_fold,
        "teacher_overall": overall,
        "loses_where": loses,
        "student_spec": spec["student_spec_future"],
        "note": "Targets only — KHONG student training o v101.",
        "independent_test": False, "exploratory": True, "live_approved": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    digests = {f.name: sha256(f) for f in sorted(out.iterdir()) if f.is_file()}
    summary["output_sha256"] = digests
    summary["input_sha256"] = {
        "config": sha256(CONFIG_PATH),
        "dataset_config": sha256(ds / "config.json"),
        "parent_plan": sha256(ROOT / spec["inputs"]["parent_plan"].split(" (")[0]),
        "v38b_policy_ref": sha256(policy_ref),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(json.dumps({"state": "done", "out": str(out), "n": n,
                      "taus": tau_per_fold, "loses_where": loses,
                      "teacher_minus_uniform_overall":
                          round(overall["teacher_minus_uniform"], 6)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
