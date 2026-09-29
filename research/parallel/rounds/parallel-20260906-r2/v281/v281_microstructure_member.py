"""v281: a MICROSTRUCTURE foundation member built from ALL kept exchange data, blended into the C4 books.

Why (user 2026-09-30: use the available exchange data to the maximum): the data leaderboard (research/diagnostics/data_leaderboard, dev
years only) shows that a pooled model on ALL exchange data groups reaches a mean IC of 0.051 on the 7-day target - the same level as the
foundation members (A 0.070, Aq 0.052, B 0.068, Bq 0.057, C4 books 0.057) - but with a different year profile: it is positive in 2022
(+0.005) where every member is negative (-0.007 .. -0.045). A member that errs in different years is the kind of diversity that can lift
the weakest year (the robust selection criterion). Earlier data additions went INTO member A and raised the drawdown; here the data form a
separate member with a small weight.
Fixed before running.
Member C: one pooled HistGradientBoostingRegressor (5 coins, depth 4, lr 0.05, 300 iter, min leaf 200, l2 1.0, seed 0) on the leaderboard's
'all' feature set (base returns / vol / taker share; TradingView; Binance perp, Binance spot, OKX and Bybit taker ORDER flow; premium /
predicted funding; open interest and long/short ratios; 1m intrabar flow), target = 7-day forward return in sigma units clipped to +-4,
rows from 2020-01. Walk-forward: the model predicting anchor year Y trains on rows whose label ended before Y - 7 days; 2021 uses the
2021 anchor model the same way (training rows 2020-01 .. 2021-09-17). Book C = clip(prediction, -2, 2) x k, k = mean |C4 book| / mean
|clipped prediction| over the model's training rows inside the live period (rows from 2021-09-24); the 2021 model has no live training
rows and uses k = 0.05 / mean |clipped prediction| of its training rows (0.05 = pre-registered typical C4 book magnitude).
Environment = C4 rules (v269 M1: dip stops on 5m closes at 4 sigma + 8-sigma native backstop, budget 0.18, v218 D2 settings).
  U1_c20   books = 0.8 x C4 books + 0.2 x C
  U2_c33   books = 0.67 x C4 books + 0.33 x C
Reference: C4 books (must reproduce dev4 6.026). SELECTION = robust criterion among U1, U2; the most recent year is scored once for the
selected row. Reported: member C IC per dev year.

  python research/parallel/rounds/parallel-20260906-r2/v281/v281_microstructure_member.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = HERE.parent
C4 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)
K0 = 0.05


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    dl = _load("dl", Path("research/diagnostics/data_leaderboard/data_leaderboard_dev.py"))
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    c4 = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]

    P, groups = dl.panel()
    feats = [c for g in groups.values() for c in g]
    label_end = P["t"] + pd.Timedelta(hours=4 * (dl.H + 1))
    has_y = np.isfinite(P["y"]).to_numpy()
    Cbook = pd.DataFrame(0.0, index=idx, columns=cols)
    out = {"version": "v281", "n_features": len(feats), "member_ic": {}, "k": {}, "rows": {}, "trades": {}}
    c4_abs = c4.abs().stack()
    for j in range(len(anchors)):
        tr = ((label_end < anchors[j] - pd.Timedelta(days=7)).to_numpy()) & has_y
        mdl = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=200, l2_regularization=1.0,
                                            random_state=0).fit(P.loc[tr, feats].to_numpy(float), P.loc[tr, "y"].clip(-4, 4).to_numpy(float))
        te_end = anchors[j + 1] if j + 1 < len(anchors) else pd.Timestamp("2100-01-01", tz="UTC")
        te = ((P["t"] >= anchors[j]) & (P["t"] < te_end)).to_numpy()
        pr_tr = np.clip(mdl.predict(P.loc[tr, feats].to_numpy(float)), -2, 2)
        live_tr = tr & (P["t"] >= anchors[0]).to_numpy()
        if live_tr.any():
            ref = c4.stack().reindex(pd.MultiIndex.from_arrays([P.loc[live_tr, "t"], P.loc[live_tr, "sym"]])).abs().mean()
            k = float(ref / max(np.abs(np.clip(mdl.predict(P.loc[live_tr, feats].to_numpy(float)), -2, 2)).mean(), 1e-9))
        else:
            k = float(K0 / max(np.abs(pr_tr).mean(), 1e-9))
        out["k"][str(anchors[j].date())] = round(k, 5)
        pr = np.clip(mdl.predict(P.loc[te, feats].to_numpy(float)), -2, 2) * k
        sub = pd.DataFrame({"t": P.loc[te, "t"].to_numpy(), "sym": P.loc[te, "sym"].to_numpy(), "w": pr})
        piv = sub.pivot_table(index="t", columns="sym", values="w").reindex(idx).reindex(columns=cols)
        Cbook = Cbook.where(piv.isna(), piv)
        if j < 4:
            ok = te & has_y
            out["member_ic"][str(anchors[j].year)] = round(float(pd.Series(mdl.predict(P.loc[ok, feats].to_numpy(float))).corr(
                P.loc[ok, "y"].reset_index(drop=True), method="spearman")), 4)
        print("anchor", anchors[j].date(), "train rows", int(tr.sum()), "k", round(k, 4), flush=True)
    print("member C IC by dev year", out["member_ic"], flush=True)
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    mixes = {"C4": c4, "U1_c20": 0.8 * c4 + 0.2 * Cbook, "U2_c33": 0.67 * c4 + 0.33 * Cbook}
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev win", out["trades"][key]["dev"].get("win_rate"), flush=True)
        if key == "C4":
            assert abs(r["monthly_dev4"] - 6.026) < 0.002, "C4 books must reproduce v269 M1"
    cands = ("U1_c20", "U2_c33")
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
    (HERE / "v281_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
