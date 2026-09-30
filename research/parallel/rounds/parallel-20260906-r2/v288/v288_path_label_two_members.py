"""v288: path labels in a second feature set - does the v287 gain generalise? (registry v288; closes the path-label direction).

Why: v287 P1 (0.8 CB + 0.2 path-labelled O1 member PA) is preferred over CB by the dev-only robust criterion (worst dev year 3.054 vs
3.005, dev DD 18.05 vs 18.39). One member is one draw: if the first-touch target is genuinely useful, the same target on the OTHER
audited feature set (member B = options + TradingView, v233 builder) should give a second diverse member, and splitting the 20% slice
between two path members should be at least as good as P1 in the weak years.
Label = v287.path_label / relabel (entry at open t+1, barrier vol42 x sqrt(h), stop-first, else clipped return; same windows, anchors,
embargo and training filter as the return labels) in all three components of the v144 builder; B members built exactly as v233 B_tv
(annual) / Bq_tv (v202 quarterly) apart from the label.
Fixed before running (everything else = CB / C4 rules as v287):
  Q1_two_path   books = 0.8 x CB + 0.2 x (PA + PAq + PB + PBq)/4
Reference rows: CB_ref (must reproduce 5.864) and v287 P1 (must reproduce dev4 5.683). Builder check: with the label switch OFF the
builder must reproduce member_B_tv exactly. DECISION (dev only, v286.dev_select with the dev-only DD filter): Q1 is adopted over P1 only if
dev_select({P1, Q1}) picks Q1; the most recent year is scored once for Q1 only if it is adopted. This is the third and last variant of
the path-label direction (v287 P1 / P2, v288 Q1); the direction closes after it.

  python research/parallel/rounds/parallel-20260906-r2/v288/v288_path_label_two_members.py
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


v287 = _load("v287_q", RD / "v287/v287_path_label_member.py")
v286 = v287.v286
v231 = _load("v231_q", RD / "v231/v231_quality_features.py")
TV = list(v231.tvm.TV)


def build_member_b(quarterly: bool, path: bool):
    """v233.build_member(quarterly, options=True) with the optional v287 path label."""
    tag = f"{'q' if quarterly else 'a'}{int(path)}"
    v202 = _load(f"v202_q{tag}", RD / "v202/v202_quarterly_retrain.py")
    v150 = _load(f"v150_q{tag}", RD / "v150/v150_options_flow.py")
    v144 = v150.v144
    OPT, ofeats = list(v150.OPT), v150.opt_features()
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
        return p.merge(ofeats, on="t", how="left").merge(xf, on=["t", "sym"], how="left")
    if not path:
        ext.v92.build = lambda: add(base92)
        v103.build = lambda: add(b103())
        return v144.books_v142()[1]
    ohlc = {s: ext.load_asset_ext(s)[0][["open_time", "high", "low"]].drop_duplicates("open_time") for s in v287.v240.SYMS}
    add94 = ext.v94.add_targets
    ext.v92.build = lambda: v287.relabel(add(base92), [("y", ext.v92.H)], ohlc)
    ext.v94.add_targets = lambda p: v287.relabel(add94(p), [(f"y{h}", h) for h in ext.v94.HORIZONS], ohlc)
    v103.build = lambda: v287.relabel(add(b103()), [(f"y{h}", h) for h in v103.HS], ohlc)
    return v144.books_v142()[1]


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    b_tv = pd.read_parquet(C / "member_B_tv.parquet")
    chk = build_member_b(False, False).reindex(b_tv.index)[list(b_tv.columns)]
    diff = float((chk - b_tv).abs().max().max())
    assert diff < 1e-12, f"builder does not reproduce member_B_tv (max diff {diff})"
    print("builder check: member_B_tv reproduced exactly", flush=True)
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"),
        ("PA", "member_PA_path.parquet"), ("PAq", "member_PAq_path.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    for name, q in (("PB", False), ("PBq", True)):
        cache = C / f"member_{name}_path.parquet"
        if not cache.exists():
            build_member_b(q, True).to_parquet(cache)
        m[name] = pd.read_parquet(cache).reindex(idx).fillna(0.0)[cols]
        print("member", name, "cached", flush=True)
    for k in ("B", "Bq"):
        c = pd.concat([m[k].stack(), m["P" + k].stack()], axis=1).corr().iloc[0, 1]
        print(f"book-weight corr {k} vs P{k}: {c:.3f}", flush=True)
    c4 = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    cb = 0.8 * c4 + 0.2 * (m["D"] + m["Dq"]) / 2
    mixes = {"CB_ref": cb, "P1_ref": 0.8 * cb + 0.2 * (m["PA"] + m["PAq"]) / 2,
             "Q1_two_path": 0.8 * cb + 0.2 * (m["PA"] + m["PAq"] + m["PB"] + m["PBq"]) / 4}
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {"version": "v288", "rows": {}, "trades": {}}
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4R))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        ref = {"CB_ref": 5.864, "P1_ref": 5.683}.get(key)
        if ref is not None:
            assert abs(r["monthly_dev4"] - ref) < 0.002
    adopt = v286.dev_select({k: out["rows"][k] for k in ("P1_ref", "Q1_two_path")}, v204.worst_month) == "Q1_two_path"
    out["selected"] = "Q1_two_path" if adopt else "P1_ref"
    out["q1_adopted"] = adopt
    if adopt:
        s_ = out["rows"]["Q1_two_path"]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"]["Q1_two_path"]["_hidden"]}
    else:
        out["final_score_selected"] = "not scored (Q1 not adopted; P1 already scored in v287)"
    keep = "Q1_two_path" if adopt else None
    for k in out["trades"]:
        if k != keep:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != keep:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("Q1 adopted:", adopt, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v288_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
