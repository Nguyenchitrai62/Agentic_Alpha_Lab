"""v159: four-member ensemble - v154 members + a Crypto Fear & Greed member (registry v159, track B).

Data: data/raw/fng_20260926/fng_daily.parquet (alternative.me, daily since 2018-02-01). The value for UTC date D is used
from D 01:00 UTC (published at 00:00, +1h safety). Market-wide features for panel row t (bar close t + 4h): fng (last
value available at the close), fng7 (mean of the last 7 daily values), fng_chg7 (fng - value 7 days earlier), fng_z
(z-score vs trailing 90 daily values, min 60). Member G = v144 builder with these merged on t before the v142 xs step (no
xs versions; vol models exclude them). Books = (A + B + D + G)/4 (A = v144, B = v150 options member, D = v154 Coinbase
member); v144 engine rows. Reference v154: 3.515/19.15. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v159/v159_ensemble_fng.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
FNG = ("fng", "fng7", "fng_chg7", "fng_z")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fng_features(times: pd.Series) -> pd.DataFrame:
    d = pd.read_parquet("data/raw/fng_20260926/fng_daily.parquet").sort_values("date")
    d["avail"] = pd.to_datetime(d["date"], utc=True) + pd.Timedelta(hours=1)
    v = d["fng"].astype(float)
    d["fng7"] = v.rolling(7).mean()
    d["fng_chg7"] = v - v.shift(7)
    d["fng_z"] = (v - v.rolling(90, min_periods=60).mean()) / v.rolling(90, min_periods=60).std()
    b = pd.DataFrame({"t": times.sort_values().to_numpy()})
    b["close_at"] = b["t"] + pd.Timedelta(hours=4)
    j = pd.merge_asof(b, d[["avail", "fng", "fng7", "fng_chg7", "fng_z"]], left_on="close_at", right_on="avail", direction="backward")
    return j[["t"] + list(FNG)]


def books_fng():
    v144 = _load("v144_fng", "v144/v144_deploy_v3.py")
    ext, v103 = v144.v115.v114.v113, v144.v103
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103 = ext.v92.build, v103.build
    feats = fng_features(pd.Series(b92()["t"].unique()))
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in FNG], anchors, emb)
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
    _, G = books_fng()
    idx = A.index.union(B.index).union(D.index).union(G.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D, G)) / 4
    out = {"version": "v159", **v144.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v159_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
