"""v284: give the flow member 2.5 more years of flow history - SPOT order flow spliced in BEFORE the perp order-flow archive starts.

Why (user 2026-09-30: use the available exchange data to the maximum): the O1 foundation member A trains on the extended panel (spot
price prefixes from 2017 for BTC / ETH / BNB / XRP), but its six order-level whale-flow features are EMPTY before the Binance perp archive
starts (2020-01; SOL 2020-09): for ~2.5 years of training rows the model learns only a 'missing' branch. The Binance spot order-level
store (kept, 2017-08 / 2017-11 / 2018-05 onward) carries the same kind of information for those years. Splicing it in front of the perp
table gives the flow relationships many more (and more varied: 2018 bear, 2019 recovery) training examples. After the perp archive
starts nothing changes (the perp table is used as in O1), so the live / recent features are identical to O1's.
Fixed before running.
Flow table per symbol = the Binance spot order-level 4h table (data/raw/aggflow_spot_20260929_orders) for bars BEFORE the first bar of the
perp order-level table (data/raw/aggflow_20260928_orders), the perp table from then on; the six v236 formulas on the spliced table
(causal; rolling windows bridge the splice).
Members as O1 (v240 builder: v144 + TradingView + order-level flow, flow excluded from the vol models; annual A and quarterly Aq wrapper);
B members = T3 (unchanged). Environment = C4 rules (v269 M1: dip stops on 5m closes at 4 sigma + 8-sigma native backstop, budget 0.18).
  P1_spliced        A / Aq with the spliced flow features
  P2_spliced_flag   as P1 plus a 0/1 column 'flow_is_spot' (1 on the spliced spot rows)
Reference: C4 (O1 members; must reproduce dev4 6.026). SELECTION = robust criterion among P1, P2; the most recent year is scored once for
the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v284/v284_spliced_flow_history.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
PERP = Path("data/raw/aggflow_20260928_orders")
SPOT = Path("data/raw/aggflow_spot_20260929_orders")
C4 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v240 = _load("v240_p", RD / "v240/v240_order_level_flow.py")
flo = v240.flo
tvm, SYMS = v240.tvm, v240.SYMS


def spliced(sym):
    p = pd.read_parquet(PERP / f"{sym}_flow_4h.parquet").sort_index()
    sp = SPOT / f"{sym}_flow_4h.parquet"
    if not sp.exists():
        return p, pd.Timestamp("2100-01-01", tz="UTC")
    s = pd.read_parquet(sp).sort_index()
    first = p.index[0]
    s = s[s.index < first]
    cols = sorted(set(p.columns) | set(s.columns))
    return pd.concat([s.reindex(columns=cols).fillna(0.0), p.reindex(columns=cols).fillna(0.0)]), first


def feature_frame(load_asset, flag):
    rows = []
    for s in SYMS:
        b, _, _ = load_asset(s)
        t = pd.DatetimeIndex(b["open_time"])
        tab, first = spliced(s)
        parts = [pd.DataFrame({"t": t, "sym": s}), tvm.tv_features(b).reset_index(drop=True),
                 flo.flow_features(s, t, tab).reset_index(drop=True)]
        if flag:
            parts.append(pd.DataFrame({"flow_is_spot": (t < first).astype(float)}))
        rows.append(pd.concat(parts, axis=1))
    return pd.concat(rows, ignore_index=True)


def build_member(quarterly, flag):
    tag = f"{'q' if quarterly else 'a'}_s{int(flag)}"
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
    xf = feature_frame(ext.v92.load_asset, flag)
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
    mixes = {"C4": base}
    for key, flag in (("P1_spliced", False), ("P2_spliced_flag", True)):
        mm = {"B": base["B"], "Bq": base["Bq"]}
        for name, q in (("A", False), ("Aq", True)):
            cache = C / f"member_{name}_{key}.parquet"
            if not cache.exists():
                build_member(q, flag).to_parquet(cache)
            mm[name] = pd.read_parquet(cache)
            print("member", name, key, "cached", flush=True)
        mixes[key] = mm
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {"version": "v284", "rows": {}, "trades": {}}
    for key, mm in mixes.items():
        m = {k: v.reindex(idx).fillna(0.0)[cols] for k, v in mm.items()}
        books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
        if key == "C4":
            assert abs(r["monthly_dev4"] - 6.026) < 0.002
    cands = ("P1_spliced", "P2_spliced_flag")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s_ = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
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
    (HERE / "v284_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
