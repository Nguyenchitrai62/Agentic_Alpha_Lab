"""v213: faster, trader-like exits for the scaling trade mode - limit exit on signal loss, repeated scale-outs (registry v213).

Why: v212 S3 (trade mode + one limit add + one 50% limit reduce) reached dev4 4.826 / worst 0.842 / DD 20.69, but the book
earned only -6% (2021) and +8% (2022) against +22% / +50% for continuous v205: positions are held ~10 days and ride through
signal losses until SL/TP (first-four-year diagnostics). A trader closes a position whose reason disappeared.

Fixed before running (everything else = v212 S3: signal |target| >= 5%, entry limit open -/+ max(0.10%, 0.25 sigma_4h) valid
8h, minute-5 rule, SL 4 sigma_d market, TP 8 sigma_d limit, break-even +2 sigma_d, tighten 1.5 sigma_d on an opposite
signal, one add at 1.5x in profit, v205 books / governor / aligned sleeve / Bybit fees / adverse funding):
  E1_exit_on_loss   when the signal is gone (|target| < 5%) or reversed, close the WHOLE position with a limit on the
                    favourable side of the open (open +/- offset), valid 8h, minute-5 rule (instead of a 50% reduce).
  E2_multi_reduce   S3 with up to 3 successive 50% reduces (each time |target| <= 0.5x the current weight).
  E3_both           E1 and E2.
References: ref_v205, v212_S3. SELECTION = robust criterion among E1..E3; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v213/v213_trade_exits.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MAKER, TAKER = 0.0002, 0.00055


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
IN = dict(add_k=1.5, max_adds=1, add_in_profit=True)
OUT = dict(reduce_k=0.5, reduce_frac=0.5, max_reduces=1)
S3 = dict(T2, **IN, **OUT)
VARIANTS = {"E1_exit_on_loss": dict(S3, exit_on_signal_loss=True), "E2_multi_reduce": dict(S3, max_reduces=3),
            "E3_both": dict(S3, exit_on_signal_loss=True, max_reduces=3)}
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")


def trade_stats(events):
    """Discrete trades (position episodes) from trade-mode events, results after maker/taker fees (funding excluded)."""
    pos, out = {}, []
    for e in events:
        k, sym = e["kind"], e["symbol"]
        if k == "book_fill":
            q = abs(e["weight"]) / e["price"]
            pos[sym] = dict(t=e["t"], side=1 if e["side"] == "buy" else -1, qty=q, cost=q * e["price"], proceeds=0.0,
                            fees=q * e["price"] * MAKER, adds=0, reduces=0, be=False)
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e["weight"]) / e["price"]
            o["qty"] += q
            o["cost"] += q * e["price"]
            o["fees"] += q * e["price"] * MAKER
            o["adds"] += 1
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e["weight"]) / e["price"], o["qty"])
            o["qty"] -= q
            o["proceeds"] += q * e["price"]
            o["fees"] += q * e["price"] * MAKER
            o["reduces"] += 1
        elif k == "sl_move" and str(e.get("why", "")).startswith("break-even"):
            o["be"] = True
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e["price"]
            o["fees"] += o["qty"] * e["price"] * (TAKER if k == "book_stop" else MAKER)
            net = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]
            out.append(dict(net=net, tp=k == "book_tp", close=k == "book_close", be=o["be"] and abs(net) < 0.002, adds=o["adds"], reduces=o["reduces"],
                            hours=(e["t"] - o["t"]).total_seconds() / 3600, hidden=o["t"] >= HIDDEN))
            pos.pop(sym)

    def summ(rows):
        if not rows:
            return {}
        r = np.array([x["net"] for x in rows])
        w = r > 0
        return dict(trades=len(rows), win_rate=round(float(w.mean()), 3), clear_win_rate=round(float((r > 0.002).mean()), 3),
                    breakeven_exits=int(sum(x["be"] for x in rows)), tp_exits=int(sum(x["tp"] for x in rows)),
                    limit_exits=int(sum(x["close"] for x in rows)),
                    avg_win_pct=round(100 * float(r[w].mean()), 2) if w.any() else None,
                    avg_loss_pct=round(100 * float(r[~w].mean()), 2) if (~w).any() else None,
                    avg_net_pct=round(100 * float(r.mean()), 3), with_adds=int(sum(x["adds"] > 0 for x in rows)),
                    with_reduces=int(sum(x["reduces"] > 0 for x in rows)),
                    median_hours=round(float(np.median([x["hours"] for x in rows])), 1))
    return {"dev": summ([x for x in out if not x["hidden"]]), "_hidden": summ([x for x in out if x["hidden"]])}


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v213", "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("ref_v205", {}), ("v212_S3", dict(trade=S3, win_start=5))] + [(k, dict(trade=v, win_start=5)) for k, v in VARIANTS.items()]
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
              {k: st[k] for k in ("fills", "stops", "tps", "adds", "reduces", "limit_exits", "scale_orders", "be_moves", "tightened") if k in st},
              "dev trades", ts["dev"] if ts else None, flush=True)
        if key == "ref_v205":
            assert abs(r["monthly_dev4"] - 5.824) < 0.002, "reference must reproduce v205"
        if key == "v212_S3":
            assert abs(r["monthly_dev4"] - 4.826) < 0.002, "reference must reproduce v212 S3"
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
    (HERE / "v213_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
