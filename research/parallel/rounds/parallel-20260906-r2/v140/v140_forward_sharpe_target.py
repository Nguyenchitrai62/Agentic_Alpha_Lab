"""v140: predict the forward Sharpe of the holding window instead of the trailing-vol-normalised return (registry v140).

For horizon h and entry at open[t+1]: R_h = log(open[t+1+h]/open[t+1]); fv_h = std of the 4h open-to-open log returns
over bars t+2..t+1+h; target s_h = clip(R_h / (fv_h * sqrt(h)), -4, 4) (NaN if fv_h is 0/NaN). Replaces y (v92, h=42),
y18/y42/y84 (v94) and y6/y18 (v103) as training targets; the label is realised at the same time as before, so the audited
cutoffs/embargoes and row filters are unchanged. Predictions feed the unchanged v133 pipeline (vol-forecast sizing,
tranching, v115 portfolio 15% target). Reports v92 IC against both the new target and the old y, and three scenarios.
Reference v133: 2.44/2.222/1.95. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v140/v140_forward_sharpe_target.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v138", HERE.parent / "v138" / "v138_hgb_ridge_blend.py")
v138 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v138)
v129, v125, v115, v103, v110 = v138.v129, v138.v125, v138.v115, v138.v103, v138.v110
PD = 6
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402


def add_sharpe_targets(panel, horizons):
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        lo_ = np.log(g["open"].to_numpy())
        r = pd.Series(np.diff(lo_, prepend=np.nan))  # r[k] = log(open[k]/open[k-1])
        n = len(g)
        for h in horizons:
            R = np.full(n, np.nan)
            R[: n - 1 - h] = lo_[1 + h:] - lo_[1: n - h]
            fv = r.rolling(h).std().shift(-(h + 1)).to_numpy()  # std of r[t+2..t+1+h]
            with np.errstate(divide="ignore", invalid="ignore"):
                g[f"s{h}"] = np.clip(R / (fv * np.sqrt(h)), -4, 4)
            g.loc[~np.isfinite(g[f"s{h}"]), f"s{h}"] = np.nan
        out.append(g)
    return pd.concat(out, ignore_index=True)


def hgb_fit_predict(tr, te, feats, target):
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
    return m.fit(tr[feats], tr[target]).predict(te[feats])


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92 = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    ext.v92.FEATS = f92
    p94 = add_sharpe_targets(ext.v94.add_targets(p92), (18, 42, 84))
    tgt = re.compile(r"s\d+")
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y") and not tgt.fullmatch(c)]
    p103 = add_sharpe_targets(v103.build(), v103.HS)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y") and not tgt.fullmatch(c)]
    lo, ls, fl, ic = [], [], [], {}
    for a in ext.v92.ANCHORS:
        tr, te = v138.window(p94, a, "s42", ext.v92.H, ext.v92.EMBARGO_BARS)
        pr = hgb_fit_predict(tr, te, f92, "s42")
        lo.append(te.assign(pred=pr))
        ic[a] = dict(ic_new=round(float(pd.Series(pr, index=te.index).corr(te["s42"], method="spearman")), 4),
                     ic_old_y=round(float(pd.Series(pr, index=te.index).corr(te["y"], method="spearman")), 4))
        preds = []
        for h in (18, 42, 84):
            tr, te = v138.window(p94, a, f"s{h}", h, ext.v94.EMBARGO_BARS)
            preds.append(hgb_fit_predict(tr, te, f94, f"s{h}"))
        ls.append(te.assign(pred=np.mean(preds, axis=0)))
        preds = []
        for h in v103.HS:
            tr, te = v138.window(p103, a, f"s{h}", h, v103.EMBARGO)
            preds.append(hgb_fit_predict(tr, te, f103, f"s{h}"))
        fl.append(te.assign(pred=np.mean(preds, axis=0)))
        print(a, ic[a], flush=True)
    lo, ls, fl = (pd.concat(x, ignore_index=True) for x in (lo, ls, fl))
    pv92, _ = v129.vol_predict(p92, f92, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

    def swap(df, pv):
        d = df.merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    ph = list(range(PD))
    W_lo = v125.phased(v125.raw_lo(swap(lo, pv92)), ph)
    W94 = v125.phased(v125.raw_ls(swap(ls, pv92)), ph)
    W103 = v125.phased(v125.raw_ls(swap(fl, pv103)), ph)
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    books = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.25 * W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    out = {"version": "v140", "ic_v92": ic}
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print(sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_scenarios"] = res
    out["reference_v133"] = {"normal": 2.44, "fee_stress": 2.222, "execution_stress": 1.95}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v140_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
