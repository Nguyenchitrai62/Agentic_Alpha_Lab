"""kelly round 2, disclosed extra variant W4 meanvar_sigunits (PLAN2.md addendum) + tail report (worst day, max DD of the cumulative daily
sum(size * y_dep) per year at the harness equal exposure) for deployed, V2, W1-W4.

  .venv/Scripts/python.exe research/tournament/kelly/round2/run_w4.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_round2 as R  # noqa: E402

K, H = R.K, R.H
FEATS_N = [c for c in K.FEATS if c != "lsig"]


def sig4_table():
    """Asset.sig per (sym, T) on the standard grid from hourly opens."""
    h = pd.read_parquet(K.HERE.parent / "data/hourly.parquet")
    out = []
    for s, g in h.groupby("sym"):
        g = g.set_index("t").sort_index()
        grid = pd.date_range(pd.Timestamp("2020-08-01", tz="UTC"), g.index.max(), freq="4h")
        o = g.open.reindex(grid)
        sig = o.reset_index(drop=True).pct_change().rolling(360, min_periods=120).std().shift(1).to_numpy()
        out.append(pd.DataFrame(dict(sym=s, T=grid, sig4=sig)))
    return pd.concat(out, ignore_index=True)


def spot_check(d):
    sp = importlib.util.spec_from_file_location("v293_w4", H.ROOT / "research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py")
    v293 = importlib.util.module_from_spec(sp); sp.loader.exec_module(v293)
    v293.END = pd.Timestamp("2025-09-25", tz="UTC")
    import os
    cwd = os.getcwd(); os.chdir(H.ROOT)
    try:
        A = v293.Asset("BTCUSDT")
    finally:
        os.chdir(cwd)
    m = d.sym == "BTCUSDT"
    ref = A.sig[d.j[m].to_numpy()]
    mine = d.sig4[m].to_numpy()
    ok = np.isfinite(ref) & np.isfinite(mine)
    return dict(rows=int(m.sum()), both_finite=int(ok.sum()), nan_mismatch=int((np.isfinite(ref) != np.isfinite(mine)).sum()),
                max_rel_diff=float(np.max(np.abs(mine[ok] / ref[ok] - 1))), share_rel_lt_1e9=float(np.mean(np.abs(mine[ok] / ref[ok] - 1) < 1e-9)))


def tails(d, size):
    """Per year (equal exposure): worst day and max drawdown of the cumulative daily sum(size * y_dep)."""
    out = []
    for yi, a0, tr, te in H.folds(d):
        sd, sn, yy = d.size_dep.to_numpy()[te], np.asarray(size, float)[te], d.y_dep.to_numpy()[te]
        sn = np.where(np.isfinite(sn), sn, sd)
        sn = sn * sd.mean() / max(sn.mean(), 1e-12)
        day = pd.Series(sn * yy).groupby(d["T"][te].dt.floor("D").to_numpy()).sum().sort_index()
        cum = day.cumsum()
        dd = float((cum - np.maximum(cum.cummax(), 0)).min())
        out.append(dict(year=str(a0.date()), worst_day=round(float(day.min()), 4), max_dd_cum=round(dd, 4), S=round(float(day.sum()), 4)))
    return out


def main():
    d = R.build()
    d = d.merge(sig4_table(), on=["sym", "T"], how="left", validate="many_to_one")
    ref = H.load()
    assert all((d[c].to_numpy() == ref[c].to_numpy()).all() for c in ("j", "sym", "r"))
    chk = spot_check(d)
    print("sig4 spot check BTC", chk, "coverage", float(d.sig4.notna().mean()), flush=True)
    X = d[FEATS_N].to_numpy(float)
    z = (d.y_dep / d.sig4).to_numpy(float)
    half = (d.j.to_numpy() % 2).astype(int)
    size = np.full(len(d), np.nan)
    diag = []
    for yi, a0, tr0, te in H.folds(d):
        tr = tr0 & np.isfinite(z)
        oof, mt, ms = R.mean_cf(X, z, tr, te, half)
        rm = HistGradientBoostingRegressor(**K.HGB).fit(X[tr], np.abs(z[tr] - oof))
        so = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X[tr]), 1e-4)
        c = K.scale_c(np.maximum(oof, 0) / so ** 2)
        size[te] = R.predict((a0, ms, rm, c), X[te])
        diag.append(dict(year=str(a0.date()), train_rows=int(tr.sum()), train_dropped_nan_sig=int((tr0 & ~np.isfinite(z)).sum()),
                         test_nan_sig=int((te & ~np.isfinite(z)).sum()), c=c,
                         ic_mu_z=round(float(pd.Series(mt).corr(pd.Series(z[te]), method="spearman")), 4)))
    res = H.score(d, size, "W4_meanvar_sigunits")
    (HERE / "score_W4_meanvar_sigunits.json").write_text(json.dumps(res, indent=1))
    v2 = pd.read_parquet(K.HERE / "sizes.parquet").V2_meanvar.to_numpy()
    rv2 = H.score(d, v2, "V2")
    yrs = []
    for (yi, a0, tr, te), r, r2, dg in zip(H.folds(d), res["years"], rv2["years"], diag):
        yrs.append(dict(year=r["year"], gain_vs_dep=r["gain"], gain_vs_v2=round(r["S_new"] - r2["S_new"], 4), worst_day=r["worst_day_new"],
                        ic=r["ic_size_y"], raw_mean_size=round(float(size[te].mean()), 3), share_0=round(float((size[te] <= 0).mean()), 3),
                        share_2=round(float((size[te] >= 2).mean()), 3), **{k: v for k, v in dg.items() if k != "year"}))
    wins = sum(e["gain_vs_v2"] > 0 for e in yrs)
    wd, wd2 = min(e["worst_day"] for e in yrs), min(r["worst_day_new"] for r in rv2["years"])
    w4 = dict(total_gain_vs_dep=res["total_gain"], total_gain_vs_v2=round(sum(e["gain_vs_v2"] for e in yrs), 4), graduates=res["graduates"],
              years_beating_v2=wins, worst_day_min=wd, worst_day_min_v2=wd2, table_trigger=bool(wins >= 3 and wd >= wd2), sig4_check=chk, years=yrs)
    print("W4", json.dumps(w4), flush=True)
    s2 = pd.read_parquet(HERE / "sizes_round2.parquet")
    tl = {"deployed": tails(d, d.size_dep.to_numpy()), "V2_meanvar": tails(d, v2),
          **{c: tails(d, s2[c].to_numpy()) for c in s2.columns}, "W4_meanvar_sigunits": tails(d, size)}
    for k, v in tl.items():
        print("tail", k, [(e["year"][:4], e["worst_day"], e["max_dd_cum"]) for e in v], flush=True)
    s2["W4_meanvar_sigunits"] = size
    s2.to_parquet(HERE / "sizes_round2.parquet")
    (HERE / "summary_w4.json").write_text(json.dumps(dict(W4=w4, tails=tl), indent=1))


if __name__ == "__main__":
    main()
