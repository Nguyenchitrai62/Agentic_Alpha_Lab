"""v350 building block: walk-forward dip-agent prediction tables trained on outcomes under the MANUAL M3 rules (no selection input by itself).

Same as v306_gene_tables.py (pooled 5 majors + 30 U2020 alts, cross-fitted halves j % 2, v296 HGB, fills exited before anchor - 7 days, bar-open
state at minute 0, actions TP 0.5 / 1.0 / 1.5 sigma) except the outcome labels: the replica's stop is the M3 exchange-native TOUCH stop at 8 sigma
(close5 trigger and backstop both at 8 sigma = touch at 8 sigma) instead of the BOT's close5 4 sigma + 8-sigma backstop. Fits:
  "MU"  trained on all seven depths 2.0 .. 5.0   |   "M34" trained on the M3 depths 3.0 / 4.0 only
Output: artifacts/research/engine_real/v350_m3rule_tables.parquet (columns as v306_gene_tables; fit in {MU, M34})
  python research/parallel/rounds/parallel-20260906-r2/v350/v350_m3rule_tables.py
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
FITS = {"MU": U, "M34": (3.0, 4.0)}


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main():
    v294 = L("v294_gt", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = L("v296_gt", RD / "v296/v296_joint_dip_agent.py")
    v221 = L("v221", RD / "v221/v221_grid_hysteresis.py"); eu = v221.eu
    v293.RUNGS = U
    v293.M_SL, v293.BACKSTOP = 8.0, 8.0  # M3: exchange-native touch stop at 8 sigma
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
    p = eu.er.CACHE / "v350_m3rule_tables.parquet"
    tab.to_parquet(p)
    print("saved", p, len(tab))


if __name__ == "__main__":
    main()
