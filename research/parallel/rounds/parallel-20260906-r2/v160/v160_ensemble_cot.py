"""v160: four-member ensemble - v154 members + a CFTC COT (CME Bitcoin futures positioning) member (registry v160).

Data: data/raw/cftc_20260926/btc_cme_tff.parquet (CFTC Traders in Financial Futures, BITCOIN - CHICAGO MERCANTILE EXCHANGE,
weekly 2018-04..2026-09). A report dated Tuesday D is used from D + 4 days 00:00 UTC (Saturday after the Friday release).
Features (market-wide, as-of the bar close t + 4h): cot_lev_net = (Lev_Money long - short)/Open_Interest_All,
cot_am_net = (Asset_Mgr long - short)/Open_Interest_All, cot_lev_chg4 / cot_am_chg4 = change vs 4 reports earlier,
cot_lev_z / cot_am_z = z vs trailing 52 reports (min 26). Member H = v144 builder with these merged on t before the xs
step (no xs versions; vol models exclude them). Books = (A + B + D + H)/4; v144 engine rows. Reference v154:
3.515/19.15. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v160/v160_ensemble_cot.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
COT = ("cot_lev_net", "cot_am_net", "cot_lev_chg4", "cot_am_chg4", "cot_lev_z", "cot_am_z")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cot_features(times: pd.Series) -> pd.DataFrame:
    d = pd.read_parquet("data/raw/cftc_20260926/btc_cme_tff.parquet")
    d["date"] = pd.to_datetime(d["Report_Date_as_YYYY-MM-DD"], utc=True)
    d = d.sort_values("date").drop_duplicates("date")
    oi = d["Open_Interest_All"].astype(float)
    lev = (d["Lev_Money_Positions_Long_All"].astype(float) - d["Lev_Money_Positions_Short_All"].astype(float)) / oi
    am = (d["Asset_Mgr_Positions_Long_All"].astype(float) - d["Asset_Mgr_Positions_Short_All"].astype(float)) / oi
    z = lambda s: (s - s.rolling(52, min_periods=26).mean()) / s.rolling(52, min_periods=26).std()
    f = pd.DataFrame({"avail": d["date"] + pd.Timedelta(days=4), "cot_lev_net": lev, "cot_am_net": am, "cot_lev_chg4": lev - lev.shift(4),
                      "cot_am_chg4": am - am.shift(4), "cot_lev_z": z(lev), "cot_am_z": z(am)})
    b = pd.DataFrame({"t": times.sort_values().to_numpy()})
    b["close_at"] = b["t"] + pd.Timedelta(hours=4)
    j = pd.merge_asof(b, f.sort_values("avail"), left_on="close_at", right_on="avail", direction="backward")
    return j[["t"] + list(COT)]


def books_cot():
    v144 = _load("v144_cot", "v144/v144_deploy_v3.py")
    ext, v103 = v144.v115.v114.v113, v144.v103
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103 = ext.v92.build, v103.build
    feats = cot_features(pd.Series(b92()["t"].unique()))
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in COT], anchors, emb)
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
    _, H = books_cot()
    idx = A.index.union(B.index).union(D.index).union(H.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D, H)) / 4
    out = {"version": "v160", **v144.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v160_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
