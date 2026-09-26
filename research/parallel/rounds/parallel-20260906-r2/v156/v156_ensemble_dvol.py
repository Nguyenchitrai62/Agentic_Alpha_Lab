"""v156: four-member information ensemble - v154 members + a DVOL (implied volatility) member (registry v156).

E = v144 builder with market-wide DVOL features merged on t (before the v142 xs step, no xs versions; vol models exclude
them). DVOL hourly candles (data/raw/dvol_20260924, Deribit BTC DVOL) are available at ts + 1h; each panel row t (4h bar
[t, t+4h)) takes the last candle with avail_utc <= t + 4h. Features: dvol_lvl (close), dvol_chg24 / dvol_chg168 (log
change vs 24 / 168 hourly candles earlier), dvol_z (vs trailing 2160 hourly closes, min 720), dvol_rvspread = dvol_lvl -
100 * BTC 30-day realised vol (std of the last 180 BTC 4h log returns * sqrt(2190), BTC rows of the v114 panel, known at
the bar close). NaN before 2021-03-24. Books = (A + B + D + E)/4, v144 engine rows (0.15 ungoverned, 0.20/0.25 governed).
Reference v154: 3.515/19.15 at 0.25. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v156/v156_ensemble_dvol.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DV = ("dvol_lvl", "dvol_chg24", "dvol_chg168", "dvol_z", "dvol_rvspread")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dvol_features(p92: pd.DataFrame) -> pd.DataFrame:
    d = pd.read_parquet("data/raw/dvol_20260924/dvol_hourly.parquet")
    d["avail"] = pd.to_datetime(d["avail_utc"], utc=True)
    d = d.sort_values("avail")
    c = d["dvol_close"].astype(float).where(lambda x: x > 0)
    d["dvol_lvl"] = c
    d["dvol_chg24"] = np.log(c / c.shift(24))
    d["dvol_chg168"] = np.log(c / c.shift(168))
    d["dvol_z"] = (c - c.rolling(2160, min_periods=720).mean()) / c.rolling(2160, min_periods=720).std()
    btc = p92[p92.sym == "BTCUSDT"].sort_values("t")[["t", "vol180"]].copy()
    btc["close_at"] = btc["t"] + pd.Timedelta(hours=4)
    j = pd.merge_asof(btc.sort_values("close_at"), d[["avail"] + list(DV[:4])], left_on="close_at", right_on="avail", direction="backward")
    j["dvol_rvspread"] = j["dvol_lvl"] - 100 * j["vol180"] * np.sqrt(2190)
    return j[["t"] + list(DV)]


def books_dvol():
    v144 = _load("v144_dv", "v144/v144_deploy_v3.py")
    ext, v103 = v144.v115.v114.v113, v144.v103
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103 = ext.v92.build, v103.build
    feats = dvol_features(b92())
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in DV], anchors, emb)
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    return v144.books_v142()


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    v154 = _load("v154", "v154/v154_ensemble_coinbase.py")
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, D = v154.books_coinbase()
    _, E = books_dvol()
    idx = A.index.union(B.index).union(D.index).union(E.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D, E)) / 4
    out = {"version": "v156", **v144.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v156_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
