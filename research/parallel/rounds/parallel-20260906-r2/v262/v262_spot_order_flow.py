"""v262: SPOT order-level whale flow (Binance spot aggTrades rebuilt into taker orders) next to the perp order flow of O1.

Why (user: focus on complete data): whale flow was the last foundation information that transferred to the unseen year, and rebuilding
taker ORDERS instead of per-price fills (W2 -> O1) made it more robust. Spot flow was tried only at the fill level (v237: DD 21-22). Spot
whales trade without leverage and are a different population from perp traders; the Binance spot archive is complete for the majors
(2017 / 2018 on, SOL 2020), longer than the perp archive, so the pre-2021 training years also carry flow.
Data: scripts/fetch_aggtrades_flow.py --market spot --orders --out data/raw/aggflow_spot_20260929_orders (same order rebuild and tiers as
O1; a 1m store is kept in <out>_1m). Features: the six v236 formulas on the spot order table (causal at the bar close; NaN before a
symbol's spot archive starts). Before the perp archive starts (2020) the Z2 sum equals the spot table.
Members as in v240 (v144 builder, v202 quarterly wrapper); B members = T3 (unchanged); new features excluded from the vol models.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings otherwise).
Fixed before running:
  Z1_add_spot         A members = TV + Binance perp order-level flow (O1) + spot order-level flow (suffix _so)
  Z2_venue_sum_spot   A members = TV + order-level flow computed on the SUM of the perp and spot order tables
Reference: v247_B18 (O1 members at budget 0.18, must reproduce dev4 5.777). SELECTION = robust criterion among Z1, Z2; the most recent
year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v262/v262_spot_order_flow.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
SPOT = Path("data/raw/aggflow_spot_20260929_orders")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v240 = _load("v240_z", RD / "v240/v240_order_level_flow.py")
flo = v240.flo  # Binance order-level (D = the orders archive)
fly = _load("flow_features_spot_orders", RD / "v236/flow_features.py")
fly.D = SPOT
tvm, SYMS = v240.tvm, v240.SYMS


def venue_sum(sym: str) -> pd.DataFrame:
    a = pd.read_parquet(v240.ORDERS / f"{sym}_flow_4h.parquet").sort_index()
    p = SPOT / f"{sym}_flow_4h.parquet"
    if not p.exists():
        return a
    b = pd.read_parquet(p).sort_index()
    idx = a.index.union(b.index)
    cols = sorted(set(a.columns) | set(b.columns))
    return a.reindex(index=idx, columns=cols).fillna(0.0) + b.reindex(index=idx, columns=cols).fillna(0.0)


def feature_frame(load_asset, kind: str) -> pd.DataFrame:
    rows = []
    for s in SYMS:
        b, _, _ = load_asset(s)
        t = pd.DatetimeIndex(b["open_time"])
        parts = [pd.DataFrame({"t": t, "sym": s}), tvm.tv_features(b).reset_index(drop=True)]
        if kind == "add":
            parts.append(flo.flow_features(s, t).reset_index(drop=True))
            so = fly.flow_features(s, t) if (SPOT / f"{s}_flow_4h.parquet").exists() else pd.DataFrame(index=t, columns=list(fly.FL), dtype=float)
            parts.append(so.add_suffix("_so").reset_index(drop=True))
        else:
            parts.append(flo.flow_features(s, t, venue_sum(s)).reset_index(drop=True))
        rows.append(pd.concat(parts, axis=1))
    return pd.concat(rows, ignore_index=True)


def build_member(quarterly: bool, kind: str):
    tag = f"{'q' if quarterly else 'a'}_z{kind}"
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
    xf = feature_frame(ext.v92.load_asset, kind)
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
    for key, kind in (("Z1_add_spot", "add"), ("Z2_venue_sum_spot", "sum")):
        mm = {"B": base["B"], "Bq": base["Bq"]}
        for name, q in (("A", False), ("Aq", True)):
            cache = C / f"member_{name}_{key}.parquet"
            if not cache.exists():
                build_member(q, kind).to_parquet(cache)
            mm[name] = pd.read_parquet(cache)
            print("member", name, key, "cached", flush=True)
        mixes[key] = mm
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v262", "rows": {}, "trades": {}}
    for key, mm in mixes.items():
        m = {k: v.reindex(idx).fillna(0.0)[cols] for k, v in mm.items()}
        books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **dict(v221.KW, sleeve_risk_budget=0.18))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("Z1_add_spot", "Z2_venue_sum_spot")})
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
    (HERE / "v262_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
