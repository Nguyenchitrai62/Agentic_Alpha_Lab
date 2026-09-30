"""v292: a stress-robust CB - select the risk levels by drawdown under realistic stress, not only in the base run (registry v292).

Why (user: results must be GENERAL): CB passes the gate in the base run (DD 18.39) but its drawdown breaks 20% under the cost-stress
row (maker 0.04% / taker 0.07% + 5 bps: 20.75) and 30-minute latency (22.49) (research/diagnostics/d2c_robustness). A live bot pays
more than the base costs at times and sometimes reacts late, so the risk level should be chosen where the drawdown survives those
rows. Candidates change only the two risk dials of CB (the dip-sleeve risk budget and the book vol target); no new model or data.
Disclosure: the d2c robustness report already showed CB at sleeve budget 0.16 (dev4 5.952, DD 17.49, most recent year 5.151 vs CB
5.167 - the unseen-year value is equal, so it gives no hidden-year advantage); that report motivates this version.
Rows (every engine argument = CB / C4 rules: G2 grid trader, close5 dip stops 4 sigma + 8-sigma backstop, v221.KW, minute-5 rule, limit
entries, SL market / TP limit, Bybit fees, adverse funding), each run in three conditions: base, cost_stress (maker 0.0004,
taker 0.0007 + 0.0005, exactly as d2c_robustness), latency_15 (win_start 15). latency_30 is reported for information only.
  CB_ref     sleeve budget 0.18, target 0.25        R1_b16    budget 0.16, target 0.25
  R2_b14     budget 0.14, target 0.25               R3_t23    budget 0.18, target 0.23
SELECTION (dev years only): pool = rows whose dev DD (max yearly 1m-marked DD 2021-2024) is <= 20 and with no losing dev year in ALL three
conditions; within the pool the v204 robust criterion on the base condition (prefer dev4 >= 5, then the highest worst dev year, ties ->
dev4). If the pool is empty, CB stays. The selected row replaces CB only if it is not CB_ref; its most recent year (base) is scored once.

  python research/parallel/rounds/parallel-20260906-r2/v292/v292_stress_robust_cb.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C4R = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0)
ROWS = {"CB_ref": (0.18, 0.25), "R1_b16": (0.16, 0.25), "R2_b14": (0.14, 0.25), "R3_t23": (0.18, 0.23)}
CONDS = {"base": {}, "cost_stress": dict(maker=0.0004, taker=0.0007 + 0.0005), "latency_15": dict(win_start=15),
         "latency_30": dict(win_start=30)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_r", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    maker0, taker0 = eu.MAKER, eu.TAKER
    out = {"version": "v292", "rows": {}, "trades": {}}
    for key, (budget, target) in ROWS.items():
        out["rows"][key], out["trades"][key] = {}, {}
        for cond, c in CONDS.items():
            eu.MAKER, eu.TAKER = c.get("maker", maker0), c.get("taker", taker0)
            try:
                ev = []
                r = eu.simulate(cb, opens, prep, trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)),
                                win_start=c.get("win_start", 5), events=ev, target=target,
                                **dict(v221.KW, sleeve_risk_budget=budget, **C4R))
            finally:
                eu.MAKER, eu.TAKER = maker0, taker0
            r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
            r["dev_dd"] = v286.dev_dd(r)
            out["rows"][key][cond], out["trades"][key][cond] = r, v213.trade_stats(ev)
            print(key, cond, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
                  "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
        if key == "CB_ref":
            assert abs(out["rows"][key]["base"]["monthly_dev4"] - 5.864) < 0.002
    sel_conds = ("base", "cost_stress", "latency_15")
    pool = {k: out["rows"][k]["base"] for k in ROWS
            if all(out["rows"][k][c]["dev_dd"] <= 20 and all(y["net_pct"] >= 0 for y in out["rows"][k][c]["yearly"][:4]) for c in sel_conds)}
    out["stress_pool"] = sorted(pool)
    if pool:
        five = {k: v for k, v in pool.items() if v["monthly_dev4"] >= 5} or pool
        sel = max(five, key=lambda k: (round(v204.worst_month(five[k]), 4), five[k]["monthly_dev4"]))
    else:
        sel = "CB_ref"
    out["selected"], out["replaces_cb"] = sel, sel != "CB_ref"
    s_ = out["rows"][sel]["base"]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["base"]["_hidden"],
                                   "stress_gate_dd": {c: out["rows"][sel][c]["gate_dd"] for c in CONDS}}
    for k in ROWS:
        for c in CONDS:
            if not (k == sel and c == "base"):
                out["trades"][k][c].pop("_hidden", None)
                if not (k == sel):
                    for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                        out["rows"][k][c].pop(fld, None)
                    out["rows"][k][c]["yearly"] = out["rows"][k][c]["yearly"][:4]
                else:
                    for fld in ("monthly_last_year", "monthly_5y", "losing_years", "gate_pass"):
                        out["rows"][k][c].pop(fld, None)
                    out["rows"][k][c]["yearly"] = out["rows"][k][c]["yearly"][:4]
    print("POOL", out["stress_pool"], "SELECTED", sel, "replaces CB:", out["replaces_cb"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v292_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
