"""EXT thin wrapper for tp V2 diff (2026-10-05): same code path as research/tournament/tp/tp_bandit.py v2_diff,
NO parameter changes, models refit per fold exactly as the original script does (inner chronological split, margin grid, HGB settings).
Only data paths and harness module are swapped: harness5 (5 folds; harness5.score_tp has the same formula as harness.score_tp),
ext/fills_U_ext.parquet, ext/bar_open_ext.parquet. Overlap assert: on the first 4 folds the tp decisions equal the original scored
decisions (tp/tp_v2_diff.parquet) for rows with t_fill < 2025-09-24 (match share reported).

Writes: scores5_tp_v2_diff.json, tp5_v2_diff.parquet, tp5_overlap.json
  .venv/Scripts/python.exe research/tournament/ext/score_tp5.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch  # noqa: F401 (import before pandas on this host)
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tp"))
sys.path.insert(0, str(HERE))
import harness5 as H5  # noqa: E402
from tp_bandit import ACT, FEAT, MARGINS, diff_decide, diff_models  # noqa: E402 (read-only reuse, no param changes)


def data5():
    d = H5.load()
    fills = pd.read_parquet(HERE / "fills_U_ext.parquet")
    keep = (fills.t_fill < H5.DEV_END).to_numpy()
    bo = pd.read_parquet(HERE / "bar_open_ext.parquet")[keep].reset_index(drop=True)
    assert len(bo) == len(d) and (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all() \
        and (bo.r.to_numpy() == d.r.to_numpy()).all(), "bar_open_ext misaligned"
    for c in FEAT:
        if c in bo.columns:
            d[c] = bo[c].to_numpy()
        elif c == "k":
            d[c] = d["k"].to_numpy()
    Y = np.clip(d[["y0.5", "y1.0", "y1.5"]].to_numpy(float), -0.10, 0.08)
    return d, Y


def inner_split(d, tr):
    idx = np.flatnonzero(tr)
    T = d["T"].to_numpy()[idx]
    cut = np.sort(T)[int(0.75 * len(T))]
    va = np.zeros(len(d), bool); va[idx[T >= cut]] = True
    it = tr & (d.t_exit < pd.Timestamp(cut) - H5.EMBARGO).to_numpy()
    return it, va


def v2(d, Y, tr, te, cols):
    X = d[cols].to_numpy(float)
    it, va = inner_split(d, tr)
    mods = diff_models(X, Y, it)
    gains = {}
    for m in MARGINS:
        a = diff_decide(mods, X[va], m)
        ya = np.select([a == 0.5, a == 1.5], [Y[va, 0], Y[va, 2]], Y[va, 1])
        gains[m] = float((ya - Y[va, 1]).sum())
    best = max(gains.values())
    margin = max(m for m, g in gains.items() if g >= best - 1e-12)
    mods = diff_models(X, Y, tr)
    return diff_decide(mods, X[te], margin), dict(margin=margin, inner_gain={str(k): round(v, 4) for k, v in gains.items()},
                                                 n_inner_train=int(it.sum()), n_inner_val=int(va.sum()))


def main():
    d, Y = data5()
    tp = np.full(len(d), np.nan)
    fold_info = []
    for y, a0, tr, te in H5.folds(d):
        assert d.t_exit[tr].max() < a0 - H5.EMBARGO and d["T"][te].min() >= a0
        a, inf = v2(d, Y, tr, te, FEAT)
        tp[te] = a
        fold_info.append(dict(year=str(a0.date()), n_train=int(tr.sum()), n_test=int(te.sum()),
                              tp_counts={str(k): int(v) for k, v in pd.Series(a).value_counts().items()}, **inf))
        print("v2_diff", a0.date(), fold_info[-1], flush=True)

    # ---- overlap assert vs the original scored decisions (first 4 folds) ----
    tpo = pd.read_parquet(HERE.parent / "tp/tp_v2_diff.parquet")
    key_new = pd.DataFrame({"T": d["T"].to_numpy(), "sym": d.sym.to_numpy(), "k": d.k.to_numpy(), "i_new": np.arange(len(d))})
    mo = tpo.merge(key_new, on=["T", "sym", "k"], how="left", indicator=True)
    assert (mo._merge == "both").all(), int((mo._merge != "both").sum())
    folds5 = H5.folds(d)
    tot, exact = 0, 0
    for yi in range(4):
        te = folds5[yi][3]
        idx = np.flatnonzero(te)
        sub = mo[mo.i_new.isin(idx)]
        assert len(sub) == len(idx), (yi, len(sub), len(idx))
        a = tp[sub.i_new.to_numpy()]
        b = sub.tp_new.to_numpy(float)
        exact += int((a == b).sum())
        tot += len(idx)
    overlap = dict(rows_checked=tot, match_share_exact=exact / tot)
    print(json.dumps(overlap, indent=1), flush=True)
    assert overlap["match_share_exact"] == 1.0, overlap

    res = H5.score_tp(d, tp, "v2_diff")
    ref = json.loads((HERE.parent / "tp/score_v2_diff.json").read_text())
    for r5, ro in zip(res["years"][:4], ref["years"]):
        assert r5["year"] == ro["year"] and abs(r5["gain"] - ro["gain"]) < 5e-5, (r5, ro)
    res["folds"] = fold_info
    res["overlap_vs_original_decisions"] = overlap
    (HERE / "scores5_tp_v2_diff.json").write_text(json.dumps(res, indent=1))
    (HERE / "tp5_overlap.json").write_text(json.dumps(overlap, indent=1))
    te_all = np.isfinite(tp)
    pd.DataFrame({"row": np.flatnonzero(te_all), "T": d["T"][te_all].to_numpy(), "sym": d.sym[te_all].to_numpy(),
                  "k": d.k[te_all].to_numpy(), "tp_dep": d.tp_dep[te_all].to_numpy(), "tp_new": tp[te_all]}).to_parquet(
        HERE / "tp5_v2_diff.parquet")
    print(json.dumps({k: v for k, v in res.items() if k != "folds"}, indent=1))


if __name__ == "__main__":
    main()
