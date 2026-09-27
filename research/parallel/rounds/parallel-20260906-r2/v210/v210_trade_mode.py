"""v210: discrete TRADE MODE for the v205 books - resting limit orders, 5-minute rule, SL/TP-only management (registry v210).

Why (user, 2026-09-28): v205 re-sizes every 4h (adds, trims, flips), so a trader or a bot cannot follow it and the web
cannot say what to do. Required structure: (1) no position -> ONE limit order at a distance from the price, valid for
some hours, never filled in the first 5 minutes after the 4h close (the pipeline needs that time); (2) in a position ->
no adds, trims, rebalances or flips; only the SL/TP may be changed; exits only by SL (market) or TP (limit); market
orders only for stops.

engine_user trade mode (unit tests: tests/test_engine_trade_mode.py). Fixed before running, not tuned:
  order     : issued at a decision when flat and |target| >= 5% equity (target = the v205 book weight); side = sign;
              limit = open -/+ max(0.10%, 0.25 * sigma_4h); size = |target| fixed at issue; valid 2 bars (8h); a new
              order may fill only from minute 5 of the bar after the decision, a resting one from minute 0; cancelled
              when the signal weakens below 5% or reverses; filled on a 1m trade-through (maker 0.02%).
  position  : SL = entry -/+ 4 sigma_d, TP = entry +/- 8 sigma_d (sigma_d of the issuing bar, fixed); stop first on ties.
  T1_base          no management.
  T2_be_tighten    + stop to break-even (entry +/- 0.10%) once price reaches entry +/- 2 sigma_d (from the next minute);
                   + on an opposite signal (|target| >= 5% against the position) the stop tightens to open -/+ 1.5 sigma_d
                   of the current bar (never loosens).
  T3_partial       T2 + take 50% profit (limit) at entry +/- 4 sigma_d, then the stop goes to break-even.
Everything else = v205 (books 0.5 annual + 0.5 quarterly v151, vol target 0.25 cap 2, governor, aligned dip sleeve
unchanged (its bids live from minute 16), Bybit fees, adverse funding, 1m marks, gate DD = max(4h, 1m)).
References (not candidates, they break the user's structure): ref_v205 (audited), ref_v205_min5 (continuous mode with
the 5-minute rule: first fill minute 5 instead of 2).
SELECTION = robust criterion (AGENTS.md) among T1..T3 only; the most recent year is scored once for the selected row.
Per row: trades, win rate, average win / loss, exit mix (TP / SL / partial / break-even), orders issued / cancelled /
expired, median holding time.

  python research/parallel/rounds/parallel-20260906-r2/v210/v210_trade_mode.py
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
VARIANTS = {
    "T1_base": dict(BASE),
    "T2_be_tighten": dict(BASE, be_k=2.0, be_off=0.001, tighten=1.5),
    "T3_partial": dict(BASE, be_k=2.0, be_off=0.001, tighten=1.5, partial_k=4.0, partial_frac=0.5),
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
    out = {"version": "v210", "base": BASE, "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("ref_v205", {}), ("ref_v205_min5", dict(win_start=5))] + [(k, dict(trade=v, win_start=v["win_start"])) for k, v in VARIANTS.items()]
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
              {k: st[k] for k in ("issued", "cancelled", "expired", "partials", "be_moves", "tightened") if k in st},
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
    (HERE / "v210_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
