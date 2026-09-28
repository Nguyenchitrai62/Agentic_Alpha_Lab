"""v230: a Korean-premium ("kimchi premium") member for the executable trade mode D2 (registry v230).

Why: every trade-management layer plateaus (dev4 ~5.2, most recent year ~3.8-4.0): the foundation signal is the limit, and the only
members that ever helped were information-diverse ones that are good alone (options flow B, Coinbase premium D). The Korean retail
market (Upbit, KRW) is a separate demand pool whose premium over offshore prices swings by several percent in frenzies and capitulations;
this data (data/raw/upbit_20260926, 1h candles, UTC-aligned: lag-0 return correlation with Coinbase 0.87) was downloaded but never tested.
Data (all known at the close of 4h bar t):
  Upbit KRW-BTC / KRW-ETH / KRW-XRP 1h candles resampled to UTC 4h bars (close = the close of the hour ending at the bar close, >= 3 hours);
  Binance spot 4h close + quote volume (data/raw/spot_majors_20260925, as v111); USD/KRW daily close (Yahoo KRW=X,
  data/raw/fx_krw_20260928) used only from bar-start + 2 days (a full day of lag on top of the bar -> no look-ahead).
  premium p_c = 1e4 * log(upbit_close_c / (binance_close_c * usdkrw)), bps.
Features (market-wide, merged on t, 540-bar = 90-day rolling stats, 6/42-bar means as the v111 Coinbase features):
  kr_btc_lvl = mean6(p_btc); kr_btc_z = (mean6 - mean540) / std540; kr_btc_chg = mean6 - mean42;
  rel = mean over ETH, XRP of (p_c - p_btc) (FX-free cross-coin Korean demand): kr_alt_z, kr_alt_chg as above;
  kr_vol_z = z540 of mean6(log(Upbit KRW quote volume / usdkrw) - log(Binance spot quote volume)) over BTC+ETH+XRP.
Member K = the v144 builder (v92 long-only + v94 long/short + v103 flow, v142 xs step, v129 vol models without the kr features,
annual expanding anchors with the audited embargo) with these features merged into the v92 and v103 panels - exactly the v154 member-D
recipe with the Coinbase features replaced. Cached to artifacts/research/engine_real/member_K_annual.parquet.
Fixed before running (everything else = v218 D2: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit orders,
SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding):
  K1_add        books = 0.5 (A + B + K)/3 + 0.5 (Aq + Bq)/2          (K in the annual half)
  K2_add_both   books = 0.5 (A + B + K)/3 + 0.5 (Aq + Bq + K)/3      (K in both halves, 1/3 weight)
  K3_replace_A  books = 0.5 (K + B)/2 + 0.5 (Aq + Bq)/2              (K = A plus the Korean features)
Reference: v218_D2 = 0.5 (A + B)/2 + 0.5 (Aq + Bq)/2. Diagnostic (not selectable): K_alone = K in both halves.
SELECTION = robust criterion among K1..K3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v230/v230_korea_premium_member.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KR = ("kr_btc_lvl", "kr_btc_z", "kr_btc_chg", "kr_alt_z", "kr_alt_chg", "kr_vol_z")
UP = Path("data/raw/upbit_20260926")
SP = Path("data/raw/spot_majors_20260925")
FX = Path("data/raw/fx_krw_20260928/usdkrw_1d.csv")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upbit_4h(coin: str) -> pd.DataFrame:
    u = pd.read_parquet(UP / f"KRW-{coin}_1h.parquet")
    u["open_time"] = pd.to_datetime(u["open_time"], utc=True)
    u = u.drop_duplicates("open_time").set_index("open_time").sort_index()
    u["qv"] = u["volume"] * u["close"]
    last_hour = u.index.to_series().dt.hour % 4 == 3
    g = u.resample("4h", label="left", closed="left")
    b = pd.DataFrame({"close": g["close"].last(), "qv": g["qv"].sum(), "n": g["close"].count(),
                      "has_last": last_hour.resample("4h", label="left", closed="left").max()})
    b = b[(b["n"] >= 3) & (b["has_last"] == True)]  # the close must be the hour ending at the bar close
    return b[["close", "qv"]]


def binance_4h(coin: str) -> pd.DataFrame:
    parts = [pd.read_parquet(SP / f"{coin}USDT_spot_4h_2017.parquet"), pd.read_parquet(SP / f"{coin}USDT_spot_4h.parquet")]
    bn = pd.concat([p[["open_time", "close", "quote_volume"]] for p in parts], ignore_index=True)
    bn["open_time"] = pd.to_datetime(bn["open_time"], utc=True)
    bn = bn.drop_duplicates("open_time").set_index("open_time").sort_index()
    return bn.astype(float)


def usdkrw(index: pd.DatetimeIndex) -> pd.Series:
    fx = pd.read_csv(FX)
    fx["avail"] = pd.to_datetime(fx["ts"], utc=True) + pd.Timedelta(days=2)
    fx = fx.dropna(subset=["close"]).sort_values("avail")
    j = pd.merge_asof(pd.DataFrame({"t": index}), fx[["avail", "close"]], left_on="t", right_on="avail", direction="backward")
    return pd.Series(j["close"].to_numpy(float), index=index)


def korea_features() -> pd.DataFrame:
    bn = {c: binance_4h(c) for c in ("BTC", "ETH", "XRP")}
    up = {c: upbit_4h(c) for c in ("BTC", "ETH", "XRP")}
    idx = bn["BTC"].index
    fx = usdkrw(idx)
    prem, vol_u, vol_b = {}, 0.0, 0.0
    for c in ("BTC", "ETH", "XRP"):
        u = up[c].reindex(idx)
        b = bn[c].reindex(idx)
        prem[c] = 1e4 * np.log(u["close"] / (b["close"] * fx))
        vol_u = vol_u + (u["qv"] / fx)
        vol_b = vol_b + b["quote_volume"]

    def stats(p):
        p6, p42 = p.rolling(6, min_periods=4).mean(), p.rolling(42, min_periods=30).mean()
        m540, s540 = p.rolling(540, min_periods=270).mean(), p.rolling(540, min_periods=270).std()
        return p6, (p6 - m540) / s540, p6 - p42

    b6, bz, bchg = stats(prem["BTC"])
    rel = ((prem["ETH"] - prem["BTC"]) + (prem["XRP"] - prem["BTC"])) / 2
    _, az, achg = stats(rel)
    v = np.log(vol_u) - np.log(vol_b)
    _, vz, _ = stats(v.replace([np.inf, -np.inf], np.nan))
    f = pd.DataFrame({"t": idx, "kr_btc_lvl": b6.to_numpy(), "kr_btc_z": bz.to_numpy(), "kr_btc_chg": bchg.to_numpy(),
                      "kr_alt_z": az.to_numpy(), "kr_alt_chg": achg.to_numpy(), "kr_vol_z": vz.to_numpy()})
    return f


def books_korea():
    v144 = _load("v144_kr", HERE.parent / "v144/v144_deploy_v3.py")
    krf = korea_features()
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in KR], anchors, emb)
    ext.v92.build = lambda: b92().merge(krf, on="t", how="left")
    v103.build = lambda: b103().merge(krf, on="t", how="left")
    return v144.books_v142()


def main():
    v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B"))
    kc = eu.er.CACHE / "member_K_annual.parquet"
    if not kc.exists():
        _, K = books_korea()
        K.to_parquet(kc)
    K = pd.read_parquet(kc).reindex(idx).fillna(0.0)[cols]
    f = korea_features()
    f = f[(f.t >= pd.Timestamp("2020-09-24", tz="UTC")) & (f.t < pd.Timestamp("2025-09-24", tz="UTC"))]
    cover = {c: round(float(f[c].notna().mean()), 3) for c in KR}
    print("feature coverage 2020-09..2025-09", cover, flush=True)
    mixes = {"v218_D2": 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2,
             "K1_add": 0.5 * (A + B + K) / 3 + 0.5 * (Aq + Bq) / 2,
             "K2_add_both": 0.5 * (A + B + K) / 3 + 0.5 * (Aq + Bq + K) / 3,
             "K3_replace_A": 0.5 * (K + B) / 2 + 0.5 * (Aq + Bq) / 2,
             "K_alone_diag": K}
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v230", "feature_coverage": cover, "rows": {}, "trades": {}}
    for key, books in mixes.items():
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v218_D2":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("K1_add", "K2_add_both", "K3_replace_A")})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v230_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
