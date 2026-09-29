"""v272: the RL optimal-stopping agent of v271 WITH a budget lock - a cut dip rung keeps its risk in the budget until the bar ends.

Why: v271's agent (cut a losing dip rung at a 5m close when the cross-fitted value model predicts that cutting beats following the B1 rule)
made the drawdown worse (21.3) although it cut only 26-42 rungs: every cut freed risk budget that the next, deeper rungs of the SAME flush
immediately used, so the account ended up with more exposure in the cascade, not less. A disciplined trader who cuts a position does not
re-load the same risk into the same falling market. Fix: the stop risk of an agent-cut rung stays counted in the budget until the 4h bar
ends. Everything else (data, state, models, margins, walk-forward windows) is exactly v271's.
Fixed before running.
Environment = v266 B1 (O1 books, sleeve budget 0.18, dip stops on 5m closes at 5 sigma + 8-sigma native backstop, v218 D2 settings) + new
engine flag sleeve_lock_cut=True in the agent rows.
  L1_agent_lock          margin 0, budget lock
  L2_agent_strict_lock   margin 0.002, budget lock
Reference: v266 B1 (must reproduce dev4 6.13). SELECTION = robust criterion among L1, L2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v272/v272_stop_agent_lock.py
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
EMBARGO = pd.Timedelta(days=7)
B1 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    Cc = eu.er.CACHE
    m = {k: pd.read_parquet(Cc / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    KW = dict(v221.KW, **B1)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    C, O, L, sig4, o2 = prep["C"], prep["O"], prep["L"], prep["sig4"], prep["o2"]
    b = cols.index("BTCUSDT")
    t_hold = idx + pd.Timedelta(hours=4)
    hours = np.array([t.hour for t in t_hold], float)

    def state(i, a, f, c, lv, sg):
        cc = float(C[i, c, a])
        lo = float(np.nanmin(L[i, f:c + 1, a]))
        r5 = (cc / float(C[i, c - 5, a]) - 1) / sg if c >= 5 else 0.0
        r15 = (cc / float(C[i, c - 15, a]) - 1) / sg if c >= 15 else 0.0
        btc = (float(C[i, c, b]) / float(O[i, 0, b]) - 1) / sig4[i][b] if np.isfinite(sig4[i][b]) and sig4[i][b] > 0 else 0.0
        nfl = float(np.nansum(C[i, c, :].astype(float) <= O[i, 0, :].astype(float) * (1 - 2 * sig4[i])))
        return np.nan_to_num(np.array([(cc / lv - 1) / sg, (c - f) / 240, (239 - c) / 240, r5, r15, (lo / lv - 1) / sg,
                                       (cc / lo - 1) / sg, btc, nfl, (hours[i] + c / 60) / 24], float))

    def run(agent=None, ev=None, lock=False):
        return eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_exit_agent=agent, sleeve_lock_cut=lock, **KW)

    # ---- data: record every checkpoint of a B1 run (the recorder always holds)
    rec = []

    def recorder(i, a, r, f, c, lv, sg):
        rec.append((i, a, r, f, c, lv, sg))
        return False
    ev = []
    r0 = run(recorder, ev)
    assert abs(r0["monthly_dev4"] - 6.13) < 0.002, "the recording run must reproduce v266 B1"
    rung_ret, last = {}, None
    for e in ev:
        if e["kind"] == "rung_fill":
            last = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and last is not None:
            t0 = last["t"].floor("4h")
            i = int(np.searchsorted(t_hold, t0))
            f = int((last["t"] - t0).total_seconds() // 60)
            rung_ret[(i, cols.index(last["symbol"]), float(last["rung"]), f)] = float(e["ret"])
            last = None
    rungs = list(v221.KW.get("rungs", eu.RUNGS))
    X, Y, I, keep = [], [], [], []
    for (i, a, r, f, c, lv, sg) in rec:
        hold = rung_ret.get((i, a, float(rungs[r]), f))
        if hold is None:
            continue
        px = float(O[i, c + 1, a]) if c + 1 < 240 else float(o2[i][a])
        X.append(state(i, a, f, c, lv, sg))
        Y.append(np.clip(px / lv - 1 - eu.MAKER - eu.TAKER - hold, -0.05, 0.05))
        I.append(i)
    X, Y, I = np.array(X), np.array(Y), np.array(I)
    bar_end = t_hold[I] + pd.Timedelta(hours=4)
    dev = np.asarray((t_hold[I] >= anchors[0]) & (t_hold[I] < anchors[4]))
    out = {"version": "v272", "checkpoints": int(len(Y)), "dev_mean_advantage_pct": round(100 * float(Y[dev].mean()), 4),
           "dev_share_positive": round(float((Y[dev] > 0).mean()), 3), "train": {}, "rows": {}, "trades": {}}
    print("checkpoints", len(Y), "dev mean adv %", out["dev_mean_advantage_pct"], "share > 0", out["dev_share_positive"], flush=True)
    models = {}
    for j in range(1, len(anchors)):
        tr = np.asarray((bar_end < anchors[j] - EMBARGO) & (t_hold[I] >= anchors[0]))
        models[j] = [HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                                   random_state=10 * j + h).fit(X[tr & (I % 2 == h)], Y[tr & (I % 2 == h)]) for h in (0, 1)]
        out["train"][str(anchors[j].date())] = int(tr.sum())

    def year(i):
        t = t_hold[i]
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    def agent(margin):
        stats = {"asked": 0, "cut": 0}

        def ag(i, a, r, f, c, lv, sg):
            jj = year(i)
            if jj == 0:
                return False
            x = state(i, a, f, c, lv, sg)[None, :]
            stats["asked"] += 1
            if all(mm.predict(x)[0] > margin for mm in models[jj]):
                stats["cut"] += 1
                return True
            return False
        ag.stats = stats
        return ag

    for key, ag in (("v266_B1", None), ("L1_agent_lock", agent(0.0)), ("L2_agent_strict_lock", agent(0.002))):
        ev = []
        r = run(ag, ev, lock=ag is not None)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if ag is not None:
            r["agent"] = dict(ag.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], r.get("agent"), flush=True)
    cands = ("L1_agent_lock", "L2_agent_strict_lock")
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
    (HERE / "v272_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
