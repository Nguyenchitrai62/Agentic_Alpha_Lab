"""v143: cross-asset attention network for the short-horizon book (registry parallel-20260906-r2 / v143, track A).

Model and training: artifacts/kaggle/v143/kernel/train_v143.py (per-time-step set of the 5 majors, per-token MLP +
2-layer Transformer encoder across assets, 3 heads y6/y18/y42, masked MSE, audited anchors/cutoffs/embargoes, early
stopping on the last 365 days of training steps, 5 seeds). Light model (~0.1M parameters, minutes on the local GTX1650),
so it runs locally, not as a heavy Kaggle job. Input: the exported audited v103 panel (v143_export.py).
Evaluation (this script, fixed before the full training run):
  NN short signal = mean(p6, p18); IC per anchor vs y6/y18 for NN, HGB (v103) and the blend.
  Primary: v133 configuration where the v103 book signal = 0.5 * HGB + 0.5 * (sd_hgb/sd_nn) * NN (sd = std of each
  model's OOS predictions within the anchor year's first 90 days? NO - to stay causal the NN is rescaled by the ratio of
  standard deviations computed on the PREVIOUS anchor year's predictions; the first year uses the ratio 1).
  Secondary: NN-only v103 book (scaled the same way).
  Reference v133: 2.44/2.222/1.95.

  python research/parallel/rounds/parallel-20260906-r2/v143/v143_evaluate.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRED = Path("artifacts/kaggle/v143/local_out")
spec = importlib.util.spec_from_file_location("v129", HERE.parent / "v129" / "v129_vol_forecast_sizing.py")
v129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v129)
v125, v115, v103, v110 = v129.v125, v129.v115, v129.v103, v129.v110
PD = 6


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    nn = pd.concat([pd.read_parquet(PRED / f"pred_{a}.parquet") for a in ext.v92.ANCHORS], ignore_index=True)
    nn["t"] = pd.to_datetime(nn["t"], utc=True)
    nn["nn"] = 0.5 * (nn["p6"] + nn["p18"])
    fl = fl.merge(nn[["t", "sym", "nn"]], on=["t", "sym"], how="left")
    ic, ratio, prev = {}, {}, None
    for a in ext.v92.ANCHORS:
        m = (fl.t >= pd.Timestamp(a, tz="UTC")) & (fl.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))
        g = fl[m]
        ratio[a] = 1.0 if prev is None else float(prev["pred"].std() / prev["nn"].std())
        prev = g
        ic[a] = {k: round(float(g[[c, "y6"]].corr(method="spearman").iloc[0, 1]), 4) for k, c in (("hgb_y6", "pred"), ("nn_y6", "nn"))}
        ic[a].update({k: round(float(g[[c, "y18"]].corr(method="spearman").iloc[0, 1]), 4) for k, c in (("hgb_y18", "pred"), ("nn_y18", "nn"))})
        print(a, ic[a], "scale", round(ratio[a], 3), flush=True)
    fl["scale"] = fl["t"].apply(lambda t: ratio[max(a for a in ext.v92.ANCHORS if t >= pd.Timestamp(a, tz="UTC"))])
    pv92, _ = v129.vol_predict(p92, ext.v92.FEATS, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

    def swap(df, pv):
        d = df.merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    ph = list(range(PD))
    W_lo = v125.phased(v125.raw_lo(swap(lo, pv92)), ph)
    W94 = v125.phased(v125.raw_ls(swap(ls, pv92)), ph)
    out = {"version": "v143", "ic": ic, "nn_scale_ratio": ratio}
    for key, sig in (("primary_blend", lambda d: 0.5 * d["pred"] + 0.5 * d["scale"] * d["nn"].fillna(0.0)),
                     ("secondary_nn_only", lambda d: d["scale"] * d["nn"].fillna(0.0))):
        f2 = fl.assign(pred=sig(fl))
        W103 = v125.phased(v125.raw_ls(swap(f2, pv103)), ph)
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103.t.min()]
        books = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0) \
            + 0.25 * W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0) \
            + 0.5 * W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
        res = {}
        for sc, (fee, slip) in ext.v92.SCEN.items():
            res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
            print(key, sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
        out[key] = res
    out["reference_v133"] = {"normal": 2.44, "fee_stress": 2.222, "execution_stress": 1.95}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v143_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
