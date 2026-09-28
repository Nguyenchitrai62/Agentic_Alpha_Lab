"""v231: quality-data features for the foundation member A - TradingView indicators and exact premium / predicted funding (registry v231).

Why (user 2026-09-28): search for quality data instead of more blind logic. (1) The models only see basic transforms (returns / SNR,
vol, EMA distances, daily ribbon, settled-funding means, taker flow); stateful trader indicators (SuperTrend, squeeze, WaveTrend,
VIX Fix, Ichimoku, anchored VWAP, volume-profile POC, market-structure breaks, Fisher) are hard for a depth-4 tree to rebuild from
returns. (2) The funding actually paid follows the 1m premium index; the settled rate alone hides the path and the last-minute
pressure (funding hunters). Binance 1m premium-index klines 2020-01.. (data/raw/binance_premium_20260928) reconstruct the settled BTC
rate with MAE 0.05 bp (90% within 0.1 bp), so the predicted funding is known causally at every bar close. The Fear & Greed index
(alternative.me, v159 timing: value of UTC day D usable from D 01:00) joins the crowd-positioning group.
Features (fixed lists, standard parameters, no tuning): tv_indicators.TV (17, per asset, from the panel's own 4h bars; causality test
tests/test_tv_indicators.py); premium_features.PF (7, per asset, NaN before 2020-01 as the options / Coinbase members before their
data); v159 FNG (4, market-wide).
Member A' = the v144 builder (v92 long-only + v94 long/short + v103 flow, v142 xs step, v129 vol models WITHOUT the new features,
annual expanding anchors, audited embargo) with the new features merged on (t, sym) into the v92 and v103 panels.
Fixed before running (everything else = v218 D2: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit orders,
SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding):
  V1_tv         books = 0.5 (A_tv + B)/2 + 0.5 (Aq + Bq)/2
  V2_prem_fng   books = 0.5 (A_pf + B)/2 + 0.5 (Aq + Bq)/2
  V3_all        books = 0.5 (A_all + B)/2 + 0.5 (Aq + Bq)/2
Reference: v218_D2 = 0.5 (A + B)/2 + 0.5 (Aq + Bq)/2.
SELECTION = robust criterion among V1..V3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v231/v231_quality_features.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tvm = _load("tv_indicators", HERE / "tv_indicators.py")
pfm = _load("premium_features", HERE / "premium_features.py")
v159 = _load("v159_q", HERE.parent / "v159/v159_ensemble_fng.py")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def extra_features(groups, load_asset, times):
    """Per-(t, sym) frame of the requested groups ('tv', 'pf', 'fng')."""
    rows = []
    for s in SYMS:
        b, _, _ = load_asset(s)
        x = pd.DataFrame({"t": b["open_time"].to_numpy(), "sym": s})
        if "tv" in groups:
            x = pd.concat([x, tvm.tv_features(b).reset_index(drop=True)], axis=1)
        if "pf" in groups:
            pf = pfm.premium_features(s, pd.DatetimeIndex(b["open_time"]))
            x = pd.concat([x, pf.reset_index(drop=True)], axis=1)
        rows.append(x)
    out = pd.concat(rows, ignore_index=True)
    if "fng" in groups:
        out = out.merge(v159.fng_features(pd.Series(times)), on="t", how="left")
    return out


def names(groups):
    return (list(tvm.TV) if "tv" in groups else []) + (list(pfm.PF) if "pf" in groups else []) + (list(v159.FNG) if "fng" in groups else [])


def books_with(groups):
    v144 = _load("v144_q_" + "_".join(groups), HERE.parent / "v144/v144_deploy_v3.py")
    ext, v103 = v144.v115.v114.v113, v144.v103
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103 = ext.v92.build, v103.build
    base92 = b92()
    xf = extra_features(groups, ext.v92.load_asset, base92["t"].unique())
    new = names(groups)
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in new], anchors, emb)
    ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
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
    members = {}
    for key, groups in (("tv", ("tv",)), ("pf", ("pf", "fng")), ("all", ("tv", "pf", "fng"))):
        cache = eu.er.CACHE / f"member_A_{key}_annual.parquet"
        if not cache.exists():
            _, M = books_with(groups)
            M.to_parquet(cache)
        members[key] = pd.read_parquet(cache).reindex(idx).fillna(0.0)[cols]
        print("member", key, "cached", flush=True)
    mixes = {"v218_D2": 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2,
             "V1_tv": 0.5 * (members["tv"] + B) / 2 + 0.5 * (Aq + Bq) / 2,
             "V2_prem_fng": 0.5 * (members["pf"] + B) / 2 + 0.5 * (Aq + Bq) / 2,
             "V3_all": 0.5 * (members["all"] + B) / 2 + 0.5 * (Aq + Bq) / 2}
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v231", "rows": {}, "trades": {},
           "premium_reconstruction_check": {s: pfm.validate(s) for s in SYMS}}
    print("premium reconstruction", out["premium_reconstruction_check"], flush=True)
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
    sel = v204.robust_select({k: out["rows"][k] for k in ("V1_tv", "V2_prem_fng", "V3_all")})
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
    (HERE / "v231_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
