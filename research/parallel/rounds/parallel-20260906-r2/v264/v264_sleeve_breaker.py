"""v264: a CIRCUIT BREAKER for the dip ladder - stop adding bids while the bar's dip trades are bleeding (trader discipline in a cascade).

Why: the binding drawdown of the deployed O1 B18 pipeline (2023 walk-forward year, 19.65%) is essentially one bar (2024-08-05): the ladder
kept filling deeper rungs on all five coins while the market kept falling, and the stops hit together (sleeve -12.3% in one bar). A
trader stops catching the knife once the open dip positions are deep in loss. Fills are processed minute by minute, so the rule is causal:
a new fill at minute f is skipped when the rungs already taken in this bar are marked below -X of equity at the close of minute f-1
(realised exits included). If the breaker cuts the crash tail, the freed drawdown can carry a larger budget.
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings otherwise). New engine argument sleeve_breaker (None = unchanged).
  C1_break3          breaker X = 3% of equity, budget 0.18
  C2_break5          breaker X = 5%, budget 0.18
  C3_break3_b22      breaker X = 3%, budget 0.22
Reference: no breaker (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among C1..C3; the most recent year is scored once
for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v264/v264_sleeve_breaker.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
BUDGET = 0.18
VARIANTS = {"C1_break3": (0.03, 0.18), "C2_break5": (0.05, 0.18), "C3_break3_b22": (0.03, 0.22)}


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
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    out = {"version": "v264", "variants": {k: list(v) for k, v in VARIANTS.items()}, "rows": {}, "trades": {}}
    runs = [("v247_B18", (None, BUDGET))] + list(VARIANTS.items())
    for key, (brk, bud) in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_breaker=brk, **dict(KW, sleeve_risk_budget=bud))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "no breaker must reproduce v247 B18"
    cands = tuple(VARIANTS)
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
    (HERE / "v264_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
