"""v229: an hourly dip ladder inside the executable trade mode D2 (registry v229).

Why: the dip sleeve is the most efficient alpha of the executable pipeline, but its bids are anchored to the 4h open only, so crashes
that start mid-bar are caught late or not at all. engine_user has an hourly ladder (bids k sigma_1h below each hour's open, sigma_1h known
before the holding bar, live minutes 4..57 of the hour; exit TP / SL / at the next hour's open). v201 tried it on the continuous book with
one shared budget and the DD exploded (39.7); the trade mode and the aligned sizing change the risk structure, and the stop-risk budget
(0.15) caps the combined open sleeve risk.
Fixed before running (everything else = v218 D2: v216 G2 grid trader, 4h ladder 2.5/3/3.5/4 sigma_4h, TP 1 sigma, SL 5 sigma, budget
0.15, rung x1.75, aligned x1.5 / x0.5, minute-5 rule, Bybit fees, adverse funding):
  L1_hourly          hourly ladder on (same rungs, sizes and shared budget).
  L2_hourly_small    hourly ladder on, rung size x1.5 instead of x1.75 (offsets the extra crowding).
  L3_hourly_aligned  hourly ladder on, alignment x1.5 on coins the books are long and x0.0 elsewhere (dip bids only with the trend).
Reference: v218_D2. SELECTION = robust criterion among L1..L3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v229/v229_trade_hourly_ladder.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
VARIANTS = {"L1_hourly": dict(hourly=True), "L2_hourly_small": dict(hourly=True, size_mult=1.5),
            "L3_hourly_aligned": dict(hourly=True, align=(1.5, 0.0))}


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v229", "variants": {k: str(v) for k, v in VARIANTS.items()}, "rows": {}, "trades": {}}
    for key, extra in [("v218_D2", {})] + list(VARIANTS.items()):
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **dict(v221.KW, **extra))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        st = r["stats"]
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", st["rungs"], "rung sl/tp", st["rung_stops"], st["rung_tps"], flush=True)
        if key == "v218_D2":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002
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
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v229_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
