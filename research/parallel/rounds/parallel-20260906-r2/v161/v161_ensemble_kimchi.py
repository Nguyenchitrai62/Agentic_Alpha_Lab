"""v161: four-member ensemble - v154 members + a Korean (Upbit) premium member (registry v161).

Premium of coin a at 4h bar t (known at the close t + 4h): kp_a = 1e4 * log(Upbit KRW-a close of the 1h candle opening at
t + 3h (asof backward within 2h) / Binance SPOT aUSDT 4h close) for a in BTC, ETH, XRP, SOL (spot 4h = 2017 prefix +
spot file; SOL spot from 2020-08). BNB is not listed on Upbit KRW -> NaN.
Market features (per t): kp_btc_dev = rolling-6 mean - rolling-540 mean of kp_btc; kp_btc_z = kp_btc_dev / rolling-540 std;
kp_btc_chg = rolling-6 mean - rolling-42 mean.
Asset features (per t, sym): rp = kp_a - kp_btc (USD/KRW cancels; 0 for BTC); rp_dev = rolling-6 mean - rolling-540 mean
of rp; rp_z = rp_dev / rolling-540 std; rp_chg = rolling-6 mean - rolling-42 mean (min periods 4/30/270 as v111).
Member K = v144 builder with these merged into the v114 and v103 panels before the v142 xs step (no xs versions; vol models
exclude them). Books = (A + B + D + K)/4; v144 engine rows. Reference v154: 3.515/19.15. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v161/v161_ensemble_kimchi.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
SP = Path("data/raw/spot_majors_20260925")
MK = ("kp_btc_dev", "kp_btc_z", "kp_btc_chg")
AS = ("rp_dev", "rp_z", "rp_chg")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def premium(coin: str) -> pd.Series:
    u = pd.read_parquet(f"data/raw/upbit_20260926/KRW-{coin}_1h.parquet")[["open_time", "close"]].rename(columns={"close": "krw"})
    u["open_time"] = pd.to_datetime(u["open_time"], utc=True)
    parts = [SP / f"{coin}USDT_spot_4h_2017.parquet", SP / f"{coin}USDT_spot_4h.parquet"]
    bn = pd.concat([pd.read_parquet(p)[["open_time", "close"]] for p in parts if p.exists()], ignore_index=True)
    bn["open_time"] = pd.to_datetime(bn["open_time"], utc=True)
    bn = bn.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    bn["key"] = bn["open_time"] + pd.Timedelta(hours=3)
    j = pd.merge_asof(bn, u.sort_values("open_time"), left_on="key", right_on="open_time", direction="backward",
                      tolerance=pd.Timedelta(hours=2), suffixes=("", "_u"))
    return pd.Series(1e4 * np.log(j["krw"].astype(float) / j["close"].astype(float)).to_numpy(), index=bn["open_time"])


def smooth(s: pd.Series):
    p6, p42 = s.rolling(6, min_periods=4).mean(), s.rolling(42, min_periods=30).mean()
    m, sd = s.rolling(540, min_periods=270).mean(), s.rolling(540, min_periods=270).std()
    return p6 - m, (p6 - m) / sd, p6 - p42


def kimchi_tables():
    kp = {c: premium(c) for c in ("BTC", "ETH", "XRP", "SOL")}
    dev, z, chg = smooth(kp["BTC"])
    market = pd.DataFrame({"t": kp["BTC"].index, "kp_btc_dev": dev.to_numpy(), "kp_btc_z": z.to_numpy(), "kp_btc_chg": chg.to_numpy()})
    rows = []
    for c in ("BTC", "ETH", "XRP", "SOL"):
        rp = (kp[c] - kp["BTC"].reindex(kp[c].index)) if c != "BTC" else kp["BTC"] * 0.0
        d_, z_, c_ = smooth(rp)
        rows.append(pd.DataFrame({"t": rp.index, "sym": f"{c}USDT", "rp_dev": d_.to_numpy(), "rp_z": z_.to_numpy(), "rp_chg": c_.to_numpy()}))
    return market, pd.concat(rows, ignore_index=True)


def books_kimchi():
    v144 = _load("v144_kp", "v144/v144_deploy_v3.py")
    market, asset = kimchi_tables()
    ext, v103 = v144.v115.v114.v113, v144.v103
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103 = ext.v92.build, v103.build
    allc = MK + AS
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in allc], anchors, emb)
    ext.v92.build = lambda: b92().merge(market, on="t", how="left").merge(asset, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(market, on="t", how="left").merge(asset, on=["t", "sym"], how="left")
    return v144.books_v142()


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    v154 = _load("v154", "v154/v154_ensemble_coinbase.py")
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, D = v154.books_coinbase()
    _, K = books_kimchi()
    idx = A.index.union(B.index).union(D.index).union(K.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D, K)) / 4
    out = {"version": "v161", **v144.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v161_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
