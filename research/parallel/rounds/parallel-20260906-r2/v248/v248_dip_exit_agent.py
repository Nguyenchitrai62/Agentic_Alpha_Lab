"""v248: a learned dip-exit agent - choose the take-profit of every filled dip bid (contextual bandit with EXACT counterfactuals).

Why (RL on the part of the pipeline that earns most): every dip bid exits by a take-profit limit at 1 sigma_4h above the fill, a stop at
5 sigma below, or at the next 4h open. Entry filters cannot help (all groups are positive, v220 / v235 / v243 / intrabar diagnostic), but
the diagnostic showed that FAST drops revert more than slow grinds - the right exit may differ by situation. Unlike the earlier value-based
agents, the outcome of every alternative exit is known exactly from the 1m path after the fill (full-information bandit): no exploration,
no bootstrapped values.
Fixed before running.
Environment: v240 O1 books with the v247 sleeve budget 0.18 (current best), v218 D2 settings otherwise (G2 grid trader, rung x1.75,
minute-5 rule, limits, SL market 5 sigma / TP limit, governor, aligned sleeve, Bybit fees, adverse funding).
Actions at the fill: take-profit multiple m in {0.5, 1.0, 1.5, 2.0} sigma_4h (engine hook sleeve_tp; stop and timeout unchanged).
Counterfactual data: four engine runs with a fixed multiple (0.5 / 1.0 / 1.5 / 2.0); fills matched on (time, coin, rung) -> net return
of each action. State at the fill (known at the minute before the fill): pre-fill speed (30-minute log return to minute f-1 over
sigma_1m * sqrt(30), sigma_1m from the previous 24 h), rung depth, sigma_4h regime (sigma / 540-bar median), the coin's 4h SuperTrend
direction and order-level fl_big_imb6 at the decision row, hour of day. Model: per action HistGradientBoostingRegressor (depth 3, lr 0.05,
200 iter, min leaf 200) on the clipped net return, two models per year on even / odd fills (cross-fitting); fits use fills that EXITED
before Y - 7 days; 2021 uses m = 1.0.
Policy: argmax of the averaged predictions; deviate from 1.0 only if both halves prefer the same action by more than the margin.
  T1_agent        margin 0.0
  T2_agent_strict margin 0.05% (0.0005)
  T3_fixed_1_5    no learning: m = 1.5 for every fill (tests whether 1.0 is simply too tight)
Reference: v247_B18 (m = 1.0, must reproduce dev4 5.777). SELECTION = robust criterion among T1..T3; the most recent year is scored once for
the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v248/v248_dip_exit_agent.py
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
ACTIONS = (0.5, 1.0, 1.5, 2.0)
EMBARGO = pd.Timedelta(days=7)
BUDGET = 0.18


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_x", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_x", RD / "v240/v240_order_level_flow.py")
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
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]

    # ---- state pieces known before the fill
    Cm = prep["C"]  # (bars, 240, assets) 1m closes of each holding bar
    st_dir = v232.tv_frames(idx, cols)["tv_st_dir"].to_numpy(float)
    flow = np.stack([v240.flo.flow_features(s, idx)["fl_big_imb6"].to_numpy(float) for s in cols], axis=1)
    o1 = opens.reindex(idx)[cols].shift(-1)
    sig = np.log(o1).diff().rolling(360, min_periods=120).std()
    vol = (sig / sig.rolling(540, min_periods=180).median()).to_numpy(float)
    flat = Cm.reshape(-1, Cm.shape[2])  # continuous 1m closes (bar i minute f -> row i*240+f)
    lr = np.diff(np.log(flat), axis=0, prepend=np.nan)
    sig1 = pd.DataFrame(lr).rolling(1440, min_periods=720).std().to_numpy()

    def state(i, a, r, f):
        k = i * 240 + f - 1  # last fully known minute
        sp = np.log(flat[k, a] / flat[k - 30, a]) / (sig1[k, a] * np.sqrt(30)) if k >= 30 and sig1[k, a] > 0 else 0.0
        return np.nan_to_num(np.array([sp, float(eu.RUNGS[r]), vol[i, a], st_dir[i, a], flow[i, a], (idx[i].hour + 4) % 24], float))

    # ---- counterfactual outcomes: one engine run per fixed action, fills matched on (fill time, coin, rung)
    per_action, feats, meta = {}, {}, {}
    for mult in ACTIONS:
        ev = []
        rec = {}

        def hook(i, a, r, f, mult=mult):
            key = (i, a, r, f)
            if key not in feats:
                feats[key] = state(i, a, r, f)
            rec[(idx[i], a, r, f)] = key
            return mult
        res = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_tp=hook, **KW)
        if mult == 1.0:
            assert abs(res["monthly_dev4"] - 5.777) < 0.002, "m = 1.0 must reproduce v247 B18"
        pend, outc = {}, {}
        for e in ev:
            if e["kind"] == "rung_fill":
                pend[e["symbol"]] = e
            elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and e["symbol"] in pend:
                f0 = pend.pop(e["symbol"])
                bar = f0["t"].floor("4h") - pd.Timedelta(hours=4)
                fm = int((f0["t"] - (bar + pd.Timedelta(hours=4))).total_seconds() // 60)
                a = cols.index(e["symbol"])
                r = list(eu.RUNGS).index(f0["rung"])
                k = rec.get((bar, a, r, fm))
                if k is not None:
                    outc[k] = (float(e["ret"]), e["t"])
        per_action[mult] = outc
        print(f"action {mult}: dev4 {res['monthly_dev4']} fills {len(outc)}", flush=True)
    keys = sorted(set.intersection(*[set(v) for v in per_action.values()]))
    X = np.array([feats[k] for k in keys])
    Y = np.clip(np.array([[per_action[mu][k][0] for mu in ACTIONS] for k in keys]), -0.10, 0.08)
    t_exit = pd.DatetimeIndex([max(per_action[mu][k][1] for mu in ACTIONS) for k in keys])
    t_fill = pd.DatetimeIndex([idx[k[0]] + pd.Timedelta(hours=4) for k in keys])
    half = np.array([k[0] % 2 for k in keys])
    out = {"version": "v248", "actions": ACTIONS, "matched_fills": len(keys), "train": {}, "rows": {}, "trades": {}}
    dev = np.asarray(t_fill < anchors[4])
    out["dev_mean_net_by_action_pct"] = {str(mu): round(100 * float(Y[dev, j].mean()), 4) for j, mu in enumerate(ACTIONS)}
    print("matched fills", len(keys), "dev mean net by action %", out["dev_mean_net_by_action_pct"], flush=True)

    models = {}
    for j in range(1, len(anchors)):
        keep = np.asarray(t_exit < anchors[j] - EMBARGO)
        pair = []
        for h in (0, 1):
            sel = keep & (half == h)
            pair.append([HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200,
                                                       l2_regularization=1.0, random_state=10 * j + h + 3 * c).fit(X[sel], Y[sel, c])
                         for c in range(len(ACTIONS))])
        models[j] = pair
        out["train"][str(anchors[j].date())] = int(keep.sum())

    def year(i):
        t = idx[i] + pd.Timedelta(hours=4)
        k = 0
        for jj, a0 in enumerate(anchors):
            if t >= a0:
                k = jj
        return k

    base = ACTIONS.index(1.0)

    def agent(margin):
        stats = {"asked": 0, "changed": {str(mu): 0 for mu in ACTIONS}}

        def pol(i, a, r, f):
            jj = year(i)
            if jj == 0:
                return 1.0
            x = state(i, a, r, f)[None, :]
            pa = np.array([mm.predict(x)[0] for mm in models[jj][0]])
            pb = np.array([mm.predict(x)[0] for mm in models[jj][1]])
            best_a, best_b = int(np.argmax(pa)), int(np.argmax(pb))
            stats["asked"] += 1
            if best_a == best_b and best_a != base and pa[best_a] - pa[base] > margin and pb[best_b] - pb[base] > margin:
                stats["changed"][str(ACTIONS[best_a])] += 1
                return ACTIONS[best_a]
            return 1.0
        pol.stats = stats
        return pol

    runs = [("v247_B18", None), ("T1_agent", agent(0.0)), ("T2_agent_strict", agent(0.0005)), ("T3_fixed_1_5", lambda i, a, r, f: 1.5)]
    for key, hook in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_tp=hook, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if hasattr(hook, "stats"):
            r["agent"] = dict(hook.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], r.get("agent"), flush=True)
    cands = ("T1_agent", "T2_agent_strict", "T3_fixed_1_5")
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
    (HERE / "v248_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
