"""v234: higher-timeframe TradingView indicators (daily / weekly) in every foundation member (registry v234).

Why: v231 / v233 showed that trader indicators on the 4h bars are the first foundation gain in a long time (v233 T3: dev4 5.485,
5y 5.156, DD 18.41). Traders confirm a 4h setup with the higher-timeframe trend (daily / weekly SuperTrend, market structure, cloud,
VIX Fix); a depth-4 tree on 4h returns cannot rebuild those states either.
Features (fixed before running): the same 17 indicators (v231/tv_indicators.py, standard parameters) computed on
  1D bars  = the panel's daily klines (load_asset's d), suffix _1d, usable from the daily bar's close (open_time + 1 day);
  1W bars  = the daily bars aggregated to Monday-start UTC weeks (complete weeks only), suffix _1w, usable from week start + 7 days;
merged into each 4h row by availability time <= the 4h bar close (merge_asof, backward). Members are built as in v233
(v144 builder, v202 quarterly wrapper, v150 options features for B), each with the 4h TV set plus the new sets, all excluded from
the vol models.
Everything else = v218 D2 settings (v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit orders, SL market /
TP limit, governor, aligned sleeve, Bybit fees, adverse funding).
  H1_daily         4h + 1D indicators in all four members
  H2_daily_weekly  4h + 1D + 1W indicators in all four members
Reference: v233_T3 (4h indicators in all four members, must reproduce dev4 5.485). SELECTION = robust criterion among H1, H2; the most
recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v234/v234_htf_indicators.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v231 = _load("v231_h", RD / "v231/v231_quality_features.py")
tvm = v231.tvm
SYMS = v231.SYMS


def weekly(d: pd.DataFrame) -> pd.DataFrame:
    x = d.set_index("open_time")
    g = x.resample("W-MON", label="left", closed="left")
    w = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                      "volume": g["volume"].sum(), "n": g["close"].count()})
    w = w[w["n"] == 7].drop(columns="n").reset_index()
    return w


def htf_frame(load_asset, tfs) -> pd.DataFrame:
    """Per-(t, sym) frame: 4h TV set + the requested higher-timeframe sets, each value usable only after its bar closed."""
    rows = []
    for s in SYMS:
        b, d, _ = load_asset(s)
        x = pd.concat([pd.DataFrame({"t": b["open_time"].to_numpy(), "sym": s}), tvm.tv_features(b).reset_index(drop=True)], axis=1)
        close_at = pd.DataFrame({"close_at": b["open_time"] + pd.Timedelta(hours=4)})
        for tf in tfs:
            bars = d[["open_time", "open", "high", "low", "close", "volume"]].copy() if tf == "1d" else weekly(d)
            bars["open_time"] = pd.to_datetime(bars["open_time"], utc=True)
            f = tvm.tv_features(bars.reset_index(drop=True)).add_suffix(f"_{tf}")
            f["avail"] = (bars["open_time"] + pd.Timedelta(days=1 if tf == "1d" else 7)).to_numpy()
            j = pd.merge_asof(close_at, f.sort_values("avail"), left_on="close_at", right_on="avail", direction="backward")
            x = pd.concat([x, j.drop(columns=["close_at", "avail"])], axis=1)
        rows.append(x)
    return pd.concat(rows, ignore_index=True)


def build_member(quarterly: bool, options: bool, tfs):
    tag = f"{'q' if quarterly else 'a'}{'o' if options else ''}_{'_'.join(tfs)}"
    v202 = _load(f"v202_{tag}", RD / "v202/v202_quarterly_retrain.py")
    if options:
        v150 = _load(f"v150_{tag}", RD / "v150/v150_options_flow.py")
        v144, OPT, ofeats = v150.v144, list(v150.OPT), v150.opt_features()
    else:
        v144, OPT, ofeats = _load(f"v144_{tag}", RD / "v144/v144_deploy_v3.py"), [], None
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    xf = htf_frame(ext.v92.load_asset, tfs)
    drop = set(OPT) | {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)

    def add(p):
        if ofeats is not None:
            p = p.merge(ofeats, on="t", how="left")
        return p.merge(xf, on=["t", "sym"], how="left")
    ext.v92.build = lambda: add(base92)
    v103.build = lambda: add(b103())
    return v144.books_v142()[1]


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    t3 = {k: pd.read_parquet(C / f) for k, f in (("A", "member_A_tv_annual.parquet"), ("Aq", "member_Aq_tv.parquet"),
                                                  ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    mixes = {"v233_T3": t3}
    for key, tfs in (("H1_daily", ("1d",)), ("H2_daily_weekly", ("1d", "1w"))):
        mm = {}
        for name, q, o in (("A", False, False), ("Aq", True, False), ("B", False, True), ("Bq", True, True)):
            cache = C / f"member_{name}_{key}.parquet"
            if not cache.exists():
                build_member(q, o, tfs).to_parquet(cache)
            mm[name] = pd.read_parquet(cache)
            print("member", name, key, "cached", flush=True)
        mixes[key] = mm
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v234", "rows": {}, "trades": {}}
    for key, mm in mixes.items():
        m = {k: v.reindex(idx).fillna(0.0)[cols] for k, v in mm.items()}
        books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v233_T3":
            assert abs(r["monthly_dev4"] - 5.485) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("H1_daily", "H2_daily_weekly")})
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
    (HERE / "v234_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
