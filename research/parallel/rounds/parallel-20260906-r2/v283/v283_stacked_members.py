"""v283: WALK-FORWARD STACKING of the foundation members, with and without the all-exchange-data microstructure member C.

Why: v281 blended the microstructure member C (all kept exchange data; IC close to the members' but positive in 2022 where every member
is negative) with a FIXED weight and the drawdown jumped to 27. A trader weights information sources by how well they have worked; a
stacker does that walk-forward: for each anchor year Y the member weights are fitted on earlier years only, so an unstable source gets a
small weight. This uses the exchange data to the maximum without committing to it blindly.
Fixed before running.
Members (books on the decision rows): A, Aq (O1 flow member, annual / quarterly), B, Bq (options + TV, annual / quarterly), C (v281's
microstructure member, rebuilt with the same code: pooled HGB on all exchange data groups, annual walk-forward, scaled to the C4 book
magnitude on its training rows). Target: the 7-day forward return in sigma units (the data-leaderboard target). Stacker for anchor year Y:
non-negative least squares of the target on the members' standardised books (pooled over coins) using live rows (from 2021-09-24) whose
label ended before Y - 7 days; weights normalised to sum 1; for 2021 (no live history) and whenever all weights are 0: the C4 weights
(A, Aq, B, Bq 0.25 each, C 0). Stacked book = sum_k w_k x book_k (books keep their own scale, so the stacked book has the members'
magnitude).
Environment = C4 rules (v269 M1: dip stops on 5m closes at 4 sigma + 8-sigma native backstop, budget 0.18, v218 D2 settings).
  S1_stack4   stack of A, Aq, B, Bq
  S2_stack5   stack of A, Aq, B, Bq, C
Reference: C4 books (0.25 each; must reproduce dev4 6.026). SELECTION = robust criterion among S1, S2; the most recent year is scored once
for the selected row. Reported: the weights per anchor.

  python research/parallel/rounds/parallel-20260906-r2/v283/v283_stacked_members.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls
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
    Cc = eu.er.CACHE
    M = {k: pd.read_parquet(Cc / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    c4 = 0.25 * (M["A"] + M["Aq"] + M["B"] + M["Bq"])
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]

    # ---- member C exactly as v281
    P, groups = dl.panel()
    feats = [c for g in groups.values() for c in g]
    label_end = P["t"] + pd.Timedelta(hours=4 * (dl.H + 1))
    has_y = np.isfinite(P["y"]).to_numpy()
    Cbook = pd.DataFrame(0.0, index=idx, columns=cols)
    for j in range(len(anchors)):
        tr = ((label_end < anchors[j] - pd.Timedelta(days=7)).to_numpy()) & has_y
        mdl = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=200, l2_regularization=1.0,
                                            random_state=0).fit(P.loc[tr, feats].to_numpy(float), P.loc[tr, "y"].clip(-4, 4).to_numpy(float))
        te_end = anchors[j + 1] if j + 1 < len(anchors) else pd.Timestamp("2100-01-01", tz="UTC")
        te = ((P["t"] >= anchors[j]) & (P["t"] < te_end)).to_numpy()
        live_tr = tr & (P["t"] >= anchors[0]).to_numpy()
        if live_tr.any():
            ref = c4.stack().reindex(pd.MultiIndex.from_arrays([P.loc[live_tr, "t"], P.loc[live_tr, "sym"]])).abs().mean()
            k = float(ref / max(np.abs(np.clip(mdl.predict(P.loc[live_tr, feats].to_numpy(float)), -2, 2)).mean(), 1e-9))
        else:
            k = float(K0 / max(np.abs(np.clip(mdl.predict(P.loc[tr, feats].to_numpy(float)), -2, 2)).mean(), 1e-9))
        pr = np.clip(mdl.predict(P.loc[te, feats].to_numpy(float)), -2, 2) * k
        piv = pd.DataFrame({"t": P.loc[te, "t"].to_numpy(), "sym": P.loc[te, "sym"].to_numpy(), "w": pr}).pivot_table(
            index="t", columns="sym", values="w").reindex(idx).reindex(columns=cols)
        Cbook = Cbook.where(piv.isna(), piv)
    M["C"] = Cbook.fillna(0.0)

    # ---- target on the decision rows
    Y = pd.DataFrame({s: P[P["sym"] == s].set_index("t")["y"].reindex(idx) for s in cols})[cols]
    lab_end = idx + pd.Timedelta(hours=4 * (dl.H + 1))
    out = {"version": "v283", "weights": {}, "rows": {}, "trades": {}}

    def stacked(keys):
        book = pd.DataFrame(0.0, index=idx, columns=cols)
        base_w = {k: (0.25 if k != "C" else 0.0) for k in keys}
        for j in range(len(anchors)):
            te_end = anchors[j + 1] if j + 1 < len(anchors) else pd.Timestamp("2100-01-01", tz="UTC")
            te = np.asarray((idx >= anchors[j]) & (idx < te_end))
            tr = np.asarray((idx >= anchors[0]) & (lab_end < anchors[j] - pd.Timedelta(days=7)))
            w = dict(base_w)
            if tr.sum() > 500:
                Xs = []
                for k in keys:
                    v = M[k][tr].to_numpy().ravel()
                    Xs.append(v / (np.std(v) + 1e-12))
                Xs = np.stack(Xs, axis=1)
                yv = Y[tr].to_numpy().ravel()
                ok = np.isfinite(yv) & np.isfinite(Xs).all(axis=1)
                coef, _ = nnls(Xs[ok], np.clip(yv[ok], -4, 4))
                if coef.sum() > 0:
                    w = {k: float(c / coef.sum()) for k, c in zip(keys, coef)}
            out["weights"].setdefault("+".join(keys), {})[str(anchors[j].date())] = {k: round(v, 3) for k, v in w.items()}
            book.loc[te] = sum(w[k] * M[k].loc[te] for k in keys)
        return book

    mixes = {"C4": c4, "S1_stack4": stacked(["A", "Aq", "B", "Bq"]), "S2_stack5": stacked(["A", "Aq", "B", "Bq", "C"])}
    print("weights", json.dumps(out["weights"]), flush=True)
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
        if key == "C4":
            assert abs(r["monthly_dev4"] - 6.026) < 0.002
    cands = ("S1_stack4", "S2_stack5")
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
    (HERE / "v283_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
