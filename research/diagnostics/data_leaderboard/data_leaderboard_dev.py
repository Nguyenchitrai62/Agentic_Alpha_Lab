"""Data-quality leaderboard (first four walk-forward years only; diagnostic, nothing is deployed from it).

Which exchange data sources carry STABLE predictive information for the majors? One pooled HistGradientBoosting model (5 coins, 4h rows
from 2020-01) predicts the 7-day forward return in sigma units; the model for dev year Y trains on rows whose label ended before Y - 7 days.
Every data group is added alone to the same base set, then all groups together; the report is the Spearman IC per dev year and its gain
over the base. All features are causal (known at the 4h bar close).
  base        r6 / r42 / r180 in sigma units, sigma regime, taker-buy share of the quote volume over 6 bars
  tv          17 TradingView indicators (v231)
  perp_flow   Binance perp taker ORDER flow by size (v236 formulas on aggflow_20260928_orders) = O1's information
  spot_flow   Binance spot taker order flow (aggflow_spot_20260929_orders)
  okx_flow    OKX perp taker order flow (okxflow_20260929, from 2021-10)
  bybit_flow  Bybit perp taker order flow (bybitflow_20260929)
  premium     Binance premium index / predicted funding (v231 premium_features)
  position    Binance open interest and long/short ratios (v139 definitions; BTC from 2020-09, others 2021-12)
  intrabar    1m order-level intrabar features (v252)
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

RD = Path("research/parallel/rounds/parallel-20260906-r2")
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
START = pd.Timestamp("2020-01-01", tz="UTC")
H = 42


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tvm = _load("tvm", RD / "v231/tv_indicators.py")
pfm = _load("pfm", RD / "v231/premium_features.py")
ib = _load("ib", RD / "v252/intrabar_flow.py")
FLOW_DIRS = {"perp_flow": "data/raw/aggflow_20260928_orders", "spot_flow": "data/raw/aggflow_spot_20260929_orders",
             "okx_flow": "data/raw/okxflow_20260929", "bybit_flow": "data/raw/bybitflow_20260929"}
flows = {}
for g, d in FLOW_DIRS.items():
    m = _load(f"fl_{g}", RD / "v236/flow_features.py")
    m.D = Path(d)
    flows[g] = m


def bars4h(sym):
    f = Path("data/raw/btc_intraday_20260924/klines_15m.parquet") if sym == "BTCUSDT" else Path(f"data/raw/majors_intraday_20260924/{sym}_15m.parquet")
    k = pd.read_parquet(f)
    k["open_time"] = pd.to_datetime(k["open_time"], utc=True)
    k = k.drop_duplicates("open_time").set_index("open_time").sort_index()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "quote_volume": "sum", "taker_buy_quote_volume": "sum"}
    b = k[list(agg)].astype(float).resample("4h").agg(agg).dropna(subset=["open"])
    return b[b.index >= START - pd.Timedelta(days=120)]


def position(sym, t):
    m = pd.read_parquet(f"data/raw/um_metrics_20260926/{sym}_metrics.parquet")
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.sort_values("create_time")
    key = pd.DataFrame({"t": t, "key": t + pd.Timedelta(hours=4) - pd.Timedelta(minutes=5)})
    j = pd.merge_asof(key.sort_values("key"), m, left_on="key", right_on="create_time", direction="backward",
                      tolerance=pd.Timedelta(hours=4)).sort_values("t").reset_index(drop=True)
    lg = lambda c: np.log(j[c].astype(float).where(lambda x: x > 0))
    oi, top, crowd, taker = lg("sum_open_interest_value"), lg("sum_toptrader_long_short_ratio"), lg("count_long_short_ratio"), lg("sum_taker_long_short_vol_ratio")
    z = lambda s: (s - s.rolling(180, min_periods=90).mean()) / s.rolling(180, min_periods=90).std()
    return pd.DataFrame({"oi_chg6": oi.diff(6), "oi_chg42": oi.diff(42), "oi_z": z(oi), "top_ls": top, "top_ls_chg6": top.diff(6),
                         "top_ls_z": z(top), "crowd_ls_z": z(crowd), "taker_ls6": taker.rolling(6, min_periods=3).mean()}).set_index(t)


def panel():
    rows = []
    for s in SYMS:
        b = bars4h(s)
        t = b.index
        lo = np.log(b["open"])
        o1 = lo.shift(-1)  # open of the next bar = close of bar t
        sig = o1.diff().rolling(360, min_periods=120).std()
        base = pd.DataFrame({f"r{h}": o1.diff(h) / (sig * np.sqrt(h)) for h in (6, 42, 180)}, index=t)
        base["vol_reg"] = sig / sig.rolling(540, min_periods=180).median()
        base["taker6"] = b["taker_buy_quote_volume"].rolling(6).sum() / b["quote_volume"].rolling(6).sum().replace(0, np.nan)
        y = (lo.shift(-1 - H) - o1) / (sig * np.sqrt(H))
        g = {"base": base, "tv": tvm.tv_features(b.reset_index().rename(columns={"index": "open_time"})).set_index(t)}
        for k, mod in flows.items():
            p = Path(FLOW_DIRS[k]) / f"{s}_flow_4h.parquet"
            g[k] = (mod.flow_features(s, t) if p.exists() else pd.DataFrame(index=t, columns=list(mod.FL), dtype=float)).add_prefix(k[:3] + "_")
        g["premium"] = pfm.premium_features(s, t)
        g["position"] = position(s, t)
        g["intrabar"] = ib.intrabar_features(s, t)
        df = pd.concat([v.reindex(t) for v in g.values()], axis=1)
        df["y"], df["sym"], df["t"] = y, s, t
        rows.append(df[(t >= START)])
        print(s, "rows", int((t >= START).sum()), flush=True)
    return pd.concat(rows, ignore_index=True), {k: list(v.columns) for k, v in g.items()}


def main():
    P, groups = panel()
    P = P[np.isfinite(P["y"])].reset_index(drop=True)
    label_end = P["t"] + pd.Timedelta(hours=4 * (H + 1))
    configs = {"base": ["base"]} | {f"base+{g}": ["base", g] for g in groups if g != "base"} | {"all": list(groups)}
    out = {}
    for name, gs in configs.items():
        cols = [c for g in gs for c in groups[g]]
        ics = []
        for j in range(4):
            tr = (label_end < ANCHORS[j] - pd.Timedelta(days=7)).to_numpy()
            te = ((P["t"] >= ANCHORS[j]) & (P["t"] < ANCHORS[j + 1])).to_numpy()
            mdl = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=200, l2_regularization=1.0,
                                                random_state=0).fit(P.loc[tr, cols].to_numpy(float), P.loc[tr, "y"].clip(-4, 4).to_numpy(float))
            pr = mdl.predict(P.loc[te, cols].to_numpy(float))
            ics.append(round(float(pd.Series(pr).corr(P.loc[te, "y"].reset_index(drop=True), method="spearman")), 4))
        out[name] = {"ic_by_year": ics, "mean": round(float(np.mean(ics)), 4), "min": round(float(np.min(ics)), 4)}
        print(name, out[name], flush=True)
    b = out["base"]["ic_by_year"]
    for name in out:
        out[name]["gain_by_year"] = [round(x - y, 4) for x, y in zip(out[name]["ic_by_year"], b)]
        out[name]["gain_positive_years"] = int(sum(g > 0 for g in out[name]["gain_by_year"]))
    Path("research/diagnostics/data_leaderboard/data_leaderboard_dev.json").write_text(json.dumps(out, indent=1))
    print("LEADERBOARD (gain over base, per dev year):")
    for name in sorted(out, key=lambda k: -out[k]["mean"]):
        print(f"  {name:18s} mean IC {out[name]['mean']:+.4f}  min {out[name]['min']:+.4f}  gains {out[name]['gain_by_year']}  (+ in {out[name]['gain_positive_years']}/4)")


if __name__ == "__main__":
    main()
