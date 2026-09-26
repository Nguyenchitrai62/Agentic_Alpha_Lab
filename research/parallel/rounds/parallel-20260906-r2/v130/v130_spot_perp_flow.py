"""v130: spot-vs-perp flow and basis features for the v103 short-horizon book (registry parallel-20260906-r2 / v130).

Per asset, joined on 4h open_time between the USD-M perp bar and the Binance SPOT bar
(data/raw/spot_majors_20260925/{SYM}_spot_4h.parquet); NaN for rows before the first USD-M perp bar (those panel rows
are the spot prefix itself):
  sp_share_z  = 180-bar z-score of log(spot quote_volume / perp quote_volume)
  sp_share_chg = rolling-6 mean - rolling-42 mean of log(spot qv / perp qv)
  tbr_gap6, tbr_gap42 = rolling means of (spot taker-buy ratio - perp taker-buy ratio)
  basis6 = rolling-6 mean of 1e4*log(perp close / spot close); basis_chg = basis6 - rolling-42 mean;
  basis_z = (basis6 - rolling-180 mean) / rolling-180 std
Added to the v103 features (v103 targets/HGB/book unchanged). Primary: v115 portfolio (v92/v94 books on the v114 panel
unchanged, 0.5 weight on the new v103 book) evaluated as the PHASE MEAN over six rebalance phases (v126 method);
reference = v126 phase mean (2.311/2.09/1.815%/month). Secondary: the new LS book alone (phase 0). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v130/v130_spot_perp_flow.py
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
v125, v115, v103 = v129.v125, v129.v115, v129.v103
SP = ("sp_share_z", "sp_share_chg", "tbr_gap6", "tbr_gap42", "basis6", "basis_chg", "basis_z")
PERP = {"BTCUSDT": Path("data/raw/ma_ribbon_20260924/klines_4h.parquet")}
PERP.update({s: Path(f"data/raw/xs_universe_20260924/{s}_4h.parquet") for s in ("ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")})


def sp_features(sym):
    pp = pd.read_parquet(PERP[sym])
    sp = pd.read_parquet(f"data/raw/spot_majors_20260925/{sym}_spot_4h.parquet")
    for d in (pp, sp):
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    j = pp.merge(sp, on="open_time", suffixes=("_p", "_s")).sort_values("open_time").reset_index(drop=True)
    qp, qs = j["quote_volume_p"].astype(float).clip(lower=1), j["quote_volume_s"].astype(float).clip(lower=1)
    share = np.log(qs / qp)
    tp = (j["taker_buy_quote_volume_p"].astype(float) / qp).clip(0, 1)
    ts = (j["taker_buy_quote_volume_s"].astype(float) / qs).clip(0, 1)
    basis = 1e4 * np.log(j["close_p"].astype(float) / j["close_s"].astype(float))
    b6 = basis.rolling(6).mean()
    x = pd.DataFrame({"t": j["open_time"],
                      "sp_share_z": (share - share.rolling(180).mean()) / share.rolling(180).std(),
                      "sp_share_chg": share.rolling(6).mean() - share.rolling(42).mean(),
                      "tbr_gap6": (ts - tp).rolling(6).mean(), "tbr_gap42": (ts - tp).rolling(42).mean(),
                      "basis6": b6, "basis_chg": b6 - basis.rolling(42).mean(),
                      "basis_z": (b6 - basis.rolling(180).mean()) / basis.rolling(180).std()})
    x["sym"] = sym
    return x


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
    p103 = v103.build().merge(pd.concat([sp_features(s) for s in ext.v92.SYMS], ignore_index=True), on=["t", "sym"], how="left")
    cover = {s: round(float(g[list(SP)].notna().all(axis=1).mean()), 3) for s, g in p103.groupby("sym")}
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    assert all(f in f103 for f in SP)
    fl, ic = [], {}
    for a in ext.v92.ANCHORS:
        te, _ = v103.train_predict(p103, a, f103)
        fl.append(te)
        ic[a] = {f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in v103.HS}
    fl = pd.concat(fl, ignore_index=True)
    print("coverage", cover, "IC", ic, flush=True)
    out = {"version": "v130", "coverage": cover, "ic": ic}
    out["secondary_ls_book"] = v103.evaluate(p103, ext.v94.weights_ls(fl, True), "v130 LS book")
    out["primary_phase_mean"] = v129.phase_mean(ext, p92, p103, lo, ls, fl)
    print("v130 portfolio phase mean", {sc: (v["monthly_pct"], v["worst_year_dd"]) for sc, v in out["primary_phase_mean"].items()}, flush=True)
    out["reference_v126_phase_mean"] = {"normal": 2.311, "fee_stress": 2.09, "execution_stress": 1.815}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v130_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
