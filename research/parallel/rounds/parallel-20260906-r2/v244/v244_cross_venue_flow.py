"""v244: cross-venue order-level whale flow - Bybit USDT perpetuals next to Binance, on the O1 foundation (registry v244).

Why: the order-level large-order flow on Binance (v240 O1) is the most robust foundation (dev4 5.690, worst dev year 2.759, DD 19.08,
5y 5.364, most recent year 4.069). Binance is one venue; Bybit is the second-largest USDT-perp venue (XRPUSDT 2024-03-01: 242M vs 777M
USDT taker notional). Large orders placed on Bybit are information the Binance tape does not contain.
Data: Bybit public trades (public.bybit.com/trading, daily files; BTC from 2020-03, the others from mid-2021), rebuilt into taker orders
(fills with the same timestamp and side) and aggregated per UTC 4h bar and order-size tier (scripts/fetch_bybit_flow.py ->
data/raw/bybitflow_20260929); same table format as the Binance order-level archive, so the v236 feature formulas apply (causal,
known at the bar close; NaN before a venue's data starts).
Members as in v240 (v144 builder, v202 quarterly wrapper); B members = T3 (unchanged); new features excluded from the vol models.
Fixed before running (everything else = v218 D2 settings: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit
orders, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding):
  Y1_add_bybit     A members = TV + Binance order-level flow (O1) + Bybit order-level flow (suffix _by)
  Y2_venue_sum     A members = TV + order-level flow computed on the SUM of the Binance and Bybit tables (replaces Binance-only flow)
Reference: v240_O1 (must reproduce dev4 5.690). SELECTION = robust criterion among Y1, Y2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v244/v244_cross_venue_flow.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
BYBIT = Path("data/raw/bybitflow_20260929")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v240 = _load("v240_y", RD / "v240/v240_order_level_flow.py")
flo = v240.flo  # Binance order-level (D = the orders archive)
fly = _load("flow_features_bybit", RD / "v236/flow_features.py")
fly.D = BYBIT
tvm, SYMS = v240.tvm, v240.SYMS


def venue_sum(sym: str) -> pd.DataFrame:
    a = pd.read_parquet(v240.ORDERS / f"{sym}_flow_4h.parquet").sort_index()
    p = BYBIT / f"{sym}_flow_4h.parquet"
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
            by = fly.flow_features(s, t) if (BYBIT / f"{s}_flow_4h.parquet").exists() else pd.DataFrame(index=t, columns=list(fly.FL), dtype=float)
            parts.append(by.add_suffix("_by").reset_index(drop=True))
        else:
            parts.append(flo.flow_features(s, t, venue_sum(s)).reset_index(drop=True))
        rows.append(pd.concat(parts, axis=1))
    return pd.concat(rows, ignore_index=True)


def build_member(quarterly: bool, kind: str):
    tag = f"{'q' if quarterly else 'a'}_y{kind}"
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
    mixes = {"v240_O1": base}
    for key, kind in (("Y1_add_bybit", "add"), ("Y2_venue_sum", "sum")):
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
    out = {"version": "v244", "rows": {}, "trades": {}}
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
        if key == "v240_O1":
            assert abs(r["monthly_dev4"] - 5.690) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("Y1_add_bybit", "Y2_venue_sum")})
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
    (HERE / "v244_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
