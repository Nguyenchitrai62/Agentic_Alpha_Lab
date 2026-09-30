"""v286: upgrade the Coinbase-premium member D with the features that lifted the other members (registry v286).

Why: v285 D2 (CB) = 0.8 x C4 books + 0.2 x (D + Dq)/2 is the first deterministic gate pass, but its member D is still the OLD v154
feature set (v144 builder + Coinbase premium, 2026-09 vintage). The other members each gained when upgraded: TradingView indicators
(v231/v233: A and B), order-level whale flow (v240: A). D never received either. Hypothesis: a stronger D member (same Coinbase
information + the audited causal TV / flow features) lifts CB's weak years without adding DD, because D is only 20% of the book.
Data: same caches / archives as the audited members - Coinbase premium features (v111.add_cb, merged on t), 17 TradingView
indicators (v231/tv_indicators.py, merged on (t, sym)), order-level flow (v236/flow_features.py on data/raw/aggflow_20260928_orders,
merged on (t, sym)). New features are excluded from the vol models (as in v154 / v233 / v240). Builder = v154.books_coinbase (v144
builder, annual) and the v202 quarterly wrapper (v206 Dq); walk-forward anchors, label windows and embargo unchanged.
Fixed before running (everything else = CB / C4 rules: v216 G2 grid trader, dip stops on 5m closes at 4 sigma + 8-sigma native
backstop, sleeve budget 0.18, v218 D2 settings, minute-5 rule, limit entries, SL market / TP limit, Bybit fees, adverse funding):
  E1_dtv     books = 0.8 x C4 + 0.2 x (D_tv + Dq_tv)/2          D = Coinbase premium + TradingView
  E2_dtvo    books = 0.8 x C4 + 0.2 x (D_tvo + Dq_tvo)/2        D = Coinbase premium + TradingView + order-level flow
Reference: CB_ref = v285 D2 (must reproduce dev4 5.864). Builder check: the annual builder with no extra features must reproduce
members_v154 'D' exactly.
SELECTION (dev only): the v204 robust criterion among E1, E2 with the drawdown filter computed on the FIRST FOUR YEARS ONLY
(max of the yearly 1m-marked DD 2021-2024; the old filter used the full path, which includes the most recent year - a protocol fix,
identical whenever the worst DD sits in a dev year, as in every recent version). The selected row replaces CB only if the same
criterion prefers it over CB_ref. The most recent year is scored once, for the selected row, for information.

  python research/parallel/rounds/parallel-20260906-r2/v286/v286_coinbase_member_upgrade.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C4R = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v240 = _load("v240_d", RD / "v240/v240_order_level_flow.py")
tvm, flo, SYMS = v240.tvm, v240.flo, v240.SYMS


def feature_frame(load_asset, flow: bool) -> pd.DataFrame:
    rows = []
    for s in SYMS:
        b, _, _ = load_asset(s)
        t = pd.DatetimeIndex(b["open_time"])
        parts = [pd.DataFrame({"t": t, "sym": s}), tvm.tv_features(b).reset_index(drop=True)]
        if flow:
            parts.append(flo.flow_features(s, t).reset_index(drop=True))
        rows.append(pd.concat(parts, axis=1))
    return pd.concat(rows, ignore_index=True)


def build_member(quarterly: bool, tv: bool, flow: bool):
    """v154.books_coinbase (annual) / v206 member_d_quarterly, plus optional TV / order-flow features on (t, sym)."""
    tag = f"{'q' if quarterly else 'a'}{int(tv)}{int(flow)}"
    v144 = _load(f"v144_d{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        _load(f"v202_d{tag}", RD / "v202/v202_quarterly_retrain.py").quarterly(v144)
    v111 = _load(f"v111_d{tag}", RD / "v111/v111_coinbase_premium.py")
    cbf = v111.add_cb(v144.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    drop = set(v111.CB)
    xf = None
    if tv or flow:
        xf = feature_frame(ext.v92.load_asset, flow)
        drop |= {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)

    def add(p):
        p = p.merge(cbf, on="t", how="left")
        return p if xf is None else p.merge(xf, on=["t", "sym"], how="left")
    ext.v92.build = lambda: add(b92())
    v103.build = lambda: add(b103())
    return v144.books_v142()[1]


def dev_dd(r):
    return max(y["dd_1m_pct"] for y in r["yearly"][:4])


def dev_select(rows, worst_month):
    ok = {k: v for k, v in rows.items() if dev_dd(v) <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or rows
    five = {k: v for k, v in pool.items() if v["monthly_dev4"] >= 5}
    pool = five or pool
    return max(pool, key=lambda k: (round(worst_month(pool[k]), 4), pool[k]["monthly_dev4"]))


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    d154 = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0)
    m["D"] = d154.reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    chk = build_member(False, False, False).reindex(d154.index)[list(d154.columns)]
    diff = float((chk - d154).abs().max().max())
    assert diff < 1e-12, f"builder does not reproduce members_v154 D (max diff {diff})"
    print("builder check: members_v154 D reproduced exactly", flush=True)
    for name, q, tv, fl in (("D_tv", False, True, False), ("Dq_tv", True, True, False), ("D_tvo", False, True, True), ("Dq_tvo", True, True, True)):
        cache = C / f"member_{name}.parquet"
        if not cache.exists():
            build_member(q, tv, fl).to_parquet(cache)
        m[name] = pd.read_parquet(cache).reindex(idx).fillna(0.0)[cols]
        print("member", name, "cached", flush=True)
    c4 = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    mixes = {"CB_ref": 0.8 * c4 + 0.2 * (m["D"] + m["Dq"]) / 2,
             "E1_dtv": 0.8 * c4 + 0.2 * (m["D_tv"] + m["Dq_tv"]) / 2,
             "E2_dtvo": 0.8 * c4 + 0.2 * (m["D_tvo"] + m["Dq_tvo"]) / 2}
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {"version": "v286", "rows": {}, "trades": {}}
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4R))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = dev_dd(r)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "CB_ref":
            assert abs(r["monthly_dev4"] - 5.864) < 0.002
    sel = dev_select({k: out["rows"][k] for k in ("E1_dtv", "E2_dtvo")}, v204.worst_month)
    out["selected"] = sel
    out["replaces_cb"] = dev_select({k: out["rows"][k] for k in ("CB_ref", sel)}, v204.worst_month) == sel
    s_ = out["rows"][sel]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, "replaces CB:", out["replaces_cb"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v286_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
