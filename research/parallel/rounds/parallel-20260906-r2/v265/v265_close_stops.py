"""v265: CANDLE-CLOSE stops for the dip ladder - a wick through the stop does not stop the trade out, a close beyond it does.

Why (dev-year event study, 2024-08-05, the bar that binds the walk-forward drawdown): 18 dip rungs filled on all five coins between
00:38 and 00:57 UTC, and ALL were stopped between 01:06 and 01:10 at the bottom of a liquidation wick; the market then recovered and the
next rungs of the same day took profit. A 5-sigma touch stop is hunted exactly at the flush low. Many traders use candle-close stops for
this reason: the protective market order is still attached to every position and the loss stays bounded, but it fires only when a 1m
(or 5m) candle CLOSES at or below the stop, and it fills at the next minute's open (the gap allowance of the risk budget covers the
slippage beyond the stop).
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings otherwise). New engine argument sleeve_stop_mode ("touch" =
unchanged). TP (1 sigma limit, touch) and timeout unchanged; a same-minute TP touch and stop trigger resolve stop-first.
  S1_close1m   stop triggers on a 1m close at or below the stop
  S2_close5m   stop triggers on a 5m-block close (minutes 4, 9, ... of the bar) at or below the stop
Reference: touch stops (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among S1, S2; the most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v265/v265_close_stops.py
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
VARIANTS = {"S1_close1m": "close1", "S2_close5m": "close5"}


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
    out = {"version": "v265", "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("v247_B18", "touch")] + list(VARIANTS.items())
    for key, mode in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_stop_mode=mode, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "touch stops must reproduce v247 B18"
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
    (HERE / "v265_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
