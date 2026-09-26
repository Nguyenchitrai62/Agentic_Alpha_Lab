"""v123: multi-timeframe MA-ribbon features (user's TradingView MA Ribbon idea) on the v114 panel.

Registry parallel-20260906-r2 / v123. Added per-asset features (all from closed bars):
  r4_50, r4_200 = log(close / SMA50) and log(close / SMA200) on 4h closes
  rib4 = +1 if close > SMA50 > SMA200 (4h), -1 if close < SMA50 < SMA200, else 0 (TradingView ribbon SMA50/SMA200)
  w50 = log(daily close / SMA350 of daily closes) (50-week SMA), w50_slope = 5-day change of log SMA350
  ribw = +1 / -1 / 0 with SMA350 and SMA1400 (200-week) on daily closes (0 while SMA1400 is unavailable)
  rib_agree = rib4 + rib (daily) + ribw
Daily-derived columns are joined to 4h bars by the daily close time (asof backward), like v92's daily features.
Books: v92 long-only and v94 long/short retrained on v114 panel + these features; primary: the v115 portfolio with these
books (0.25/0.25 + 0.5 unchanged v103; 15% target, ungoverned, v110 engine); secondary: the v96 blend. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v123/v123_mtf_ribbon.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v115 = _load("v115", "v115/v115_candidate.py")
v103, v110 = v115.v103, v115.v110
MTF = ("r4_50", "r4_200", "rib4", "w50", "w50_slope", "ribw", "rib_agree")


def mtf_features(ext, sym):
    b, d, _ = ext.load_asset_ext(sym)
    c = b["close"].astype(float)
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    x = pd.DataFrame({"t": b["open_time"], "r4_50": np.log(c / s50), "r4_200": np.log(c / s200),
                      "rib4": np.where((c > s50) & (s50 > s200), 1.0, np.where((c < s50) & (s50 < s200), -1.0, 0.0))})
    x.loc[s200.isna(), "rib4"] = np.nan
    dc = d["close"].astype(float)
    w350, w1400 = dc.rolling(350).mean(), dc.rolling(1400).mean()
    ribw = np.where(w1400.isna(), 0.0, np.where((dc > w350) & (w350 > w1400), 1.0, np.where((dc < w350) & (w350 < w1400), -1.0, 0.0)))
    dd = pd.DataFrame({"tc": d["close_time"], "w50": np.log(dc / w350), "w50_slope": np.log(w350).diff(5), "ribw": ribw})
    dd.loc[w350.isna(), "ribw"] = np.nan
    j = pd.merge_asof(pd.DataFrame({"tc": b["close_time"]}), dd.sort_values("tc"), on="tc", direction="backward")
    x[["w50", "w50_slope", "ribw"]] = j[["w50", "w50_slope", "ribw"]].to_numpy()
    x["sym"] = sym
    return x


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p = ext.v92.build()
    p = p.merge(pd.concat([mtf_features(ext, s) for s in ext.v92.SYMS], ignore_index=True), on=["t", "sym"], how="left")
    p["rib_agree"] = p["rib4"] + p["rib"] + p["ribw"]
    ext.v92.FEATS = [c for c in p.columns if c not in ("y", "t", "open", "sym", "bar")]
    assert all(f in ext.v92.FEATS for f in MTF)
    lo, ic = [], {}
    for a in ext.v92.ANCHORS:
        te, _ = ext.v92.train_predict(p, a)
        lo.append(te)
        ic[a] = dict(ic_v92=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4))
    W_lo = ext.v92.weights_from(pd.concat(lo, ignore_index=True), "model")
    p94 = ext.v94.add_targets(p)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = []
    for a in ext.v92.ANCHORS:
        te, _ = ext.v94.train_predict(p94, a, f94)
        ls.append(te)
        ic[a]["ic_v94"] = round(float(te[["pred", "y42"]].corr(method="spearman").iloc[0, 1]), 4)
        print(a, ic[a], flush=True)
    W94 = ext.v94.weights_ls(pd.concat(ls, ignore_index=True), True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W103 = ext.v94.weights_ls(pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True), True)
    out = {"version": "v123", "ic": ic}
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p, W_lo).reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p, W94).reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    out["secondary_v96_blend"] = v103.evaluate(p, 0.5 * b_lo + 0.5 * b94, "v123 v96 blend", scale=1.0)
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, 0.25 * b_lo + 0.25 * b94 + 0.5 * b103, 0.15, False, fee, slip))
        print("v123 portfolio", sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_portfolio"] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v123_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
