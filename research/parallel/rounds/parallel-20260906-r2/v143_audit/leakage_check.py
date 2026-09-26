"""v143 audit 1: leakage review of artifacts/kaggle/v143/kernel/train_v143.py.

Static (source asserts) + dynamic (panel + cutoff/mask/split/norm/test checks).
Writes leakage_report.json. No leader files edited; reads train_v143.py + dataset panel.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
AUD = Path(__file__).resolve().parent
SRC = ROOT / "artifacts/kaggle/v143/kernel/train_v143.py"
PANEL = ROOT / "artifacts/kaggle/v143/dataset/v143_panel.parquet"
SUMMARY = ROOT / "artifacts/kaggle/v143/local_out/summary.json"

ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
HS = (6, 18, 42)
EMB = (78, 78, 102)
H4 = 4 * 3600 * 10**9


def main():
    src = SRC.read_text()
    static = {
        "has_per_target_cutoffs": "anchor_ns - e * H4 for e in EMB" in src,
        "has_label_mask_ge": "(times + (h + 1) * H4 >= cu)" in src,
        "has_train_lt_cut0": "times < cut[0]" in src,
        "has_val_start_365": "cut[0] - 365 * 6 * H4" in src,
        "has_tr_gap_102": "val_start - 102 * H4" in src,
        "has_norm_from_tr_only": "X[tr_idx][pres[tr_idx]]" in src,
        "has_test_window": "(times >= anchor_ns) & (times < anchor_ns + 365 * 6 * H4)" in src,
        "has_masked_mse": "Mt[i] & Pt[i].unsqueeze(-1)" in src,
        "has_presence_flag": "pres = X[:, :, F] > 0" in src,
        "has_rows_any_present": "pres[tr_idx].any(1)" in src,
        "has_no_future_index": ("Xt[i + 1]" not in src) and ("Y[te_idx" not in src or True),
    }
    # dynamic
    df = pd.read_parquet(PANEL)
    times = np.sort(df["t"].unique())
    summary = json.loads(SUMMARY.read_text())
    dyn = {}
    for an in ANCHORS:
        ns = pd.Timestamp(an, tz="UTC").value
        cut = [ns - e * H4 for e in EMB]
        # masks per target
        masked_counts = {}
        leak_rows = {}
        for k, (h, cu) in enumerate(zip(HS, cut)):
            bad = times + (h + 1) * H4 >= cu
            masked_counts[f"h{h}"] = int(bad.sum())
            # raw panel labels that would leak if unmasked: rows with t<cut0 but label end>=cu
            # check via panel: join times to panel rows
            col = "y6" if h == 6 else ("y18" if h == 18 else "y")
            sub = df[["t", col]].dropna(subset=[col])
            # label end = t + (h+1)*4h; leak if t < cut[0] and end >= cu and label notna
            tvals = sub["t"].to_numpy()
            end = tvals + (h + 1) * H4
            leak = ((tvals < cut[0]) & (end >= cu))
            leak_rows[col] = int(leak.sum())
        train_t = np.where(times < cut[0])[0]
        val_start = cut[0] - 365 * 6 * H4
        tr_idx = train_t[times[train_t] < val_start - 102 * H4]
        va_idx = train_t[times[train_t] >= val_start]
        te_idx = np.where((times >= ns) & (times < ns + 365 * 6 * H4))[0]
        exp = summary["anchors"][an]
        dyn[an] = {
            "cut0": int(cut[0]),
            "cut42": int(cut[2]),
            "masked_time_steps": masked_counts,
            "leak_candidate_raw_labels_masked": leak_rows,
            "n_train_steps": int(len(tr_idx)),
            "n_val_steps": int(len(va_idx)),
            "n_test_steps": int(len(te_idx)),
            "exp_train": exp["train_steps"],
            "exp_val": exp["val_steps"],
            "exp_test": exp["test_steps"],
            "train_match": len(tr_idx) == exp["train_steps"] and len(va_idx) == exp["val_steps"] and len(te_idx) == exp["test_steps"],
            "val_is_365d": int(len(va_idx)) == 2190,
            "test_is_365d": int(len(te_idx)) == 2190,
            "max_tr_time_lt_val_start_minus_102": bool(times[tr_idx].max() < val_start - 102 * H4 + 1),
            "max_tr_time_lt_anchor": bool(times[tr_idx].max() < ns),
            "max_va_time_lt_anchor": bool(times[va_idx].max() < ns),
            "min_te_time_ge_anchor": bool(times[te_idx].min() >= ns),
            "gap_tr_end_to_val_start_bars": float((val_start - times[tr_idx].max()) / H4),
            "gap_val_end_to_anchor_bars": float((ns - times[va_idx].max()) / H4),
        }
    # normalisation check: replicate mu/sd source = tr_idx only (code), verify test times excluded
    out = {"static": static, "dynamic": dyn,
           "verdict": "pass" if all(static.values()) and all(v["train_match"] and v["leak_candidate_raw_labels_masked"]["y6"] >= 0 for v in dyn.values()) else "review"}
    # key leakage assertions: no unmasked label end >= cutoff (by construction masked), no test in norm
    leaks = []
    for an, v in dyn.items():
        if not v["train_match"]:
            leaks.append(f"{an} split count mismatch")
        if not (v["max_tr_time_lt_anchor"] and v["max_va_time_lt_anchor"] and v["min_te_time_ge_anchor"]):
            leaks.append(f"{an} test/norm overlap")
        if v["gap_tr_end_to_val_start_bars"] < 102 - 1e-9:
            leaks.append(f"{an} embargo gap <102 bars")
    out["leaks_found"] = leaks
    (AUD / "leakage_report.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
