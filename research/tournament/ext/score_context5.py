"""EXT thin wrapper for context V2 hgb_mono (2026-10-05): same code path as research/tournament/context/run_variants.py hgb_mono,
NO parameter changes, models refit per fold exactly as the original script does. Only data paths and harness module are swapped:
harness5 (5 folds), ext/bar_open_ext.parquet, ext/market_features_ext.parquet. Overlap assert: the wrapper re-runs the identical pipeline
on the OLD data (read-only) for the first 4 folds, checks its gains reproduce score_hgb_mono.json, then asserts the ext-run sizes equal the
old-run sizes on the overlapping test rows (match share reported).

Writes: scores5_context_hgb_mono.json, sizes5_context_hgb_mono.parquet, context5_overlap.json
  .venv/Scripts/python.exe research/tournament/ext/score_context5.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "context"))
sys.path.insert(0, str(HERE))
import harness5 as H5  # noqa: E402
from build_market_features_ext import FEATS as MKT  # noqa: E402 (same column list as the original)
from run_variants import ALL, BASE, MONO, hgb  # noqa: E402 (read-only reuse, no param changes)


def features_new(d):
    fills = pd.read_parquet(HERE / "fills_U_ext.parquet")
    keep = (fills.t_fill < H5.DEV_END).to_numpy()
    bo = pd.read_parquet(HERE / "bar_open_ext.parquet")[keep].reset_index(drop=True)
    assert len(bo) == len(d) and (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all() \
        and (bo.r.to_numpy() == d.r.to_numpy()).all(), "bar_open_ext misaligned"
    mf = pd.read_parquet(HERE / "market_features_ext.parquet")
    assert len(mf) == len(d) and (mf.sym.to_numpy() == d.sym.to_numpy()).all() and (mf["T"].to_numpy() == d["T"].to_numpy()).all()
    return pd.concat([bo[[c for c in BASE if c != "k"]], d[["k"]], mf[MKT]], axis=1)[ALL]


def run_pipeline(d, F, folds, label):
    y = np.clip(d["y1.0"].to_numpy(float), -0.10, 0.08)
    half = (d.j % 2).to_numpy()
    yd = d.y_dep.to_numpy(float)
    X = F[ALL].to_numpy(float)
    size = np.full(len(d), np.nan)
    for yi, a0, tr, te in folds:
        mu = float(y[tr].mean())
        ms = [hgb(10 * yi + h, MONO, ALL).fit(X[tr & (half == h)], y[tr & (half == h)]) for h in (0, 1)]
        pa, pb = (m.predict(X[te]) for m in ms)
        s = np.where((pa > 2 * mu) & (pb > 2 * mu), 1.5, np.where((pa < 0) & (pb < 0), 0.5, 1.0))
        size[te] = s
        print(label, str(a0.date()), "mu", round(mu, 5), "up", round(float((s == 1.5).mean()), 3),
              "down", round(float((s == 0.5).mean()), 3), flush=True)
    return size


def main():
    d = H5.load()
    F = features_new(d)
    size = run_pipeline(d, F, H5.folds(d), "new")

    # ---- faithful-port check on OLD data (read-only) + overlap assert ----
    sys.path.insert(0, str(HERE.parent))
    import harness as H  # noqa: E402 (read-only)
    do = H.load()
    fills_o = pd.read_parquet(HERE.parent.parent / "diagnostics/phase_agents/fills_U.parquet")
    keep_o = (fills_o.t_fill < H.DEV_END).to_numpy()
    bo_o = pd.read_parquet(HERE.parent / "data/bar_open.parquet")[keep_o].reset_index(drop=True)
    mf_o = pd.read_parquet(HERE.parent / "context/market_features.parquet")
    Fo = pd.concat([bo_o[[c for c in BASE if c != "k"]], do[["k"]], mf_o[MKT]], axis=1)[ALL]
    size_o = run_pipeline(do, Fo, H.folds(do), "old")
    ref = json.loads((HERE.parent / "context/score_hgb_mono.json").read_text())
    res_o = H.score(do, size_o, "hgb_mono")
    for r, ro in zip(res_o["years"], ref["years"]):
        assert r["year"] == ro["year"] and abs(r["gain"] - ro["gain"]) < 5e-5, (r, ro)
    ko = pd.DataFrame({"sym": do.sym.to_numpy(), "j": do.j.to_numpy(), "r": do.r.to_numpy(), "i_old": np.arange(len(do))})
    kn = pd.DataFrame({"sym": d.sym.to_numpy(), "j": d.j.to_numpy(), "r": d.r.to_numpy(), "i_new": np.arange(len(d))})
    mp = ko.merge(kn, on=["sym", "j", "r"], how="inner")
    assert len(mp) == len(do), (len(mp), len(do))
    lut = dict(zip(mp.i_new.to_numpy(), mp.i_old.to_numpy()))
    folds5 = H5.folds(d)
    tot, exact = 0, 0
    for yi in range(4):
        idx = np.flatnonzero(folds5[yi][3])
        a, b = size[idx], size_o[[lut[i] for i in idx]]
        exact += int((a == b).sum())
        tot += len(idx)
    overlap = dict(rows_checked=tot, match_share_exact=exact / tot, old_gains_reproduced=True)
    print(json.dumps(overlap, indent=1), flush=True)
    assert overlap["match_share_exact"] == 1.0, overlap

    res = H5.score(d, size, "hgb_mono")
    ref4 = [r["gain"] for r in ref["years"]]
    for r5, g in zip(res["years"][:4], ref4):
        assert abs(r5["gain"] - g) < 5e-5, (r5, g)
    res["overlap_vs_original_sizes"] = overlap
    (HERE / "scores5_context_hgb_mono.json").write_text(json.dumps(res, indent=1))
    (HERE / "context5_overlap.json").write_text(json.dumps(overlap, indent=1))
    pd.DataFrame({"hgb_mono": size, "sym": d.sym.to_numpy(), "T": d["T"].to_numpy()}).to_parquet(
        HERE / "sizes5_context_hgb_mono.parquet")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
