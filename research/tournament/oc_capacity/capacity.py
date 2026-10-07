"""oc_capacity: G2 per-order notional vs Binance order-book depth (capacity study).

RULE (stated up front, before running):
  Depth D = relevant-side notional within 1% of mid at order time (ask_n1 for
  buys, bid_n1 for sells) from the last bookDepth snapshot with ts strictly
  before the order time (lag <= 5 min, else unmatched). The archive
  (data/raw/bookdepth_20261004, from scripts/fetch_bookdepth.py) stores ONLY
  1%/2%/5% cumulative bands, so "within 0.2%" is proxied as D02 = D/5 (uniform
  density assumption = conservative lower bound; the true touch-concentrated
  book is deeper, so D02 impact shares are upper bounds). Primary metric is
  r = notional / D (exact 1% band, relevant side).
  Per-order notional for total account equity E:
    notional(E) = |weight| * eq_idx(t) * E/4
  (weight = stored fraction of phase sub-account equity; eq_idx = phase equity
  indexed to 1.0 from barsum; /4 because the 4 phase sub-accounts split E).
  Conservative return haircut, applied ONLY to orders with r > 5%:
    maker entries (rung_fill/book_fill/book_add): fill prob p = 0.05/r, the
      unfilled fraction (1-p) misses the trade -> missed = (1-p)*max(profit,0)
      (missing a loser costs nothing; rung profit = ret*|weight|*eq_idx, book
      episode profit allocated to fills pro-rata by |weight|). TP/timeout
      exits get no extra haircut (same round-trip; avoids double counting).
    stop exits (book_stop/rung_sl): extra cost = 0.5*Bybit_p90_spread*notional
      (half-spread walk; per-coin p90 from oc_spreadcost: BTC 0.0117, ETH
      0.0371, SOL 0.8337, BNB 1.2810, XRP 0.6679 bps).
  Total haircut H(E) in initial-mix-equity units (sum over 4 shifts /4) ->
  monthly drag pp = H(E)/M*100, M = months in the depth window
  (2023-01-01..2026-09-23); adjusted monthly ~= 5.41 - drag. "Material" =
  drag >= 0.5 pp/month.
POST-HOC FIX (logged 2026-10-07, before any REPORT conclusion): the first run
  matched a few orders to bad depth prints with near-zero one-sided notional
  (min $8-$71 vs medians $5M-$135M; stale repeated prints, e.g. XRP ask q0.1%
  = $100), giving absurd r up to 23000%. Snapshots whose relevant side is
  below that side's 0.5th percentile over the archive are now treated as
  missing (depth unknown that minute; counted as n_badprint, excluded from
  shares). Direction: removes fake impact; real thin minutes (>= floor) kept.

Inputs: research/tournament/oc_kpi_g2/events_s{0..3}.parquet (v421 R2B1D17BFG2
replica, 4h-close equity matches v421_runs.pkl to 1e-9) + barsum_s{0..3}.parquet
(phase equity index) + data/raw/bookdepth_20261004/{SYM}_bookdepth_1m.parquet.
Grep of research/ before writing: no prior per-order notional-vs-depth capacity
study exists (v385 = depth-tilt sizing, oc_depthtilt = depth tilt,
oc_spreadcost = quoted spread only, research/diagnostics/newdata_bookdepth =
depth-as-signal screening). Uses no market row >= 2026-09-24. LIGHT (one symbol
of depth at a time, peak < 0.5 GB); runs directly.

Writes ONLY research/tournament/oc_capacity/results.json (+ REPORT.md by hand).
Usage: .venv/Scripts/python.exe research/tournament/oc_capacity/capacity.py
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
EQUITIES = [1_000, 5_000, 10_000, 50_000, 100_000, 500_000]
T0 = pd.Timestamp("2023-01-01", tz="UTC")
T1 = pd.Timestamp("2026-09-24", tz="UTC")  # exclusive cap
MAX_LAG_S = 300
BASE_MONTHLY = 5.41  # v421_result.json row R2B1D17BFG2 5y geometric mean
HALF_P90 = {  # 0.5 * Bybit p90 quoted spread as fraction (oc_spreadcost REPORT)
    "BTCUSDT": 0.5 * 0.0117 / 1e4, "ETHUSDT": 0.5 * 0.0371 / 1e4,
    "SOLUSDT": 0.5 * 0.8337 / 1e4, "BNBUSDT": 0.5 * 1.2810 / 1e4,
    "XRPUSDT": 0.5 * 0.6679 / 1e4}
ENTRY_KINDS = ("rung_fill", "book_fill", "book_add")
STOP_KINDS = ("book_stop", "rung_sl")
ORDER_KINDS = ENTRY_KINDS + ("book_reduce", "book_partial", "rung_sl", "rung_tp",
                             "rung_timeout", "book_stop", "book_tp", "book_close")
MAKER, TAKER = 0.0002, 0.00055


def phase_eq_idx(shift: int):
    bs = pd.read_parquet(G2 / f"barsum_s{shift}.parquet", columns=["t", "equity"])
    t = pd.to_datetime(bs["t"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    o = np.argsort(t)
    return t[o], bs["equity"].to_numpy(float)[o]


def load_orders():
    """All liquidity-consuming G2 orders in [T0, T1) with equity index + profit."""
    frames = []
    for s in range(4):
        ev = pd.read_parquet(G2 / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        ev = ev.sort_values("t").reset_index(drop=True)
        teq, eeq = phase_eq_idx(s)
        tns = ev["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        ev["_eq"] = eeq[np.clip(np.searchsorted(teq, tns, side="right") - 1, 0, len(eeq) - 1)]
        ev["_shift"] = s
        frames.append(ev)
    # --- rung profits: FIFO fill->exit per (shift, symbol), as in oc_kpi_g2 ---
    rung_profit = {}
    for s, ev in enumerate(frames):
        pend: dict[str, deque] = {}
        for i, r in ev.iterrows():
            if r["kind"] == "rung_fill":
                pend.setdefault(r["symbol"], deque()).append(i)
            elif r["kind"] in ("rung_sl", "rung_tp", "rung_timeout"):
                q = pend.get(r["symbol"])
                if q:
                    f = q.popleft()
                    fr = ev.loc[f]
                    rung_profit[(s, f)] = float(r["ret"]) * abs(float(fr["weight"])) * float(fr["_eq"])
    # --- book profits: episode loop (v213/compute_kpi logic) + fill attribution ---
    book_profit = {}  # (shift, event_idx) -> allocated profit (indexed units)
    for s, ev in enumerate(frames):
        pos, fills = {}, {}
        for i, e in ev.iterrows():
            k, sym = e["kind"], e["symbol"]
            if k == "book_fill":
                q = abs(e["weight"]) / e["price"]
                pos[sym] = dict(qty=q, cost=q * e["price"], proc=0.0,
                                fees=q * e["price"] * MAKER,
                                cidx=abs(float(e["weight"])) * float(e["_eq"]))
                fills[sym] = [(i, abs(float(e["weight"])))]
            elif k in ("book_add", "book_partial"):
                o = pos.get(sym)
                if o is None:
                    continue
                if k == "book_add":
                    q = abs(e["weight"]) / e["price"]
                    o["qty"] += q
                    o["cost"] += q * e["price"]
                    o["fees"] += q * e["price"] * MAKER
                    o["cidx"] += abs(float(e["weight"])) * float(e["_eq"])
                    fills[sym].append((i, abs(float(e["weight"]))))
                else:
                    q = min(abs(e["weight"]) / e["price"], o["qty"])
                    o["qty"] -= q
                    o["proc"] += q * e["price"]
                    o["fees"] += q * e["price"] * MAKER
            elif k in ("book_reduce",):
                o = pos.get(sym)
                if o is None:
                    continue
                q = min(abs(e["weight"]) / e["price"], o["qty"])
                o["qty"] -= q
                o["proc"] += q * e["price"]
                o["fees"] += q * e["price"] * MAKER
            elif k in ("book_stop", "book_tp", "book_close"):
                o = pos.pop(sym, None)
                fl = fills.pop(sym, [])
                if o is None:
                    continue
                o["proc"] += o["qty"] * e["price"]
                o["fees"] += o["qty"] * e["price"] * (TAKER if k == "book_stop" else MAKER)
                side = 1  # episodes here are netted symmetric; use signed P&L below
                # signed profit in indexed units: scale price-domain P&L by equity index
                # at exit relative to entry blend (approx: exit eq index)
                pnl_price = o["proc"] - o["cost"] - o["fees"]
                # sign: proceeds vs cost already encode direction only for longs;
                # recover side from first fill event row
                f0 = ev.loc[fl[0][0]]
                sgn = 1 if f0["side"] == "buy" else -1
                pnl_idx = sgn * pnl_price / max(o["cost"], 1e-12) * o["cidx"] if o["cost"] else 0.0
                tot_w = sum(w for _, w in fl) or 1.0
                for fi, w in fl:
                    book_profit[(s, fi)] = float(pnl_idx) * w / tot_w
    rows = []
    for s, ev in enumerate(frames):
        sub = ev[ev["kind"].isin(ORDER_KINDS)]
        for i, r in sub.iterrows():
            t = pd.Timestamp(r["t"])
            if not (T0 <= t < T1):
                continue
            kind = r["kind"]
            leg = "maker_entry" if kind in ENTRY_KINDS else (
                "stop" if kind in STOP_KINDS else "other_exit")
            profit = None
            if (s, i) in rung_profit:
                profit = rung_profit[(s, i)]
            elif (s, i) in book_profit:
                profit = book_profit[(s, i)]
            rows.append(dict(t=t, sym=r["symbol"], side=r["side"], kind=kind,
                             leg=leg, w=abs(float(r["weight"])),
                             eq=float(r["_eq"]), profit=profit, shift=s))
    return pd.DataFrame(rows)


def attach_depth(orders: pd.DataFrame):
    n_unmatched = 0
    n_badprint = 0
    D = np.full(len(orders), np.nan)
    Dt = np.full(len(orders), np.nan)
    med = {}
    for sym in SYMS:
        d = pd.read_parquet(DEPTH / f"{sym}_bookdepth_1m.parquet",
                            columns=["ts", "bid_n1", "ask_n1"])
        ts = pd.to_datetime(d["ts"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        o = np.argsort(ts)
        ts = ts[o]
        bid = d["bid_n1"].to_numpy(float)[o]
        ask = d["ask_n1"].to_numpy(float)[o]
        fl_b, fl_a = float(np.quantile(bid, 0.005)), float(np.quantile(ask, 0.005))
        med[sym] = dict(n=int(len(d)),
                        med_tot1=round(float(np.median(bid + ask)), 0),
                        med_side1=round(float(np.median((bid + ask) / 2)), 0))
        m = orders["sym"].to_numpy() == sym
        idx = np.where(m)[0]
        if len(idx) == 0:
            continue
        tns = orders["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)[idx]
        pos = np.searchsorted(ts, tns, side="left") - 1  # strictly before t
        ok = pos >= 0
        lag = np.full(len(idx), np.inf)
        lag[ok] = (tns[ok] - ts[pos[ok]]) / 1e9
        ok = ok & (lag <= MAX_LAG_S)
        side_buy = (orders["side"].to_numpy()[idx] == "buy")
        pi = np.clip(pos, 0, len(ts) - 1)
        depth = np.where(side_buy, ask[pi], bid[pi])
        floor = np.where(side_buy, fl_a, fl_b)
        ok = ok & (depth >= floor)  # bad prints (stale near-zero side) -> missing
        n_badprint += int(((lag <= MAX_LAG_S) & (pos >= 0) & (depth < floor)).sum())
        D[idx[ok]] = depth[ok]
        Dt[idx[ok]] = (bid + ask)[np.clip(pos[ok], 0, len(ts) - 1)]
        n_unmatched += int((~ok).sum())
        del d, ts, bid, ask
    orders = orders.copy()
    orders["D_side"] = D
    orders["D_tot"] = Dt
    return orders, n_unmatched, n_badprint, med


def main():
    orders = load_orders()
    n_pre2023_excluded = "n/a (filtered in loader)"
    orders, n_unmatched, n_badprint, med = attach_depth(orders)
    m = orders.dropna(subset=["D_side"]).copy()
    # base ratio factor b: r(E) = b * E/4 with b = w*eq/D_side
    m["b"] = m["w"].to_numpy() * m["eq"].to_numpy() / m["D_side"].to_numpy()
    m["b_tot"] = m["w"].to_numpy() * m["eq"].to_numpy() / m["D_tot"].to_numpy()
    months = (T1 - T0).total_seconds() / (30.4375 * 86400)
    per_sym, overall, hair = {}, {}, {}
    for E in EQUITIES:
        r = (m["b"].to_numpy() * E / 4.0)
        r02 = r * 5.0
        ekey = str(E)
        per_sym[ekey] = {}
        for sym in SYMS:
            sel = (m["sym"].to_numpy() == sym)
            rs, r5 = r[sel], r02[sel]
            n = int(sel.sum())
            wsum = float((m["w"] * m["eq"]).to_numpy()[sel].sum())
            over = {}
            for thr in (0.01, 0.05, 0.20):
                c = rs > thr
                over[f"gt{int(thr*100)}_1pct"] = dict(
                    share=round(float(c.mean()), 4) if n else 0.0, n=int(c.sum()))
                c2 = r5 > thr
                over[f"gt{int(thr*100)}_02pct"] = dict(
                    share=round(float(c2.mean()), 4) if n else 0.0, n=int(c2.sum()))
            per_sym[ekey][sym] = dict(
                n=n, med_r=round(float(np.median(rs)), 6),
                p90_r=round(float(np.quantile(rs, 0.9)), 6),
                max_r=round(float(rs.max()), 4), frac=over)
        n = len(m)
        all_over = {}
        for thr in (0.01, 0.05, 0.20):
            all_over[f"gt{int(thr*100)}_1pct"] = round(float((r > thr).mean()), 4)
            all_over[f"gt{int(thr*100)}_02pct"] = round(float((r02 > thr).mean()), 4)
        overall[ekey] = dict(n=n, med_r=round(float(np.median(r)), 6),
                             p90_r=round(float(np.quantile(r, 0.9)), 6),
                             max_r=round(float(r.max()), 4), frac=all_over)
        # --- haircut: entries with r>5%, stops with r>5% ---
        is_entry = m["leg"].to_numpy() == "maker_entry"
        is_stop = np.isin(m["kind"].to_numpy(), list(STOP_KINDS))
        prof = m["profit"].to_numpy(dtype=float)
        missed = np.zeros(len(m))
        aff = r > 0.05
        p = np.ones(len(m))
        p[aff] = 0.05 / r[aff]
        has_prof = np.isfinite(prof)
        gain = np.clip(prof, 0, None)
        missed[is_entry & aff & has_prof] = ((1 - p[is_entry & aff & has_prof])
                                             * gain[is_entry & aff & has_prof])
        n_maker_aff = int((is_entry & aff).sum())
        n_maker_noprof = int((is_entry & aff & ~has_prof).sum())
        stop_hit = is_stop & aff
        wfrac = m["w"].to_numpy() * m["eq"].to_numpy()
        hs = np.array([HALF_P90[s] for s in m["sym"].to_numpy()])
        stop_cost = float((hs[stop_hit] * wfrac[stop_hit]).sum())
        missed_sum = float(missed.sum()) / 4.0  # 4 shifts -> mix units
        stop_sum = stop_cost / 4.0
        H = missed_sum + stop_sum
        drag = H / months * 100
        hair[ekey] = dict(n_maker_above5=int(n_maker_aff),
                          n_maker_noprofit_pair=int(n_maker_noprof),
                          n_stop_above5=int(stop_hit.sum()),
                          missed_frac=round(missed_sum, 6),
                          stop_frac=round(stop_sum, 6),
                          haircut_frac=round(H, 6),
                          drag_pp_month=round(float(drag), 4),
                          adj_monthly=round(BASE_MONTHLY - float(drag), 3))
    out = dict(
        rule=("r=notional(E)/D, D=relevant-side 1% notional, ts strictly before t; "
              "D02=D/5 proxy; notional(E)=|weight|*eq_idx*E/4; makers r>5%: p=0.05/r, "
              "missed=(1-p)*max(profit,0) on entries only; stops r>5%: 0.5*Bybit_p90*notional; "
              "drag_pp=H/months*100 over 2023-01-01..2026-09-23; material=drag>=0.5pp"),
        inputs=dict(g2="research/tournament/oc_kpi_g2/events_s{0..3}.parquet "
                       "(v421 R2B1D17BFG2, equity match 1e-9) + barsum equity index",
                    depth="data/raw/bookdepth_20261004/{SYM}_bookdepth_1m.parquet "
                          "(1%/2%/5% bands; D02=D/5 proxy, disclosed)",
                    base_monthly=BASE_MONTHLY, months_window=round(months, 2),
                    equities=EQUITIES, t_cap="no row >= 2026-09-24 used"),
        coverage=dict(n_orders_window=int(len(orders)),
                      n_matched=int(len(m)),
                      n_unmatched_lag=int(n_unmatched),
                      n_badprint_below_p05=int(n_badprint),
                      depth_medians=med),
        per_symbol=per_sym, overall=overall, haircut=hair)
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"orders={len(orders)} matched={len(m)} unmatched={n_unmatched} badprint={n_badprint} months={months:.2f}")
    for E in EQUITIES:
        ekey = str(E)
        print(E, overall[ekey]["frac"], "drag", hair[ekey]["drag_pp_month"],
              "adj", hair[ekey]["adj_monthly"], "maker>5%",
              hair[ekey]["n_maker_above5"], "stop>5%", hair[ekey]["n_stop_above5"])


if __name__ == "__main__":
    main()
