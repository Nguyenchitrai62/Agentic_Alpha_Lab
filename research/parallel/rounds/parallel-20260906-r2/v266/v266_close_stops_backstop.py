"""v266: EXECUTABLE candle-close stops for the dip ladder - 5m-close stop run by the bot PLUS an exchange-native disaster stop.

Why: v265 S2 (dip-rung stops triggered on a 5m-block close instead of a touch) lifted dev4 5.777 -> 6.178, the worst dev year 2.854 ->
2.903 and lowered the gate DD 19.65 -> 19.29 (stops 196 -> 100: flush wicks no longer stop the rungs out). Bybit has no native
candle-close stop, so a bot must watch the 5m closes; if the bot fails, the position must still be protected. The executable form is the
5m-close stop PLUS a native touch stop further away (a trader's disaster stop). The risk budget can count either the 5-sigma close stop
or the 8-sigma disaster stop as the stop distance.
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings otherwise). Engine: sleeve_stop_mode "close5" (trigger on a 5m-block
close at or below lv * (1 - 5 sigma), fill at the next minute's open), sleeve_backstop 8 (native touch stop at lv * (1 - 8 sigma), fill at
min(level, open), wins over a same-minute close trigger or TP).
  B1_close5_back8          risk budget counts 5 sigma (as v265)
  B2_close5_back8_bud8     risk budget counts the 8-sigma disaster stop (conservative: fewer rungs in a cascade)
Reference: touch stops (must reproduce v247 B18, dev4 5.777); v265 S2 (close5 without a backstop) reported as a labelled comparison.
SELECTION = robust criterion among B1, B2; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v266/v266_close_stops_backstop.py
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
VARIANTS = {"B1_close5_back8": dict(sleeve_stop_mode="close5", sleeve_backstop=8.0),
            "B2_close5_back8_bud8": dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, sleeve_budget_sl=8.0)}


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
    out = {"version": "v266", "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("v247_B18", {}), ("v265_S2_close5_nobackstop", dict(sleeve_stop_mode="close5"))] + list(VARIANTS.items())
    for key, extra in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **dict(KW, **extra))
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
    (HERE / "v266_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
