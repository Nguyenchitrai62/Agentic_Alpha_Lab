"""v255: let the dip ladder work from minute 5 of the bar (the user's execution rule) instead of the legacy minute 16.

Why: the 4h dip-ladder bids fill only from minute 16 of the holding bar - a leftover of the v171 era (15-minute strict execution). The
user's executable rule (2026-09-28) is that no order may fill in the first 5 minutes after the 4h close; from minute 5 a resting limit
fills on a 1m trade-through. Liquidation cascades often start right after a 4h close, so minutes 5..15 may hold flushes the ladder
misses. The levels (bar open, sigma_4h) are known at the close, so the bids can rest from minute 5 exactly like the book orders.
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings otherwise). New engine argument sleeve_start (default 16 =
unchanged results): first holding-bar minute in which a 4h ladder bid may fill.
  M1_start5    sleeve_start = 5  (the user rule)
  M2_start10   sleeve_start = 10 (5 more minutes of slack for a slow pipeline / human)
Reference: sleeve_start 16 (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among M1, M2; the most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v255/v255_sleeve_start.py
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
VARIANTS = {"M1_start5": 5, "M2_start10": 10}


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
    out = {"version": "v255", "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("v247_B18", 16)] + list(VARIANTS.items())
    for key, st in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_start=st, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "sleeve_start 16 must reproduce v247 B18"
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
    (HERE / "v255_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
