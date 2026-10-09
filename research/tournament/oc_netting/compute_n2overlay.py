"""oc_netting N2 overlay (PLAN-frozen §2): N1 engine + cross-clock same-direction merge.

LABELLED fee-only approximation, no re-simulation. For each wall-clock hour h
and coin c, phases holding same-direction book targets (close-known ffill) are
merged to ONE TP/stop at the earliest price: redundant exits beyond the first
leg per (h,c,direction) save their exit fee (book_tp maker 0.0002 / book_stop
taker 0.00055 on realised exit notional). Savings enter the pooled mix
accountant A(t)=A(t-1)*g(t)+S(t) (oc_carrycompound form); per-year R/DD use the
same reset convention (rebase 1.0 at each anchor).

Usage:
  .venv/Scripts/python.exe research/tournament/oc_netting/compute_n2overlay.py --stage dev
  .venv/Scripts/python.exe research/tournament/oc_netting/compute_n2overlay.py --stage full
LIGHT: 4h books + stored/N1 runs + N1 events only. No 1m. One coin-bar at a time
in spirit: vectorized per-coin masks, hourly grid ~35k rows.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
MAKER, TAKER = 0.0002, 0.00055


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def books_bear_shift(shift):
    """Recompute the close-known book targets for one shift (4h only, no 1m)."""
    import sys
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v221 = pof._load(f"v221_n2_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwn2_{shift}", ROOT / "scripts/forward_v205.py")
    eu = v221.eu
    books154, _opens_std = eu.er.v154_books()
    sh = pd.Timedelta(hours=shift)
    idx = books154.index + sh
    cols = list(books154.columns)
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    return sb.reindex(idx, method="ffill").fillna(0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "full"], required=True)
    args = ap.parse_args()
    v388 = _load("v388_for_n2", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_for_n2", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    runs = pickle.loads((HERE / "tmp" / f"engine_{args.stage}.pkl").read_bytes())
    allevents = pickle.loads((HERE / "tmp" / f"engine_{args.stage}_events.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    cols = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

    # N1 mixed hourly equity is NOT rebuilt here: with S(h) == 0 the pooled
    # accountant reproduces the N1 mix exactly, so N2 per-year R/DD come from
    # rm.year_reset on the N1 runs (the same function that scored N1) — N2 == N1
    # by construction. The hourly grid below serves the census only (agreement
    # frequency of close-known target signs across clocks).
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    g1 = (v388.Y1 if args.stage == "full" else pd.Timestamp("2025-09-24", tz="UTC")) + pd.Timedelta(hours=12)
    grid = pd.date_range(g0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    # Per-shift active target signs on the hourly grid (holding interval [T,T+4h)).
    sgn = {}
    for s in range(4):
        bb = books_bear_shift(s)
        tstarts = (bb.index + pd.Timedelta(hours=4)).values.astype("datetime64[ns]").astype(np.int64)
        vals = np.sign(bb[cols].to_numpy(float))  # booking-bar decision sign per phase-bar
        pos = np.searchsorted(tstarts, gn, side="right") - 1
        pos = np.clip(pos, 0, len(bb) - 1)
        ok = gn >= tstarts[0]
        g = np.zeros((n, len(cols)))
        g[ok] = vals[pos[ok]]
        sgn[s] = g
    S = np.stack([sgn[s] for s in range(4)])  # (4, n, 5)
    n_long = (S > 0).sum(axis=0)
    n_short = (S < 0).sum(axis=0)

    # Savings census: count redundant exits, then apply the proportional-fee
    # proof. Each phase holds a 1/4-size leg; a merged OMS position carries the
    # SUM notional, so its exit fee at the same proportional rate equals the sum
    # of the legs' fees: saving = sum_i |w_i|*rate - |sum_i w_i|*rate = 0 for
    # same-direction legs at the same rate. (Legs exit at different times via
    # different TP/stop levels; picking a single merged exit time/price would be
    # a strategy change needing pooled re-simulation — excluded.) Hence S(h)=0
    # and N2 == N1 path-wise. The census below documents how often the merge
    # would nominally apply.
    S_save = np.zeros(n)
    n_redundant_exits = 0
    n_book_exits = 0
    saved_by_coin = {c: 0.0 for c in cols}
    for s in range(4):
        for e in allevents[s]["N1"]:
            if e.get("kind") not in ("book_tp", "book_stop"):
                continue
            n_book_exits += 1
            sym = e.get("symbol")
            if sym not in cols:
                continue
            a = cols.index(sym)
            side = e.get("side")  # sell = was LONG, buy = was SHORT
            direction = 1 if side == "sell" else -1
            t = pd.Timestamp(e["t"])
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            else:
                t = t.tz_convert("UTC")
            h = int(np.searchsorted(gn, t.value, side="right")) - 1
            if h < 1 or h >= n:
                continue
            mates = int(n_long[h, a]) if direction > 0 else int(n_short[h, a])
            if mates < 2:
                continue
            if int(np.sign(sgn[s][h, a])) != direction:
                continue  # conservative: own leg must agree at exit hour
            rate = MAKER if e["kind"] == "book_tp" else TAKER
            w = abs(float(e.get("weight", 0.0)))  # fraction of phase bar-start equity
            if not np.isfinite(w) or w <= 0:
                continue
            # Proven zero (see header): merged notional fee == sum of leg fees.
            n_redundant_exits += 1

    # N2 == N1 by the zero-proof: score with the same reset function on N1 runs.
    slim = {s: {"N1": runs[s]["N1"]} for s in range(4)}
    ys = [4] if args.stage == "full" else [0, 1, 2, 3]
    yy = [rm.year_reset(slim, "N1", y) for y in ys]
    years = [{"anchor": str(pd.Timestamp(v388.ANCH[y], tz="UTC").date()),
              "R": yy[i]["R"], "DD": yy[i]["DD"]} for i, y in enumerate(ys)]
    R = round(float(np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1) * 100, 3)
    # agreement census: share of hourly coin-slots with >=2 phases same-direction
    agree = ((n_long >= 2) | (n_short >= 2)).mean()
    out = {"stage": args.stage, "years": years, "R": R,
           "W": min(y["R"] for y in yy), "DD": max(y["DD"] for y in yy),
           "losing": sum(y["R"] < 0 for y in yy),
           "method": "N2==N1 by proportional-fee zero-proof; years via reset_metric.year_reset on N1 runs",
           "agree_share": round(float(agree), 4),
           "n_book_exits": n_book_exits, "n_redundant_exits": n_redundant_exits,
           "saved_abs_total": 0.0,
           "saved_by_coin": {k: 0.0 for k in cols}}
    (HERE / "tmp" / f"n2overlay_{args.stage}.json").write_text(json.dumps(out, indent=1))
    for y in years:
        print(y, flush=True)
    print(f"N2 dev R={out['R']} W={out['W']} DD={out['DD']} "
          f"redundant {n_redundant_exits}/{n_book_exits} saved {out['saved_abs_total']}", flush=True)


if __name__ == "__main__":
    main()
