"""v306 building block: walk-forward dip-agent prediction tables for the evolutionary search (no selection input by itself).

The v301 G2 agents (size model on y1.0, take-profit models per action, cross-fitted halves j % 2, HGB of v296, fits on pooled fills of the 5 majors
+ 30 U2020 alts that exited before anchor - 7 days) are refitted on three rung sets and their RAW predictions stored in the deployable bar-open
form (state at the close of minute 0 of the holding bar, as research/diagnostics/g2_exec/g2_cache.py), for every holding bar, major and rung
depth k in U = 2.0 .. 5.0 step 0.5:
  fit "G2"  trained on rungs 2.5 / 3.0 / 3.5 / 4.0     (= v301 G2; must reproduce G2_bar_open dev4 6.504 with the S1 / X4 rules)
  fit "R1"  trained on rungs 2.0 .. 4.0                 (= v304 R1 rung set)
  fit "U"   trained on rungs 2.0 .. 5.0                 (all seven depths)
Per row: pa, pb (size-model predictions of the two halves), mu (mean clipped y1.0 of the fit window), qa0..2 / qb0..2 (take-profit model
predictions for ACTIONS 0.5 / 1.0 / 1.5 sigma). The evolutionary genome turns these into size / TP decisions (thresholds are genes).
Output: artifacts/research/engine_real/v306_gene_tables.parquet
  python research/parallel/rounds/parallel-20260906-r2/v306/v306_gene_tables.py
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
FITS = {"G2": (2.5, 3.0, 3.5, 4.0), "R1": (2.0, 2.5, 3.0, 3.5, 4.0), "U": U}


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main():
    v294 = L("v294_gt", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = L("v296_gt", RD / "v296/v296_joint_dip_agent.py")
    v221 = L("v221", RD / "v221/v221_grid_hysteresis.py"); eu = v221.eu
    v293.RUNGS = U
    assets = {s: v293.Asset(s) for s in v293.MAJORS}; btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + v294.universe():
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
        if len(d):
            parts.append(d.assign(sym=s))
        print("fills", s, len(d), flush=True)
        del A
    allf = pd.concat(parts, ignore_index=True)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    meta, feats = [], []
    for s, A in assets.items():
        for j, T in enumerate(A.t0):
            if T < anchors[0] or not np.isfinite(A.sig[j]):
                continue
            jj = max(q for q, a0 in enumerate(anchors) if T >= a0)
            kk = j * 240
            base = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk),
                    np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, T.hour]
            for k in U:
                meta.append((T, s, k, jj))
                feats.append(base[:1] + [k] + base[2:])
    F = np.array(feats, float)
    J = np.array([m_[3] for m_ in meta])
    out = []
    for fit, ks in FITS.items():
        sub = allf[allf["x1"].isin(ks)].reset_index(drop=True)
        X = sub[[f"x{q}" for q in range(7)]].to_numpy(float)
        Y = np.clip(sub[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
        y1 = Y[:, v293.ACTIONS.index(1.0)]
        half = (sub["j"] % 2).to_numpy()
        res = {c: np.full(len(meta), np.nan) for c in ("pa", "pb", "mu", "qa0", "qa1", "qa2", "qb0", "qb1", "qb2")}
        for jj, a0 in enumerate(anchors):
            keep = np.asarray(sub.t_exit < a0 - v293.EMBARGO)
            mu = float(y1[keep].mean())
            sm = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
            tm = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(len(v293.ACTIONS))]
                  for h in (0, 1)]
            sel = J == jj
            x = F[sel]
            res["pa"][sel], res["pb"][sel] = sm[0].predict(x), sm[1].predict(x)
            res["mu"][sel] = mu
            for c in range(3):
                res[f"qa{c}"][sel] = tm[0][c].predict(x)
                res[f"qb{c}"][sel] = tm[1][c].predict(x)
            print("fit", fit, "anchor", jj, "rows", int(keep.sum()), "mu", round(mu, 5), flush=True)
        df = pd.DataFrame({"T": [m_[0] for m_ in meta], "sym": [m_[1] for m_ in meta], "k": [m_[2] for m_ in meta], **res}).assign(fit=fit)
        out.append(df)
    tab = pd.concat(out, ignore_index=True)
    # check: the G2 fit with the v301 S1 / X4 rules equals the audited bar-open G2 table on the G2 rungs
    ref = pd.read_parquet(eu.er.CACHE / "v301_g2_table_m0.parquet")
    g = tab[(tab.fit == "G2") & tab.k.isin(FITS["G2"])].copy()
    g["rung"] = g.k.map({k: r for r, k in enumerate(FITS["G2"])})
    g["size"] = np.where((g.pa > 2 * g.mu) & (g.pb > 2 * g.mu), 1.5, np.where((g.pa < 0) & (g.pb < 0), 0.5, 1.0))
    qa, qb = g[["qa0", "qa1", "qa2"]].to_numpy(), g[["qb0", "qb1", "qb2"]].to_numpy()
    ba, bb = qa.argmax(1), qb.argmax(1)
    n = np.arange(len(g))
    ok = (ba == bb) & (ba != 1) & (qa[n, ba] - qa[:, 1] > 0.0010) & (qb[n, bb] - qb[:, 1] > 0.0010)
    g["tp"] = np.where(ok, np.array(v293.ACTIONS)[ba], 1.0)
    mg = ref.merge(g[["T", "sym", "rung", "size", "tp"]], on=["T", "sym", "rung"], suffixes=("_ref", ""))
    print("check rows", len(ref), len(mg), "size match", float((mg.size_ref == mg["size"]).mean()), "tp match", float((mg.tp_ref == mg.tp).mean()))
    assert len(mg) == len(ref) and (mg.size_ref == mg["size"]).mean() > 0.999 and (mg.tp_ref == mg.tp).mean() > 0.999
    p = eu.er.CACHE / "v306_gene_tables.parquet"
    tab.to_parquet(p)
    print("saved", p, len(tab))


if __name__ == "__main__":
    main()
