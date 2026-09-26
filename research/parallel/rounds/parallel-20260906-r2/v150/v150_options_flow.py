"""v150: Deribit BTC options-flow features (market-wide) on the v144 configuration (registry v150).

Data: data/raw/deribit_opt_20260926/BTC_options_4h.parquet (public option trades aggregated per UTC 4h bar [T, T+4h),
known at the bar close, so the options bar T joins the panel row t = T). Market features joined on t to every asset:
  opt_net6 = rolling-6 sum(put_buy - put_sell - call_buy + call_sell) / rolling-6 sum(all four)   (net bearish aggression)
  opt_pcr_z = 180-bar z-score of log((put_buy + put_sell) / (call_buy + call_sell))
  opt_skew6 = rolling-6 mean of (iv_otm_put - iv_otm_call); opt_skew_z = 180-bar z-score of the same difference
  opt_act_z = 180-bar z-score of log(n_trades)
(rolling statistics over the options bar sequence; NaN where no data / before 2019). Added to the v92/v94 panel (v114)
and the v103 panel before the v142 cross-sectional step (no xs versions: they are market-wide). Everything else = v144
(vol models on original feature sets, tranching, realistic 10 bps 1m execution, governor). Rows as v144; primary 0.25
governed. Reference v144: 2.361/16.89, 2.955/18.28, 3.374/19.63. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v150/v150_options_flow.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v144", HERE.parent / "v144" / "v144_deploy_v3.py")
v144 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v144)
OPT = ("opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z")


def opt_features():
    o = pd.read_parquet("data/raw/deribit_opt_20260926/BTC_options_4h.parquet")
    o["t"] = pd.to_datetime(o["bar"], utc=True)
    o = o.set_index("t").sort_index()
    full = pd.date_range(o.index.min(), o.index.max(), freq="4h", tz="UTC")
    o = o.reindex(full)
    for c in ("call_buy", "call_sell", "put_buy", "put_sell", "n_trades"):
        o[c] = o[c].fillna(0.0)
    z = lambda s: (s - s.rolling(180, min_periods=90).mean()) / s.rolling(180, min_periods=90).std()
    tot = o[["call_buy", "call_sell", "put_buy", "put_sell"]].sum(axis=1)
    net = o["put_buy"] - o["put_sell"] - o["call_buy"] + o["call_sell"]
    pcr = np.log((o["put_buy"] + o["put_sell"]).clip(lower=1) / (o["call_buy"] + o["call_sell"]).clip(lower=1))
    skew = o["iv_otm_put"] - o["iv_otm_call"]
    return pd.DataFrame({"t": o.index, "opt_net6": (net.rolling(6).sum() / tot.rolling(6).sum().replace(0, np.nan)).to_numpy(),
                         "opt_pcr_z": z(pcr).to_numpy(), "opt_skew6": skew.rolling(6, min_periods=3).mean().to_numpy(),
                         "opt_skew_z": z(skew).to_numpy(), "opt_act_z": z(np.log(o["n_trades"].clip(lower=1))).to_numpy()})


def main():
    feats = opt_features()
    ext = v144.v115.v114.v113
    v103 = v144.v103
    orig92, orig103 = None, v103.build
    ext_build_orig = ext.v92.build

    def build92():
        return ext_build_orig().merge(feats, on="t", how="left")

    def build103():
        return orig103().merge(feats, on="t", how="left")

    # vol models must keep the original feature sets: wrap vol_predict to drop the option columns
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in OPT], anchors, emb)
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = build92
    v103.build = build103
    p103, books = v144.books_v142()
    cover = {s: round(float(g[list(OPT)].notna().all(axis=1).mean()), 3) for s, g in p103.groupby("sym")}
    print("coverage (v103 panel rows with all option features)", cover, flush=True)
    out = {"version": "v150", "coverage": cover, **v144.simulate(p103, books)}
    out["reference_v144"] = {"t15": (2.361, 16.89), "t20": (2.955, 18.28), "t25": (3.374, 19.63)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v150_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
