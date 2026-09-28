"""v233: the TradingView indicator features in every foundation member (registry v233).

Why: v231 V1 (TradingView features in the annual member A only) is the first foundation gain in a long time (dev4 5.462, 5y 5.115,
DD 20.00), but the book is 0.5 annual (A, B) + 0.5 quarterly (Aq, Bq) and only A saw the new features. This version completes the
direction: the same 17 causal indicators (v231/tv_indicators.py, standard parameters) in the quarterly member A and/or in the options
member B (annual / quarterly). Members are built exactly as the audited ones (v144 builder; v202 quarterly wrapper; v150 options
features for B) with the indicators merged on (t, sym) into the v92 and v103 panels and excluded from the vol models.
Fixed before running (everything else = v218 D2 settings: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit
orders, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding):
  T1_A_both     books = 0.5 (A_tv + B)/2 + 0.5 (Aq_tv + Bq)/2
  T2_AB_annual  books = 0.5 (A_tv + B_tv)/2 + 0.5 (Aq + Bq)/2
  T3_all        books = 0.5 (A_tv + B_tv)/2 + 0.5 (Aq_tv + Bq_tv)/2
Builder check: build_member(annual, no options) must reproduce the cached v231 A_tv exactly. Reference: v231_V1 = 0.5 (A_tv + B)/2 + 0.5 (Aq + Bq)/2 (must reproduce dev4 5.462). SELECTION = robust criterion among T1..T3; the
most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v233/v233_tv_all_members.py
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


v231 = _load("v231_t", RD / "v231/v231_quality_features.py")
TV = list(v231.tvm.TV)


def build_member(quarterly: bool, options: bool):
    tag = f"{'q' if quarterly else 'a'}{'o' if options else ''}"
    v202 = _load(f"v202_{tag}", RD / "v202/v202_quarterly_retrain.py")
    if options:
        v150 = _load(f"v150_{tag}", RD / "v150/v150_options_flow.py")
        v144 = v150.v144
        OPT, ofeats = list(v150.OPT), v150.opt_features()
    else:
        v144 = _load(f"v144_{tag}", RD / "v144/v144_deploy_v3.py")
        OPT, ofeats = [], None
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    xf = v231.extra_features(("tv",), ext.v92.load_asset, None)
    drop = set(OPT) | set(TV)
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
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    B = mem.xs("B", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B"))
    m = {"A_tv": pd.read_parquet(eu.er.CACHE / "member_A_tv_annual.parquet")}
    chk = build_member(False, False).reindex(m["A_tv"].index)  # the builder must reproduce the v231 member exactly
    assert float((chk - m["A_tv"]).abs().max().max()) < 1e-12, "build_member does not reproduce member_A_tv_annual"
    print("builder check: A_tv reproduced exactly", flush=True)
    for name, q, o in (("Aq_tv", True, False), ("B_tv", False, True), ("Bq_tv", True, True)):
        cache = eu.er.CACHE / f"member_{name}.parquet"
        if not cache.exists():
            build_member(q, o).to_parquet(cache)
        m[name] = pd.read_parquet(cache)
        print("member", name, "cached", flush=True)
    m = {k: v.reindex(idx).fillna(0.0)[cols] for k, v in m.items()}
    mixes = {"v231_V1": 0.5 * (m["A_tv"] + B) / 2 + 0.5 * (Aq + Bq) / 2,
             "T1_A_both": 0.5 * (m["A_tv"] + B) / 2 + 0.5 * (m["Aq_tv"] + Bq) / 2,
             "T2_AB_annual": 0.5 * (m["A_tv"] + m["B_tv"]) / 2 + 0.5 * (Aq + Bq) / 2,
             "T3_all": 0.5 * (m["A_tv"] + m["B_tv"]) / 2 + 0.5 * (m["Aq_tv"] + m["Bq_tv"]) / 2}
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v233", "rows": {}, "trades": {}}
    for key, books in mixes.items():
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v231_V1":
            assert abs(r["monthly_dev4"] - 5.462) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("T1_A_both", "T2_AB_annual", "T3_all")})
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
    (HERE / "v233_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
