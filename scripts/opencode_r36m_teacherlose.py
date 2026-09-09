"""R-DIAGNOSTIC v103 (r36m teacherlose): dac ta teacher-losing folds {1,9,10} vs winning {3,5,7}.

Su dung frozen v38 ensemble predictions + labels + decisions.parquet + funding as-of join
+ v29 ensemble (overlap voi v56 error sets, cung dinh nghia sign).

Pre-spec: configs/opencode_v103_teacherlose.json — script RAISE neu thieu config.
Chi analysis, KHONG student training. Labels exploratory. Descriptors past-only.
Ghi moi artifacts/research/opencode_v103_teacherlose/ (khong ghi de).
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
from agentic_alpha_lab.data.swing import grid  # noqa: E402

SEEDS = [1729, 1730, 1731]
N_FOLDS = 11

CONFIG_PATH = ROOT / "configs/opencode_v103_teacherlose.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v103_teacherlose"


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


def load_ensemble_raw(source, parts, expect_ch=6):
    per_seed = []
    for seed in SEEDS:
        folds = []
        for fold in range(N_FOLDS):
            path = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            arr = np.load(path, allow_pickle=False)
            if arr.shape != (len(parts[fold]), 16, expect_ch) or not np.isfinite(arr).all():
                raise ValueError(f"shape/values mismatch: {path} {arr.shape}")
            folds.append(arr)
        per_seed.append(np.concatenate(folds, axis=0))
    return np.stack(per_seed)  # (3, n, 16, 6)


def stable_softmax(logits):
    z = np.asarray(logits, dtype=np.float64)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(x, dtype=np.float64), -40, 40)))


def cohen_d(m1, s1, n1, m2, s2, n2):
    den = (n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2
    pooled = np.sqrt(den / (n1 + n2 - 2)) if (n1 + n2 - 2) > 0 else np.nan
    return float((m1 - m2) / pooled) if pooled and np.isfinite(pooled) and pooled > 0 else None


def cohen_h(p1, p2):
    return float(2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p2)))


def phi_of(a, b):
    n11 = int(((a == 1) & (b == 1)).sum())
    n10 = int(((a == 1) & (b == 0)).sum())
    n01 = int(((a == 0) & (b == 1)).sum())
    n00 = int(((a == 0) & (b == 0)).sum())
    den = np.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return ((n11 * n00 - n10 * n01) / den if den > 0 else float("nan"), (n11, n10, n01, n00))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Thieu pre-spec config: {CONFIG_PATH} (khong tinh khi chua pre-spec)")
    spec = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de teacherlose cu; dung dir moi")
    out.mkdir(parents=True)

    L_FOLDS = list(spec["splits"]["L_losing"]["folds"])
    W_FOLDS = list(spec["splits"]["W_winning"]["folds"])
    VOL_CUT = float(spec["descriptors_past_only"]["vol"]["vol_high"].split("reuse VERBATIM")[0].split(">=")[1].strip().split(" ")[0])
    FUND_ABS = 0.0001

    # ---- inputs ----
    v38_src = ROOT / spec["inputs"]["v38_source"].split(" (")[0]
    v29_src = ROOT / spec["inputs"]["v29_source"].split(" (")[0]
    ds = ROOT / spec["inputs"]["labels"].split(" (")[0]
    ds = ds.parent
    fund_path = ROOT / spec["inputs"]["funding"].split(" (")[0]
    parent = json.loads((ROOT / spec["inputs"]["parent_plan"].split(" (")[0]).read_text(encoding="utf-8"))
    taus_doc = json.loads((ROOT / spec["inputs"]["taus"].split(" (")[0]).read_text(encoding="utf-8"))
    tau_per_fold = [float(t) for t in taus_doc["tau_per_fold"]]
    assert len(tau_per_fold) == N_FOLDS

    decisions_all = pd.read_parquet(ds / "decisions.parquet")
    decisions_all["signal_time"] = pd.to_datetime(decisions_all["signal_time"], utc=True)
    decisions_all["label_end"] = pd.to_datetime(decisions_all["label_end"], utc=True)
    with np.load(ds / "examples.npz", allow_pickle=False) as data:
        labels_all = data["labels"]
    assert labels_all.shape == (len(decisions_all), 16, 3) and np.isfinite(labels_all).all()

    parts = partitions(decisions_all, parent)
    fold_lens = [len(p) for p in parts]
    indices = np.concatenate(parts)
    n = len(indices)
    assert n == 4076, (n, fold_lens)
    part = decisions_all.iloc[indices].reset_index(drop=True)
    truth = labels_all[indices].astype(np.float64)
    fold_of = np.concatenate([np.full(len(p), f, dtype=np.int64) for f, p in enumerate(parts)])
    sig_time = pd.to_datetime(part["signal_time"], utc=True)

    # ---- teacher: frozen v38 ensemble (VERBATIM v101) ----
    stacked38 = load_ensemble_raw(v38_src, parts, 6)
    _, det38 = combine(stacked38, 0.0)
    E38 = np.asarray(det38["mean_expected_net_percent"], dtype=np.float64)
    assert E38.shape == (n, 16) and np.isfinite(E38).all()

    teacher_top1 = E38.argmax(axis=1)  # first-max
    oracle_top1 = truth[:, :, 0].argmax(axis=1)  # first-max, exploratory
    agree = (teacher_top1 == oracle_top1).astype(int)
    t_real = truth[np.arange(n), teacher_top1, 0]
    t_fill = truth[np.arange(n), teacher_top1, 1]
    t_pos = truth[np.arange(n), teacher_top1, 2]
    uni = truth[:, :, 0].mean(axis=1)
    oracle_real = truth[np.arange(n), oracle_top1, 0]
    teacher_sign = (t_real > 0).astype(int)  # strict, giong v56

    srt = np.sort(E38, axis=1)
    margin12 = srt[:, -1] - srt[:, -2]
    margin1m = srt[:, -1] - E38.mean(axis=1)
    tau_row = np.array([tau_per_fold[f] for f in fold_of])
    P = stable_softmax(E38 / tau_row[:, None])
    Pc = np.clip(P, 1e-12, 1.0)
    entropy = -(Pc * np.log(Pc)).sum(axis=1)
    conf = P.max(axis=1)

    lab_std = truth[:, :, 0].std(axis=1)
    lab_range = truth[:, :, 0].max(axis=1) - truth[:, :, 0].min(axis=1)
    frac_pos = (truth[:, :, 0] > 0).mean(axis=1)

    # ---- past-only descriptors ----
    cand_grid = np.asarray(grid(json.loads((ds / "config.json").read_text(encoding="utf-8"))))
    assert cand_grid.shape == (16, 6) and set(np.unique(cand_grid[:, 0]).tolist()) == {-1.0, 1.0}
    side_long = (cand_grid[teacher_top1, 0] == 1.0).astype(int)  # k<8 long
    hour = sig_time.dt.hour.to_numpy()
    year = sig_time.dt.year.to_numpy()
    atr_ratio = part["atr4"].to_numpy(dtype=float) / part["close"].to_numpy(dtype=float)
    vol_high = (atr_ratio >= VOL_CUT).astype(int)

    # funding as-of join (strict past-only: funding_time < signal_time)
    fund = pd.read_parquet(fund_path)
    fund["funding_time"] = pd.to_datetime(fund["funding_time"], utc=True)
    fund = fund.sort_values("funding_time")
    left = pd.DataFrame({"signal_time": sig_time, "_ord": np.arange(n)}).sort_values("signal_time")
    joined = pd.merge_asof(left, fund[["funding_time", "fundingRate"]],
                           left_on="signal_time", right_on="funding_time",
                           direction="backward", allow_exact_matches=False)
    joined = joined.sort_values("_ord").reset_index(drop=True)
    fund_last = joined["fundingRate"].to_numpy(dtype=float)
    fund_cov = float(np.isfinite(fund_last).sum() / n)
    fund_last = np.where(np.isfinite(fund_last), fund_last, 0.0)
    fund_pos = (fund_last > 0).astype(int)
    fund_high = (np.abs(fund_last) >= FUND_ABS).astype(int)

    # ---- v29 ensemble (VERBATIM v56: combo[...,0]*sigmoid(combo[...,4])) ----
    stacked29 = load_ensemble_raw(v29_src, parts, 6)
    combo29, _ = combine(stacked29, 0.0)
    exp29 = (combo29[..., 0].astype(np.float64) * sigmoid(combo29[..., 4])).astype(np.float64)
    assert exp29.shape == (n, 16) and np.isfinite(exp29).all()
    v29_top1 = exp29.argmax(axis=1)
    v29_sign = (truth[np.arange(n), v29_top1, 0] > 0).astype(int)
    teacher_err = 1 - teacher_sign
    v29_err = 1 - v29_sign

    # ---- per-fold table ----
    def scope_idx(key):
        if key == "overall":
            return np.arange(n)
        if key == "L":
            return np.flatnonzero(np.isin(fold_of, L_FOLDS))
        if key == "W":
            return np.flatnonzero(np.isin(fold_of, W_FOLDS))
        return np.flatnonzero(fold_of == int(key))

    scopes = [str(f) for f in range(N_FOLDS)] + ["overall", "L", "W"]
    pf_rows = []
    for key in scopes:
        idx = scope_idx(key if key in ("overall", "L", "W") else int(key))
        f = filled = t_fill[idx] == 1
        pf_rows.append({
            "scope": key, "n": int(len(idx)),
            "agree_rate": float(agree[idx].mean()),
            "teacher_realized_mean": float(t_real[idx].mean()),
            "oracle_realized_mean": float(oracle_real[idx].mean()),
            "uniform_realized_mean": float(uni[idx].mean()),
            "teacher_minus_uniform": float(t_real[idx].mean() - uni[idx].mean()),
            "p_net_positive_teacher": float(teacher_sign[idx].mean()),
            "fill_rate_teacher": float(t_fill[idx].mean()),
            "pos_given_fill_teacher": (float(t_pos[idx][filled].mean()) if filled.any() else None),
            "n_filled_teacher": int(filled.sum()),
            "margin_top1_top2_mean": float(margin12[idx].mean()),
            "margin_top1_top2_median": float(np.median(margin12[idx])),
            "margin_top1_mean_mean": float(margin1m[idx].mean()),
            "entropy_mean": float(entropy[idx].mean()),
            "top1_conf_mean": float(conf[idx].mean()),
            "label_std_mean": float(lab_std[idx].mean()),
            "label_range_mean": float(lab_range[idx].mean()),
            "frac_pos_candidates_mean": float(frac_pos[idx].mean()),
            "side_long_frac": float(side_long[idx].mean()),
            "vol_high_frac": float(vol_high[idx].mean()),
            "atr_ratio_mean": float(atr_ratio[idx].mean()),
            "atr_ratio_median": float(np.median(atr_ratio[idx])),
            "fund_pos_frac": float(fund_pos[idx].mean()),
            "fund_high_frac": float(fund_high[idx].mean()),
            "fund_last_mean": float(fund_last[idx].mean()),
            "era_2025_2026_frac": float((year[idx] >= 2025).mean()),
            "sess_00_frac": float((hour[idx] == 0).mean()),
            "sess_06_frac": float((hour[idx] == 6).mean()),
            "sess_12_frac": float((hour[idx] == 12).mean()),
            "sess_18_frac": float((hour[idx] == 18).mean()),
            "v29_sign_acc": float(v29_sign[idx].mean()),
        })
    pd.DataFrame(pf_rows).to_csv(out / "per_fold.csv", index=False)

    # ---- L vs W: ALL comparisons + effect sizes ----
    idxL = scope_idx("L")
    idxW = scope_idx("W")
    nL, nW = int(len(idxL)), int(len(idxW))
    cont_vars = {
        "teacher_realized": t_real, "uniform_realized": uni, "oracle_realized": oracle_real,
        "margin_top1_top2": margin12, "margin_top1_mean": margin1m,
        "entropy": entropy, "top1_conf": conf,
        "label_std": lab_std, "label_range": lab_range, "frac_pos_candidates": frac_pos,
        "atr_ratio": atr_ratio, "fund_last": fund_last,
    }
    bin_vars = {
        "agree_rate": agree, "p_net_positive_teacher": teacher_sign,
        "fill_rate_teacher": (t_fill == 1).astype(int),
        "side_long": side_long, "vol_high": vol_high,
        "fund_pos": fund_pos, "fund_high": fund_high,
        "era_2025_2026": (year >= 2025).astype(int),
        "sess_00": (hour == 0).astype(int), "sess_06": (hour == 6).astype(int),
        "sess_12": (hour == 12).astype(int), "sess_18": (hour == 18).astype(int),
        "v29_sign_acc": v29_sign,
    }
    lw_rows = []
    for name, v in cont_vars.items():
        a, b = v[idxL].astype(float), v[idxW].astype(float)
        m1, m2 = float(a.mean()), float(b.mean())
        s1, s2 = float(a.std(ddof=1)), float(b.std(ddof=1))
        d = cohen_d(m1, s1, nL, m2, s2, nW)
        se = float(np.sqrt(s1 * s1 / nL + s2 * s2 / nW))
        z = float((m1 - m2) / se) if se > 0 else None
        lw_rows.append({"metric": name, "kind": "continuous", "mean_L": m1, "mean_W": m2,
                        "diff_LminusW": m1 - m2, "sd_L": s1, "sd_W": s2,
                        "effect": d, "effect_name": "cohen_d",
                        "se_diff": se, "z": z, "n_L": nL, "n_W": nW,
                        "flagged": bool(d is not None and abs(d) >= 0.50)})
    for name, v in bin_vars.items():
        a, b = v[idxL].astype(float), v[idxW].astype(float)
        p1, p2 = float(a.mean()), float(b.mean())
        h = cohen_h(p1, p2)
        se = float(np.sqrt(p1 * (1 - p1) / nL + p2 * (1 - p2) / nW))
        z = float((p1 - p2) / se) if se > 0 else None
        lw_rows.append({"metric": name, "kind": "proportion", "mean_L": p1, "mean_W": p2,
                        "diff_LminusW": p1 - p2, "sd_L": None, "sd_W": None,
                        "effect": h, "effect_name": "cohen_h",
                        "se_diff": se, "z": z, "n_L": nL, "n_W": nW,
                        "flagged": bool(abs(p1 - p2) >= 0.10)})
    # pos_given_fill: conditional tren filled subset (n = filled counts)
    for tag, idx in (("pos_given_fill_teacher", None),):
        _ = tag
        a = t_pos[idxL][t_fill[idxL] == 1].astype(float)
        b = t_pos[idxW][t_fill[idxW] == 1].astype(float)
        p1, p2 = float(a.mean()), float(b.mean())
        h = cohen_h(p1, p2)
        se = float(np.sqrt(p1 * (1 - p1) / len(a) + p2 * (1 - p2) / len(b)))
        z = float((p1 - p2) / se) if se > 0 else None
        lw_rows.append({"metric": "pos_given_fill_teacher", "kind": "proportion|filled-subset",
                        "mean_L": p1, "mean_W": p2, "diff_LminusW": p1 - p2,
                        "sd_L": None, "sd_W": None, "effect": h, "effect_name": "cohen_h",
                        "se_diff": se, "z": z, "n_L": int(len(a)), "n_W": int(len(b)),
                        "flagged": bool(abs(p1 - p2) >= 0.10)})
    pd.DataFrame(lw_rows).to_csv(out / "lose_vs_win.csv", index=False)
    flagged = [r["metric"] for r in lw_rows if r["flagged"]]

    # ---- overlap teacher-sign-error vs v29-sign-error ----
    ov_scopes = ["overall", "L", "W"] + [str(f) for f in L_FOLDS + W_FOLDS]
    ov_rows = []
    v29_marg_overall = float(v29_sign.mean())
    for key in ov_scopes:
        idx = scope_idx(key if key in ("overall", "L", "W") else int(key))
        ea = teacher_err[idx] == 1
        eb = v29_err[idx] == 1
        inter = int((ea & eb).sum())
        union = int((ea | eb).sum())
        phi, (n11, n10, n01, n00) = phi_of(teacher_sign[idx], v29_sign[idx])
        nw = int(ea.sum())
        pc = float(v29_sign[idx][ea].mean()) if nw else None
        marg_scope = float(v29_sign[idx].mean())
        if nw and pc is not None:
            se = float(np.sqrt(pc * (1 - pc) / nw))
            z = float((pc - marg_scope) / se) if se > 0 else 0.0
            lift = float(pc - marg_scope)
        else:
            se, z, lift = None, None, None
        ov_rows.append({"scope": key, "n": int(len(idx)),
                        "acc_teacher_sign": float(teacher_sign[idx].mean()),
                        "acc_v29_sign": marg_scope,
                        "v29_marginal_overall": v29_marg_overall,
                        "both_wrong": inter, "either_wrong": union,
                        "jaccard_error": (inter / union if union else None),
                        "agreement": float((teacher_sign[idx] == v29_sign[idx]).mean()),
                        "phi_correct": (float(phi) if np.isfinite(phi) else None),
                        "n11": n11, "n10": n10, "n01": n01, "n00": n00,
                        "n_teacher_wrong": nw,
                        "cond_v29_given_teacherwrong": pc,
                        "lift_vs_scope_marginal": lift, "se": se, "z": z})
    pd.DataFrame(ov_rows).to_csv(out / "overlap_v29.csv", index=False)

    # ---- student guidance (quy tac pre-spec trong config) ----
    rowL = [r for r in pf_rows if r["scope"] == "L"][0]
    oracle_gap_L = float(rowL["oracle_realized_mean"] - rowL["uniform_realized_mean"])
    if not flagged:
        guidance, why = ("opt_C_global",
                         f"Khong descriptor nao pass flag rule (|d|>=0.50 / |diff|>=10pp) -> "
                         f"giu global KL + small uniform ranking, KHONG dieu kien hoa.")
    elif oracle_gap_L >= 1.0:
        guidance, why = ("opt_B_upweight",
                         f"{len(flagged)} descriptor(s) flagged {flagged} + oracle ceiling o L van cao "
                         f"(oracle {rowL['oracle_realized_mean']:.3f}% vs uniform "
                         f"{rowL['uniform_realized_mean']:.3f}%, gap {oracle_gap_L:.3f}pp >= 1.0) -> "
                         f"hoc duoc nhung teacher chua hoc -> upweight L-like conditions trong ranking-on-hard.")
    else:
        guidance, why = ("opt_A_exclude",
                         f"{len(flagged)} descriptor(s) flagged {flagged} NHUNG oracle ceiling o L sup do "
                         f"(gap {oracle_gap_L:.3f}pp < 1.0) -> irreducible noise -> exclude/downweight.")
    ovL = [r for r in ov_rows if r["scope"] == "L"][0]
    ovW = [r for r in ov_rows if r["scope"] == "W"][0]
    overlap_verdict = {
        "teacher_loses_where_v29_loses": bool(ovL["acc_v29_sign"] < ovW["acc_v29_sign"]),
        "jaccard_L": ovL["jaccard_error"], "jaccard_W": ovW["jaccard_error"],
        "cond_v29_given_teacherwrong_L": ovL["cond_v29_given_teacherwrong"],
        "cond_v29_given_teacherwrong_W": ovW["cond_v29_given_teacherwrong"],
        "note": ("So sanh acc_v29_sign L vs W + Jaccard/conditional; "
                 "dinh nghia sign-error giong v56 (realized>0 strict tai own top1)."),
    }

    summary = {
        "experiment": "opencode-v103-teacherlose",
        "prespec": str(CONFIG_PATH),
        "causality": spec["causality"],
        "n": int(n), "fold_lens": fold_lens,
        "scopes": {"L_folds": L_FOLDS, "W_folds": W_FOLDS, "n_L": nL, "n_W": nW},
        "thresholds": {"vol_cut_reused_v56": VOL_CUT, "fund_abs_fixed": FUND_ABS,
                       "flag_rule": spec["flag_rule"]},
        "funding_join": {"coverage": fund_cov, "rule": "as-of funding_time < signal_time (strict past-only)",
                         "file": spec["inputs"]["funding"].split(" (")[0]},
        "taus_reused": tau_per_fold,
        "flagged_conditions": flagged,
        "n_flagged": len(flagged),
        "oracle_gap_L": oracle_gap_L,
        "student_guidance": {"option": guidance, "justification": why},
        "overlap_v29": overlap_verdict,
        "independent_test": False, "exploratory": True, "live_approved": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    digests = {f.name: sha256(f) for f in sorted(out.iterdir()) if f.is_file()}
    summary["output_sha256"] = digests
    summary["input_sha256"] = {
        "config": sha256(CONFIG_PATH),
        "dataset_config": sha256(ds / "config.json"),
        "parent_plan": sha256(ROOT / spec["inputs"]["parent_plan"].split(" (")[0]),
        "taus": sha256(ROOT / spec["inputs"]["taus"].split(" (")[0]),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"state": "done", "out": str(out), "n_L": nL, "n_W": nW,
                      "flagged": flagged, "guidance": guidance,
                      "fund_coverage": round(fund_cov, 4)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
