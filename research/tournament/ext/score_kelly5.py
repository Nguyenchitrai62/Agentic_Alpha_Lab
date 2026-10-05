"""EXT thin wrapper for kelly V2_meanvar (2026-10-05): same code path as research/tournament/kelly/kelly_sizing.py V2,
NO parameter changes, models refit per fold exactly as the original script does. Only the data paths and harness module are swapped:
harness5 (5 folds, anchors 2021-09-24..2025-09-24, TABLE v376 incl. 2025-26 rows), ext/fills_U_ext.parquet, ext/bar_open_ext.parquet,
ext/hourly_ext.parquet. Overlap assert: on the first 4 folds the sizes equal the original scored sizes (kelly/sizes.parquet V2_meanvar)
for rows with t_fill < 2025-09-24 (match share reported).

Writes: scores5_kelly_V2_meanvar.json, sizes5_kelly_V2.parquet, kelly5_overlap.json
  .venv/Scripts/python.exe research/tournament/ext/score_kelly5.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "kelly"))
sys.path.insert(0, str(HERE))
import harness5 as H5  # noqa: E402
from kelly_sizing import FEATS, HGB, fit_pred, scale_c  # noqa: E402 (read-only reuse, no param changes)


def build5():
    d = H5.load()
    fills = pd.read_parquet(HERE / "fills_U_ext.parquet")
    keep = (fills.t_fill < H5.DEV_END).to_numpy()
    bo = pd.read_parquet(HERE / "bar_open_ext.parquet")[keep].reset_index(drop=True)
    n0 = len(d)
    assert len(bo) == len(d) and (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all() \
        and (bo.r.to_numpy() == d.r.to_numpy()).all(), "bar_open_ext misaligned"
    d = d.merge(bo, on=["j", "sym", "r"], how="left", validate="one_to_one", indicator=True)
    assert len(d) == n0 and (d._merge == "both").all(), "bar_open join failed"
    d = d.drop(columns="_merge")
    assert (d.hour.astype(int) == d["T"].dt.hour).all(), "hour mismatch after join"
    d["tp"] = d.tp_dep.fillna(1.0)
    h = pd.read_parquet(HERE / "hourly_ext.parquet").sort_values(["sym", "t"])
    h["lr"] = np.log(h.close).groupby(h.sym).diff()
    h["sig"] = 2 * h.groupby("sym").lr.transform(lambda s: s.rolling(168, min_periods=48).std())
    q = d[["sym", "T"]].copy()
    q["tq"] = q["T"] - pd.Timedelta(hours=1)
    q["_i"] = np.arange(len(q))
    q = q.sort_values("tq")
    m = pd.merge_asof(q, h[["sym", "t", "sig"]].sort_values("t"), left_on="tq", right_on="t", by="sym", direction="backward",
                      tolerance=pd.Timedelta(hours=6))
    m = m.sort_values("_i")
    assert (m.t.isna() | (m.t <= m["T"] - pd.Timedelta(hours=1))).all()
    d["sig"] = m.sig.to_numpy()
    d["lsig"] = np.log(d.sig)
    return d


def main():
    d = build5()
    X = d[FEATS].to_numpy(float)
    y = d.y_dep.to_numpy(float)
    half = (d.j.to_numpy() % 2).astype(int)
    size = np.full(len(d), np.nan)
    mu5 = np.full(len(d), np.nan)
    diag = []
    for yi, a0, tr, te in H5.folds(d):
        sig = d.sig.to_numpy()
        mo, mt = fit_pred(lambda: HistGradientBoostingRegressor(**HGB), X, y, tr, te, half)
        e = np.abs(y[tr] - mo)
        rm = HistGradientBoostingRegressor(**HGB).fit(X[tr], e)
        sd_o = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X[tr]), 1e-4)
        sd_t = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X[te]), 1e-4)
        raw_o, raw_t = np.maximum(mo, 0) / sd_o ** 2, np.maximum(mt, 0) / sd_t ** 2
        c = scale_c(raw_o)
        size[te] = np.clip(c * raw_t, 0, 2)
        mu5[te] = mt
        diag.append(dict(year=str(a0.date()), n_train=int(tr.sum()), n_test=int(te.sum()), c=c,
                         train_zero_share=round(float((raw_o <= 0).mean()), 3)))
        print(json.dumps(diag[-1]), flush=True)

    # ---- overlap assert vs the original scored sizes (first 4 folds, t_fill < 2025-09-24) ----
    sys.path.insert(0, str(HERE.parent))
    import harness as H  # noqa: E402 (read-only: load keys only)
    do = H.load()
    so = pd.read_parquet(HERE.parent / "kelly/sizes.parquet")
    assert len(so) == len(do)
    ko = pd.DataFrame({"sym": do.sym.to_numpy(), "j": do.j.to_numpy(), "r": do.r.to_numpy(), "i_old": np.arange(len(do))})
    kn = pd.DataFrame({"sym": d.sym.to_numpy(), "j": d.j.to_numpy(), "r": d.r.to_numpy(), "i_new": np.arange(len(d))})
    mp = ko.merge(kn, on=["sym", "j", "r"], how="inner")
    assert len(mp) == len(do), (len(mp), len(do))
    lut = dict(zip(mp.i_new.to_numpy(), mp.i_old.to_numpy()))
    folds5 = H5.folds(d)
    tot, exact = 0, 0
    worst = 0.0
    for yi in range(4):
        te = folds5[yi][3]
        idx = np.flatnonzero(te)
        a = size[idx]
        b = so["V2_meanvar"].to_numpy()[[lut[i] for i in idx]]
        assert np.isfinite(a).all() and np.isfinite(b).all()
        dd = np.abs(a - b)
        worst = max(worst, float(dd.max()))
        exact += int((dd < 1e-12).sum())
        tot += len(idx)
    overlap = dict(rows_checked=tot, match_share_1e12=exact / tot, worst_abs_diff=worst)
    print(json.dumps(overlap, indent=1), flush=True)
    assert overlap["match_share_1e12"] == 1.0, overlap

    res = H5.score(d, size, "V2_meanvar")
    # first-4-year gains must reproduce the original score file (rounded to 4dp)
    ref = json.loads((HERE.parent / "kelly/score_V2_meanvar.json").read_text())
    for r5, ro in zip(res["years"][:4], ref["years"]):
        assert r5["year"] == ro["year"] and abs(r5["gain"] - ro["gain"]) < 5e-5, (r5, ro)
    res["overlap_vs_original_sizes"] = overlap
    (HERE / "scores5_kelly_V2_meanvar.json").write_text(json.dumps(res, indent=1))
    (HERE / "kelly5_overlap.json").write_text(json.dumps(overlap, indent=1))
    pd.DataFrame({"V2_meanvar": size, "sym": d.sym.to_numpy(), "T": d["T"].to_numpy(), "sig": d.sig.to_numpy()}).to_parquet(
        HERE / "sizes5_kelly_V2.parquet")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
