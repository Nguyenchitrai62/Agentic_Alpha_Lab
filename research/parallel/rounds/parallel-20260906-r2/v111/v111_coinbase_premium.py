"""v111: Coinbase premium features (registry parallel-20260906-r2 / v111).

Premium for P in (BTC, ETH) at each 4h bar T (known at the bar close T+4h):
  cbp = 1e4 * log(Coinbase P-USD close of the 1h candle opening at T+3h / Binance SPOT PUSDT 4h close)
(Coinbase: data/raw/coinbase_20260925/{P}-USD_1h.parquet, asof-backward within 2h if the candle is missing; Binance spot
4h = the 2017 prefix file + data/raw/spot_majors_20260925/{P}USDT_spot_4h.parquet, deduplicated).
Market features joined to every asset by t:
  cb_btc_dev = rolling-6 mean - rolling-540 mean of BTC cbp (bps; raw levels are excluded because 2017-18 levels are
               extreme and would act as a time proxy)
  cb_btc_z = (rolling-6 mean - rolling-540 mean) / rolling-540 std of BTC cbp (removes USDT/USD drift, e.g. 2018)
  cb_btc_chg = rolling-6 mean - rolling-42 mean of BTC cbp
  cb_eth_z, cb_eth_chg = the same for ETH
Primary: v103 (1d/3d targets, v92 + flow features, LS daily book, 20% vol target) + these five features.
Secondary: v92 (7d, long-only book, 20% vol target) + these five features. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v111/v111_coinbase_premium.py
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


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
CB = ("cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg")
SP = Path("data/raw/spot_majors_20260925")


def premium(asset: str) -> pd.DataFrame:
    cb = pd.read_parquet(f"data/raw/coinbase_20260925/{asset}-USD_1h.parquet")[["open_time", "close"]].rename(columns={"close": "cb"})
    cb["open_time"] = pd.to_datetime(cb["open_time"], utc=True)
    parts = [pd.read_parquet(SP / f"{asset}USDT_spot_4h_2017.parquet"), pd.read_parquet(SP / f"{asset}USDT_spot_4h.parquet")]
    bn = pd.concat([p[["open_time", "close"]] for p in parts], ignore_index=True)
    bn["open_time"] = pd.to_datetime(bn["open_time"], utc=True)
    bn = bn.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    bn["key"] = bn["open_time"] + pd.Timedelta(hours=3)
    j = pd.merge_asof(bn, cb.sort_values("open_time"), left_on="key", right_on="open_time", direction="backward",
                      tolerance=pd.Timedelta(hours=2), suffixes=("", "_cb"))
    p = pd.DataFrame({"t": bn["open_time"], "cbp": 1e4 * np.log(j["cb"].astype(float) / j["close"].astype(float))})
    p6, p42 = p["cbp"].rolling(6, min_periods=4).mean(), p["cbp"].rolling(42, min_periods=30).mean()
    m540, s540 = p["cbp"].rolling(540, min_periods=270).mean(), p["cbp"].rolling(540, min_periods=270).std()
    return pd.DataFrame({"t": p["t"], "dev": p6 - m540, "z": (p6 - m540) / s540, "chg": p6 - p42})


def add_cb(panel: pd.DataFrame) -> pd.DataFrame:
    b, e = premium("BTC"), premium("ETH")
    feat = pd.DataFrame({"t": b["t"], "cb_btc_dev": b["dev"], "cb_btc_z": b["z"], "cb_btc_chg": b["chg"]})
    feat = feat.merge(pd.DataFrame({"t": e["t"], "cb_eth_z": e["z"], "cb_eth_chg": e["chg"]}), on="t", how="left")
    return panel.merge(feat, on="t", how="left")


def main():
    panel = add_cb(v103.build())
    cover = {s: round(float(g[list(CB)].notna().all(axis=1).mean()), 3) for s, g in panel.groupby("sym")}
    print("coverage", cover, flush=True)
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    assert all(f in feats for f in CB)
    oos, ic = [], {}
    for a in v92.ANCHORS:
        te, _ = v103.train_predict(panel, a, feats)
        oos.append(te)
        ic[a] = {f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in v103.HS}
        print(a, ic[a], flush=True)
    out = {"version": "v111", "coverage": cover, "ic_short": ic}
    out["primary_v103_plus_cb_ls"] = v103.evaluate(panel, v94.weights_ls(pd.concat(oos, ignore_index=True), True), "v103+cb LS")
    p92 = add_cb(v92.build())
    v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    preds, ic2 = [], {}
    for a in v92.ANCHORS:
        te, _ = v92.train_predict(p92, a)
        preds.append(te)
        ic2[a] = round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4)
    print("v92+cb IC", ic2, flush=True)
    W = v92.weights_from(pd.concat(preds, ignore_index=True), "model")
    out["ic_v92_cb"] = ic2
    out["secondary_v92_plus_cb_lo"] = v103.evaluate(p92, W, "v92+cb LO", scale=v92.vol_target_scale(p92, W))
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v111_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
