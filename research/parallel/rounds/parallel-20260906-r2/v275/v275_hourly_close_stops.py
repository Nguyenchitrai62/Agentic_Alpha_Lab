"""v275: the HOURLY dip ladder again, now with candle-close stops (v269 M1) - its old failure was wick stops in hourly flushes.

Why: an extra ladder that re-anchors every hour (engine hourly=True: bids k sigma_1h below each hour's open, minutes 4..57 of the hour,
exit by TP / stop / the hour's end) failed twice with touch stops (v201 DD 39.7, v229 DD 42-44): hourly flushes stopped the rungs at the
wick lows and the extra bids crowded the risk budget. The 5m-close stop with an 8-sigma native backstop removed exactly that failure on
the 4h ladder (v266 / v269). The hourly rungs share the same stop rules and the same stop-risk budget.
Fixed before running.
Environment = v269 M1 (O1 books, 4h dip ladder with stops on 5m closes at 4 sigma + 8-sigma native backstop, v218 D2 settings).
  H1_hourly_b18   hourly ladder on, sleeve budget 0.18
  H2_hourly_b22   hourly ladder on, sleeve budget 0.22
Reference: v269 M1 (must reproduce dev4 6.026). SELECTION = robust criterion among H1, H2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v275/v275_hourly_close_stops.py
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
B1 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0)
VARIANTS = {"H1_hourly_b18": dict(B1, hourly=True), "H2_hourly_b22": dict(B1, hourly=True, sleeve_risk_budget=0.22)}


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
    out = {"version": "v275", "variants": {k: {kk: vv for kk, vv in v.items()} for k, v in VARIANTS.items()}, "rows": {}, "trades": {}}
    runs = [("v269_M1", B1)] + list(VARIANTS.items())
    for key, extra in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **dict(KW, **extra))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
        if key == "v269_M1":
            assert abs(r["monthly_dev4"] - 6.026) < 0.002, "must reproduce v269 M1"
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
    (HERE / "v275_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
