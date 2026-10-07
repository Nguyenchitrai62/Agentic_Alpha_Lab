"""Independent blind replication for audit_capacity.

Implements ONLY the pre-stated rule from the header of
research/tournament/oc_capacity/capacity.py (lines 1-48 as read before the
blind comparison), plus the input list named there:
  research/tournament/oc_kpi_g2/events_s{0..3}.parquet (stored G2 trades)
  research/tournament/oc_kpi_g2/barsum_s{0..3}.parquet (phase equity index)
  data/raw/bookdepth_20261004/{SYM}_bookdepth_1m.parquet (depth archive)

Does NOT import capacity.py and has not seen oc_capacity/REPORT.md or
results.json at the time of writing.

Rule restated (from header):
  D = relevant-side notional within 1% of mid at order time (ask_n1 for buys,
      bid_n1 for sells), last snapshot with ts strictly before order time,
      lag <= 300 s else unmatched. D02 = D/5 proxy for "within 0.2%".
  r = notional / D (exact 1% band). r02 = notional / D02 = 5*r.
  notional(E) = |weight| * eq_idx(t) * E/4, eq_idx from barsum step function.
  Bad prints: snapshot whose relevant side < that side's 0.5th percentile over
      the archive -> treated as missing (n_badprint, excluded from shares).
  Haircut ONLY for orders with r > 5%:
    maker entries (rung_fill/book_fill/book_add): p = 0.05/r,
      missed = (1-p) * max(profit,0); rung profit = ret*|weight|*eq_idx(fill);
      book episode profit allocated to fills pro-rata by |weight| (episode
      profit computed here as gross price-difference FIFO profit, no base fees;
      documented assumption A1 below).
    stop exits (book_stop/rung_sl): extra = 0.5*p90*notional($).
    TP/timeout/close/reduce/partial exits: no haircut.
  H(E) indexed = (sum over 4 shifts)/4; drag_pp = H(E)/M*100;
      M = months in 2023-01-01..2026-09-23; adjusted ~= 5.41 - drag.

Assumptions documented (independent choices, flagged for comparison):
  A1: book episode gross profit (no base fees/funding) via FIFO lots in indexed
      units: lot coins = |w|*eq/P_entry; exits close FIFO at exit price with
      direction sign; full flatten on book_stop/book_tp/book_close; partial
      (book_reduce/book_partial) closes min(open, |w_exit|*eq_exit/P_exit).
      Episode total allocated to its fills pro-rata by raw |weight|.
  A2: M = (2026-09-24 - 2023-01-01).days / 30.4375 (365.25/12).
  A3: shares denominator = matched orders with good depth (excludes badprint +
      unmatched), per symbol, over ALL 11 liquidity order kinds in window.
  A4: eq_idx(t) = last barsum equity with barsum_t <= order t (searchsorted
      right-1), per shift; barsum indexed to 1.0 at start.
  A5: side mapping: buy -> ask_n1, sell -> bid_n1 (as stated).
  A6: rung FIFO per (shift, symbol); unmatched exits/fills ignored (logged).
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
G2 = ROOT / "research/tournament/oc_kpi_g2"
DEPTH = ROOT / "data/raw/bookdepth_20261004"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
EQUITIES = [10_000, 50_000, 100_000]
T0 = pd.Timestamp("2023-01-01", tz="UTC")
T1 = pd.Timestamp("2026-09-24", tz="UTC")
MAX_LAG_S = 300
BASE_MONTHLY = 5.41
HALF_P90 = {
    "BTCUSDT": 0.5 * 0.0117 / 1e4, "ETHUSDT": 0.5 * 0.0371 / 1e4,
    "SOLUSDT": 0.5 * 0.8337 / 1e4, "BNBUSDT": 0.5 * 1.2810 / 1e4,
    "XRPUSDT": 0.5 * 0.6679 / 1e4}
ENTRY_KINDS = ("rung_fill", "book_fill", "book_add")
STOP_KINDS = ("book_stop", "rung_sl")
ORDER_KINDS = ENTRY_KINDS + ("book_reduce", "book_partial", "rung_sl", "rung_tp",
                             "rung_timeout", "book_stop", "book_tp", "book_close")
M_DAYS = (T1 - T0).days  # 1362
M_MONTHS = M_DAYS / 30.4375


def load_barsum(shift: int):
    bs = pd.read_parquet(G2 / f"barsum_s{shift}.parquet", columns=["t", "equity"])
    t = pd.to_datetime(bs["t"], utc=True)
    tns = t.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    o = np.argsort(tns)
    return tns[o], bs["equity"].to_numpy(float)[o]


def load_orders():
    frames = []
    for s in range(4):
        ev = pd.read_parquet(G2 / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        teq, eeq = load_barsum(s)
        ev = ev.sort_values("t").reset_index(drop=True)
        tns = ev["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        ev["_eq"] = eeq[np.clip(np.searchsorted(teq, tns, side="right") - 1, 0, len(eeq) - 1)]
        ev["_shift"] = s
        ev["_idx"] = np.arange(len(ev))
        frames.append(ev)
    return frames


def rung_profits(frames):
    """(shift, event_idx) -> indexed profit for rung_fill rows."""
    out = {}
    stats = {"fills": 0, "exits": 0, "orphan_exit": 0, "open_at_end": 0}
    for s, ev in enumerate(frames):
        pend: dict[str, deque] = {}
        for i, r in ev.iterrows():
            if r["kind"] == "rung_fill":
                stats["fills"] += 1
                pend.setdefault(r["symbol"], deque()).append((i, abs(float(r["weight"])), float(r["_eq"])))
            elif r["kind"] in ("rung_sl", "rung_tp", "rung_timeout"):
                stats["exits"] += 1
                q = pend.get(r["symbol"])
                if q:
                    f, w, eq = q.popleft()
                    out[(s, f)] = float(r["ret"]) * w * eq
                else:
                    stats["orphan_exit"] += 1
        for q in pend.values():
            stats["open_at_end"] += len(q)
    return out, stats


def book_profits(frames):
    """Episode FIFO gross profit, allocated to fills pro-rata by |weight|.

    Returns dict (shift, event_idx) -> allocated indexed profit for
    book_fill/book_add rows, plus diagnostics.
    """
    out = {}
    diag = {"episodes": 0, "fills": 0, "overlap_reopen": 0, "add_no_pos": 0,
            "reduce_no_pos": 0, "exit_no_pos": 0}
    for s, ev in enumerate(frames):
        for sym in SYMS:
            sub = ev[ev["symbol"] == sym].sort_values("t")
            lots: list[dict] = []  # each {coins: positive indexed coins, price, idx, w}
            fills: list[tuple] = []  # (idx, |w|)
            qty = 0.0  # signed coins (indexed)
            direction = 0
            ep_pnl = 0.0

            def close_episode():
                nonlocal lots, fills, qty, direction, ep_pnl
                if fills:
                    tot_w = sum(w for _, w in fills)
                    for fi, w in fills:
                        out[(s, fi)] = ep_pnl * (w / tot_w) if tot_w else 0.0
                    diag["episodes"] += 1
                lots, fills, qty, direction, ep_pnl = [], [], 0.0, 0, 0.0

            def fifo_close(price: float, close_coins: float):
                """Realize close_coins (positive) FIFO at price; mutates lots/qty."""
                nonlocal ep_pnl, qty
                need = close_coins
                while need > 1e-18 and lots:
                    lot = lots[0]
                    take = min(float(lot["coins"]), need)
                    ep_pnl += direction * take * (price - float(lot["price"]))
                    lot["coins"] = float(lot["coins"]) - take
                    need -= take
                    if float(lot["coins"]) < 1e-15:
                        lots.pop(0)
                qty -= direction * close_coins

            for i, r in sub.iterrows():
                k = r["kind"]
                if k not in ORDER_KINDS:
                    continue
                side = r["side"]
                d = 1 if side == "buy" else -1
                P = float(r["price"])
                w = abs(float(r["weight"]))
                eq = float(r["_eq"])
                if k in ("book_fill",):
                    diag["fills"] += 1
                    if qty == 0:
                        direction = d
                        coins = w * eq / P
                        lots.append({"coins": coins, "price": P, "idx": i, "w": w})
                        fills.append((i, w))
                        qty = d * coins
                    elif d == direction:
                        coins = w * eq / P
                        lots.append({"coins": coins, "price": P, "idx": i, "w": w})
                        fills.append((i, w))
                        qty += d * coins
                    else:
                        # opposite fill while open: flatten at this price, start new
                        diag["overlap_reopen"] += 1
                        # realize all lots at P
                        for lot in lots:
                            closed = lot["coins"]
                            ep_pnl += direction * closed * (P - lot["price"])
                        close_episode()
                        direction = d
                        coins = w * eq / P
                        lots.append({"coins": coins, "price": P, "idx": i, "w": w})
                        fills.append((i, w))
                        qty = d * coins
                elif k == "book_add":
                    if qty == 0:
                        diag["add_no_pos"] += 1
                        direction = d
                        coins = w * eq / P
                        lots.append({"coins": coins, "price": P, "idx": i, "w": w})
                        fills.append((i, w))
                        qty = d * coins
                    else:
                        coins = w * eq / P
                        lots.append({"coins": coins, "price": P, "idx": i, "w": w})
                        fills.append((i, w))
                        qty += direction * coins
                elif k in ("book_reduce", "book_partial"):
                    if qty == 0:
                        diag["reduce_no_pos"] += 1
                        continue
                    want = w * eq / P
                    fifo_close(P, min(want, abs(qty)))
                    if abs(qty) < 1e-12 and not lots:
                        close_episode()
                elif k in ("book_stop", "book_tp", "book_close"):
                    if qty == 0:
                        diag["exit_no_pos"] += 1
                        continue
                    fifo_close(P, abs(qty))
                    lots, qty, direction = [], 0.0, 0
                    close_episode()
                # rung kinds ignored here
            # end of symbol: leave open episode unallocated (unrealized)
    return out, diag


def main():
    frames = load_orders()
    rung_prof, rung_stats = rung_profits(frames)
    book_prof, book_diag = book_profits(frames)

    # collect window orders
    orders = []
    for s, ev in enumerate(frames):
        m = ev["kind"].isin(ORDER_KINDS) & (ev["t"] >= T0) & (ev["t"] < T1) & (ev["symbol"].isin(SYMS))
        sub = ev[m]
        for i, r in sub.iterrows():
            key = (s, i)
            if r["kind"] in ENTRY_KINDS and r["kind"].startswith("rung"):
                profit = float(rung_prof.get(key, 0.0))
            elif r["kind"] in ("book_fill", "book_add"):
                profit = float(book_prof.get(key, 0.0))
            else:
                profit = 0.0
            orders.append({
                "shift": s, "idx": int(i), "t": r["t"], "symbol": r["symbol"],
                "kind": r["kind"], "side": r["side"], "price": float(r["price"]),
                "weight": float(r["weight"]), "eq": float(r["_eq"]),
                "base": abs(float(r["weight"])) * float(r["_eq"]) / 4.0,  # notional per 1 unit E
                "profit": profit,
            })
    odf = pd.DataFrame(orders).sort_values("t").reset_index(drop=True)

    per_symbol = {}
    all_rows = []
    for sym in SYMS:
        dp = pd.read_parquet(DEPTH / f"{sym}_bookdepth_1m.parquet",
                             columns=["minute", "ts", "bid_n1", "ask_n1"])
        dp["ts"] = pd.to_datetime(dp["ts"], utc=True)
        dp = dp.sort_values("ts").reset_index(drop=True)
        for side_col in ("bid_n1", "ask_n1"):
            pass
        floor_bid = float(dp["bid_n1"].quantile(0.005))
        floor_ask = float(dp["ask_n1"].quantile(0.005))
        ts = dp["ts"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        bid = dp["bid_n1"].to_numpy(float)
        ask = dp["ask_n1"].to_numpy(float)

        so = odf[odf["symbol"] == sym].sort_values("t").reset_index(drop=True)
        tns = pd.to_datetime(so["t"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        pos = np.searchsorted(ts, tns, side="left") - 1  # strictly before
        valid = pos >= 0
        lag = np.full(len(so), np.inf)
        D = np.full(len(so), np.nan)
        is_buy = (so["side"] == "buy").to_numpy()
        for j in np.where(valid)[0]:
            p = pos[j]
            lag_s = (tns[j] - ts[p]) / 1e9
            lag[j] = lag_s
            if lag_s <= MAX_LAG_S:
                dd = ask[p] if is_buy[j] else bid[p]
                D[j] = dd
        floor = np.where(is_buy, floor_ask, floor_bid)
        badprint = np.isfinite(D) & (D < floor)
        matched = np.isfinite(D) & (~badprint)
        so = so.copy()
        so["D"] = D
        so["lag_s"] = lag
        so["badprint"] = badprint
        so["matched"] = matched
        all_rows.append(so)
        per_symbol[sym] = {"floor_bid": floor_bid, "floor_ask": floor_ask,
                           "n_orders": int(len(so)), "n_matched": int(matched.sum()),
                           "n_badprint": int(badprint.sum()),
                           "n_unmatched": int((~np.isfinite(D)).sum())}
    adf = pd.concat(all_rows, ignore_index=True) if all_rows else odf.copy()

    result = {"meta": {
        "equities": EQUITIES, "T0": "2023-01-01", "T1": "2026-09-24(excl)",
        "M_days": M_DAYS, "M_months": M_MONTHS, "base_monthly": BASE_MONTHLY,
        "max_lag_s": MAX_LAG_S, "rule": "r=notional/D(1pct); D02=D/5; haircut iff r>5pct",
        "A1_book_profit": "gross FIFO, no base fees, pro-rata by |weight|",
        "rung_stats": rung_stats, "book_diag": book_diag,
    }, "symbols": {}, "drag": {}, "totals": {}}
    for sym, d in per_symbol.items():
        result["symbols"][sym] = d

    for E in EQUITIES:
        sE = str(E)
        H = 0.0
        H_entry = 0.0
        H_stop = 0.0
        n_hit = 0
        sym_out = {}
        for sym in SYMS:
            so = adf[(adf["symbol"] == sym) & (adf["matched"])].copy()
            notion = so["base"].to_numpy(float) * E
            DD = so["D"].to_numpy(float)
            r = notion / DD
            r02 = r * 5.0
            n = len(so)
            shares = {}
            for thr, tag in ((0.01, "1pct"), (0.05, "5pct"), (0.20, "20pct")):
                shares[f"share_r1_gt_{tag}"] = float((r > thr).mean()) if n else 0.0
                shares[f"share_r02_gt_{tag}"] = float((r02 > thr).mean()) if n else 0.0
            sym_out[sym] = {"n": n, **shares}
            # haircut
            hit = r > 0.05
            kinds = so["kind"].to_numpy()
            profits = so["profit"].to_numpy(float)
            bases = so["base"].to_numpy(float)
            for j in np.where(hit)[0]:
                k = kinds[j]
                if k in ENTRY_KINDS:
                    n_hit += 1
                    p = 0.05 / r[j]
                    miss = (1 - p) * max(profits[j], 0.0)
                    H_entry += miss
                    H += miss
                elif k in STOP_KINDS:
                    n_hit += 1
                    c_dollar = HALF_P90[sym] * bases[j] * E
                    c_idx = c_dollar / E  # indexed units
                    H_stop += c_idx
                    H += c_idx
        H_mix = H / 4.0
        drag_pp = H_mix / M_MONTHS * 100.0
        result["drag"][sE] = {
            "H_indexed_mix": H_mix, "H_raw_sum4": H,
            "H_entry": H_entry / 4.0, "H_stop": H_stop / 4.0,
            "drag_pp_per_month": drag_pp,
            "adjusted_monthly": BASE_MONTHLY - drag_pp,
            "material_ge_0_5pp": bool(drag_pp >= 0.5),
            "n_haircut_orders": int(n_hit),
        }
        result["totals"][sE] = sym_out

    out = HERE / "replication.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"wrote {out} M_months={M_MONTHS:.4f}")
    for E in EQUITIES:
        d = result["drag"][str(E)]
        print(E, f"H_mix={d['H_indexed_mix']:.6f} drag={d['drag_pp_per_month']:.4f}pp adj={d['adjusted_monthly']:.4f} nhit={d['n_haircut_orders']}")


if __name__ == "__main__":
    main()
