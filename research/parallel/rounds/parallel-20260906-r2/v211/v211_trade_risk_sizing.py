"""v211: RISK-BASED SIZING for the discrete trade mode (registry v211).

Why: v210 made the book executable like a trader (one resting limit order, 5-minute rule, no resizing, SL/TP-only
management); T2 (break-even at +2 sigma_d, stop tightened on an opposite signal) was selected with dev4 4.47, worst year
0.517%/month, win rate 68%, but gate DD 25.52: each trade took the full target weight with a 4-sigma stop, so a loss cost
~10.8% of the price on a large weight. A trader sizes by risk: the loss at the stop is a fixed share of equity.

Fixed before running (everything else = v210 T2 and v205: signal |target| >= 5%, limit open -/+ max(0.10%, 0.25 sigma_4h),
valid 8h, no fill before minute 5, SL 4 sigma_d market, TP 8 sigma_d limit, break-even at +2 sigma_d, tighten to 1.5
sigma_d on an opposite signal, v205 books / governor / aligned dip sleeve / Bybit fees / adverse funding):
  R1_risk1       weight = min(1.0% * governor / (4 sigma_d), 1.0) - the stop loses 1% of equity.
  R2_risk2       weight = min(2.0% * governor / (4 sigma_d), 1.5).
  R3_risk2_cap5  R2 and a new order is skipped while the reserved risk of open (not yet break-even) positions and resting
                 orders would exceed 5% of equity.
References: ref_v205 (audited continuous), v210_T2 (full-target sizing). SELECTION = robust criterion among R1..R3 only;
the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v211/v211_trade_risk_sizing.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eu = _load("engine_user", HERE.parent / "engine_user/engine_user.py")
v204 = _load("v204", HERE.parent / "v204/v204_sleeve_book_alignment.py")

KW = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5, align=(1.5, 0.5))
BASE = dict(theta=0.05, k_off=0.25, min_off=0.001, n_valid=2, win_start=5)
T2 = dict(BASE, be_k=2.0, be_off=0.001, tighten=1.5)
VARIANTS = {
    "R1_risk1": dict(T2, risk=0.01, max_w=1.0),
    "R2_risk2": dict(T2, risk=0.02, max_w=1.5),
    "R3_risk2_cap5": dict(T2, risk=0.02, max_w=1.5, risk_cap=0.05),
}
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")


def trade_stats(events):
    """Discrete trades from the trade-mode events: result = side * (volume-weighted exit / entry - 1), before fees."""
    open_, out = {}, []
    for e in events:
        k, sym = e["kind"], e["symbol"]
        if k == "book_fill":
            open_[sym] = dict(t=e["t"], side=1 if e["side"] == "buy" else -1, px=e["price"], parts=[], be=False)
        elif sym in open_ and k == "book_partial":
            open_[sym]["parts"].append((0.5, e["price"]))
        elif sym in open_ and k == "sl_move" and e.get("why", "").startswith("break-even"):
            open_[sym]["be"] = True
        elif sym in open_ and k in ("book_stop", "book_tp"):
            o = open_.pop(sym)
            f = sum(p[0] for p in o["parts"])
            px = sum(p[0] * p[1] for p in o["parts"]) + (1 - f) * e["price"]
            ret = o["side"] * (px / o["px"] - 1)
            out.append(dict(ret=ret, reason="TP" if k == "book_tp" else ("BE stop" if o["be"] and ret > -0.002 else "SL"),
                            partial=bool(o["parts"]), hours=(e["t"] - o["t"]).total_seconds() / 3600, hidden=o["t"] >= HIDDEN))

    def summ(rows):
        if not rows:
            return {}
        r = np.array([x["ret"] for x in rows])
        w = r > 0
        mix = defaultdict(int)
        for x in rows:
            mix[x["reason"]] += 1
        return dict(trades=len(rows), win_rate=round(float(w.mean()), 3), avg_win_pct=round(100 * float(r[w].mean()), 2) if w.any() else None,
                    avg_loss_pct=round(100 * float(r[~w].mean()), 2) if (~w).any() else None, avg_pct=round(100 * float(r.mean()), 3),
                    with_partial=sum(x["partial"] for x in rows), exits=dict(mix),
                    median_hours=round(float(np.median([x["hours"] for x in rows])), 1))
    return {"dev": summ([x for x in out if not x["hidden"]]), "hidden_count_only": len([x for x in out if x["hidden"]]),
            "_hidden": summ([x for x in out if x["hidden"]])}


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v211", "base": BASE, "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("ref_v205", {}), ("v210_T2", dict(trade=T2, win_start=5))] + [(k, dict(trade=v, win_start=v["win_start"])) for k, v in VARIANTS.items()]
    for key, extra in runs:
        ev = []
        r = eu.simulate(books, opens, prep, events=ev, **KW, **extra)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key] = r
        st = r["stats"]
        ts = trade_stats(ev) if "trade" in extra else None
        if ts:
            out["trades"][key] = ts
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]],
              "fills", st["fills"], "stops", st["stops"], "tps", st["tps"],
              {k: st[k] for k in ("issued", "cancelled", "expired", "partials", "be_moves", "tightened", "risk_skipped") if k in st},
              "dev trades", ts["dev"] if ts else None, flush=True)
        if key == "ref_v205":
            assert abs(r["monthly_dev4"] - 5.824) < 0.002, "reference must reproduce v205"
    cands = {k: out["rows"][k] for k in VARIANTS}
    sel = v204.robust_select(cands)
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:  # hidden-year trade statistics are kept only for the selected row
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v211_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
