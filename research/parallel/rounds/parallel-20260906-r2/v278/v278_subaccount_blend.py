"""v278: two SUB-ACCOUNTS running different dip-stop designs (50/50, rebalanced every 4h bar) - diversification across stop rules.

Why: the candle-close stop designs differ in where they are strong: v266 B1 (5-sigma close stop) has the best weakest dev year (3.257),
v269 M1 (4-sigma close stop) the lowest drawdown (18.27). If their good and bad stretches do not coincide, a constant 50/50 mix of two
accounts may raise the weakest year and lower the drawdown. The deployed O1 (touch stops) mixed with B1 is the second candidate.
Fixed before running.
Each component is the full engine run (O1 books, v218 D2 settings, budget 0.18) with its own stop rules; the mix return of a bar is
0.5 r_1 + 0.5 r_2 (constant-mix rebalanced every 4h bar, i.e. two sub-accounts topped up to equal size at each close - a realistic
monthly/daily rebalance would drift less). Intrabar drawdown of the mix is bounded conservatively by the SUM of the two components'
intrabar minima (the true joint minimum is never lower than that). Metrics via the engine's own summarize().
  Q1_B1_M1   0.5 x v266 B1 + 0.5 x v269 M1
  Q2_O1_B1   0.5 x O1 B18 + 0.5 x v266 B1
References: O1 B18 (5.777), v266 B1 (6.13), v269 M1 (6.026). SELECTION = robust criterion among Q1, Q2; the most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v278/v278_subaccount_blend.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
CFG = {"O1": dict(), "B1": dict(sleeve_stop_mode="close5", sleeve_backstop=8.0),
       "M1": dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0)}
REF_DEV4 = {"O1": 5.777, "B1": 6.13, "M1": 6.026}
MIXES = {"Q1_B1_M1": ("B1", "M1"), "Q2_O1_B1": ("O1", "B1")}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204 = v221.eu, v221.v216, v221.v204
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    orig = eu.summarize
    paths, out = {}, {"version": "v278", "rows": {}}
    for k, extra in CFG.items():
        cap = {}

        def grab(idx_, net, eq, eq_min, g, stats, eq_max=None):
            cap.update(eq=eq.copy(), eq_min=eq_min.copy(), eq_max=(eq_max.copy() if eq_max is not None else eq.copy()), g=g.copy(), stats=dict(stats))
            return orig(idx_, net, eq, eq_min, g, stats, eq_max)
        eu.summarize = grab
        try:
            r = eu.simulate(books, opens, prep, trade=trade, win_start=5, **dict(v221.KW, sleeve_risk_budget=0.18, **extra))
        finally:
            eu.summarize = orig
        assert abs(r["monthly_dev4"] - REF_DEV4[k]) < 0.002, k
        paths[k] = cap
        out["rows"][f"ref_{k}"] = {kk: r[kk] for kk in ("monthly_dev4", "gate_dd")}
    n = len(idx)
    for key, (a, b) in MIXES.items():
        pa, pb = paths[a], paths[b]
        eq = np.ones(n)
        eq_min = np.ones(n)
        eq_max = np.ones(n)
        net = np.zeros(n)
        for i in range(n):
            prev_a = pa["eq"][i - 1] if i else 1.0
            prev_b = pb["eq"][i - 1] if i else 1.0
            ra, rb = pa["eq"][i] / prev_a - 1, pb["eq"][i] / prev_b - 1
            ma, mb = pa["eq_min"][i] / prev_a - 1, pb["eq_min"][i] / prev_b - 1
            xa, xb = pa["eq_max"][i] / prev_a - 1, pb["eq_max"][i] / prev_b - 1
            prev = eq[i - 1] if i else 1.0
            net[i] = 0.5 * ra + 0.5 * rb
            eq[i] = prev * (1 + net[i])
            eq_min[i] = prev * (1 + 0.5 * ma + 0.5 * mb)
            eq_max[i] = prev * (1 + max(0.5 * xa + 0.5 * xb, net[i]))
        r = eu.summarize(idx, net, eq, np.minimum(eq_min, eq), np.minimum(pa["g"], pb["g"]), pa["stats"], eq_max)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
    sel = v204.robust_select({k: out["rows"][k] for k in MIXES})
    s_ = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]]}
    for k in MIXES:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v278_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
