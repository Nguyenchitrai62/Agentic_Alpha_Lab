"""v139: Binance USD-M positioning metrics (open interest, long/short ratios) for the v103 book (registry v139).

Data: data/raw/um_metrics_20260926/{SYM}_metrics.parquet (5-minute rows from data.binance.vision daily 'metrics';
the same series are served live by /futures/data/*). For each 4h perp bar, take the last metrics row with
create_time <= bar close_time - 5 minutes (one-row safety lag). Features (NaN before the data starts, ~2021-12):
  oi_chg6, oi_chg42 = log change of sum_open_interest_value over 6 / 42 bars
  oi_z = 180-bar z-score of log sum_open_interest_value
  top_ls = log(sum_toptrader_long_short_ratio); top_ls_chg6 = 6-bar change; top_ls_z = 180-bar z-score
  crowd_ls_z = 180-bar z-score of log(count_long_short_ratio)
  taker_ls6 = rolling-6 mean of log(sum_taker_long_short_vol_ratio)
Added to the v103 features only (v103 targets/HGB/book unchanged); v92/v94 books unchanged. Evaluation = v133
configuration (vol-forecast sizing, tranching, v115 portfolio 15% target): three scenarios with full-path DD, v103 IC.
Reference v133: 2.44/2.222/1.95. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v139/v139_positioning.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v129", HERE.parent / "v129" / "v129_vol_forecast_sizing.py")
v129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v129)
v125, v115, v103, v110 = v129.v125, v129.v115, v129.v103, v129.v110
PD = 6
POS = ("oi_chg6", "oi_chg42", "oi_z", "top_ls", "top_ls_chg6", "top_ls_z", "crowd_ls_z", "taker_ls6")


def pos_features(panel_sym: pd.DataFrame, sym: str) -> pd.DataFrame:
    m = pd.read_parquet(f"data/raw/um_metrics_20260926/{sym}_metrics.parquet")
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.sort_values("create_time")
    b = panel_sym[["t"]].copy()
    b["key"] = b["t"] + pd.Timedelta(hours=4) - pd.Timedelta(minutes=5)
    j = pd.merge_asof(b.sort_values("key"), m, left_on="key", right_on="create_time", direction="backward",
                      tolerance=pd.Timedelta(hours=4)).sort_values("t").reset_index(drop=True)
    oi = np.log(j["sum_open_interest_value"].astype(float).where(lambda x: x > 0))
    top = np.log(j["sum_toptrader_long_short_ratio"].astype(float).where(lambda x: x > 0))
    crowd = np.log(j["count_long_short_ratio"].astype(float).where(lambda x: x > 0))
    taker = np.log(j["sum_taker_long_short_vol_ratio"].astype(float).where(lambda x: x > 0))
    z = lambda s: (s - s.rolling(180, min_periods=90).mean()) / s.rolling(180, min_periods=90).std()
    return pd.DataFrame({"t": j["t"], "sym": sym, "oi_chg6": oi.diff(6), "oi_chg42": oi.diff(42), "oi_z": z(oi),
                         "top_ls": top, "top_ls_chg6": top.diff(6), "top_ls_z": z(top), "crowd_ls_z": z(crowd),
                         "taker_ls6": taker.rolling(6, min_periods=3).mean()})


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
    pos = pd.concat([pos_features(g.sort_values("t"), s) for s, g in p103.groupby("sym")], ignore_index=True)
    p103 = p103.merge(pos, on=["t", "sym"], how="left")
    cover = {s: dict(first=str(g.loc[g[list(POS)].notna().all(axis=1), "t"].min()), share=round(float(g[list(POS)].notna().all(axis=1).mean()), 3)) for s, g in p103.groupby("sym")}
    print("coverage", cover, flush=True)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    assert all(f in f103 for f in POS)
    fl, ic = [], {}
    for a in ext.v92.ANCHORS:
        te, _ = v103.train_predict(p103, a, f103)
        fl.append(te)
        ic[a] = {f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in v103.HS}
    fl = pd.concat(fl, ignore_index=True)
    print("v103+positioning IC", ic, flush=True)
    pv92, _ = v129.vol_predict(p92, ext.v92.FEATS, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, [c for c in f103 if c not in POS], ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

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
    out = {"version": "v139", "coverage": cover, "ic_v103": ic}
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print(sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_scenarios"] = res
    out["reference_v133"] = {"normal": 2.44, "fee_stress": 2.222, "execution_stress": 1.95}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v139_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
