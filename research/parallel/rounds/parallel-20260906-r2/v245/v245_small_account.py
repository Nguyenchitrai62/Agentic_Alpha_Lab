"""v245: the O1 pipeline for a SMALL live account - trade only the coins whose orders pass the exchange minimums (registry v245).

Why: the user will test a real bot with about 100 USDT. Bybit USDT-perp lot rules (public instruments-info, 2026-09-29): minimum order
BTC 0.001 (~84 USDT), ETH 0.01 (~27 USDT), SOL 0.1 (~12 USDT), BNB 0.01 (~8 USDT), XRP 0.1 (5 USDT notional). With O1 sizes (book
~10-20% of equity, dip rungs ~6.6%) a 100 USDT account can place 0% of the BTC orders, ~5% of ETH, ~35-40% of SOL, 67-93% of BNB and
82-100% of XRP (most recent year of the O1 history): replaying O1 as is would not describe what such an account does.
Fixed before running: v240 O1 books (A: TV + order-level flow; B: options + TV), v218 D2 settings (G2 grid trader, sleeve budget 0.15,
rung x1.75, minute-5 rule, limits, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding). Coins outside the
traded set get zero books and no dip bids (sleeve_filter 0); weights of the traded coins are unchanged unless stated.
  S1_no_btc_eth        trade SOL, BNB, XRP
  S2_xrp_bnb           trade BNB, XRP (the coins a 100 USDT account can place almost always)
  S3_no_btc_eth_x1_5   S1 with the traded coins' books x1.5 (uses the capital BTC / ETH would have taken)
Reference: v240_O1 (all five coins, must reproduce dev4 5.690). SELECTION = robust criterion among S1..S3 (a deployment question for
small accounts - the reference is not a candidate); the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v245/v245_small_account.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
VARIANTS = {"S1_no_btc_eth": (("SOLUSDT", "BNBUSDT", "XRPUSDT"), 1.0), "S2_xrp_bnb": (("BNBUSDT", "XRPUSDT"), 1.0),
            "S3_no_btc_eth_x1_5": (("SOLUSDT", "BNBUSDT", "XRPUSDT"), 1.5)}


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
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v245", "variants": {k: [list(v[0]), v[1]] for k, v in VARIANTS.items()}, "rows": {}, "trades": {}}
    runs = [("v240_O1", books, None)]
    for key, (keep, mult) in VARIANTS.items():
        bk = books.copy()
        for s in cols:
            bk[s] = bk[s] * mult if s in keep else 0.0
        keep_ix = {cols.index(s) for s in keep}
        runs.append((key, bk, (lambda i, a, r, keep_ix=keep_ix: 1.0 if a in keep_ix else 0.0)))
    for key, bk, flt in runs:
        ev = []
        kw = dict(sleeve_filter=flt) if flt is not None else {}
        r = eu.simulate(bk, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **kw, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v240_O1":
            assert abs(r["monthly_dev4"] - 5.690) < 0.002
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
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v245_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
