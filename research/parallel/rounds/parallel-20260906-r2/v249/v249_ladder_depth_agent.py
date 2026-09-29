"""v249: a learned dip-ladder DEPTH agent - where to rest the four dip bids of every coin and bar (contextual bandit, exact outcomes).

Why: the dip sleeve earns most of the pipeline; its bids always rest at 2.5 / 3 / 3.5 / 4 sigma_4h below the bar open. A trader bids
shallower in calm, orderly markets and deeper when volatility or selling pressure is building. Every alternative depth has an exact
outcome from the 1m path (a bid at depth k fills iff the low trades through it; its result follows the same TP / SL / timeout rules), so
the choice can be learned offline without value estimates or exploration.
Fixed before running.
Environment: v240 O1 books, v247 sleeve budget 0.18 (current best), v218 D2 settings otherwise. Extended ladder (2.0, 2.5, 3.0, 3.5, 4.0,
4.5) sigma_4h with the same per-rung size; per coin and bar the agent activates a window of four consecutive rungs through the
sleeve_filter hook: shallow {2.0..3.5}, standard {2.5..4.0} (= the deployed ladder) or deep {3.0..4.5}.
Data: one engine run with all six rungs active and no binding budget (sleeve_risk_budget 10) -> per (bar, coin, rung) the net bid return
(0 if it does not fill). State at the decision (known at the bar close): sigma_4h regime (sigma / 540-bar median), 6- and 42-bar returns in
sigma units, SuperTrend direction, market-structure trend and Williams VIX Fix z (TradingView set), order-level fl_big_imb6, the book
target and the hour. Model: per rung a HistGradientBoostingRegressor (depth 3, lr 0.05, 200 iter, min leaf 300) on the clipped return, two
models per year on even / odd bars (cross-fitting), fits on bars that ended before Y - 7 days; 2021 uses the standard window.
Policy: the window with the highest predicted sum; deviate from standard only if both halves prefer the same window by more than the margin.
  D1_agent          margin 0
  D2_agent_strict   margin 0.001 (0.1% of the window's summed bid return)
  D3_fixed_deep     no learning: always the deep window {3.0..4.5}
Reference: standard window on the extended ladder (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among D1..D3; the most
recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v249/v249_ladder_depth_agent.py
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
RUNGS6 = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5)
WINDOWS = {"shallow": (0, 1, 2, 3), "standard": (1, 2, 3, 4), "deep": (2, 3, 4, 5)}
EMBARGO = pd.Timedelta(days=7)
BUDGET = 0.18


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_d", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_d", RD / "v240/v240_order_level_flow.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    n, na = len(idx), len(cols)

    # ---- state at the decision row (bar close)
    tv = v232.tv_frames(idx, cols)
    o1 = opens.reindex(idx)[cols].shift(-1)
    lo1 = np.log(o1)
    sig = lo1.diff().rolling(360, min_periods=120).std()
    feats = {"vol": sig / sig.rolling(540, min_periods=180).median(), "r6": lo1.diff(6) / (sig * np.sqrt(6)),
             "r42": lo1.diff(42) / (sig * np.sqrt(42)), "st": tv["tv_st_dir"], "ms": tv["tv_ms_trend"], "wvf": tv["tv_wvf_z"],
             "flow": pd.DataFrame({s: v240.flo.flow_features(s, idx)["fl_big_imb6"].to_numpy() for s in cols}, index=idx),
             "book": books}
    X3 = np.nan_to_num(np.stack([f.reindex(idx)[cols].to_numpy(float) for f in feats.values()], axis=2))
    hours = np.array([(t + pd.Timedelta(hours=4)).hour for t in idx], float)

    # ---- exact outcomes of all six rungs (no binding budget)
    ev = []
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, rungs=RUNGS6, **dict(v221.KW, sleeve_risk_budget=10.0))
    Y = np.zeros((n, na, len(RUNGS6)))
    pos = {t: k for k, t in enumerate(idx)}
    last = {}
    for e in ev:
        if e["kind"] == "rung_fill":
            last[e["symbol"]] = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and e["symbol"] in last:
            f = last.pop(e["symbol"])
            i = pos.get(f["t"].floor("4h") - pd.Timedelta(hours=4))
            if i is not None:
                Y[i, cols.index(e["symbol"]), RUNGS6.index(f["rung"])] = e["ret"]
    Y = np.clip(Y, -0.10, 0.05)
    bar_end = idx + pd.Timedelta(hours=8)
    live = np.asarray(idx + pd.Timedelta(hours=4) >= anchors[0])
    out = {"version": "v249", "rungs": RUNGS6, "windows": {k: list(v) for k, v in WINDOWS.items()}, "train": {}, "rows": {}, "trades": {}}
    dev = live & np.asarray(idx + pd.Timedelta(hours=4) < anchors[4])
    out["dev_mean_window_sum_pct"] = {w: round(100 * float(Y[dev][:, :, list(ix)].sum(axis=2).mean()), 4) for w, ix in WINDOWS.items()}
    print("dev mean window sum %", out["dev_mean_window_sum_pct"], flush=True)

    yr = np.zeros(n, int)
    for jj, a0 in enumerate(anchors):
        yr[np.asarray(idx + pd.Timedelta(hours=4) >= a0)] = jj
    P = np.zeros((2, n, na, len(RUNGS6)))  # predictions of each half's model for the year the row trades in
    for j in range(1, len(anchors)):
        tr = live & np.asarray(bar_end < anchors[j] - EMBARGO)
        rows_i = np.flatnonzero(tr)
        pair = []
        for h in (0, 1):
            ri = rows_i[rows_i % 2 == h]
            Xh = np.concatenate([np.c_[X3[ri, a], hours[ri]] for a in range(na)])
            pair.append([HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=300,
                                                       l2_regularization=1.0, random_state=10 * j + h + r)
                         .fit(Xh, np.concatenate([Y[ri, a, r] for a in range(na)])) for r in range(len(RUNGS6))])
        rows_y = np.flatnonzero(yr == j)
        for a in range(na):
            Xy = np.c_[X3[rows_y, a], hours[rows_y]]
            for h in (0, 1):
                for r in range(len(RUNGS6)):
                    P[h, rows_y, a, r] = pair[h][r].predict(Xy)
        out["train"][str(anchors[j].date())] = int(tr.sum())

    def agent(margin):
        cache, stats = {}, {w: 0 for w in WINDOWS}

        def window(i, a):
            if (i, a) in cache:
                return cache[(i, a)]
            w = "standard"
            if yr[i] > 0:
                pa, pb = P[0, i, a], P[1, i, a]
                va = {k: pa[list(v)].sum() for k, v in WINDOWS.items()}
                vb = {k: pb[list(v)].sum() for k, v in WINDOWS.items()}
                ba, bb = max(va, key=va.get), max(vb, key=vb.get)
                if ba == bb and ba != "standard" and va[ba] - va["standard"] > margin and vb[bb] - vb["standard"] > margin:
                    w = ba
            cache[(i, a)] = w
            stats[w] += 1
            return w

        def flt(i, a, r):
            return 1.0 if r in WINDOWS[window(i, a)] else 0.0
        flt.stats = stats
        return flt

    std = lambda i, a, r: 1.0 if r in WINDOWS["standard"] else 0.0
    deep = lambda i, a, r: 1.0 if r in WINDOWS["deep"] else 0.0
    runs = [("standard_ref", std), ("D1_agent", agent(0.0)), ("D2_agent_strict", agent(0.001)), ("D3_fixed_deep", deep)]
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    for key, flt in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, rungs=RUNGS6, sleeve_filter=flt, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if hasattr(flt, "stats"):
            r["agent"] = dict(flt.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], r.get("agent"), flush=True)
        if key == "standard_ref":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "standard window must reproduce v247 B18"
    cands = ("D1_agent", "D2_agent_strict", "D3_fixed_deep")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
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
    (HERE / "v249_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
