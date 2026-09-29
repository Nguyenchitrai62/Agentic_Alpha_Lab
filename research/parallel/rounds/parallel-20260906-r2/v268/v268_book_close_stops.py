"""v268: candle-close stops for the BOOK positions too (on top of v266 B1) - a wick through a trend trade's stop no longer ends the trade.

Why: v266 B1 showed that the dip rungs were stopped at liquidation-wick lows and recovered; closing-price stops (5m close, bot-watched) plus
an exchange-native disaster stop raised every dev metric and the unseen year. The book positions (G2 grid trader, median hold 44 h) carry
touch stops at 4 sigma_d (market); the same wicks can stop a trend trade out just before it resumes. A trader who holds a swing position
often uses candle-close stops (5m or 1h close) with a wider hard stop on the exchange.
Fixed before running.
Environment = v266 B1 (O1 books, sleeve budget 0.18, dip stops on 5m closes + 8-sigma native backstop, v218 D2 settings otherwise).
New engine arguments book_stop_mode / book_backstop (defaults = unchanged): the book stop (same level: 4 sigma_d initial, break-even /
tighten moves unchanged) fires on a block close beyond it and fills at the next minute's open; a native touch stop 2 sigma_d beyond it
(book_backstop 6) protects the position if the bot fails and wins on any tie.
  K1_book_close5    book stops on 5m closes + 6-sigma_d native backstop
  K2_book_close60   book stops on 1h closes + 6-sigma_d native backstop
Reference: v266 B1 (must reproduce dev4 6.13). SELECTION = robust criterion among K1, K2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v268/v268_book_close_stops.py
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
B1 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0)
VARIANTS = {"K1_book_close5": dict(B1, book_stop_mode="close5", book_backstop=6.0),
            "K2_book_close60": dict(B1, book_stop_mode="close60", book_backstop=6.0)}


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
    out = {"version": "v268", "variants": {k: {kk: vv for kk, vv in v.items()} for k, v in VARIANTS.items()}, "rows": {}, "trades": {}}
    runs = [("v266_B1", B1)] + list(VARIANTS.items())
    for key, extra in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **dict(KW, **extra))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
        if key == "v266_B1":
            assert abs(r["monthly_dev4"] - 6.13) < 0.002, "must reproduce v266 B1"
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
    (HERE / "v268_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
