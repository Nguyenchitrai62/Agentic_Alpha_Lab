"""v251: strategy-level volatility targeting - a trader sizes down after a turbulent month and back up when the book runs smoothly.

Why: dev-only diagnostic (research/diagnostics/o1_dd_episodes/strategy_vol_dev.py, first four walk-forward years): the O1 + budget 0.18
strategy's own trailing 30-day volatility predicts its NEXT 30-day return negatively in every dev year (Spearman -0.20 / -0.08 / -0.39 /
-0.33; calm half vs volatile half +4.3/+1.9, +4.6/+0.9, +11.2/+2.7, +11.5/+7.3 % per 30 days) with similar future drawdowns. Scaling the
whole strategy by its own volatility should buy return in calm regimes and cut exposure in turbulent ones at the same DD.
Fixed before running.
Environment: v240 O1 books, v247 sleeve budget 0.18 (current best), v218 D2 settings otherwise (G2 grid trader, rung x1.75, minute-5 rule,
limits, SL market 5 sigma / TP limit 1 sigma, governor, aligned sleeve, Bybit fees, adverse funding). New engine hook strat_vt: the
governor (which scales book targets and dip-rung sizes) is multiplied by clip((M / V) ** power, lo, hi), V = annualised std of the 4h log
equity changes over the last 30 days up to bar i-2 (same lag as the DD governor), M = median of all earlier bars' V (expanding, nothing is
fitted; the same rule runs in every year); multiplier 1 during the first 90 days. The sleeve's absolute stop-risk budget 0.18 still caps
the ladder, the 20% DD governor still acts.
  V1_vt_wide     lo 0.5, hi 1.5
  V2_vt_narrow   lo 0.7, hi 1.3
  V3_derisk_only lo 0.5, hi 1.0 (never levers up)
Reference: strat_vt None (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among V1..V3; the most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v251/v251_strategy_vol_target.py
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
VARIANTS = {"V1_vt_wide": dict(lo=0.5, hi=1.5), "V2_vt_narrow": dict(lo=0.7, hi=1.3), "V3_derisk_only": dict(lo=0.5, hi=1.0)}


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
    out = {"version": "v251", "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("v247_B18", None)] + list(VARIANTS.items())
    for key, vt in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, strat_vt=vt, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], "mean governor", round(float(r.get("governor_mean", float("nan"))), 3) if "governor_mean" in r else None, flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "strat_vt None must reproduce v247 B18"
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
    (HERE / "v251_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
