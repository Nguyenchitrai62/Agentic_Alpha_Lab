"""v236: large-order ("whale") vs retail taker flow from Binance aggTrades in the T3 foundation (registry v236).

Why: the foundation's flow features (v103: taker-buy ratio, trade size / count z) come from the 4h klines, which mix every order size.
aggTrades (one row per taker order fill) separate large orders from retail ones - information the klines do not contain. Data:
data/raw/aggflow_20260928 (scripts/fetch_aggtrades_flow.py, 2020-01.., per 4h bar and notional tier the taker buy / sell notional and
count); features v236/flow_features.FL (6 per asset, rows known at the bar close, NaN before the archive as the other late data).
Members are built as in v233/v234 (v144 builder, v202 quarterly wrapper, v150 options features for B) with the 4h TradingView set
(= T3) plus the flow features, all excluded from the vol models.
Fixed before running (everything else = v218 D2 settings: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit
orders, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding):
  W1_flow_all      T3 members + flow features in all four members
  W2_flow_A        flow features in the A members (annual + quarterly) only, B members = T3
Reference: v233_T3 (must reproduce dev4 5.485). SELECTION = robust criterion among W1, W2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v236/v236_whale_flow.py
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


v231 = _load("v231_w", RD / "v231/v231_quality_features.py")
flm = _load("flow_features", HERE / "flow_features.py")
tvm = v231.tvm
SYMS = v231.SYMS


def feature_frame(load_asset) -> pd.DataFrame:
    """Per-(t, sym): the 4h TradingView set (T3) + the whale-flow set."""
    rows = []
    for s in SYMS:
        b, _, _ = load_asset(s)
        t = pd.DatetimeIndex(b["open_time"])
        x = pd.concat([pd.DataFrame({"t": t, "sym": s}), tvm.tv_features(b).reset_index(drop=True),
                       flm.flow_features(s, t).reset_index(drop=True)], axis=1)
        rows.append(x)
    return pd.concat(rows, ignore_index=True)


def build_member(quarterly: bool, options: bool):
    tag = f"{'q' if quarterly else 'a'}{'o' if options else ''}_w"
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
    xf = feature_frame(ext.v92.load_asset)
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
    fw = {}
    for name, q, o in (("A", False, False), ("Aq", True, False), ("B", False, True), ("Bq", True, True)):
        cache = C / f"member_{name}_whale.parquet"
        if not cache.exists():
            build_member(q, o).to_parquet(cache)
        fw[name] = pd.read_parquet(cache)
        print("member", name, "whale cached", flush=True)
    mixes = {"v233_T3": t3, "W1_flow_all": fw, "W2_flow_A": {"A": fw["A"], "Aq": fw["Aq"], "B": t3["B"], "Bq": t3["Bq"]}}
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v236", "rows": {}, "trades": {}}
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
    sel = v204.robust_select({k: out["rows"][k] for k in ("W1_flow_all", "W2_flow_A")})
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
    (HERE / "v236_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
