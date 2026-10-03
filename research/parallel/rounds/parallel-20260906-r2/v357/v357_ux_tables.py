"""v357 building block: walk-forward dip-agent tables with a RICHER bar-open state (no selection input by itself).

= v306_gene_tables.py fit "U" (pooled 5 majors + 30 U2020 alts, BOT labels: close5 4-sigma stop + 8-sigma backstop, all seven depths 2.0 .. 5.0,
cross-fitted halves, v296 HGB, fills exited before anchor - 7 days) with four extra state features, all computed from bars CLOSED before the holding
bar (identical at the fill and at the bar open):
  x7  previous 4h bar return / sigma_4h            x8  BTC previous 4h bar return / BTC sigma_4h
  x9  24h return (6 bars) / (sigma_4h sqrt 6)      x10 previous bar's flush depth: (min 1m low of the previous bar / its open - 1) / sigma_4h
Fit name "UX". Output: artifacts/research/engine_real/v357_ux_tables.parquet (columns as v306_gene_tables).
  python research/parallel/rounds/parallel-20260906-r2/v357/v357_ux_tables.py
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
FITS = {"UX": U}
NX = 11


def extras(A, btc, j):
    """x7..x10 at holding bar j from bars closed before it."""
    sg = A.sig[j]
    if j < 7 or not (sg > 0):
        return [np.nan] * 4
    r1 = (A.o[j] / A.o[j - 1] - 1) / sg
    bs = btc.sig[j]
    rb = (btc.o[j] / btc.o[j - 1] - 1) / bs if bs > 0 else np.nan
    r6 = (A.o[j] / A.o[j - 6] - 1) / (sg * np.sqrt(6))
    lo = np.nanmin(A.L[(j - 1) * 240: j * 240]) if np.isfinite(A.L[(j - 1) * 240: j * 240]).any() else np.nan
    fl = (lo / A.o[j - 1] - 1) / sg if A.o[j - 1] > 0 else np.nan
    return [r1, rb, r6, fl]


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
            ex = np.array([extras(A, btc, int(j)) for j in d["j"]], float)
            for q in range(4):
                d[f"x{7 + q}"] = ex[:, q]
            parts.append(d.assign(sym=s))
        print("fills", s, len(d), flush=True)
        if s not in assets:
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
            ex = extras(A, btc, j)
            for k in U:
                meta.append((T, s, k, jj))
                feats.append(base[:1] + [k] + base[2:] + ex)
    F = np.array(feats, float)
    J = np.array([m_[3] for m_ in meta])
    out = []
    for fit, ks in FITS.items():
        sub = allf[allf["x1"].isin(ks)].reset_index(drop=True)
        X = sub[[f"x{q}" for q in range(NX)]].to_numpy(float)
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
    p = eu.er.CACHE / "v357_ux_tables.parquet"
    tab.to_parquet(p)
    print("saved", p, len(tab))


if __name__ == "__main__":
    main()
