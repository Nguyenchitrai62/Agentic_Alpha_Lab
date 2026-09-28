"""v246: ensemble of the two whale-flow measurements (per-price fills W2 and rebuilt orders O1) in the A members (registry v246).

Why: W2 (fill-level whale flow) has the best dev mean (5.774, worst year 2.491), O1 (order-level) the best worst year (2.759) and DD
(19.08); both reach ~4.1%/month in the most recent year. The two A members learn the same phenomenon from two different measurements
of it; averaging members that are individually good but not identical is the classic variance reduction (the earlier information
ensembles failed only when a member was weak alone).
Fixed before running (cached, audited members; everything else = v218 D2 settings: G2 grid trader, sleeve budget 0.15, rung x1.75,
minute-5 rule, limits, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding; B members = T3):
  E1_w2_o1       A = (A_whale + A_O1) / 2, Aq = (Aq_whale + Aq_O1) / 2
  E2_t3_w2_o1    A = (A_tv + A_whale + A_O1) / 3, Aq likewise (adds the no-flow TradingView member)
References: v236_W2 (5.774) and v240_O1 (5.690). SELECTION = robust criterion among E1, E2; the most recent year is scored once for
the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v246/v246_flow_ensemble.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent


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
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols]
    m = {"A_tv": rd("member_A_tv_annual.parquet"), "Aq_tv": rd("member_Aq_tv.parquet"),
         "A_w": rd("member_A_whale.parquet"), "Aq_w": rd("member_Aq_whale.parquet"),
         "A_o": rd("member_A_O1_orders.parquet"), "Aq_o": rd("member_Aq_O1_orders.parquet"),
         "B": rd("member_B_tv.parquet"), "Bq": rd("member_Bq_tv.parquet")}
    book = lambda A, Aq: 0.5 * (A + m["B"]) / 2 + 0.5 * (Aq + m["Bq"]) / 2
    mixes = {"v236_W2": book(m["A_w"], m["Aq_w"]), "v240_O1": book(m["A_o"], m["Aq_o"]),
             "E1_w2_o1": book((m["A_w"] + m["A_o"]) / 2, (m["Aq_w"] + m["Aq_o"]) / 2),
             "E2_t3_w2_o1": book((m["A_tv"] + m["A_w"] + m["A_o"]) / 3, (m["Aq_tv"] + m["Aq_w"] + m["Aq_o"]) / 3)}
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v246", "rows": {}, "trades": {}}
    for key, books in mixes.items():
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v236_W2":
            assert abs(r["monthly_dev4"] - 5.774) < 0.002
        if key == "v240_O1":
            assert abs(r["monthly_dev4"] - 5.690) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("E1_w2_o1", "E2_t3_w2_o1")})
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
    (HERE / "v246_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
