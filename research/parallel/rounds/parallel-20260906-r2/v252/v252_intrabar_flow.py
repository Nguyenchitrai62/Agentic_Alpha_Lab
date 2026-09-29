"""v252: INTRABAR whale flow (1m order-level store) in the O1 foundation members.

Why: the only changes that lifted the unseen year were new foundation information - TradingView indicators (T3) and taker whale flow
(W2 fills -> O1 orders). Every management layer on top (v241-v251) lifted the dev mean but not the unseen year. The 4h tier table only
says how much large-order flow a bar had; the 1m order-level store (re-downloaded 2026-09-29 and kept) says WHEN inside the bar and
AGAINST WHAT price move it traded: late-bar whale pressure, whales absorbing down-minutes vs chasing, the 30k-100k tier, and one-minute
bursts (v252/intrabar_flow.py; bar t aggregates minutes t .. t+239 only, known at the close).
Fixed before running.
Data: data/raw/aggflow_20260929_orders_1m (scripts/fetch_aggtrades_flow.py --orders --out data/raw/aggflow_20260929_orders, same Binance
archive as O1; the 4h totals equal the audited O1 table), Binance 1m klines for the minute returns.
Members as in v240 O1 (v144 builder annual + v202 quarterly wrapper, A = TradingView + order-level flow); new features are added to the A
members only and excluded from the vol models; B members = T3 (unchanged).
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings otherwise).
  I1_intrabar_all   A + fi_big_imb_last1h, fi_absorb6, fi_mid_imb6, fi_burst_z
  I2_intrabar_core  A + fi_big_imb_last1h, fi_absorb6
Reference: v247_B18 (O1 members, must reproduce dev4 5.777). SELECTION = robust criterion among I1, I2; the most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v252/v252_intrabar_flow.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
BUDGET = 0.18
VARIANTS = {"I1_intrabar_all": ("fi_big_imb_last1h", "fi_absorb6", "fi_mid_imb6", "fi_burst_z"),
            "I2_intrabar_core": ("fi_big_imb_last1h", "fi_absorb6")}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v240 = _load("v240_i", RD / "v240/v240_order_level_flow.py")
ib = _load("intrabar_flow", HERE / "intrabar_flow.py")
_TABLES: dict = {}


def feature_frame(load_asset, feats) -> pd.DataFrame:
    base = v240.feature_frame(load_asset, False)
    rows = []
    for s in v240.SYMS:
        b, _, _ = load_asset(s)
        t = pd.DatetimeIndex(b["open_time"])
        if s not in _TABLES:
            _TABLES[s] = ib.bar_table(s)
        x = ib.intrabar_features(s, t, _TABLES[s])[list(feats)].reset_index(drop=True)
        rows.append(pd.concat([pd.DataFrame({"t": t, "sym": s}), x], axis=1))
    return base.merge(pd.concat(rows, ignore_index=True), on=["t", "sym"], how="left")


def build_member(quarterly: bool, feats):
    tag = f"{'q' if quarterly else 'a'}_i{len(feats)}"
    v202 = _load(f"v202_{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    xf = feature_frame(ext.v92.load_asset, feats)
    drop = {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)
    ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
    return v144.books_v142()[1]


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    base = {k: pd.read_parquet(C / f) for k, f in (("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"),
                                                    ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    mixes = {"v247_B18": base}
    for key, feats in VARIANTS.items():
        mm = {"B": base["B"], "Bq": base["Bq"]}
        for name, q in (("A", False), ("Aq", True)):
            cache = C / f"member_{name}_{key}.parquet"
            if not cache.exists():
                build_member(q, feats).to_parquet(cache)
            mm[name] = pd.read_parquet(cache)
            print("member", name, key, "cached", flush=True)
        mixes[key] = mm
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    out = {"version": "v252", "variants": VARIANTS, "rows": {}, "trades": {}}
    for key, mm in mixes.items():
        m = {k: v.reindex(idx).fillna(0.0)[cols] for k, v in mm.items()}
        books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "O1 members at budget 0.18 must reproduce v247 B18"
    sel = v204.robust_select({k: out["rows"][k] for k in VARIANTS})
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
    (HERE / "v252_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
