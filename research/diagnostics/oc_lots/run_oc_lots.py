"""oc_lots: small-account Bybit lot feasibility of R2B1D17BF phase s=0.

Reads ONLY research/tournament/oc_ddanat17/events_s0.parquet and
rungs_s0.parquet (one causal engine phase; no 1m, no refit). For account sizes
A in {1000,2000,5000,10000,20000} with phase equity E=A/4, checks every book
order (order_issue |weight|>0) and every dip rung (rungs_s0 row) against live
Bybit lot rules (fallback snapshot if offline).

Usage: .venv/Scripts/python.exe research/diagnostics/oc_lots/run_oc_lots.py
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
EV = ROOT / "research/tournament/oc_ddanat17/events_s0.parquet"
RU = ROOT / "research/tournament/oc_ddanat17/rungs_s0.parquet"
OUT = HERE / "results.json"

ACCOUNTS = (1000.0, 2000.0, 5000.0, 10000.0, 20000.0)
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]

FALLBACK = {
    "BTCUSDT": {"minQty": 0.001, "qtyStep": 0.001, "minNotional": 5.0},
    "ETHUSDT": {"minQty": 0.01, "qtyStep": 0.01, "minNotional": 5.0},
    "SOLUSDT": {"minQty": 0.1, "qtyStep": 0.1, "minNotional": 5.0},
    "BNBUSDT": {"minQty": 0.01, "qtyStep": 0.01, "minNotional": 5.0},
    "XRPUSDT": {"minQty": 0.1, "qtyStep": 0.1, "minNotional": 5.0},
}


def fetch_lots():
    rules, live = {}, True
    try:
        for s in SYMS:
            url = ("https://api.bybit.com/v5/market/instruments-info"
                   f"?category=linear&symbol={s}&limit=1")
            with urllib.request.urlopen(url, timeout=15) as r:
                d = json.loads(r.read().decode())
            f = d["result"]["list"][0]["lotSizeFilter"]
            rules[s] = {"minQty": float(f["minOrderQty"]),
                        "qtyStep": float(f["qtyStep"]),
                        "minNotional": float(f.get("minNotionalValue", 5.0))}
    except Exception:
        rules, live = {k: dict(v) for k, v in FALLBACK.items()}, False
    return rules, ("live" if live else "fallback-snapshot")


def placeable(qty_raw, price, rule):
    step, mqd, mnot = rule["qtyStep"], rule["minQty"], rule["minNotional"]
    qf = np.floor(qty_raw / step + 1e-9) * step
    return bool(qf + 1e-12 >= mqd and qf * price + 1e-9 >= mnot - 1e-6)


def main():
    rules, source = fetch_lots()
    ev = pd.read_parquet(EV)
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    ru = pd.read_parquet(RU)
    ru["fill_t"] = pd.to_datetime(ru["fill_t"], utc=True)

    # --- book orders (primary): order_issue |w|>0 ---
    oi = ev[(ev["kind"] == "order_issue") & (ev["weight"].abs() > 0)].copy()
    oi = oi.sort_values("t").reset_index(drop=True)
    oi["abs_w"] = oi["weight"].abs()
    oi["notional_frac"] = oi["abs_w"]  # fraction of phase equity at issue

    # sensitivity: book_fill events
    bf = ev[ev["kind"] == "book_fill"].copy().sort_values("t").reset_index(drop=True)

    # rungs: weight/price from rungs_s0
    ru = ru.sort_values("fill_t").reset_index(drop=True)

    # --- per-account placeability ---
    book_rows = oi[["t", "symbol", "price", "abs_w"]].copy()
    rung_rows = ru[["fill_t", "symbol", "fill_price", "weight", "ret", "loss"]].copy()
    per_acct = {}
    for A in ACCOUNTS:
        E = A / 4.0
        bq = (book_rows["abs_w"] * E / book_rows["price"]).to_numpy()
        bp = book_rows["price"].to_numpy()
        bs = book_rows["symbol"].to_numpy()
        bok = np.array([placeable(q, p, rules[s]) for q, p, s in zip(bq, bp, bs)])
        rq = (rung_rows["weight"].abs() * E / rung_rows["fill_price"]).to_numpy()
        rp = rung_rows["fill_price"].to_numpy()
        rs = rung_rows["symbol"].to_numpy()
        rok = np.array([placeable(q, p, rules[s]) for q, p, s in zip(rq, rp, rs)])

        # count shares per coin
        by_coin = {}
        for s in SYMS:
            mb = bs == s
            mr = rs == s
            by_coin[s] = {
                "book_n": int(mb.sum()), "book_ok": int(bok[mb].sum()),
                "book_share": round(float(bok[mb].mean()), 4) if mb.sum() else None,
                "rung_n": int(mr.sum()), "rung_ok": int(rok[mr].sum()),
                "rung_share": round(float(rok[mr].mean()), 4) if mr.sum() else None,
            }
        # dip P&L shares from loss column + notional-share cross-check
        loss = rung_rows["loss"].to_numpy(float)
        tot_net, tot_gross = float(loss.sum()), float(np.abs(loss).sum())
        pnl_p = float(loss[rok].sum())
        pnl_g = float(np.abs(loss[rok]).sum())
        rn = rung_rows["weight"].abs().to_numpy(float)
        dip_notional_share = round(float(rn[rok].sum() / rn.sum()), 4)
        bw = book_rows["abs_w"].to_numpy(float)
        book_notional_share = round(float(bw[bok].sum() / bw.sum()), 4)
        # book FIFO P&L (computed once below; split here by mapped placeability)
        per_acct[str(A)] = {
            "phase_equity": E,
            "book_orders": int(len(book_rows)), "book_placeable": int(bok.sum()),
            "book_share": round(float(bok.mean()), 4),
            "rung_orders": int(len(rung_rows)), "rung_placeable": int(rok.sum()),
            "rung_share": round(float(rok.mean()), 4),
            "by_coin": by_coin,
            "dip_pnl_net_total": round(tot_net, 6), "dip_pnl_gross_total": round(tot_gross, 6),
            "dip_pnl_net_placeable": round(pnl_p, 6), "dip_pnl_gross_placeable": round(pnl_g, 6),
            "dip_net_share": round(pnl_p / tot_net, 4) if tot_net != 0 else None,
            "dip_gross_share": round(pnl_g / tot_gross, 4) if tot_gross else None,
            "dip_notional_share": dip_notional_share,
            "book_notional_share": book_notional_share,
            "_bok": bok, "_rok": rok,
        }

    # --- book FIFO realized P&L per entry lot (account-independent matching) ---
    # entry lots: book_fill (mapped to order_issue idx) + book_add (self)
    evs = ev.sort_values("t").reset_index(drop=True)
    lots = []  # dicts: sym, w_signed, p0, rem, pnl
    inv: dict[str, deque] = {s: deque() for s in SYMS}
    lot_pnl = []  # realized pnl per lot (fraction units), parallel to `lots`
    lot_info = []  # (sym, abs_w, price, kind, t)
    unmatched_exit = 0.0
    for pos, r in evs.iterrows():
        k = r["kind"]
        if k in ("book_fill", "book_add"):
            lot = {"sym": r["symbol"], "w": float(r["weight"]), "p0": float(r["price"]),
                   "rem": abs(float(r["weight"])), "pnl": 0.0}
            lots.append(lot)
            inv[r["symbol"]].append(lot)
            lot_pnl.append(lot)
            lot_info.append({"sym": r["symbol"], "abs_w": abs(float(r["weight"])),
                             "price": float(r["price"]), "kind": k, "t": str(r["t"])})
        elif k in ("book_close", "book_reduce", "book_stop", "book_tp"):
            need = abs(float(r["weight"]))
            p1 = float(r["price"])
            se = np.sign(float(r["weight"]))
            unmatched = need
            dq = inv.get(r["symbol"], deque())
            # consume oldest lots with opposite sign first
            for lot in list(dq):
                if unmatched <= 1e-12:
                    break
                if np.sign(lot["w"]) == se or lot["rem"] <= 1e-12:
                    continue
                m = min(lot["rem"], unmatched)
                side = np.sign(lot["w"])
                lot["pnl"] += m * side * (p1 - lot["p0"]) / lot["p0"]
                lot["rem"] -= m
                unmatched -= m
            # remainder (equity-drift over-close) recorded, not forced
            unmatched_exit += float(unmatched)
    unmatched_entry = float(sum(l["rem"] for l in lots))

    lot_pnl_arr = np.array([l["pnl"] for l in lots])
    # placeability of each lot per account: fills inherit mapped issue, adds self
    oi_by_sym: dict[str, list] = {}
    for i, r in oi.iterrows():
        oi_by_sym.setdefault(r["symbol"], []).append(i)
    # walk lots in time order to assign each fill its order_issue (adds map to self)
    lot_assign = []
    used2 = np.zeros(len(oi), bool)
    for _, r in evs.iterrows():
        if r["kind"] == "book_fill":
            found = None
            for i in oi_by_sym.get(r["symbol"], []):
                o = oi.loc[i]
                if (not used2[i] and np.sign(o["weight"]) == np.sign(float(r["weight"]))
                        and abs(abs(o["weight"]) - abs(float(r["weight"]))) < 1e-9
                        and abs(float(o["price"]) - float(r["price"])) < 1e-6
                        and o["t"] <= r["t"]):
                    found = i
                    used2[i] = True
                    break
            lot_assign.append(("issue", found))
        elif r["kind"] == "book_add":
            lot_assign.append(("add", (float(r["price"]), abs(float(r["weight"])), r["symbol"])))
    assert len(lot_assign) == len(lots)
    n_unmapped_fills = sum(1 for a in lot_assign if a[0] == "issue" and a[1] is None)

    for A in ACCOUNTS:
        E = A / 4.0
        ok = np.zeros(len(lots), bool)
        for li, a in enumerate(lot_assign):
            if a[0] == "issue" and a[1] is not None:
                o = oi.loc[a[1]]
                q = abs(float(o["weight"])) * E / float(o["price"])
                ok[li] = placeable(q, float(o["price"]), rules[o["symbol"]])
            elif a[0] == "add":
                p, w, s = a[1]
                ok[li] = placeable(w * E / p, p, rules[s])
            else:
                ok[li] = False  # unmapped fill: conservatively unplaceable
        tot_net = float(lot_pnl_arr.sum())
        tot_gross = float(np.abs(lot_pnl_arr).sum())
        p_net = float(lot_pnl_arr[ok].sum())
        p_gross = float(np.abs(lot_pnl_arr[ok]).sum())
        d = per_acct[str(A)]
        d["book_pnl_net_total"] = round(tot_net, 6)
        d["book_pnl_gross_total"] = round(tot_gross, 6)
        d["book_pnl_net_placeable"] = round(p_net, 6)
        d["book_pnl_gross_placeable"] = round(p_gross, 6)
        d["book_net_share"] = round(p_net / tot_net, 4) if tot_net != 0 else None
        d["book_gross_share"] = round(p_gross / tot_gross, 4) if tot_gross else None
        # sensitivity: book_fill-only count share
        bfq = (bf["weight"].abs() * E / bf["price"]).to_numpy()
        bok_f = np.array([placeable(q, p, rules[s]) for q, p, s in zip(bfq, bf["price"].to_numpy(), bf["symbol"].to_numpy())])
        d["book_fill_orders"] = int(len(bf))
        d["book_fill_placeable"] = int(bok_f.sum())
        d["book_fill_share"] = round(float(bok_f.mean()), 4)
        del d["_bok"], d["_rok"]

    # --- per-anchor-year descriptive count shares (fill/issue year) ---
    years = {}
    for yi, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.DateOffset(years=1)
        mb = (oi["t"] >= a0) & (oi["t"] < a1)
        mr = (ru["fill_t"] >= a0) & (ru["fill_t"] < a1)
        yd = {"book_n": int(mb.sum()), "rung_n": int(mr.sum())}
        for A in ACCOUNTS:
            E = A / 4.0
            if mb.sum():
                q = (oi.loc[mb, "abs_w"] * E / oi.loc[mb, "price"]).to_numpy()
                ok = [placeable(x, p, rules[s]) for x, p, s in
                      zip(q, oi.loc[mb, "price"].to_numpy(), oi.loc[mb, "symbol"].to_numpy())]
                yd[f"book_share_{int(A)}"] = round(float(np.mean(ok)), 4)
            else:
                yd[f"book_share_{int(A)}"] = None
            if mr.sum():
                sub = ru.loc[mr]
                q = (sub["weight"].abs() * E / sub["fill_price"]).to_numpy()
                ok = [placeable(x, p, rules[s]) for x, p, s in
                      zip(q, sub["fill_price"].to_numpy(), sub["symbol"].to_numpy())]
                yd[f"rung_share_{int(A)}"] = round(float(np.mean(ok)), 4)
            else:
                yd[f"rung_share_{int(A)}"] = None
        years[f"{a0.date()}..{(a1 - pd.Timedelta(seconds=1)).date()}"] = yd

    res = {
        "variant": "R2B1D17BF", "phase": 0,
        "inputs": {"events": str(EV.relative_to(ROOT)), "rungs": str(RU.relative_to(ROOT)),
                   "n_events": int(len(ev)), "n_book_orders": int(len(oi)),
                   "n_book_fills": int(len(bf)), "n_rungs": int(len(ru))},
        "lot_rules": rules, "lot_source": source,
        "lot_fetched_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "accounts": list(ACCOUNTS), "phase_equity_note": "E = A/4 (one sub-book per clock)",
        "placeability_rule": "qf=floor(q/step)*step placeable iff qf>=minQty and qf*price>=5",
        "per_account": {k: v for k, v in per_acct.items()},
        "per_anchor_year": years,
        "fifo": {"n_entry_lots": int(len(lots)), "n_unmapped_fills": int(n_unmapped_fills),
                 "unmatched_entry_frac": round(unmatched_entry, 6),
                 "unmatched_exit_frac": round(unmatched_exit, 6),
                 "note": "weights are fractions of then-bar equity; FIFO match is approximate across compounding"},
    }
    OUT.write_text(json.dumps(res, indent=1))
    print("wrote", OUT)
    for A in ACCOUNTS:
        d = per_acct[str(A)]
        print(int(A), "book", d["book_placeable"], "/", d["book_orders"], d["book_share"],
              "rung", d["rung_placeable"], "/", d["rung_orders"], d["rung_share"],
              "dipgross", d["dip_gross_share"], "bookgross", d["book_gross_share"], flush=True)


if __name__ == "__main__":
    main()
