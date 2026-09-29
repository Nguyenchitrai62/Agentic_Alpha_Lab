"""v250: size the four dip bids by depth like a trader scaling in (pyramid ladder) - O1 books, sleeve budget 0.18.

Why: every rung of the dip ladder (2.5 / 3 / 3.5 / 4 sigma_4h below the bar open) has the same size. A trader who buys a flush usually
bids light near the price and heavier deeper down, where the move is more stretched and the reversion larger; the opposite (heavy near,
light deep) buys more of the frequent shallow dips. The risk budget counts every rung at its stop distance, so the per-rung weights change
how the budget is spent across depths without changing the total ladder size (weights average 1).
Fixed before running.
Environment: v240 O1 books, v247 sleeve budget 0.18 (current best), v218 D2 settings otherwise (G2 grid trader, rung x1.75, minute-5 rule,
limits, SL market 5 sigma / TP limit 1 sigma, governor, aligned sleeve, Bybit fees, adverse funding). Rung weights via the engine's
sleeve_filter hook (a multiplier per rung, known when the ladder is placed):
  P1_pyramid        (0.7, 0.9, 1.1, 1.3)
  P2_pyramid_steep  (0.4, 0.8, 1.2, 1.6)
  P3_inverse        (1.3, 1.1, 0.9, 0.7)
Reference: equal weights (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among P1..P3; the most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v250/v250_pyramid_ladder.py
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
VARIANTS = {"P1_pyramid": (0.7, 0.9, 1.1, 1.3), "P2_pyramid_steep": (0.4, 0.8, 1.2, 1.6), "P3_inverse": (1.3, 1.1, 0.9, 0.7)}


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
    out = {"version": "v250", "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("v247_B18", None)] + [(k, (lambda w: (lambda i, a, r: w[r]))(w)) for k, w in VARIANTS.items()]
    for key, flt in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_filter=flt, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "equal weights must reproduce v247 B18"
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
    (HERE / "v250_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
