"""v270: the v267 STRESS-ROBUST rule applied to the tighter close stop (v269 M1: 4-sigma dip stop on 5m closes, DD 18.27).

Why: v267 found no design (not even the deployed O1) that keeps the dev drawdown <= 20% under the cost-stress and 15-minute-latency rows.
v269 M1 lowered the base DD from 19.70 (B1) to 18.27 at a similar return, i.e. it bought a 1.4 pp DD margin; the question is whether that
margin survives the stress rows, and whether part of it can be spent on a larger dip budget. The rule is exactly v267's.
Fixed before running.
Candidates (engine_user trade mode, O1 books, v218 D2 settings, G2 grid, dip stops on 5m closes + 8-sigma native backstop):
  N1_M1            close stop 4 sigma, budget 0.18 (v269 M1)
  N2_M1_budget20   close stop 4 sigma, budget 0.20
Scenarios: base; cost_stress (maker 0.04%, taker 0.07% + 5 bps on taker fills); latency_15 (a new book order may fill only from minute 15).
dev DD = max of the per-year 1m-marked DD over the first four walk-forward years.
SELECTION (v267 rule): pool = candidates with dev DD <= 20 in ALL three scenarios and no losing dev year (base); pick the highest worst
dev year (base), ties -> higher base dev4; empty pool -> keep the deployed O1 (R0_O1 reference). The most recent year is scored once for
the selected row (N1's was already seen in v269).

  python research/parallel/rounds/parallel-20260906-r2/v270/v270_stress_select_close4.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
CANDS = {"R0_O1": dict(budget=0.18, extra={}),
         "N1_M1": dict(budget=0.18, extra=dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0)),
         "N2_M1_budget20": dict(budget=0.20, extra=dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0))}
SCEN = {"base": dict(), "cost_stress": dict(maker=0.0004, taker=0.0007 + 0.0005), "latency_15": dict(win_start=15)}


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
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    maker0, taker0 = eu.MAKER, eu.TAKER
    out = {"version": "v270", "rows": {}, "trades": {}, "dev_dd": {}}
    for key, c in CANDS.items():
        for sc, s in SCEN.items():
            eu.MAKER, eu.TAKER = s.get("maker", maker0), s.get("taker", taker0)
            try:
                ev = [] if sc == "base" else None
                r = eu.simulate(books, opens, prep, trade=trade, win_start=s.get("win_start", 5), events=ev,
                                **dict(v221.KW, **dict(c["extra"], sleeve_risk_budget=c["budget"])))
            finally:
                eu.MAKER, eu.TAKER = maker0, taker0
            r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
            dd = max(y["dd_1m_pct"] for y in r["yearly"][:4])
            out["dev_dd"][f"{key}|{sc}"] = dd
            if sc == "base":
                out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
                if key == "R0_O1":
                    assert abs(r["monthly_dev4"] - 5.777) < 0.002
            print(key, sc, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "dev DD", dd,
                  "dev years", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
    pool = [k for k in CANDS if k != "R0_O1" and all(out["dev_dd"][f"{k}|{sc}"] <= 20 for sc in SCEN)
            and all(y["net_pct"] >= 0 for y in out["rows"][k]["yearly"][:4])]
    sel = max(pool, key=lambda k: (round(out["rows"][k]["worst_dev_month_pct"], 4), out["rows"][k]["monthly_dev4"])) if pool else "R0_O1"
    out["pool"], out["selected"] = pool, sel
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
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("POOL", pool, "SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v270_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
