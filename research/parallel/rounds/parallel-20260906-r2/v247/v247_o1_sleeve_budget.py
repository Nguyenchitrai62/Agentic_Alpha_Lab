"""v247: the dip-sleeve stop-risk budget on the O1 foundation (registry v247).

Why: the dip sleeve earns most of the pipeline's return and every dip-bid group has a positive expectation (v220 / v235 / v243 and the
intrabar diagnostic: filters cannot add value; the sleeve's limit is its risk budget). The budget 0.15 was chosen on the D2 books
(v218, DD 19.09); the O1 foundation has a lower DD (19.08 at dev4 5.690 with a better worst year), and on W2 the robustness grid showed a
larger budget raising returns (0.17: dev4 5.96). Only the stop-risk budget changes; the rung size (x1.75) and everything else stay.
Fixed before running (v240 O1 books, v218 D2 settings otherwise: G2 grid trader, rung x1.75, minute-5 rule, limits, SL market / TP limit,
governor, aligned sleeve, Bybit fees, adverse funding):
  B16   sleeve_risk_budget 0.16
  B17   sleeve_risk_budget 0.17
  B18   sleeve_risk_budget 0.18
Reference: v240_O1 (budget 0.15, must reproduce dev4 5.690). SELECTION = robust criterion among B16..B18 (DD <= 20 and no losing dev year
first); the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v247/v247_o1_sleeve_budget.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
VARIANTS = {"B16": 0.16, "B17": 0.17, "B18": 0.18}


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
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v247", "variants": VARIANTS, "rows": {}, "trades": {}}
    for key, budget in [("v240_O1", 0.15)] + list(VARIANTS.items()):
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev,
                        **dict(v221.KW, sleeve_risk_budget=budget))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], flush=True)
        if key == "v240_O1":
            assert abs(r["monthly_dev4"] - 5.690) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in VARIANTS})
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
    (HERE / "v247_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
